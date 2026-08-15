/* Coroners' Prevention of Future Deaths reports.
 *
 * W-25: 1,539 reports sat in the warehouse with no page. Three rules shape
 * this one, and each is the finding's own:
 *
 *   * Being *sent* a report and being *named* in one are different facts,
 *     recorded as different mention types, and they are drawn as separate
 *     numbers -- never one series.
 *   * Roughly two fifths of the corpus publishes only a metadata stub, so
 *     the stub count sits on the year chart, not in a footnote.
 *   * Coroner areas are not local authorities. There is no map.
 *
 * The names of the deceased are in restricted tables this page cannot reach,
 * and nothing here links to them. What a reader gets instead is the coroner's
 * own published page for each report.
 */
'use strict';

import { el, replace, fetchJSON, num, sourceLink } from '/app.js';
import { section, pinnedCaveat, noData, errorCard, mountChart,
          disposeCharts, provenanceFromRows, tableCard } from '/js/components.js';

export async function render(main) {
  const charts = [];
  let data;
  try {
    data = await fetchJSON('pfd');
  } catch (error) {
    replace(main, errorCard(error.message, () => render(main)));
    return () => {};
  }

  const totals = data.totals || {};
  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Prevention of Future Deaths reports' }),
      el('p', { class: 'lede' },
        `${num(totals.reports)} reports from coroners, read from judiciary.uk. `,
        'A report is the coroner\'s own words about how a death could have ',
        'been avoided — read the report, not just the numbers here.')),
    el('div', { id: 'year' }),
    el('div', { id: 'area' }),
    el('div', { id: 'terms' }),
    el('div', { id: 'mentions' }),
    el('div', { id: 'recent' }));
  replace(main, page);

  renderYears(page.querySelector('#year'), data, charts);
  renderAreas(page.querySelector('#area'), data, charts);
  renderTerms(page.querySelector('#terms'), data, charts);
  renderMentions(page.querySelector('#mentions'), data);
  renderRecent(page.querySelector('#recent'), data);

  return () => disposeCharts(charts);
}

/* Reports by year, stacked by whether the publication carried the matters of
 * concern. The stub share belongs on the chart: "no concerns here" is a
 * statement about the publication, not about the coroner. */
function renderYears(container, data, charts) {
  const byYear = data.by_year || [];
  const totals = data.totals || {};
  const holder = el('div', {});

  replace(container, section(
    'Reports by year',
    `${num(totals.with_concerns)} of ${num(totals.reports)} carry the `
    + 'matters of concern in the published data. The rest are metadata stubs '
    + '— the report itself is a PDF the publication does not link.',
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.stubs, 'The stub count is a source limitation'),
      holder)));

  if (!byYear.length) {
    replace(holder, noData('PFD reports', './start.sh run m08_pfd_reports'));
    return;
  }

  charts.push(mountChart(holder, {
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    xAxis: { type: 'category', data: byYear.map((y) => y.year) },
    yAxis: { type: 'value', name: 'reports' },
    series: [
      { name: 'with matters of concern', type: 'bar', stack: 'r',
        data: byYear.map((y) => y.with_concerns), itemStyle: { color: '#f59e0b' } },
      { name: 'metadata stub', type: 'bar', stack: 'r',
        data: byYear.map((y) => y.reports - y.with_concerns),
        itemStyle: { color: '#30363d' } },
    ],
  }, {
    height: 'short',
    aria: `Stacked bar chart of PFD reports per year, showing how many carry `
      + `matters of concern and how many are metadata stubs. `
      + `${num(totals.stubs)} of ${num(totals.reports)} are stubs, which is a `
      + 'source limitation.',
  }));
}

/* The top coroner areas. Named as what they are, with the caveat that says
 * they are not local authorities — there is deliberately no map. */
function renderAreas(container, data, charts) {
  const areas = data.by_coroner_area || [];
  const holder = el('div', {});

  replace(container, section(
    'By coroner area',
    'The coronial districts publishing the most reports in this corpus.',
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.areas, 'Not local authorities'),
      holder)));

  if (!areas.length) {
    replace(holder, noData('coroner areas', './start.sh run m08_pfd_reports'));
    return;
  }

  charts.push(mountChart(holder, {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', name: 'reports' },
    yAxis: { type: 'category', data: areas.map((a) => a.coroner_area) },
    series: [{
      type: 'bar', data: areas.map((a) => a.reports), itemStyle: { color: '#38bdf8' },
    }],
  }, {
    height: 'tall',
    aria: 'Bar chart of the twenty-five coroner areas publishing the most '
      + 'reports in this corpus.',
  }));
}

/* The finding aid. A term means the word appears — it points at reports
 * worth reading, and it is labelled as such rather than as a finding. */
function renderTerms(container, data, charts) {
  const terms = data.concern_terms || [];
  const holder = el('div', {});

  replace(container, section(
    'Terms in the matters of concern',
    'Words that appear in the published concerns, by total occurrences '
    + 'across the corpus.',
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.terms, 'A finding aid, not a finding'),
      holder)));

  if (!terms.length) {
    replace(holder, noData('concern terms', './start.sh run m08_pfd_reports'));
    return;
  }

  charts.push(mountChart(holder, {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', name: 'occurrences' },
    yAxis: { type: 'category', data: terms.map((t) => t.term) },
    series: [{
      type: 'bar', data: terms.map((t) => t.occurrences), itemStyle: { color: '#a78bfa' },
    }],
  }, {
    height: 'tall',
    aria: 'Bar chart of the terms appearing most often in the matters of '
      + 'concern, with their total occurrences across the corpus.',
  }));
}

/* Sent and named stay two numbers. The caveat says the two must never be
 * added, and nothing here sums them. */
function renderMentions(container, data) {
  const mentions = data.mentions || {};

  replace(container, section(
    'Tracked providers in the reports',
    'Two different facts, counted separately and never added together.',
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.mentions, 'Sent and named are different facts'),
      el('div', { class: 'grid cards' },
        el('div', { class: 'statcard' },
          el('div', { class: 'value plain', text: num(mentions.sent_to_providers) }),
          el('div', { class: 'label', text: 'reports sent to a tracked provider' }),
          el('div', { class: 'sub', text: 'the coroner addressed the report to them' })),
        el('div', { class: 'statcard' },
          el('div', { class: 'value plain', text: num(mentions.naming_providers) }),
          el('div', { class: 'label', text: 'reports naming a tracked provider' }),
          el('div', { class: 'sub', text: 'named in the text, not a recipient' })),
        el('div', { class: 'statcard' },
          el('div', { class: 'value plain', text: num(mentions.recipient_organisations) }),
          el('div', { class: 'label', text: 'organisations sent reports' }),
          el('div', { class: 'sub', text: 'across the whole corpus, not just providers' }))))));
}

function renderRecent(container, data) {
  const recent = data.recent || [];

  replace(container, section(
    'The latest reports',
    'The fifty newest by the coroner\'s own reference, each linking to the '
    + 'report on judiciary.uk. The date is the source\'s own wording.',
    tableCard('Latest reports', [
      { title: 'Reference', field: 'report_ref', width: 110 },
      { title: 'Date', field: 'report_date', width: 130 },
      { title: 'Coroner area', field: 'coroner_area' },
      { title: 'Categories', field: 'categories' },
      { title: 'Concerns', field: 'has_concerns', width: 90,
        formatter: (c) => (c.getValue() ? 'yes' : 'stub') },
      { title: 'Report', field: 'report_url', width: 90, headerFilter: false,
        formatter: (c) => sourceLink(c.getValue(), 'report ↗') },
    ], recent, { height: 520, total: (data.totals || {}).reports }),
    provenanceFromRows(recent, { module: 'm08_pfd_reports', tables: ['pfd_reports'] })));
}
