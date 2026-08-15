/* Geography — one metric at a time, across English local authorities.
 *
 * D3 draws the boundaries because the projection has to be right: these are
 * real administrative areas and every figure on the page is keyed to their ONS
 * codes. The geometry comes from the warehouse, where Module 0 already put it
 * with provenance, rather than from a separately-fetched boundary file that
 * could disagree with the codes everything else is joined on.
 *
 * Grant and budget are never shown together. They are different figures from
 * different documents, and the one thing this page must not do is let someone
 * read a gap between them as underspend.
 */
'use strict';

import { el, replace, fetchJSON, num, gbp, isoDate } from '/app.js';
import { section, pinnedCaveat, noData, errorCard, mountChart, disposeCharts,
          provenance, escapeHtml, exportButton } from '/js/components.js';

const METRICS = [
  ['grant_drug_alcohol', 'Drug & alcohol ring-fenced grant'],
  ['grant_total', 'Public health grant (total)'],
  ['grant_per_head', 'Grant per head'],
  ['budget_public_health', 'Budgeted public health spend'],
  ['treatment_numbers', 'Numbers in treatment'],
  ['contract_value', 'Contract value awarded'],
];

let boundaryCache = null;

export async function render(main) {
  const charts = [];
  const state = { metric: 'grant_drug_alcohol', year: null };

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Geography' }),
      el('p', { class: 'lede' },
        'Allocations, budgets and treatment numbers by local authority. ',
        'One metric at a time, because these are not comparable with each other.')),
    el('div', { id: 'geo' }));
  replace(main, page);

  const tabs = el('div', { class: 'metrictabs' });
  const yearSelect = el('select', { 'aria-label': 'Financial year' });
  const mapHolder = el('div', {});
  const rankHolder = el('div', {});
  const caveatHolder = el('div', {});
  const provHolder = el('div', {});
  const legend = el('div', { class: 'legend' });

  replace(page.querySelector('#geo'), section(
    'Choose a metric',
    null,
    el('div', { class: 'panel' },
      tabs,
      el('div', { class: 'toolbar', style: 'display:flex;gap:12px;align-items:center;margin-bottom:12px;' },
        el('label', { class: 'small muted', text: 'Year' }), yearSelect,
        el('span', { class: 'spacer' }),
        el('span', { id: 'geo-export' })),
      caveatHolder,
      el('div', { class: 'maplayout' },
        el('div', {}, mapHolder, legend),
        el('div', {}, rankHolder)),
      provHolder)));

  for (const [key, label] of METRICS) {
    tabs.append(el('button', {
      class: 'btn', type: 'button', 'aria-pressed': String(key === state.metric),
      onclick: () => { state.metric = key; state.year = null; load(); },
      dataset: { metric: key },
    }, label));
  }

  yearSelect.addEventListener('change', () => {
    state.year = yearSelect.value || null;
    load();
  });

  async function load() {
    for (const button of tabs.querySelectorAll('button')) {
      button.setAttribute('aria-pressed', String(button.dataset.metric === state.metric));
    }
    replace(mapHolder, el('div', { class: 'shimmer' }));

    let data;
    try {
      data = await fetchJSON('geography', { metric: state.metric, year: state.year });
    } catch (error) {
      replace(mapHolder, errorCard(error.message, load));
      return;
    }

    const years = data.available_years || [];
    replace(yearSelect, years.map((y) => el('option', { value: y, text: y })));
    yearSelect.value = data.year || (years[0] || '');
    state.year = yearSelect.value || null;

    replace(caveatHolder, [
      pinnedCaveat(data.caveat, 'Read this with the map'),
      indicativeNote(data),
    ].filter(Boolean));

    replace(page.querySelector('#geo-export') || el('span', {}),
      exportButton('geography', { metric: state.metric, year: state.year }));

    replace(provHolder, provenance({
      tables: tablesFor(state.metric),
      module: moduleFor(state.metric),
    }) || el('span', {}));

    await drawMap(mapHolder, legend, data);
    drawRanking(rankHolder, data, charts);
  }

  await load();
  return () => disposeCharts(charts);
}

/* Later grant years are published as indicative and revised afterwards.
 * Reading a fall between a confirmed year and an indicative one as a cut is
 * the mistake this note exists to prevent. */
function indicativeNote(data) {
  const statuses = data.allocation_status || [];
  const forYear = statuses.filter((s) => !data.year || s.financial_year === data.year);
  if (!forYear.some((s) => s.allocation_status === 'indicative')) return null;
  return pinnedCaveat(
    `Allocations for ${data.year} are published as indicative and are revised `
    + 'later. Do not compare an indicative year with a confirmed one.',
    'Indicative allocation');
}

function tablesFor(metric) {
  if (metric.startsWith('grant')) return ['public_health_grants'];
  if (metric === 'budget_public_health') return ['la_revenue_budgets'];
  if (metric === 'treatment_numbers') return ['fingertips_la_values'];
  return ['contracts'];
}

function moduleFor(metric) {
  if (metric.startsWith('grant')) return 'm11_public_health_grant';
  if (metric === 'budget_public_health') return 'm13_la_budgets';
  if (metric === 'treatment_numbers') return 'm12_fingertips';
  return 'm01_procurement';
}

async function boundaries() {
  if (boundaryCache) return boundaryCache;
  boundaryCache = await fetchJSON('boundaries');
  return boundaryCache;
}

async function drawMap(container, legend, data) {
  if (!window.d3) {
    replace(container, errorCard('Mapping library did not load.'));
    return;
  }

  let geo;
  try {
    geo = await boundaries();
  } catch (error) {
    replace(container, errorCard(error.message));
    return;
  }
  if (!geo.features?.length) {
    replace(container, noData('authority boundaries', './start.sh run m00_geography'));
    return;
  }

  const values = new Map(
    (data.features || []).map((f) => [f.ons_code, f.value]));
  const names = new Map(
    (data.features || []).map((f) => [f.ons_code, f.authority_name]));
  const numbers = [...values.values()].filter((v) => v !== null && v !== undefined);
  if (!numbers.length) {
    replace(container, noData(`${data.metric_label} values`, null));
    return;
  }

  const d3 = window.d3;
  const width = container.clientWidth || 720;
  const height = 620;

  const svg = d3.create('svg')
    .attr('class', 'map')
    .attr('viewBox', `0 0 ${width} ${height}`)
    .attr('role', 'img')
    .attr('aria-label',
      `Map of English local authorities coloured by ${data.metric_label}. `
      + `Range ${format(data.min, data.unit)} to ${format(data.max, data.unit)}. `
      + 'Click an area for its authority page.');

  const collection = { type: 'FeatureCollection', features: geo.features };
  const projection = d3.geoMercator().fitSize([width, height], collection);
  const path = d3.geoPath(projection);

  // Quantile rather than linear: grant allocations are heavily skewed by
  // authority size, and a linear ramp renders as one bright city and 300
  // indistinguishable areas.
  const scale = d3.scaleQuantile()
    .domain(numbers)
    .range(d3.quantize(d3.interpolateYlOrRd, 7));

  const tip = el('div', { class: 'maptip', hidden: true });
  document.body.append(tip);

  svg.append('g').selectAll('path')
    .data(geo.features)
    .join('path')
    .attr('d', path)
    .attr('class', (f) => (values.has(f.properties.ons_code) ? null : 'nodata'))
    .attr('fill', (f) => {
      const value = values.get(f.properties.ons_code);
      return value === null || value === undefined ? '#1c2128' : scale(value);
    })
    .on('mousemove', (event, f) => {
      const code = f.properties.ons_code;
      const value = values.get(code);
      tip.hidden = false;
      tip.textContent = '';
      tip.append(
        el('strong', { text: names.get(code) || f.properties.name || code }),
        el('div', { class: 'small muted', text: code }),
        el('div', { text: value === undefined || value === null
          ? 'no value for this metric' : format(value, data.unit) }),
        el('div', { class: 'small muted', text: 'click for this authority' }));
      tip.style.left = `${Math.min(event.clientX + 14, window.innerWidth - 300)}px`;
      tip.style.top = `${event.clientY + 14}px`;
    })
    .on('mouseleave', () => { tip.hidden = true; })
    // W-14: the map is an entry point now. The click carries the ONS code
    // through to the authority page — where the absence stories live too,
    // which is why an area with no value for this metric is still clickable.
    .on('click', (event, f) => {
      location.hash = `#/authorities/${f.properties.ons_code}`;
    });

  replace(container, svg.node());

  const stops = d3.quantize(d3.interpolateYlOrRd, 7);
  replace(legend,
    el('span', { class: 'small', text: format(data.min, data.unit) }),
    el('div', {
      class: 'legend-scale',
      style: `background: linear-gradient(90deg, ${stops.join(', ')})`,
    }),
    el('span', { class: 'small', text: format(data.max, data.unit) }),
    el('span', { class: 'small muted', text: `· ${num(data.features.length)} authorities` }));
}

function drawRanking(container, data, charts) {
  const features = (data.features || [])
    .filter((f) => f.value !== null && f.value !== undefined)
    .slice(0, 20)
    .reverse();

  const holder = el('div', {});
  replace(container, el('div', {},
    el('h3', { text: `Highest 20 — ${data.metric_label}` }),
    holder));

  if (!features.length) {
    replace(holder, noData('values', null));
    return;
  }

  charts.push(mountChart(holder, {
    grid: { left: 8, right: 24, top: 8, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const row = features[params[0].dataIndex];
        return `<strong>${escapeHtml(row.authority_name)}</strong><br>`
          + `${escapeHtml(row.region || '')}<br>${format(row.value, data.unit)}`;
      },
    },
    xAxis: { type: 'value', axisLabel: { formatter: (v) => shortValue(v, data.unit) } },
    yAxis: { type: 'category', data: features.map((f) => f.authority_name) },
    series: [{ type: 'bar', data: features.map((f) => f.value) }],
  }, {
    height: 'tall',
    aria: `Bar chart of the twenty authorities with the highest `
      + `${data.metric_label}.`,
  }));
}

function format(value, unit) {
  if (value === null || value === undefined) return '—';
  if (unit === 'gbp') return gbp(value, { compact: false });
  if (unit === 'gbp_per_head') return `${gbp(value, { compact: false })} per head`;
  return num(Math.round(value));
}

function shortValue(value, unit) {
  if (unit === 'gbp' || unit === 'gbp_per_head') return gbp(value);
  return num(value);
}
