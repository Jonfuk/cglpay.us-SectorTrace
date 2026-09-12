/* Visual research journey (BETA-094).
 *
 * The browser's back history is linear; a researcher's path is a tree — they
 * follow a lead, back up, try another. This records each route visit as a
 * node whose parent is the node the reader was on, so revisiting an earlier
 * page and going somewhere new makes a branch, not a straight line. Named
 * checkpoints mark the steps worth returning to.
 *
 * Local only, bounded, guarded. What is stored is a hash route, the page
 * label the portal already shows, a timestamp and the parent node id —
 * nothing the URL bar does not already display.
 */
'use strict';

import { el, replace } from '/app.js';

const KEY = 'sectortrace.journey';
export const SCHEMA_VERSION = 1;
const MAX_EVENTS = 150;
const MAX_LABEL = 200;
const MAX_NAME = 80;

function _fresh() { return { v: SCHEMA_VERSION, events: [], current: null }; }

function _read() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (!raw || raw.v !== SCHEMA_VERSION || !Array.isArray(raw.events)) return _fresh();
    const events = raw.events
      .filter((e) => e && typeof e.id === 'string' && typeof e.hash === 'string')
      .slice(-MAX_EVENTS)
      .map((e) => ({
        id: e.id,
        hash: String(e.hash).slice(0, 500),
        route: String(e.route || '').slice(0, 64),
        label: String(e.label || e.hash).slice(0, MAX_LABEL),
        at: e.at || new Date().toISOString(),
        parent: typeof e.parent === 'string' ? e.parent : null,
        name: e.name ? String(e.name).slice(0, MAX_NAME) : null,
      }));
    const ids = new Set(events.map((e) => e.id));
    for (const e of events) if (e.parent && !ids.has(e.parent)) e.parent = null;
    const current = ids.has(raw.current) ? raw.current : (events[events.length - 1]?.id || null);
    return { v: SCHEMA_VERSION, events, current };
  } catch (e) {
    return _fresh();
  }
}

function _write(state) {
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
    window.dispatchEvent(new CustomEvent('journeychange'));
  } catch (e) { /* private mode — the trail just does not persist */ }
}

function _id() {
  return `j${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

/** Path of ids from an event up to its root. */
function _ancestors(events, id) {
  const byId = new Map(events.map((e) => [e.id, e]));
  const out = [];
  let cur = byId.get(id);
  while (cur) { out.push(cur.id); cur = cur.parent ? byId.get(cur.parent) : null; }
  return out;
}

function _prune(state) {
  if (state.events.length <= MAX_EVENTS) return;
  const keep = new Set(_ancestors(state.events, state.current));
  const childCount = new Map();
  for (const e of state.events) if (e.parent) childCount.set(e.parent, (childCount.get(e.parent) || 0) + 1);
  // Drop oldest leaves that are not named and not on the current path.
  const ordered = [...state.events].sort((a, b) => a.at.localeCompare(b.at));
  for (const e of ordered) {
    if (state.events.length <= MAX_EVENTS) break;
    if (keep.has(e.id) || e.name || (childCount.get(e.id) || 0) > 0) continue;
    state.events = state.events.filter((x) => x.id !== e.id);
  }
}

/** Record a visit. Called by the router after a successful render. */
export function recordVisit({ hash, route, label }) {
  if (!hash || route === 'journey') return;
  const state = _read();
  const existing = state.events.find((e) => e.hash === hash);
  if (existing) {
    if (label) existing.label = String(label).slice(0, MAX_LABEL);
    state.current = existing.id;
    _write(state);
    return;
  }
  const event = {
    id: _id(), hash, route: route || '', label: String(label || hash).slice(0, MAX_LABEL),
    at: new Date().toISOString(), parent: state.current, name: null,
  };
  state.events.push(event);
  state.current = event.id;
  _prune(state);
  _write(state);
}

export function list() {
  const state = _read();
  return { events: state.events, current: state.current };
}

export function checkpoint(id, name) {
  const state = _read();
  const e = state.events.find((x) => x.id === id);
  if (!e) return;
  e.name = name ? String(name).slice(0, MAX_NAME) : null;
  _write(state);
}

export function clear() {
  _write(_fresh());
}

// --- the #/journey page ------------------------------------------------

function _buildTree(events) {
  const children = new Map();
  for (const e of events) {
    const key = e.parent || '__root__';
    if (!children.has(key)) children.set(key, []);
    children.get(key).push(e);
  }
  for (const list of children.values()) list.sort((a, b) => a.at.localeCompare(b.at));
  return children;
}

function _node(e, children, current, rerender, depth) {
  const kids = children.get(e.id) || [];
  const isCurrent = e.id === current;
  const row = el('div', { class: `jr-node${isCurrent ? ' jr-current' : ''}${e.name ? ' jr-checkpoint' : ''}` },
    e.name ? el('span', { class: 'jr-diamond', text: '◆ ' }) : null,
    el('a', { href: e.hash, class: 'jr-link' }, e.name || e.label),
    e.name ? null : el('span', { class: 'jr-route small muted', text: ` ${e.route || '/'}` }),
    el('button', {
      class: 'linklike jr-name', type: 'button',
      onclick: () => {
        const name = window.prompt('Name this step (blank to clear)', e.name || '');
        if (name !== null) { checkpoint(e.id, name.trim() || null); rerender(); }
      },
    }, e.name ? 'rename' : 'checkpoint'));
  // Nested divs, so each level adds its indent relative to its parent.
  const wrap = el('div', { class: 'jr-branch', style: depth ? 'margin-left:16px' : '' }, row);
  for (const kid of kids) wrap.append(_node(kid, children, current, rerender, depth + 1));
  return wrap;
}

export async function render(main) {
  const rerender = () => render(main);
  const { events, current } = list();
  const children = _buildTree(events);
  const roots = children.get('__root__') || [];

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Research journey' }),
      el('p', { class: 'lede', text:
        'This session as a branching trail — every page you opened, in the '
        + 'order and shape you explored it, with the checkpoints you named. '
        + 'Stored only in this browser.' }),
      el('div', { class: 'hero-actions' },
        el('button', { class: 'btn', type: 'button',
          onclick: () => { if (confirm('Clear the whole trail?')) { clear(); rerender(); } } },
          'Clear trail'))),
    el('div', { class: 'panel' },
      events.length
        ? el('div', { class: 'jr-tree' }, ...roots.map((r) => _node(r, children, current, rerender, 0)))
        : el('p', { class: 'muted', text: 'Nothing recorded yet. Browse the portal and your trail builds here.' })));

  replace(main, page);
  return () => {};
}
