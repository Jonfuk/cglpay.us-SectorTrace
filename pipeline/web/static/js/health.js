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

/** A compact summary for the evidence-graph card: the card's `card()` helper
 *  takes a single short string, unlike the tables below that can use
 *  `when()`'s full `<time>` element. */
function graphRunLabel(run) {
  if (run.status === 'running') return 'running now';
  if (!run.completed_at) return run.status || 'unknown';
  const parsed = new Date(run.completed_at);
  if (isNaN(parsed)) return run.status || 'unknown';
  const days = Math.round((Date.now() - parsed.getTime()) / 86_400_000);
  const label = days <= 0 ? 'today' : (days === 1 ? 'yesterday' : `${days}d ago`);
  return run.status === 'failed' ? `failed ${label}` : label;
}

// --- warehouse cards -----------------------------------------------------------

async function loadHealth() {
  let data;
  try { data = await api('/api/admin/health'); }
  catch (e) { return $('health-cards').replaceChildren(
    el('div', { class: 'warn', text: e.message })); }

  const w = data.warehouse;
  const schemaOff = w.unapplied.length || w.applied_without_file.length;
  const graph = data.graph || { last_run: null, pending_queue: 0 };
  const run = graph.last_run;
  const docs = data.documents || { registered: 0, parsed: 0, failed: 0, documents: 0 };

  $('health-cards').replaceChildren(
    card(bytes(w.bytes), 'warehouse on disk'),
    card(bytes(w.free_bytes), 'free pages inside it'),
    card(num(w.applied_migrations.length), 'migrations applied'),
    card(schemaOff ? 'behind' : 'current', 'schema', schemaOff ? 'bad' : 'good'),
    card(num(data.hosts.length), 'source hosts'),
    card(run ? graphRunLabel(run) : 'never run', 'evidence graph',
      run && run.status === 'failed' ? 'bad' : null),
    card(num(run ? run.entity_count : null), 'graph entities (last run)'),
    card(num(docs.parsed), `documents parsed${docs.registered ? ` of ${num(docs.registered)}` : ''}`,
      docs.failed ? 'bad' : null),
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

  // PostgreSQL only — the list is empty on SQLite. Each feature has a fallback,
  // so a missing extension is a note, not an alarm: the card says which path
  // the deployment is on.
  const exts = data.extensions || [];
  if (exts.length) {
    $('health-cards').append(...exts.map((ext) => card(
      ext.installed ? (ext.version || 'installed') : (ext.available ? 'not installed' : 'absent'),
      `${ext.name} extension`,
      ext.installed ? 'good' : null)));
    const missing = exts.filter((ext) => !ext.installed);
    if (missing.length) {
      $('health-cards').append(el('div', { class: 'muted small' },
        missing.map((ext) => `${ext.name}: ${ext.backs}.`).join(' ')));
    }
  }

  // PostGIS only. `geom` is derived from `geometry_geojson`; the two counts
  // should agree and `invalid` should be zero.
  const g = data.geometry;
  if (g) {
    const behind = g.with_geom !== g.with_geojson;
    $('health-cards').append(
      card(`${num(g.with_geom)} / ${num(g.with_geojson)}`, 'authority geom built',
        behind ? 'bad' : 'good'),
      card(num(g.invalid), 'invalid boundaries', g.invalid ? 'bad' : 'good'));
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
      el('th', { text: 'Directory' }), el('th', { text: 'Backend' }),
      el('th', { class: 'num', text: 'Files' }), el('th', { class: 'num', text: 'Size' }),
      el('th', { text: 'Mirror lag' }), el('th', { text: 'Newest' }),
      el('th', { text: 'What it is' }))),
    el('tbody', {}, rows.map((row) => el('tr', {},
      el('td', {},
        el('div', { class: 'mono small', text: row.path }),
        row.exists ? null : el('div', { class: 'muted small', text: 'not created yet' })),
      el('td', { class: 'mono small', text: row.backend || '—' }),
      el('td', { class: 'num', text: num(row.files) }),
      el('td', { class: 'num', text: bytes(row.bytes) }),
      el('td', { class: 'num', text: row.mirror_lag
        ? `${num(row.mirror_lag.objects)} objects · ${bytes(row.mirror_lag.bytes)}` : '—' }),
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

/* BETA-104: the validation-rule explorer. Rules are derived on the request —
 * schema rules from the live schema, observed rules from parse_failures and
 * review_queue. Failure examples arrive already reduced to their shape. */
const VR_STATE = { data: null, q: '', kinds: null };
const VR_KIND_LABEL = {
  trigger: 'Trigger', check: 'CHECK', provenance: 'Provenance',
  parse_failure: 'Parse failure', review_gate: 'Review gate',
};

function vrRuleCard(rule) {
  const bits = [];
  if (rule.counts) {
    if (rule.kind === 'parse_failure') {
      bits.push(el('span', { class: 'badge type', text: `${rule.counts.total} total` }));
      if (rule.counts.recent) bits.push(el('span', { class: 'badge pending', text: `${rule.counts.recent} in ${VR_STATE.data.window_days}d` }));
    } else if (rule.kind === 'review_gate') {
      if (rule.counts.pending) bits.push(el('span', { class: 'badge pending', text: `${rule.counts.pending} pending` }));
      bits.push(el('span', { class: 'badge approved', text: `${rule.counts.resolved} resolved` }));
    }
  }
  if (rule.kind === 'provenance') {
    bits.push(el('span', { class: `badge ${rule.enforced ? 'approved' : 'rejected'}`,
      text: rule.enforced ? 'enforced' : 'not enforced' }));
  }

  const examples = (rule.examples || []).length
    ? el('details', { class: 'vr-examples' },
        el('summary', { class: 'small', text: `${rule.examples.length} representative failure${rule.examples.length === 1 ? '' : 's'} (shape only)` }),
        el('ul', { class: 'small' }, ...rule.examples.map((ex) => el('li', {},
          el('span', { class: 'mono', text: ex.shape || '(empty)' }),
          el('span', { class: 'muted', text: ` — ${ex.reason || 'no reason'} · ${ex.source_host || 'no host'} · ${(ex.at || '').slice(0, 10)} · ${ex.chars} chars` })))))
    : null;

  return el('div', { class: 'vr-rule' },
    el('div', { class: 'vr-rule-head' },
      el('span', { class: 'badge muted', text: VR_KIND_LABEL[rule.kind] || rule.kind }),
      el('span', { class: 'mono small', text: ` ${rule.id}` }),
      ...bits),
    el('div', { class: 'small', text: rule.title }),
    rule.purpose ? el('p', { class: 'muted small', text: rule.purpose }) : null,
    rule.detail ? el('p', { class: 'small mono', text: rule.detail }) : null,
    rule.reasons?.length ? el('p', { class: 'muted small', text: `reasons: ${rule.reasons.join('; ')}` }) : null,
    examples);
}

function vrRender() {
  const holder = $('validation-rules');
  const d = VR_STATE.data;
  if (!holder || !d) return;
  const q = VR_STATE.q.toLowerCase();
  const all = [...d.schema_rules, ...d.observed_rules].filter((r) =>
    VR_STATE.kinds.has(r.kind)
    && (!q || `${r.id} ${r.title} ${r.purpose}`.toLowerCase().includes(q)));
  holder.replaceChildren(...(all.length
    ? all.map(vrRuleCard)
    : [el('p', { class: 'muted small', text: 'No rules match.' })]));
}

async function loadValidationRules() {
  const holder = $('validation-rules');
  if (!holder || VR_STATE.data) return;
  let data;
  try { data = await api('/api/admin/validation-rules'); }
  catch (e) { holder.replaceChildren(el('p', { class: 'muted small', text: 'Validation rules unavailable.' })); return; }
  VR_STATE.data = data;
  VR_STATE.kinds = new Set(data.kinds);
  $('validation-note').textContent = `${data.note} Redaction: ${data.redaction}.`;

  const kindWrap = $('vr-kinds');
  if (kindWrap && !kindWrap.dataset.filled) {
    kindWrap.replaceChildren(...data.kinds.map((k) => {
      const box = el('input', { type: 'checkbox', checked: true,
        onchange: (e) => { e.target.checked ? VR_STATE.kinds.add(k) : VR_STATE.kinds.delete(k); vrRender(); } });
      return el('label', { class: 'small' }, box, ` ${VR_KIND_LABEL[k] || k} (${data.counts.by_kind[k] || 0})`);
    }));
    kindWrap.dataset.filled = '1';
  }
  const search = $('vr-search');
  if (search && !search.dataset.wired) {
    search.addEventListener('input', () => { VR_STATE.q = search.value; vrRender(); });
    search.dataset.wired = '1';
  }
  vrRender();
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
  loadCompleteness();
  loadArchiveAudits();
  loadUrlOverlaps();
  loadPgCapabilities();
}

/* BETA-063: PostgreSQL extension + extension-backed-index readiness, and the
 * query paths currently on their fallback. Empty on SQLite — the gate does
 * not apply there. Not lazy: it is two catalogue lookups. */
async function loadPgCapabilities() {
  const holder = $('pg-capabilities');
  if (!holder) return;

  let data;
  try { data = await api('/api/admin/pg-capabilities'); }
  catch (e) { holder.replaceChildren(el('p', { class: 'bad small', text: e.message })); return; }

  if (!data.applies) {
    return holder.replaceChildren(el('p', { class: 'muted small', text: data.note }));
  }

  const parts = [
    el('p', { class: 'small' },
      el('strong', { text: data.ready ? 'ready' : 'degraded' }),
      el('span', { class: 'muted', text: ` · PostgreSQL ${data.server_version}` })),
  ];

  parts.push(el('table', {},
    el('thead', {}, el('tr', {},
      el('th', { text: 'Index' }), el('th', { text: 'Extension' }),
      el('th', { text: 'Expected' }), el('th', { text: 'State' }))),
    el('tbody', {}, data.indexes.map((row) => el('tr', {},
      el('td', { class: 'mono small', text: row.index }),
      el('td', { class: 'small', text: row.extension }),
      el('td', { class: 'mono small',
        text: row.expected_opclass
          ? `${row.expected_method} / ${row.expected_opclass}` : row.expected_method }),
      el('td', { class: row.healthy ? 'small good' : 'small bad',
        text: row.healthy ? 'ok'
          : (!row.present ? 'missing'
            : (!row.method_ok ? 'wrong method' : 'wrong opclass')) }))))));

  const fallbacks = data.active_fallbacks || [];
  if (fallbacks.length) {
    parts.push(el('p', { class: 'small bad',
      text: `${fallbacks.length} query path(s) on a fallback:` }));
    parts.push(el('ul', { class: 'small' }, fallbacks.map((f) => el('li', {},
      el('span', { text: f.feature }),
      el('span', { class: 'muted', text: ` — ${f.reason}; using ${f.fallback}` })))));
  } else {
    parts.push(el('p', { class: 'muted small',
      text: 'Every extension-backed query path is on its accelerated index.' }));
  }

  (data.notes || []).forEach((note) =>
    parts.push(el('p', { class: 'muted small', text: note })));

  holder.replaceChildren(...parts);
}

/* BETA-057: one canonical URL appearing in more than one source table. A
 * lead a reviewer looks at — not a merge instruction. Loaded lazily on the
 * <details> first-expand because it scans several tables. */
async function loadUrlOverlaps() {
  const holder = $('url-overlaps');
  if (!holder) return;
  const details = holder.closest('details');
  if (details && !details.open) {
    if (!details.dataset.wired) {
      details.dataset.wired = '1';
      details.addEventListener('toggle', () => {
        if (details.open && !details.dataset.loaded) {
          details.dataset.loaded = '1';
          loadUrlOverlaps();
        }
      });
    }
    return;
  }

  holder.replaceChildren(el('p', { class: 'muted small', text: 'Scanning…' }));
  let data;
  try { data = await api('/api/admin/url-overlaps'); }
  catch (e) { holder.replaceChildren(el('p', { class: 'bad small', text: e.message })); return; }

  const groups = data.overlaps || [];
  if (!groups.length) {
    return holder.replaceChildren(el('p', { class: 'muted small',
      text: `No overlaps found across ${data.scanned} URLs.` }));
  }

  holder.replaceChildren(
    el('p', { class: 'muted small',
      text: `${data.total} overlap(s) over ${data.scanned} URLs` }),
    ...groups.map((g) => el('details', {},
      el('summary', { class: 'small' },
        el('strong', { text: g.canonical_url }), ' ',
        el('span', { class: 'muted', text: `· ${g.distinct_sources} sources` })),
      el('table', {}, el('tbody', {}, g.occurrences.map((o) => el('tr', {},
        el('td', { class: 'muted small', text: o.table }),
        el('td', { class: 'small', text: o.role }),
        el('td', { class: 'num', text: String(o.row_count) }),
        el('td', {}, el('a', { href: o.raw_url, target: '_blank', rel: 'noopener',
          class: 'small', text: o.raw_url })))))))));
}

/* BETA-060: the append-only archive-audit history. Read-only — recording one
 * is `pipeline archive-audit`. */
function _bytes(n) {
  if (!n) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0; let v = Number(n);
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

async function loadArchiveAudits() {
  const holder = $('archive-audits');
  if (!holder) return;
  let data;
  try { data = await api('/api/admin/archive-audits'); }
  catch (e) { return; }

  const audits = data.audits || [];
  if (!audits.length) {
    return holder.replaceChildren(el('p', { class: 'muted small',
      text: 'No audits recorded yet — run `pipeline archive-audit`.' }));
  }

  const rows = audits.map((a) => el('tr', {},
    el('td', { class: 'muted small', text: (a.run_at || '').replace('T', ' ').slice(0, 16) }),
    el('td', { class: 'num', text: Number(a.object_count).toLocaleString('en-GB') }),
    el('td', { class: 'num', text: _bytes(a.total_bytes) }),
    el('td', { class: `num${a.missing_refs ? ' bad' : ''}`, text: String(a.missing_refs) }),
    el('td', { class: 'num', text: String(a.duplicate_hashes) }),
    el('td', { class: 'muted small mono', title: a.git_revision || '',
      text: (a.git_revision || '').slice(0, 10) })));

  holder.replaceChildren(el('table', {},
    el('thead', {}, el('tr', {},
      el('th', { text: 'When' }), el('th', { text: 'Objects' }),
      el('th', { text: 'Size' }), el('th', { text: 'Unarchived refs' }),
      el('th', { text: 'Dup hashes' }), el('th', { text: 'Revision' }))),
    el('tbody', {}, rows)));
}

/* BETA-059: the coverage completion action board. One reason code + one
 * non-destructive next step per catalogued dataset. */
const _REASON_LABEL = {
  run_needed: 'run needed', review_needed: 'review needed',
  source_blocked: 'source blocked', not_published: 'not published',
  complete: 'complete',
};

function _actionNode(action) {
  if (action.kind === 'run') {
    return el('a', { href: '#pipeline', title: 'Open the Pipeline tab to run it' },
      action.label);
  }
  if (action.kind === 'review') {
    return el('a', {
      href: `#review?module=${encodeURIComponent(action.target)}&status=pending`,
      title: 'Open the Review queue filtered to this module',
    }, action.label);
  }
  return el('a', {
    href: `/#/catalogue?dataset=${encodeURIComponent(action.target)}`,
    target: '_blank', rel: 'noopener',
    title: 'Open this dataset in the public catalogue',
  }, action.label);
}

async function loadCompleteness() {
  const board = $('completeness-board');
  if (!board) return;
  let data;
  try { data = await api('/api/admin/completeness'); }
  catch (e) { return; }

  $('completeness-summary').replaceChildren(
    ...data.reasons.map((r) => el('span', { class: 'chip',
      text: `${_REASON_LABEL[r]}: ${data.by_reason[r] || 0}` })));

  const rows = data.datasets.map((d) => el('tr', {},
    el('td', {}, el('span', {
      class: `badge ${d.reason === 'complete' ? 'approved'
        : (d.reason === 'run_needed' ? 'rejected' : 'pending')}`,
      text: _REASON_LABEL[d.reason] })),
    el('td', { text: d.title }),
    el('td', { class: 'muted small mono', text: d.module }),
    el('td', { class: 'num', text: String(d.row_count) }),
    el('td', {}, _actionNode(d.action)),
    el('td', { class: 'muted small', text: d.reason_note || '' })));

  board.replaceChildren(el('table', {},
    el('thead', {}, el('tr', {},
      el('th', { text: 'Reason' }), el('th', { text: 'Dataset' }),
      el('th', { text: 'Module' }), el('th', { text: 'Rows' }),
      el('th', { text: 'Next step' }), el('th', { text: 'Note' }))),
    el('tbody', {}, rows)));
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

  // BETA-104: fetch the validation-rule catalogue the first time its panel
  // is opened. Registry-derived plus recent counts — not worth polling.
  $('validation-panel')?.addEventListener('toggle', (event) => {
    if (event.target.open) loadValidationRules();
  });

  document.addEventListener('tabshown', (event) => {
    if (event.detail.tab === 'health') loadAll();
  });

  // app.js has already routed the opening hash by the time this module runs.
  if ($('tab-health').classList.contains('active')) loadAll();
}
