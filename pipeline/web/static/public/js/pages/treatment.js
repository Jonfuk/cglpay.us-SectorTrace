/* Treatment demand and outcomes, from OHID Fingertips.
 *
 * The note that matters is the one about unmet need. Prevalence estimates and
 * treatment numbers come from different methods and different populations, and
 * subtracting one from the other produces a number this pipeline will not
 * publish. It is stated on the page rather than left in a document nobody
 * opens.
 */
'use strict';

import { el, replace, fetchJSON, num, isoDate } from '/app.js';
import { section, pinnedCaveat, noData, errorCard, mountChart, disposeCharts,
          provenanceFromRows, tableCard, symbolFor, escapeHtml,
          exportButton } from '/js/components.js';

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
      el('h1', { text: 'Treatment demand' }),
      el('p', { class: 'lede' },
        'Indicators published by OHID through Fingertips, by local authority ',
        'and against the England figure.')),
    el('div', { id: 'ft' }));
  replace(main, page);

  const tabs = el('div', { class: 'metrictabs' });
  const areaInput = el('input', {
    type: 'search', placeholder: 'All authorities', 'aria-label': 'Local authority',
    autocomplete: 'off',
  });
  const areaList = el('ul', { class: 'typeahead-list', hidden: true, role: 'listbox' });
  const chartHolder = el('div', {});
  const tableHolder = el('div', {});
  const provHolder = el('div', {});
  const exportHolder = el('span', {});

  replace(page.querySelector('#ft'), section(
    'Indicators',
    null,
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
    areaList.hidden = false;
  };
  const pick = (code, label) => {
    state.ons = code;
    areaInput.value = label;
    areaList.hidden = true;
    load();
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
      replace(chartHolder, errorCard(error.message, load));
      return;
    }

    replace(exportHolder, exportButton('fingertips',
      { topic: state.topic, ons_code: state.ons }));
    replace(provHolder, provenanceFromRows(data.indicators, {
      tables: ['fingertips_indicators', 'fingertips_la_values'],
      module: 'm12_fingertips',
    }) || el('span', {}));

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
  return () => disposeCharts(charts);
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
      textStyle: { fontSize: 15, color: '#e6edf3' },
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
  replace(container, tableCard(`${num(rows.length)} values`, [
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
