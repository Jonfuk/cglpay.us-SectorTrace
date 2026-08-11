/* The whole front end. No framework, no build step.
 *
 * One rule runs through it: every value that came out of the database is put
 * on the page as a text node or an attribute set through the DOM, never by
 * concatenating HTML. This warehouse is full of scraped council pages, PDF
 * extracts and FOI text — strings that arrived from the open web and are
 * displayed back here — so building markup out of them by hand would be
 * running whatever they happen to contain.
 */
'use strict';

// --- small helpers ----------------------------------------------------------

function el(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'html') throw new Error('no raw HTML');
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const $ = (sel) => document.querySelector(sel);
const num = (n) => (n === null || n === undefined ? '—' : Number(n).toLocaleString('en-GB'));

function bytes(n) {
  if (!n) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function when(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return String(iso);
  return d.toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' });
}

/** A link only for http(s). Anything else stays plain text — a value from the
 *  database is not permitted to decide what a click does. */
function maybeLink(value) {
  const text = String(value ?? '');
  if (/^https?:\/\//i.test(text)) {
    return el('a', { href: text, target: '_blank', rel: 'noopener noreferrer', text });
  }
  return document.createTextNode(text);
}

let toastTimer = null;
function toast(message, isError) {
  const box = $('#toast');
  box.textContent = message;
  box.className = isError ? 'toast error' : 'toast';
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; }, isError ? 9000 : 4000);
}

async function api(path, options) {
  const response = await fetch(path, options);
  let payload = null;
  try { payload = await response.json(); } catch (e) { /* non-JSON error page */ }
  if (!response.ok) {
    const message = (payload && payload.error) || `${response.status} ${response.statusText}`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return payload;
}

const post = (path, body) => api(path, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

function replace(container, ...children) {
  container.replaceChildren(...children.flat().filter(Boolean));
}

// --- tabs -------------------------------------------------------------------

const TABS = ['overview', 'review', 'database', 'sql'];
let currentTab = 'overview';

function showTab(name) {
  if (!TABS.includes(name)) name = 'overview';
  currentTab = name;
  for (const tab of TABS) {
    $(`#tab-${tab}`).classList.toggle('active', tab === name);
    const button = document.querySelector(`.tab[data-tab="${tab}"]`);
    button.setAttribute('aria-selected', String(tab === name));
  }
  if (location.hash.slice(1).split('?')[0] !== name) history.replaceState(null, '', `#${name}`);
  if (name === 'overview') loadOverview();
  if (name === 'review') loadReview();
  if (name === 'database') loadSchema();
}

// --- reviewer identity ------------------------------------------------------

function reviewer() {
  return $('#reviewer').value.trim();
}

function requireReviewer() {
  const name = reviewer();
  if (!name) {
    toast('Enter your name in the Reviewer box first — decisions are recorded against it.', true);
    $('#reviewer').focus();
    return null;
  }
  localStorage.setItem('cglpay.reviewer', name);
  return name;
}

// --- overview ---------------------------------------------------------------

async function loadOverview() {
  let data;
  try { data = await api('/api/overview'); }
  catch (e) { return toast(e.message, true); }

  $('#db-path').textContent = data.database.path;
  $('#pending-pill').textContent = num(data.review.statuses.pending);

  const card = (n, label) => el('div', { class: 'card' },
    el('div', { class: 'n', text: num(n) }), el('div', { class: 'label', text: label }));

  replace($('#overview-cards'),
    card(data.review.statuses.pending, 'pending review'),
    card(data.review.statuses.approved, 'approved'),
    card(data.review.statuses.rejected, 'rejected'),
    card(data.parse_failures.total, 'parse failures'),
    card(data.database.tables, 'tables'),
    card(data.database.views, 'views'),
    el('div', { class: 'card' },
      el('div', { class: 'n', text: bytes(data.database.size_bytes) }),
      el('div', { class: 'label', text: `warehouse · ${data.database.migrations} migrations` })));

  // Pending by module and item type.
  const rows = data.review.item_types.map((row) => el('tr', {
    class: 'clickable',
    title: 'Open in the review queue',
    onclick: () => {
      $('#f-status').value = 'pending';
      $('#f-module').value = row.module;
      populateItemTypes(row.module);
      $('#f-type').value = row.item_type;
      reviewState.offset = 0;
      showTab('review');
    },
  },
    el('td', {}, el('span', { class: 'badge module', text: row.module })),
    el('td', {}, el('span', { class: 'badge type', text: row.item_type })),
    el('td', { class: 'num', text: num(row.pending) }),
    el('td', { class: 'num muted', text: num(row.total) })));

  replace($('#overview-types'), el('table', {},
    el('thead', {}, el('tr', {},
      el('th', { text: 'Module' }), el('th', { text: 'Item type' }),
      el('th', { class: 'num', text: 'Pending' }), el('th', { class: 'num', text: 'All' }))),
    el('tbody', {}, rows.length ? rows
      : el('tr', {}, el('td', { colspan: '4', class: 'empty', text: 'Queue is empty.' })))));

  // Recent decisions.
  const decisions = data.recent_decisions.map((d) => el('tr', {},
    el('td', {}, el('span', { class: `badge ${d.decision}`, text: d.decision })),
    el('td', {}, el('div', { class: 'mono', text: d.raw_value.slice(0, 90) }),
      el('div', { class: 'muted small', text: `${d.module} · ${d.item_type}` }),
      d.note ? el('div', { class: 'small', text: `“${d.note}”` }) : null),
    el('td', { class: 'muted small' }, el('div', { text: d.decided_by }), el('div', { text: when(d.decided_at) }))));

  replace($('#overview-decisions'), el('table', {}, el('tbody', {},
    decisions.length ? decisions
      : el('tr', {}, el('td', { class: 'empty', text: 'Nothing decided yet.' })))));

  // Parse failures.
  const failures = data.parse_failures.groups.map((f) => el('tr', {},
    el('td', {}, el('span', { class: 'badge module', text: f.module })),
    el('td', {}, el('div', { text: f.reason || '—' }),
      f.field_name ? el('div', { class: 'muted small mono', text: f.field_name }) : null),
    el('td', { class: 'num', text: num(f.n) })));

  replace($('#overview-failures'), el('table', {},
    el('thead', {}, el('tr', {},
      el('th', { text: 'Module' }), el('th', { text: 'Reason' }), el('th', { class: 'num', text: 'Rows' }))),
    el('tbody', {}, failures.length ? failures
      : el('tr', {}, el('td', { colspan: '3', class: 'empty', text: 'No parse failures.' })))));
}

// --- review queue -----------------------------------------------------------

const reviewState = { offset: 0, total: 0, items: [], focus: -1, facets: null };
const selected = new Set();

function reviewQuery() {
  const params = new URLSearchParams({
    status: $('#f-status').value,
    limit: $('#f-limit').value,
    offset: String(reviewState.offset),
  });
  if ($('#f-module').value) params.set('module', $('#f-module').value);
  if ($('#f-type').value) params.set('item_type', $('#f-type').value);
  if ($('#f-search').value.trim()) params.set('q', $('#f-search').value.trim());
  if (!$('#f-oldest').checked) params.set('newest_first', '1');
  return params;
}

function populateItemTypes(moduleName) {
  const select = $('#f-type');
  const previous = select.value;
  const types = (reviewState.facets ? reviewState.facets.item_types : [])
    .filter((t) => !moduleName || t.module === moduleName);
  const seen = new Set();
  const options = [el('option', { value: '', text: 'All types' })];
  for (const t of types) {
    if (seen.has(t.item_type)) continue;
    seen.add(t.item_type);
    options.push(el('option', { value: t.item_type, text: `${t.item_type} (${num(t.pending)})` }));
  }
  replace(select, options);
  select.value = seen.has(previous) ? previous : '';
}

async function loadFacets() {
  try { reviewState.facets = await api('/api/review/facets'); }
  catch (e) { return toast(e.message, true); }

  $('#pending-pill').textContent = num(reviewState.facets.statuses.pending);

  const moduleSelect = $('#f-module');
  const previous = moduleSelect.value;
  replace(moduleSelect, [
    el('option', { value: '', text: 'All modules' }),
    ...reviewState.facets.modules.map((m) =>
      el('option', { value: m.module, text: `${m.module} (${num(m.pending)})` })),
  ]);
  moduleSelect.value = previous;
  populateItemTypes(previous);
}

async function loadReview() {
  if (!reviewState.facets) await loadFacets();
  let data;
  try { data = await api(`/api/review?${reviewQuery()}`); }
  catch (e) { return toast(e.message, true); }

  reviewState.items = data.items;
  reviewState.total = data.total;
  reviewState.focus = data.items.length ? 0 : -1;

  const from = data.total ? data.offset + 1 : 0;
  const to = Math.min(data.offset + data.limit, data.total);
  $('#review-count').textContent = `${num(from)}–${num(to)} of ${num(data.total)}`;

  replace($('#review-list'), data.items.length
    ? data.items.map(renderItem)
    : el('div', { class: 'empty', text: 'Nothing matches these filters.' }));

  renderPager($('#review-pager'), data.offset, data.limit, data.total, (offset) => {
    reviewState.offset = offset;
    loadReview();
    window.scrollTo({ top: 0 });
  });

  $('#select-page').checked = false;
  updateBulkBar();
  renderFocus();
}

function renderItem(item) {
  const checkbox = el('input', {
    type: 'checkbox', 'aria-label': `Select item ${item.id}`,
    onchange: (e) => {
      if (e.target.checked) selected.add(item.id); else selected.delete(item.id);
      updateBulkBar();
    },
  });
  checkbox.checked = selected.has(item.id);

  const note = el('input', { type: 'text', placeholder: 'note (optional)' });

  const act = async (decision) => {
    const by = requireReviewer();
    if (!by) return;
    try {
      const result = await post('/api/review/decide', {
        ids: [item.id], decision, decided_by: by, note: note.value,
      });
      if (result.updated.length) {
        toast(`Item ${item.id} ${decision}.`);
      } else {
        toast(`Item ${item.id} was already ${decision}.`);
      }
      await loadFacets();
      await loadReview();
    } catch (e) { toast(e.message, true); }
  };

  const context = formatContext(item.context_json);

  const body = el('div', {},
    el('div', { class: 'meta' },
      el('span', { class: 'badge module', text: item.module }),
      el('span', { class: 'badge type', text: item.item_type }),
      el('span', { class: `badge ${item.status}`, text: item.status }),
      el('span', { class: 'muted', text: `#${item.id} · seen ${when(item.created_at)}` })),
    el('div', { class: 'raw' }, maybeLink(item.raw_value)),
    context ? el('pre', { class: 'context', text: context }) : null,
    item.last_decision ? el('div', { class: 'muted small' },
      `${item.last_decision} by ${item.last_decided_by} on ${when(item.last_decided_at)}`
      + (item.last_note ? ` — “${item.last_note}”` : '')) : null,
    item.decision_count > 1 ? historyBlock(item.id, item.decision_count) : null,
    el('div', { class: 'actions' },
      note,
      el('button', { class: 'btn approve', onclick: () => act('approved') }, 'Approve'),
      el('button', { class: 'btn reject', onclick: () => act('rejected') }, 'Reject'),
      item.status !== 'pending'
        ? el('button', { class: 'btn ghost', onclick: () => act('pending') }, 'Reset to pending')
        : null));

  return el('div', { class: 'item', dataset: { id: String(item.id) } },
    el('div', {}, checkbox), body);
}

/** Context comes out of the database as a JSON string. Pretty-print it when it
 *  parses, and show it as it stands when it does not — a module that wrote
 *  something unexpected there is worth seeing, not hiding behind a parse
 *  error. */
function formatContext(raw) {
  if (!raw) return '';
  try { return JSON.stringify(JSON.parse(raw), null, 2); }
  catch (e) { return String(raw); }
}

function historyBlock(itemId, count) {
  const table = el('div', { class: 'muted small', text: 'loading…' });
  const details = el('details', { class: 'history' },
    el('summary', { text: `${count} decisions on this item` }), table);

  details.addEventListener('toggle', async () => {
    if (!details.open || details.dataset.loaded) return;
    details.dataset.loaded = '1';
    try {
      const full = await api(`/api/review/${itemId}`);
      replace(table, el('table', {},
        el('thead', {}, el('tr', {},
          el('th', { text: 'Decision' }), el('th', { text: 'From' }),
          el('th', { text: 'By' }), el('th', { text: 'When' }), el('th', { text: 'Note' }))),
        el('tbody', {}, full.decisions.map((d) => el('tr', {},
          el('td', {}, el('span', { class: `badge ${d.decision}`, text: d.decision })),
          el('td', { class: 'muted', text: d.status_before }),
          el('td', { text: d.decided_by }),
          el('td', { class: 'muted', text: when(d.decided_at) }),
          el('td', { text: d.note || '—' }))))));
    } catch (e) { replace(table, el('div', { class: 'muted small', text: e.message })); }
  });
  return details;
}

function updateBulkBar() {
  const bar = $('#bulkbar');
  bar.hidden = selected.size === 0;
  $('#bulk-count').textContent = `${num(selected.size)} selected`;
}

async function bulkDecide(decision) {
  const by = requireReviewer();
  if (!by) return;
  const ids = [...selected];
  if (!ids.length) return;

  const verb = decision === 'pending' ? 'reset to pending' : decision;
  if (!confirm(`${verb} ${ids.length} item${ids.length === 1 ? '' : 's'}?`)) return;

  try {
    const result = await post('/api/review/decide', {
      ids, decision, decided_by: by, note: $('#bulk-note').value,
    });
    const parts = [`${num(result.updated.length)} ${verb}`];
    if (result.unchanged.length) parts.push(`${num(result.unchanged.length)} already ${decision}`);
    if (result.missing.length) parts.push(`${num(result.missing.length)} no longer exist`);
    toast(parts.join(', ') + '.');
    selected.clear();
    $('#bulk-note').value = '';
    await loadFacets();
    await loadReview();
  } catch (e) { toast(e.message, true); }
}

function renderPager(container, offset, limit, total, go) {
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  replace(container,
    el('button', { class: 'btn', disabled: offset <= 0, onclick: () => go(Math.max(0, offset - limit)) }, '‹ Previous'),
    el('span', { text: `Page ${num(page)} of ${num(pages)}` }),
    el('button', { class: 'btn', disabled: offset + limit >= total, onclick: () => go(offset + limit) }, 'Next ›'));
}

// --- keyboard ---------------------------------------------------------------

function renderFocus() {
  document.querySelectorAll('#review-list .item').forEach((node, index) => {
    node.classList.toggle('focused', index === reviewState.focus);
  });
}

function focusedItem() {
  return reviewState.items[reviewState.focus] || null;
}

function moveFocus(delta) {
  if (!reviewState.items.length) return;
  reviewState.focus = Math.max(0, Math.min(reviewState.items.length - 1, reviewState.focus + delta));
  renderFocus();
  const node = document.querySelectorAll('#review-list .item')[reviewState.focus];
  if (node) node.scrollIntoView({ block: 'nearest' });
}

async function decideFocused(decision) {
  const item = focusedItem();
  if (!item) return;
  const by = requireReviewer();
  if (!by) return;
  const index = reviewState.focus;
  try {
    await post('/api/review/decide', { ids: [item.id], decision, decided_by: by });
    toast(`Item ${item.id} ${decision === 'pending' ? 'reset to pending' : decision}.`);
    await loadFacets();
    await loadReview();
    // Keep the cursor where it was. Filtering on pending means the decided
    // item leaves the list, so staying put lands on the next one.
    reviewState.focus = Math.min(index, reviewState.items.length - 1);
    renderFocus();
  } catch (e) { toast(e.message, true); }
}

document.addEventListener('keydown', (event) => {
  const tag = (event.target.tagName || '').toLowerCase();
  const typing = tag === 'input' || tag === 'textarea' || tag === 'select';

  if (event.key === '/' && !typing) {
    event.preventDefault();
    (currentTab === 'database' ? $('#obj-filter') : $('#f-search')).focus();
    return;
  }
  if (typing || event.ctrlKey || event.metaKey || event.altKey) return;
  if (currentTab !== 'review') return;

  const keys = {
    j: () => moveFocus(1),
    k: () => moveFocus(-1),
    a: () => decideFocused('approved'),
    r: () => decideFocused('rejected'),
    u: () => decideFocused('pending'),
    x: () => {
      const item = focusedItem();
      if (!item) return;
      if (selected.has(item.id)) selected.delete(item.id); else selected.add(item.id);
      const box = document.querySelectorAll('#review-list .item input[type=checkbox]')[reviewState.focus];
      if (box) box.checked = selected.has(item.id);
      updateBulkBar();
    },
  };
  if (keys[event.key]) { event.preventDefault(); keys[event.key](); }
});

// --- database browser -------------------------------------------------------

const browserState = { objects: [], current: null, offset: 0, limit: 50, orderBy: null, desc: false, reveal: new Set() };

async function loadSchema() {
  if (browserState.objects.length) return renderObjectList();
  try {
    const data = await api('/api/schema');
    browserState.objects = data.objects;
  } catch (e) { return toast(e.message, true); }
  renderObjectList();
}

function renderObjectList() {
  const filter = $('#obj-filter').value.trim().toLowerCase();
  const matching = browserState.objects.filter((o) => o.name.toLowerCase().includes(filter));
  const groups = [['table', 'Tables'], ['view', 'Views']];

  const nodes = [];
  for (const [type, label] of groups) {
    const items = matching.filter((o) => o.type === type);
    if (!items.length) continue;
    nodes.push(el('div', { class: 'objgroup', text: `${label} (${items.length})` }));
    for (const object of items) {
      nodes.push(el('div', {
        class: `obj${object.restricted ? ' restricted' : ''}`,
        'aria-current': String(browserState.current === object.name),
        title: object.restricted ? 'Holds personal data' : object.name,
        onclick: () => openObject(object.name),
      },
        el('span', { class: 'name', text: object.name }),
        el('span', { class: 'n', text: object.rows === null ? 'view' : num(object.rows) })));
    }
  }
  replace($('#object-list'), nodes.length ? nodes : el('div', { class: 'empty small', text: 'No match.' }));
}

function openObject(name) {
  browserState.current = name;
  browserState.offset = 0;
  browserState.orderBy = null;
  browserState.desc = false;
  $('#table-search') && ($('#table-search').value = '');
  renderObjectList();
  loadTable();
}

async function loadTable(search) {
  const name = browserState.current;
  if (!name) return;

  const params = new URLSearchParams({
    limit: String(browserState.limit),
    offset: String(browserState.offset),
  });
  if (browserState.orderBy) {
    params.set('order_by', browserState.orderBy);
    params.set('dir', browserState.desc ? 'desc' : 'asc');
  }
  const term = search !== undefined ? search : ($('#table-search') ? $('#table-search').value.trim() : '');
  if (term) params.set('q', term);
  if (browserState.reveal.has(name)) params.set('reveal', '1');

  let data;
  try {
    data = await api(`/api/table/${encodeURIComponent(name)}?${params}`);
  } catch (e) {
    if (e.status === 403) return renderRestrictedGate(name, e.message);
    return toast(e.message, true);
  }
  renderTable(data, term);
}

function renderRestrictedGate(name, message) {
  replace($('#table-head'),
    el('h2', { text: name }),
    el('div', { class: 'warn' }, message));
  replace($('#data-table'));
  replace($('#table-pager'),
    el('button', {
      class: 'btn reject',
      onclick: () => { browserState.reveal.add(name); loadTable(); },
    }, 'Show personal data'),
    el('span', { class: 'muted small' },
      'Nothing here is exported: restricted_ tables are blocked from every export by pipeline/exports.'));
}

function renderTable(data, term) {
  const from = data.total ? data.offset + 1 : 0;
  const to = Math.min(data.offset + data.limit, data.total);

  const search = el('input', {
    id: 'table-search', type: 'search', placeholder: 'search all columns…', value: term || '',
    onchange: (e) => { browserState.offset = 0; loadTable(e.target.value.trim()); },
  });

  replace($('#table-head'),
    el('h2', { text: data.name }),
    el('span', { class: 'muted small', text: `${data.type} · ${num(data.total)} rows · showing ${num(from)}–${num(to)}` }),
    data.restricted ? el('span', { class: 'badge rejected', text: 'personal data' }) : null,
    el('span', { class: 'spacer' }),
    search);

  const header = el('tr', {}, data.columns.map((column) => el('th', {
    class: 'clickable',
    title: `${column.name} ${column.type || ''}`.trim() + ' — click to sort',
    onclick: () => {
      browserState.desc = browserState.orderBy === column.name ? !browserState.desc : false;
      browserState.orderBy = column.name;
      browserState.offset = 0;
      loadTable();
    },
  }, column.name + (data.order_by === column.name ? (data.descending ? ' ↓' : ' ↑') : ''))));

  const body = data.rows.map((row) => el('tr', {}, row.map((value) =>
    value === null
      ? el('td', { class: 'null', text: 'NULL' })
      : el('td', {}, maybeLink(value)))));

  replace($('#data-table'),
    el('thead', {}, header),
    el('tbody', {}, body.length ? body
      : el('tr', {}, el('td', { colspan: String(data.columns.length), class: 'empty', text: 'No rows.' }))));

  const pager = [];
  if (!data.ordered) {
    pager.push(el('span', { class: 'muted small' },
      'This view has no stable order — sort by a column before paging, or rows may repeat across pages.'));
  }
  renderPager($('#table-pager'), data.offset, data.limit, data.total, (offset) => {
    browserState.offset = offset;
    loadTable();
  });
  $('#table-pager').append(...pager);
}

// --- SQL --------------------------------------------------------------------

async function runSql() {
  const sql = $('#sql-input').value.trim();
  if (!sql) return;
  $('#sql-status').textContent = 'running…';
  try {
    const data = await post('/api/query', { sql });
    $('#sql-status').textContent = `${num(data.rows.length)} row${data.rows.length === 1 ? '' : 's'}`
      + (data.truncated ? ` (capped at ${num(data.limit)})` : '');
    replace($('#sql-table'),
      el('thead', {}, el('tr', {}, data.columns.map((c) => el('th', { text: c.name })))),
      el('tbody', {}, data.rows.map((row) => el('tr', {}, row.map((value) =>
        value === null ? el('td', { class: 'null', text: 'NULL' }) : el('td', {}, maybeLink(value)))))));
  } catch (e) {
    $('#sql-status').textContent = '';
    replace($('#sql-table'));
    toast(e.message, true);
  }
}

// --- wiring -----------------------------------------------------------------

function debounce(fn, ms) {
  let timer = null;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

function init() {
  $('#reviewer').value = localStorage.getItem('cglpay.reviewer') || '';
  $('#reviewer').addEventListener('change', () => localStorage.setItem('cglpay.reviewer', reviewer()));

  document.querySelectorAll('.tab').forEach((button) =>
    button.addEventListener('click', () => showTab(button.dataset.tab)));

  for (const id of ['#f-status', '#f-module', '#f-type', '#f-limit', '#f-oldest']) {
    $(id).addEventListener('change', () => {
      if (id === '#f-module') populateItemTypes($('#f-module').value);
      reviewState.offset = 0;
      selected.clear();
      loadReview();
    });
  }
  $('#f-search').addEventListener('input', debounce(() => {
    reviewState.offset = 0;
    loadReview();
  }, 300));

  $('#select-page').addEventListener('change', (e) => {
    for (const item of reviewState.items) {
      if (e.target.checked) selected.add(item.id); else selected.delete(item.id);
    }
    document.querySelectorAll('#review-list .item input[type=checkbox]')
      .forEach((box) => { box.checked = e.target.checked; });
    updateBulkBar();
  });

  document.querySelectorAll('[data-bulk]').forEach((button) =>
    button.addEventListener('click', () => bulkDecide(button.dataset.bulk)));
  $('#bulk-clear').addEventListener('click', () => {
    selected.clear();
    document.querySelectorAll('#review-list .item input[type=checkbox]')
      .forEach((box) => { box.checked = false; });
    $('#select-page').checked = false;
    updateBulkBar();
  });

  $('#obj-filter').addEventListener('input', debounce(renderObjectList, 150));
  $('#sql-run').addEventListener('click', runSql);
  $('#sql-input').addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') runSql();
  });

  window.addEventListener('hashchange', () => showTab(location.hash.slice(1)));
  showTab(location.hash.slice(1) || 'overview');
}

init();
