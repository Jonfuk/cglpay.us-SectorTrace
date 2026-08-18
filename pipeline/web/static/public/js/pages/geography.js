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
          provenance, escapeHtml, exportButton, shareButton, tableCard } from '/js/components.js';

const METRICS = [
  ['grant_drug_alcohol', 'Drug & alcohol ring-fenced grant'],
  ['grant_total', 'Public health grant (total)'],
  ['grant_per_head', 'Grant per head'],
  ['budget_public_health', 'Budgeted public health spend'],
  ['treatment_numbers', 'Numbers in treatment'],
  ['contract_value', 'Contract value awarded'],
];

const POSITRON_LAYERS = new Set(['cqc_locations', 'contracts', 'treatment']);

let boundaryCache = null;

/* W-19: overlay layers, toggled per kind of evidence. The toggles are built
 * from /api/v1/layers, whose caveats come from the same source the export
 * layers use, so a layer that is drawn here carries the caveat discipline its
 * export carries — and a layer added to the payload gains a toggle here
 * without anyone hardcoding a caveat text. PFD reports are deliberately not
 * in the payload at all: they have no geometry, and coroner areas must not be
 * mapped as if they were authorities. */
let layersPayload = null;
let layerState = {};
let mapContext = null;
let rerenderMap = null;

export async function render(main) {
  const charts = [];
  const state = { metric: 'grant_drug_alcohol', year: null };

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Compare local evidence' }),
      el('p', { class: 'lede' },
        'Explore one published metric at a time across local authorities. Allocations, budgets and treatment numbers remain separate measures.'),
      el('div', { class: 'hero-actions' },
        shareButton({
          title: 'SectorTrace local evidence',
          text: 'Explore this SectorTrace local evidence view with its metric and year context.',
          label: 'Share this view',
        }))),
    el('details', { class: 'read-first' },
      el('summary', { text: 'How this map works' }),
      el('p', { text: 'Choose a question, then a year. The map is an entry point to an authority page; it is not a league table.' }),
      el('p', { text: 'The visible caveat, legend and selected metric define what the values mean. No data is shown separately from a low value.' })),
    el('div', { id: 'geo' }));
  replace(main, page);

  const tabs = el('div', { class: 'metrictabs' });
  const yearSelect = el('select', { 'aria-label': 'Financial year' });
  const mapHolder = el('div', {});
  const rankHolder = el('div', {});
  const caveatHolder = el('div', {});
  const layerHolder = el('div', {});
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
      layerHolder,
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
    redrawOverlays();
  }

  rerenderMap = load;
  await load();
  initLayers(layerHolder);
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
  const leafletKey = [...POSITRON_LAYERS].find((key) => layerState[key]);
  const leafletLayer = layersPayload?.layers?.[leafletKey];
  if (leafletLayer && window.L) {
    await drawLeafletMap(container, legend, leafletKey, leafletLayer);
    mapContext = null;
    return;
  }
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

  // The context the overlay layers draw on: the same projection and path the
  // choropleth used, so a contract point and a boundary edge cannot disagree
  // about where an authority is.
  mapContext = {
    svg, projection, path, tip, features: geo.features, legend,
    names: (f) => names.get(f.properties.ons_code) || f.properties.name,
  };
  redrawOverlays();
  return mapContext;
}

function drawRanking(container, data, charts) {
  const features = (data.features || [])
    .filter((f) => f.value !== null && f.value !== undefined)
    .slice(0, 20)
    .reverse();

  const holder = el('div', {});
  replace(container, el('div', {},
    el('h3', { text: `Explore values — ${data.metric_label}` }),
    el('p', { class: 'small muted', text: 'A text table alternative to the map. Open an authority page to explore its evidence in context.' }),
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

  container.append(tableCard('Visible authority values', [
    { title: 'Authority', field: 'authority_name' },
    { title: 'Region', field: 'region' },
    { title: data.metric_label, field: 'value_display' },
  ], features.slice().reverse().map((feature) => ({
    authority_name: feature.authority_name,
    region: feature.region || '—',
    value_display: format(feature.value, data.unit),
  })), { height: 320, total: features.length }));
}

// --- overlay layers (W-19) ----------------------------------------------------

/* The toggle panel, built from the payload so a layer's label and caveats
 * live in one place: the same caveats the export layer carries, joined for
 * the screen. A checked layer draws its overlay on the current map and pins
 * its caveat beside the toggle; the overlay and the caveat are cleared
 * together, so a figure and the warning that governs it never separate. */
async function initLayers(holder) {
  let payload;
  try {
    payload = await fetchJSON('layers');
  } catch (error) {
    replace(holder, el('p', { class: 'small muted' },
      'Overlay layers unavailable: ', error.message));
    return;
  }
  layersPayload = payload;

  const rows = [];
  const inputs = new Map();
  const caveats = new Map();
  for (const [key, layer] of Object.entries(payload.layers || {})) {
    const caveatBox = el('div', { class: 'layer-caveat' });
    const input = el('input', { type: 'checkbox', dataset: { layer: key } });
    input.addEventListener('change', (e) => {
      layerState[key] = e.target.checked;
      if (e.target.checked && POSITRON_LAYERS.has(key)) {
        for (const [otherKey, otherInput] of inputs) {
          if (otherKey === key || !POSITRON_LAYERS.has(otherKey)) continue;
          otherInput.checked = false;
          layerState[otherKey] = false;
          replace(caveats.get(otherKey), el('span', {}));
        }
      }
      replace(caveatBox, e.target.checked
        ? pinnedCaveat(layer.caveats.join(' '),
            `Read this with the ${layer.label} layer`)
        : el('span', {}));
      if (rerenderMap) rerenderMap();
    });
    inputs.set(key, input);
    caveats.set(key, caveatBox);
    rows.push(el('label', { class: 'layer-toggle' },
      input,
      el('span', { text: layer.label })),
      caveatBox);
  }
  replace(holder, el('div', { class: 'layerpanel' }, rows));
}

/* The overlays are drawn after every map redraw — a metric switch replaces
 * the SVG, and the layers must come back with it. Layer state persists across
 * switches, which is the point: a reader comparing contracts against two
 * metrics changes the base, not the overlays. */
function redrawOverlays() {
  const ctx = mapContext;
  if (!ctx || !layersPayload) return;
  ctx.svg.selectAll('.overlay').remove();
  ctx.legend.querySelectorAll('.layer-legend').forEach((n) => n.remove());
  ctx.svg.classed('cqc-location-map', Boolean(layerState.cqc_locations));
  if (layerState.cqc_locations) {
    ctx.svg.attr('aria-label', 'Map of England showing CQC-registered locations. '
      + 'Authority boundaries provide geographic context; CQC registration does not cover every service.');
  }
  for (const [key, on] of Object.entries(layerState)) {
    if (!on) continue;
    const layer = layersPayload.layers?.[key];
    if (!layer) continue;
    if (key === 'contracts') drawContractPoints(ctx, layer);
    else if (key === 'cqc_locations') drawCqcPoints(ctx, layer);
    else if (key === 'treatment') drawTreatmentFill(ctx, layer);
    else if (key === 'coverage') drawCoverageOutline(ctx, layer);
  }
}

function overlayTip(ctx, event, lines) {
  const tip = ctx.tip;
  tip.hidden = false;
  tip.textContent = '';
  for (const line of lines) tip.append(line);
  tip.style.left = `${Math.min(event.clientX + 14, window.innerWidth - 300)}px`;
  tip.style.top = `${event.clientY + 14}px`;
}

/* Contracts: one point per commissioning authority, sized by notice count.
 * The payload aggregated the corpus — 98,636 points are a canvas no reader
 * can use — and the layer's caveats say so. The point sits at the authority's
 * own centroid, which is exactly what the caveat warns about. */
function drawContractPoints(ctx, layer) {
  const byCode = new Map((layer.features || []).map((f) => [f.ons_code, f]));
  const points = [];
  for (const feature of ctx.features) {
    const row = byCode.get(feature.properties.ons_code);
    if (!row) continue;
    points.push({ ...row, xy: ctx.path.centroid(feature) });
  }
  if (!points.length) return;

  ctx.svg.append('g').attr('class', 'overlay')
    .selectAll('circle')
    .data(points)
    .join('circle')
    .attr('cx', (d) => d.xy[0])
    .attr('cy', (d) => d.xy[1])
    .attr('r', (d) => Math.max(3, Math.min(15, Math.sqrt(d.count) / 7)))
    .attr('fill', 'rgba(45, 212, 191, 0.8)')
    .attr('stroke', '#0d1117')
    .attr('stroke-width', 0.6)
    .on('mousemove', (event, d) => {
      overlayTip(ctx, event, [
        el('strong', { text: d.authority_name }),
        el('div', { class: 'small muted', text: d.ons_code }),
        el('div', { text: `${num(d.count)} notices · ${gbp(d.value_gbp)}` }),
      ]);
    })
    .on('mouseleave', () => { ctx.tip.hidden = true; })
    .on('click', (event, d) => { location.hash = `#/authorities/${d.ons_code}`; });

  ctx.legend.append(el('span', {
    class: 'small muted layer-legend',
    text: `· ○ contracts, size by notice count (${num(points.length)} authorities)`,
  }));
}

/* CQC: every regulated location with a published coordinate. The layer's
 * caveat is the whole point — most community provision is not CQC-registered,
 * so the pins are a map of regulated locations, not of services. */
function drawCqcLeafletMap(container, legend, layer) {
  const points = englandPoints(layer.features || []);
  return drawLeafletPoints(container, legend, points, {
    color: '#2563eb',
    legend: `CQC-registered locations in England: ${num(points.length)}`,
    radius: () => 5,
    tooltip: (point) => point.location_name,
  });
}

async function drawLeafletMap(container, legend, key, layer) {
  if (key === 'cqc_locations') {
    drawCqcLeafletMap(container, legend, layer);
    return;
  }
  const geo = await boundaries();
  const points = authorityPoints(layer.features || [], geo.features || []);
  const isContracts = key === 'contracts';
  drawLeafletPoints(container, legend, points, {
    color: isContracts ? '#0f766e' : '#7c3aed',
    legend: isContracts
      ? `Commissioning authorities with contracts: ${num(points.length)}`
      : `Authorities with treatment numbers: ${num(points.length)}`,
    radius: isContracts
      ? (point) => Math.max(5, Math.min(15, Math.sqrt(point.count) / 7))
      : () => 6,
    tooltip: isContracts
      ? (point) => `${point.authority_name}: ${num(point.count)} notices`
      : (point) => `${point.authority_name}: treatment numbers available`,
  });
}

function drawLeafletPoints(container, legend, points, options) {
  const holder = el('div', { class: 'leaflet-map' });
  replace(container, holder);
  const map = window.L.map(holder, { scrollWheelZoom: false });
  map.fitBounds([[49.8, -6.5], [56.1, 2.2]]);
  window.L.tileLayer(
    'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
    { subdomains: 'abcd', maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO' },
  ).addTo(map);
  for (const point of points) {
    window.L.circleMarker([point.latitude, point.longitude], {
      radius: options.radius(point), color: '#0f172a', weight: 1,
      fillColor: options.color, fillOpacity: 0.9,
    }).bindTooltip(escapeHtml(options.tooltip(point)))
      .on('click', () => { location.hash = `#/authorities/${point.ons_code}`; })
      .addTo(map);
  }
  replace(legend, el('span', { class: 'small muted', text: options.legend }));
}

function englandPoints(features) {
  return features.filter((point) => point.latitude != null
    && point.longitude != null && point.latitude >= 49.8 && point.latitude <= 56.1
    && point.longitude >= -6.5 && point.longitude <= 2.2 && point.ons_code);
}

function authorityPoints(rows, features) {
  const boundariesByCode = new Map(features.map((feature) => [
    feature.properties.ons_code, feature,
  ]));
  const seen = new Set();
  return rows.filter((row) => {
    if (!row.ons_code || seen.has(row.ons_code)) return false;
    seen.add(row.ons_code);
    return boundariesByCode.has(row.ons_code);
  }).map((row) => {
    const [longitude, latitude] = window.d3.geoCentroid(
      boundariesByCode.get(row.ons_code));
    return { ...row, latitude, longitude };
  });
}

function drawCqcPoints(ctx, layer) {
  const points = (layer.features || [])
    .filter((f) => f.latitude !== null && f.longitude !== undefined
      && f.latitude !== undefined && f.longitude !== null)
    .map((f) => {
      const xy = ctx.projection([f.longitude, f.latitude]);
      return xy ? { ...f, xy } : null;
    })
    .filter(Boolean);
  if (!points.length) return;

  ctx.svg.append('g').attr('class', 'overlay')
    .selectAll('circle')
    .data(points)
    .join('circle')
    .attr('cx', (d) => d.xy[0])
    .attr('cy', (d) => d.xy[1])
    .attr('r', 4)
    .attr('fill', 'rgba(96, 165, 250, 0.9)')
    .attr('stroke', '#0d1117')
    .attr('stroke-width', 0.6)
    .on('mousemove', (event, d) => {
      overlayTip(ctx, event, [
        el('strong', { text: d.location_name }),
        el('div', { class: 'small muted', text: d.region || 'region not recorded' }),
        el('div', { text: `CQC rating: ${d.overall_rating || 'not rated'}` }),
      ]);
    })
    .on('mouseleave', () => { ctx.tip.hidden = true; });

  ctx.legend.append(el('span', {
    class: 'small muted layer-legend',
    text: `· ● CQC-registered locations (${num(points.length)})`,
  }));
}

/* Treatment: the latest published rate per authority, as a translucent fill
 * over whatever metric the base map shows. The rate scale is quantile over
 * this layer's own values, never shared with the base metric's. */
function drawTreatmentFill(ctx, layer) {
  const values = (layer.features || [])
    .map((f) => f.value).filter((v) => v !== null && v !== undefined);
  if (!values.length) return;

  const byCode = new Map((layer.features || []).map((f) => [f.ons_code, f]));
  const scale = window.d3.scaleQuantile()
    .domain(values)
    .range(window.d3.quantize(window.d3.interpolateYlGnBu, 6));

  ctx.svg.append('g').attr('class', 'overlay')
    .selectAll('path')
    .data(ctx.features)
    .join('path')
    .attr('d', ctx.path)
    .attr('fill', (f) => {
      const row = byCode.get(f.properties.ons_code);
      return row ? scale(row.value) : 'none';
    })
    .attr('opacity', 0.5)
    .attr('pointer-events', 'none');

  const period = [...new Set((layer.features || [])
    .map((f) => f.time_period).filter(Boolean))].sort().pop();
  ctx.legend.append(el('span', {
    class: 'small muted layer-legend',
    text: `· treatment rates, latest period (${period || 'period varies'})`,
  }));
}

/* Coverage: how many evidence kinds the warehouse holds per authority, as an
 * outline. The layer's caveat is the standing one — absence is absence of
 * collection, not evidence of absence — and the outline intensity shows how
 * much the pipeline holds here without implying the authority is anything. */
function drawCoverageOutline(ctx, layer) {
  const byCode = new Map((layer.features || []).map((f) => [f.ons_code, f]));
  const max = Math.max(1, ...(layer.features || []).map((f) => f.kinds_held));

  ctx.svg.append('g').attr('class', 'overlay')
    .selectAll('path')
    .data(ctx.features)
    .join('path')
    .attr('d', ctx.path)
    .attr('fill', 'none')
    .attr('stroke', (f) => {
      const row = byCode.get(f.properties.ons_code);
      return row ? '#f59e0b' : 'none';
    })
    .attr('stroke-width', (f) => {
      const row = byCode.get(f.properties.ons_code);
      return row ? 0.8 + (row.kinds_held / max) * 2.4 : 0;
    })
    .attr('opacity', 0.9)
    .attr('pointer-events', 'none');

  ctx.legend.append(el('span', {
    class: 'small muted layer-legend',
    text: `· amber outline: evidence kinds held (of ${num(max)})`,
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
