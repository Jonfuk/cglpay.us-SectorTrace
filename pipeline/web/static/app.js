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

/* Timestamps in this UI are nearly always being read for one reason: is this
 * from the run I just did, or from last week? A relative label answers that
 * without arithmetic. The exact value is kept in title= and datetime=, since
 * "3 hours ago" is worthless the moment it goes into a bug report. */
const RELATIVE = new Intl.RelativeTimeFormat('en-GB', { numeric: 'auto' });
const RELATIVE_UNITS = [
  ['year', 31_536_000], ['month', 2_592_000], ['week', 604_800],
  ['day', 86_400], ['hour', 3_600], ['minute', 60],
];

function timeAgo(date) {
  const seconds = (date.getTime() - Date.now()) / 1000;
  for (const [unit, size] of RELATIVE_UNITS) {
    if (Math.abs(seconds) >= size) return RELATIVE.format(Math.round(seconds / size), unit);
  }
  return RELATIVE.format(Math.round(seconds), 'second');
}

/** A <time> element: relative text, exact value on hover, and the ISO string
 *  in the dataset so the ticker can rewrite it without a re-render. */
function timeNode(iso) {
  if (!iso) return document.createTextNode('—');
  const d = new Date(iso);
  if (isNaN(d)) return document.createTextNode(String(iso));
  return el('time', {
    datetime: d.toISOString(),
    title: when(iso),
    dataset: { iso: String(iso) },
    text: timeAgo(d),
  });
}

/* "2 minutes ago" is a lie after five minutes on a page left open, which this
 * one routinely is. */
function retickTimes() {
  for (const node of document.querySelectorAll('time[data-iso]')) {
    const d = new Date(node.dataset.iso);
    if (!isNaN(d)) node.textContent = timeAgo(d);
  }
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
function toast(message, isError, action) {
  const box = $('#toast');
  box.className = isError ? 'toast error' : 'toast';
  box.hidden = false;

  const children = [document.createTextNode(message)];
  if (action) {
    children.push(el('button', {
      class: 'btn ghost toast-action',
      onclick: () => { box.hidden = true; action.run(); },
    }, action.label));
  }
  box.replaceChildren(...children);

  clearTimeout(toastTimer);
  // An offered undo that vanishes in four seconds is not an offer. Long enough
  // to notice a mistake and reach the mouse.
  const life = action ? 15000 : (isError ? 9000 : 4000);
  toastTimer = setTimeout(() => { box.hidden = true; }, life);
}

/* A request counter rather than a boolean: several calls overlap (facets and
 * items always go together), and a boolean would clear the indicator when the
 * first of them returned while the page was still waiting on the rest. */
let inFlight = 0;
function setBusy(delta) {
  inFlight = Math.max(0, inFlight + delta);
  $('#busybar').hidden = inFlight === 0;
}

async function api(path, options) {
  setBusy(1);
  let response;
  try {
    response = await fetch(path, options);
  } finally {
    setBusy(-1);
  }
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

/** Placeholder rows while a page loads. Height-matched to the real thing so
 *  the list does not jump when it arrives. */
function skeletonList(count) {
  return Array.from({ length: count }, () => el('div', { class: 'skel-item' },
    el('div', { class: 'skeleton', style: 'width: 30%' }),
    el('div', { class: 'skeleton', style: 'width: 75%' }),
    el('div', { class: 'skeleton', style: 'width: 55%' })));
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

/* 'pipeline' is rendered by an ES module, not from here. This file still owns
 * the routing, so the name has to be known to it; what happens next is the
 * module's business, and it finds out through the event at the end of
 * showTab rather than by being called. */
const TABS = ['overview', 'review', 'pipeline', 'health', 'candidates', 'census',
               'claims', 'search', 'claimreview', 'exports', 'database', 'sql'];
let currentTab = 'overview';

function showTab(name) {
  if (!TABS.includes(name)) name = 'overview';
  currentTab = name;
  for (const tab of TABS) {
    $(`#tab-${tab}`).classList.toggle('active', tab === name);
    const button = document.querySelector(`.tab[data-tab="${tab}"]`);
    button.setAttribute('aria-selected', String(tab === name));
  }
  syncUrl();
  if (name === 'overview') loadOverview();
  if (name === 'review') loadReview();
  if (name === 'database') {
    // Schema first, then rows. The cells decide whether a value is a jump to
    // another table by looking that table up in the object list, so rendering
    // before it arrives silently produces a page with no jumps on it.
    const ready = loadSchema();
    if (browserState.current) ready.then(() => loadTable());
  }
  document.dispatchEvent(new CustomEvent('tabshown', { detail: { tab: name } }));
}

/* The review filters live in the URL, so a worklist is a link. "m10's unknown
 * committee URLs" is a thing worth sending to someone, or keeping in a
 * bookmark, and re-selecting four dropdowns every time is how a queue stops
 * getting looked at. */
function syncUrl() {
  const params = new URLSearchParams();
  if (currentTab === 'review') {
    const filters = {
      status: $('#f-status').value,
      module: $('#f-module').value,
      item_type: $('#f-type').value,
      q: $('#f-search').value.trim(),
      limit: $('#f-limit').value,
    };
    // Defaults are omitted, so an untouched review tab is just "#review".
    if (filters.status !== 'pending') params.set('status', filters.status);
    if (filters.module) params.set('module', filters.module);
    if (filters.item_type) params.set('item_type', filters.item_type);
    if (filters.q) params.set('q', filters.q);
    if (filters.limit !== '50') params.set('limit', filters.limit);
    if (!$('#f-oldest').checked) params.set('newest_first', '1');
    if (reviewState.offset) params.set('offset', String(reviewState.offset));
  }
  // Which table is open is worth linking to for the same reason a worklist
  // is: "look at supplier_aliases" is a message someone sends.
  if (currentTab === 'database' && browserState.current) {
    params.set('table', browserState.current);
    if (browserState.search) params.set('q', browserState.search);
  }
  const query = params.toString();
  const target = `#${currentTab}${query ? `?${query}` : ''}`;
  if (location.hash !== target) history.replaceState(null, '', target);
  remember(target);
}

/* Where the last session got to, so that opening /admin with a bare URL
 * resumes it rather than dropping someone at an unfiltered queue several
 * thousand items long. Only ever consulted when the URL says nothing at all:
 * a link, a bookmark or the back button is an instruction and wins outright.
 */
const LOCATION_KEY = 'cglpay.location';

function remember(target) {
  try { localStorage.setItem(LOCATION_KEY, target); } catch (e) { /* private mode */ }
}

function remembered() {
  try { return localStorage.getItem(LOCATION_KEY) || ''; } catch (e) { return ''; }
}

function parseHash() {
  const raw = location.hash.slice(1);
  const [tab, query] = raw.split('?');
  return { tab: tab || 'overview', params: new URLSearchParams(query || '') };
}

/** Push URL parameters into the filter controls. Returns true if the review
 *  tab's controls changed, so the caller knows whether a reload is due. */
function applyUrlFilters(params) {
  const before = JSON.stringify([$('#f-status').value, $('#f-module').value,
    $('#f-type').value, $('#f-search').value, $('#f-limit').value,
    $('#f-oldest').checked, reviewState.offset]);

  $('#f-status').value = params.get('status') || 'pending';
  $('#f-module').value = params.get('module') || '';
  populateItemTypes($('#f-module').value);
  $('#f-type').value = params.get('item_type') || '';
  $('#f-search').value = params.get('q') || '';
  $('#f-limit').value = params.get('limit') || '50';
  $('#f-oldest').checked = params.get('newest_first') !== '1';
  reviewState.offset = Number(params.get('offset') || 0) || 0;

  const after = JSON.stringify([$('#f-status').value, $('#f-module').value,
    $('#f-type').value, $('#f-search').value, $('#f-limit').value,
    $('#f-oldest').checked, reviewState.offset]);
  return before !== after;
}

/** Push the selected table from URL parameters into the browser state.
 *  Returns true if it changed, so the caller knows whether to reload. */
function applyUrlTable(params, tab) {
  // `q` means the review search on one tab and the table search on the other,
  // so this only reads it where it means the latter.
  if (tab !== 'database') return false;
  const wanted = params.get('table') || null;
  const term = params.get('q') || '';
  if (wanted === browserState.current && term === browserState.search) return false;
  browserState.current = wanted;
  browserState.search = term;
  browserState.offset = 0;
  browserState.orderBy = null;
  browserState.desc = false;
  return true;
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
    el('td', { class: 'muted small' }, el('div', { text: d.decided_by }),
      el('div', {}, timeNode(d.decided_at)))));

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

async function loadReview(keepFocus) {
  if (!reviewState.facets) await loadFacets();

  if ($('#f-clusters') && $('#f-clusters').checked) {
    return loadReviewClusters();
  }
  const clustersHolder = $('#review-clusters');
  if (clustersHolder) clustersHolder.hidden = true;
  $('#review-list').hidden = false;
  $('#review-pager').hidden = false;

  const previousFocus = keepFocus ? reviewState.focus : 0;
  // Skeletons sized to the page being requested, so the list does not
  // collapse to nothing and jump back when the rows arrive.
  replace($('#review-list'), skeletonList(Math.min(Number($('#f-limit').value) || 50, 8)));

  let data;
  try { data = await api(`/api/review?${reviewQuery()}`); }
  catch (e) {
    replace($('#review-list'), el('div', { class: 'empty', text: e.message }));
    return toast(e.message, true);
  }

  reviewState.items = data.items;
  reviewState.total = data.total;
  reviewState.focus = data.items.length
    ? Math.max(0, Math.min(previousFocus, data.items.length - 1)) : -1;

  renderList();
  renderCounts();
  syncUrl();

  renderPager($('#review-pager'), data.offset, data.limit, data.total, (offset) => {
    reviewState.offset = offset;
    loadReview();
    window.scrollTo({ top: 0 });
  });

  $('#select-page').checked = false;
  updateBulkBar();
  renderFocus();
}

/* BETA-053: the cluster view. Pending items grouped by (module, item_type,
 * a shared organisation/source token) so a reviewer sees "40 unknown
 * committee URLs for Kent" as one row. Grouping is display only — the
 * per-cluster Approve/Reject drives the existing decide-matching endpoint,
 * which recounts its exact id set inside the transaction and refuses on a
 * mismatch (confirm_count). */
async function loadReviewClusters() {
  const holder = $('#review-clusters');
  $('#review-list').hidden = true;
  $('#review-pager').hidden = true;
  holder.hidden = false;
  replace(holder, el('div', { class: 'muted small', text: 'Grouping…' }));

  let data;
  try { data = await api(`/api/review/clusters?status=${$('#f-status').value || 'pending'}`); }
  catch (e) { return replace(holder, el('div', { class: 'empty', text: e.message })); }

  const decideCluster = async (cluster, decision) => {
    const by = requireReviewer();
    if (!by) return;
    try {
      const result = await post('/api/review/decide-matching', {
        decision, decided_by: by,
        confirm_count: cluster.count,
        status: $('#f-status').value || 'pending',
        module: cluster.module, item_type: cluster.item_type,
        search: cluster.token === '(none)' ? null : cluster.token,
      });
      toast(`${decision}: ${result.updated.length} item(s) in this cluster.`);
      loadReviewClusters();
      loadFacets();
    } catch (e) {
      toast(e.message, true);
    }
  };

  const rows = (data.clusters || []).map((cluster) => el('details', { class: 'cluster' },
    el('summary', {},
      el('span', { class: 'badge module', text: cluster.module }), ' ',
      el('span', { class: 'badge type', text: cluster.item_type }), ' ',
      el('strong', { text: cluster.token }), ' ',
      el('span', { class: 'muted', text: `· ${cluster.count} item${cluster.count === 1 ? '' : 's'}` })),
    el('div', { class: 'cluster-body' },
      el('p', { class: 'muted small', text: cluster.sample_raw || '' }),
      el('div', { class: 'actions' },
        el('button', { class: 'btn approve',
          onclick: () => decideCluster(cluster, 'approved') }, `Approve ${cluster.count}`),
        el('button', { class: 'btn reject',
          onclick: () => decideCluster(cluster, 'rejected') }, `Reject ${cluster.count}`)))));

  replace(holder,
    el('p', { class: 'muted small', text: data.caveat }),
    el('p', { class: 'muted small',
      text: `${data.cluster_count} cluster(s) over ${data.scanned} pending item(s)`
        + (data.truncated ? ' (scan capped at 5000)' : '') }),
    rows.length ? el('div', {}, ...rows)
      : el('div', { class: 'empty', text: 'No pending items to group.' }));
}

function renderList() {
  const items = reviewState.items;
  if (!items.length) {
    return replace($('#review-list'),
      el('div', { class: 'empty', text: 'Nothing matches these filters.' }));
  }
  replace($('#review-list'), dense() ? renderDense(items) : items.map(renderItem));
}

function dense() {
  return $('#f-dense').checked;
}

function renderCounts() {
  const offset = reviewState.offset;
  const limit = Number($('#f-limit').value) || 50;
  const total = reviewState.total;
  const from = total ? offset + 1 : 0;
  const to = Math.min(offset + reviewState.items.length, total);
  $('#review-count').textContent = `${num(from)}–${num(to)} of ${num(total)}`;

  // "Approve all matching" only offers itself when a filter is narrowing the
  // queue and there is more than one page of it — the case the per-page
  // checkboxes handle badly.
  const filtered = $('#f-module').value || $('#f-type').value
    || $('#f-search').value.trim() || $('#f-status').value !== 'all';
  const worthIt = filtered && total > reviewState.items.length && total > 0;
  $('#matchbar').hidden = !worthIt;
  if (worthIt) {
    $('#match-summary').textContent =
      `${num(total)} items match this filter, across ${num(Math.ceil(total / limit))} pages`;
  }
}

/* Dense mode. Two item types are 72% of this queue and they are homogeneous —
 * one fact about one kind of document, repeated. A card each is the wrong
 * shape for that; a row each is the right one. */
function renderDense(items) {
  const head = el('tr', {},
    el('th', {}), el('th', { text: '#' }), el('th', { text: 'Module' }),
    el('th', { text: 'Item type' }), el('th', { text: 'Value' }),
    el('th', { text: 'Status' }), el('th', { text: 'Seen' }), el('th', {}));

  const rows = items.map((item, index) => {
    const checkbox = el('input', {
      type: 'checkbox', 'aria-label': `Select item ${item.id}`,
      onchange: (e) => {
        if (e.target.checked) selected.add(item.id); else selected.delete(item.id);
        updateBulkBar();
      },
    });
    checkbox.checked = selected.has(item.id);

    return el('tr', { dataset: { id: String(item.id) }, onclick: () => {
      reviewState.focus = index;
      renderFocus();
    } },
      el('td', {}, checkbox),
      el('td', { class: 'muted', text: `#${item.id}` }),
      el('td', {}, el('span', { class: 'badge module', text: item.module })),
      el('td', {}, el('span', { class: 'badge type', text: item.item_type })),
      el('td', { class: 'raw', title: item.raw_value }, maybeLink(item.raw_value)),
      el('td', {}, el('span', { class: `badge ${item.status}`, text: item.status })),
      el('td', { class: 'muted' }, timeNode(item.created_at)),
      el('td', { class: 'act' },
        el('button', { class: 'btn approve', title: 'Approve',
          onclick: (e) => { e.stopPropagation(); decideItems([item.id], 'approved'); } }, 'A'),
        ' ',
        el('button', { class: 'btn reject', title: 'Reject',
          onclick: (e) => { e.stopPropagation(); decideItems([item.id], 'rejected'); } }, 'R')));
  });

  return el('div', { class: 'densewrap' },
    el('table', { class: 'dense' }, el('thead', {}, head), el('tbody', {}, rows)));
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

  const act = (decision) => decideItems([item.id], decision, note.value);

  const body = el('div', {},
    el('div', { class: 'meta' },
      el('span', { class: 'badge module', text: item.module }),
      el('span', { class: 'badge type', text: item.item_type }),
      el('span', { class: `badge ${item.status}`, text: item.status }),
      el('span', { class: 'muted' }, `#${item.id} · seen `, timeNode(item.created_at))),
    el('div', { class: 'raw' }, maybeLink(item.raw_value)),
    typedContext(item.context_json),
    item.last_decision ? el('div', { class: 'muted small' },
      `${item.last_decision} by ${item.last_decided_by} `,
      timeNode(item.last_decided_at),
      item.last_note ? ` — “${item.last_note}”` : '') : null,
    item.decision_count > 1 ? historyBlock(item.id, item.decision_count) : null,
    sidecarBlock(item),
    resolveForm(item),
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

/* Some items can be answered, not just judged. `authority_website_unknown`
 * and `committee_url_unknown` both mean "nobody has told the pipeline where
 * this council publishes", and a person with a browser can settle that in a
 * minute — so those get a URL field, and answering writes somewhere the
 * modules read. Every other type gets no form, because inventing one would
 * promise a resolution that does not exist. */
function resolveForm(item) {
  const spec = reviewState.facets && reviewState.facets.resolvable
    && reviewState.facets.resolvable[item.item_type];
  if (!spec || item.status !== 'pending') return null;

  const input = el('input', { type: 'url', placeholder: 'https://…',
    'aria-label': spec.label, class: 'grow' });
  const status = el('span', { class: 'muted small' });

  const setStatus = (text, kind) => {
    status.textContent = text;
    status.className = `small ${kind || 'muted'}`;
  };

  const check = async () => {
    if (!input.value.trim()) return setStatus('Enter a URL first.', 'muted');
    setStatus('checking…');
    try {
      const result = await post('/api/check-url', { url: input.value });
      if (result.error) return setStatus(result.error, 'bad');
      if (!result.ok) return setStatus(`HTTP ${result.status} — not usable.`, 'bad');
      setStatus(`HTTP ${result.status} · ${result.system === 'unknown'
        ? 'no known committee system detected' : `${result.system} detected`}`, 'good');
    } catch (e) { setStatus(e.message, 'bad'); }
  };

  const save = async () => {
    const by = requireReviewer();
    if (!by) return;
    setStatus('checking and saving…');
    try {
      const result = await post('/api/review/resolve', {
        id: item.id, url: input.value, resolved_by: by,
      });
      toast(`${result.ons_code}: ${result.url} saved — ${result.module} will use it on its next run.`);
      await loadFacets();
      await loadReview(true);
    } catch (e) {
      setStatus(e.message, 'bad');
      toast(e.message, true);
    }
  };

  return el('div', { class: 'resolve' },
    el('div', { class: 'muted small', text: spec.help }),
    el('div', { class: 'actions' },
      input,
      el('button', { class: 'btn', onclick: check }, 'Check'),
      el('button', { class: 'btn primary', onclick: save }, `Save ${spec.label}`)),
    status);
}

/* A ranked shortlist for the two item types that name something unresolved —
 * an `unmatched_buyer_name` against `authorities`, a `possible_group_company`
 * against known companies and providers. Lazy-loaded on open, like the
 * history block. It is a suggestion to confirm: nothing here writes, and the
 * override still goes in by hand (pipeline/buyer_name_overrides.py). Absent
 * for every other type, and — being under /api/admin — absent entirely on a
 * hosted deployment with the operator UI off. */
const FUZZY_MATCH_TYPES = {
  unmatched_buyer_name: 'authority',
  possible_group_company: 'company / provider',
};

function nameMatchBlock(item) {
  if (!(item.item_type in FUZZY_MATCH_TYPES)) return null;
  const out = el('div', { class: 'muted small', text: 'loading…' });
  const details = el('details', { class: 'history' },
    el('summary', { text: `Similar ${FUZZY_MATCH_TYPES[item.item_type]} names` }), out);

  details.addEventListener('toggle', async () => {
    if (!details.open || details.dataset.loaded) return;
    details.dataset.loaded = '1';
    try {
      const res = await api(`/api/admin/review/${item.id}/name-matches`);
      if (!res.matches || !res.matches.length) {
        return replace(out, el('div', { class: 'muted small',
          text: res.note || 'No close matches — resolve by hand.' }));
      }
      replace(out, el('div', {},
        el('div', { class: 'muted small', text:
          `ranked by ${res.method === 'pg_trgm' ? 'trigram similarity'
            : 'difflib (pg_trgm not installed)'} — a suggestion to confirm, `
          + 'not a resolution' }),
        el('table', {},
          el('thead', {}, el('tr', {},
            el('th', { text: 'Score' }), el('th', { text: 'Match' }),
            el('th', { text: 'Id' }), el('th', { text: 'In' }))),
          el('tbody', {}, res.matches.map((m) => el('tr', {},
            el('td', { class: 'num', text: m.score.toFixed(2) }),
            el('td', { text: m.name }),
            el('td', { class: 'mono', text: String(m.id) }),
            el('td', { class: 'muted small', text: m.target })))))));
    } catch (e) {
      replace(out, el('div', { class: 'bad small', text: e.message }));
    }
  });

  return details;
}

/* BETA-054: the evidence sidecar — the item's own source excerpt, and (for
 * the name-match types) the ranked candidates relabelled as a similarity
 * percentage. Loaded lazily on expand. Nothing here is preselected and
 * approving the item still writes nothing to a canonical table. */
function sidecarBlock(item) {
  const body = el('div', { class: 'muted small', text: 'loading…' });
  const details = el('details', { class: 'history sidecar' },
    el('summary', { text: 'Evidence & candidates' }), body);

  details.addEventListener('toggle', async () => {
    if (!details.open || details.dataset.loaded) return;
    details.dataset.loaded = '1';
    let data;
    try { data = await api(`/api/review/${item.id}/sidecar`); }
    catch (e) { return replace(body, el('div', { class: 'bad small', text: e.message })); }

    const parts = [];
    const src = data.source || {};
    if (src.excerpt) {
      parts.push(el('blockquote', { class: 'ctx-evidence', text: src.excerpt }));
    }
    if (src.url) {
      parts.push(el('div', { class: 'small' }, maybeLink(src.url)));
    }
    if (src.retrieved_at || src.payload_sha256) {
      parts.push(el('div', { class: 'muted small mono',
        text: [src.retrieved_at ? `retrieved ${src.retrieved_at}` : null,
               src.payload_sha256 ? `sha ${String(src.payload_sha256).slice(0, 12)}` : null]
          .filter(Boolean).join(' · ') }));
    }
    if (!src.excerpt && !src.url && src.note) {
      parts.push(el('div', { class: 'muted small', text: src.note }));
    }

    const cand = data.candidates || {};
    if (cand.supported) {
      const rows = (cand.ranking || []).map((m) => el('tr', {},
        el('td', { class: 'num', text: `${m.similarity_percent}%` }),
        el('td', { text: m.name }),
        el('td', { class: 'mono', text: String(m.id) }),
        el('td', { class: 'muted small', text: m.target })));
      parts.push(el('div', { class: 'muted small', text:
        `Candidates ranked by ${cand.method === 'pg_trgm' ? 'trigram similarity'
          : 'difflib'} — nothing is selected; pick one by hand.` }));
      parts.push(rows.length
        ? el('table', {}, el('thead', {}, el('tr', {},
            el('th', { text: 'Similarity' }), el('th', { text: 'Name' }),
            el('th', { text: 'Id' }), el('th', { text: 'In' }))),
            el('tbody', {}, rows))
        : el('div', { class: 'muted small', text: 'No candidate above the similarity floor.' }));
      if ((cand.suppressed || []).length) {
        parts.push(el('div', { class: 'muted small',
          text: `${cand.suppressed.length} generic name(s) suppressed as known false matches.` }));
      }
    }
    parts.push(el('div', { class: 'muted small', text: data.caveat }));
    replace(body, el('div', {}, ...parts));
  });

  return details;
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

/* BETA-052: the review item's context_json rendered as typed sections rather
 * than a wall of pretty-printed JSON. Keys are classified by name into the
 * five things a reviewer actually needs — source, entity, reason, evidence,
 * navigation — and the complete raw object is kept under a <details> so
 * nothing is lost for audit. A generic classifier, not a per-item_type map:
 * the review types share these key shapes and a map would rot the first time
 * a module added a context key. */
const _CTX_URL_KEYS = /url$|_url$|^url$|link$|href$/i;
const _CTX_EVIDENCE_KEYS = /^(sentence|evidence_span|snippet|excerpt|text|match_text|mention_text|contravention_text|description)$/i;
const _CTX_ENTITY_KEYS = /(provider_key|provider_name|subject_entity_id|entity_id|ons_code|authority|buyer|supplier|charity_number|company_number|board|register_name|recipient_name|employer_name)/i;
const _CTX_REASON_KEYS = /(reason|selection_reason|basis|match_basis|selection|rule|score|relation_score|confidence|assertion_status|status_reason)/i;

function _ctxRows(entries, valueNode) {
  return el('dl', { class: 'ctx-kv' }, entries.flatMap(([key, value]) => [
    el('dt', { text: key }),
    el('dd', {}, valueNode(key, value)),
  ]));
}

function _ctxScalar(key, value) {
  if (value === null || value === undefined) return el('span', { class: 'muted', text: '—' });
  const text = typeof value === 'object' ? JSON.stringify(value) : String(value);
  if (_CTX_URL_KEYS.test(key) && /^https?:\/\//i.test(text)) {
    return el('a', { href: text, target: '_blank', rel: 'noopener noreferrer', text });
  }
  return document.createTextNode(text);
}

/* A provider_key / ons_code in the context is a jump to that entity's portal
 * page — opened in a new tab, since the operator UI is a separate app. */
function _ctxNav(context) {
  const links = [];
  if (context.provider_key) {
    links.push(el('a', { href: `/#/providers/${encodeURIComponent(context.provider_key)}`,
      target: '_blank', rel: 'noopener', text: `provider: ${context.provider_key}` }));
  }
  const ons = context.ons_code || context.authority_ons_code || context.buyer_ons_code;
  if (ons && /^[A-Z][0-9]{8}$/.test(String(ons))) {
    links.push(el('a', { href: `/#/authorities/${ons}`,
      target: '_blank', rel: 'noopener', text: `authority: ${ons}` }));
  }
  if (context.document_id) {
    links.push(el('a', { href: `/#/documents?q=`, target: '_blank', rel: 'noopener',
      text: `document: ${context.document_id}` }));
  }
  return links.length ? el('div', { class: 'ctx-nav' }, ...links) : null;
}

function typedContext(raw) {
  if (!raw) return null;
  let context;
  try { context = JSON.parse(raw); }
  catch (e) { return el('pre', { class: 'context', text: String(raw) }); }
  if (context === null || typeof context !== 'object' || Array.isArray(context)) {
    return el('pre', { class: 'context', text: formatContext(raw) });
  }

  const buckets = { source: [], entity: [], reason: [], evidence: [], other: [] };
  for (const [key, value] of Object.entries(context)) {
    if (_CTX_EVIDENCE_KEYS.test(key)) buckets.evidence.push([key, value]);
    else if (_CTX_URL_KEYS.test(key)) buckets.source.push([key, value]);
    else if (_CTX_ENTITY_KEYS.test(key)) buckets.entity.push([key, value]);
    else if (_CTX_REASON_KEYS.test(key)) buckets.reason.push([key, value]);
    else buckets.other.push([key, value]);
  }

  const sections = [];
  const add = (title, entries) => {
    if (entries.length) {
      sections.push(el('div', { class: 'ctx-section' },
        el('h4', { text: title }), _ctxRows(entries, _ctxScalar)));
    }
  };
  for (const [key, value] of buckets.evidence) {
    sections.push(el('div', { class: 'ctx-section' },
      el('h4', { text: key }),
      el('blockquote', { class: 'ctx-evidence', text: String(value ?? '') })));
  }
  add('Source', buckets.source);
  add('Entity', buckets.entity);
  add('Reason', buckets.reason);
  add('Other', buckets.other);

  const nav = _ctxNav(context);
  if (nav) sections.push(el('div', { class: 'ctx-section' },
    el('h4', { text: 'Open' }), nav));

  return el('div', { class: 'ctx-typed' },
    ...sections,
    el('details', { class: 'ctx-raw' },
      el('summary', { text: 'Raw context (lossless)' }),
      el('pre', { class: 'context', text: formatContext(raw) })));
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
          el('td', { class: 'muted' }, timeNode(d.decided_at)),
          el('td', { text: d.note || '—' }))))));
    } catch (e) { replace(table, el('div', { class: 'muted small', text: e.message })); }
  });
  return details;
}

/* One decision path for the buttons, the keyboard and the bulk bar.
 *
 * The row is updated in place rather than by reloading the list. Clearing a
 * queue is a rhythm — look, decide, next — and a full refetch between every
 * item breaks it: the list flashes, scroll position moves, and the row under
 * the cursor is replaced by a different one just as the next key is pressed.
 * The response is awaited first, so nothing is shown as decided that was not.
 */
async function decideItems(ids, decision, note, isUndo) {
  const by = requireReviewer();
  if (!by) return null;

  // What each item was, captured before the request: the rows are mutated (or
  // removed) as soon as it succeeds, and this is the only chance to know what
  // to put back. An undo is itself a recorded decision -- the queue keeps the
  // whole history, including the mistake -- so this is a convenience, not an
  // erasure.
  const previously = new Map();
  for (const id of ids) {
    const item = reviewState.items.find((candidate) => candidate.id === id);
    if (item) previously.set(id, item.status);
  }

  let result;
  try {
    result = await post('/api/review/decide', { ids, decision, decided_by: by, note });
  } catch (e) {
    toast(e.message, true);
    return null;
  }

  const statusFilter = $('#f-status').value;
  // An item that no longer matches the filter leaves the list; one that still
  // matches (viewing "all", or re-deciding) is re-rendered where it sits.
  const leaves = statusFilter !== 'all' && statusFilter !== decision;

  for (const id of result.updated) {
    const index = reviewState.items.findIndex((item) => item.id === id);
    if (index === -1) continue;
    if (leaves) {
      reviewState.items.splice(index, 1);
      reviewState.total = Math.max(0, reviewState.total - 1);
      selected.delete(id);
    } else {
      Object.assign(reviewState.items[index], {
        status: decision, last_decision: decision, last_decided_by: by,
        last_decided_at: new Date().toISOString(), last_note: note || null,
      });
    }
  }

  if (result.updated.length) {
    // Keep the cursor where it was: with a pending filter the decided row has
    // gone, so staying put lands on the next one down.
    reviewState.focus = Math.min(reviewState.focus, reviewState.items.length - 1);
    renderList();
    renderCounts();
    renderFocus();
    bumpPendingPill(decision, result.updated.length);
    if (!isUndo) bumpReviewSession(result.updated.length);
  }

  const noun = result.updated.length === 1 ? 'item' : 'items';
  if (result.updated.length) {
    toast(`${num(result.updated.length)} ${noun} ${verbFor(decision)}.`, false,
           isUndo ? null : undoFor(result.updated, previously));
  } else if (result.unchanged.length) {
    toast(`Already ${decision}; nothing changed.`);
  }

  // The page empties as items are decided; pull the next one in rather than
  // leaving a blank list under a pager that says there is more.
  if (!reviewState.items.length && reviewState.total > 0) {
    reviewState.offset = Math.max(0, Math.min(reviewState.offset, reviewState.total - 1));
    await loadReview();
  }
  scheduleFacetRefresh();
  return result;
}

function verbFor(decision) {
  return decision === 'pending' ? 'reset to pending' : decision;
}

/** An undo action for the toast, or null if there is nothing to put back.
 *
 *  Grouped by what each item was: a bulk decision over a mixed selection has
 *  no single previous status, and restoring them all to one would be a second
 *  mistake dressed as a correction.
 */
function undoFor(updatedIds, previously) {
  const groups = new Map();
  for (const id of updatedIds) {
    const was = previously.get(id);
    if (was === undefined) continue;
    if (!groups.has(was)) groups.set(was, []);
    groups.get(was).push(id);
  }
  if (!groups.size) return null;

  return {
    label: 'Undo',
    run: async () => {
      for (const [status, ids] of groups) {
        await decideItems(ids, status, null, true);
      }
      // The rows may have left the page when they were decided; if the undo
      // put them back into the current filter, they belong on screen.
      await loadReview(true);
    },
  };
}

/** The header pill, adjusted locally. The authoritative counts come back on
 *  the next facet refresh; this keeps the number honest in between. */
function bumpPendingPill(decision, count) {
  if (!reviewState.facets) return;
  const statuses = reviewState.facets.statuses;
  if (decision === 'pending') statuses.pending += count;
  else if ($('#f-status').value === 'pending') statuses.pending = Math.max(0, statuses.pending - count);
  $('#pending-pill').textContent = num(statuses.pending);
}

/* Facet counts feed the dropdown labels, which nobody reads mid-triage.
 * Refreshing them after every decision doubles the requests for a number that
 * can be a few seconds stale without costing anything. */
let facetTimer = null;
function scheduleFacetRefresh() {
  clearTimeout(facetTimer);
  facetTimer = setTimeout(() => loadFacets(), 2000);
}

function updateBulkBar() {
  const bar = $('#bulkbar');
  bar.hidden = selected.size === 0;
  $('#bulk-count').textContent = `${num(selected.size)} selected`;
}

/* Deciding a whole filtered set — the 1,067-item case. The count is sent with
 * it and checked server-side inside the transaction, so if the set moved since
 * the page loaded, nothing happens. */
async function decideMatching(decision) {
  const by = requireReviewer();
  if (!by) return;

  const total = reviewState.total;
  const scope = [
    $('#f-status').value !== 'all' ? `status ${$('#f-status').value}` : null,
    $('#f-module').value, $('#f-type').value,
    $('#f-search').value.trim() ? `matching “${$('#f-search').value.trim()}”` : null,
  ].filter(Boolean).join(' · ');

  const typed = prompt(
    `${verbFor(decision)} all ${total.toLocaleString('en-GB')} items in:\n\n  ${scope}\n\n`
    + 'This cannot be undone in bulk. Type the number to confirm:');
  if (typed === null) return;
  if (typed.replace(/[,\s]/g, '') !== String(total)) {
    return toast('That number did not match — nothing was changed.', true);
  }

  try {
    const result = await post('/api/review/decide-matching', {
      decision, decided_by: by, confirm_count: total,
      note: $('#match-note').value,
      status: $('#f-status').value,
      module: $('#f-module').value,
      item_type: $('#f-type').value,
      search: $('#f-search').value.trim(),
    });
    toast(`${num(result.updated.length)} items ${verbFor(decision)}`
      + (result.unchanged.length ? `, ${num(result.unchanged.length)} already were.` : '.'));
    $('#match-note').value = '';
    selected.clear();
    reviewState.offset = 0;
    await loadFacets();
    await loadReview();
  } catch (e) { toast(e.message, true); }
}

async function bulkDecide(decision) {
  const ids = [...selected];
  if (!ids.length) return;
  if (!confirm(`${verbFor(decision)} ${ids.length} item${ids.length === 1 ? '' : 's'}?`)) return;

  const result = await decideItems(ids, decision, $('#bulk-note').value);
  if (!result) return;
  if (result.missing.length) {
    toast(`${num(result.missing.length)} selected item(s) no longer exist.`, true);
  }
  selected.clear();
  $('#bulk-note').value = '';
  updateBulkBar();
  $('#select-page').checked = false;
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

/** The focusable rows, whichever view is on — cards and dense rows both carry
 *  data-id, so the keyboard works identically in each. */
function rowNodes() {
  return [...document.querySelectorAll('#review-list [data-id]')];
}

function renderFocus() {
  rowNodes().forEach((node, index) => {
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
  const node = rowNodes()[reviewState.focus];
  if (node) node.scrollIntoView({ block: 'nearest' });
}

async function decideFocused(decision) {
  const item = focusedItem();
  if (!item) return;
  await decideItems([item.id], decision);
}

/* BETA-055: the URL a reviewer would open to see the item's primary source —
 * a context URL key, else the raw value if it is itself a URL. */
function itemSourceUrl(item) {
  if (!item) return null;
  let context = {};
  try { context = JSON.parse(item.context_json || '{}') || {}; } catch (e) { /* */ }
  for (const key of ['source_url', 'url', 'page_url', 'source_page', 'notice_web_url',
                     'document_url', 'report_url', 'written_statement_url']) {
    if (context[key] && /^https?:\/\//i.test(String(context[key]))) return String(context[key]);
  }
  return /^https?:\/\//i.test(String(item.raw_value || '')) ? String(item.raw_value) : null;
}

function openFocusedSource() {
  const url = itemSourceUrl(focusedItem());
  if (!url) return toast('This item has no primary source URL.', true);
  window.open(url, '_blank', 'noopener');
}

/* Decisions taken in this browser session — a progress signal, not part of
 * the audit trail (that is review_decisions). Reset on reload. */
const reviewSession = { decided: 0 };
function bumpReviewSession(n) {
  reviewSession.decided += n;
  const node = $('#review-session');
  if (node) node.textContent = reviewSession.decided
    ? `${reviewSession.decided} decided this session` : '';
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
    o: openFocusedSource,
    x: () => {
      const item = focusedItem();
      if (!item) return;
      if (selected.has(item.id)) selected.delete(item.id); else selected.add(item.id);
      const node = rowNodes()[reviewState.focus];
      const box = node && node.querySelector('input[type=checkbox]');
      if (box) box.checked = selected.has(item.id);
      updateBulkBar();
    },
  };
  if (keys[event.key]) { event.preventDefault(); keys[event.key](); }
});

/* BETA-055: saved filter + note presets. localStorage only — a reviewer's
 * own convenience, never sent to the server and never part of a decision. */
const PRESET_KEY = 'cglpay.review.presets';

function loadPresets() {
  try { return JSON.parse(localStorage.getItem(PRESET_KEY) || '{}') || {}; }
  catch (e) { return {}; }
}
function savePresets(presets) {
  try { localStorage.setItem(PRESET_KEY, JSON.stringify(presets)); } catch (e) { /* */ }
}

function refreshPresetOptions() {
  const select = $('#review-preset');
  if (!select) return;
  const current = select.value;
  const presets = loadPresets();
  select.replaceChildren(el('option', { value: '', text: '—' }),
    ...Object.keys(presets).sort().map((name) => el('option', { value: name, text: name })));
  select.value = presets[current] ? current : '';
  $('#review-preset-delete').hidden = !select.value;
}

function applyPreset(preset) {
  if (!preset) return;
  $('#f-status').value = preset.status || 'pending';
  $('#f-module').value = preset.module || '';
  populateItemTypes($('#f-module').value);
  $('#f-type').value = preset.item_type || '';
  $('#f-search').value = preset.search || '';
  if ('note' in preset) {
    const box = $('#bulk-note');
    if (box) box.value = preset.note || '';
    const mnote = $('#match-note');
    if (mnote) mnote.value = preset.note || '';
  }
  reviewState.offset = 0;
  selected.clear();
  loadReview();
}

function initReviewPresets() {
  if (!$('#review-preset')) return;
  refreshPresetOptions();

  $('#review-preset').addEventListener('change', (e) => {
    $('#review-preset-delete').hidden = !e.target.value;
    if (e.target.value) applyPreset(loadPresets()[e.target.value]);
  });

  $('#review-preset-save').addEventListener('click', () => {
    const name = (window.prompt('Name this preset') || '').trim();
    if (!name) return;
    const presets = loadPresets();
    presets[name] = {
      status: $('#f-status').value,
      module: $('#f-module').value,
      item_type: $('#f-type').value,
      search: $('#f-search').value.trim(),
      note: ($('#bulk-note') && $('#bulk-note').value) || '',
    };
    savePresets(presets);
    refreshPresetOptions();
    $('#review-preset').value = name;
    $('#review-preset-delete').hidden = false;
    toast(`Preset "${name}" saved.`);
  });

  $('#review-preset-delete').addEventListener('click', () => {
    const name = $('#review-preset').value;
    if (!name) return;
    const presets = loadPresets();
    delete presets[name];
    savePresets(presets);
    refreshPresetOptions();
    toast(`Preset "${name}" deleted.`);
  });
}

/* BETA-056: the alias-resolution panel. Resolving an unmatched name is a
 * named, append-only decision through /api/admin/aliases/decide — the only
 * path that resolves a name. Nothing here applies a fuzzy match. */
async function loadAliasList() {
  const holder = $('#alias-list');
  if (!holder) return;
  const scheme = $('#alias-scheme').value;
  $('#alias-status').textContent = 'Loading…';
  let data;
  try { data = await api(`/api/admin/aliases?scheme=${scheme}`); }
  catch (e) { $('#alias-status').textContent = e.message; return; }

  $('#alias-status').textContent =
    `${data.items.filter((i) => i.resolved).length} of ${data.count} resolved`;

  const targetLabel = scheme === 'buyer' ? 'ons_code (E########)' : 'provider_key';
  const rows = data.items.map((item) => {
    const cid = el('input', { type: 'text', placeholder: targetLabel, 'aria-label': targetLabel });
    const reason = el('input', { type: 'text', placeholder: 'reason (optional)', 'aria-label': 'reason' });
    const status = el('span', { class: 'small muted' });

    const decide = async (verdict) => {
      const by = requireReviewer();
      if (!by) return;
      const body = {
        unmatched_name: item.unmatched_name, target_scheme: scheme,
        status: verdict, decided_by: by, reason: reason.value.trim() || null,
      };
      if (verdict === 'accepted') body.canonical_id = cid.value.trim();
      const last = (item.decisions || []).filter((d) => d.status === 'accepted').pop();
      if (last) body.supersedes_id = last.decision_id;
      try {
        await post('/api/admin/aliases/decide', body);
        status.textContent = `recorded: ${verdict}`;
        loadAliasList();
      } catch (e) { status.textContent = `refused: ${e.message}`; }
    };

    return el('div', { class: 'panel' },
      el('div', { class: 'row', style: 'justify-content:space-between;gap:8px' },
        el('strong', { text: item.unmatched_name }),
        el('span', { class: `badge ${item.resolved ? 'approved' : 'pending'}`,
          text: item.resolved
            ? `→ ${item.verified.canonical_name} (${item.verified.canonical_id})`
            : 'unresolved' })),
      (item.decisions || []).length
        ? el('div', { class: 'muted small' },
            `${item.decisions.length} decision(s); latest by `
            + `${item.decisions[item.decisions.length - 1].decided_by}`)
        : null,
      el('div', { class: 'runbar' }, cid, reason,
        el('button', { class: 'btn approve', onclick: () => decide('accepted') }, 'Accept'),
        el('button', { class: 'btn reject', onclick: () => decide('rejected') }, 'Reject'),
        status));
  });

  holder.replaceChildren(rows.length ? el('div', {}, ...rows)
    : el('div', { class: 'empty', text: 'No unmatched names of this kind.' }));
}

function initAliasResolution() {
  if (!$('#alias-scheme')) return;
  $('#alias-scheme').addEventListener('change', loadAliasList);
  $('#alias-reload').addEventListener('click', loadAliasList);
  // Load lazily on first expand of the <details>.
  const details = $('#alias-scheme').closest('details');
  if (details) {
    details.addEventListener('toggle', () => {
      if (details.open && !details.dataset.loaded) {
        details.dataset.loaded = '1';
        loadAliasList();
      }
    });
  }
}

// --- database browser -------------------------------------------------------

const browserState = { objects: [], current: null, offset: 0, limit: 50, orderBy: null, desc: false, search: '', reveal: new Set() };

/* Columns that name a row in another table. Following one by hand means
 * reading the value, finding the other table in a list of sixty-five, and
 * retyping the value into its search box — which is enough friction that the
 * question usually just goes unasked.
 *
 * A short explicit map rather than anything derived from foreign keys: most of
 * these relationships are not declared as constraints (evidence arrives from
 * separate sources and is matched afterwards, so a code can legitimately
 * reference an authority this warehouse has never seen), and the ones that are
 * declared are not the ones worth clicking. */
const JUMP_TARGETS = {
  ons_code: 'authorities',
  buyer_ons_code: 'authorities',
  authority_ons_code: 'authorities',
  local_authority_ons_code: 'authorities',
  parent_code: 'authorities',
  provider_key: 'providers',
  supplier_key: 'providers',
  company_number: 'companies',
  charity_number: 'charity_financials',
  indicator_id: 'fingertips_indicators',
};

/** A table cell: a jump to the row this value names, a link if it is a URL, or
 *  plain text. Never markup built from a database value. */
function cellContent(columnName, value) {
  const target = JUMP_TARGETS[columnName];
  const known = target && browserState.objects.some((o) => o.name === target);
  if (known && target !== browserState.current && String(value).trim()) {
    return el('a', {
      class: 'jump',
      href: `#database?table=${encodeURIComponent(target)}&q=${encodeURIComponent(value)}`,
      title: `Find ${value} in ${target}`,
      text: String(value),
    });
  }
  return maybeLink(value);
}

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
  browserState.search = '';
  renderObjectList();
  syncUrl();
  loadTable();
}

/** Reflect browserState.current into the page — used when the selection came
 *  from the URL (a link, or the back button) rather than from a click. */
function showSelectedTable() {
  renderObjectList();
  if (browserState.current) return loadTable();
  replace($('#table-head'));
  replace($('#data-table'));
  replace($('#table-pager'));
}

async function loadTable(search) {
  const name = browserState.current;
  if (!name) return;

  // The term lives in browserState, not in the input: the input is rebuilt on
  // every render, and a jump link or a pasted URL sets the term before there
  // is an input to read it from.
  if (search !== undefined) browserState.search = search;

  const params = new URLSearchParams({
    limit: String(browserState.limit),
    offset: String(browserState.offset),
  });
  if (browserState.orderBy) {
    params.set('order_by', browserState.orderBy);
    params.set('dir', browserState.desc ? 'desc' : 'asc');
  }
  const term = browserState.search;
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
  renderSchemaPanel(name);
}

// BETA-083: the read-only schema graph, fetched once and reused. Tables,
// columns, foreign keys and short descriptions from /api/admin/schema-graph.
let schemaGraph = null;
async function renderSchemaPanel(name) {
  const holder = $('#table-schema');
  if (!holder) return;
  if (!schemaGraph) {
    try { schemaGraph = await api('/api/admin/schema-graph'); }
    catch (e) { holder.hidden = true; return; }
  }
  const table = (schemaGraph.tables || []).find((t) => t.name === name);
  if (!table) { holder.hidden = true; return; }
  holder.hidden = false;

  const rows = table.columns.map((column) => el('tr', {},
    el('td', { class: 'mono small', text: column.name }),
    el('td', { class: 'small', text: column.type || '' }),
    el('td', { class: 'small', text: [column.pk ? 'pk' : null, column.notnull ? 'not null' : null].filter(Boolean).join(' ') }),
    el('td', { class: 'small' }, column.fk
      ? el('a', {
          href: `#database?table=${encodeURIComponent(column.fk.table)}`,
          onclick: () => openObject(column.fk.table),
          title: `references ${column.fk.table}.${column.fk.column}`,
        }, `→ ${column.fk.table}`)
      : null)));

  replace(holder,
    el('summary', { text: `Columns & keys — ${table.columns.length} columns` }),
    table.description ? el('p', { class: 'muted small', text: table.description }) : null,
    el('table', { class: 'schema-cols' },
      el('thead', {}, el('tr', {},
        el('th', { text: 'column' }), el('th', { text: 'type' }),
        el('th', { text: 'key' }), el('th', { text: 'references' }))),
      el('tbody', {}, ...rows)));
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
    onchange: (e) => {
      browserState.offset = 0;
      loadTable(e.target.value.trim());
      syncUrl();
    },
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

  const columnNames = data.columns.map((column) => column.name);
  const body = data.rows.map((row) => el('tr', {}, row.map((value, index) =>
    value === null
      ? el('td', { class: 'null', text: 'NULL' })
      : el('td', {}, cellContent(columnNames[index], value)))));

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

/* The last fifty statements, so the query someone spent ten minutes getting
 * right is still there tomorrow. Kept newest-first and deduplicated: running
 * the same thing four times while watching a run should leave one entry. */
const SQL_HISTORY_KEY = 'cglpay.sql.history';
const SQL_HISTORY_MAX = 50;

function sqlHistory() {
  try { return JSON.parse(localStorage.getItem(SQL_HISTORY_KEY) || '[]'); }
  catch (e) { return []; }
}

function rememberSql(sql) {
  const kept = [sql, ...sqlHistory().filter((entry) => entry !== sql)]
    .slice(0, SQL_HISTORY_MAX);
  try { localStorage.setItem(SQL_HISTORY_KEY, JSON.stringify(kept)); }
  catch (e) { /* private mode */ }
  renderSqlHistory();
}

function renderSqlHistory() {
  const select = $('#sql-history');
  if (!select) return;
  const entries = sqlHistory();
  replace(select, [
    el('option', { value: '', text: entries.length ? `${entries.length} recent` : '—' }),
    ...entries.map((sql, index) => el('option', {
      value: String(index),
      // Collapsed to one line: a select cannot show a newline, and a
      // multi-line query renders as a run of spaces without this.
      text: sql.replace(/\s+/g, ' ').slice(0, 90),
    })),
  ]);
  select.value = '';
}

// BETA-083: named, saved read-only queries — distinct from `sql-history`
// (which is the last N run, unnamed). Local to this browser.
const SQL_SAVED_KEY = 'cglpay.sql.saved';
function savedSql() {
  try { return JSON.parse(localStorage.getItem(SQL_SAVED_KEY) || '{}'); }
  catch (e) { return {}; }
}
function saveSql(name, sql) {
  const all = { ...savedSql(), [name]: sql };
  try { localStorage.setItem(SQL_SAVED_KEY, JSON.stringify(all)); }
  catch (e) { /* private mode */ }
  renderSavedSql();
}
function deleteSavedSql(name) {
  const all = savedSql(); delete all[name];
  try { localStorage.setItem(SQL_SAVED_KEY, JSON.stringify(all)); }
  catch (e) { /* private mode */ }
  renderSavedSql();
}
function renderSavedSql() {
  const select = $('#sql-saved');
  if (!select) return;
  const names = Object.keys(savedSql()).sort();
  replace(select, [
    el('option', { value: '', text: names.length ? `${names.length} saved` : '—' }),
    ...names.map((name) => el('option', { value: name, text: name })),
  ]);
  select.value = '';
}

/** The last result, kept for the CSV button. */
let lastSqlResult = null;

async function runSql(explain) {
  const typed = $('#sql-input').value.trim();
  if (!typed) return;
  // EXPLAIN QUERY PLAN is a read like any other and goes down the same
  // read-only connection; it answers "will this scan 98,000 contracts?"
  // before someone finds out by waiting.
  const sql = explain ? `EXPLAIN QUERY PLAN ${typed}` : typed;

  $('#sql-status').textContent = 'running…';
  try {
    const data = await post('/api/query', { sql });
    lastSqlResult = explain ? null : data;
    $('#sql-status').textContent = `${num(data.rows.length)} row${data.rows.length === 1 ? '' : 's'}`
      + (data.truncated ? ` (capped at ${num(data.limit)})` : '')
      + (explain ? ' — query plan, nothing was fetched' : '');
    replace($('#sql-table'),
      el('thead', {}, el('tr', {}, data.columns.map((c) => el('th', { text: c.name })))),
      el('tbody', {}, data.rows.map((row) => el('tr', {}, row.map((value) =>
        value === null ? el('td', { class: 'null', text: 'NULL' }) : el('td', {}, maybeLink(value)))))));
    if (!explain) rememberSql(typed);
  } catch (e) {
    $('#sql-status').textContent = '';
    lastSqlResult = null;
    replace($('#sql-table'));
    toast(e.message, true);
  }
}

/** RFC 4180: quotes doubled, anything with a comma, quote or newline quoted. */
function csvCell(value) {
  if (value === null || value === undefined) return '';
  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadSqlCsv() {
  if (!lastSqlResult) return toast('Run a query first.', true);
  const lines = [lastSqlResult.columns.map((c) => csvCell(c.name)).join(',')];
  for (const row of lastSqlResult.rows) lines.push(row.map(csvCell).join(','));

  // Built and downloaded in the page: the rows are already here, and a round
  // trip to ask the server to serialise what it just sent would be a second
  // query against the warehouse for the same answer.
  const blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = el('a', { href: url, download: `query_${new Date().toISOString().slice(0, 10)}.csv` });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
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

  for (const id of ['#f-status', '#f-module', '#f-type', '#f-limit', '#f-oldest', '#f-clusters']) {
    const node = $(id);
    if (!node) continue;
    node.addEventListener('change', () => {
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

  $('#f-dense').checked = localStorage.getItem('cglpay.dense') === '1';
  $('#f-dense').addEventListener('change', (e) => {
    localStorage.setItem('cglpay.dense', e.target.checked ? '1' : '0');
    renderList();
    renderFocus();
  });

  initReviewPresets();
  initAliasResolution();

  $('#select-page').addEventListener('change', (e) => {
    for (const item of reviewState.items) {
      if (e.target.checked) selected.add(item.id); else selected.delete(item.id);
    }
    document.querySelectorAll('#review-list input[type=checkbox]')
      .forEach((box) => { box.checked = e.target.checked; });
    updateBulkBar();
  });

  document.querySelectorAll('[data-bulk]').forEach((button) =>
    button.addEventListener('click', () => bulkDecide(button.dataset.bulk)));
  document.querySelectorAll('[data-matching]').forEach((button) =>
    button.addEventListener('click', () => decideMatching(button.dataset.matching)));
  $('#bulk-clear').addEventListener('click', () => {
    selected.clear();
    document.querySelectorAll('#review-list input[type=checkbox]')
      .forEach((box) => { box.checked = false; });
    $('#select-page').checked = false;
    updateBulkBar();
  });

  $('#obj-filter').addEventListener('input', debounce(renderObjectList, 150));
  $('#sql-run').addEventListener('click', () => runSql(false));
  $('#sql-explain').addEventListener('click', () => runSql(true));
  $('#sql-csv').addEventListener('click', downloadSqlCsv);
  $('#sql-input').addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') runSql(false);
  });
  $('#sql-history').addEventListener('change', (event) => {
    const entry = sqlHistory()[Number(event.target.value)];
    if (entry === undefined) return;
    $('#sql-input').value = entry;
    $('#sql-input').focus();
    event.target.value = '';
  });
  $('#sql-save').addEventListener('click', () => {
    const sql = $('#sql-input').value.trim();
    if (!sql) return;
    const name = prompt('Save this query as:');
    if (name && name.trim()) saveSql(name.trim(), sql);
  });
  $('#sql-saved').addEventListener('change', (event) => {
    const name = event.target.value;
    if (!name) return;
    if (event.shiftKey) { deleteSavedSql(name); return; }
    $('#sql-input').value = savedSql()[name] || '';
    $('#sql-input').focus();
    event.target.value = '';
  });
  renderSqlHistory();
  renderSavedSql();

  setInterval(retickTimes, 60_000);

  // Back/forward, pasted worklist links and the command palette all arrive
  // here: everything that navigates does it by setting the hash.
  window.addEventListener('hashchange', async () => {
    const { tab, params } = parseHash();
    // The same ordering the initial load needs, for the same reason: the
    // module and item-type dropdowns are built from the facets, and setting a
    // <select> to a value it has no option for silently does nothing. Without
    // this, a link naming a worklist lands on an unfiltered queue and then
    // rewrites itself to match, quietly losing what it was pointing at.
    if (tab === 'review' && !reviewState.facets) await loadFacets();
    const filtersChanged = applyUrlFilters(params);
    const tableChanged = applyUrlTable(params, tab);
    if (tab !== currentTab) showTab(tab);
    else if (tab === 'review' && filtersChanged) loadReview();
    else if (tab === 'database' && tableChanged) showSelectedTable();
  });

  // A bare /admin means "I have just opened the tool", so the last place this
  // browser was looking at comes back. Any hash at all is an instruction.
  if (!location.hash && remembered()) {
    history.replaceState(null, '', remembered());
  }

  const opened = parseHash();
  applyUrlTable(opened.params, opened.tab);

  if (opened.tab === 'review') {
    // Facets first: the item-type dropdown is built from them, so a link
    // naming one has nothing to select until they are in.
    loadFacets().then(() => {
      applyUrlFilters(opened.params);
      showTab('review');
    });
    return;
  }
  showTab(opened.tab);
}

init();
