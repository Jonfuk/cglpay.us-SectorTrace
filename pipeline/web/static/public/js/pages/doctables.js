/* Document table extraction viewer (BETA-099).
 *
 * Tables detected in a parsed document — the grid the parser produced, its
 * page context, its extraction status, and a CSV of exactly those cells. No
 * cell is re-detected; the source document is the authority for anything the
 * parse got wrong.
 *
 * State is the query: `#/doctables?doc=<document_id>` or `&table=<table_id>`.
 */
'use strict';

import { el, replace, fetchJSON, isoDate, sourceLink, num } from '/app.js';
import { section, pinnedCaveat, noData, errorCard } from '/js/components.js';

const STATUS_BADGE = { structured: 'ok', markdown_only: 'unverified', empty: 'muted' };

function readQuery(params) {
  const q = params || new URLSearchParams(location.hash.split('?')[1] || '');
  return { doc: q.get('doc') || '', table: q.get('table') || '' };
}

function toCSV(grid) {
  return grid.map((row) => row.map((c) => {
    const s = String(c ?? '');
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  }).join(',')).join('\r\n');
}

function download(name, text, type) {
  try {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = el('a', { href: url, download: name });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) { /* the browser blocked it */ }
}

function gridTable(grid) {
  if (!grid.length) return el('p', { class: 'small muted', text: 'No structured grid was extracted for this table.' });
  const [head, ...body] = grid;
  return el('div', { class: 'dt-scroll' }, el('table', { class: 'dt-grid' },
    el('thead', {}, el('tr', {}, ...head.map((c) => el('th', { text: c })))),
    el('tbody', {}, ...body.map((r) => el('tr', {}, ...r.map((c) => el('td', { text: c })))))));
}

async function renderDetail(main, params, tableId, backHref) {
  let data;
  try { data = await fetchJSON('document_tables', { table_id: tableId }); }
  catch (error) {
    replace(main, el('div', { class: 'section' }, errorCard(error, () => renderDetail(main, params, tableId, backHref))));
    return;
  }
  const page = el('div', {},
    el('div', { class: 'hero' },
      el('p', {}, el('a', { href: backHref, text: '← All tables in this document' })),
      el('h1', { text: `Table on page ${data.page_number ?? '—'}` }),
      data.caption ? el('p', { class: 'lede', text: data.caption }) : null,
      el('p', { class: 'small muted' },
        el('span', { class: `badge ${STATUS_BADGE[data.extraction_status] || 'muted'}`, text: data.extraction_status }),
        el('span', { text: ` ${num(data.row_count)} × ${num(data.column_count)} · ` }),
        el('a', { href: data.reading_room_link, text: 'open in the reading room' }))),
    el('div', { class: 'panel' },
      el('div', { class: 'dt-actions' },
        el('button', { class: 'btn', type: 'button',
          onclick: () => download(`${data.document_table_id}.csv`, toCSV(data.grid), 'text/csv') },
          'Download CSV'),
        data.document.source_url ? sourceLink(data.document.source_url, 'the source document ↗') : null),
      gridTable(data.grid),
      data.markdown ? el('details', { class: 'dt-md' },
        el('summary', { text: 'Parser markdown' }),
        el('pre', { class: 'small', text: data.markdown })) : null,
      pinnedCaveat(data.note, 'Read this with the grid')),
    data.context.length ? el('div', { class: 'panel' },
      section('Around this table', null,
        el('ul', { class: 'small' }, ...data.context.map((c) => el('li', {},
          el('span', { class: 'muted', text: `${c.element_type || 'text'}: ` }), c.text))))) : null);
  replace(main, page);
}

export async function render(main, { params = null } = {}) {
  const cur = readQuery(params);

  const docInput = el('input', { value: cur.doc, class: 'dt-input',
    placeholder: 'document_id', 'aria-label': 'document id' });
  const controls = el('div', { class: 'panel dt-controls' }, docInput,
    el('button', { class: 'btn primary', type: 'button',
      onclick: () => { location.hash = docInput.value.trim() ? `#/doctables?doc=${encodeURIComponent(docInput.value.trim())}` : '#/doctables'; } },
      'Show tables'));

  if (cur.table && cur.doc) {
    await renderDetail(main, params, cur.table, `#/doctables?doc=${encodeURIComponent(cur.doc)}`);
    return () => {};
  }

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Document tables' }),
      el('p', { class: 'lede', text:
        'Tables detected in a parsed document, shown as the grid the parser '
        + 'produced. No cell is re-detected — the source document is the '
        + 'authority for anything the parse got wrong.' })),
    controls);

  if (!cur.doc) {
    page.append(el('div', { class: 'panel' },
      pinnedCaveat('Give a document_id (from document search).', 'How to use this')));
    replace(main, page);
    return () => {};
  }

  let data;
  try { data = await fetchJSON('document_tables', { document_id: cur.doc }); }
  catch (error) {
    page.append(el('div', { class: 'section' }, errorCard(error, () => render(main, { params }))));
    replace(main, page);
    return () => {};
  }

  const byStatus = data.counts.by_status || {};
  page.append(el('div', { class: 'panel' },
    el('h2', { text: data.document.title || data.document.document_id }),
    el('p', { class: 'small muted' },
      data.document.source_url ? sourceLink(data.document.source_url, 'source ↗') : null,
      el('span', { text: ` retrieved ${isoDate(data.document.retrieved_at)} · `
        + data.statuses.filter((s) => byStatus[s]).map((s) => `${byStatus[s]} ${s}`).join(' · ') })),
    pinnedCaveat(data.note, 'How these were extracted'),
    data.tables.length
      ? el('ul', { class: 'dt-list' }, ...data.tables.map((t) => el('li', { class: 'dt-item' },
          el('a', { href: `#/doctables?doc=${encodeURIComponent(cur.doc)}&table=${encodeURIComponent(t.document_table_id)}`,
            text: `Page ${t.page_number ?? '—'} · ${num(t.row_count)} × ${num(t.column_count)}` }),
          el('span', { class: `badge ${STATUS_BADGE[t.extraction_status] || 'muted'}`, text: t.extraction_status }),
          t.preview.length ? el('div', { class: 'dt-preview small muted',
            text: t.preview.map((r) => r.join(' | ')).join('  //  ').slice(0, 160) }) : null)))
      : noData('a table in this document')));

  replace(main, page);
  return () => {};
}
