/* Ctrl+K: go somewhere by typing its name.
 *
 * The warehouse has 65 tables and the queue has a couple of dozen live
 * (module, item type) pairs. Both are reachable by clicking, and both are
 * slow to reach that way once you know what you want -- the database sidebar
 * needs scrolling past forty names, and a worklist needs two dropdowns set in
 * the right order because one filters the other.
 *
 * So this offers the same destinations by name, and nothing else. Every entry
 * either sets the URL hash -- which app.js already treats as the single way
 * anything navigates -- or flips a control the page already has. It knows no
 * application state of its own, and deliberately cannot decide anything:
 * approvals stay where they can be seen.
 */
import { el, store } from './dom.js';
import { cycleTheme } from './theme.js';

const TABS = [
  ['overview', 'Overview'],
  ['review', 'Review queue'],
  ['database', 'Database browser'],
  ['sql', 'SQL'],
];

// Facets and the table list change as modules run and items are decided, but
// not between two keystrokes. Cached for a minute, refreshed in the
// background so an open palette is never waiting on the network.
const MAX_AGE_MS = 60_000;
const MAX_RESULTS = 40;

let overlay = null;
let input = null;
let list = null;
let restoreFocusTo = null;

let commands = [];
let active = 0;
let catalogue = { objects: [], facets: null, fetchedAt: 0, inFlight: null };

// --- matching -----------------------------------------------------------------

/* Contiguous matches beat scattered ones and earlier beats later, which
 * between them put "contracts" above "charity_accounts_documents" for "con".
 * Subsequence matching is the fallback, so "cad" still finds the latter. */
function score(text, query) {
  const haystack = text.toLowerCase();
  const direct = haystack.indexOf(query);
  if (direct !== -1) return 1000 - direct;

  let from = 0;
  let previous = -1;
  let gaps = 0;
  for (const character of query) {
    const at = haystack.indexOf(character, from);
    if (at === -1) return -1;
    if (previous !== -1) gaps += at - previous - 1;
    previous = at;
    from = at + 1;
  }
  return 500 - Math.min(gaps, 400);
}

function ranked(query) {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed) return commands.slice(0, MAX_RESULTS);
  return commands
    .map((command) => ({ command, score: score(`${command.label} ${command.detail || ''}`, trimmed) }))
    .filter((entry) => entry.score >= 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, MAX_RESULTS)
    .map((entry) => entry.command);
}

// --- the command list ---------------------------------------------------------

function go(hash) {
  // Everything navigates by hash, so the palette does too rather than calling
  // into app.js. Same code path as a pasted link or the back button.
  if (location.hash === hash) return;
  location.hash = hash;
}

function flip(selector) {
  const control = document.querySelector(selector);
  if (!control) return;
  control.checked = !control.checked;
  control.dispatchEvent(new Event('change'));
}

function copyLink() {
  // navigator.clipboard is undefined on plain http from another machine --
  // only localhost counts as a secure context -- and this UI is routinely
  // reached over the LAN.
  if (!navigator.clipboard) {
    window.prompt('Copy this link:', location.href);
    return;
  }
  navigator.clipboard.writeText(location.href);
}

function buildCommands() {
  const built = [];

  for (const [tab, label] of TABS) {
    built.push({ kind: 'Go to', label, detail: `#${tab}`, run: () => go(`#${tab}`) });
  }

  built.push(
    { kind: 'Action', label: 'Change theme', detail: 'light · dark · system', run: cycleTheme },
    { kind: 'Action', label: 'Toggle dense rows', detail: 'review queue', run: () => flip('#f-dense') },
    { kind: 'Action', label: 'Clear review filters', detail: 'back to all pending', run: () => go('#review') },
    { kind: 'Action', label: 'Copy link to this view', detail: location.hash || '#overview', run: copyLink },
    { kind: 'Action', label: 'Set reviewer name', detail: 'decisions are recorded against it',
      run: () => { const box = document.getElementById('reviewer'); if (box) box.focus(); } },
  );

  for (const status of ['approved', 'rejected', 'all']) {
    built.push({
      kind: 'Queue', label: `${status[0].toUpperCase()}${status.slice(1)} items`,
      detail: `status=${status}`, run: () => go(`#review?status=${status}`),
    });
  }

  const facets = catalogue.facets;
  if (facets) {
    const worklists = [...facets.item_types]
      .filter((entry) => entry.pending > 0)
      .sort((a, b) => b.pending - a.pending);
    for (const entry of worklists) {
      built.push({
        kind: 'Worklist',
        label: `${entry.module} · ${entry.item_type}`,
        detail: `${entry.pending.toLocaleString('en-GB')} pending`,
        run: () => go(`#review?module=${encodeURIComponent(entry.module)}`
          + `&item_type=${encodeURIComponent(entry.item_type)}`),
      });
    }
  }

  for (const object of catalogue.objects) {
    built.push({
      kind: object.type === 'view' ? 'View' : 'Table',
      label: object.name,
      detail: object.restricted ? 'personal data'
        : (object.rows === null ? 'view' : `${object.rows.toLocaleString('en-GB')} rows`),
      restricted: object.restricted,
      run: () => go(`#database?table=${encodeURIComponent(object.name)}`),
    });
  }

  commands = built;
}

async function refreshCatalogue() {
  if (catalogue.inFlight) return catalogue.inFlight;
  if (Date.now() - catalogue.fetchedAt < MAX_AGE_MS) return null;

  catalogue.inFlight = (async () => {
    // Failure here is not worth a toast: the palette still navigates to every
    // tab, and the sidebar remains the way to find a table.
    const [schema, facets] = await Promise.all([
      fetch('/api/schema').then((r) => (r.ok ? r.json() : null)).catch(() => null),
      fetch('/api/review/facets').then((r) => (r.ok ? r.json() : null)).catch(() => null),
    ]);
    if (schema) catalogue.objects = schema.objects || [];
    if (facets) catalogue.facets = facets;
    catalogue.fetchedAt = Date.now();
    catalogue.inFlight = null;
    buildCommands();
    if (overlay && !overlay.hidden) render();
  })();
  return catalogue.inFlight;
}

// --- the overlay --------------------------------------------------------------

function build() {
  input = el('input', {
    type: 'text', id: 'palette-input', autocomplete: 'off', spellcheck: 'false',
    placeholder: 'Jump to a tab, a table, or a worklist…',
    'aria-label': 'Command palette', 'aria-controls': 'palette-list',
    oninput: () => { active = 0; render(); },
  });

  list = el('div', { class: 'palette-list', id: 'palette-list', role: 'listbox' });

  overlay = el('div', {
    class: 'palette-backdrop', hidden: true,
    onmousedown: (event) => { if (event.target === overlay) close(); },
  }, el('div', { class: 'palette', role: 'dialog', 'aria-modal': 'true',
    'aria-label': 'Command palette' },
    el('div', { class: 'palette-head' }, input),
    list,
    el('div', { class: 'palette-foot muted small' },
      el('span', {}, el('kbd', { text: '↑' }), el('kbd', { text: '↓' }), ' move'),
      el('span', {}, el('kbd', { text: 'Enter' }), ' open'),
      el('span', {}, el('kbd', { text: 'Esc' }), ' close'))));

  document.body.append(overlay);
}

function render() {
  const results = ranked(input.value);
  active = Math.max(0, Math.min(active, results.length - 1));

  if (!results.length) {
    list.replaceChildren(el('div', { class: 'palette-empty muted', text: 'Nothing matches.' }));
    return;
  }

  list.replaceChildren(...results.map((command, index) => el('div', {
    class: `palette-item${index === active ? ' active' : ''}${command.restricted ? ' restricted' : ''}`,
    role: 'option', 'aria-selected': String(index === active),
    onmousemove: () => { if (active !== index) { active = index; paintActive(); } },
    onclick: () => run(command),
  },
    el('span', { class: 'palette-kind', text: command.kind }),
    el('span', { class: 'palette-label', text: command.label }),
    command.detail ? el('span', { class: 'palette-detail muted', text: command.detail }) : null)));

  scrollActiveIntoView();
}

/* Repainting the whole list on every arrow key loses the scroll position and
 * costs a rebuild of forty nodes for a two-class change. */
function paintActive() {
  const items = [...list.children];
  items.forEach((node, index) => {
    node.classList.toggle('active', index === active);
    node.setAttribute('aria-selected', String(index === active));
  });
  scrollActiveIntoView();
}

function scrollActiveIntoView() {
  const node = list.children[active];
  if (node && node.scrollIntoView) node.scrollIntoView({ block: 'nearest' });
}

function move(delta) {
  const count = list.children.length;
  if (!count) return;
  active = (active + delta + count) % count;
  paintActive();
}

function run(command) {
  close();
  try { command.run(); }
  catch (e) { /* a palette entry must not be able to break the page */ }
}

export function openPalette() {
  if (!overlay) build();
  restoreFocusTo = document.activeElement;
  buildCommands();
  overlay.hidden = false;
  input.value = '';
  active = 0;
  render();
  input.focus();
  refreshCatalogue();
}

export function close() {
  if (!overlay || overlay.hidden) return;
  overlay.hidden = true;
  if (restoreFocusTo && restoreFocusTo.focus) restoreFocusTo.focus();
  restoreFocusTo = null;
}

export function initPalette() {
  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      if (overlay && !overlay.hidden) return close();
      return openPalette();
    }

    if (!overlay || overlay.hidden) return;

    if (event.key === 'Escape') { event.preventDefault(); return close(); }
    if (event.key === 'ArrowDown') { event.preventDefault(); return move(1); }
    if (event.key === 'ArrowUp') { event.preventDefault(); return move(-1); }
    if (event.key === 'Enter') {
      event.preventDefault();
      const results = ranked(input.value);
      if (results[active]) run(results[active]);
    }
  });

  const button = document.getElementById('palette-open');
  if (button) button.addEventListener('click', openPalette);
}
