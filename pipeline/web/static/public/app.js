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

import { registerTheme } from '/js/theme.js';

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
  if (window.dateFns?.formatDistanceToNow) {
    return `${window.dateFns.formatDistanceToNow(date)} ago`;
  }
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
    if (value !== null && value !== undefined && value !== '') {
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
      throw new Error((payload && payload.error) || `HTTP ${response.status}`);
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
  const [path] = (location.hash.slice(1) || '/').split('?');
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(state)) {
    if (value !== null && value !== undefined && value !== '') params.set(key, value);
  }
  const query = params.toString();
  const target = `#${path}${query ? `?${query}` : ''}`;
  if (location.hash !== target) history.replaceState(null, '', target);
}

function readStateFromUrl() {
  const params = parseHash().params;
  setState({
    provider: params.get('provider') || null,
    yearFrom: params.get('yearFrom') || null,
    yearTo: params.get('yearTo') || null,
  }, { silent: true });
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
  '/authorities': () => import('/js/pages/authority.js'),
};

let disposeCurrent = null;

async function render() {
  const { path } = parseHash();
  // Deep dives share their base module: /providers/:key is the providers
  // module with a key, /authorities/:ons_code the authority module with one.
  const base = path.startsWith('/providers/') ? '/providers'
    : path.startsWith('/authorities/') ? '/authorities' : path;
  const load = ROUTES[base] || ROUTES['/'];

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
  replace(main, el('div', { class: 'shimmer' }));

  try {
    const module = await load();
    disposeCurrent = await module.render(main, { path });
  } catch (error) {
    replace(main, el('div', { class: 'section' },
      el('div', { class: 'chart-error' },
        el('strong', { text: 'This section could not be loaded.' }),
        el('span', { class: 'small', text: error.message }),
        el('button', { class: 'btn', onclick: () => render() }, 'Retry'))));
  }
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

  const input = $('#f-provider');
  const list = $('#f-provider-list');
  // Fuse where it loaded, substring matching otherwise. Thirteen providers do
  // not need fuzzy search to be usable, so its absence degrades rather than
  // breaks.
  const fuse = window.Fuse
    ? new window.Fuse(providers, { keys: ['canonical_name', 'provider_key'], threshold: 0.4 })
    : null;

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
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
  };

  input.addEventListener('focus', showMatches);
  input.addEventListener('input', showMatches);
  input.addEventListener('blur', () => setTimeout(() => { list.hidden = true; }, 120));

  $('#f-year-from').addEventListener('change', (e) => setState({ yearFrom: e.target.value || null }));
  $('#f-year-to').addEventListener('change', (e) => setState({ yearTo: e.target.value || null }));
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
  };

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
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
  };

  input.addEventListener('focus', showMatches);
  input.addEventListener('input', showMatches);
  input.addEventListener('blur', () => setTimeout(() => { list.hidden = true; }, 120));
  // Enter picks the top match. A search box that swallows Enter invites the
  // reader to type and wait for nothing.
  input.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || list.hidden) return;
    const first = list.querySelector('li');
    if (first) first.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
  });
}

// --- boot --------------------------------------------------------------------

function boot() {
  registerTheme();
  readStateFromUrl();
  initFilterBar();
  initFindCouncil();
  subscribe(() => render());
  window.addEventListener('hashchange', render);
  render();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
