/* Geography — a map workspace for one evidence question at a time. */
'use strict';

import { el, replace, fetchJSON, num, gbp, getState } from '/app.js';
import { section, pinnedCaveat, errorCard, provenance, exportButton, shareButton, tableCard, findingBlock, evidenceMeta, thinEvidenceControl } from '/js/components.js';

/* BETA-078: the unified evidence atlas. Exactly one layer is shown at a time
 * — chosen from the closed registry at /api/v1/atlas_layers — with a
 * synchronised accessible table. There is no overlay and no arithmetic
 * between layers. `ATLAS` is filled from that registry at render time;
 * `CHOROPLETH_DEFAULT` is the fallback when no layer is named in the URL. */
let ATLAS = [];
const CHOROPLETH_DEFAULT = 'grant_drug_alcohol';
const ENGLAND_BOUNDS = [[-6.5, 49.8], [2.2, 56.1]];
let boundaryCache = null;

function atlasLayer(key) { return ATLAS.find((l) => l.key === key) || null; }

function routeState() {
  const [, raw = ''] = (location.hash.slice(1) || '').split('?'); const params = new URLSearchParams(raw);
  // `layer` is the atlas key; fall back to the old `metric` param so shared
  // links from before the atlas still open on the right choropleth.
  const layer = params.get('layer') || params.get('metric') || CHOROPLETH_DEFAULT;
  return { layer, year: params.get('year') || null, selected: params.get('selected') || null };
}
function writeRouteState(state) {
  const [path] = (location.hash.slice(1) || '/geography').split('?'); const params = new URLSearchParams();
  for (const [key, value] of Object.entries(getState())) if (value) params.set(key, value);
  params.set('layer', state.layer); if (state.year) params.set('year', state.year);
  if (state.selected) params.set('selected', state.selected);
  history.replaceState(null, '', `#${path}?${params.toString()}`);
}
function isDark() { return document.documentElement.dataset.bsTheme !== 'light'; }
function styleUrl() { return isDark() ? 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json' : 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json'; }
function format(value, unit) { if (value === null || value === undefined) return '—'; if (unit === 'gbp') return gbp(value, { compact: false }); if (unit === 'gbp_per_head') return `${gbp(value, { compact: false })} per head`; return num(Math.round(value)); }
function tablesFor(key) { if (key.startsWith('grant')) return ['public_health_grants']; if (key === 'budget_public_health') return ['la_revenue_budgets']; if (key === 'treatment_numbers') return ['fingertips_la_values']; if (key === 'cqc_locations') return ['cqc_locations']; if (key === 'coverage') return ['authorities']; return ['contracts']; }
function moduleFor(key) { if (key.startsWith('grant')) return 'm11_public_health_grant'; if (key === 'budget_public_health') return 'm13_la_budgets'; if (key === 'treatment_numbers') return 'm12_fingertips'; if (key === 'cqc_locations') return 'm26_cqc_directory'; if (key === 'coverage') return null; return 'm01_procurement'; }
async function boundaries() { if (!boundaryCache) boundaryCache = fetchJSON('boundaries'); return boundaryCache; }
function englandFeatures(features) { return (features || []).filter((feature) => feature?.properties?.ons_code); }
async function ensureMapLibre() {
  if (window.maplibregl) return true;
  const existing = document.querySelector('script[src="/vendor/maplibre-gl.js"]');
  await new Promise((resolve) => {
    const done = () => resolve();
    if (existing) {
      existing.addEventListener('load', done, { once: true });
      existing.addEventListener('error', done, { once: true });
    } else {
      const script = document.createElement('script');
      script.src = '/vendor/maplibre-gl.js'; script.onload = done; script.onerror = done;
      document.head.append(script);
    }
    window.setTimeout(done, 1600);
  });
  return Boolean(window.maplibregl);
}

export async function render(main) {
  const state = routeState();
  const page = el('div', { class: 'geography-page' },
    el('div', { class: 'hero' }, el('p', { class: 'eyebrow', text: 'Local evidence workspace' }), el('h1', { text: 'Compare local evidence' }),
      el('p', { class: 'lede', text: 'Explore published evidence across English local authorities. Measures stay separate, and every map view retains its source and caveat.' }),
      el('div', { class: 'hero-actions' }, shareButton({ title: 'SectorTrace local evidence', label: 'Share this map view', text: 'A SectorTrace local evidence view with its selected measure, year and layers.' }))),
    el('details', { class: 'read-first' }, el('summary', { text: 'How this workspace works' }), el('p', { text: 'Choose a published question and year, then add one map layer. Select a place from the map or table to preview its evidence and open its authority page or comparison workspace.' }), el('p', { text: 'No data is distinct from a low value. Contract notices, treatment data and regulated locations do not measure the same thing.' })),
    el('div', { id: 'geo-workspace' }));
  replace(main, page);
  const layerSelect = el('select', { 'aria-label': 'Atlas layer', class: 'atlas-layer-select' });
  const yearSelect = el('select', { 'aria-label': 'Financial year' }); const yearWrap = el('label', { class: 'small muted' }, 'Year ', yearSelect);
  const legendHolder = el('div', { class: 'atlas-legend' }); const caveatHolder = el('div', {}); const workspace = el('div', {}); const listHolder = el('div', {}); const provenanceHolder = el('div', {}); const exportHolder = el('span', {});
  replace(page.querySelector('#geo-workspace'), section('Choose one layer', null, el('div', { class: 'panel' },
    el('div', { class: 'toolbar workspace-toolbar' }, el('label', { class: 'small muted' }, 'Layer ', layerSelect), yearWrap, el('span', { class: 'spacer' }), exportHolder),
    legendHolder, caveatHolder, el('div', { class: 'maplayout' }, workspace, listHolder), provenanceHolder)));

  // The atlas registry drives the single selector. One layer at a time; the
  // atlas performs no arithmetic between layers.
  try { ATLAS = (await fetchJSON('atlas_layers')).layers || []; }
  catch (e) { ATLAS = []; }
  if (!atlasLayer(state.layer)) state.layer = ATLAS[0]?.key || CHOROPLETH_DEFAULT;
  replace(layerSelect, ATLAS.map((l) => el('option', { value: l.key, text: l.label, selected: l.key === state.layer })));
  layerSelect.addEventListener('change', () => { state.layer = layerSelect.value; state.year = null; state.selected = null; writeRouteState(state); load(); });
  yearSelect.addEventListener('change', () => { state.year = yearSelect.value || null; state.selected = null; writeRouteState(state); load(); });

  let layerPayload = null;

  async function load() {
    const layer = atlasLayer(state.layer) || ATLAS[0];
    if (!layer) { replace(workspace, errorCard('The atlas layer registry did not load.', () => render(main))); return; }
    layerSelect.value = layer.key;
    yearWrap.hidden = layer.kind !== 'choropleth';
    replace(legendHolder, el('p', { class: 'small' },
      el('strong', { text: `${layer.label}. ` }), `${layer.legend}. Unit: ${layer.unit}.`));
    replace(workspace, el('div', { class: 'shimmer', text: 'Loading atlas layer…' }));

    let geo; try { geo = await boundaries(); } catch (error) { replace(workspace, errorCard(error, load)); return; }

    if (layer.kind === 'choropleth') {
      let data; try { data = await fetchJSON('geography', { metric: layer.key, year: state.year }); }
      catch (error) { replace(workspace, errorCard(error, load)); return; }
      const years = data.available_years || []; replace(yearSelect, years.map((year) => el('option', { value: year, text: year })));
      state.year = data.year || state.year || years[0] || null; yearSelect.value = state.year || ''; writeRouteState(state);
      replace(exportHolder, exportButton('geography', { metric: layer.key, year: state.year }));
      const meta = evidenceMeta({ features: data.features || [] });
      const thin = data.thinEvidence && thinEvidenceControl({
        count: data.thinEvidence.count, threshold: data.thinEvidence.threshold,
        checked: data.thinEvidence.included !== false,
        label: data.thinEvidence.label || 'Include low-evidence places',
        onChange: (included) => { data.thinEvidence.included = included; load(); },
      });
      replace(caveatHolder, [findingBlock({
        finding: 'The atlas shows one published measure at a time with place selection. Layers are never overlaid, differenced or combined into a score.',
        value: `${num((data.features || []).length)} authority values`,
        evidenceStatus: meta.sources.length || meta.retrievedAt ? 'Published' : null,
        timing: { kind: meta.retrievedAt ? 'current' : 'snapshot', date: meta.retrievedAt?.slice(0, 10) },
        sources: meta.sources, retrievedAt: meta.retrievedAt?.slice(0, 10),
        caveat: layer.caveat,
      }), thin, pinnedCaveat(layer.caveat, 'Read this with the map')]);
      replace(provenanceHolder, provenance({ tables: tablesFor(layer.key), module: moduleFor(layer.key) }) || el('span', {}));
      drawList(listHolder, data, geo.features || []);
      await drawWorkspace(workspace, data, geo.features || [], []);
      return;
    }

    // A points or authority-fill layer from /api/v1/layers — drawn alone.
    if (!layerPayload) { try { layerPayload = await fetchJSON('layers'); } catch (error) { replace(workspace, errorCard(error, load)); return; } }
    const sub = layerPayload.layers?.[layer.layer];
    if (!sub) { replace(workspace, errorCard(`The ${layer.label} layer is not available.`, load)); return; }
    writeRouteState(state);
    replace(exportHolder, el('span', {}));
    replace(caveatHolder, [findingBlock({
      finding: 'The atlas shows one published layer at a time. This layer is not overlaid on any other and is never combined into a score.',
      value: `${num((sub.features || []).length)} features`,
      evidenceStatus: 'Published',
      caveat: layer.caveat,
    }), pinnedCaveat(layer.caveat, `Read this with the ${layer.label} layer`)]);
    replace(provenanceHolder, provenance({ tables: tablesFor(layer.key), module: moduleFor(layer.key) }) || el('span', {}));
    drawPointList(listHolder, layer, sub);
    await drawWorkspace(workspace, { features: [], unit: layer.unit, metric_label: layer.label }, geo.features || [], [[layer.layer, sub]]);
  }

  function drawPointList(holder, layer, sub) {
    const cols = layer.table_columns.map((f) => ({ title: f.replace(/_/g, ' '), field: f }));
    replace(holder, el('div', { class: 'map-list panel' },
      el('h3', { text: layer.label }),
      el('p', { class: 'small muted', text: `${num((sub.features || []).length)} features. This table is the accessible equivalent of the map layer.` }),
      tableCard(layer.label, cols, sub.features || [], { height: 460, total: (sub.features || []).length })));
  }
  function select(code) { state.selected = code; writeRouteState(state); load(); }
  function drawList(holder, data, features) {
    const values = new Map((data.features || []).map((row) => [row.ons_code, row])); const rows = englandFeatures(features).map((feature) => { const code = feature.properties.ons_code; const value = values.get(code); return { code, authority_name: value?.authority_name || feature.properties.name || code, region: value?.region || '—', value_display: format(value?.value, data.unit) }; }).sort((a, b) => a.authority_name.localeCompare(b.authority_name)); const selected = rows.find((row) => row.code === state.selected);
    const chooser = el('select', { 'aria-label': 'Select an authority from the text alternative' }, el('option', { value: '', text: 'Select an authority…' }), rows.map((row) => el('option', { value: row.code, text: row.authority_name })));
    chooser.value = state.selected || '';
    chooser.addEventListener('change', () => { if (chooser.value) select(chooser.value); });
    replace(holder, el('div', { class: 'map-list panel' }, el('h3', { text: selected ? selected.authority_name : 'Explore places' }), el('p', { class: 'small muted', text: selected ? `${selected.value_display} · ${selected.region}` : 'Select a map feature or choose a row below. This text alternative has the same selection actions as the map.' }), chooser, selected ? el('div', { class: 'map-preview-actions' }, el('a', { class: 'btn primary', href: `#/authorities/${selected.code}`, text: 'Open authority' }), el('a', { class: 'btn', href: `#/compare?ons_code=${encodeURIComponent(selected.code)}`, text: 'Compare' })) : null, tableCard('Authority values', [{ title: 'Authority', field: 'authority_name' }, { title: 'Region', field: 'region' }, { title: data.metric_label, field: 'value_display' }], rows, { height: 460, total: rows.length })));
  }
  // A MapLibre style with no sources: just a themed background. Used only when
  // the CARTO basemap style cannot be fetched (offline, or the CDN is down).
  // The choropleth is drawn from GeoJSON the portal serves itself, so it does
  // not need the basemap — settled decision 6 ("both front ends render with
  // the network cable unplugged") then holds on this page too, which is the
  // one page that currently half-breaks it. The cluster-count text layer still
  // needs the CDN's glyphs and will not label in this mode; the clusters,
  // points and authority fill/line all draw without it.
  function localMapStyle() {
    return { version: 8, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': isDark() ? '#0b1220' : '#e9eef4' } }] };
  }
  async function drawWorkspace(holder, data, features, activeLayers) {
    if (!await ensureMapLibre()) { replace(holder, errorCard('Map workspace did not load. Reload this page to retry the map library.')); return; }
    const canvas = el('div', { class: 'map-canvas', role: 'region', 'aria-label': `Interactive map of English authorities showing ${data.metric_label}` }); const preview = el('div', { class: 'map-preview' }, el('strong', { text: 'Select a place' }), el('p', { class: 'small muted', text: 'Use the map or the adjacent table to inspect an authority.' })); replace(holder, el('div', { class: 'map-workspace' }, canvas, preview));
    const map = new window.maplibregl.Map({ container: canvas, style: styleUrl(), bounds: ENGLAND_BOUNDS, fitBoundsOptions: { padding: 36 }, cooperativeGestures: true }); map.addControl(new window.maplibregl.NavigationControl({ showCompass: false }), 'top-left');
    let layersDrawn = false; let styleFallbackTried = false;
    // Lifted out of the map.on('load') closure so the offline path can re-run
    // it against the local style after setStyle(). Idempotent via layersDrawn.
    function drawAuthorityLayers() {
      if (layersDrawn) return; layersDrawn = true;
      const values = new Map((data.features || []).map((row) => [row.ons_code, row])); const authorityGeo = { type: 'FeatureCollection', features: englandFeatures(features).map((feature) => ({ ...feature, properties: { ...feature.properties, ...values.get(feature.properties.ons_code), ons_code: feature.properties.ons_code } })) }; map.addSource('authorities', { type: 'geojson', data: authorityGeo }); map.addLayer({ id: 'authority-fill', type: 'fill', source: 'authorities', paint: { 'fill-color': ['case', ['has', 'value'], '#21d4d0', '#4d627b'], 'fill-opacity': ['case', ['has', 'value'], .30, .13] } }); map.addLayer({ id: 'authority-line', type: 'line', source: 'authorities', paint: { 'line-color': isDark() ? '#b2c0d3' : '#4a637c', 'line-width': .7, 'line-opacity': .72 } }); map.on('click', 'authority-fill', (event) => select(event.features?.[0]?.properties?.ons_code)); map.on('mouseenter', 'authority-fill', () => { map.getCanvas().style.cursor = 'pointer'; }); map.on('mouseleave', 'authority-fill', () => { map.getCanvas().style.cursor = ''; }); for (const [key, layer] of activeLayers) addLayer(map, key, layer, authorityGeo); if (state.selected) updatePreview(preview, state.selected, values, data.unit);
    }
    map.on('load', drawAuthorityLayers);
    // Settled decision 6: if the basemap style itself never loads, swap to the
    // local one and draw the choropleth on that. Guarded so a late tile or
    // glyph error on an already-working map can never blank it: once only,
    // only before our layers are on, and only while no style has loaded.
    map.on('error', () => {
      if (styleFallbackTried || layersDrawn || map.isStyleLoaded()) return;
      // diff: false — the CARTO style never finished loading, so there is
      // nothing to diff against and MapLibre would warn and rebuild anyway.
      styleFallbackTried = true; map.setStyle(localMapStyle(), { diff: false });
      const whenReady = () => { if (map.isStyleLoaded()) drawAuthorityLayers(); else map.once('styledata', whenReady); };
      map.once('styledata', whenReady);
    });
  }
  function addLayer(map, key, layer, authorityGeo) {
    const points = (layer.features || []).filter((row) => row.latitude != null && row.longitude != null && row.ons_code).map((row) => ({ type: 'Feature', properties: row, geometry: { type: 'Point', coordinates: [Number(row.longitude), Number(row.latitude)] } }));
    if (key === 'treatment') { const values = new Map((layer.features || []).map((row) => [row.ons_code, row.value])); const geo = { ...authorityGeo, features: authorityGeo.features.map((feature) => ({ ...feature, properties: { ...feature.properties, treatment_value: values.get(feature.properties.ons_code) } })) }; map.addSource('treatment', { type: 'geojson', data: geo }); map.addLayer({ id: 'treatment-fill', type: 'fill', source: 'treatment', paint: { 'fill-color': ['case', ['has', 'treatment_value'], '#a78bfa', 'transparent'], 'fill-opacity': .36 } }); return; }
    if (key === 'coverage') { const values = new Map((layer.features || []).map((row) => [row.ons_code, row.kinds_held])); const geo = { ...authorityGeo, features: authorityGeo.features.map((feature) => ({ ...feature, properties: { ...feature.properties, kinds_held: values.get(feature.properties.ons_code) } })) }; map.addSource('coverage', { type: 'geojson', data: geo }); map.addLayer({ id: 'coverage-fill', type: 'fill', source: 'coverage', paint: { 'fill-color': ['interpolate', ['linear'], ['coalesce', ['get', 'kinds_held'], 0], 0, '#26324a', 8, '#21d4d0'], 'fill-opacity': ['case', ['has', 'kinds_held'], .5, .1] } }); map.on('click', 'coverage-fill', (event) => select(event.features?.[0]?.properties?.ons_code)); return; }
    if (!points.length) return; map.addSource(`${key}-points`, { type: 'geojson', data: { type: 'FeatureCollection', features: points }, cluster: true, clusterRadius: 42, clusterMaxZoom: 10 }); map.addLayer({ id: `${key}-clusters`, type: 'circle', source: `${key}-points`, filter: ['has', 'point_count'], paint: { 'circle-color': key === 'contracts' ? '#21d4d0' : '#4f8cff', 'circle-radius': ['step', ['get', 'point_count'], 16, 10, 21, 50, 27], 'circle-stroke-width': 2, 'circle-stroke-color': '#fbbf24' } }); map.addLayer({ id: `${key}-count`, type: 'symbol', source: `${key}-points`, filter: ['has', 'point_count'], layout: { 'text-field': '{point_count_abbreviated}', 'text-size': 12 }, paint: { 'text-color': '#08111f' } }); map.addLayer({ id: `${key}-point`, type: 'circle', source: `${key}-points`, filter: ['!', ['has', 'point_count']], paint: { 'circle-color': key === 'contracts' ? '#21d4d0' : '#4f8cff', 'circle-radius': key === 'contracts' ? ['interpolate', ['linear'], ['coalesce', ['get', 'count'], 0], 0, 5, 50, 10, 200, 15] : 6, 'circle-stroke-width': 1.5, 'circle-stroke-color': '#f4f8ff' } }); map.on('click', `${key}-clusters`, (event) => { const feature = event.features?.[0]; map.getSource(`${key}-points`).getClusterExpansionZoom(feature.properties.cluster_id, (error, zoom) => { if (!error) map.easeTo({ center: feature.geometry.coordinates, zoom }); }); }); map.on('click', `${key}-point`, (event) => select(event.features?.[0]?.properties?.ons_code));
  }
  function updatePreview(preview, code, values, unit) { const row = values.get(code); const name = row?.authority_name || code; replace(preview, el('div', {}, el('h3', { text: name }), el('p', { class: 'small muted', text: `${format(row?.value, unit)} · ${row?.region || 'English local authority'}` }), el('div', { class: 'map-preview-actions' }, el('a', { class: 'btn primary', href: `#/authorities/${code}`, text: 'Open authority' }), el('a', { class: 'btn', href: `#/compare?ons_code=${encodeURIComponent(code)}`, text: 'Compare' })))); }
  await load(); return () => {};
}
