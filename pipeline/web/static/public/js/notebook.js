/* Evidence notebook (BETA-088).
 *
 * A single-browser research workspace: named collections of pinned records,
 * passages, charts, providers and authorities, each with a private note,
 * held in `localStorage` under one versioned, size-bounded key. Nothing
 * leaves the browser — there is no account and no server call — and every
 * read and write is guarded so private mode degrades to "nothing pinned"
 * rather than throwing.
 *
 * What is stored is only what the portal already shows: a public identifier
 * or a hash route, a display label, and whatever the reader typed as a note.
 * Import/export is the whole key as JSON, so a notebook is lossless to move
 * between browsers.
 */
'use strict';

import { el, replace } from '/app.js';

const KEY = 'sectortrace.notebook';
export const SCHEMA_VERSION = 1;

// Bounds. localStorage is a few MB per origin and shared with my_area and
// recent; a notebook that fills it would break them too, so writes that
// would cross MAX_BYTES are refused rather than truncating silently.
const MAX_BYTES = 200_000;
const MAX_COLLECTIONS = 25;
const MAX_ITEMS = 250;          // per collection
const MAX_NOTE = 2000;          // characters
const MAX_LABEL = 300;

// The kinds a pin can be, and the hash route each links to when its `ref`
// is a bare identifier rather than a full `#/...` route.
export const ITEM_KINDS = {
  record: null,
  passage: null,
  chart: null,
  provider: '#/providers/',
  authority: '#/authorities/',
};

function _fresh() {
  return { v: SCHEMA_VERSION, collections: [] };
}

function _clean(nb) {
  if (!nb || nb.v !== SCHEMA_VERSION || !Array.isArray(nb.collections)) return _fresh();
  const collections = nb.collections
    .filter((c) => c && typeof c.id === 'string' && typeof c.name === 'string' && Array.isArray(c.items))
    .slice(0, MAX_COLLECTIONS)
    .map((c) => ({
      id: c.id,
      name: String(c.name).slice(0, MAX_LABEL),
      created_at: c.created_at || new Date().toISOString(),
      updated_at: c.updated_at || c.created_at || new Date().toISOString(),
      items: c.items
        .filter((i) => i && typeof i.ref === 'string' && i.kind in ITEM_KINDS)
        .slice(0, MAX_ITEMS)
        .map((i) => ({
          id: typeof i.id === 'string' ? i.id : _id(),
          kind: i.kind,
          ref: String(i.ref).slice(0, MAX_LABEL),
          label: String(i.label || i.ref).slice(0, MAX_LABEL),
          note: String(i.note || '').slice(0, MAX_NOTE),
          added_at: i.added_at || new Date().toISOString(),
        })),
    }));
  return { v: SCHEMA_VERSION, collections };
}

function _id() {
  return `n${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

export function read() {
  try {
    return _clean(JSON.parse(localStorage.getItem(KEY) || 'null'));
  } catch (e) {
    return _fresh();
  }
}

/** Persist a cleaned notebook. Returns { ok, reason? }. A write that would
 *  exceed MAX_BYTES is refused so the reader can prune rather than lose an
 *  unrelated key. */
export function write(nb) {
  const clean = _clean(nb);
  let serialized;
  try {
    serialized = JSON.stringify(clean);
  } catch (e) {
    return { ok: false, reason: 'serialize' };
  }
  if (serialized.length > MAX_BYTES) return { ok: false, reason: 'full' };
  try {
    localStorage.setItem(KEY, serialized);
  } catch (e) {
    return { ok: false, reason: 'blocked' };  // private mode / quota
  }
  window.dispatchEvent(new CustomEvent('notebookchange'));
  return { ok: true };
}

export function collections() {
  return read().collections;
}

export function collectionCount() {
  return read().collections.length;
}

export function itemCount() {
  return read().collections.reduce((n, c) => n + c.items.length, 0);
}

export function createCollection(name) {
  const nb = read();
  if (nb.collections.length >= MAX_COLLECTIONS) return { ok: false, reason: 'limit' };
  const id = _id();
  const now = new Date().toISOString();
  nb.collections.push({ id, name: String(name || 'Untitled').slice(0, MAX_LABEL), created_at: now, updated_at: now, items: [] });
  return { ...write(nb), id };
}

export function renameCollection(id, name) {
  const nb = read();
  const c = nb.collections.find((x) => x.id === id);
  if (!c) return { ok: false, reason: 'missing' };
  c.name = String(name || c.name).slice(0, MAX_LABEL);
  c.updated_at = new Date().toISOString();
  return write(nb);
}

export function deleteCollection(id) {
  const nb = read();
  nb.collections = nb.collections.filter((c) => c.id !== id);
  return write(nb);
}

/** Move a collection or an item one place up (dir -1) or down (dir +1). */
export function reorder(collectionId, dir, itemId = null) {
  const nb = read();
  const list = itemId
    ? (nb.collections.find((c) => c.id === collectionId)?.items || null)
    : nb.collections;
  if (!list) return { ok: false, reason: 'missing' };
  const idx = itemId ? list.findIndex((i) => i.id === itemId) : list.findIndex((c) => c.id === collectionId);
  const next = idx + dir;
  if (idx < 0 || next < 0 || next >= list.length) return { ok: false, reason: 'edge' };
  [list[idx], list[next]] = [list[next], list[idx]];
  return write(nb);
}

/** Pin an item into a collection (created by name if `collectionId` is a
 *  name not an id, or if absent — the "quick pin" path). Idempotent on
 *  (kind, ref): a second pin updates the label/note instead of duplicating. */
export function addItem({ kind, ref, label, note = '', collectionId = null, collectionName = 'My evidence' }) {
  if (!(kind in ITEM_KINDS) || !ref) return { ok: false, reason: 'invalid' };
  const nb = read();
  let c = collectionId ? nb.collections.find((x) => x.id === collectionId) : null;
  if (!c) c = nb.collections.find((x) => x.name === collectionName);
  if (!c) {
    if (nb.collections.length >= MAX_COLLECTIONS) return { ok: false, reason: 'limit' };
    const now = new Date().toISOString();
    c = { id: _id(), name: String(collectionName).slice(0, MAX_LABEL), created_at: now, updated_at: now, items: [] };
    nb.collections.push(c);
  }
  const existing = c.items.find((i) => i.kind === kind && i.ref === ref);
  if (existing) {
    existing.label = String(label || existing.label).slice(0, MAX_LABEL);
    if (note) existing.note = String(note).slice(0, MAX_NOTE);
  } else {
    if (c.items.length >= MAX_ITEMS) return { ok: false, reason: 'full' };
    c.items.push({ id: _id(), kind, ref: String(ref).slice(0, MAX_LABEL), label: String(label || ref).slice(0, MAX_LABEL), note: String(note).slice(0, MAX_NOTE), added_at: new Date().toISOString() });
  }
  c.updated_at = new Date().toISOString();
  return { ...write(nb), collectionId: c.id };
}

export function removeItem(collectionId, itemId) {
  const nb = read();
  const c = nb.collections.find((x) => x.id === collectionId);
  if (!c) return { ok: false, reason: 'missing' };
  c.items = c.items.filter((i) => i.id !== itemId);
  c.updated_at = new Date().toISOString();
  return write(nb);
}

export function setNote(collectionId, itemId, note) {
  const nb = read();
  const i = nb.collections.find((x) => x.id === collectionId)?.items.find((x) => x.id === itemId);
  if (!i) return { ok: false, reason: 'missing' };
  i.note = String(note || '').slice(0, MAX_NOTE);
  return write(nb);
}

/** Is this (kind, ref) pinned anywhere? Returns the collection id or null. */
export function findPin(kind, ref) {
  for (const c of read().collections) {
    if (c.items.some((i) => i.kind === kind && i.ref === ref)) return c.id;
  }
  return null;
}

// --- lossless import / export ---------------------------------------------

export function exportJSON() {
  return JSON.stringify(read(), null, 2);
}

/** Replace the whole notebook from an exported JSON string. Returns
 *  { ok, collections?, reason? }. Rejects anything that is not a
 *  version-matched notebook rather than merging partial data. */
export function importJSON(text, { merge = false } = {}) {
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (e) {
    return { ok: false, reason: 'not JSON' };
  }
  if (!parsed || parsed.v !== SCHEMA_VERSION || !Array.isArray(parsed.collections)) {
    return { ok: false, reason: `not a v${SCHEMA_VERSION} notebook` };
  }
  const incoming = _clean(parsed);
  const next = merge
    ? _clean({ v: SCHEMA_VERSION, collections: [...read().collections, ...incoming.collections] })
    : incoming;
  const res = write(next);
  return res.ok ? { ok: true, collections: next.collections.length } : res;
}

// --- the pin button pages drop in ---------------------------------------

/** A toggle: pins (kind, ref, label) into the reader's default collection,
 *  or removes it if already there. Re-renders itself in place. */
export function notebookButton({ kind, ref, label, className = 'btn' }) {
  const btn = el('button', { type: 'button', class: className });
  const paint = () => {
    const where = findPin(kind, ref);
    btn.textContent = where ? 'In notebook ✓' : '+ Notebook';
    btn.setAttribute('aria-pressed', String(Boolean(where)));
  };
  btn.addEventListener('click', () => {
    const where = findPin(kind, ref);
    if (where) removeItem(where, read().collections.find((c) => c.id === where).items.find((i) => i.kind === kind && i.ref === ref).id);
    else addItem({ kind, ref, label });
    paint();
  });
  window.addEventListener('notebookchange', paint);
  paint();
  return btn;
}

// --- the #/notebook page ------------------------------------------------

function _download(name, text) {
  try {
    const blob = new Blob([text], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = el('a', { href: url, download: name });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) {
    /* nothing to do — the browser blocked the download */
  }
}

function renderCollection(c, rerender) {
  const items = c.items.map((it, idx) => {
    const routePrefix = ITEM_KINDS[it.kind];
    const href = routePrefix ? `${routePrefix}${encodeURIComponent(it.ref)}` : it.ref;
    // `el()` sets attributes, and a <textarea>'s initial text is its child
    // content, not a `value` attribute — pass the note as a text child.
    const noteBox = el('textarea', {
      class: 'nb-note', rows: '2',
      placeholder: 'private note…',
      onchange: (e) => setNote(c.id, it.id, e.target.value),
    }, it.note || '');
    return el('li', { class: 'nb-item' },
      el('div', { class: 'nb-item-head' },
        el('span', { class: 'nb-kind', text: it.kind }),
        el('a', { href, text: it.label }),
        el('span', { class: 'spacer' }),
        el('button', { class: 'linklike', type: 'button', title: 'move up',
          onclick: () => { reorder(c.id, -1, it.id); rerender(); } }, '↑'),
        el('button', { class: 'linklike', type: 'button', title: 'move down',
          onclick: () => { reorder(c.id, 1, it.id); rerender(); } }, '↓'),
        el('button', { class: 'linklike', type: 'button',
          onclick: () => { removeItem(c.id, it.id); rerender(); } }, 'Remove')),
      noteBox);
  });
  return el('div', { class: 'nb-collection' },
    el('div', { class: 'nb-collection-head' },
      el('input', { class: 'nb-name', value: c.name,
        onchange: (e) => renameCollection(c.id, e.target.value) }),
      el('span', { class: 'nb-count', text: `${c.items.length} item${c.items.length === 1 ? '' : 's'}` }),
      el('span', { class: 'spacer' }),
      el('button', { class: 'linklike', type: 'button', title: 'move collection up',
        onclick: () => { reorder(c.id, -1); rerender(); } }, '↑'),
      el('button', { class: 'linklike', type: 'button', title: 'move collection down',
        onclick: () => { reorder(c.id, 1); rerender(); } }, '↓'),
      el('button', { class: 'linklike', type: 'button',
        onclick: () => { if (confirm(`Delete “${c.name}” and its ${c.items.length} items?`)) { deleteCollection(c.id); rerender(); } } }, 'Delete')),
    items.length ? el('ul', { class: 'nb-items' }, ...items)
      : el('p', { class: 'small muted', text: 'Nothing pinned here yet. Use the “+ Notebook” button on a provider, authority, document passage or chart.' }));
}

export async function render(main) {
  const rerender = () => render(main);
  const nb = read();

  const importInput = el('input', { type: 'file', accept: 'application/json', class: 'nb-hidden-input',
    onchange: (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      const fr = new FileReader();
      fr.onload = () => {
        const res = importJSON(String(fr.result), { merge: true });
        alert(res.ok ? `Imported — ${res.collections} collection(s) now in your notebook.` : `Import failed: ${res.reason}.`);
        rerender();
      };
      fr.readAsText(file);
    } });

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Evidence notebook' }),
      el('p', { class: 'lede', text:
        'Your own collections of pinned records, passages, charts, providers '
        + 'and authorities, with private notes. Everything here is stored only '
        + 'in this browser — there is no account — so export it to keep it or '
        + 'move it.' })),
    el('div', { class: 'panel' },
      el('div', { class: 'nb-toolbar' },
        (() => {
          const name = el('input', { class: 'nb-new-name', placeholder: 'New collection name', 'aria-label': 'New collection name' });
          return el('span', { class: 'nb-new' }, name,
            el('button', { class: 'btn', type: 'button',
              onclick: () => { const r = createCollection(name.value || 'Untitled'); if (!r.ok) alert(`Could not add: ${r.reason}.`); rerender(); } }, 'Add collection'));
        })(),
        el('span', { class: 'spacer' }),
        el('button', { class: 'btn', type: 'button',
          onclick: () => _download('sectortrace-notebook.json', exportJSON()) }, 'Export JSON'),
        el('button', { class: 'btn', type: 'button',
          onclick: () => importInput.click() }, 'Import JSON'),
        importInput),
      nb.collections.length
        ? el('div', { class: 'nb-collections' }, ...nb.collections.map((c) => renderCollection(c, rerender)))
        : el('p', { class: 'muted', text: 'No collections yet. Add one above, or pin something with the “+ Notebook” button elsewhere in the portal.' })));

  replace(main, page);
  return () => {};
}
