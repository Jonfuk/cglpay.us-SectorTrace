/* SectorTrace portal — bootstrap, router, global filter state, data access.
 *
 * Same-origin throughout: the portal is served by the process that serves the
 * API, so requests are relative and there is no CORS to configure and no host
 * to get wrong when the server is reached over the LAN rather than loopback.
 *
 * As in the operator UI, values from the warehouse reach the page as text
 * nodes and never as concatenated HTML. This data is scraped council pages,
 * FOI text and PDF extracts — strings that came from the open web — and the
 * portal is the copy that gets shown to people outside the team.
 */
'use strict';

import { initPortalTheme, registerTheme } from '/js/theme.js';
import { initPalette } from '/js/palette.js';
import { parseFilters, serializeFilters, validateFilters, chipLabels }
  from '/js/filterstate.js';

// --- DOM helpers -------------------------------------------------------------

export function el(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
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

/* Same contract as `el()` — attributes via setAttribute, text via
 * textContent, never innerHTML — but in the SVG namespace, which
 * `document.createElement` cannot produce. Used by the overview hero's
 * region map; nothing else in the portal draws its own SVG. */
export function svgEl(tag, props, ...children) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'text') node.textContent = value;
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export const $ = (sel, root = document) => root.querySelector(sel);

export function replace(container, ...children) {
  container.replaceChildren(...children.flat().filter(Boolean));
}

/** A link only for http(s). A URL out of the warehouse does not get to decide
 *  what a click does. */
export function sourceLink(url, label) {
  const text = String(url ?? '');
  if (!/^https?:\/\//i.test(text)) return document.createTextNode(label || text || '—');
  return el('a', { href: text, target: '_blank', rel: 'noopener noreferrer' },
    label || text);
}

/* Arrow-key roving highlight for a typeahead's `<ul role="listbox">`, shared
 * by every typeahead on the portal — the top-bar council search, the filter
 * bar's provider search, and the authority/provider pickers on
 * `compare.js`/`treatment.js`. All five declare (or should declare, for
 * consistency) `role="combobox"`, but until now only implemented "Enter
 * selects the first match" — the roles overpromised what arrow keys and a
 * screen reader's activedescendant announcement actually did. Written once
 * here rather than five times; `styles.css`'s `li[aria-selected="true"]`
 * rule already existed and expected this, unused, before this. `input` must
 * have an `id` for `aria-activedescendant` to reference into. Call the
 * returned `reset()` every time `list`'s `<li>` children are replaced — the
 * old highlighted option no longer exists once that happens. */
export function typeaheadKeyboard(input, list) {
  let active = -1;
  const options = () => Array.from(list.children);

  const reset = () => {
    active = -1;
    input.removeAttribute('aria-activedescendant');
  };

  const setActive = (index) => {
    const opts = options();
    if (!opts.length) { reset(); return; }
    active = index;
    opts.forEach((li, i) => {
      li.id = `${input.id}-opt-${i}`;
      li.setAttribute('aria-selected', String(i === active));
    });
    input.setAttribute('aria-activedescendant', opts[active].id);
    opts[active].scrollIntoView({ block: 'nearest' });
  };

  const move = (delta) => {
    const count = options().length;
    if (!count) return;
    const next = active < 0 ? (delta > 0 ? 0 : count - 1)
      : (active + delta + count) % count;
    setActive(next);
  };

  input.addEventListener('keydown', (event) => {
    if (list.hidden) return;
    if (event.key === 'ArrowDown') { event.preventDefault(); move(1); }
    else if (event.key === 'ArrowUp') { event.preventDefault(); move(-1); }
    else if (event.key === 'Escape') { list.hidden = true; reset(); }
    else if (event.key === 'Enter') {
      const opts = options();
      const target = active >= 0 ? opts[active] : opts[0];
      if (target) {
        event.preventDefault();
        target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
      }
    }
  });

  return reset;
}

// --- formatting --------------------------------------------------------------

export const num = (n) =>
  n === null || n === undefined || Number.isNaN(n) ? '—' : Number(n).toLocaleString('en-GB');

export function gbp(value, { compact = true } = {}) {
  if (value === null || value === undefined) return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  if (!compact) return n.toLocaleString('en-GB', { style: 'currency', currency: 'GBP', maximumFractionDigits: 0 });
  const abs = Math.abs(n);
  if (abs >= 1e12) return `£${(n / 1e12).toFixed(1)}tn`;
  if (abs >= 1e9) return `£${(n / 1e9).toFixed(1)}bn`;
  if (abs >= 1e6) return `£${(n / 1e6).toFixed(1)}m`;
  if (abs >= 1e3) return `£${(n / 1e3).toFixed(0)}k`;
  return `£${n.toFixed(0)}`;
}

export function pct(fraction, digits = 1) {
  if (fraction === null || fraction === undefined) return '—';
  return `${(Number(fraction) * 100).toFixed(digits)}%`;
}

export function isoDate(value) {
  if (!value) return '—';
  return String(value).slice(0, 10);
}

/** "3 days ago", via date-fns where it loaded and Intl otherwise. The portal
 *  must render with any one vendored script missing rather than blank. */
export function ago(value) {
  if (!value) return 'never';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const seconds = (Date.now() - date.getTime()) / 1000;
  const units = [['year', 31536000], ['month', 2592000], ['day', 86400],
    ['hour', 3600], ['minute', 60]];
  const rtf = new Intl.RelativeTimeFormat('en-GB', { numeric: 'auto' });
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return rtf.format(-Math.round(seconds / size), unit);
  }
  return 'just now';
}

// --- data access -------------------------------------------------------------

let inFlight = 0;
function setBusy(delta) {
  inFlight = Math.max(0, inFlight + delta);
  $('#busybar').hidden = inFlight === 0;
}

const cache = new Map();

export async function fetchJSON(endpoint, params = {}, { fresh = false } = {}) {
  const url = new URL(`/api/v1/${endpoint}`, location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue;
    // An array becomes repeated params (`?k=a&k=b`), the shape the server's
    // repeatable parameters (`ons_code`, `provider_key`) expect — not the
    // comma-joined single value `set()` would produce.
    if (Array.isArray(value)) {
      for (const item of value) {
        if (item !== null && item !== undefined && item !== '') {
          url.searchParams.append(key, item);
        }
      }
    } else {
      url.searchParams.set(key, value);
    }
  }
  const key = url.toString();
  if (!fresh && cache.has(key)) return cache.get(key);

  setBusy(1);
  try {
    const response = await fetch(url);
    let payload = null;
    try { payload = await response.json(); } catch (e) { /* not JSON */ }
    if (!response.ok) {
      const err = new Error((payload && payload.error) || `HTTP ${response.status}`);
      // BETA-068: the server attaches a structured unavailable envelope for a
      // capability it cannot serve on this build (missing migration, absent
      // extension, section timeout). Carry it so the route catch can render a
      // feature-specific state with retry and a diagnostic reference instead
      // of a bare message.
      if (payload && payload.error_detail) err.detail = payload.error_detail;
      err.status = response.status;
      throw err;
    }
    cache.set(key, payload);
    return payload;
  } finally {
    setBusy(-1);
  }
}

export function exportUrl(endpoint, params = {}, format = 'csv') {
  const url = new URL('/api/v1/export', location.origin);
  url.searchParams.set('endpoint', endpoint);
  url.searchParams.set('format', format);
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') {
      url.searchParams.set(key, value);
    }
  }
  return url.toString();
}

// --- global filter state -----------------------------------------------------

/* Every key here is forwarded by `filterParams()` and read by a page. A key
 * that is written and never read is worse than a missing filter: the control
 * that sets it looks like it worked. The portal carried a Region select for
 * months that wrote `state.region` and reached no endpoint, so a reader could
 * pick a region, see the same figures, and have no way to tell. See
 * tests/test_portal_controls.py, which fails if a control is added back
 * without a consumer. */
const state = { provider: null, yearFrom: null, yearTo: null };
const listeners = new Set();

export function getState() { return { ...state }; }

export function setState(patch, { silent = false } = {}) {
  Object.assign(state, patch);
  writeStateToUrl();
  if (!silent) listeners.forEach((fn) => fn(getState()));
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Filters live in the URL so a filtered view is a link. The route is the hash
 *  path; filters are its query, which keeps one shareable address for
 *  "contracts, this provider, these years". */
function writeStateToUrl() {
  const [path, rawQuery] = (location.hash.slice(1) || '/').split('?');
  const existing = rawQuery ? new URLSearchParams(rawQuery) : null;
  // One serializer (BETA-072): shared filter keys in their schema shape,
  // page-owned keys (compare's `ons_code`, contracts' `q`, pay's `source`)
  // carried through untouched so one URL restores both.
  const params = serializeFilters(state, existing);
  const query = params.toString();
  const target = `#${path}${query ? `?${query}` : ''}`;
  if (location.hash !== target) history.replaceState(null, '', target);
}

function readStateFromUrl() {
  setState(parseFilters(parseHash().params), { silent: true });
}

/** Global filters as API params. Pages pass this straight through, so a filter
 *  added here reaches every endpoint that understands it. */
export function filterParams(extra = {}) {
  const s = getState();
  return {
    provider_key: s.provider || undefined,
    year_from: s.yearFrom || undefined,
    year_to: s.yearTo || undefined,
    ...extra,
  };
}

// --- routing -----------------------------------------------------------------

function parseHash() {
  const raw = location.hash.slice(1) || '/';
  const [path, query] = raw.split('?');
  return { path: path || '/', params: new URLSearchParams(query || '') };
}

const ROUTES = {
  '/': () => import('/js/pages/overview.js'),
  '/pay': () => import('/js/pages/pay.js'),
  '/contracts': () => import('/js/pages/contracts.js'),
  '/geography': () => import('/js/pages/geography.js'),
  '/treatment': () => import('/js/pages/treatment.js'),
  '/providers': () => import('/js/pages/providers.js'),
  '/pfd': () => import('/js/pages/pfd.js'),
  '/authorities': () => import('/js/pages/authority.js'),
  '/compare': () => import('/js/pages/compare.js'),
  '/relationships': () => import('/js/pages/relationships.js'),
  '/claims': () => import('/js/pages/claims.js'),
  '/coverage': () => import('/js/pages/coverage.js'),
  '/documents': () => import('/js/pages/documents.js'),
  '/catalogue': () => import('/js/pages/catalogue.js'),
  '/cqc': () => import('/js/pages/cqc.js'),
  '/changes': () => import('/js/pages/changes.js'),
  '/calendar': () => import('/js/pages/calendar.js'),
  '/notebook': () => import('/js/notebook.js'),
  '/saved': () => import('/js/savedsearch.js'),
  '/revisions': () => import('/js/pages/revisions.js'),
  '/pathfinder': () => import('/js/pages/pathfinder.js'),
  '/timeline': () => import('/js/pages/timeline.js'),
  '/journey': () => import('/js/journey.js'),
};

/* One <title> per route. Until now all thirteen shared index.html's static
 * title, so browser history could not tell two routes apart, a bookmark
 * named itself after whichever page was open first, and nothing announced
 * the change to a screen reader. Deep dives keep their section name rather
 * than fetching the entity just for the tab — the page's own h1 carries the
 * specifics once data arrives. */
const ROUTE_TITLES = {
  '/': 'Overview',
  '/pay': 'Pay & benchmarks',
  '/contracts': 'Funding & contracts',
  '/geography': 'Places',
  '/treatment': 'Treatment data',
  '/providers': 'Providers',
  '/relationships': 'Relationships',
  '/pfd': 'Safety & legal',
  '/authorities': 'Authorities',
  '/compare': 'Compare authorities',
  '/claims': 'Evidence-backed claims',
  '/coverage': 'Coverage & limitations',
  '/documents': 'Document search',
  '/catalogue': 'Dataset catalogue',
  '/cqc': 'CQC-registered locations',
  '/changes': 'What changed?',
  '/calendar': 'Publication calendar',
  '/notebook': 'Evidence notebook',
  '/saved': 'Saved searches',
  '/revisions': 'Compare revisions',
  '/pathfinder': 'Relationship pathfinder',
  '/timeline': 'Coverage timeline',
  '/journey': 'Research journey',
};

let disposeCurrent = null;
/* The base route of the previous render. Filter changes re-render the whole
 * page through the state subscription — same route, new data — and those
 * must not steal focus from whatever control the reader is using. Only a
 * change of route does that, and only after the first paint (focusing #main
 * on initial load would fight the reader's own starting point). */
let renderedBase = null;

/* BETA-077 navigation continuity.
 *
 * `scrollByHash` remembers where the reader was on each URL, so returning to a
 * list from a detail page (back button, or a breadcrumb) lands where they left
 * it rather than at the top. `lastListHash` remembers the *full* hash — filters
 * and all — of the last bare list route for each base, so a detail page's
 * "back to Providers" link restores the exact filtered list it was opened
 * from. Both are session-only and hold no personal data. */
const scrollByHash = new Map();
const lastListHash = new Map();
let lastRenderedHash = null;

const CRUMB_PARENTS = {
  '/providers': ['Providers', '#/providers'],
  '/authorities': ['Places', '#/geography'],
};

async function render() {
  const { path, params } = parseHash();
  const hereHash = location.hash || '#/';
  // Save where we were before this render replaces the page.
  if (lastRenderedHash && lastRenderedHash !== hereHash) {
    scrollByHash.set(lastRenderedHash, window.scrollY);
  }
  // Deep dives share their base module: /providers/:key is the providers
  // module with a key, /authorities/:ons_code the authority module with one.
  const base = path.startsWith('/providers/') ? '/providers'
    : path.startsWith('/authorities/') ? '/authorities' : path;
  const load = ROUTES[base] || ROUTES['/'];
  const routeLabel = ROUTE_TITLES[base];
  document.title = routeLabel ? `${routeLabel} · SectorTrace` : 'SectorTrace';
  const navigating = renderedBase !== null && renderedBase !== base;
  renderedBase = base;
  // BETA-077: on a bare list route (no `/key` suffix), remember the full hash
  // — filters included — as the place a detail page opened from.
  if (path === base) lastListHash.set(base, hereHash);
  // BETA-072: the previous page's match count does not describe this one.
  if (navigating) resultCount = null;
  updateFilterVisibility(base);

  for (const link of document.querySelectorAll('.mainnav a')) {
    const route = link.dataset.route;
    const active = base === `/${route}` || (route === '' && base === '/');
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }

  if (typeof disposeCurrent === 'function') {
    try { disposeCurrent(); } catch (e) { /* a page that fails to clean up
      must not stop the next one rendering */ }
    disposeCurrent = null;
  }

  const main = $('#main');
  replace(main, el('div', { class: 'loading-state', role: 'status' },
    el('div', { class: 'shimmer', 'aria-hidden': 'true' }),
    el('p', { class: 'small muted', text: 'Loading published evidence…' })));

  try {
    const module = await load();
    // The query is passed through so a page can key off its own hash params —
    // the compare page is `#/compare?ons=...&ons=...`, a URL that is the whole
    // comparison. Pages that do not ask for params ignore them.
    disposeCurrent = await module.render(main, { path, params });
    // A small, route-wide campaign cue keeps the familiar page-specific
    // headings intact while making the shared lens visible on every public
    // workbench and deep-detail route. It is presentation metadata only; all
    // evidence remains owned by the page module below it.
    const lensByRoute = {
      '/pay': ['Workforce', 'workforce'], '/providers': ['Workforce · Service access', 'access'],
      '/contracts': ['Public money', 'money'], '/geography': ['Service access · Public money', 'access'],
      '/treatment': ['Service access', 'access'], '/pfd': ['Safety & legal', 'safety'],
      '/claims': ['Safety & legal · Accountability', 'accountability'],
      '/documents': ['Accountability', 'accountability'],
      '/coverage': ['Accountability', 'accountability'], '/authorities': ['Service access · Accountability', 'access'],
      '/compare': ['Accountability', 'accountability'],
      // No '/' entry (BETA-069): the overview hero already carries an
      // "Accountability" lens badge in its kicker, and the extra route-lens
      // strip above it stacked into a visible duplicate at phone widths.
    };
    const lens = lensByRoute[base];
    if (lens && !main.querySelector(':scope > .route-lens')) {
      const cue = el('div', { class: `route-lens lens-${lens[1]}` },
        el('span', { class: 'eyebrow', text: 'Campaign lens' }),
        el('span', { text: lens[0] }));
      main.prepend(cue);
    }

    // BETA-077: a route-aware breadcrumb on a detail page. `path !== base`
    // means a `/key` suffix — a provider or authority detail. The parent
    // crumb links back to the exact filtered list the reader came from
    // (`lastListHash`), falling back to the section's own route. The entity
    // crumb is read from the page's own <h1> so the router does not need to
    // know each page's naming.
    if (path !== base && CRUMB_PARENTS[base]) {
      const [parentLabel, parentFallback] = CRUMB_PARENTS[base];
      const parentHref = lastListHash.get(base) || parentFallback;
      // The <h1>'s first text node — some heroes append status badges to it.
      const h1 = main.querySelector('.hero h1');
      const entity = (h1?.firstChild?.nodeType === Node.TEXT_NODE
        ? h1.firstChild.textContent : h1?.textContent || '').trim();
      const crumbs = el('nav', { class: 'breadcrumbs', 'aria-label': 'Breadcrumb' },
        el('a', { href: '#/' }, 'Overview'),
        el('span', { 'aria-hidden': 'true', text: '›' }),
        el('a', { href: parentHref }, `Back to ${parentLabel.toLowerCase()}`),
        entity ? el('span', { 'aria-hidden': 'true', text: '›' }) : null,
        entity ? el('span', { 'aria-current': 'page', text: entity }) : null);
      main.prepend(crumbs);
    }

    // The page content changed wholesale, but focus stayed on the nav link
    // that was clicked — a screen reader has no idea anything happened.
    // #main carries tabindex="-1" for exactly this; preventScroll keeps the
    // reader where they were instead of jumping the viewport to the top.
    if (navigating) main.focus({ preventScroll: true });

    // BETA-094: record this visit on the local research trail. Loaded on
    // demand so app.js and journey.js do not import each other; a failure
    // here must never stop a page rendering.
    import('/js/journey.js')
      .then((m) => m.recordVisit({ hash: hereHash, route: base.replace(/^\//, ''), label: routeLabel }))
      .catch(() => {});

    // BETA-077: restore scroll for a URL we have seen before (back/forward,
    // or a breadcrumb to a list); a fresh navigation starts at the top.
    lastRenderedHash = hereHash;
    if (scrollByHash.has(hereHash)) {
      const y = scrollByHash.get(hereHash);
      requestAnimationFrame(() => window.scrollTo(0, y));
    } else if (navigating) {
      window.scrollTo(0, 0);
    }
  } catch (error) {
    // components.js imports from this module, so pull the renderer lazily to
    // keep the module graph acyclic at load time (BETA-068).
    let card;
    try {
      const mod = await import('/js/components.js');
      card = mod.unavailableCard(error, () => render());
    } catch (e) {
      card = el('div', { class: 'chart-error' },
        el('strong', { text: 'This section could not be loaded.' }),
        el('span', { class: 'small', text: error.message }),
        el('button', { class: 'btn', onclick: () => render() }, 'Retry'));
    }
    replace(main, el('div', { class: 'section' }, card));
  }
}

const FILTER_ROUTES = new Set(['/pay', '/contracts', '/providers', '/pfd', '/treatment', '/geography', '/authorities', '/compare']);

function updateFilterVisibility(base) {
  const bar = $('#filterbar');
  const toggle = $('#filters-toggle');
  const relevant = FILTER_ROUTES.has(base);
  if (!relevant) {
    bar.hidden = true;
    toggle.hidden = true;
    $('#filter-summary').hidden = true;
    return;
  }
  bar.hidden = false;
  toggle.hidden = false;
  const mobile = window.matchMedia?.('(max-width: 720px)').matches;
  bar.classList.toggle('is-mobile-filter', Boolean(mobile));
  if (!mobile) {
    bar.classList.remove('show');
    bar.removeAttribute('aria-modal');
  }
  renderFilterSummary();
}

// Cached once by initFilterBar so a chip can show "Provider: Change Grow
// Live" rather than the raw key.
let providerNames = new Map();

// BETA-072: the last page's "N notices match" count, so the filter summary
// can say how much the current query returns. A page sets it after its fetch
// and the router clears it before the next page renders.
let resultCount = null;

/** Pages call this after loading so the shared summary can show the count.
 *  `null` clears it (a page with no single countable result). */
export function setFilterResultCount(count, noun = 'result') {
  resultCount = (count === null || count === undefined)
    ? null : { count: Number(count), noun };
  renderFilterSummary();
}

function renderFilterSummary() {
  const summary = $('#filter-summary');
  const s = getState();
  const chips = chipLabels(s, { providerName: providerNames.get(s.provider) });
  const errors = validateFilters(s);
  summary.replaceChildren();
  // The summary is the active-filter surface: no chips and no error means
  // nothing to show, even if a page reported a count (its own hero already
  // states totals).
  summary.hidden = chips.length === 0 && !errors.length;
  if (summary.hidden) return;

  if (chips.length) {
    summary.append(el('span', { class: 'filter-summary-label', text: 'Showing:' }));
    for (const chip of chips) {
      summary.append(el('button', {
        class: 'filter-chip', type: 'button',
        'aria-label': `Remove filter ${chip.text}`,
        onclick: () => setState({ [chip.key]: null }),
      }, `${chip.text} ×`));
    }
  }
  if (resultCount && chips.length) {
    const { count, noun } = resultCount;
    summary.append(el('span', { class: 'filter-summary-count',
      text: `${count.toLocaleString('en-GB')} ${noun}${count === 1 ? '' : 's'}` }));
  }
  if (errors.length) {
    summary.append(el('span', { class: 'filter-summary-error', role: 'alert',
      text: errors.join(' ') }));
  }
  if (chips.length) {
    summary.append(el('button', { class: 'filter-clear', type: 'button',
      onclick: () => clearFilters() }, 'Clear all'));
    // BETA-089: keep this exact search — route plus its whole filter query —
    // in the local saved-search list. Loaded on demand so app.js and
    // savedsearch.js do not import each other.
    summary.append(el('button', { class: 'filter-save', type: 'button',
      onclick: () => import('/js/savedsearch.js').then((m) => m.promptSave(location.hash)) },
      'Save search'));
  }
}

/** Clear-all (BETA-072): the whole hash query, not only the shared keys — a
 *  reader who clicks "Clear all" expects the page-local search and explorer
 *  filters gone too. The route path stays. */
function clearFilters() {
  const [path] = (location.hash.slice(1) || '/').split('?');
  for (const control of document.querySelectorAll('#filterbar [data-filter]')) control.value = '';
  const note = $('#filter-note');
  if (note) note.textContent = '';
  history.replaceState(null, '', `#${path}`);
  setState({ provider: null, yearFrom: null, yearTo: null });
}

// --- global filter bar -------------------------------------------------------

async function initFilterBar() {
  const bar = $('#filterbar');
  bar.hidden = false;

  let providers = [];
  try {
    providers = (await fetchJSON('providers')).providers || [];
  } catch (e) {
    $('#filter-note').textContent = 'Filters unavailable: ' + e.message;
    return;
  }
  providerNames = new Map(providers.map((p) => [p.provider_key, p.canonical_name]));

  const input = $('#f-provider');
  const list = $('#f-provider-list');
  // Fuse where it loaded, substring matching otherwise. Thirteen providers do
  // not need fuzzy search to be usable, so its absence degrades rather than
  // breaks.
  const fuse = window.Fuse
    ? new window.Fuse(providers, { keys: ['canonical_name', 'provider_key'], threshold: 0.4 })
    : null;

  const resetKeyboard = typeaheadKeyboard(input, list);

  const applyProvider = (key, label) => {
    input.value = label || '';
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    setState({ provider: key });
  };

  const showMatches = () => {
    const term = input.value.trim();
    const matches = !term ? providers
      : fuse ? fuse.search(term).map((r) => r.item)
        : providers.filter((p) => p.canonical_name.toLowerCase().includes(term.toLowerCase()));
    replace(list, [
      el('li', { role: 'option', onmousedown: () => applyProvider(null, '') }, 'All providers'),
      ...matches.slice(0, 12).map((p) => el('li', {
        role: 'option',
        class: p.is_target ? 'target' : null,
        onmousedown: () => applyProvider(p.provider_key, p.canonical_name),
      }, p.is_target ? `★ ${p.canonical_name}` : p.canonical_name)),
    ]);
    resetKeyboard();
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
  };

  input.addEventListener('focus', showMatches);
  input.addEventListener('input', showMatches);
  input.addEventListener('blur', () => setTimeout(() => { list.hidden = true; }, 120));

  // BETA-072: validate the year range before it becomes state. An invalid
  // pair (out of bounds, or from > to) is refused with an inline message
  // rather than sent to an endpoint that would 400 or silently return
  // nothing.
  const applyYear = (key, raw) => {
    const next = { ...getState(), [key]: raw || null };
    const errors = validateFilters(next);
    const note = $('#filter-note');
    if (errors.length) {
      note.textContent = errors[0];
      $('#f-year-from').setAttribute('aria-invalid', String(Boolean(errors.length)));
      $('#f-year-to').setAttribute('aria-invalid', String(Boolean(errors.length)));
      return;
    }
    note.textContent = '';
    $('#f-year-from').removeAttribute('aria-invalid');
    $('#f-year-to').removeAttribute('aria-invalid');
    setState({ [key]: raw || null });
  };
  $('#f-year-from').addEventListener('change', (e) => applyYear('yearFrom', e.target.value));
  $('#f-year-to').addEventListener('change', (e) => applyYear('yearTo', e.target.value));
  // Reset walks the controls rather than naming them, so a filter added to the
  // bar is cleared by this without anyone remembering to come back here. It
  // also keeps `data-filter` honest: a wrong key stops reset working, which is
  // visible, rather than rotting quietly.
  $('#f-reset').addEventListener('click', () => {
    const cleared = {};
    for (const control of document.querySelectorAll('#filterbar [data-filter]')) {
      control.value = '';
      cleared[control.dataset.filter] = null;
    }
    setState(cleared);
  });

  // Reflect state restored from a shared link.
  const s = getState();
  if (s.provider) {
    const match = providers.find((p) => p.provider_key === s.provider);
    if (match) input.value = match.canonical_name;
  }
  if (s.yearFrom) $('#f-year-from').value = s.yearFrom;
  if (s.yearTo) $('#f-year-to').value = s.yearTo;
  renderFilterSummary();
}

// --- find your council -------------------------------------------------------

/* W-17: a reader who knows their town, not their ONS code, has no entry
 * point. This navigates rather than filters — picking an authority goes
 * straight to its page — which is why it is in the top bar rather than the
 * filter bar: the filter bar's controls declare a state key for a page to
 * read (tests/test_portal_controls.py), and a navigator holds no state. */
async function initFindCouncil() {
  const input = $('#find-council');
  const list = $('#find-council-list');

  let authorities = [];
  try {
    authorities = (await fetchJSON('authorities')).authorities || [];
  } catch (e) {
    input.disabled = true;
    input.placeholder = 'Council search unavailable';
    return;
  }

  const fuse = window.Fuse
    ? new window.Fuse(authorities, { keys: ['name', 'ons_code'], threshold: 0.4 })
    : null;

  const go = (code, label) => {
    input.value = label || '';
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    if (code) location.hash = `#/authorities/${code}`;
    // BETA-069: the field now lives inside the section drawer. Picking a
    // council navigates via a listbox option (not an <a>), so the drawer's
    // link-click auto-close does not fire — close it here.
    const nav = $('#portal-nav');
    if (nav?.classList.contains('show')) {
      window.bootstrap?.Offcanvas.getInstance(nav)?.hide();
    }
  };

  const resetKeyboard = typeaheadKeyboard(input, list);

  const showMatches = () => {
    const term = input.value.trim();
    const matches = !term ? authorities.slice(0, 12)
      : fuse ? fuse.search(term).slice(0, 12).map((r) => r.item)
        : authorities.filter((a) =>
          a.name.toLowerCase().includes(term.toLowerCase())).slice(0, 12);
    replace(list, matches.map((a) => el('li', {
      role: 'option',
      onmousedown: () => go(a.ons_code, a.name),
    }, `${a.name} · ${a.ons_code}`)));
    resetKeyboard();
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
  };

  input.addEventListener('focus', showMatches);
  input.addEventListener('input', showMatches);
  input.addEventListener('blur', () => setTimeout(() => { list.hidden = true; }, 120));
  // Arrow keys move the highlight; Enter picks the highlighted option, or
  // the top match if none is highlighted yet — a search box that swallows
  // Enter invites the reader to type and wait for nothing.
}

// Bootstrap's dismissal data API deliberately prevents an anchor's normal
// action. Navigation links therefore never carry data-bs-dismiss: when the
// mobile offcanvas is open, close it here while leaving the link's hash or URL
// action intact. On desktop the same links are ordinary anchors.
function initMobileNavigation() {
  const nav = $('#portal-nav');
  nav?.addEventListener('click', (event) => {
    if (!event.target.closest('a') || !nav.classList.contains('show')) return;
    window.bootstrap?.Offcanvas.getInstance(nav)?.hide();
  });
}

// Release identity in the footer, from /api/v1/meta (BETA-039). A build and
// schema fingerprint so a reviewer can tell which deployment they are on;
// staying quiet on any failure, because a footer line is not worth an error.
async function initBuildIdentity() {
  const target = $('#build-identity');
  if (!target) return;
  let meta;
  try {
    meta = await fetchJSON('meta');
  } catch (e) {
    return;
  }
  const parts = [];
  if (meta.environment) parts.push(meta.environment);
  if (meta.revision) parts.push(`build ${String(meta.revision).slice(0, 10)}`);
  if (meta.schema && meta.schema.latest_migration) {
    parts.push(`schema ${meta.schema.latest_migration.replace(/\.sql$/, '')}`);
  }
  if (meta.build_time) parts.push(`deployed ${meta.build_time}`);
  if (!parts.length) return;
  target.textContent = parts.join(' · ');
  target.hidden = false;
}

// --- boot --------------------------------------------------------------------

function boot() {
  initPortalTheme();
  registerTheme();
  readStateFromUrl();
  initFilterBar();
  initFindCouncil();
  initMobileNavigation();
  initPalette();
  initBuildIdentity();
  subscribe(() => render());
  // BETA-072: a hash change is also how the back/forward buttons and an
  // edited address bar arrive. Re-sync the shared filter state from the URL
  // before rendering so history and shared links restore the exact query,
  // not just the route.
  window.addEventListener('hashchange', () => { readStateFromUrl(); render(); });
  window.addEventListener('portalthemechange', render);
  render();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
