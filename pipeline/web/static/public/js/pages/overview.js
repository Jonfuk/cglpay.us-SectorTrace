/* Overview — what is in the corpus, and what it is not.
 *
 * The hero cards are deliberately conservative. Two of the figures the brief
 * asked for at the top of this page cannot honestly be headline numbers
 * against the current warehouse, and the page says so instead of rendering
 * them anyway:
 *
 *   * Sector vacancy and turnover rates. A census metric is `verified = 0`
 *     until somebody has checked it against the page it was parsed from, and
 *     the pipeline's own caveats say to filter on that before publishing. The
 *     card reads the flag per figure rather than per corpus — a partly-checked
 *     census is the normal state now that checking is done one figure at a
 *     time — and an unverified one is drawn plain and marked as such.
 *
 *   * Total contract value. A handful of cross-government framework notices
 *     carry ceilings in the tens of billions, so the sum is not a figure about
 *     this sector at all. The card shows the median notice instead, with the
 *     total and its concentration a click away.
 */
'use strict';

import { el, svgEl, replace, fetchJSON, num, gbp, pct, ago } from '/app.js';
import { statCard, section, pinnedCaveat, noData, errorCard, mountChart,
          disposeCharts, provenance, truncate, escapeHtml, shareButton, tableCard,
          lensBadge, timingBadge, findingBlock, revealOnScroll } from '/js/components.js';

const SOURCE_LABELS = {
  contracts_finder: 'Contracts Finder',
  contracts_finder_csv_archive: 'Contracts Finder (historical CSV archive)',
  all_staff: 'All staff',
  change_grow_live: 'Change Grow Live',
};

export async function render(main) {
  const charts = [];
  let summary;
  try {
    summary = await fetchJSON('summary');
  } catch (error) {
    replace(main, errorCard(error.message, () => render(main)));
    return () => {};
  }

  const heroMap = el('div', { class: 'hero-map', id: 'hero-map' });
  const page = el('div', {},
    el('div', { class: 'hero hero-split hero-animated' },
      el('div', { class: 'hero-copy' },
        el('div', { class: 'hero-kicker' }, lensBadge('accountability'), ' · England-wide evidence desk'),
        el('h1', { text: 'Evidence for fair pay in England’s drug and alcohol treatment sector' }),
        el('p', { class: 'lede' },
          'Explore published evidence about pay, commissioning, providers, treatment activity ',
          'and workforce conditions. Every figure links to its source, retrieval date and caveats; ',
          'missing values are never guessed.'),
        el('div', { class: 'hero-actions' },
          shareButton({
            title: 'SectorTrace overview',
            text: 'Explore the latest SectorTrace evidence snapshot.',
          }),
          el('a', { class: 'btn ghost', href: '#/coverage' }, 'How evidence is handled')),
        el('details', { class: 'read-first' },
          el('summary', { text: 'Read this first' }),
          el('p', { text: 'This is a map of the evidence held by the portal, not a single scorecard. Pay, contracts, treatment activity, workforce figures and safety evidence remain separate layers.' }),
          el('p', { text: 'A status such as unverified, not collected or unavailable describes the evidence state. It does not mean zero.' }))),
      heroMap),
    el('div', { id: 'snapshot' }),
    el('div', { id: 'briefing-strip' }),
    el('div', { id: 'explore' }),
    el('div', { id: 'evidence-status' }),
    el('div', { id: 'contracts-chart' }));
  replace(main, page);

  // Pre-existing bug fixed in passing (BETA-032): this used to fill a
  // detached `el('div', {})` that was never inserted into `page` — the
  // element below with a matching id was a separate, permanently-empty
  // node. The whole "Current snapshot" band (coverage, evidence quality,
  // sector context cards) has not rendered on the live site until now.
  renderCards(page.querySelector('#snapshot'), summary);
  renderBriefingStrip(page.querySelector('#briefing-strip'), summary);
  renderExplore(page.querySelector('#explore'));
  renderEvidenceStatus(page.querySelector('#evidence-status'), summary);
  // Lazily filled after first paint — a separate fetch of its own, and not
  // on the critical path for the headline text above it.
  renderHeroMap(heroMap, summary);
  // Freshness is seconds of table scans, so renderEvidenceStatus fetches it
  // lazily after first paint and fills the third status panel in place.
  await renderTopContracts(page.querySelector('#contracts-chart'), charts);

  revealOnScroll(page);
  return () => disposeCharts(charts);
}

// --- hero: England region silhouette -----------------------------------------

/* The hero's one visual risk: a real (if simplified) silhouette of England's
 * nine regions, shaded by the same "appears as a contract buyer" coverage
 * signal the snapshot cards already report nationally -- so darker is not
 * decoration, it is "more of this region's authorities show contract
 * evidence." Deliberately not the /geography page's live MapLibre workspace:
 * that fetches 14MB of full authority boundaries plus live basemap tiles
 * from a CDN, which is a reasonable cost for a page a reader chose to visit
 * and a bad one for the homepage's first paint. This fetches a ~60KB
 * pre-simplified region dissolve (scripts/generate_region_outline.py) and
 * draws it as plain inline SVG -- no map library, no network dependency
 * beyond the portal's own static file.
 */
const REGION_MAP_HEIGHT = 380;

function projectRing(ring, bbox, width, height) {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const points = ring.map(([lon, lat]) => {
    const x = (lon - minLon) / (maxLon - minLon) * width;
    const y = height - (lat - minLat) / (maxLat - minLat) * height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return `M ${points.join(' L ')} Z`;
}

function pathForGeometry(geometry, bbox, width, height) {
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;
  const parts = [];
  for (const polygon of polygons) {
    for (const ring of polygon) parts.push(projectRing(ring, bbox, width, height));
  }
  return parts.join(' ');
}

// Real England, not a naive lon/lat rectangle: a degree of longitude is
// shorter than a degree of latitude this far from the equator, and drawing
// both as equal units makes the country look wider and squatter than it is.
function viewBoxFor(bbox) {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const meanLatRad = (minLat + maxLat) / 2 * (Math.PI / 180);
  const aspect = ((maxLon - minLon) * Math.cos(meanLatRad)) / (maxLat - minLat);
  return { width: Math.round(REGION_MAP_HEIGHT * aspect), height: REGION_MAP_HEIGHT };
}

async function renderHeroMap(container, summary) {
  let shapes;
  try {
    const response = await fetch('/assets/england-regions.json');
    shapes = await response.json();
  } catch (error) {
    // Decorative: a failed fetch removes the visual rather than showing an
    // error card the hero has no room for.
    container.remove();
    return;
  }

  const density = new Map(
    (summary.authorities?.regions || []).map((r) => [r.region, r]));
  const fractions = [...density.values()]
    .map((r) => (r.authorities_total ? r.authorities_with_contracts / r.authorities_total : 0));
  const maxFraction = Math.max(...fractions, 0.0001);

  const { width, height } = viewBoxFor(shapes.meta.bbox);
  const paths = shapes.features.map((feature) => {
    const region = feature.properties.region;
    const row = density.get(region);
    const fraction = row?.authorities_total ? row.authorities_with_contracts / row.authorities_total : 0;
    const intensity = fraction / maxFraction;
    // Muted slate for genuinely zero coverage (rare, but distinct from "some
    // coverage, drawn pale") rather than the same hue at near-zero opacity,
    // which a reader could mistake for "no data" either way.
    const fill = fraction === 0 ? 'rgba(130, 147, 170, 0.25)'
      : `rgba(33, 212, 208, ${(0.18 + intensity * 0.62).toFixed(2)})`;
    return svgEl('path', {
      d: pathForGeometry(feature.geometry, shapes.meta.bbox, width, height),
      fill, stroke: '#08111f', 'stroke-width': '1',
    }, svgEl('title', { text: row
      ? `${region}: ${num(row.authorities_with_contracts)} of ${num(row.authorities_total)} authorities appear as a contract buyer (${pct(fraction)})`
      : `${region}: no coverage data` }));
  });

  const sorted = [...density.values()].filter((r) => r.authorities_total)
    .sort((a, b) => (b.authorities_with_contracts / b.authorities_total) - (a.authorities_with_contracts / a.authorities_total));
  const best = sorted[0];
  const worst = sorted[sorted.length - 1];
  const ariaLabel = best && worst
    ? `Map of England's nine regions, shaded by the share of local authorities `
      + `that appear as a contract buyer. Highest: ${best.region} at `
      + `${pct(best.authorities_with_contracts / best.authorities_total)}. `
      + `Lowest: ${worst.region} at ${pct(worst.authorities_with_contracts / worst.authorities_total)}.`
    : `Map of England's nine regions, shaded by contract-buyer coverage.`;

  replace(container,
    svgEl('svg', {
      viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': ariaLabel,
      class: 'hero-map-svg',
    }, paths),
    el('p', { class: 'hero-map-caption small muted',
      text: 'Share of local authorities appearing as a contract buyer, by region.' }));
}

/** A `<strong>` that counts up to `value` on first paint rather than
 *  appearing pre-filled. Purely a presentation flourish on the strip's own
 *  numbers -- it reads the same value `num()` would have rendered outright,
 *  it just gets there over a few frames. A missing value renders as the
 *  usual em dash, unanimated, because there is nothing to count up to. */
function countUpMetric(value) {
  const n = Number(value);
  if (value === null || value === undefined || Number.isNaN(n)) {
    return el('strong', { text: '—' });
  }
  return el('strong', { text: '0', 'data-count-target': String(n) });
}

/** Runs every `[data-count-target]` inside `root` from 0 to its target over
 *  ~900ms with an ease-out curve. Skipped for reduced motion -- the number is
 *  set to its final value immediately rather than left at 0. */
function animateCounts(root) {
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  for (const node of root.querySelectorAll('[data-count-target]')) {
    const target = Number(node.dataset.countTarget);
    if (reduceMotion || !Number.isFinite(target)) {
      node.textContent = num(target);
      continue;
    }
    const duration = 900;
    const start = performance.now();
    const step = (now) => {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - progress) ** 3;
      node.textContent = num(Math.round(target * eased));
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
}

function renderBriefingStrip(container, summary) {
  const sources = summary.pipeline?.sources || [];
  const retrieved = sources.map((s) => s.last_retrieved).filter(Boolean).sort().pop() || null;
  const signalCount = [summary.contracts?.total_notices, summary.providers?.total,
    summary.funnel?.evidence_rows].filter((value) => Number(value) > 0).length;
  replace(container, el('section', { class: 'evidence-strip', 'aria-label': 'Evidence briefing' },
    el('div', { class: 'evidence-strip-head' },
      el('div', {}, el('span', { class: 'eyebrow' }, 'Evidence briefing'),
        el('h2', { text: 'The campaign view, at a glance' })),
      timingBadge({ kind: retrieved ? 'current' : 'snapshot', date: retrieved ? retrieved.slice(0, 10) : null })),
    el('div', { class: 'evidence-strip-grid' },
      el('div', {}, countUpMetric(summary.funnel?.evidence_rows), el('span', { text: ' verified evidence rows' })),
      el('div', {}, countUpMetric(summary.contracts?.total_notices), el('span', { text: ' procurement notices indexed' })),
      el('div', {}, countUpMetric(summary.providers?.total), el('span', { text: ' providers tracked' })),
      // Same "matched to a known provider" measure as the contracts page, in
      // place of a count of how many layers happened to be non-zero.
      el('div', {}, countUpMetric(summary.contracts?.matched_to_provider), el('span', { text: ' matched to a known provider' }))),
    el('p', { class: 'small muted', text: retrieved
      ? `Scope: England-wide public evidence. Latest source retrieval: ${retrieved.slice(0, 10)}.`
      : 'Scope: England-wide public evidence. Retrieval timing is not available in this extract.' }),
    findingBlock({
      finding: signalCount ? 'The portal has a usable evidence base across coverage, procurement, and provider layers; each layer still needs to be read with its own caveats.' : null,
      value: `${num(summary.funnel?.evidence_rows)} verified rows`, evidenceStatus: signalCount ? 'Supported' : null,
      timing: { kind: retrieved ? 'current' : 'snapshot', date: retrieved ? retrieved.slice(0, 10) : null },
      caveat: 'Coverage counts describe what is held and reviewed, not the quality or outcome of a service.',
      sources: sources.map((s) => SOURCE_LABELS[s.source_system] || s.source_system).filter(Boolean),
      retrievedAt: retrieved ? retrieved.slice(0, 10) : null,
    })));
  animateCounts(container);
}

function renderCards(container, summary) {
  const contracts = summary.contracts || {};
  const workforce = summary.workforce || {};
  const concentrated = contracts.value_is_concentrated;

  const snapshotCard = (config) => statCard({
    ...config,
    action: shareButton({
      title: `SectorTrace: ${config.label}`,
      text: `${config.value} ${config.label}. Evidence status: ${config.status || 'not stated'}.`,
      label: `Share ${config.label}`,
    }),
  });
  const coverage = [
    snapshotCard({
      value: num(summary.authorities?.total),
      label: 'local authorities tracked',
      sub: `${num(summary.authorities?.with_contracts)} appear as a contract buyer`,
      status: summary.authorities?.total ? 'Tracked' : 'Not collected',
      statusClass: summary.authorities?.total ? 'good' : 'neutral',
    }),
    snapshotCard({
      value: num(contracts.total_notices),
      label: 'procurement notices indexed',
      sub: 'award and contract notices matching the sector keyword set',
      caveat: contracts.caveat,
      status: contracts.total_notices ? 'Indexed' : 'Not collected',
      statusClass: contracts.total_notices ? 'good' : 'neutral',
    }),
    snapshotCard({
      value: num(summary.providers?.total),
      label: 'providers tracked',
      sub: summary.providers?.target ? `Campaign subject: ${summary.providers.target}` : null,
      status: summary.providers?.total ? 'Tracked' : 'Not collected',
      statusClass: summary.providers?.total ? 'good' : 'neutral',
    }),
  ];

  const evidenceQuality = [snapshotCard({
    value: num(summary.funnel?.evidence_rows),
    label: 'human-verified evidence rows',
    sub: 'documents promoted into the evidence base after review',
    caveat: summary.funnel?.caveat,
    status: summary.funnel?.evidence_rows ? 'Human-verified' : 'Not collected',
    statusClass: summary.funnel?.evidence_rows ? 'good' : 'neutral',
  })];

  // The value card, shaped by what the corpus actually supports.
  if (concentrated) {
    evidenceQuality.push(snapshotCard({
      value: 'not a total',
      plain: true,
      label: 'contract value',
      sub: 'dominated by framework ceilings — see Contracts',
      caveat: contracts.sum_caveat,
      status: 'Caveated',
      statusClass: 'neutral',
    }));
  } else {
    evidenceQuality.push(snapshotCard({
      value: gbp(contracts.total_value_gbp),
      label: 'total contract value',
      caveat: contracts.caveat,
      status: contracts.total_value_gbp == null ? 'Missing' : 'Published',
      statusClass: contracts.total_value_gbp == null ? 'neutral' : 'good',
    }));
  }

  // Workforce: shown, but never as a clean headline while unverified.
  const sectorContext = [];
  const metrics = workforce.metrics || [];
  const pick = (name) => metrics.find((m) => m.metric === name);
  for (const [metric, label] of [['vacancy_rate', 'vacancy rate'],
    ['turnover_rate', 'turnover rate']]) {
    const row = pick(metric);
    if (!row) {
      sectorContext.push(snapshotCard({
        value: '—', plain: true, label: `sector ${label}`,
        sub: 'not collected yet — run m06_workforce_census',
        status: 'Not collected', statusClass: 'neutral',
      }));
      continue;
    }
    sectorContext.push(snapshotCard({
      value: `${row.value}${row.unit === 'percent' ? '%' : ''}`,
      plain: !row.verified,
      label: `sector ${label} (${workforce.latest_census_year})`,
      sub: row.workforce_segment ? `segment: ${row.workforce_segment}` : null,
      unverified: !row.verified,
      caveat: workforce.caveat,
      status: row.verified ? 'Human-verified' : 'Unverified',
      statusClass: row.verified ? 'good' : 'unverified',
    }));
  }

  const band = (title, description, cards) => el('section', { class: 'snapshot-band' },
    el('header', {}, el('h3', { text: title }), el('p', { text: description })),
    el('div', { class: 'grid cards' }, cards));

  replace(container, section(
    'Current snapshot',
    'A quick view of the evidence held today. These figures describe coverage and publication state; they are not a composite score.',
    el('div', { class: 'snapshot-bands' },
      band('Coverage', 'What the portal currently tracks across places, notices, and providers.', coverage),
      band('Evidence quality', 'What has been reviewed and which headline values need careful interpretation.', evidenceQuality),
      band('Sector context', 'Published workforce context, kept separate from the coverage counts above.', sectorContext))));
}

// Same lens classification app.js stamps onto each route's page-top cue
// (`lensByRoute` in app.js), repeated here rather than imported: it is
// presentation metadata about where a route sits in the campaign's argument,
// not evidence, and the card's accent colour is the only place on this page
// that reads it. Set as an inline custom property rather than a `lens-*`
// class -- that class name is already `.lens-accountability` etc. on the
// hero-kicker badge (components.js's lensBadge()), styled bare rather than
// scoped to the badge, and reusing it here would pull that styling onto
// two of these five cards.
const EXPLORE_LENS = {
  '#/pay': ['--accent-green', 'Workforce'],
  '#/contracts': ['--accent-amber', 'Public money'],
  '#/geography': ['--accent-teal', 'Service access'],
  '#/providers': ['--accent-teal', 'Service access'],
  '#/treatment': ['--accent-teal', 'Service access'],
  '#/pfd': ['--accent-red', 'Safety & legal'],
  '#/claims': ['--accent-purple', 'Accountability'],
  '#/documents': ['--accent-purple', 'Accountability'],
};

function renderExplore(container) {
  const routes = [
    ['#/pay', 'Pay & benchmarks', 'Follow the workforce story from published pay to labour-market context.'],
    ['#/contracts', 'Funding & contracts', 'See buyers, providers, notice values, and procurement patterns.'],
    ['#/geography', 'Places', 'Choose a metric, explore local evidence, and open an authority page.'],
    ['#/providers', 'Providers', 'Browse provider evidence across pay, contracts, claims, and safety.'],
    ['#/treatment', 'Treatment data', 'Understand demand and activity figures with their uncertainty and limits.'],
    ['#/pfd', 'Safety & legal', 'Explore coroners’ reports, concerns, and provider mentions responsibly.'],
    ['#/claims', 'Evidence-backed claims', 'Find campaign-ready claims with the evidence behind them.'],
    ['#/documents', 'Document search', 'Search the text of published committee papers and partnership documents.'],
  ];
  const routeCards = [];
  for (const route of routes) {
    const href = route[0];
    const title = route[1];
    const description = route[2];
    const [lensVar, lensLabel] = EXPLORE_LENS[href] || ['--accent-teal', 'Evidence'];
    routeCards.push(el('a', { class: 'explore-card', style: `--lens: var(${lensVar})`, href },
      el('span', { class: 'explore-card-lens', text: lensLabel }),
      el('span', { class: 'explore-card-title', text: title }),
      el('span', { class: 'explore-card-description', text: description }),
      el('span', { class: 'explore-card-arrow', 'aria-hidden': 'true', text: '→' })));
  }
  replace(container, section(
    'Explore the evidence',
    'Choose a question to move from the snapshot into the evidence layer that can answer it.',
    el('div', { class: 'grid explore-grid' }, routeCards)));
}

function statusKey() {
  return el('div', { class: 'status-key', 'aria-label': 'Evidence status key' },
    el('span', { class: 'small muted', text: 'Status key' }),
    el('span', { class: 'badge good', text: 'Published / indexed' }),
    el('span', { class: 'badge unverified', text: 'Unverified' }),
    el('span', { class: 'badge neutral', text: 'Not collected / missing' }));
}

function renderEvidenceStatus(container, summary) {
  const freshness = el('div', { class: 'panel status-panel', id: 'freshness-panel' },
    el('h3', { text: 'Freshness' }),
    el('p', { class: 'small muted', text: 'Loading source updates…' }));
  replace(container, section(
    'Evidence status',
    'Where the evidence comes from, how much has been verified, and when each source layer was last written.',
    statusKey(),
    el('div', { class: 'grid evidence-status-grid' },
      renderSourcesPanel(summary),
      renderFunnelPanel(summary.funnel),
      freshness)));
  renderFreshnessPanel(freshness);
}

function renderSourcesPanel(summary) {
  const sources = summary.pipeline?.sources || [];
  const chips = sources.map((s) => el('div', { class: 'sourcechip' },
    el('span', { class: `dot ${s.last_retrieved ? 'green' : ''}` }),
    el('span', { text: SOURCE_LABELS[s.source_system] || s.source_system }),
    el('span', { class: 'muted small', text: ago(s.last_retrieved) })));

  return el('div', { class: 'panel status-panel' },
    el('h3', { text: 'Sources and latest updates' }),
    el('p', { class: 'small muted', text: 'Each source system, and when the pipeline last fetched from it.' }),
    el('details', { class: 'source-details' },
      el('summary', { text: chips.length ? `View ${num(chips.length)} source updates` : 'View source updates' }),
      el('div', { class: 'sourcestrip' }, chips.length ? chips
        : el('span', { class: 'muted', text: 'Nothing collected yet.' }))),
    el('p', { class: 'small muted status-footnote' },
      `Fingertips: ${num(summary.fingertips?.indicators_collected)} indicators, `
      + `latest period ${summary.fingertips?.latest_period || '—'}.`));
}

/* W-26: the verification funnel. Drawn as bars with the count as a label so
 * that a zero is visibly a zero -- an empty chart reads as "no data", which
 * is exactly the wrong reading for the campaign's standing argument. */
function renderFunnelPanel(funnel) {
  if (!funnel) return el('div', { class: 'panel status-panel' },
    el('h3', { text: 'Verification progress' }),
    el('p', { class: 'small muted', text: 'No verification summary is available.' }));
  const stages = [
    ['discovered', 'discovered', 'candidates found by the modules'],
    ['undecided', 'undecided', 'waiting for a human decision'],
    ['promoted', 'promoted', 'verified by a named person'],
    ['evidence_rows', 'evidence rows', 'verified documents in the evidence base'],
  ];
  const max = Math.max(...stages.map(([key]) => funnel[key] || 0), 1);
  const rows = stages.map(([key, label, sub]) => {
    const value = funnel[key] || 0;
    return el('div', { class: 'flowrow' },
      el('div', { class: 'flowlabel' },
        el('span', { text: label }),
        el('span', { class: 'flowvalue', text: num(value) })),
      el('div', { class: 'flowbar', role: 'img',
        'aria-label': `${label}: ${num(value)}` },
        el('div', { class: 'flowbar-fill', style: `width: ${Math.round(value / max * 100)}%` })),
      el('div', { class: 'small muted', text: sub }));
  });

  return el('div', { class: 'panel status-panel' },
    el('h3', { text: 'From candidate to evidence' }),
    el('p', { class: 'small muted' }, 'How much of what the modules found has been verified by a person. '
    + 'Rejected candidates are the difference between discovered and the '
    + 'rest of the funnel.'),
    funnel.caveat ? pinnedCaveat(funnel.caveat, 'A zero here means') : null,
    el('div', { class: 'flowrows' }, rows));
}

/* W-26: how fresh each source table is, per the rows' own retrieval stamps.
 * The payload is fetched lazily (it is seconds of scans) and the bars use
 * the same ago() helper as the sources strip. "Never" is drawn as a full
 * muted track, never as a zero. */
async function renderFreshnessPanel(container) {
  let data;
  try {
    data = await fetchJSON('freshness');
  } catch (error) {
    replace(container,
      el('h3', { text: 'Freshness' }),
      el('p', { class: 'small muted', text: `Could not load: ${error.message}` }));
    return;
  }

  const days = (stamp) => {
    if (!stamp) return null;
    const then = new Date(stamp).getTime();
    if (Number.isNaN(then)) return null;
    return Math.max(0, Math.round((Date.now() - then) / 86400000));
  };
  const rows = (data.tables || []).map((t) => ({ ...t, days: days(t.retrieved_at) }));
  const maxDays = Math.max(...rows.map((r) => r.days || 0), 1);

  const bars = rows.map((t) => el('div', { class: 'flowrow' },
    el('div', { class: 'flowlabel' },
      el('span', { text: t.label }),
      el('span', { class: 'flowvalue', text: t.days === null ? 'never' : ago(t.retrieved_at) })),
    el('div', { class: 'flowbar', role: 'img',
      'aria-label': `${t.label}: ${t.days === null ? 'never collected' : `${t.days} days ago`}` },
      t.days === null
        ? el('div', { class: 'flowbar-fill never', style: 'width: 100%' })
        : el('div', { class: 'flowbar-fill', style: `width: ${Math.round(t.days / maxDays * 100)}%` }))));

  replace(container,
    el('h3', { text: 'Freshness' }),
    el('p', { class: 'small muted' }, 'Days since each source table was last written. A table that has never been collected is drawn as “never”, not as zero.'),
    data.caveat ? pinnedCaveat(data.caveat, 'Read before comparing tables') : null,
    el('div', { class: 'flowrows' }, bars));
}

async function renderTopContracts(container, charts) {
  let data;
  try {
    data = await fetchJSON('contracts', { limit: 500 });
  } catch (error) {
    replace(container, errorCard(error.message));
    return;
  }

  const concentration = data.value_concentration || {};
  const matchedLargest = data.largest_matched_to_provider || [];
  const largest = matchedLargest.slice(0, 5).reverse();
  const tableRows = matchedLargest.slice(0, 5);

  const holder = el('div', {});
  const valueCaveat = data.caveats?.value_sum
    || 'Published notice values can include framework ceilings and are not a measure of sector spend.';
  const providerCaveat = data.caveats?.provider_match;

  replace(container, section(
    'The largest notices in the corpus',
    'Five highest published values, limited to notices matched to a tracked '
    + 'provider by exact supplier name. Read the caveats before treating '
    + 'any of these as sector spend.',
    pinnedCaveat(valueCaveat, 'Important limitation'),
    providerCaveat ? pinnedCaveat(providerCaveat, 'Matching is a floor') : null,
    findingBlock({
      finding: 'The largest notices matched to a tracked provider are useful for locating procurement activity, but their headline values should not be read as sector spend.',
      value: `Median notice (all notices) ${gbp(concentration.median_value_gbp, { compact: false })}`,
      evidenceStatus: 'Published', timing: { kind: 'current', date: (data.notices || []).map((n) => n.retrieved_at).filter(Boolean).sort().pop()?.slice(0, 10) },
      caveat: valueCaveat, sources: ['Contracts Finder'],
      retrievedAt: (data.notices || []).map((n) => n.retrieved_at).filter(Boolean).sort().pop()?.slice(0, 10),
    }),
    el('div', { class: 'panel' },
      el('p', { class: 'small muted' },
        `Corpus-wide: median notice ${gbp(concentration.median_value_gbp, { compact: false })} · `,
        `mean ${gbp(concentration.mean_value_gbp)} · `,
        `${num(concentration.notices_over_1bn)} notices above £1bn carry `,
        `${pct(concentration.share_over_1bn)} of the total`),
      holder,
      el('details', { class: 'chart-data' },
        el('summary', { text: `View data (${num(tableRows.length)} notices)` }),
        tableCard('Largest published notices matched to a provider', [
          { title: 'Provider', field: 'canonical_name' },
          { title: 'Buyer', field: 'buyer_name' },
          { title: 'Notice', field: 'title' },
          { title: 'Published value', field: 'value_display', width: 150 },
          { title: 'Notice ID', field: 'notice_id', width: 150 },
        ], tableRows.map((notice) => ({
          canonical_name: notice.canonical_name || '—',
          buyer_name: notice.buyer_name || 'Not published',
          title: notice.title || 'Untitled notice',
          value_display: gbp(notice.value_core, { compact: false }),
          notice_id: notice.notice_id || '—',
        })), { height: 300, total: tableRows.length })),
      provenance({
        sources: (data.notices || []).map((n) => n.source_url),
        retrievedAt: (data.notices || []).map((n) => n.retrieved_at).sort().pop(),
        tables: ['contracts', 'supplier_aliases'],
        module: 'm01_procurement',
      }))));

  if (!largest.length) {
    replace(holder, noData('procurement notices', './start.sh run m01_procurement'));
    return;
  }

  charts.push(mountChart(holder, {
    grid: { left: 8, right: 32, top: 16, bottom: 8, containLabel: true },
    xAxis: {
      type: 'log', name: 'published value (£, log scale)', nameLocation: 'middle',
      nameGap: 32, min: 1000,
    },
    yAxis: {
      type: 'category',
      data: largest.map((n) => truncate(n.canonical_name || n.buyer_name || n.notice_id, 32)),
    },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const row = largest[params[0].dataIndex];
        return [
          `<strong>${escapeHtml(row.canonical_name || '')}</strong>`,
          escapeHtml(row.buyer_name || ''),
          escapeHtml(truncate(row.title || '', 80)),
          `<strong>${gbp(row.value_core, { compact: false })}</strong>`,
        ].join('<br>');
      },
    },
    series: [{
      type: 'bar',
      data: largest.map((n) => n.value_core),
      itemStyle: {
        // Billion-pound notices are the distortion, so they are coloured as a
        // warning rather than blended into the same ramp as everything else.
        color: (p) => (largest[p.dataIndex].value_core > 1e9 ? '#f59e0b' : '#38bdf8'),
      },
    }],
  }, {
    height: 'tall',
    aria: `Bar chart of the five highest-value procurement notices matched to `
      + `a tracked provider by exact supplier name. Matching is a floor, so `
      + `this is not the five highest-value notices in the whole corpus.`,
  }));
}

