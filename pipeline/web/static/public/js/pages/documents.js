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

export async function render(main, { params = null } = {}) {
  const initialQuery = (params ? params.get('q') : '') || '';

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

  await runSearch(resultsHolder, initialQuery);
  return () => {};
}

async function runSearch(holder, query) {
  replace(holder, el('div', { class: 'section' },
    el('div', { class: 'panel' }, el('div', { class: 'shimmer' }))));

  let data;
  try {
    data = await fetchJSON('document_search', { q: query, limit: 50 });
  } catch (error) {
    replace(holder, el('div', { class: 'section' },
      errorCard(error.message, () => runSearch(holder, query))));
    return;
  }

  const results = data.results || [];
  const total = Number(data.total);
  const truncated = Number.isFinite(total) && total > results.length;
  replace(holder, section(
    `Results for "${query}"`,
    null,
    pinnedCaveat(data.caveat, 'Read before citing a result'),
    results.length
      ? [
          // The count is said out loud for the same reason tableCard's row
          // count is: a list that simply stops looks complete, and a reader
          // who cites "nothing found" from page one of three pages of
          // matches has been failed by the page, not by the warehouse.
          el('p', {
            class: 'small muted',
            text: truncated
              ? `Showing ${num(results.length)} of ${num(total)} matching `
                + 'pages — narrow the search to reach the rest.'
              : `${num(results.length)} matching `
                + `page${results.length === 1 ? '' : 's'}.`,
          }),
          el('div', { class: 'doc-results' },
            results.map((result) => renderResult(result, query))),
        ]
      : noData(`pages matching "${query}"`, null)));
}

function escapeRegExp(text) {
  return String(text).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/* Marks each query term inside the snippet. Built as element and text nodes,
 * not an HTML string — this text was extracted from council PDFs and reaches
 * the DOM as a text node like every other warehouse value (settled decision
 * 9), so an innerHTML shortcut here would be exactly the hole that rule
 * closes. Falls back to plain text when no term can be parsed (symbol-only
 * input). */
function highlightedSnippet(passage, query) {
  const holder = el('p', { class: 'small doc-snippet' });
  const value = String(passage ?? '');
  const tokens = [...new Set(
    (String(query || '').toLowerCase().match(/[a-z0-9][a-z0-9']*/g) || [])
      .filter((token) => token.length >= 2))];
  if (!tokens.length) {
    holder.textContent = value;
    return holder;
  }
  const pattern = new RegExp(`(${tokens.map(escapeRegExp).join('|')})`, 'gi');
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
