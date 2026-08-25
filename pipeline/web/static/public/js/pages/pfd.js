/* Coroners' Prevention of Future Deaths reports, and Safeguarding Adult
 * Reviews (SARs) -- two distinct evidence streams on one "Safety & legal
 * evidence" page, drawn separately and never combined into one series.
 *
 * PFD (judiciary.uk). W-25: 1,539 reports sat in the warehouse with no page.
 * Three rules shape that half of the page, and each is the finding's own:
 *
 *   * Being *sent* a report and being *named* in one are different facts,
 *     recorded as different mention types, and they are drawn as separate
 *     numbers -- never one series.
 *   * Roughly two fifths of the corpus publishes only a metadata stub, so
 *     the stub count sits on the year chart, not in a footnote.
 *   * Coroner areas are not local authorities. There is no map.
 *
 * SAR (the National SAR Library). Read from a single national library that
 * boards submit to, rather than ~150 board websites. It carries no
 * structured date or excerpt the way judiciary.uk does, so this half of the
 * page is deliberately thinner: counts, the boards documents name
 * themselves as, a term-frequency finding aid, and provider mentions. There
 * is no "matters of concern" equivalent -- SAR reports share no common
 * template across ~150 boards for a section-boundary guess to be trusted.
 *
 * The names of the deceased/reviewed are in restricted tables this page
 * cannot reach, and nothing here links to them. What a reader gets instead
 * is the source's own published page for each report or review.
 */
'use strict';

import { el, replace, fetchJSON, num, sourceLink } from '/app.js';
import { section, pinnedCaveat, noData, errorCard, mountChart,
          disposeCharts, provenanceFromRows, tableCard, shareButton,
          findingBlock, evidenceMeta } from '/js/components.js';

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
  const sar = data.sar || {};
  const sarTotals = sar.totals || {};
  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Safety & legal evidence' }),
      el('p', { class: 'lede' },
        `${num(totals.reports)} reports from coroners, read from judiciary.uk, `,
        `and ${num(sarTotals.documents)} Safeguarding Adult Reviews from the `,
        'National SAR Library. Each is the author\'s own words about how harm ',
        'could have been avoided — read the document, not just the numbers here.'),
      el('div', { class: 'hero-actions' },
        shareButton({
          title: 'SectorTrace safety and legal evidence',
          text: 'Explore source-linked coroners’ reports and safeguarding reviews in SectorTrace.',
          label: 'Share this view',
        }))),
    (() => {
      const meta = evidenceMeta(data);
      return findingBlock({
        finding: 'Safety and legal evidence distinguishes reports sent by coroners from provider mentions; metadata stubs and missing links remain visible limitations rather than evidence of absence.',
        value: `${num(totals.reports)} coroner reports`, evidenceStatus: meta.sources.length || meta.retrievedAt ? 'Published' : null,
        timing: { kind: meta.retrievedAt ? 'current' : 'snapshot', date: meta.retrievedAt?.slice(0, 10) },
        sources: meta.sources, retrievedAt: meta.retrievedAt?.slice(0, 10),
        caveat: data.caveats?.stubs || 'A provider mention is not a finding of fault, causation, prevalence, or responsibility.',
      });
    })(),
    el('details', { class: 'read-first' },
      el('summary', { text: 'Read reports responsibly' }),
      el('p', { text: 'A provider mention is not a finding of fault, causation, prevalence, or responsibility. “Sent to” and “named in” are different facts.' }),
      el('p', { text: 'Some publications are metadata stubs, so an absent concern is a source limitation rather than evidence of absence.' }),
      el('p', { text: 'Safeguarding Adult Reviews carry none of these numbers as a "matters of concern" excerpt — the source has no shared template across ~150 boards for that to be trusted from.' })),
    el('div', { id: 'recent' }),
    el('div', { id: 'year' }),
    el('div', { id: 'area' }),
    el('div', { id: 'terms' }),
    el('div', { id: 'mentions' }),
    el('h2', { text: 'Safeguarding Adult Reviews' }),
    el('p', { class: 'lede' },
      'A separate evidence stream from a separate source — see the caveats on ',
      'each panel before comparing it with the coroners\' reports above.'),
    el('div', { id: 'sar-recent' }),
    el('div', { id: 'sar-year' }),
    el('div', { id: 'sar-board' }),
    el('div', { id: 'sar-terms' }),
    el('div', { id: 'sar-mentions' }));
  replace(main, page);

  renderRecent(page.querySelector('#recent'), data);
  renderYears(page.querySelector('#year'), data, charts);
  renderAreas(page.querySelector('#area'), data, charts);
  renderTerms(page.querySelector('#terms'), data, charts);
  renderMentions(page.querySelector('#mentions'), data);

  renderSarRecent(page.querySelector('#sar-recent'), sar);
  renderSarYears(page.querySelector('#sar-year'), sar, charts);
  renderSarBoards(page.querySelector('#sar-board'), sar, charts);
  renderSarTerms(page.querySelector('#sar-terms'), sar, charts);
  renderSarMentions(page.querySelector('#sar-mentions'), sar);

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
    'Concern themes',
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
    ], recent, {
      height: 520, total: (data.totals || {}).reports,
      // The complete corpus, not just these 50 -- server.py streams every
      // row from its own unwindowed query (public_queries.all_pfd_reports),
      // the same pattern contracts.js's export uses for the same reason.
      exportEndpoint: 'pfd',
    }),
    provenanceFromRows(recent, { module: 'm08_pfd_reports', tables: ['pfd_reports'] })));
}

/* --- Safeguarding Adult Reviews ------------------------------------------- */

/* Documents by the library's own year folder, stacked by whether text was
 * extracted. Not a publication-date chart -- see the scope caveat -- but the
 * only grouping the source actually gives. */
function renderSarYears(container, sar, charts) {
  const byYear = sar.by_year || [];
  const totals = sar.totals || {};
  const holder = el('div', {});

  replace(container, section(
    'SARs by library year',
    `${num(totals.with_text)} of ${num(totals.documents)} were readable as text `
    + '(the rest are scans with nothing to extract, or a file format other than PDF). '
    + 'The year is when the library filed the document, not when it was published.',
    el('div', { class: 'panel' },
      pinnedCaveat(sar.caveats?.scope, 'Coverage is whatever boards submitted'),
      holder)));

  if (!byYear.length) {
    replace(holder, noData('SAR documents', './start.sh run m28_sar_reports'));
    return;
  }

  charts.push(mountChart(holder, {
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    xAxis: { type: 'category', data: byYear.map((y) => y.year) },
    yAxis: { type: 'value', name: 'documents' },
    series: [
      { name: 'text extracted', type: 'bar', stack: 'r',
        data: byYear.map((y) => y.with_text), itemStyle: { color: '#f59e0b' } },
      { name: 'no text extracted', type: 'bar', stack: 'r',
        data: byYear.map((y) => y.documents - y.with_text),
        itemStyle: { color: '#30363d' } },
    ],
  }, {
    height: 'short',
    aria: `Stacked bar chart of SAR documents per library year, showing how `
      + `many were readable as text. ${num(totals.documents - totals.with_text)} `
      + `of ${num(totals.documents)} were not.`,
  }));
}

/* The boards whose own documents name them most often. Free text, not a
 * fixed list of the ~150 boards -- see the board caveat. */
function renderSarBoards(container, sar, charts) {
  const boards = sar.by_board || [];
  const holder = el('div', {});

  replace(container, section(
    'By board',
    'Boards named by their own documents, most-documented first.',
    el('div', { class: 'panel' },
      pinnedCaveat(sar.caveats?.board, 'Read from the document, not a fixed list'),
      holder)));

  if (!boards.length) {
    replace(holder, noData('SAR board names', './start.sh run m28_sar_reports'));
    return;
  }

  charts.push(mountChart(holder, {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', name: 'documents' },
    yAxis: { type: 'category', data: boards.map((b) => b.sab_name) },
    series: [{
      type: 'bar', data: boards.map((b) => b.documents), itemStyle: { color: '#38bdf8' },
    }],
  }, {
    height: 'tall',
    aria: 'Bar chart of the twenty-five Safeguarding Adults Boards named most '
      + 'often by their own documents in this corpus.',
  }));
}

/* The same finding-aid idea as PFD's concern terms, over the whole document
 * text rather than one extracted section -- there is no section to extract. */
function renderSarTerms(container, sar, charts) {
  const terms = sar.concern_terms || [];
  const holder = el('div', {});

  replace(container, section(
    'Themes in the documents',
    'Words that appear anywhere in the extracted text, by total occurrences '
    + 'across the corpus.',
    el('div', { class: 'panel' },
      pinnedCaveat(sar.caveats?.terms, 'A finding aid, not a finding'),
      holder)));

  if (!terms.length) {
    replace(holder, noData('SAR concern terms', './start.sh run m28_sar_reports'));
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
    aria: 'Bar chart of the terms appearing most often across the SAR '
      + 'documents, with their total occurrences.',
  }));
}

/* One number, not two: the library gives no distribution list, so there is
 * no "sent to" fact to distinguish from "named in" the way PFD's mentions
 * are. */
function renderSarMentions(container, sar) {
  const mentions = sar.mentions || {};

  replace(container, section(
    'Tracked providers in the reviews',
    'Documents naming a tracked provider anywhere in the text.',
    el('div', { class: 'panel' },
      pinnedCaveat(sar.caveats?.mentions, 'A mention is not a finding of fault'),
      el('div', { class: 'grid cards' },
        el('div', { class: 'statcard' },
          el('div', { class: 'value plain', text: num(mentions.naming_providers) }),
          el('div', { class: 'label', text: 'reviews naming a tracked provider' }),
          el('div', { class: 'sub', text: 'named in the text; the library gives no distribution list' }))))));
}

function renderSarRecent(container, sar) {
  const recent = sar.recent || [];

  replace(container, section(
    'The latest SAR documents',
    'The fifty most recently filed by the library\'s own year folder, each '
    + 'linking to the source document. Titles are not shown here — see the '
    + 'personal data note in the module\'s docstring.',
    tableCard('Latest SAR documents', [
      { title: 'Year', field: 'library_year', width: 90 },
      { title: 'Board', field: 'sab_name' },
      { title: 'Format', field: 'document_ext', width: 90 },
      { title: 'Text read', field: 'has_body_text', width: 90,
        formatter: (c) => (c.getValue() ? 'yes' : 'no') },
      { title: 'Document', field: 'source_url', width: 100, headerFilter: false,
        formatter: (c) => sourceLink(c.getValue(), 'document ↗') },
    ], recent, { height: 520, total: (sar.totals || {}).documents }),
    provenanceFromRows(recent, { module: 'm28_sar_reports', tables: ['sar_documents'] })));
}
