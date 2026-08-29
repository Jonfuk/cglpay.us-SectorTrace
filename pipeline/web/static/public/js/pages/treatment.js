/* Treatment demand and outcomes, from OHID Fingertips and NDTMS.
 *
 * The note that matters is the one about unmet need. Prevalence estimates and
 * treatment numbers come from different methods and different populations, and
 * subtracting one from the other produces a number this pipeline will not
 * publish. It is stated on the page rather than left in a document nobody
 * opens.
 *
 * The NDTMS section below has a second rule of its own: every figure in it is
 * a modelled estimate published with a 95% confidence interval, so nothing is
 * drawn as a bare point. An estimate whose bounds could not be paired to it
 * with certainty is drawn hollow and counted in the line under the chart --
 * visibly missing an interval rather than quietly appearing to have none.
 */
'use strict';

import { el, replace, fetchJSON, setFilterResultCount, num, isoDate, typeaheadKeyboard } from '/app.js';
import { section, pinnedCaveat, caveat, noData, errorCard, mountChart,
          disposeCharts, provenanceFromRows, tableCard, symbolFor, escapeHtml,
          exportButton, shareButton, findingBlock, evidenceMeta, evidenceHealthStrip } from '/js/components.js';

const TOPICS = [
  ['numbers_in_treatment', 'Numbers in treatment'],
  ['successful_completions', 'Successful completions'],
  ['waiting_times', 'Waiting times'],
  ['prevalence', 'Prevalence'],
  ['treatment_need', 'Treatment need'],
  ['harm', 'Harm'],
];

export async function render(main) {
  const charts = [];
  const state = { topic: 'numbers_in_treatment', ons: null };

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Understand treatment data' }),
      el('p', { class: 'lede' },
        'Explore published treatment indicators by local authority and against '
        + 'the England figure. Demand, activity and outcomes remain separate measures.'),
      el('div', { class: 'hero-actions' },
        shareButton({
          title: 'SectorTrace treatment data',
          text: 'Explore published treatment indicators in SectorTrace.',
          label: 'Share this view',
        }))),
    el('details', { class: 'read-first' },
      el('summary', { text: 'What treatment data can answer' }),
      el('p', { text: 'The figures show published indicators and estimates. They cannot show unmet need by subtracting one measure from another.' }),
      el('p', { text: 'A blank, suppressed value, or missing confidence interval is not zero and is shown separately from a published value.' })),
    el('div', { id: 'evidence-health' }),
    el('div', { id: 'metric-catalogue' }),
    el('div', { id: 'ft' }),
    el('div', { id: 'ndtms' }));
  replace(main, page);

  // BETA-084: the standardised evidence-health strip. Filled after the first
  // fingertips load so it can show the latest retrieval; verification is not
  // applicable to a published statistic, and coverage is partial by design
  // (only local authorities with a public health role publish).
  const healthSlot = page.querySelector('#evidence-health');
  replace(healthSlot, evidenceHealthStrip({
    scope: 'OHID Fingertips and NDTMS treatment indicators, by English local authority, against the England figure.',
    retrievedAt: null,
    verification: 'n/a',
    coverage: 'partial',
    licence: { name: 'Open Government Licence v3.0', url: 'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/' },
    limitation: 'Unmet need cannot be derived by subtracting one measure from another; missing periods are shown as missing, never zero.',
    catalogueSlug: 'fingertips',
  }));

  // BETA-075: the metric catalogue comes before the chart. It exposes what a
  // metric is, its unit, whether a 95% CI is published, the exact periods it
  // holds, its authority/England coverage and its provenance — so choosing a
  // technically named indicator is no longer the entry price to understanding
  // the page.
  renderMetricCatalogue(page.querySelector('#metric-catalogue'), (topic) => {
    if (topic) { state.topic = topic; load(); }
    page.querySelector('#ft')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  const tabs = el('div', { class: 'metrictabs' });
  const areaInput = el('input', {
    type: 'search', id: 'treatment-area', placeholder: 'All authorities',
    'aria-label': 'Local authority', autocomplete: 'off', role: 'combobox',
    'aria-expanded': 'false', 'aria-controls': 'treatment-area-list',
  });
  const areaList = el('ul', { id: 'treatment-area-list', class: 'typeahead-list',
    hidden: true, role: 'listbox' });
  const chartHolder = el('div', {});
  const tableHolder = el('div', {});
  const provHolder = el('div', {});
  const exportHolder = el('span', {});
  const guideHolder = el('div', {});

  replace(page.querySelector('#ft'), section(
    'Choose an indicator and authority',
    'Start with national context, then select an authority for its local series.',
    el('div', { class: 'panel' },
      tabs,
      el('div', { style: 'display:flex;gap:12px;align-items:center;margin-bottom:12px;flex-wrap:wrap;' },
        el('label', { class: 'small muted', text: 'Authority' }),
        el('div', { class: 'typeahead' }, areaInput, areaList),
        el('span', { class: 'spacer' }), exportHolder),
      pinnedCaveat(
        'Prevalence and treatment numbers use different estimation methods and '
        + 'populations. This pipeline does not compute unmet need by subtracting '
        + 'one from the other, and that calculation is left as a downstream '
        + 'decision made explicitly, not implied by a chart.',
        'What must not be computed here'),
      guideHolder,
      chartHolder,
      tableHolder,
      provHolder)));

  for (const [key, label] of TOPICS) {
    tabs.append(el('button', {
      class: 'btn', type: 'button', 'aria-pressed': String(key === state.topic),
      dataset: { topic: key },
      onclick: () => { state.topic = key; load(); },
    }, label));
  }

  // Authority typeahead. Fuse where present, substring otherwise.
  let authorities = [];
  try {
    authorities = (await fetchJSON('authorities')).authorities || [];
  } catch (e) { /* the page still works across all authorities */ }
  const fuse = window.Fuse
    ? new window.Fuse(authorities, { keys: ['name', 'ons_code'], threshold: 0.4 })
    : null;

  const resetAreaKeyboard = typeaheadKeyboard(areaInput, areaList);

  const showAreas = () => {
    const term = areaInput.value.trim();
    const matches = !term ? authorities.slice(0, 12)
      : fuse ? fuse.search(term).slice(0, 12).map((r) => r.item)
        : authorities.filter((a) => a.name.toLowerCase().includes(term.toLowerCase())).slice(0, 12);
    replace(areaList, [
      el('li', { role: 'option', onmousedown: () => pick(null, '') }, 'All authorities'),
      ...matches.map((a) => el('li', {
        role: 'option', onmousedown: () => pick(a.ons_code, a.name),
      }, a.name)),
    ]);
    resetAreaKeyboard();
    areaList.hidden = false;
    areaInput.setAttribute('aria-expanded', 'true');
  };
  const pick = (code, label) => {
    state.ons = code;
    areaInput.value = label;
    areaList.hidden = true;
    areaInput.setAttribute('aria-expanded', 'false');
    load();
    // NDTMS is local-authority only and does not know about the topic tabs,
    // so it reloads when the authority changes and not when a tab is pressed.
    loadNdtms(page.querySelector('#ndtms'), state, charts);
  };
  areaInput.addEventListener('focus', showAreas);
  areaInput.addEventListener('input', showAreas);
  areaInput.addEventListener('blur', () => setTimeout(() => { areaList.hidden = true; }, 120));

  async function load() {
    for (const button of tabs.querySelectorAll('button')) {
      button.setAttribute('aria-pressed', String(button.dataset.topic === state.topic));
    }
    replace(chartHolder, el('div', { class: 'shimmer' }));

    let data;
    try {
      data = await fetchJSON('fingertips', { topic: state.topic, ons_code: state.ons });
    } catch (error) {
      replace(chartHolder, errorCard(error, load));
      return;
    }

    replace(exportHolder, exportButton('fingertips',
      { topic: state.topic, ons_code: state.ons }));
    replace(provHolder, provenanceFromRows(data.indicators, {
      tables: ['fingertips_indicators', 'fingertips_la_values'],
      module: 'm12_fingertips',
    }) || el('span', {}));
    replace(guideHolder, indicatorGuide(data, state));

    // BETA-084: fill the health strip's latest-retrieval now the data is in.
    const ftMeta = evidenceMeta({ indicators: data.indicators });
    if (ftMeta.retrievedAt) {
      replace(healthSlot, evidenceHealthStrip({
        scope: 'OHID Fingertips and NDTMS treatment indicators, by English local authority, against the England figure.',
        retrievedAt: ftMeta.retrievedAt,
        verification: 'n/a',
        coverage: 'partial',
        licence: { name: 'Open Government Licence v3.0', url: 'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/' },
        limitation: 'Unmet need cannot be derived by subtracting one measure from another; missing periods are shown as missing, never zero.',
        catalogueSlug: 'fingertips',
      }));
    }

    setFilterResultCount(data.indicators?.length ?? 0, 'indicator');

    if (!data.indicators?.length) {
      replace(chartHolder, noData(`${state.topic} indicators`,
        './start.sh run m12_fingertips'));
      replace(tableHolder, el('span', {}));
      return;
    }
    drawSeries(chartHolder, data, state, charts);
    drawTable(tableHolder, data, state);
  }

  await load();
  await loadNdtms(page.querySelector('#ndtms'), state, charts);
  return () => disposeCharts(charts);
}

// BETA-075: searchable metric catalogue rendered before any chart.
async function renderMetricCatalogue(container, onPick) {
  let data;
  try {
    data = await fetchJSON('treatment_metrics');
  } catch (error) {
    replace(container, section('Treatment metric catalogue', null,
      errorCard(error, () => renderMetricCatalogue(container, onPick))));
    return;
  }
  const metrics = data.metrics || [];
  const listHolder = el('div', { class: 'metric-list' });
  const countLine = el('p', { class: 'small muted' });

  const paint = (term) => {
    const q = (term || '').trim().toLowerCase();
    const shown = q
      ? metrics.filter((m) => `${m.name} ${m.topic || ''} ${m.unit || ''} ${m.definition || ''}`
          .toLowerCase().includes(q))
      : metrics;
    countLine.textContent = `${shown.length} of ${metrics.length} metrics`;
    replace(listHolder, shown.map((m) => {
      const range = m.period_range && m.period_range[0]
        ? `${m.period_range[0]}–${m.period_range[1]} (${m.period_count})`
        : (m.period_count ? `${m.period_count} periods` : 'no periods published');
      const row = el('div', { class: 'metric-row' },
        el('div', { class: 'metric-row-head' },
          el('button', {
            class: 'linklike metric-pick', type: 'button',
            onclick: () => onPick(m.source === 'fingertips' ? m.topic : null),
          }, m.name),
          el('span', { class: `badge ${m.source === 'ndtms' ? 'neutral' : 'good'}`,
            text: m.source === 'ndtms' ? 'NDTMS' : 'Fingertips' }),
          m.has_confidence_interval
            ? el('span', { class: 'badge good', text: '95% CI' })
            : el('span', { class: 'badge unverified', text: 'no CI' })),
        el('dl', { class: 'metric-meta' },
          el('dt', { text: 'Unit' }), el('dd', { text: m.unit || 'published with the metric' }),
          el('dt', { text: 'Periods' }), el('dd', { text: range }),
          el('dt', { text: 'Authorities' }), el('dd', { text: String(m.authority_count) }),
          el('dt', { text: 'England figure' }), el('dd', { text: m.england_available ? 'available' : 'not held' }),
          el('dt', { text: 'Retrieved' }), el('dd', { text: isoDate(m.retrieved_at) })),
        m.definition
          ? el('details', { class: 'metric-def' },
              el('summary', { text: 'Definition' }),
              el('p', { class: 'small', text: m.definition }))
          : null,
        m.source_url
          ? el('p', { class: 'small' },
              el('a', { href: m.source_url, target: '_blank', rel: 'noopener noreferrer' }, 'Source ↗'))
          : null);
      return row;
    }));
  };

  const search = el('input', {
    type: 'search', placeholder: 'Search metrics by name, unit or definition',
    'aria-label': 'Search treatment metrics',
    oninput: (e) => paint(e.target.value),
  });

  replace(container, section(
    'Treatment metric catalogue',
    'What each metric measures, its unit, whether a confidence interval is '
    + 'published, the exact periods it holds and its coverage — before a chart.',
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveat, 'Different measures, not one scale'),
      search, countLine, listHolder)));
  paint('');
}

function indicatorGuide(data, state) {
  const indicator = data.indicators?.[0];
  if (!indicator) return el('span', {});
  const selected = state.ons ? 'Selected authority and England are shown.'
    : 'The chart shows the authority median and England until an authority is selected.';
  const meta = evidenceMeta({ indicators: data.indicators });
  return el('div', {},
    el('div', { class: 'takeaway' },
      el('span', { class: 'badge good', text: 'PUBLISHED' }),
      el('p', {},
        el('strong', { text: indicator.indicator_name }),
        ` · ${indicator.unit || 'unit published with the indicator'}. ${selected}`)),
    findingBlock({
      finding: `${indicator.indicator_name} is shown as the source published it; the selected authority changes the comparison context, not the meaning of the measure.`,
      value: indicator.unit || 'Published indicator', evidenceStatus: 'Published',
      timing: { kind: meta.retrievedAt ? 'current' : 'snapshot', date: meta.retrievedAt?.slice(0, 10) },
      sources: meta.sources, retrievedAt: meta.retrievedAt?.slice(0, 10),
      caveat: 'Demand, activity, outcomes, and prevalence are different measures and should not be subtracted or combined into unmet need.',
    }));
}

// --- NDTMS ---------------------------------------------------------------
//
// 17,231 local-authority rows the portal did not read until now: opiate and
// crack use, alcohol dependency, and deaths in treatment against expected.
// All estimates, all published with bounds.

async function loadNdtms(container, state, charts) {
  let data;
  try {
    data = await fetchJSON('ndtms', { ons_code: state.ons });
  } catch (error) {
    replace(container, section('NDTMS estimates', null, errorCard(error,
      () => loadNdtms(container, state, charts))));
    return;
  }

  const datasets = data.datasets || [];
  const holder = el('div', {});
  const tableHolder = el('div', {});
  const provHolder = el('div', {});

  replace(container, section(
    'NDTMS estimates',
    'Modelled estimates of opiate and crack use, alcohol dependency, and '
    + 'deaths in treatment, published by OHID with 95% confidence intervals.',
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.estimates, 'These are estimates, not counts'),
      el('p', { class: 'small muted', text: data.caveats?.coverage || '' }),
      state.ons
        ? el('p', {}, exportButton('ndtms', { ons_code: state.ons }))
        : null,
      holder,
      tableHolder,
      provHolder)));

  if (!datasets.length) {
    replace(holder, noData('NDTMS local-authority statistics',
      './start.sh run m07_ndtms'));
    return;
  }

  if (!state.ons) {
    // The figures are per authority and there is no meaningful England row in
    // this table, so the catalogue is the honest thing to show rather than a
    // chart averaging 150 authorities into one bar.
    replace(holder,
      el('p', { class: 'small' },
        'Choose an authority above to see its estimates. Held for '
        + `${num(Math.max(...datasets.map((d) => d.authorities)))} authorities `
        + `across ${datasets.length} published tables:`),
      el('ul', { class: 'small muted' }, datasets.map((d) => el('li', {},
        `${d.label} — ${num(d.rows)} values, ${num(d.authorities)} authorities`))));
    replace(tableHolder, tableCard('Publications read', [
      { title: 'Publication', field: 'title' },
      { title: 'Year', field: 'financial_year', width: 100 },
      { title: 'Cohort', field: 'cohort', width: 90 },
      { title: 'LA sheets', field: 'sheets_local_authority', width: 100 },
      { title: 'Sheets', field: 'sheets_total', width: 80 },
    ], data.publications || [], { height: 260 }));
    return;
  }

  const estimates = data.estimates || [];
  if (!estimates.length) {
    replace(holder, noData(`NDTMS estimates for ${data.authority?.name || state.ons}`,
      null));
    replace(tableHolder, el('span', {}));
    return;
  }

  // Only the figures the source published with an interval reach the chart.
  // That is not a display preference: these sheets put a dependency estimate,
  // the mid-year population it was calculated against, and a rate per
  // thousand side by side, and a single axis carrying 1,363 and 73,236 and
  // 1.86 tells the reader nothing about any of them. Having an interval is
  // the source's own mark of which rows are the estimates.
  const charted = estimates.filter((e) => e.has_interval);
  const rest = estimates.filter((e) => !e.has_interval);

  if (charted.length) {
    drawNdtms(holder, data, charted, rest.length, charts);
  } else {
    replace(holder, noData('estimates with published confidence intervals', null));
  }

  replace(tableHolder, tableCard(
    'Other published values', [
      { title: 'Dataset', field: 'dataset' },
      { title: 'Measure', field: 'measure' },
      { title: 'Period', field: 'time_period', width: 170 },
      { title: 'In publication', field: 'published_in', width: 120 },
      // `value_text` and not `value`: some of these rows have no number at
      // all. Some are context (a region name); some are a disclosure marker,
      // which is not zero and must not be shown as one.
      { title: 'Published as', field: 'value_text', width: 140 },
    ], [...rest, ...(data.other_rows || [])], { height: 260 }));

  replace(provHolder, provenanceFromRows(estimates, {
    tables: ['ndtms_la_statistics', 'ndtms_publications'],
    module: 'm07_ndtms',
  }) || el('span', {}));
}

function drawNdtms(container, data, estimates, without, charts) {
  // One row per measure-and-period. Where a sheet gives no period the label
  // says which publication the figure was read from instead — several
  // editions reprint the same estimate, and dating a 2017 estimate to the
  // 2019 report that reprinted it would be wrong.
  const labels = estimates.map((e) => (e.time_period
    ? `${e.measure} · ${e.time_period}`
    : `${e.measure} · in ${e.published_in} report`));

  charts.push(mountChart(container, {
    grid: { left: 220, top: 30, right: 40, bottom: 40 },
    tooltip: {
      trigger: 'item',
      formatter: (p) => {
        const e = estimates[p.dataIndex];
        return `<strong>${escapeHtml(e.measure)}</strong><br>`
          + `${escapeHtml(String(e.value_text ?? e.value))}<br>`
          + `<span style="color:#8b949e">95% CI ${escapeHtml(String(e.lower))}`
          + ` to ${escapeHtml(String(e.upper))}</span><br>`
          + `<span style="color:#8b949e">read from the ${escapeHtml(String(e.published_in))}`
          + ' publication</span>';
      },
    },
    xAxis: { type: 'value', name: 'published value' },
    yAxis: { type: 'category', data: labels, axisLabel: { width: 210, overflow: 'truncate' } },
    series: [
      // The interval first, so the point estimate draws on top of it.
      {
        name: '95% confidence interval',
        type: 'custom',
        silent: true,
        renderItem: (params, api) => {
          const estimate = estimates[api.value(0)];
          if (!estimate) return null;
          const y = api.coord([0, api.value(0)])[1];
          const left = api.coord([estimate.lower, api.value(0)])[0];
          const right = api.coord([estimate.upper, api.value(0)])[0];
          const cap = 5;
          return {
            type: 'group',
            children: [
              { type: 'line', shape: { x1: left, y1: y, x2: right, y2: y },
                style: { stroke: 'rgba(56, 189, 248, 0.65)', lineWidth: 2 } },
              { type: 'line', shape: { x1: left, y1: y - cap, x2: left, y2: y + cap },
                style: { stroke: 'rgba(56, 189, 248, 0.65)', lineWidth: 2 } },
              { type: 'line', shape: { x1: right, y1: y - cap, x2: right, y2: y + cap },
                style: { stroke: 'rgba(56, 189, 248, 0.65)', lineWidth: 2 } },
            ],
          };
        },
        data: estimates.map((e, i) => [i, e.value]),
      },
      {
        name: 'published estimate',
        type: 'scatter',
        symbolSize: 11,
        itemStyle: { color: '#38bdf8' },
        data: estimates.map((e, i) => [e.value, i]),
      },
    ],
  }, {
    height: estimates.length > 12 ? 'tall' : null,
    aria: `${estimates.length} estimates for `
      + `${data.authority?.name || 'the selected authority'}, each drawn as a `
      + 'point with the 95% confidence interval the source published for it.',
  }));

  if (without) {
    const note = caveat(
      'These sheets print an estimate, the population it was calculated '
      + 'against and a rate per thousand side by side. Charting them on one '
      + 'axis would make all three unreadable, and only the estimates carry '
      + 'an interval — which is the source’s own mark of which rows are '
      + 'estimates. The rest are in the table below, with their values.',
      { label: 'What is not on this chart' });
    container.append(el('p', { class: 'small muted' },
      `${without} further published value${without === 1 ? '' : 's'} `
      + 'for this authority carry no confidence interval and are not charted. ',
      note.button), note.body);
  }
}

function drawSeries(container, data, state, charts) {
  const indicator = data.indicators[0];
  const rows = (data.series || []).filter((r) => r.indicator_id === indicator.indicator_id);
  const england = (data.england_series || [])
    .filter((r) => r.indicator_id === indicator.indicator_id);

  if (!rows.length && !england.length) {
    replace(container, noData(`values for ${indicator.indicator_name}`, null));
    return;
  }

  const periods = [...new Set([...rows, ...england].map((r) => r.time_period))]
    .sort((a, b) => String(a).localeCompare(String(b)));

  const series = [];

  if (state.ons && rows.length) {
    const byPeriod = new Map(rows.map((r) => [r.time_period, r]));
    const values = periods.map((p) => byPeriod.get(p)?.value ?? null);
    const lower = periods.map((p) => byPeriod.get(p)?.lower_ci_95 ?? null);
    const upper = periods.map((p) => byPeriod.get(p)?.upper_ci_95 ?? null);

    // The confidence interval as a band: a lower bound, then the distance up
    // to the upper bound stacked on it and left transparent.
    if (lower.some((v) => v !== null)) {
      series.push({
        name: 'lower 95% CI', type: 'line', stack: 'ci', symbol: 'none',
        lineStyle: { opacity: 0 }, areaStyle: { opacity: 0 }, silent: true,
        data: lower,
      }, {
        name: '95% confidence interval', type: 'line', stack: 'ci', symbol: 'none',
        lineStyle: { opacity: 0 },
        areaStyle: { color: 'rgba(56, 189, 248, 0.18)' },
        data: periods.map((p, i) => (upper[i] === null || lower[i] === null
          ? null : upper[i] - lower[i])),
      });
    }
    series.push({
      name: rows[0].authority_name || state.ons,
      type: 'line', symbol: symbolFor(0), symbolSize: 8, connectNulls: true,
      data: values,
    });
  } else if (rows.length) {
    // No authority chosen: show the spread across authorities rather than 300
    // unreadable lines.
    const byPeriod = new Map();
    for (const row of rows) {
      if (row.value === null || row.value === undefined) continue;
      if (!byPeriod.has(row.time_period)) byPeriod.set(row.time_period, []);
      byPeriod.get(row.time_period).push(row.value);
    }
    series.push({
      name: 'authority median',
      type: 'line', symbol: symbolFor(1), connectNulls: true,
      data: periods.map((p) => median(byPeriod.get(p) || [])),
    });
  }

  if (england.length) {
    const byPeriod = new Map(england.map((r) => [r.time_period, r.value]));
    series.push({
      name: 'England',
      type: 'line', symbol: symbolFor(2), connectNulls: true,
      lineStyle: { type: 'dashed', width: 2 },
      data: periods.map((p) => byPeriod.get(p) ?? null),
    });
  }

  charts.push(mountChart(container, {
    title: {
      text: indicator.indicator_name,
      subtext: indicator.unit || '',
      left: 0, top: 0,
      textStyle: { fontSize: 15 },
      subtextStyle: { color: '#8b949e' },
    },
    grid: { top: 76 },
    legend: { top: 46, type: 'scroll',
      data: series.map((s) => s.name).filter((n) => n !== 'lower 95% CI') },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: periods },
    yAxis: { type: 'value', name: indicator.unit || '' },
    series,
  }, {
    aria: `Line chart of ${indicator.indicator_name} over time`
      + (state.ons ? ` for the selected authority, with its 95% confidence interval,`
        : ' as a median across authorities,')
      + ' compared with the England figure.',
  }));
}

function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function drawTable(container, data, state) {
  const rows = data.series || [];
  // The count lives in the toolbar now, so the title is just what these are.
  replace(container, tableCard('Indicator values', [
    { title: 'Authority', field: 'authority_name' },
    { title: 'ONS code', field: 'ons_code', width: 110 },
    { title: 'Period', field: 'time_period', width: 110 },
    { title: 'Value', field: 'value', width: 100 },
    { title: 'Lower 95%', field: 'lower_ci_95', width: 110 },
    { title: 'Upper 95%', field: 'upper_ci_95', width: 110 },
    { title: 'Note', field: 'value_note' },
  ], rows, {
    height: 360,
    exportEndpoint: 'fingertips',
    exportParams: { topic: state.topic, ons_code: state.ons },
  }));
}
