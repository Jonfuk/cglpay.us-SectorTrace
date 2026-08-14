/* Providers — the comparison list, and the per-provider deep dive.
 *
 * Both live here because the deep dive is the list with one row expanded into
 * everything the warehouse holds about it: a dated evidence stream, the entity
 * graph, CQC registrations and tribunal cases.
 *
 * The entity graph is the part to be careful with. Some of its edges are
 * `name_only_unconfirmed` — a name that matched, which is not the same as a
 * relationship that exists — and those are drawn as dashed warning-coloured
 * lines rather than as facts.
 */
'use strict';

import { el, replace, fetchJSON, num, gbp, isoDate, sourceLink } from '/app.js';
import { section, pinnedCaveat, caveat, noData, errorCard, mountChart,
          disposeCharts, provenance, tableCard, escapeHtml, truncate,
          statCard, exportButton, registerLink, registerLinks } from '/js/components.js';

export async function render(main, { path }) {
  const key = path.startsWith('/providers/') ? path.slice('/providers/'.length) : null;
  return key ? renderOne(main, key) : renderList(main);
}

// --- the list ----------------------------------------------------------------

async function renderList(main) {
  const charts = [];
  let providers;
  try {
    providers = (await fetchJSON('providers')).providers || [];
  } catch (error) {
    replace(main, errorCard(error.message, () => renderList(main)));
    return () => {};
  }

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Providers' }),
      el('p', { class: 'lede' },
        `${num(providers.length)} organisations tracked across the sector. `,
        'Counts come from different sources with different coverage, so they '
        + 'compare like with like only within a column.')),
    el('div', { id: 'cards' }),
    el('div', { id: 'chart' }),
    el('div', { id: 'table' }));
  replace(main, page);

  replace(page.querySelector('#cards'), el('div', { class: 'grid cards' },
    providers.slice(0, 8).map((p) => el('a', {
      href: `#/providers/${p.provider_key}`,
      style: 'text-decoration:none;color:inherit;',
    }, statCard({
      value: p.canonical_name,
      plain: true,
      label: p.is_target ? '★ campaign subject' : 'provider',
      sub: `${num(p.cqc_locations)} CQC locations · ${num(p.tribunal_count)} tribunal cases`,
    })))));

  const holder = el('div', {});
  replace(page.querySelector('#chart'), section(
    'Evidence held per provider',
    'How much of each kind of record the warehouse holds. A low count is a '
    + 'statement about coverage, not about the provider.',
    el('div', { class: 'panel' }, holder)));

  const named = providers.filter((p) =>
    p.cqc_locations || p.tribunal_count || p.contract_count || p.nhs_job_advert_count);

  if (named.length) {
    charts.push(mountChart(holder, {
      legend: { top: 0 },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      xAxis: { type: 'value', name: 'records' },
      yAxis: { type: 'category', data: named.map((p) => p.canonical_name) },
      series: [
        { name: 'CQC locations', type: 'bar', stack: 'x', data: named.map((p) => p.cqc_locations) },
        { name: 'Tribunal cases', type: 'bar', stack: 'x', data: named.map((p) => p.tribunal_count) },
        { name: 'Contract notices', type: 'bar', stack: 'x', data: named.map((p) => p.contract_count) },
        { name: 'NHS Jobs adverts', type: 'bar', stack: 'x', data: named.map((p) => p.nhs_job_advert_count) },
      ],
    }, {
      height: 'tall',
      aria: 'Stacked bar chart of how many records of each type the warehouse '
        + 'holds for each provider.',
    }));
  } else {
    replace(holder, noData('provider evidence', './start.sh run all'));
  }

  replace(page.querySelector('#table'), tableCard('All providers', [
    { title: 'Provider', field: 'canonical_name' },
    { title: 'Campaign subject', field: 'is_target', width: 140,
      formatter: (c) => (c.getValue() ? '★ yes' : '') },
    { title: 'Contracts', field: 'contract_count', width: 100 },
    { title: 'Contract value', field: 'contract_value_gbp', width: 130,
      formatter: (c) => gbp(c.getValue()) },
    { title: 'CQC locations', field: 'cqc_locations', width: 120 },
    { title: 'Tribunals', field: 'tribunal_count', width: 100 },
    { title: 'NHS adverts', field: 'nhs_job_advert_count', width: 110 },
    { title: 'Charity income', field: 'charity_income_latest', width: 130,
      formatter: (c) => gbp(c.getValue()) },
    // Tabulator formatters may return a DOM node, so these stay text nodes
    // built by el() like everything else on this page -- no HTML string is
    // assembled from a warehouse value to make a link.
    { title: 'Companies House', field: 'company_number', width: 190,
      formatter: (c) => registerLink('company_number', c.getValue()) || '' },
    { title: 'Charity Commission', field: 'charity_number', width: 200,
      formatter: (c) => registerLink('charity_number', c.getValue()) || '' },
  ], providers, { height: 380, exportEndpoint: 'providers' }));

  return () => disposeCharts(charts);
}

// --- the deep dive -----------------------------------------------------------

async function renderOne(main, key) {
  const charts = [];
  let data;
  try {
    data = await fetchJSON(`providers/${encodeURIComponent(key)}/timeline`);
  } catch (error) {
    replace(main, errorCard(error.message, () => renderOne(main, key)));
    return () => {};
  }

  const provider = data.provider || {};
  const page = el('div', {},
    el('div', { class: 'hero' },
      el('p', {}, el('a', { href: '#/providers' }, '← All providers')),
      el('h1', {}, provider.canonical_name || key,
        provider.is_target ? ' ' : null,
        provider.is_target ? el('span', { class: 'badge target', text: '★ CAMPAIGN SUBJECT' }) : null),
      provider.notes ? el('p', { class: 'lede', text: provider.notes }) : null,
      // Built from the entity edges the timeline already carries rather than
      // from a new query: an `identified_by` edge is a scheme and an
      // identifier, which is exactly what a register lookup takes.
      registerLinks((data.entity_edges || [])
        .filter((e) => e.source_id === key)
        .map((e) => ({ scheme: e.target_type, identifier: e.target_id })))),
    el('div', { id: 'timeline' }),
    el('div', { id: 'graph' }),
    el('div', { id: 'cqc' }),
    el('div', { id: 'tribunals' }));
  replace(main, page);

  renderTimeline(page.querySelector('#timeline'), data);
  renderGraph(page.querySelector('#graph'), data, charts, key);
  renderCqc(page.querySelector('#cqc'), data);
  renderTribunals(page.querySelector('#tribunals'), data);

  return () => disposeCharts(charts);
}

function renderTimeline(container, data) {
  const events = data.events || [];
  const list = el('ul', { class: 'timeline' });

  for (const event of events.slice().reverse()) {
    const note = event.caveat ? caveat(event.caveat) : null;
    list.append(el('li', { class: event.event_type },
      el('div', { class: 'when', text: isoDate(event.date) }),
      el('div', { class: 'what' }, event.label || event.event_type,
        note ? note.button : null),
      event.value_summary
        ? el('div', { class: 'detail', text: truncate(event.value_summary, 160) }) : null,
      // A contract event links to the notice, not to the API page it was
      // parsed from — that one is a paginated cursor. Everything else has
      // only the one address.
      event.notice_link
        ? el('div', { class: 'small' }, sourceLink(event.notice_link,
            event.notice_link_basis === 'constructed' ? 'notice ↗ (built from id)' : 'notice ↗'))
        : (event.source_url
          ? el('div', { class: 'small' }, sourceLink(event.source_url, 'source ↗')) : null),
      note ? note.body : null));
  }

  replace(container, section(
    'Evidence timeline',
    `${num(events.length)} dated records, newest first. Each carries the `
    + 'document it came from.',
    el('div', { class: 'panel' },
      events.length ? list : noData('dated evidence', './start.sh run all'))));
}

function renderGraph(container, data, charts, key) {
  const edges = data.entity_edges || [];
  const holder = el('div', {});

  replace(container, section(
    'Entity graph',
    'Company registrations, charity numbers, CQC registrations and contract '
    + 'relationships connected to this provider.',
    el('div', { class: 'panel' },
      edges.some((e) => e.basis === 'name_only_unconfirmed')
        ? pinnedCaveat(
          'Dashed edges matched on name alone. A name that coincides is not a '
          + 'relationship that exists, and nothing here has been confirmed '
          + 'against a register.', 'Unconfirmed edges')
        : null,
      holder)));

  if (!edges.length) {
    replace(holder, noData('entity relationships', './start.sh run m04_companies'));
    return;
  }

  const nodes = new Map();
  const addNode = (id, label, type) => {
    if (!id || nodes.has(id)) return;
    nodes.set(id, {
      id, name: truncate(label || id, 28), category: type || 'other',
      symbolSize: id === key ? 42 : 22,
      itemStyle: id === key ? { color: '#f59e0b' } : undefined,
    });
  };

  for (const edge of edges) {
    addNode(edge.source_id, edge.source_id, edge.source_type);
    addNode(edge.target_id, edge.target_label, edge.target_type);
  }

  const categories = [...new Set([...nodes.values()].map((n) => n.category))]
    .map((name) => ({ name }));

  charts.push(mountChart(holder, {
    legend: { top: 0, data: categories.map((c) => c.name) },
    tooltip: {
      formatter: (p) => (p.dataType === 'edge'
        ? `${escapeHtml(p.data.relationship || '')}<br><span style="color:#8b949e">`
          + `${escapeHtml(p.data.basis || '')}</span>`
        : `<strong>${escapeHtml(p.data.name)}</strong><br>`
          + `<span style="color:#8b949e">${escapeHtml(p.data.category)}</span>`),
    },
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      categories,
      force: { repulsion: 260, edgeLength: 130 },
      label: { show: true, color: '#e6edf3', position: 'right', fontSize: 11 },
      edgeLabel: { show: false },
      data: [...nodes.values()].map((n) => ({
        ...n, category: categories.findIndex((c) => c.name === n.category),
      })),
      links: edges.map((e) => ({
        source: e.source_id,
        target: e.target_id,
        relationship: e.relationship,
        basis: e.basis,
        lineStyle: e.basis === 'name_only_unconfirmed'
          ? { type: 'dashed', color: '#f59e0b', opacity: 0.8 }
          : { color: '#30363d', opacity: 0.7 },
      })),
    }],
  }, {
    height: 'tall',
    aria: `Force-directed graph of ${nodes.size} entities connected to this `
      + `provider by ${edges.length} relationships. Dashed edges are matched on `
      + 'name only and are unconfirmed.',
  }));
}

function renderCqc(container, data) {
  const locations = data.cqc_locations || [];
  const ratingClass = (rating) => {
    const value = (rating || '').toLowerCase();
    if (value === 'outstanding' || value === 'good') return 'good';
    if (value.includes('inadequate') || value.includes('requires')) return 'bad';
    return 'neutral';
  };

  // No "verify at source" link per location, deliberately. The CQC public API
  // publishes no profile URL -- 520 archived payloads contain no cqc.org.uk
  // address at all -- and the conventional shape could not be verified without
  // working around a bot block. A link that 404s is worse than a name.
  replace(container, section(
    'CQC registrations',
    `${num(locations.length)} registered locations.`,
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.cqc_coverage, 'This is not a service map'),
      locations.length
        ? el('div', { style: 'display:flex;flex-wrap:wrap;gap:8px;' },
          locations.map((l) => el('span', {
            class: `badge ${ratingClass(l.overall_rating)}`,
            title: `${l.location_name} — ${l.overall_rating || 'not rated'}`,
          }, `${truncate(l.location_name, 34)} · ${l.overall_rating || 'not rated'}`)))
        : noData('CQC locations', './start.sh run m05_cqc'))));
}

function renderTribunals(container, data) {
  const cases = data.tribunal_cases || [];
  replace(container, section(
    'Employment tribunal cases',
    `${num(cases.length)} judgments naming this provider.`,
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.tribunal_component, 'Read before counting these'),
      cases.length
        ? tableCard('Cases', [
          { title: 'Case', field: 'case_number', width: 150 },
          { title: 'Decided', field: 'decision_date', width: 120,
            formatter: (c) => isoDate(c.getValue()) },
          { title: 'Outcome', field: 'outcome' },
          { title: 'Confidence', field: 'outcome_confidence', width: 120 },
          { title: 'Basis', field: 'provider_match_basis', width: 130 },
          { title: 'Venue', field: 'hearing_venue_raw' },
        ], cases, { height: 320 })
        : noData('tribunal judgments', './start.sh run m02_tribunals'))));
}
