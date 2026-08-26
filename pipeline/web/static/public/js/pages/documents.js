/* Document search — full-text search over the two document types the
 * document-analysis pipeline (docs/document-analysis.md) has parsed so far:
 * committee papers and community drug partnership documents.
 *
 * Deliberately narrow. This is not "search the warehouse" — every structured
 * table already has its own filtered page, and PFD reports, tribunal
 * judgments and anything else with a restricted_ personal-data counterpart
 * are not reachable here regardless of whether a future session ever parses
 * their text: `pipeline/web/public_queries.py`'s `document_search()` reads
 * from an explicit source-system allowlist, not "everything in
 * document_records", and that boundary is enforced server-side, not by this
 * page choosing not to ask.
 *
 * The URL is the search: `#/documents?q=...`, the same "the query is the
 * whole page" convention `compare.js` established for its own state.
 */
'use strict';

import { el, replace, fetchJSON, isoDate, sourceLink, num } from '/app.js';
import { section, pinnedCaveat, noData, errorCard, truncate,
         shareButton } from '/js/components.js';

/* Matches the server's own ceiling for one response; larger result sets are
 * reached through "show more", which asks for the next window by offset. */
const PAGE_SIZE = 50;

export async function render(main, { params = null } = {}) {
  const initialQuery = (params ? params.get('q') : '') || '';
  /* Accumulates across "show more" clicks for this visit to the route. It is
   * deliberately not URL state: the shareable address is `#/documents?q=…`,
   * and how far a reader has paged through their results is nobody else's
   * business — unlike compare.js's selection, which *is* the whole finding. */
  const session = { query: initialQuery, results: [], total: NaN };

  const input = el('input', {
    type: 'search', name: 'q', value: initialQuery,
    placeholder: 'Search committee papers and CDP documents',
    'aria-label': 'Search document text', autocomplete: 'off',
  });
  const resultsHolder = el('div', {});

  const form = el('form', {
    class: 'row wrap', style: 'gap:8px;align-items:center;',
    onsubmit: (event) => {
      event.preventDefault();
      const term = input.value.trim();
      location.hash = `#/documents${term ? `?q=${encodeURIComponent(term)}` : ''}`;
    },
  }, input, el('button', { class: 'btn', type: 'submit', text: 'Search' }));

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Document search' }),
      el('p', { class: 'lede' },
        'Search the text of published committee papers and community drug '
        + 'partnership documents. Not a search of the whole warehouse — '
        + 'every structured evidence table has its own page.'),
      el('div', { class: 'hero-actions' },
        shareButton({
          title: 'SectorTrace document search',
          text: initialQuery
            ? `SectorTrace document search: "${initialQuery}"`
            : 'Search SectorTrace’s published committee and partnership documents.',
          label: 'Share this search',
        }))),
    el('details', { class: 'read-first' },
      el('summary', { text: 'What this searches, and what it does not' }),
      el('p', { text: 'A result is a page that contains the term, not a finding. Read the source page, and its own caveats, before citing anything found here. Only two document types are searchable today: council committee papers and community drug partnership documents. PFD reports, tribunal judgments and every structured table have their own pages and are not included here.' })),
    el('div', { class: 'panel' }, form),
    resultsHolder);
  replace(main, page);

  if (!initialQuery) {
    replace(resultsHolder, el('div', { class: 'section' },
      el('div', { class: 'panel' },
        el('p', { text: 'Enter a search term above to see matching pages.' }))));
    return () => {};
  }

  await runSearch(resultsHolder, session);
  return () => {};
}

async function runSearch(holder, session) {
  replace(holder, el('div', { class: 'section' },
    el('div', { class: 'panel' }, el('div', { class: 'shimmer' }))));

  let data;
  try {
    data = await fetchJSON('document_search',
      { q: session.query, limit: PAGE_SIZE, offset: 0 });
  } catch (error) {
    replace(holder, el('div', { class: 'section' },
      errorCard(error.message, () => runSearch(holder, session))));
    return;
  }

  session.results = data.results || [];
  session.total = Number(data.total);

  const hasMore = () =>
    Number.isFinite(session.total) && session.total > session.results.length;

  const countLine = el('p', { class: 'small muted' });
  const list = el('div', { class: 'doc-results' });
  const moreSlot = el('div', {});

  const refreshCount = () => {
    // The count is said out loud for the same reason tableCard's row count
    // is: a list that simply stops looks complete, and a reader who cites
    // "nothing found" from page one of thousands of matches has been failed
    // by the page, not by the warehouse.
    const shown = session.results.length;
    countLine.textContent = hasMore()
      ? `Showing ${num(shown)} of ${num(session.total)} matching pages.`
      : `${num(shown)} matching page${shown === 1 ? '' : 's'}.`;
  };

  const refreshMore = () => {
    moreSlot.replaceChildren();
    if (!hasMore()) return;
    const remaining = Math.min(PAGE_SIZE, session.total - session.results.length);
    moreSlot.append(el('button', {
      class: 'btn ghost', type: 'button',
      onclick: () => loadMore(),
    }, `Show ${num(remaining)} more`));
  };

  const loadMore = async () => {
    // The slot is replaced wholesale while the request runs so no second
    // click can queue a duplicate window.
    moreSlot.replaceChildren(el('span', { class: 'small muted', text: 'Loading…' }));
    let page;
    try {
      page = await fetchJSON('document_search',
        { q: session.query, limit: PAGE_SIZE, offset: session.results.length });
    } catch (error) {
      // The pages already shown stay on screen; the failure and its retry
      // belong to the slot the button came from.
      moreSlot.replaceChildren(
        errorCard(error.message, () => refreshMore()));
      return;
    }
    const rows = page.results || [];
    session.results = session.results.concat(rows);
    for (const result of rows) list.append(renderResult(result, session.query));
    refreshCount();
    refreshMore();
  };

  for (const result of session.results) {
    list.append(renderResult(result, session.query));
  }
  refreshCount();
  refreshMore();

  replace(holder, section(
    `Results for "${session.query}"`,
    null,
    pinnedCaveat(data.caveat, 'Read before citing a result'),
    session.results.length
      ? [countLine, list, moreSlot]
      : noData(`pages matching "${session.query}"`, null)));
}

function escapeRegExp(text) {
  return String(text).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/* Marks each query term inside the snippet, quoted phrases first: the server
 * reads "rough sleeping" as a required phrase, so where the phrase occurs
 * contiguously it is marked as one unit rather than as two words that happen
 * to be near each other. Built as element and text nodes, not an HTML string
 * — this text was extracted from council PDFs and reaches the DOM as a text
 * node like every other warehouse value (settled decision 9), so an
 * innerHTML shortcut here would be exactly the hole that rule closes. Falls
 * back to plain text when no term can be parsed (symbol-only input). */
function highlightedSnippet(passage, query) {
  const holder = el('p', { class: 'small doc-snippet' });
  const value = String(passage ?? '');
  const raw = String(query || '');
  // Mirrors _search_terms() in public_queries.py; keep the two in step.
  const phrases = [...new Set((raw.match(/"[^"]+"/g) || [])
    .map((span) => span.slice(1, -1).trim().toLowerCase())
    .filter((token) => token.length >= 2))];
  const words = [...new Set(
    (raw.toLowerCase().match(/[a-z0-9][a-z0-9']*/g) || [])
      .filter((token) => token.length >= 2))];
  const terms = [...new Set([...phrases, ...words])];
  if (!terms.length) {
    holder.textContent = value;
    return holder;
  }
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join('|')})`, 'gi');
  let last = 0;
  for (let match = pattern.exec(value); match; match = pattern.exec(value)) {
    if (match.index > last) holder.append(value.slice(last, match.index));
    holder.append(el('mark', { text: match[0] }));
    last = match.index + match[0].length;
  }
  if (last < value.length) holder.append(value.slice(last));
  return holder;
}

function renderResult(result, query) {
  const label = result.title || `${result.document_type} page ${result.page_number ?? ''}`.trim();
  // The snippet arrives centred on the match; against an older cached API
  // response without one, fall back to the head of the page rather than
  // rendering nothing at all.
  const passage = result.snippet ?? truncate(result.text || '', 320);
  return el('article', { class: 'claim' },
    el('div', { class: 'row wrap', style: 'justify-content:space-between;align-items:baseline;gap:8px;' },
      el('strong', { text: label }),
      el('span', { class: 'small muted',
        text: [result.document_type, result.page_number ? `page ${result.page_number}` : null]
          .filter(Boolean).join(' · ') })),
    highlightedSnippet(passage, query),
    el('div', { class: 'row wrap', style: 'gap:8px;', },
      result.source_url ? sourceLink(result.source_url, 'Read the source page') : null,
      el('span', { class: 'small muted',
        text: [result.published_at ? `published ${isoDate(result.published_at)}` : null,
               result.retrieved_at ? `retrieved ${isoDate(result.retrieved_at)}` : null]
          .filter(Boolean).join(' · ') })));
}
