/* Recently viewed entities (BETA-077).
 *
 * A short local list of the providers and authorities the reader has opened,
 * so a research session has a trail back to where it has been. `localStorage`
 * holds a capped array of `{type, id, name, at}` — a public identifier and a
 * display name the portal already shows, nothing more — and every access is
 * guarded so private mode degrades to "no list".
 */
'use strict';

import { el, replace } from '/app.js';

const KEY = 'sectortrace.recent';
const CAP = 12;
const TYPES = { provider: '#/providers/', authority: '#/authorities/' };

export function getRecent() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || '[]');
    return Array.isArray(raw)
      ? raw.filter((r) => r && TYPES[r.type] && r.id && r.name).slice(0, CAP)
      : [];
  } catch (e) {
    return [];
  }
}

export function pushRecent({ type, id, name }) {
  if (!TYPES[type] || !id || !name) return;
  try {
    const next = [{ type, id, name, at: new Date().toISOString() },
      ...getRecent().filter((r) => !(r.type === type && r.id === id))].slice(0, CAP);
    localStorage.setItem(KEY, JSON.stringify(next));
    window.dispatchEvent(new CustomEvent('recentchange'));
  } catch (e) {
    /* private mode — the list just does not persist */
  }
}

export function clearRecent() {
  try { localStorage.removeItem(KEY); } catch (e) { /* private mode */ }
  window.dispatchEvent(new CustomEvent('recentchange'));
}

/** A compact "Recently viewed" block. Renders nothing when the list is empty. */
export function renderRecentList(container) {
  const items = getRecent();
  if (!items.length) { replace(container, el('span', {})); return; }
  replace(container, el('div', { class: 'recent-list' },
    el('div', { class: 'recent-head' },
      el('h2', { text: 'Recently viewed' }),
      el('button', { class: 'linklike', type: 'button',
        onclick: () => { clearRecent(); renderRecentList(container); } }, 'Clear')),
    el('ul', {},
      ...items.map((r) => el('li', {},
        el('a', { href: `${TYPES[r.type]}${encodeURIComponent(r.id)}` }, r.name),
        el('span', { class: 'recent-type', text: ` · ${r.type}` }))))));
}
