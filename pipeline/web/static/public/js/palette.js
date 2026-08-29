/* The public command palette — one search box for the whole portal (BETA-027).
 *
 * The portal's search surfaces were three separate boxes that each knew one
 * thing: the top-bar council search navigates, the filter bar's provider
 * search filters, and the documents page searches full text. A reader who
 * did not already know which box knows what has no way in. Every comparable
 * evidence platform treats search as the front door; this is that door.
 *
 * Architecturally this is the operator UI's palette (static/js/palette.js)
 * wearing public clothes, because that pattern is already proven in this
 * codebase: a lazily-built dialog, everything navigates by hash change only
 * (the same code path as a pasted link or the back button), the palette owns
 * no state and decides nothing. Two things are new here. The councils and
 * providers lists come from the API payloads app.js already fetches and
 * caches at boot, so opening the palette costs no extra request. And
 * document results arrive live, debounced, from the BETA-022 endpoint —
 * guarded so a slow response for an abandoned query can never paint over
 * the results for the current one.
 *
 * Like the top-bar council search this is a navigator, not a filter: every
 * entry ends in a hash change, so no control here carries a data-filter
 * state key and the filter-bar contract in tests/test_portal_controls.py is
 * untouched.
 */
'use strict';

import { el, fetchJSON } from '/app.js';

/* Destinations only. Titles are pinned against app.js's ROUTE_TITLES by
 * tests/test_portal_palette.py, so a route renamed in the router cannot
 * leave the palette pointing somewhere stale. '/authorities' is included
 * as a destination because the bare route renders its own landing page. */
const PAGES = [
  ['/', 'Overview', 'The campaign view at a glance'],
  ['/documents', 'Document search', 'Full text of committee papers and partnership documents'],
  ['/pay', 'Pay & benchmarks', 'Published pay and labour-market context'],
  ['/contracts', 'Funding & contracts', 'Buyers, providers, notices and values'],
  ['/geography', 'Places', 'Evidence across England on a map'],
  ['/providers', 'Providers', 'Pay, contracts, claims and safety per provider'],
  ['/relationships', 'Relationships', 'Who commissions whom'],
  ['/treatment', 'Treatment data', 'Demand and activity, with their limits'],
  ['/pfd', 'Safety & legal', 'Prevention of future deaths reports'],
  ['/claims', 'Evidence-backed claims', 'Campaign claims with the evidence behind them'],
  ['/authorities', 'Authorities', 'One page per local authority'],
  ['/compare', 'Compare authorities', 'Authorities side by side on shared axes'],
  ['/coverage', 'Coverage & limitations', 'What this portal holds, and what it does not'],
  ['/catalogue', 'Dataset catalogue', 'Every source, its licence, cadence and one key limitation'],
];

const MAX_RESULTS = 24;
const AUTHORITY_LIMIT = 6;
const PROVIDER_LIMIT = 6;
const DOCUMENT_LIMIT = 5;
/* More than the display limit because duplicate pages of one document are
 * deduped on arrival; five unique documents needs a wider raw window. */
const DOCUMENT_FETCH_LIMIT = 12;
/* Shorter queries hit the document index with terms that match a fifth of
 * the corpus; the documents page is the honest surface for those. */
const DOC_MIN_QUERY = 3;
const DOC_DEBOUNCE_MS = 200;

let overlay = null;
let input = null;
let list = null;
let restoreFocusTo = null;

let commands = [];
let active = 0;

/* null = not asked yet; false = asked and unavailable (the group simply
 * never renders, the way the top-bar search degrades when its list fails
 * to load — a palette that dies because one source did not is worse than
 * one that searches slightly less). */
let authorities = null;
let providers = null;

/* The last completed document fetch, with the term it answered. Results
 * only ever render against the term they were fetched for. */
let docResults = { term: '', rows: [] };
let docTimer = null;
let docToken = 0;

// --- matching -----------------------------------------------------------------

/* Contiguous matches beat scattered ones and earlier beats later. Same
 * scoring as the operator palette so the two feel identical to anyone who
 * uses both; subsequence fallback so "nottsshire" still finds Nottinghamshire. */
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
  // Everything navigates by hash: the same code path as a nav link, a pasted
  // URL or the back button. The palette has no other way to act.
  if (location.hash === hash) return;
  location.hash = hash;
}

/* Document type as a reader would write it, with the raw value as the
 * fallback so a new type in the warehouse still says something true. */
const DOC_TYPE_LABELS = {
  COMMITTEE_PAPER: 'Committee paper',
  CDP_DOCUMENT: 'CDP document',
};

/* One palette row of a matched passage: enough to recognise the context,
 * cut at a word boundary so it never ends mid-word. */
function trimSnippet(passage) {
  const text = String(passage ?? '').replace(/\s+/g, ' ').trim();
  if (text.length <= 96) return text;
  const cut = text.slice(0, 96);
  const space = cut.lastIndexOf(' ');
  return `${space > 48 ? cut.slice(0, space) : cut}…`;
}

function buildCommands() {
  const term = input.value.trim();
  const lowered = term.toLowerCase();
  const built = [];

  for (const [route, title, description] of PAGES) {
    built.push({ kind: 'Page', label: title, detail: description,
      run: () => go(route === '/' ? '#/' : `#${route}`) });
  }

  // Councils and providers only when the reader has typed something: on an
  // empty query the pages are the menu, and a wall of 296 councils is not.
  if (lowered && Array.isArray(authorities)) {
    const matches = authorities
      .filter((a) => (a.name || '').toLowerCase().includes(lowered)
        || (a.ons_code || '').toLowerCase().includes(lowered))
      .slice(0, AUTHORITY_LIMIT);
    for (const authority of matches) {
      built.push({ kind: 'Council', label: authority.name || authority.ons_code,
        detail: [authority.region, authority.ons_code].filter(Boolean).join(' · '),
        run: () => go(`#/authorities/${authority.ons_code}`) });
    }
  }

  if (lowered && Array.isArray(providers)) {
    const matches = providers
      .filter((p) => (p.canonical_name || '').toLowerCase().includes(lowered)
        || (p.provider_key || '').includes(lowered))
      .slice(0, PROVIDER_LIMIT);
    for (const provider of matches) {
      built.push({
        kind: 'Provider',
        label: provider.is_target ? `★ ${provider.canonical_name}` : provider.canonical_name,
        detail: [provider.provider_key,
          Number(provider.contract_count) > 0 ? `${provider.contract_count} notices` : null]
          .filter(Boolean).join(' · '),
        run: () => go(`#/providers/${provider.provider_key}`) });
    }
  }

  if (lowered.length >= DOC_MIN_QUERY) {
    // Live results only for the term they were actually fetched for; a slow
    // response for an abandoned query renders nothing. One document can
    // match on several pages, so rows are deduped by document and page —
    // the palette shows five *documents*, not five copies of one.
    if (docResults.term === lowered) {
      const seen = new Set();
      for (const row of docResults.rows) {
        const key = `${row.source_url || row.title}|${row.page_number}`;
        if (seen.has(key)) continue;
        seen.add(key);
        built.push({
          kind: 'Document',
          // The matched passage, not the document's stored title: in this
          // corpus a committee paper's title is usually a content-hash
          // filename, and a row of hashes teaches the reader nothing. The
          // snippet is real text, already windowed onto the match, and it
          // is exactly the reason the row is here at all.
          label: trimSnippet(row.snippet || row.text || row.title),
          detail: [DOC_TYPE_LABELS[row.document_type] || row.document_type,
            row.page_number ? `page ${row.page_number}` : null]
            .filter(Boolean).join(' · '),
          run: () => go(`#/documents?q=${encodeURIComponent(term)}`) });
        if (seen.size >= DOCUMENT_LIMIT) break;
      }
    }
    // Always offered, even while the live results are still in flight: it
    // navigates to the documents page, which is the surface built to answer
    // the query properly — with its own caveat, snippet and result count.
    built.push({ kind: 'Documents', label: `Search document text for “${term}”`,
      detail: 'committee papers and partnership documents',
      run: () => go(`#/documents?q=${encodeURIComponent(term)}`) });
  }

  commands = built;
}

function scheduleDocumentSearch() {
  const term = input.value.trim();
  if (docTimer) { clearTimeout(docTimer); docTimer = null; }
  if (term.length < DOC_MIN_QUERY) {
    docToken += 1;
    docResults = { term: '', rows: [] };
    return;
  }
  const token = ++docToken;
  const lowered = term.toLowerCase();
  docTimer = setTimeout(async () => {
    docTimer = null;
    let payload = null;
    try {
      // fetchJSON caches by URL, so retyping a just-searched term is free.
      payload = await fetchJSON('document_search', { q: term, limit: DOCUMENT_FETCH_LIMIT });
    } catch (error) {
      payload = null;
    }
    if (token !== docToken || !overlay || overlay.hidden) return;
    docResults = { term: lowered, rows: (payload && payload.results) || [] };
    render();
  }, DOC_DEBOUNCE_MS);
}

async function loadLists() {
  // Both lists are fetched by app.js at boot for the top-bar search and the
  // filter bar; these calls normally hit that cache and cost nothing.
  if (authorities === null) {
    authorities = false;
    try {
      authorities = (await fetchJSON('authorities')).authorities || [];
    } catch (error) {
      authorities = false;
    }
    if (overlay && !overlay.hidden) render();
  }
  if (providers === null) {
    providers = false;
    try {
      providers = (await fetchJSON('providers')).providers || [];
    } catch (error) {
      providers = false;
    }
    if (overlay && !overlay.hidden) render();
  }
}

// --- the overlay --------------------------------------------------------------

function build() {
  input = el('input', {
    type: 'search', id: 'palette-input', autocomplete: 'off', spellcheck: 'false',
    placeholder: 'Search pages, councils, providers, documents…',
    'aria-label': 'Search the portal',
    role: 'combobox', 'aria-expanded': 'true', 'aria-controls': 'palette-list',
    'aria-autocomplete': 'list',
    oninput: () => { active = 0; scheduleDocumentSearch(); render(); },
  });

  list = el('div', { class: 'palette-list', id: 'palette-list', role: 'listbox',
    'aria-label': 'Search results' });

  overlay = el('div', {
    class: 'palette-backdrop', hidden: true,
    onmousedown: (event) => { if (event.target === overlay) close(); },
  }, el('div', { class: 'palette', role: 'dialog', 'aria-modal': 'true',
    'aria-label': 'Search SectorTrace' },
    el('div', { class: 'palette-head' },
      el('span', { class: 'search-icon', 'aria-hidden': 'true', text: '⌕' }),
      input,
      el('kbd', { class: 'palette-esc', 'aria-hidden': 'true', text: 'Esc' })),
    list,
    el('div', { class: 'palette-foot', 'aria-hidden': 'true' },
      el('span', {}, el('kbd', { text: '↑' }), el('kbd', { text: '↓' }), ' move'),
      el('span', {}, el('kbd', { text: 'Enter' }), ' open'),
      el('span', {}, el('kbd', { text: 'Esc' }), ' close'))));

  document.body.append(overlay);
}

/* The matched span is marked, not replaced: an option whose label changed
 * shape between query and result is harder to scan, and the portal already
 * has a mark style for exactly this (the document snippets). Built from
 * text nodes like every other warehouse-derived string that reaches the
 * DOM — settled decision 9 applies to palette rows too. */
function markMatch(label, term) {
  const text = String(label ?? '');
  const needle = String(term || '').trim().toLowerCase();
  if (!needle) return [text];
  const at = text.toLowerCase().indexOf(needle);
  if (at < 0) return [text];
  return [text.slice(0, at),
    el('mark', { text: text.slice(at, at + needle.length) }),
    text.slice(at + needle.length)];
}

function render() {
  const term = input.value.trim();
  const results = ranked(term);
  active = Math.max(0, Math.min(active, results.length - 1));

  if (!results.length) {
    list.replaceChildren(el('div', { class: 'palette-empty', role: 'presentation',
      text: 'No quick matches. Try a council name, a provider, or a page.' }));
    input.removeAttribute('aria-activedescendant');
    return;
  }

  list.replaceChildren(...results.map((command, index) => el('div', {
    id: `palette-opt-${index}`,
    class: `palette-item${index === active ? ' active' : ''}`,
    role: 'option', 'aria-selected': String(index === active),
    onmousemove: () => { if (active !== index) { active = index; paintActive(); } },
    onclick: () => run(command),
  },
    el('span', { class: 'palette-kind', text: command.kind }),
    el('span', { class: 'palette-label' }, ...markMatch(command.label, term)),
    command.detail ? el('span', { class: 'palette-detail', text: command.detail }) : null)));

  paintActive();
}

/* Repainting classes and aria state only, not the list: a full rebuild per
 * arrow key loses scroll position and costs a rebuild of nodes for a
 * two-class change. */
function paintActive() {
  [...list.children].forEach((node, index) => {
    node.classList.toggle('active', index === active);
    node.setAttribute('aria-selected', String(index === active));
  });
  const current = list.children[active];
  if (current) {
    input.setAttribute('aria-activedescendant', current.id);
    current.scrollIntoView?.({ block: 'nearest' });
  } else {
    input.removeAttribute('aria-activedescendant');
  }
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
  catch (error) { /* a palette entry must not be able to break the page */ }
}

export function openPalette() {
  if (!overlay) build();
  restoreFocusTo = document.activeElement;
  overlay.hidden = false;
  active = 0;
  docResults = { term: '', rows: [] };
  buildCommands();
  render();
  // Keep what the reader last searched, selected, so one keystroke replaces
  // it and Tab keeps focus here rather than escaping the dialog.
  input.focus();
  input.select();
  loadLists();
}

export function close() {
  if (!overlay || overlay.hidden) return;
  overlay.hidden = true;
  if (docTimer) { clearTimeout(docTimer); docTimer = null; }
  docToken += 1;
  if (restoreFocusTo && restoreFocusTo.isConnected) {
    try { restoreFocusTo.focus(); } catch (error) { /* focus a deleted node */ }
  }
  restoreFocusTo = null;
}

function isTyping(target) {
  return target instanceof Element
    && Boolean(target.closest('input, textarea, select, [contenteditable]'));
}

export function initPalette() {
  const button = document.getElementById('palette-open');

  // The static hint says Ctrl; a Mac reader's modifier is ⌘, and a hint that
  // names a key the machine does not have is a papercut on first contact.
  if (button) {
    const kbd = button.querySelector('kbd');
    if (kbd) kbd.textContent = /Mac|iPhone|iPad/.test(navigator.platform || '') ? '⌘K' : 'Ctrl K';
    button.addEventListener('click', () => {
      if (overlay && !overlay.hidden) close();
      else openPalette();
    });
  }

  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      if (overlay && !overlay.hidden) return close();
      return openPalette();
    }

    // "/" opens search the way it does on every developer-facing site a
    // researcher might already know — but never while something is being
    // typed into, where "/" is input, not a shortcut.
    if (event.key === '/' && (!overlay || overlay.hidden) && !isTyping(event.target)) {
      event.preventDefault();
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
    if (event.key === 'Tab') {
      // The dialog is aria-modal with one tab stop: the input. Tab is kept
      // here rather than escaping into the page behind the overlay, whose
      // focusable controls are now covered and should not be reachable.
      event.preventDefault();
    }
  });
}
