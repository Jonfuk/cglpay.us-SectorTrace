/* Overview — what is in the corpus, and what it is not.
 *
 * The hero cards are deliberately conservative. Two of the figures the brief
 * asked for at the top of this page cannot honestly be headline numbers
 * against the current warehouse, and the page says so instead of rendering
 * them anyway:
 *
 *   * Sector vacancy and turnover rates. All 68 workforce census metrics are
 *     `verified = 0`, and the pipeline's own caveats say to filter on that
 *     before publishing. They appear, marked as awaiting verification.
 *
 *   * Total contract value. A handful of cross-government framework notices
 *     carry ceilings in the tens of billions, so the sum is not a figure about
 *     this sector at all. The card shows the median notice instead, with the
 *     total and its concentration a click away.
 */
'use strict';

import { el, replace, fetchJSON, num, gbp, pct, ago } from '/app.js';
import { statCard, section, caveat, noData, errorCard, mountChart,
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
    el('div', { id: 'contracts-chart' }));
  replace(main, page);

  renderCards(cards, summary);
  renderSources(page.querySelector('#sources'), summary);
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

