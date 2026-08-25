/* Relationships — a one-hop commissioning neighbourhood in the evidence
 * graph (docs/evidence-graph.md, migration 0050).
 *
 * Deliberately one entity at a time, not a map of the whole corpus: the
 * reader picks who to look at, the same "the reader picks the peers" shape
 * the compare page (W-11) already established. A diagram of every
 * relationship at once would invite a size/importance/centrality reading
 * this pipeline never asserts — a line here means exactly one thing, "a
 * contract notice named this authority as buyer and this provider as
 * supplier", and nothing about how many lines an entity has says anything
 * about its scale.
 *
 * The graph diagram is illustrative; the table beneath it is the citable
 * record, because a force-directed layout has no accessible text
 * equivalent and "everything is citable" applies here exactly as it does
 * everywhere else in the portal.
 */
'use strict';

import { el, replace, fetchJSON } from '/app.js';
import { section, pinnedCaveat, noData, errorCard, mountChart, disposeCharts,
          provenance, shareButton } from '/js/components.js';

export async function render(main, { params = null } = {}) {
  const charts = [];
  const onsCode = params?.get('ons_code') || null;
  const providerKey = params?.get('provider_key') || null;

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Who commissions whom' }),
      el('p', { class: 'lede', text: 'Pick a council or a provider and see '
        + 'who it has a matched contract award with — one relationship at '
        + 'a time, never a map of the whole sector.' }),
      el('div', { class: 'hero-actions' },
        shareButton({
          title: 'SectorTrace relationships',
          text: 'See who a council or provider has commissioning relationships with.',
          label: 'Share this view',
        }))),
    el('details', { class: 'read-first' },
      el('summary', { text: 'What this shows, and what it does not' }),
      el('p', { text: 'A line means a contract notice named this authority '
        + 'as buyer and this provider as supplier — a commissioning '
        + 'relationship, not a measure of size, value, importance or '
        + 'reliance. Coverage is the same floor as the contracts page: '
        + 'only notices with an exact supplier-name match are here. This '
        + 'is one relationship type from the evidence graph, not the '
        + 'whole of it — ownership and corporate-group relationships are '
        + 'a separate, not-yet-published view.' })),
    el('div', { id: 'rel-picker' }),
    el('div', { id: 'rel-caveat' }),
    el('div', { id: 'rel-content' }));
  replace(main, page);

  const pickerHolder = page.querySelector('#rel-picker');
  const caveatHolder = page.querySelector('#rel-caveat');
  const contentHolder = page.querySelector('#rel-content');

  await renderPicker(pickerHolder, onsCode, providerKey);

  if (!onsCode && !providerKey) {
    replace(contentHolder, el('div', { class: 'section' },
      el('div', { class: 'panel' },
        el('p', { text: 'Pick an authority or provider above to see its '
          + 'commissioning relationships.' }))));
    return () => disposeCharts(charts);
  }

  let data;
  try {
    data = await fetchJSON('relationships',
      onsCode ? { ons_code: onsCode } : { provider_key: providerKey });
  } catch (error) {
    replace(contentHolder, errorCard(error.message, () => render(main, { params })));
    return () => disposeCharts(charts);
  }

  if (data.caveat) {
    replace(caveatHolder, pinnedCaveat(data.caveat, 'Read this with the diagram'));
  }

  renderRelationships(contentHolder, data, charts);

  return () => disposeCharts(charts);
}

/* A single picker, not compare's multi-select chips: relationships centres
 * on one entity, so choosing a second replaces the first rather than
 * adding to it. The URL is still the whole state, shareable exactly as
 * compare's is. */
async function renderPicker(holder, onsCode, providerKey) {
  let authorities = [];
  let providers = [];
  try {
    authorities = (await fetchJSON('authorities')).authorities || [];
    providers = (await fetchJSON('providers')).providers || [];
  } catch (e) { /* the pickers fall back to empty lists */ }

  const currentName = onsCode
    ? authorities.find((a) => a.ons_code === onsCode)?.name
    : providerKey
      ? providers.find((p) => p.provider_key === providerKey)?.canonical_name
      : null;

  replace(holder, section('Choose an authority or provider',
    currentName ? `Showing: ${currentName}` : 'Nothing selected yet.',
    el('div', { class: 'panel' },
      currentName ? el('div', { class: 'section-links' },
        el('button', {
          type: 'button', text: 'Clear selection',
          onclick: () => { location.hash = '#/relationships'; },
        })) : null,
      el('div', { class: 'compare-pickers' },
        entityPicker({
          placeholder: 'Find an authority', ariaLabel: 'Find an authority',
          items: authorities, keys: ['name', 'ons_code'],
          label: (a) => `${a.name} · ${a.ons_code}`,
          pick: (a) => { location.hash = `#/relationships?ons_code=${encodeURIComponent(a.ons_code)}`; },
        }),
        entityPicker({
          placeholder: 'Find a provider', ariaLabel: 'Find a provider',
          items: providers, keys: ['canonical_name', 'provider_key'],
          label: (p) => p.canonical_name,
          pick: (p) => { location.hash = `#/relationships?provider_key=${encodeURIComponent(p.provider_key)}`; },
        })))));
}

/* The typeahead pattern from the compare page, itself from the treatment
 * page — generalised here to one picker function for either entity kind,
 * since this page never needs two different selection behaviours at once. */
function entityPicker({ placeholder, ariaLabel, items, keys, label, pick }) {
  const input = el('input', { type: 'search', placeholder, 'aria-label': ariaLabel,
    autocomplete: 'off' });
  const list = el('ul', { class: 'typeahead-list', hidden: true, role: 'listbox' });
  const fuse = window.Fuse ? new window.Fuse(items, { keys, threshold: 0.4 }) : null;

  const show = () => {
    const term = input.value.trim();
    const matches = !term ? items.slice(0, 8)
      : fuse ? fuse.search(term).slice(0, 8).map((r) => r.item)
        : items.filter((item) => keys.some((k) =>
            String(item[k] ?? '').toLowerCase().includes(term.toLowerCase())))
          .slice(0, 8);
    replace(list, matches.map((item) => el('li', {
      role: 'option', onmousedown: () => { input.value = ''; list.hidden = true; pick(item); },
    }, label(item))));
    list.hidden = false;
  };
  input.addEventListener('focus', show);
  input.addEventListener('input', show);
  input.addEventListener('blur', () => setTimeout(() => { list.hidden = true; }, 120));
  input.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || list.hidden) return;
    const first = list.querySelector('li');
    if (first) first.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
  });
  return el('div', { class: 'typeahead' }, input, list);
}

function renderRelationships(container, data, charts) {
  const { center, neighbours, edges } = data;

  if (!center.entity_id || !edges.length) {
    replace(container, section(
      `Relationships for ${center.canonical_name}`,
      null,
      noData('commissioning relationships', null),
      el('p', { class: 'small muted', text: 'No matched contract award — '
        + 'this may mean none exists, or that the buyer/supplier names in '
        + 'a real notice could not be matched exactly. Absence here is not '
        + 'evidence that no relationship exists; see the contracts page '
        + 'for the same coverage floor.' })));
    return;
  }

  const byId = new Map([[center.entity_id, center], ...neighbours.map((n) => [n.entity_id, n])]);
  const nodes = [
    { id: center.entity_id, name: center.canonical_name,
      category: center.entity_type === 'PROVIDER' ? 1 : 0, symbolSize: 42 },
    ...neighbours.map((n) => ({ id: n.entity_id, name: n.canonical_name,
      category: n.entity_type === 'PROVIDER' ? 1 : 0, symbolSize: 22 })),
  ];
  const links = edges.map((e) => ({ source: e.subject_entity_id, target: e.object_entity_id }));

  const holder = el('div', {});
  const chartWrap = el('div', {});
  const tableWrap = el('div', {});
  replace(container, section(
    `Relationships for ${center.canonical_name}`,
    `${neighbours.length} ${neighbours.length === 1 ? 'entity' : 'entities'} with a matched commissioning relationship.`,
    chartWrap, tableWrap));

  charts.push(mountChart(chartWrap, {
    tooltip: {},
    legend: [{ data: ['Authority', 'Provider'], bottom: 0 }],
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      label: { show: true, position: 'right', fontSize: 11 },
      force: { repulsion: 220, edgeLength: 110, gravity: 0.15 },
      categories: [{ name: 'Authority' }, { name: 'Provider' }],
      data: nodes,
      links,
      lineStyle: { color: 'source', curveness: 0.08, opacity: 0.6 },
      emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
    }],
  }, {
    height: 'tall',
    aria: `Relationship diagram for ${center.canonical_name}: ${neighbours.length} connected entities`,
    caption: `Commissioning relationships for ${center.canonical_name}`,
    caveat: data.caveat,
  }));

  // The citable record. A force diagram has no accessible text equivalent,
  // and "everything is citable" applies to a relationship exactly as it
  // does to every other figure in this portal.
  replace(tableWrap, el('table', { class: 'small' },
    el('thead', {}, el('tr', {},
      el('th', { text: 'Authority' }), el('th', { text: 'Provider' }),
      el('th', { text: 'Contract period' }), el('th', { text: 'Source' }))),
    el('tbody', {}, edges.map((e) => {
      const subject = byId.get(e.subject_entity_id);
      const object = byId.get(e.object_entity_id);
      const authority = subject?.entity_type === 'PROVIDER' ? object : subject;
      const provider = subject?.entity_type === 'PROVIDER' ? subject : object;
      return el('tr', {},
        el('td', { text: authority?.canonical_name || '—' }),
        el('td', { text: provider?.canonical_name || '—' }),
        el('td', { class: 'small muted',
          text: [e.valid_from, e.valid_to].filter(Boolean).join(' – ') || '—' }),
        el('td', {}, provenance({
          sources: [e.source_url], retrievedAt: e.retrieved_at,
          module: 'm01_procurement', tables: ['contracts', 'entity_relationships'],
        })));
    }))));
}
