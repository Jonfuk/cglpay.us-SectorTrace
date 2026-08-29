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

/* The facet and scope filters the page carries in the hash beside `q`
 * (BETA-041), so a filtered search is a shareable link. `offset` stays out of
 * the URL — how far a reader has paged is nobody else's business. */
const FILTER_KEYS = ['source_system', 'document_type', 'year_from', 'year_to',
                     'since_retrieved_at'];

function readFilters(params) {
  const source = params || new URLSearchParams(location.hash.split('?')[1] || '');
  const out = {};
  for (const key of FILTER_KEYS) {
    const value = (source.get(key) || '').trim();
    if (value) out[key] = value;
  }
  return out;
}

/* Merge a patch into the hash query, preserving `q` and any filter the patch
 * does not mention. An empty value clears that key. */
function setDocParams(patch) {
  const params = new URLSearchParams(location.hash.split('?')[1] || '');
  for (const [key, value] of Object.entries(patch)) {
    if (value) params.set(key, value); else params.delete(key);
  }
  const query = params.toString();
  location.hash = `#/documents${query ? `?${query}` : ''}`;
}

export async function render(main, { params = null } = {}) {
  const initialQuery = (params ? params.get('q') : '') || '';
  const filters = readFilters(params);
  /* Accumulates across "show more" clicks for this visit to the route. Not URL
   * state: the shareable address is `#/documents?q=…&document_type=…`, and how
   * far a reader has paged is nobody else's business. */
  const session = { query: initialQuery, filters, results: [], total: NaN };

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
      // A new search term resets the facet/scope filters: their available
      // values belong to the previous query's result set.
      location.hash = `#/documents${term ? `?q=${encodeURIComponent(term)}` : ''}`;
    },
  }, input, el('button', { class: 'btn', type: 'submit', text: 'Search' }));

  const readingHolder = el('div', {});
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
    readingHolder,
    resultsHolder);
  replace(main, page);

  // BETA-081: `#/documents?...&doc=<id>&el=<element_id>` opens the reading
  // room above the results. Removing those keys returns to the search, whose
  // query stays in the hash and whose scroll is restored by the router.
  const readingDoc = params ? params.get('doc') : null;
  if (readingDoc) {
    renderReadingRoom(readingHolder, readingDoc,
      (params && params.get('el')) || null, initialQuery);
  }

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

  const requestParams = () => ({
    q: session.query, limit: PAGE_SIZE, ...session.filters,
  });

  let data;
  try {
    data = await fetchJSON('document_search', { ...requestParams(), offset: 0 });
  } catch (error) {
    replace(holder, el('div', { class: 'section' },
      errorCard(error, () => runSearch(holder, session))));
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
        { ...requestParams(), offset: session.results.length });
    } catch (error) {
      // The pages already shown stay on screen; the failure and its retry
      // belong to the slot the button came from.
      moreSlot.replaceChildren(
        errorCard(error, () => refreshMore()));
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
    facetBar(data, session.filters),
    pinnedCaveat(data.caveat, 'Read before citing a result'),
    session.results.length
      ? [countLine, list, moreSlot]
      : noData(`pages matching "${session.query}"`, null)));
}

/* The four filters, driven by the payload's own `facets` block. Changing any
 * of them rewrites the hash (keeping `q` and the others), which re-renders the
 * page from scratch — a filtered search is a link, and paging starts over
 * because the result set changed. The facet <select>s always list every
 * bucket the current query has, each with its size, so a reader can widen
 * again after narrowing. */
function facetBar(data, active) {
  const facets = data.facets || {};
  const label = (key) => ({
    committee_paper_promotion: 'Committee papers',
    cdp_document_promotion: 'Partnership documents',
  }[key] || key);

  const facetSelect = (key, allLabel, rows) => {
    const options = [el('option', { value: '', text: allLabel })];
    for (const row of rows || []) {
      options.push(el('option', {
        value: row.value, selected: active[key] === row.value || undefined,
        text: `${label(row.value)} (${num(row.count)})`,
      }));
    }
    return el('label', { class: 'small muted' }, `${allLabel.replace('All ', '')} `,
      el('select', {
        'aria-label': allLabel,
        onchange: (event) => setDocParams({ [key]: event.target.value }),
      }, options));
  };

  const yearInput = (key, placeholder) => el('input', {
    type: 'number', inputmode: 'numeric', value: active[key] || '',
    placeholder, min: '1990', max: '2100', style: 'width:6rem;',
    'aria-label': placeholder,
    onchange: (event) => setDocParams({ [key]: event.target.value.trim() }),
  });

  const hasFilter = FILTER_KEYS.some((key) => active[key]);

  return el('div', { class: 'panel row wrap', style: 'gap:12px;align-items:center;' },
    facetSelect('source_system', 'All sources', facets.source_system),
    facetSelect('document_type', 'All document types', facets.document_type),
    el('label', { class: 'small muted' }, 'Published ',
      yearInput('year_from', 'from year'), ' ', yearInput('year_to', 'to year')),
    hasFilter
      ? el('button', {
          class: 'btn ghost', type: 'button',
          onclick: () => setDocParams(Object.fromEntries(
            FILTER_KEYS.map((key) => [key, '']))),
        }, 'Clear filters')
      : null);
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

// BETA-062: how the displayed title was arrived at, when it was not the
// source's own label. `source_label` and a missing basis (a row the backfill
// has not reached) get no marker — only a title we derived is flagged, so a
// reader never takes it for verbatim source text.
const TITLE_BASIS_NOTE = {
  pdf_metadata: 'title from PDF metadata',
  heading: 'title from first heading',
  filename: 'title from file name',
  unknown: 'no document title — showing file name',
};

function renderResult(result, query) {
  const label = result.title || `${result.document_type} page ${result.page_number ?? ''}`.trim();
  const basisNote = TITLE_BASIS_NOTE[result.title_basis];
  // The snippet arrives centred on the match; against an older cached API
  // response without one, fall back to the head of the page rather than
  // rendering nothing at all.
  const passage = result.snippet ?? truncate(result.text || '', 320);
  const strong = el('strong', { text: label });
  if (basisNote && result.source_title && result.source_title !== label) {
    strong.setAttribute('title', `source title: ${result.source_title}`);
  }
  return el('article', { class: 'claim' },
    el('div', { class: 'row wrap', style: 'justify-content:space-between;align-items:baseline;gap:8px;' },
      strong,
      el('span', { class: 'small muted',
        text: [result.document_type, result.page_number ? `page ${result.page_number}` : null,
               basisNote]
          .filter(Boolean).join(' · ') })),
    highlightedSnippet(passage, query),
    contextExpander(result, query),
    el('div', { class: 'row wrap', style: 'gap:8px;', },
      result.document_id && result.document_element_id
        ? el('button', {
            class: 'btn tiny', type: 'button',
            onclick: () => setDocParams({
              doc: result.document_id, el: result.document_element_id,
            }),
          }, 'Open in reading room')
        : null,
      result.source_url ? sourceLink(result.source_url, 'Read the source page') : null,
      el('span', { class: 'small muted',
        text: [result.published_at ? `published ${isoDate(result.published_at)}` : null,
               result.retrieved_at ? `retrieved ${isoDate(result.retrieved_at)}` : null]
          .filter(Boolean).join(' · ') })));
}

/* BETA-081: the reading room. A split view over one document: metadata and
 * provenance on the left, the matched passage with its surrounding elements
 * on the right, "earlier / later" that re-anchors on an edge element (each
 * response stays a bounded window — this is not the whole document), a
 * stable passage link, and a back link that keeps the search behind it. */
async function renderReadingRoom(holder, docId, elId, query) {
  replace(holder, el('div', { class: 'section reading-room' },
    el('div', { class: 'panel' }, el('div', { class: 'shimmer' }))));

  const load = async (anchorId) => {
    let data;
    try {
      data = await fetchJSON(`documents/${encodeURIComponent(docId)}`,
        { element_id: anchorId || undefined, context: 8 });
    } catch (error) {
      replace(holder, el('div', { class: 'section reading-room' },
        errorCard(error, () => renderReadingRoom(holder, docId, elId, query))));
      return;
    }
    paint(data);
  };

  const paint = (data) => {
    const passageLink = () => {
      const p = new URLSearchParams(location.hash.split('?')[1] || '');
      p.set('doc', docId);
      if (data.anchor_element_id) p.set('el', data.anchor_element_id);
      return `${location.origin}/#/documents?${p.toString()}`;
    };

    const meta = el('div', { class: 'reading-meta panel' },
      el('h3', { text: data.title || docId }),
      el('dl', {},
        el('dt', { text: 'Type' }), el('dd', { text: data.document_type || '—' }),
        el('dt', { text: 'Source' }), el('dd', { text: data.source_system || '—' }),
        el('dt', { text: 'Published' }), el('dd', { text: isoDate(data.published_at) }),
        el('dt', { text: 'Retrieved' }), el('dd', { text: isoDate(data.retrieved_at) }),
        el('dt', { text: 'Parser' }),
        el('dd', { text: `${data.parser?.name || '—'} ${data.parser?.version || ''}`.trim() }),
        el('dt', { text: 'Elements' }), el('dd', { text: num(data.element_count) })),
      data.source_url
        ? el('p', {}, sourceLink(data.source_url, 'Open the source document ↗'))
        : null,
      el('button', {
        class: 'btn tiny', type: 'button',
        onclick: (e) => {
          const link = passageLink();
          if (navigator.clipboard) navigator.clipboard.writeText(link);
          e.target.textContent = 'Link copied';
          setTimeout(() => { e.target.textContent = 'Copy passage link'; }, 1500);
        },
      }, 'Copy passage link'),
      el('button', {
        class: 'btn ghost tiny', type: 'button',
        onclick: () => setDocParams({ doc: '', el: '' }),
      }, '← Back to results'),
      pinnedCaveat(data.caveat, 'Read this with the passage'));

    const elements = data.elements || [];
    const body = el('div', { class: 'reading-body panel' },
      el('div', { class: 'reading-nav' },
        el('button', {
          class: 'btn tiny', type: 'button', disabled: !data.has_more_before,
          onclick: () => load(elements[0]?.document_element_id),
        }, '↑ Earlier'),
        el('span', { class: 'small muted',
          text: elements[0]?.page_number != null ? `page ${elements[0].page_number}` : '' }),
        el('button', {
          class: 'btn tiny', type: 'button', disabled: !data.has_more_after,
          onclick: () => load(elements[elements.length - 1]?.document_element_id),
        }, 'Later ↓')),
      ...elements.map((element) => {
        const node = element.is_anchor
          ? highlightedSnippet(element.text || '', query)
          : el('p', { class: 'small muted', text: element.text || '' });
        if (element.is_anchor) node.classList.add('reading-anchor');
        node.id = `el-${element.document_element_id}`;
        return node;
      }));

    replace(holder, el('div', { class: 'section reading-room' },
      el('h2', { text: 'Reading room' }),
      el('div', { class: 'reading-split' }, meta, body)));
    holder.querySelector('.reading-anchor')?.scrollIntoView({ block: 'center' });
  };

  await load(elId);
}

/* BETA-042: a lazily-loaded window of the surrounding elements, from
 * /api/v1/documents/{id}. Bounded server-side to a few elements either side —
 * enough to read a hit in context, not enough to reassemble the document. */
function contextExpander(result, query) {
  if (!result.document_id || !result.document_element_id) return null;
  const body = el('div', { class: 'doc-context' });
  let loaded = false;
  const details = el('details', { class: 'doc-context-toggle' },
    el('summary', { class: 'small', text: 'Show surrounding text' }),
    body);
  details.addEventListener('toggle', async () => {
    if (!details.open || loaded) return;
    loaded = true;
    body.replaceChildren(el('div', { class: 'shimmer' }));
    let data;
    try {
      data = await fetchJSON(`documents/${encodeURIComponent(result.document_id)}`,
        { element_id: result.document_element_id, context: 3 });
    } catch (error) {
      loaded = false;
      body.replaceChildren(errorCard(error, () => {
        details.open = false;
      }));
      return;
    }
    const parts = [];
    if (data.has_more_before) {
      parts.push(el('p', { class: 'small muted', text: '…earlier text on this page' }));
    }
    for (const element of data.elements || []) {
      parts.push(element.is_anchor
        ? highlightedSnippet(element.text || '', query)
        : el('p', { class: 'small muted', text: element.text || '' }));
    }
    if (data.has_more_after) {
      parts.push(el('p', { class: 'small muted', text: 'later text on this page…' }));
    }
    body.replaceChildren(...parts);
  });
  return details;
}
