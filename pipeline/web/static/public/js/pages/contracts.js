/* Contracts — what was published, by whom, to whom.
 *
 * The corpus this reads is broad: notices matching the sector keyword set,
 * which includes health and care awards well outside substance misuse, and
 * cross-government frameworks whose published value is a ceiling. The page
 * leads with that rather than presenting a total and leaving it to be
 * discovered.
 */
'use strict';

import { el, replace, fetchJSON, filterParams, num, gbp, pct, isoDate } from '/app.js';
import { section, pinnedCaveat, caveat, noData, errorCard, mountChart,
          disposeCharts, provenance, tableCard, escapeHtml, truncate,
          exportButton } from '/js/components.js';

export async function render(main) {
  const charts = [];
  let data, spending;
  try {
    [data, spending] = await Promise.all([
      fetchJSON('contracts', filterParams({ limit: 1000 })),
      fetchJSON('council_spend', filterParams({ limit: 500 })),
    ]);
  } catch (error) {
    replace(main, errorCard(error.message, () => render(main)));
    return () => {};
  }

  const concentration = data.value_concentration || {};
  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Contracts' }),
      el('p', { class: 'lede' },
        `${num(data.total)} published notice${data.total === 1 ? '' : 's'}. `,
        data.total
          ? `The middle one is ${gbp(concentration.median_value_gbp, { compact: false })}; `
            + `the mean is ${gbp(concentration.mean_value_gbp)}.`
          : 'Nothing matches these filters.')),
    el('div', { id: 'shape' }),
    el('div', { id: 'corpus' }),
    el('div', { id: 'breakdown' }),
    el('div', { id: 'buyers' }),
    el('div', { id: 'notices' }));
  replace(main, page);

  renderShape(page.querySelector('#shape'), data, charts);
  renderCorpus(page.querySelector('#corpus'), data, charts);
  renderBreakdown(page.querySelector('#breakdown'), data, charts);
  renderBuyers(page.querySelector('#buyers'), data, charts);
  renderNotices(page.querySelector('#notices'), data);
  renderCouncilSpend(page.querySelector('#notices').parentNode, spending);

  return () => disposeCharts(charts);
}

function renderCouncilSpend(container, data) {
  const payments = data.payments || [];
  const files = data.files || [];
  const hasUnreadable = files.some((file) => file.parse_status === 'unreadable');
  const sectionNode = section(
    'Published council payments',
    `${num(data.total)} payment line${data.total === 1 ? '' : 's'} in council spend-transparency files. These are actual published payments, separate from notice-stage contract values and authority budgets.`,
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.payments, 'Not a sector-spend total'),
      pinnedCaveat(data.caveats?.provider_match, 'Provider links are exact-name matches only'),
      payments.length ? tableCard('Payment lines', [
        { title: 'Authority', field: 'authority_name' },
        { title: 'Period', field: 'period' },
        { title: 'Payee', field: 'payee' },
        { title: 'Published amount', field: 'amount_text' },
        { title: 'Description', field: 'description' },
        { title: 'Matched provider', field: 'canonical_name' },
      ], payments, { height: 360 }) : noData('published council payment lines', './start.sh run m24_council_spend'),
      hasUnreadable ? el('p', { class: 'small muted', text: 'Some collected files were unreadable. Their status is shown below; this is not evidence that the council published no payments.' }) : null,
      files.length ? tableCard('Collected spend files', [
        { title: 'Authority', field: 'authority_name' },
        { title: 'Format', field: 'file_format' },
        { title: 'Status', field: 'parse_status' },
        { title: 'Rows', field: 'row_count' },
        { title: 'Retrieved', field: 'retrieved_at', formatter: (c) => isoDate(c.getValue()) },
      ], files, { height: 240 }) : null,
      provenance(payments, { tables: ['council_spend', 'council_spend_files'], module: 'm24_council_spend' })));
  container.append(sectionNode);
}

function renderShape(container, data, charts) {
  const c = data.value_concentration || {};
  const range = data.date_range || {};
  const matched = data.matched_to_provider || 0;

  replace(container, section(
    'What this corpus is',
    'Three properties to know before reading anything else on this page.',
    el('div', { class: 'panel' },
      el('div', { class: 'grid cards' },
        fact(gbp(c.median_value_gbp, { compact: false }), 'median notice value',
          `${num(c.priced_notices)} of ${num(data.total)} notices carry a value`),
        fact(`${num(c.notices_over_1bn)}`, 'notices above £1bn',
          `carrying ${pct(c.share_over_1bn)} of the total value`),
        fact(`${num(matched)} of ${num(data.total)}`, 'matched to a known provider',
          'exact supplier-name match only'),
        fact(`${isoDate(range.earliest)} → ${isoDate(range.latest)}`,
          'notice dates collected', 'not the period awards were made over')),
      pinnedCaveat(data.caveats?.value_sum, 'Why there is no total on this page'),
      el('p', { class: 'small muted' }, data.caveats?.provider_match || ''),
      el('p', { class: 'small muted' }, data.caveats?.window || ''))));
}

function fact(value, label, sub) {
  return el('div', { class: 'statcard' },
    el('div', { class: 'value plain', text: value }),
    el('div', { class: 'label', text: label }),
    sub ? el('div', { class: 'sub', text: sub }) : null);
}

/* W-23: the shape of the corpus, drawn instead of the total the page
 * refuses. Three charts, all computed over the same filters as the rest of
 * the page, so they follow the filter bar rather than silently ignoring it:
 *
 *   * notices per quarter against the priced count — the gap between the
 *     lines is the coverage story, and the caveat for the window applies;
 *   * value distribution in fixed bands — never derived from the data, so
 *     the same notice sits in the same band whatever is filtered;
 *   * the contract-end runway, with its own pinned caveat: an end date as
 *     published at notice stage is not a retendering forecast.
 */
function renderCorpus(container, data, charts) {
  const quarters = data.by_quarter || [];
  const bands = data.value_bands || [];
  const runway = data.ending_soon || {};
  const runwayRows = runway.rows || [];

  const qHolder = el('div', {});
  const bHolder = el('div', {});
  const rHolder = el('div', {});

  replace(container, section(
    'The shape of the corpus',
    `What ${num((data.value_concentration || {}).priced_notices)} priced `
    + 'notices actually look like. All three charts are computed over the '
    + 'filtered corpus, so they follow the filters.',
    el('div', { class: 'grid two' },
      el('div', { class: 'panel' },
        el('h3', { text: 'Notices by quarter, priced or not' }), qHolder),
      el('div', { class: 'panel' },
        el('h3', { text: 'Published value, by fixed band' }), bHolder),
      el('div', { class: 'panel' },
        el('h3', { text: 'Contract-end runway' }), rHolder,
        runway.caveat ? pinnedCaveat(runway.caveat,
          'Read before calling anything retendered') : null))));

  if (quarters.length) {
    charts.push(mountChart(qHolder, {
      tooltip: { trigger: 'axis' },
      legend: { top: 0 },
      xAxis: { type: 'category', data: quarters.map((q) => q.quarter) },
      yAxis: { type: 'value', name: 'notices' },
      series: [
        { name: 'notices published', type: 'bar',
          data: quarters.map((q) => q.count), itemStyle: { color: '#38bdf8' } },
        { name: 'with a published value', type: 'line', smooth: true,
          data: quarters.map((q) => q.priced), itemStyle: { color: '#f59e0b' } },
      ],
    }, {
      height: 'short',
      aria: 'Bar chart of notices published per quarter, with a line for '
        + 'those carrying a published value. The gap between the two is '
        + 'notices with no value stated.',
    }));
  } else {
    replace(qHolder, noData('notice dates', './start.sh run m01_procurement'));
  }

  if (bands.length) {
    charts.push(mountChart(bHolder, {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      xAxis: {
        type: 'category', name: 'band', nameLocation: 'middle', nameGap: 28,
        data: bands.map((b) => b.band_label),
        axisLabel: { interval: 0, rotate: 30, fontSize: 10 },
      },
      yAxis: { type: 'value', name: 'notices' },
      series: [{
        type: 'bar', data: bands.map((b) => b.count),
        itemStyle: { color: '#38bdf8' },
        label: { show: true, position: 'top', color: '#8b949e', fontSize: 10 },
      }],
    }, {
      height: 'short',
      aria: 'Histogram of notices by published value in fixed bands, from '
        + 'under ten thousand pounds to one billion pounds and above. The '
        + 'bands never change with the filters.',
    }));
  } else {
    replace(bHolder, noData('priced notices', './start.sh run m01_procurement'));
  }

  if (runwayRows.length) {
    charts.push(mountChart(rHolder, {
      tooltip: { trigger: 'axis' },
      legend: { top: 0 },
      xAxis: { type: 'category', data: runwayRows.map((r) => r.quarter) },
      yAxis: { type: 'value', name: 'notices' },
      series: [
        { name: 'ending in quarter', type: 'bar',
          data: runwayRows.map((r) => r.count), itemStyle: { color: '#38bdf8' } },
        { name: 'matched to a tracked provider', type: 'line', smooth: true,
          data: runwayRows.map((r) => r.matched), itemStyle: { color: '#f59e0b' } },
      ],
    }, {
      height: 'short',
      aria: `Bar chart of notices whose published end date falls between `
        + `${runway.window_start} and ${runway.window_end}, by end quarter, `
        + 'with the count matched to a tracked provider alongside. Extensions '
        + 'are not applied and this is not a retendering forecast.',
    }));
  } else {
    replace(rHolder, el('div', { class: 'chart-empty' },
      el('strong', { text: 'No notices end within this window.' }),
      el('span', { class: 'small', text:
        `${runway.window_start} → ${runway.window_end}, as published at `
        + 'notice stage.' })));
  }
}

function renderBreakdown(container, data, charts) {
  const procedures = data.by_procedure_type || [];
  const providers = (data.by_provider || []).filter((p) => p.count);
  const procHolder = el('div', {});
  const provHolder = el('div', {});

  replace(container, section(
    'Procedure and provider',
    'How notices were awarded, and which of them name a provider this '
    + 'pipeline tracks.',
    el('div', { class: 'grid two' },
      el('div', { class: 'panel' },
        el('h3', { text: 'Procedure type' }), procHolder),
      el('div', { class: 'panel' },
        el('h3', { text: 'Notices matched to a tracked provider' }), provHolder))));

  if (procedures.length) {
    charts.push(mountChart(procHolder, {
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, type: 'scroll' },
      series: [{
        type: 'pie',
        radius: ['45%', '70%'],
        itemStyle: { borderRadius: 4 },
        label: { color: '#8b949e' },
        data: procedures.map((p) => ({ name: p.procedure_type, value: p.count })),
      }],
    }, {
      height: 'short',
      aria: `Donut chart of notices by procedure type. `
        + procedures.map((p) => `${p.procedure_type}: ${p.count}`).join(', '),
    }));
  } else {
    replace(procHolder, noData('procedure data', './start.sh run m01_procurement'));
  }

  if (providers.length) {
    charts.push(mountChart(provHolder, {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      xAxis: { type: 'value', name: 'notices' },
      yAxis: { type: 'category', data: providers.map((p) => p.canonical_name) },
      series: [{ type: 'bar', data: providers.map((p) => p.count) }],
    }, {
      height: 'short',
      aria: 'Bar chart of notices matched to each tracked provider. Matching '
        + 'requires an exact supplier-name match, so these are floors.',
    }));
  } else {
    replace(provHolder, el('div', { class: 'chart-empty' },
      el('strong', { text: 'No notices matched a tracked provider.' }),
      el('span', { class: 'small', text: data.caveats?.provider_match || '' })));
  }
}

function renderBuyers(container, data, charts) {
  const buyers = (data.top_buyers || []).slice(0, 20);
  const holder = el('div', {});

  replace(container, section(
    'Buyers',
    'Authorities and bodies publishing the most notices in this corpus.',
    el('div', { class: 'panel' }, holder)));

  if (!buyers.length) {
    replace(holder, noData('buyers', './start.sh run m01_procurement'));
    return;
  }

  charts.push(mountChart(holder, {
    tooltip: {
      trigger: 'item',
      formatter: (p) => `<strong>${escapeHtml(p.name)}</strong><br>`
        + `${num(p.data.count)} notices<br>${gbp(p.value, { compact: false })}`,
    },
    series: [{
      type: 'treemap',
      roam: false,
      breadcrumb: { show: false },
      label: { color: '#e6edf3', fontSize: 11 },
      upperLabel: { show: false },
      itemStyle: { borderColor: '#0d1117', borderWidth: 2, gapWidth: 2 },
      data: buyers.map((b) => ({
        name: truncate(b.buyer_name || 'not stated', 40),
        value: b.value_gbp || 0,
        count: b.count,
      })),
    }],
  }, {
    height: 'tall',
    aria: `Treemap of published contract value by buyer. Largest: `
      + `${buyers[0]?.buyer_name} at ${gbp(buyers[0]?.value_gbp)}.`,
  }));
}

function renderNotices(container, data) {
  const notices = data.notices || [];
  // Not "every notice", which is what this section used to be called: the page
  // asks for 1,000 of a corpus that is currently 98,636. The count in the
  // toolbar says which, and the description says why there is a limit at all.
  replace(container, section(
    'The notices',
    notices.length < (data.total || 0)
      ? 'The most recent notices behind the charts above. The charts are '
        + 'computed over the whole corpus; this list is the page\'s share of '
        + 'it. Search a column, or narrow the filters, to reach the rest — or '
        + 'download the CSV, which carries every row these filters match.'
      : 'The full list behind the charts above, downloadable with its provenance.',
    tableCard('Published notices', [
      { title: 'Published', field: 'date_published', width: 110,
        formatter: (c) => isoDate(c.getValue()) },
      { title: 'Buyer', field: 'buyer_name' },
      { title: 'Title', field: 'title' },
      { title: 'Supplier', field: 'supplier_name_raw' },
      { title: 'Value', field: 'value_core', width: 120,
        formatter: (c) => gbp(c.getValue(), { compact: false }) },
      { title: 'Procedure', field: 'procedure_type', width: 130 },
      // Two links, because they are two different things and the useful one
      // used to be missing. "Notice" is the notice's own page on Find a
      // Tender or Contracts Finder — what a reader wants. "Data" is
      // `source_url`: the API page these bytes came from, which is the
      // provenance and is a paginated cursor nobody can read.
      //
      // A constructed link says so on hover. 84% of rows have one, because
      // most releases do not publish their own address; the mapping from the
      // notice id is verified but it is still not something the source said.
      // No header filter on the two link columns: the cell shows "notice ↗",
      // so a search box there would filter on a URL the reader cannot see.
      { title: 'Notice', field: 'notice_link', width: 90, headerFilter: false,
        formatter: (c) => {
          const url = c.getValue();
          if (!url) return '';
          const built = c.getData().notice_link_basis === 'constructed';
          const title = built
            ? 'Built from the notice id — the release did not publish its own address'
            : 'The address published by the release itself';
          return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer"`
            + ` title="${escapeHtml(title)}"${built ? ' style="border-bottom:1px dotted"' : ''}>`
            + `notice ↗</a>`;
        },
        // Tabulator renders this cell as HTML, so everything in it is escaped
        // above. Nothing here is concatenated from a value that was not.
        formatterParams: {}, htmlOutput: true },
      { title: 'Data', field: 'source_url', width: 70, headerFilter: false,
        formatter: (c) => (c.getValue()
          ? `<a href="${escapeHtml(c.getValue())}" target="_blank" rel="noopener noreferrer"`
            + ` title="The API response this row was parsed from">api ↗</a>`
          : ''),
        formatterParams: {}, htmlOutput: true },
    ], notices, {
      height: 520,
      total: data.total,
      exportEndpoint: 'contracts',
      exportParams: filterParams(),
    })));
}
