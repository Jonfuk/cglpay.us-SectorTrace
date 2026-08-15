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
import { statCard, section, caveat, pinnedCaveat, noData, errorCard, mountChart,
          disposeCharts, provenance, truncate, escapeHtml } from '/js/components.js';

export async function render(main) {
  const charts = [];
  let summary;
  try {
    summary = await fetchJSON('summary');
  } catch (error) {
    replace(main, errorCard(error.message, () => render(main)));
    return () => {};
  }

  const cards = el('div', { class: 'grid cards' });
  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'England-wide evidence on substance misuse treatment' }),
      el('p', { class: 'lede' },
        'A standing evidence base for the drug and alcohol treatment sector, ',
        'assembled from public-domain sources. ',
        el('strong', { text: 'Nothing here is inferred or defaulted' }),
        ': a value that could not be parsed is empty with a logged reason, ',
        'and every figure carries the document it came from.'),
      cards),
    el('div', { id: 'sources' }),
    el('div', { id: 'funnel' }),
    el('div', { id: 'freshness' }),
    el('div', { id: 'contracts-chart' }));
  replace(main, page);

  renderCards(cards, summary);
  renderSources(page.querySelector('#sources'), summary);
  renderFunnel(page.querySelector('#funnel'), summary.funnel);
  // Freshness is seconds of table scans, so it is fetched lazily after first
  // paint and rendered in place when it arrives; the rest of the page does
  // not wait for it. See the comment on the route in server.py.
  renderFreshness(page.querySelector('#freshness'));
  await renderTopContracts(page.querySelector('#contracts-chart'), charts);

  return () => disposeCharts(charts);
}

function renderCards(container, summary) {
  const contracts = summary.contracts || {};
  const workforce = summary.workforce || {};
  const concentrated = contracts.value_is_concentrated;

  const cards = [
    statCard({
      value: num(summary.authorities?.total),
      label: 'local authorities tracked',
      sub: `${num(summary.authorities?.with_contracts)} appear as a contract buyer`,
    }),
    statCard({
      value: num(contracts.total_notices),
      label: 'procurement notices indexed',
      sub: 'award and contract notices matching the sector keyword set',
      caveat: contracts.caveat,
    }),
    statCard({
      value: num(summary.providers?.total),
      label: 'providers tracked',
      sub: summary.providers?.target ? `Campaign subject: ${summary.providers.target}` : null,
    }),
  ];

  // The value card, shaped by what the corpus actually supports.
  if (concentrated) {
    cards.push(statCard({
      value: 'not a total',
      plain: true,
      label: 'contract value',
      sub: 'dominated by framework ceilings — see Contracts',
      caveat: contracts.sum_caveat,
    }));
  } else {
    cards.push(statCard({
      value: gbp(contracts.total_value_gbp),
      label: 'total contract value',
      caveat: contracts.caveat,
    }));
  }

  // Workforce: shown, but never as a clean headline while unverified.
  const metrics = workforce.metrics || [];
  const pick = (name) => metrics.find((m) => m.metric === name);
  for (const [metric, label] of [['vacancy_rate', 'vacancy rate'],
    ['turnover_rate', 'turnover rate']]) {
    const row = pick(metric);
    if (!row) {
      cards.push(statCard({
        value: '—', plain: true, label: `sector ${label}`,
        sub: 'not collected yet — run m06_workforce_census',
      }));
      continue;
    }
    cards.push(statCard({
      value: `${row.value}${row.unit === 'percent' ? '%' : ''}`,
      plain: !row.verified,
      label: `sector ${label} (${workforce.latest_census_year})`,
      sub: row.workforce_segment ? `segment: ${row.workforce_segment}` : null,
      unverified: !row.verified,
      caveat: workforce.caveat,
    }));
  }

  replace(container, cards);
}

function renderSources(container, summary) {
  const sources = summary.pipeline?.sources || [];
  const chips = sources.map((s) => el('div', { class: 'sourcechip' },
    el('span', { class: `dot ${s.last_retrieved ? 'green' : ''}` }),
    el('span', { class: 'mono', text: s.source_system }),
    el('span', { class: 'muted small', text: ago(s.last_retrieved) })));

  replace(container, section(
    'What has been collected',
    'Each source system, and when the pipeline last fetched from it.',
    el('div', { class: 'sourcestrip' }, chips.length ? chips
      : el('span', { class: 'muted', text: 'Nothing collected yet.' })),
    el('p', { class: 'small muted' },
      `Fingertips: ${num(summary.fingertips?.indicators_collected)} indicators, `
      + `latest period ${summary.fingertips?.latest_period || '—'}.`)));
}

/* W-26: the verification funnel. Drawn as bars with the count as a label so
 * that a zero is visibly a zero -- an empty chart reads as "no data", which
 * is exactly the wrong reading for the campaign's standing argument. */
function renderFunnel(container, funnel) {
  if (!funnel) return;
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

  replace(container, section(
    'From candidate to evidence',
    'How much of what the modules found has been verified by a person. '
    + 'Rejected candidates are the difference between discovered and the '
    + 'rest of the funnel.',
    el('div', { class: 'panel' },
      funnel.caveat ? pinnedCaveat(funnel.caveat, 'A zero here means') : null,
      el('div', { class: 'flowrows' }, rows))));
}

/* W-26: how fresh each source table is, per the rows' own retrieval stamps.
 * The payload is fetched lazily (it is seconds of scans) and the bars use
 * the same ago() helper as the sources strip. "Never" is drawn as a full
 * muted track, never as a zero. */
async function renderFreshness(container) {
  let data;
  try {
    data = await fetchJSON('freshness');
  } catch (error) {
    replace(container, section('How fresh the evidence is',
      'Days since each source table was last written by a pipeline run.',
      el('p', { class: 'small muted', text: `Could not load: ${error.message}` })));
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

  replace(container, section(
    'How fresh the evidence is',
    'Days since each source table was last written. A table that has never '
    + 'been collected is drawn as \'never\', not as zero.',
    el('div', { class: 'panel' },
      data.caveat ? pinnedCaveat(data.caveat, 'Read before comparing tables') : null,
      el('div', { class: 'flowrows' }, bars))));
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

  const holder = el('div', {});
  const note = caveat(data.caveats?.value_sum);

  replace(container, section(
    'The largest notices in the corpus',
    'Ten highest published values. Read the caveat before treating any of '
    + 'these as sector spend.',
    el('div', { class: 'panel' },
      el('p', { class: 'small muted' },
        `Median notice ${gbp(concentration.median_value_gbp, { compact: false })} · `,
        `mean ${gbp(concentration.mean_value_gbp)} · `,
        `${num(concentration.notices_over_1bn)} notices above £1bn carry `,
        `${pct(concentration.share_over_1bn)} of the total`,
        note ? note.button : null),
      note ? note.body : null,
      holder,
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

