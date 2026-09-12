/* Dataset catalogue (BETA-043) — what this portal collects, and its limits.
 *
 * Every collecting module has exactly one entry (pinned server-side by
 * tests/test_web_catalogue.py). The static description — title, publisher,
 * official URL, evidence layer, geography, cadence, licence, caveat — comes
 * from pipeline/web/datasets.py; the row counts and last-retrieved dates are
 * measured against the warehouse on each request, so a dataset showing zero
 * rows has not been collected here rather than being empty at source.
 *
 * The URL is the view: `#/catalogue` is the list, `#/catalogue?dataset=<id>`
 * is one entry's detail — the same "the query is the whole page" convention
 * compare.js and documents.js use for their own state.
 */
'use strict';

import { el, replace, fetchJSON, isoDate, sourceLink } from '/app.js';
import { section, pinnedCaveat, errorCard } from '/js/components.js';

function setDataset(id) {
  location.hash = id ? `#/catalogue?dataset=${encodeURIComponent(id)}` : '#/catalogue';
}

function freshnessLine(entry) {
  const bits = [];
  bits.push(entry.row_count === 0
    ? 'Not collected here yet'
    : `${entry.row_count.toLocaleString('en-GB')} rows`);
  if (entry.last_retrieved_at) {
    bits.push(`last retrieved ${isoDate(entry.last_retrieved_at)}`);
  }
  return bits.join(' · ');
}

function licenceLine(licence) {
  if (!licence) return null;
  return licence.url
    ? el('span', { class: 'small muted' }, 'Licence: ',
        sourceLink(licence.url, licence.name))
    : el('span', { class: 'small muted', text: `Licence: ${licence.name}` });
}

function datasetCard(entry) {
  return el('article', { class: 'claim' },
    el('div', { class: 'row wrap', style: 'justify-content:space-between;align-items:baseline;gap:8px;' },
      el('strong', { text: entry.title }),
      el('span', { class: 'small muted', text: entry.evidence_layer_label })),
    el('p', { class: 'small', text: entry.caveat }),
    el('dl', { class: 'kv small' },
      el('dt', { text: 'Publisher' }), el('dd', { text: entry.publisher }),
      el('dt', { text: 'Geography' }), el('dd', { text: entry.geography }),
      el('dt', { text: 'Update cadence' }), el('dd', { text: entry.cadence }),
      el('dt', { text: 'Holdings' }), el('dd', { text: freshnessLine(entry) })),
    el('div', { class: 'row wrap', style: 'gap:12px;align-items:baseline;' },
      entry.official_url ? sourceLink(entry.official_url, 'Official source') : null,
      licenceLine(entry.licence),
      el('button', {
        class: 'btn ghost', type: 'button',
        onclick: () => setDataset(entry.dataset_id),
      }, 'Details')));
}

async function renderList(main) {
  replace(main, el('div', {}, el('div', { class: 'section' },
    el('div', { class: 'panel' }, el('div', { class: 'shimmer' })))));

  let data;
  try {
    data = await fetchJSON('catalogue');
  } catch (error) {
    replace(main, el('div', { class: 'section' },
      errorCard(error, () => renderList(main))));
    return () => {};
  }

  const datasets = data.datasets || [];
  const layers = data.evidence_layers || {};
  // Group by evidence layer, in the order the layer vocabulary declares them,
  // so the "never combined across layers" boundary is visible in the layout.
  const groups = [];
  for (const [key, label] of Object.entries(layers)) {
    const members = datasets.filter((d) => d.evidence_layer === key);
    if (members.length) groups.push([label, members]);
  }

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Dataset catalogue' }),
      el('p', { class: 'lede' },
        `${data.count} sources, grouped by evidence layer. Each row names its `
        + 'official publisher, licence, update cadence and the single '
        + 'limitation that matters most before you quote it.')),
    el('details', { class: 'read-first' },
      el('summary', { text: 'How to read this catalogue' }),
      el('p', { text: data.caveat })));

  for (const [label, members] of groups) {
    page.append(section(label, null,
      ...members.map((entry) => datasetCard(entry))));
  }
  replace(main, page);
  return () => {};
}

function tablesTable(tables) {
  return el('table', { class: 'params' },
    el('thead', {}, el('tr', {},
      el('th', { text: 'Warehouse table' }),
      el('th', { text: 'Rows' }),
      el('th', { text: 'Last retrieved' }))),
    el('tbody', {},
      ...tables.map((t) => el('tr', {},
        el('td', {}, el('code', { text: t.name })),
        el('td', { text: (t.rows ?? 0).toLocaleString('en-GB') }),
        el('td', { text: t.last_retrieved_at ? isoDate(t.last_retrieved_at) : '—' })))));
}

async function renderDetail(main, id) {
  replace(main, el('div', {}, el('div', { class: 'section' },
    el('div', { class: 'panel' }, el('div', { class: 'shimmer' })))));

  let entry;
  try {
    entry = await fetchJSON(`catalogue/${encodeURIComponent(id)}`);
  } catch (error) {
    replace(main, el('div', { class: 'section' },
      el('div', { class: 'panel' },
        el('button', { class: 'btn ghost', type: 'button',
          onclick: () => setDataset(null) }, '← All datasets')),
      errorCard(error, () => renderDetail(main, id))));
    return () => {};
  }

  const page = el('div', {},
    el('div', { class: 'panel' },
      el('button', { class: 'btn ghost', type: 'button',
        onclick: () => setDataset(null) }, '← All datasets')),
    el('div', { class: 'hero' },
      el('h1', { text: entry.title }),
      el('p', { class: 'lede', text: entry.evidence_layer_label })),
    section('Before you quote it', null,
      pinnedCaveat(entry.caveat, 'The limitation that matters most'),
      entry.licence_caution
        ? pinnedCaveat(entry.licence_caution, 'Licence caution')
        : null),
    section('Source', null,
      el('dl', { class: 'kv small' },
        el('dt', { text: 'Publisher' }), el('dd', { text: entry.publisher }),
        el('dt', { text: 'Official URL' }),
        el('dd', {}, entry.official_url
          ? sourceLink(entry.official_url, entry.official_url) : '—'),
        el('dt', { text: 'Geography' }), el('dd', { text: entry.geography }),
        el('dt', { text: 'Update cadence' }), el('dd', { text: entry.cadence }),
        el('dt', { text: 'Collecting module' }),
        el('dd', {}, el('code', { text: entry.module })),
        el('dt', { text: 'Licence' }),
        el('dd', { text: entry.licence_statement || (entry.licence && entry.licence.name) || '—' }))),
    section('Holdings in this warehouse', null,
      el('p', { class: 'small muted', text: freshnessLine(entry) }),
      tablesTable(entry.tables || [])));

  replace(main, page);
  return () => {};
}

export async function render(main, { params = null } = {}) {
  const id = params ? (params.get('dataset') || '').trim() : '';
  return id ? renderDetail(main, id) : renderList(main);
}
