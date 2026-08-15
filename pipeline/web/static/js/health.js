/* The Health tab: freshness, coverage, and the parser bug list.
 *
 * The coverage matrix is the part with a wrong answer available. England has
 * 347 local authorities in this warehouse and 159 of them are responsible for
 * public health; counting against 347 turns "155 of the 159 authorities that
 * could have a grant" into "45% coverage", which is a number someone would
 * put in a document. So the denominator is printed above the matrix in words,
 * the tier that produced it is named, and switching to every authority is a
 * deliberate act with its own explanation.
 */
import { el, store } from './dom.js';

const $ = (id) => document.getElementById(id);

const state = { coverage: null, filter: '', tier: 'upper' };

async function api(path) {
  const response = await fetch(path);
  let payload = null;
  try { payload = await response.json(); } catch (e) { /* not JSON */ }
  if (!response.ok) throw new Error((payload && payload.error) || response.statusText);
  return payload;
}

function bytes(n) {
  if (!n) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

const num = (n) => (n === null || n === undefined ? '—' : Number(n).toLocaleString('en-GB'));

function card(value, label, kind) {
  return el('div', { class: 'card' },
    el('div', { class: `n${kind ? ` ${kind}` : ''}`, text: value }),
    el('div', { class: 'label', text: label }));
}

/** A <time> with the exact value on hover, matching the rest of the UI. */
function when(iso) {
  if (!iso) return el('span', { class: 'muted', text: '—' });
  const parsed = new Date(iso);
  if (isNaN(parsed)) return document.createTextNode(String(iso));
  const days = Math.round((Date.now() - parsed.getTime()) / 86_400_000);
  const text = days <= 0 ? 'today' : (days === 1 ? 'yesterday' : `${days} days ago`);
  return el('time', { datetime: parsed.toISOString(), title: iso, text });
}

// --- warehouse cards -----------------------------------------------------------

async function loadHealth() {
  let data;
  try { data = await api('/api/admin/health'); }
  catch (e) { return $('health-cards').replaceChildren(
    el('div', { class: 'warn', text: e.message })); }

  const w = data.warehouse;
  const schemaOff = w.unapplied.length || w.applied_without_file.length;

  $('health-cards').replaceChildren(
    card(bytes(w.bytes), 'warehouse on disk'),
    card(bytes(w.free_bytes), 'free pages inside it'),
    card(num(w.applied_migrations.length), 'migrations applied'),
    card(schemaOff ? 'behind' : 'current', 'schema', schemaOff ? 'bad' : 'good'),
    card(num(data.hosts.length), 'source hosts'),
    el('div', { class: 'card' },
      el('button', { class: 'btn', id: 'integrity-run' }, 'Check integrity'),
      el('div', { class: 'label', id: 'integrity-result',
                   text: 'reads every page; runs as a job' })));

  $('integrity-run').addEventListener('click', runIntegrity);

  if (schemaOff) {
    $('health-cards').append(el('div', { class: 'warn' },
      w.unapplied.length
        ? `Not applied to this warehouse: ${w.unapplied.join(', ')}. `
          + 'A module will fail on a missing column part-way through a run.'
        : `Applied but no longer in the checkout: ${w.applied_without_file.join(', ')}.`));
  }

  renderHosts(data.hosts);
}

/* What this pipeline is holding on disk, beside the warehouse.
 *
 * The archive is the audit trail and cannot be deleted, so the answer to its
 * growth is to watch it — and until now the only instrument was a one-off
 * measurement written into the roadmap. A table rather than cards: the
 * interesting comparison is between the four directories, and four numbers
 * that have to be read against each other belong in rows.
 *
 * On its own request, like freshness: stat-ing 8,502 archived files takes six
 * seconds on the real archive, and the cards above have no reason to wait.
 */
async function loadStorage() {
  $('health-storage').replaceChildren(
    el('div', { class: 'muted small', text: 'measuring…' }));
  try { renderStorage((await api('/api/admin/storage')).storage); }
  catch (e) {
    $('health-storage').replaceChildren(el('div', { class: 'warn', text: e.message }));
  }
}

function renderStorage(rows) {
  const target = $('health-storage');
  if (!target) return;

  target.replaceChildren(el('table', {},
    el('thead', {}, el('tr', {},
      el('th', { text: 'Directory' }), el('th', { class: 'num', text: 'Files' }),
      el('th', { class: 'num', text: 'Size' }), el('th', { text: 'Newest' }),
      el('th', { text: 'What it is' }))),
    el('tbody', {}, rows.map((row) => el('tr', {},
      el('td', {},
        el('div', { class: 'mono small', text: row.path }),
        row.exists ? null : el('div', { class: 'muted small', text: 'not created yet' })),
      el('td', { class: 'num', text: num(row.files) }),
      el('td', { class: 'num', text: bytes(row.bytes) }),
      el('td', {}, when(row.newest)),
      el('td', { class: 'muted small', text: row.note }))))));
}

/* Separately, and last. On the real warehouse this is a couple of seconds of
 * table scans, and the rest of the tab has no reason to wait for it. */
async function loadFreshness() {
  $('health-freshness').replaceChildren(
    el('div', { class: 'muted small', text: 'measuring…' }));
  try { renderFreshness((await api('/api/admin/freshness')).freshness); }
  catch (e) {
    $('health-freshness').replaceChildren(el('div', { class: 'warn', text: e.message }));
  }
}

function renderHosts(hosts) {
  $('health-hosts').replaceChildren(el('table', {},
    el('thead', {}, el('tr', {},
      el('th', { text: 'Host' }), el('th', { class: 'num', text: 'URLs' }),
      el('th', { text: 'Last asked' }))),
    el('tbody', {}, hosts.length
      ? hosts.map((host) => el('tr', {},
        el('td', { class: 'mono', text: host.host }),
        el('td', { class: 'num', text: num(host.urls) }),
        el('td', {}, when(host.newest))))
      : el('tr', {}, el('td', { colspan: '3', class: 'empty',
          text: 'Nothing fetched yet.' })))));
}

function renderFreshness(rows) {
  const withRows = rows.filter((row) => row.rows > 0);
  $('health-freshness').replaceChildren(el('table', {},
    el('thead', {}, el('tr', {},
      el('th', { text: 'Table' }), el('th', { class: 'num', text: 'Rows' }),
      el('th', { text: 'Newest' }), el('th', { text: 'Oldest' }))),
    el('tbody', {}, withRows.length
      ? withRows.map((row) => el('tr', {},
        el('td', { class: 'mono', text: row.table }),
        el('td', { class: 'num', text: num(row.rows) }),
        el('td', {}, when(row.newest)),
        el('td', {}, when(row.oldest))))
      : el('tr', {}, el('td', { colspan: '4', class: 'empty', text: 'No evidence yet.' })))));
}

async function runIntegrity() {
  const button = $('integrity-run');
  const result = $('integrity-result');
  button.disabled = true;
  result.textContent = 'checking…';

  let job;
  try {
    job = await (await fetch('/api/admin/check', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    })).json();
  } catch (e) {
    button.disabled = false;
    result.textContent = e.message;
    return;
  }
  if (!job.id) {
    // Most likely a 409: a module run has the slot, which is correct — both
    // want the whole warehouse.
    button.disabled = false;
    result.textContent = job.error || 'could not start';
    return;
  }

  const poll = setInterval(async () => {
    let current;
    try { current = await api(`/api/admin/jobs/${job.id}`); }
    catch (e) { clearInterval(poll); button.disabled = false; result.textContent = e.message; return; }
    if (current.state === 'running') return;

    clearInterval(poll);
    button.disabled = false;
    const outcome = (current.summary || [])[0];
    if (current.state === 'failed' || !outcome) {
      result.textContent = current.error || 'check failed';
      result.className = 'label bad';
    } else if (outcome.ok) {
      // What was checked differs by backend and the difference matters:
      // SQLite walks every page of the file, PostgreSQL cannot and sweeps the
      // foreign keys instead. "No corruption found" would claim the same
      // thing for both, so the panel says what it looked at.
      result.textContent = outcome.checked
        ? `no problems found in ${outcome.checked}`
        : 'no corruption found';
      result.title = outcome.not_checked || '';
      result.className = 'label good';
    } else {
      result.textContent = `${outcome.integrity.slice(0, 2).join('; ')}`
        + (outcome.foreign_key_violation_count
          ? ` · ${outcome.foreign_key_violation_count} foreign-key violations` : '');
      result.className = 'label bad';
    }
  }, 500);
}

// --- coverage --------------------------------------------------------------------

async function loadCoverage() {
  try { state.coverage = await api(`/api/admin/coverage?tier=${state.tier}`); }
  catch (e) { return $('coverage-note').textContent = e.message; }
  renderCoverage();
}

function renderCoverage() {
  const data = state.coverage;
  if (!data) return;

  const total = data.authority_count;
  $('coverage-note').replaceChildren(
    data.tier === 'upper'
      ? el('span', {}, `${num(total)} authorities responsible for public health `,
        el('span', { class: 'muted',
          text: `(${data.upper_tier_types.join(', ').replace(/_/g, ' ')})` }),
        '. Non-metropolitan districts have no treatment role and are not counted: '
        + 'including them would report every one of them as a gap.')
      : el('span', {}, `Every authority in the warehouse — ${num(total)} of them. `,
        el('span', { class: 'bad',
          text: 'Most will be blank for most columns by design: districts are not '
            + 'responsible for public health. Read a percentage from this view '
            + 'with care.' })));

  const term = state.filter.trim().toLowerCase();
  const rows = data.authorities.filter((authority) =>
    !term || authority.name.toLowerCase().includes(term)
    || (authority.region || '').toLowerCase().includes(term)
    || authority.ons_code.toLowerCase().includes(term));

  const header = el('tr', {},
    el('th', { class: 'sticky-left', text: 'Authority' }),
    el('th', { text: 'Region' }),
    ...data.columns.map((column) => el('th', {
      class: 'rot',
      title: `${column.table} — ${column.module}`
        + (column.missing ? ' (table not in this warehouse)' : ''),
    },
      el('div', { text: column.label }),
      el('div', { class: 'muted small', text: `${num(column.covered)}/${num(total)}` }))));

  const body = rows.map((authority) => el('tr', {},
    el('td', { class: 'sticky-left' },
      el('span', { text: authority.name }),
      el('span', { class: 'muted small mono', text: ` ${authority.ons_code}` })),
    el('td', { class: 'muted small', text: authority.region || '—' }),
    ...data.columns.map((column) => {
      const count = authority.cells[column.label];
      return count
        ? el('td', { class: 'cell has', title: `${num(count)} rows in ${column.table}`,
                      text: count > 999 ? '●' : String(count) })
        : el('td', { class: 'cell', title: `nothing in ${column.table}`, text: '' });
    })));

  $('coverage-table').replaceChildren(
    el('thead', {}, header),
    el('tbody', {}, body.length ? body
      : el('tr', {}, el('td', { colspan: String(data.columns.length + 2),
          class: 'empty', text: 'No authority matches.' }))));
}

// --- parse failures ----------------------------------------------------------------

function failureQuery() {
  const params = new URLSearchParams();
  if ($('failure-module').value) params.set('module', $('failure-module').value);
  if ($('failure-search').value.trim()) params.set('q', $('failure-search').value.trim());
  params.set('limit', '30');
  return params.toString();
}

async function loadFailures() {
  let data;
  try { data = await api(`/api/admin/failures?${failureQuery()}`); }
  catch (e) { return $('failure-groups').replaceChildren(
    el('div', { class: 'warn', text: e.message })); }

  const select = $('failure-module');
  if (select.options.length <= 1 && data.modules.length) {
    select.append(...data.modules.map((name) => el('option', { value: name, text: name })));
  }

  $('failure-groups').replaceChildren(el('table', {},
    el('thead', {}, el('tr', {},
      el('th', { class: 'num', text: 'N' }), el('th', { text: 'Module' }),
      el('th', { text: 'Field' }), el('th', { text: 'Reason' }))),
    el('tbody', {}, data.groups.length
      ? data.groups.map((group) => el('tr', {},
        el('td', { class: 'num', text: num(group.n) }),
        el('td', {}, el('span', { class: 'badge module', text: group.module })),
        el('td', { class: 'mono small', text: group.field_name || '—' }),
        el('td', { class: 'small', text: group.reason || '—' })))
      : el('tr', {}, el('td', { colspan: '4', class: 'empty',
          text: 'No parse failures. Every field this pipeline read, it read.' })))));

  $('failure-rows').replaceChildren(el('table', {},
    el('tbody', {}, data.rows.length
      ? data.rows.map((row) => el('tr', {},
        el('td', {},
          el('div', { class: 'mono small', text: row.raw_fragment || '(empty)' }),
          el('div', { class: 'muted small', text: `${row.module} · ${row.field_name || '—'} · ${row.reason || ''}` }),
          row.source_url
            ? el('a', { href: row.source_url, target: '_blank',
                         rel: 'noopener noreferrer', class: 'small',
                         text: row.source_url })
            : null)))
      : el('tr', {}, el('td', { class: 'empty', text: '—' })))));
}

// --- wiring ---------------------------------------------------------------------------

function debounce(fn, ms) {
  let timer = null;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

function loadAll() {
  loadHealth();
  loadCoverage();
  loadFailures();
  loadStorage();
  loadFreshness();
}

export function initHealth() {
  if (!$('coverage-table')) return;

  state.tier = store.get('cglpay.coverage.tier', 'upper');
  $('coverage-tier').value = state.tier;
  $('coverage-tier').addEventListener('change', (event) => {
    state.tier = event.target.value;
    store.set('cglpay.coverage.tier', state.tier);
    loadCoverage();
  });

  $('coverage-filter').addEventListener('input', debounce((event) => {
    state.filter = event.target.value;
    renderCoverage();
  }, 150));

  $('failure-module').addEventListener('change', loadFailures);
  $('failure-search').addEventListener('input', debounce(loadFailures, 250));

  document.addEventListener('tabshown', (event) => {
    if (event.detail.tab === 'health') loadAll();
  });

  // app.js has already routed the opening hash by the time this module runs.
  if ($('tab-health').classList.contains('active')) loadAll();
}
