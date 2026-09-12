/* CQC regulated-location explorer (BETA-065).
 *
 * A filterable map and an accessible table, in parity, over the locations
 * that belong to a provider this pipeline tracks and are registered with the
 * Care Quality Commission.
 *
 * The scope limit is the whole point, and it is repeated on the page: CQC
 * registration covers only certain regulated activities. Most community drug
 * and alcohol provision is NOT registered, so this is a map of regulated
 * locations, never a service map, and a count of locations is neither
 * coverage nor quality. Nothing here is combined with any other layer.
 *
 * No personal data: CQC embeds registered-manager names in each location's
 * regulated activities, and those are held in a restricted table the public
 * query never reads.
 */
'use strict';

import { el, replace, fetchJSON, num, sourceLink } from '/app.js';
import { section, pinnedCaveat, errorCard, tableCard, shareButton,
          provenanceFromRows } from '/js/components.js';

// The filters the reader can set. Kept module-local and re-fetched on change;
// the whole results region re-renders, the map and the table together.
const filters = {
  provider_key: '', authority_ons_code: '', registration_status: '',
  regulated_activity: '', service_type: '', rating: '',
};
let offset = 0;
const PAGE = 100;

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

function isDark() {
  return document.documentElement.dataset.theme === 'dark'
    || (!document.documentElement.dataset.theme
        && window.matchMedia('(prefers-color-scheme: dark)').matches);
}

function styleUrl() {
  return isDark()
    ? 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
    : 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';
}

function facetSelect(label, key, options, { placeholder = 'Any' } = {}) {
  const select = el('select', { 'aria-label': label },
    el('option', { value: '', text: placeholder }),
    ...options.map((opt) => {
      const node = el('option', {
        value: opt.value, text: `${opt.value} (${num(opt.count)})`,
      });
      if (String(opt.value) === String(filters[key])) node.selected = true;
      return node;
    }));
  select.addEventListener('change', () => {
    filters[key] = select.value;
    offset = 0;
    rerender();
  });
  return el('label', { class: 'small muted' }, `${label} `, select);
}

function textFilter(label, key) {
  const input = el('input', {
    type: 'search', value: filters[key], 'aria-label': label,
    placeholder: label,
  });
  let timer = null;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      filters[key] = input.value.trim();
      offset = 0;
      rerender();
    }, 300);
  });
  return el('label', { class: 'small muted' }, `${label} `, input);
}

let _resultsHolder = null;
let _map = null;

function disposeMap() {
  if (_map) { try { _map.remove(); } catch (e) { /* already gone */ } _map = null; }
}

async function rerender() {
  if (!_resultsHolder) return;
  disposeMap();
  _resultsHolder.replaceChildren(el('p', { class: 'muted small', text: 'Loading…' }));

  const params = { limit: PAGE, offset };
  for (const [key, value] of Object.entries(filters)) if (value) params[key] = value;

  let data;
  try {
    data = await fetchJSON('cqc_locations', params);
  } catch (error) {
    _resultsHolder.replaceChildren(errorCard(error, rerender));
    return;
  }

  const rows = data.results || [];
  const shown = data.offset + rows.length;
  const located = rows.filter((r) => r.latitude != null && r.longitude != null);

  const mapCanvas = el('div', {
    class: 'cqc-map', role: 'img',
    'aria-label': `Map of ${num(located.length)} CQC-registered locations`,
  });

  const pager = el('div', { class: 'row wrap', style: 'gap:8px;align-items:center;' },
    el('span', { class: 'muted small',
      text: rows.length
        ? `${num(data.offset + 1)}–${num(shown)} of ${num(data.total)}` : 'No matching locations.' }),
    el('button', {
      class: 'btn tiny', disabled: data.offset === 0,
      onclick: () => { offset = Math.max(0, offset - PAGE); rerender(); }, text: 'Previous',
    }),
    el('button', {
      class: 'btn tiny', disabled: shown >= data.total,
      onclick: () => { offset += PAGE; rerender(); }, text: 'Next',
    }));

  _resultsHolder.replaceChildren(
    el('div', { class: 'row wrap', style: 'gap:12px;' },
      facetSelect('Registration status', 'registration_status',
        data.facets.registration_status),
      facetSelect('Overall rating', 'rating', data.facets.overall_rating),
      facetSelect('Service type', 'service_type', data.facets.service_type),
      textFilter('Provider key', 'provider_key'),
      textFilter('Authority ONS code', 'authority_ons_code'),
      textFilter('Regulated activity contains', 'regulated_activity')),
    data.without_coordinate
      ? el('p', { class: 'muted small',
          text: `${num(data.without_coordinate)} location(s) in this filter have no `
                + 'coordinate and are listed in the table but not shown on the map.' })
      : null,
    mapCanvas,
    tableCard('CQC-registered locations', [
      { title: 'Provider', field: 'provider_name', width: 200 },
      { title: 'Location', field: 'location_name', width: 220 },
      { title: 'Authority', field: 'local_authority_raw', width: 160 },
      { title: 'Status', field: 'registration_status', width: 130 },
      { title: 'Rating', field: 'overall_rating', width: 120 },
      { title: 'Rating source', field: 'rating_source', width: 120 },
      { title: 'Service types', field: 'service_types', width: 260 },
    ], rows, { height: Math.min(460, 80 + rows.length * 32) }),
    pager,
    provenanceFromRows(rows, {
      module: 'm05_cqc', tables: ['cqc_locations'],
    }) || el('span', {}));

  if (!located.length) {
    mapCanvas.replaceChildren(el('p', { class: 'muted small',
      text: 'No located results to map for this filter.' }));
    return;
  }
  if (!(await ensureMapLibre())) {
    mapCanvas.replaceChildren(el('p', { class: 'muted small',
      text: 'The map library did not load; the table above is the full result.' }));
    return;
  }

  const points = {
    type: 'FeatureCollection',
    features: located.map((r) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [r.longitude, r.latitude] },
      properties: {
        name: r.location_name || r.provider_name || r.location_id,
        rating: r.overall_rating || 'Not rated',
      },
    })),
  };
  _map = new window.maplibregl.Map({
    container: mapCanvas, style: styleUrl(),
    bounds: [[-6.5, 49.8], [1.9, 55.9]], fitBoundsOptions: { padding: 36 },
    cooperativeGestures: true,
  });
  _map.addControl(new window.maplibregl.NavigationControl({ showCompass: false }), 'top-left');
  _map.on('load', () => {
    _map.addSource('locations', { type: 'geojson', data: points });
    _map.addLayer({
      id: 'location-point', type: 'circle', source: 'locations',
      paint: {
        'circle-color': '#4f8cff', 'circle-radius': 6,
        'circle-stroke-width': 1.5, 'circle-stroke-color': '#f4f8ff',
      },
    });
    _map.on('click', 'location-point', (event) => {
      const props = event.features?.[0]?.properties || {};
      new window.maplibregl.Popup()
        .setLngLat(event.lngLat)
        .setText(`${props.name} — ${props.rating}`)
        .addTo(_map);
    });
    _map.on('mouseenter', 'location-point', () => { _map.getCanvas().style.cursor = 'pointer'; });
    _map.on('mouseleave', 'location-point', () => { _map.getCanvas().style.cursor = ''; });
  });
}

export async function render(main) {
  offset = 0;

  let first;
  try {
    first = await fetchJSON('cqc_locations', { limit: 1 });
  } catch (error) {
    replace(main, errorCard(error, () => render(main)));
    return () => {};
  }

  _resultsHolder = el('div', {});
  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'CQC-registered locations' }),
      el('p', { class: 'lede' },
        `${num(first.total)} locations of tracked providers are registered with `,
        'the Care Quality Commission. CQC registration covers only certain '
        + 'regulated activities, so this is a map of regulated locations — '
        + 'never a complete service map, and a location count is neither '
        + 'coverage nor quality.'),
      el('div', { class: 'hero-actions' },
        shareButton({
          title: 'SectorTrace CQC-registered locations',
          text: 'Explore tracked providers’ CQC-registered locations in SectorTrace.',
          label: 'Share this view',
        }))),
    pinnedCaveat(first.caveat, 'Read this before reading the map'),
    section('Locations', null, el('div', { class: 'panel' }, _resultsHolder)));
  replace(main, page);

  await rerender();
  return () => { disposeMap(); _resultsHolder = null; };
}
