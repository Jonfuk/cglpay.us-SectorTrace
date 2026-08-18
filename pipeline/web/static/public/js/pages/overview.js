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

import { el, replace, fetchJSON, num, gbp, pct, ago } from '/app.js';
import { statCard, section, pinnedCaveat, noData, errorCard, mountChart,
          disposeCharts, provenance, truncate, escapeHtml, shareButton, tableCard } from '/js/components.js';

const SOURCE_LABELS = {
  contracts_finder: 'Contracts Finder',
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

  const snapshot = el('div', {});
  const page = el('div', {},
    el('div', { class: 'hero' },
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
    el('div', { id: 'snapshot' }),
    el('div', { id: 'explore' }),
    el('div', { id: 'evidence-status' }),
    el('div', { id: 'contracts-chart' }));
  replace(main, page);

  renderCards(snapshot, summary);
  renderExplore(page.querySelector('#explore'));
  renderEvidenceStatus(page.querySelector('#evidence-status'), summary);
  // Freshness is seconds of table scans, so renderEvidenceStatus fetches it
  // lazily after first paint and fills the third status panel in place.
  await renderTopContracts(page.querySelector('#contracts-chart'), charts);

  return () => disposeCharts(charts);
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

function renderExplore(container) {
  const routes = [
    ['#/pay', 'Pay & benchmarks', 'Follow the workforce story from published pay to labour-market context.'],
    ['#/contracts', 'Funding & contracts', 'See buyers, providers, notice values, and procurement patterns.'],
    ['#/geography', 'Places', 'Choose a metric, explore local evidence, and open an authority page.'],
    ['#/providers', 'Providers', 'Browse provider evidence across pay, contracts, claims, and safety.'],
    ['#/treatment', 'Treatment data', 'Understand demand and activity figures with their uncertainty and limits.'],
    ['#/pfd', 'Safety & legal', 'Explore coroners’ reports, concerns, and provider mentions responsibly.'],
    ['#/claims', 'Evidence-backed claims', 'Find campaign-ready claims with the evidence behind them.'],
  ];
  const routeCards = [];
  for (const route of routes) {
    const href = route[0];
    const title = route[1];
    const description = route[2];
    routeCards.push(el('a', { class: 'explore-card', href },
      el('span', { class: 'explore-card-title', text: title }),
      el('span', { class: 'explore-card-description', text: description }),
      el('span', { class: 'explore-card-arrow', 'aria-hidden': 'true', text: 'Open route' })));
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
  const largest = (concentration.largest || []).slice(0, 10).reverse();
  const tableRows = (concentration.largest || []).slice(0, 10);

  const holder = el('div', {});
  const valueCaveat = data.caveats?.value_sum
    || 'Published notice values can include framework ceilings and are not a measure of sector spend.';

  replace(container, section(
    'The largest notices in the corpus',
    'Ten highest published values. Read the caveat before treating any of '
    + 'these as sector spend.',
    pinnedCaveat(valueCaveat, 'Important limitation'),
    el('div', { class: 'panel' },
      el('p', { class: 'small muted' },
        `Median notice ${gbp(concentration.median_value_gbp, { compact: false })} · `,
        `mean ${gbp(concentration.mean_value_gbp)} · `,
        `${num(concentration.notices_over_1bn)} notices above £1bn carry `,
        `${pct(concentration.share_over_1bn)} of the total`),
      holder,
      el('details', { class: 'chart-data' },
        el('summary', { text: `View data (${num(tableRows.length)} notices)` }),
        tableCard('Largest published notices', [
          { title: 'Buyer', field: 'buyer_name' },
          { title: 'Notice', field: 'title' },
          { title: 'Published value', field: 'value_display', width: 150 },
          { title: 'Notice ID', field: 'notice_id', width: 150 },
        ], tableRows.map((notice) => ({
          buyer_name: notice.buyer_name || 'Not published',
          title: notice.title || 'Untitled notice',
          value_display: gbp(notice.value_core, { compact: false }),
          notice_id: notice.notice_id || '—',
        })), { height: 360, total: tableRows.length })),
      provenance({
        sources: (data.notices || []).map((n) => n.source_url),
        retrievedAt: (data.notices || []).map((n) => n.retrieved_at).sort().pop(),
        tables: ['contracts'],
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
      data: largest.map((n) => truncate(n.buyer_name || n.notice_id, 32)),
    },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const row = largest[params[0].dataIndex];
        return [
          `<strong>${escapeHtml(row.buyer_name || '')}</strong>`,
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
    aria: `Bar chart of the ten highest-value procurement notices. `
      + `${num(concentration.notices_over_1bn)} notices above one billion pounds `
      + `account for ${pct(concentration.share_over_1bn)} of the total value, `
      + `and are cross-government framework ceilings rather than sector spend.`,
  }));
}

