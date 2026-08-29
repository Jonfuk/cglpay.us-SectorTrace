/* Saved searches and change alerts (BETA-089).
 *
 * A repeat researcher saves a complete search — its route and its full filter
 * query — into `localStorage` (guarded, public identifiers only). Later, after
 * a release, "Check for new" re-runs the same query and shows the count
 * against the last-seen count. For the change stream there is also a stable
 * Atom feed (`/api/v1/feed/changes.atom`) to subscribe to externally.
 *
 * No account, no server state: a saved search is a name plus a `#/...` hash.
 */
'use strict';

import { el, replace, fetchJSON } from '/app.js';

const KEY = 'sectortrace.saved_searches';
export const SCHEMA_VERSION = 1;
const MAX_SEARCHES = 50;
const MAX_NAME = 120;

// Route -> the /api/v1 endpoint whose payload carries the result count for
// that route's filters. Routes not listed here can still be saved and re-run;
// they just do not get a "new matches" number.
const COUNT_ENDPOINT = {
  contracts: 'contracts', providers: 'providers', pfd: 'pfd',
  authorities: 'authorities', geography: 'geography', changes: 'changes',
};

function _fresh() { return { v: SCHEMA_VERSION, searches: [] }; }

function _read() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (!raw || raw.v !== SCHEMA_VERSION || !Array.isArray(raw.searches)) return _fresh();
    return {
      v: SCHEMA_VERSION,
      searches: raw.searches
        .filter((s) => s && typeof s.id === 'string' && typeof s.hash === 'string')
        .slice(0, MAX_SEARCHES)
        .map((s) => ({
          id: s.id,
          name: String(s.name || 'Untitled').slice(0, MAX_NAME),
          hash: String(s.hash).slice(0, 500),
          route: String(s.route || '').slice(0, 64),
          query: String(s.query || '').slice(0, 400),
          saved_at: s.saved_at || new Date().toISOString(),
          last_count: Number.isFinite(s.last_count) ? s.last_count : null,
          last_checked: s.last_checked || null,
        })),
    };
  } catch (e) {
    return _fresh();
  }
}

function _write(obj) {
  try {
    localStorage.setItem(KEY, JSON.stringify(obj));
    window.dispatchEvent(new CustomEvent('savedsearchchange'));
    return { ok: true };
  } catch (e) {
    return { ok: false, reason: 'blocked' };
  }
}

function _id() {
  return `s${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

function _parse(hash) {
  const [path, q = ''] = String(hash || '').replace(/^#/, '').split('?');
  return { route: path.replace(/^\//, '').split('/')[0], query: q };
}

export function list() {
  return _read().searches;
}

/** Save (or update, matched on hash) a search. */
export function saveSearch({ name, hash }) {
  const nb = _read();
  const { route, query } = _parse(hash);
  const existing = nb.searches.find((s) => s.hash === hash);
  if (existing) {
    existing.name = String(name || existing.name).slice(0, MAX_NAME);
    return { ...(_write(nb)), id: existing.id };
  }
  if (nb.searches.length >= MAX_SEARCHES) return { ok: false, reason: 'limit' };
  const id = _id();
  nb.searches.unshift({
    id, name: String(name || 'Untitled').slice(0, MAX_NAME), hash, route, query,
    saved_at: new Date().toISOString(), last_count: null, last_checked: null,
  });
  return { ...(_write(nb)), id };
}

export function removeSearch(id) {
  const nb = _read();
  nb.searches = nb.searches.filter((s) => s.id !== id);
  return _write(nb);
}

export function renameSearch(id, name) {
  const nb = _read();
  const s = nb.searches.find((x) => x.id === id);
  if (!s) return { ok: false, reason: 'missing' };
  s.name = String(name || s.name).slice(0, MAX_NAME);
  return _write(nb);
}

export function markSeen(id, count) {
  const nb = _read();
  const s = nb.searches.find((x) => x.id === id);
  if (!s) return { ok: false, reason: 'missing' };
  s.last_count = Number.isFinite(count) ? count : s.last_count;
  s.last_checked = new Date().toISOString();
  return _write(nb);
}

function _countOf(payload) {
  if (!payload || typeof payload !== 'object') return null;
  if (Number.isFinite(payload.total)) return payload.total;
  if (Number.isFinite(payload.count)) return payload.count;
  for (const key of ['events', 'datasets', 'results', 'rows', 'notices', 'providers', 'authorities']) {
    if (Array.isArray(payload[key])) return payload[key].length;
  }
  return null;
}

/** Re-run a saved search's query and report the count and the delta against
 *  its last-seen count. Does not persist — call `markSeen` to accept it. */
export async function checkNew(search) {
  const endpoint = COUNT_ENDPOINT[search.route];
  if (!endpoint) return { supported: false };
  const params = {};
  for (const [k, v] of new URLSearchParams(search.query)) params[k] = v;
  let payload;
  try {
    payload = await fetchJSON(endpoint, params);
  } catch (e) {
    return { supported: true, error: true };
  }
  const count = _countOf(payload);
  if (count == null) return { supported: false };
  const base = Number.isFinite(search.last_count) ? search.last_count : count;
  return { supported: true, count, delta: count - base, first: search.last_count == null };
}

/** The stable Atom feed URL for a saved "changes" search, or null. */
export function feedURL(search) {
  if (search.route !== 'changes') return null;
  const q = new URLSearchParams(search.query);
  const keep = new URLSearchParams();
  for (const k of ['kind', 'source', 'since']) if (q.get(k)) keep.set(k, q.get(k));
  return `/api/v1/feed/changes.atom${keep.toString() ? `?${keep}` : ''}`;
}

// --- the "Save search" control the filter bar drops in ------------------

export function promptSave(hash) {
  const { route } = _parse(hash);
  const name = window.prompt('Name this saved search', route || 'search');
  if (name) saveSearch({ name, hash });
}

// --- the #/saved page --------------------------------------------------

export async function render(main) {
  const rerender = () => render(main);
  const searches = list();

  const rows = await Promise.all(searches.map(async (s) => {
    const res = await checkNew(s);
    const status = !res.supported
      ? el('span', { class: 'small muted', text: 'run to see matches' })
      : res.error
        ? el('span', { class: 'small muted', text: 'check failed' })
        : res.first
          ? el('span', { class: 'small', text: `${res.count} match${res.count === 1 ? '' : 'es'} now (first check)` })
          : el('span', { class: `small ${res.delta > 0 ? 'ss-new' : 'muted'}` },
              res.delta > 0 ? `+${res.delta} new since last seen (${res.count} total)`
                : res.delta < 0 ? `${res.delta} since last seen (${res.count} total)`
                  : `no change (${res.count})`);
    const feed = feedURL(s);
    return el('li', { class: 'ss-item' },
      el('div', { class: 'ss-item-head' },
        el('input', { class: 'ss-name', value: s.name,
          onchange: (e) => renameSearch(s.id, e.target.value) }),
        el('span', { class: 'spacer' }),
        el('a', { class: 'btn tiny', href: s.hash }, 'Run'),
        el('button', { class: 'btn tiny', type: 'button',
          onclick: async () => { const r = await checkNew(s); if (r.supported && !r.error) markSeen(s.id, r.count); rerender(); } }, 'Mark seen'),
        el('button', { class: 'linklike', type: 'button',
          onclick: () => { removeSearch(s.id); rerender(); } }, 'Delete')),
      el('div', { class: 'small muted', text: s.query ? s.query.replace(/&/g, ' · ') : 'no filters — the whole list' }),
      status,
      feed
        ? el('p', { class: 'small' }, 'Atom feed: ',
            el('code', {}, `${location.origin}${feed}`))
        : null);
  }));

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Saved searches' }),
      el('p', { class: 'lede', text:
        'Searches you saved from the filter bar. Everything is stored in this '
        + 'browser only. “Check” re-runs the query and compares the match count '
        + 'with what you last saw; a saved change-stream search also has a '
        + 'stable Atom feed you can subscribe to.' })),
    el('div', { class: 'panel' },
      searches.length
        ? el('ul', { class: 'ss-list' }, ...rows)
        : el('p', { class: 'muted', text: 'No saved searches yet. Filter any list, then use “Save search” in the filter bar.' })));

  replace(main, page);
  return () => {};
}
