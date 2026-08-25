/* Authority — one page per local authority (W-13).
 *
 * "What does my authority get?" is the campaign's own question, and this is
 * where the answer lives: grant allocation, budgeted spend, the budget lines
 * behind it, treatment estimates with their paired confidence intervals, and
 * the contracts the authority let.
 *
 * The endpoint composes the existing endpoint queries rather than re-writing
 * them, so a number here cannot disagree with the same number on the
 * geography, treatment or contracts page — and this page shows the budget
 * drill-down (W-27) that sits behind the one budget figure those pages draw.
 *
 * The rule this page exists to keep: a grant allocation and a budgeted spend
 * are different figures from different documents. They are shown side by
 * side and never combined, differenced or divided — the pinned caveat above
 * them is why the section exists.
 */
'use strict';

import { el, replace, fetchJSON, num, gbp, isoDate } from '/app.js';
import { section, pinnedCaveat, noData, errorCard, mountChart, disposeCharts,
          provenanceFromRows, tableCard, escapeHtml, shareButton,
          findingBlock, evidenceMeta } from '/js/components.js';

const TYPE_LABELS = {
  county: 'County council',
  unitary: 'Unitary authority',
  london_borough: 'London borough',
  metropolitan_district: 'Metropolitan borough',
  non_metropolitan_district: 'District council',
  combined_authority: 'Combined authority',
};

export async function render(main, { path }) {
  const code = path.startsWith('/authorities/')
    ? path.slice('/authorities/'.length) : null;
  return code ? renderOne(main, code) : renderLanding(main);
}

/* A bare #/authorities route has no key to show. The honest answer is an
 * entry point: the top-bar search, the map, or the treatment page's picker. */
function renderLanding(main) {
  replace(main, el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Authority pages' }),
      el('p', { class: 'lede' },
        'One page per local authority: grant allocation, budgeted spend, '
        + 'treatment estimates and contracts let. ',
        'Find one by name in the search at the top of this page, by area on ',
        el('a', { href: '#/geography' }, 'the map'),
        ', or from ',
        el('a', { href: '#/treatment' }, 'the treatment page'),
        '.'))));
  return () => {};
}

async function renderOne(main, code) {
  const charts = [];
  let data;
  try {
    data = await fetchJSON(`authorities/${encodeURIComponent(code)}`);
  } catch (error) {
    replace(main, errorCard(error.message, () => renderOne(main, code)));
    return () => {};
  }

  const authority = data.authority || {};
  const type = TYPE_LABELS[authority.type] || authority.type || 'Local authority';
  const page = el('div', {},
    el('div', { class: 'hero' },
      el('p', {}, el('a', { href: '#/geography' }, '← Map of all authorities'),
        ' · ', el('a', { href: `#/compare?ons_code=${code}` },
          'Compare with other authorities →'),
        ' · ', el('a', { href: `#/relationships?ons_code=${code}` },
          'Who it commissions →')),
      el('h1', { text: authority.name || code }),
      el('p', { class: 'lede' },
        `${type} · ${authority.region || 'region not recorded'} · `,
        el('code', { text: authority.ons_code || code })),
      el('div', { class: 'hero-actions' },
        shareButton({
          title: `SectorTrace — ${authority.name || code}`,
          text: 'Explore published local-authority evidence in SectorTrace.',
          label: 'Share this authority',
        }))),
    el('details', { class: 'read-first' },
      el('summary', { text: 'How to read this authority workbench' }),
      el('p', { text: 'Grant allocation, budgeted spend, treatment estimates and contracts come from different sources. They are shown side by side, never combined into a score.' })),
    (() => {
      const meta = evidenceMeta(data);
      return findingBlock({
        finding: 'This authority page keeps grants, budgets, treatment estimates, and contracts as separate evidence layers so the reader can inspect the local picture without a composite score.',
        value: authority.name || code, evidenceStatus: meta.sources.length || meta.retrievedAt ? 'Published' : null,
        timing: { kind: meta.retrievedAt ? 'current' : 'snapshot', date: meta.retrievedAt?.slice(0, 10) },
        sources: meta.sources, retrievedAt: meta.retrievedAt?.slice(0, 10),
        caveat: 'A grant allocation and budgeted spend come from different documents and are never combined or differenced here.',
      });
    })(),
    el('div', { id: 'coverage' }),
    el('div', { id: 'grant-budget' }),
    el('div', { id: 'drilldown' }),
    el('div', { id: 'treatment' }),
    el('div', { id: 'contracts' }),
    el('div', { id: 'comparators' }));
  replace(main, page);

  renderCoverage(page.querySelector('#coverage'), data);
  renderGrantBudget(page.querySelector('#grant-budget'), data, charts);
  renderDrillDown(page.querySelector('#drilldown'), data);
  renderTreatment(page.querySelector('#treatment'), data, charts);
  renderContracts(page.querySelector('#contracts'), data, code);
  renderComparators(page.querySelector('#comparators'), data);

  return () => disposeCharts(charts);
}

// --- coverage (W-12) ---------------------------------------------------------

/* Ticks for which evidence kinds exist for this authority. A gap must read
 * as "the pipeline has not looked there", never as a zero figure — the
 * pinned caveat says it in prose and the empty chips say it in shape. */
function renderCoverage(container, data) {
  const cells = data.coverage?.cells || {};
  const labels = data.coverage?.labels || Object.keys(cells);

  replace(container, section(
    'Evidence inventory',
    'Which kinds of evidence the warehouse holds. Absence is absence of '
    + 'collection, not evidence of absence.',
    el('div', { class: 'panel' },
      pinnedCaveat(data.coverage?.caveat, 'Read before using these ticks'),
      el('div', { class: 'coverage-ticks' },
        labels.map((label) => {
          const count = cells[label] || 0;
          return el('span', {
            class: `coverage-tick${count ? ' yes' : ''}`,
            title: count ? `${num(count)} rows` : 'nothing held',
          },
            el('span', { class: 'tick-mark', 'aria-hidden': 'true', text: count ? '✓' : '○' }),
            label,
            el('span', { class: 'tick-count', text: count ? num(count) : 'none' }));
        })))));
}

// --- grant and budget (W-27) -------------------------------------------------

/* Two charts, two axes, one caveat. The allocation and its ring-fenced
 * drug-and-alcohol share are one document's figures and share the grant
 * axis; the budget is a different document and gets its own. */
function renderGrantBudget(container, data, charts) {
  const grant = data.grant?.rows || [];
  const budget = data.budget?.rows || [];
  const holder = el('div', { class: 'split' },
    el('div', { id: 'grant-chart' }),
    el('div', { id: 'budget-chart' }));

  replace(container, section(
    'Grant allocation and budgeted spend',
    'The grant is what DHSC allocated this authority; the budget is what the '
    + 'authority planned to spend. Both are shown as published, never '
    + 'combined.',
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.grant_not_budget, 'Do not compare these'),
      holder,
      el('div', {}, [
        provenanceFromRows(grant, {
          module: 'm11_public_health_grant',
          tables: ['public_health_grants'],
        }),
        provenanceFromRows(data.budget_detail?.rows || [], {
          module: 'm13_la_budgets',
          tables: ['la_revenue_budgets'],
        }),
      ].filter(Boolean)))));

  const allocation = grant.filter((r) => r.grant_type === 'allocation'
    && r.unit === 'gbp');
  const ringfenced = grant.filter((r) =>
    r.grant_type === 'of_which_is_drug_&_alcohol_ring-fenced_funding_total');

  if (allocation.length || ringfenced.length) {
    const years = [...new Set([...allocation, ...ringfenced]
      .map((r) => r.financial_year))].sort();
    const byYear = (rows) => new Map(rows.map((r) => [r.financial_year, r.amount]));
    const alloc = byYear(allocation);
    const ring = byYear(ringfenced);

    charts.push(mountChart(container.querySelector('#grant-chart'), {
      grid: { left: 8, right: 24, top: 60, bottom: 8, containLabel: true },
      title: { text: 'Public health grant', left: 0, top: 0,
        textStyle: { fontSize: 15, color: '#e6edf3' } },
      legend: { top: 30, type: 'scroll' },
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: (params) => {
          const year = params[0].axisValue;
          const status = allocation.find((r) => r.financial_year === year)
            ?.allocation_status;
          return `<strong>${escapeHtml(year)}</strong>`
            + params.map((p) => `<br>${escapeHtml(p.seriesName)}: ${gbp(p.value)}`)
              .join('')
            + (status ? `<br><span style="color:#8b949e">published as `
              + `${escapeHtml(status)}</span>` : '');
        },
      },
      xAxis: { type: 'category', data: years },
      yAxis: { type: 'value', axisLabel: { formatter: (v) => gbp(v) } },
      series: [
        { name: 'Allocation', type: 'bar', data: years.map((y) => alloc.get(y) ?? null),
          itemStyle: { color: '#2dd4bf' } },
        { name: 'Of which drug & alcohol ring-fence', type: 'bar',
          data: years.map((y) => ring.get(y) ?? null), itemStyle: { color: '#f59e0b' } },
      ],
    }, {
      aria: 'Bar chart of public health grant allocation by financial year, '
        + 'with the drug and alcohol ring-fenced share of it.',
    }));

    const latest = allocation[allocation.length - 1];
    if (latest && latest.allocation_status === 'indicative') {
      container.querySelector('#grant-chart').append(pinnedCaveat(
        `Allocations for ${latest.financial_year} are published as indicative `
        + 'and are revised later. Do not compare an indicative year with a '
        + 'confirmed one.', 'Indicative allocation'));
    }
  } else {
    replace(container.querySelector('#grant-chart'),
      noData('grant allocation', './start.sh run m11_public_health_grant'));
  }

  if (budget.length) {
    charts.push(mountChart(container.querySelector('#budget-chart'), {
      grid: { left: 8, right: 24, top: 60, bottom: 8, containLabel: true },
      title: { text: 'Budgeted public health spend', left: 0, top: 0,
        textStyle: { fontSize: 15, color: '#e6edf3' } },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      xAxis: { type: 'category', data: budget.map((r) => r.financial_year) },
      yAxis: { type: 'value', axisLabel: { formatter: (v) => gbp(v) } },
      series: [{
        name: 'Budgeted spend', type: 'bar',
        data: budget.map((r) => r.amount), itemStyle: { color: '#60a5fa' },
      }],
    }, {
      aria: 'Bar chart of budgeted public health spend by financial year.',
    }));
  } else {
    replace(container.querySelector('#budget-chart'),
      noData('budgeted public health spend', './start.sh run m13_la_budgets'));
  }
}

// --- the budget drill-down (W-27) -------------------------------------------

/* 477,199 budget lines sit behind one number on the geography page. Here the
 * lines are the section: by financial year, by section and line code as
 * MHCLG published them. Amounts only — the pinned caveat is the reason. */
function renderDrillDown(container, data) {
  const rows = data.budget_detail?.rows || [];
  const years = [...new Set(rows.map((r) => r.financial_year))].sort().reverse();
  const select = el('select', { 'aria-label': 'Financial year' });
  const holder = el('div', {});

  replace(container, section(
    'Budget lines',
    'The budgeted revenue expenditure lines this authority reported to MHCLG, '
    + 'by service section. Amounts are as published.',
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.budget_detail, 'Read before using these lines'),
      el('div', { class: 'toolbar', style: 'display:flex;gap:12px;align-items:center;margin-bottom:12px;' },
        el('label', { class: 'small muted', text: 'Financial year' }), select,
        el('span', { class: 'spacer' }),
        el('span', { text: `${num(rows.length)} lines held` })),
      holder,
      provenanceFromRows(rows, {
        module: 'm13_la_budgets', tables: ['la_revenue_budgets'],
      }) || el('span', {}))));

  replace(select, years.map((y) => el('option', { value: y, text: y })));
  select.value = years[0] || '';

  const show = (year) => {
    const filtered = rows.filter((r) => r.financial_year === year);
    replace(holder, tableCard('Budget lines', [
      { title: 'Section', field: 'section', width: 220 },
      { title: 'Line code', field: 'line_code', width: 130 },
      { title: 'Line no', field: 'line_number', width: 90 },
      { title: 'Label', field: 'column_label' },
      { title: 'Amount', field: 'amount', width: 140,
        formatter: (c) => (c.getValue() === null ? '—' : gbp(c.getValue(), { compact: false })) },
      { title: 'As published', field: 'value_text', width: 160 },
    ], filtered, { height: 420 }));
  };
  select.addEventListener('change', () => show(select.value));
  show(select.value);
}

// --- treatment ---------------------------------------------------------------

/* The estimates with their paired intervals, straight from the functions the
 * treatment page itself uses. The NDTMS charting rule applies here too: only
 * the figures the source published an interval for are drawn — a confidence
 * interval on the wrong estimate is invented, which is worse than an absent
 * one. */
function renderTreatment(container, data, charts) {
  const ft = data.treatment?.fingertips || {};
  const nd = data.treatment?.ndtms || {};
  const holder = el('div', {});

  replace(container, section(
    'Treatment',
    'Treatment demand indicators for this authority, with the confidence '
    + 'intervals the sources published.',
    el('div', { class: 'panel' },
      pinnedCaveat(ft.caveat, 'Read this with the figures'),
      holder)));

  const indicators = ft.indicators || [];
  if (!indicators.length) {
    replace(holder, noData('treatment indicators',
      './start.sh run m12_fingertips'));
    return;
  }

  // One chart per indicator under the topic, so an authority with several
  // published series sees all of them rather than only the first.
  const seriesByIndicator = (ft.series || []).reduce((map, row) => {
    if (!map.has(row.indicator_id)) map.set(row.indicator_id, []);
    map.get(row.indicator_id).push(row);
    return map;
  }, new Map());

  for (const indicator of indicators) {
    const rows = seriesByIndicator.get(indicator.indicator_id) || [];
    const england = (ft.england_series || [])
      .filter((r) => r.indicator_id === indicator.indicator_id);
    if (!rows.length && !england.length) continue;

    const chartHolder = el('div', {});
    holder.append(chartHolder);
    drawIndicator(chartHolder, indicator, rows, england, charts);
  }

  // The NDTMS estimates belong to this authority, not to any one indicator,
  // so they are drawn once, after the indicator charts.
  drawNdtms(holder, nd, charts);
}

function drawIndicator(container, indicator, rows, england, charts) {
  const periods = [...new Set([...rows, ...england].map((r) => r.time_period))]
    .sort((a, b) => String(a).localeCompare(String(b)));
  const byPeriod = new Map(rows.map((r) => [r.time_period, r]));
  const values = periods.map((p) => byPeriod.get(p)?.value ?? null);
  const lower = periods.map((p) => byPeriod.get(p)?.lower_ci_95 ?? null);
  const upper = periods.map((p) => byPeriod.get(p)?.upper_ci_95 ?? null);

  const series = [];
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
    name: rows[0]?.authority_name || indicator.indicator_name,
    type: 'line', symbol: 'circle', symbolSize: 8, connectNulls: true,
    data: values,
  });
  if (england.length) {
    const englandByPeriod = new Map(england.map((r) => [r.time_period, r.value]));
    series.push({
      name: 'England', type: 'line', symbol: 'diamond', symbolSize: 7,
      lineStyle: { type: 'dashed', width: 2 },
      data: periods.map((p) => englandByPeriod.get(p) ?? null),
    });
  }

  charts.push(mountChart(container, {
    title: {
      text: indicator.indicator_name, subtext: indicator.unit || '',
      left: 0, top: 0, textStyle: { fontSize: 15, color: '#e6edf3' },
      subtextStyle: { color: '#8b949e' },
    },
    grid: { top: 76 },
    legend: { top: 46, type: 'scroll' },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: periods },
    yAxis: { type: 'value', name: indicator.unit || '' },
    series,
  }, {
    aria: `Line chart of ${indicator.indicator_name} for this authority, `
      + 'with its 95% confidence interval, compared with the England figure.',
  }));
}

function drawNdtms(container, data, charts) {
  const estimates = data.estimates || [];
  const charted = estimates.filter((e) => e.has_interval);
  const rest = estimates.filter((e) => !e.has_interval);
  const other = data.other_rows || [];

  // The chart and the table are independent: an authority whose estimates
  // all lack a pairable interval still gets its "other published values"
  // table, because those rows are real figures that must not vanish.
  if (charted.length) {
    const labels = charted.map((e) => (e.time_period
      ? `${e.measure} · ${e.time_period}`
      : `${e.measure} · in ${e.published_in} report`));

    charts.push(mountChart(container, {
    grid: { left: 220, top: 30, right: 40, bottom: 40 },
    tooltip: {
      trigger: 'item',
      formatter: (p) => {
        const e = charted[p.dataIndex];
        return `<strong>${escapeHtml(e.measure)}</strong><br>`
          + `${escapeHtml(String(e.value_text ?? e.value))}<br>`
          + `<span style="color:#8b949e">95% CI ${escapeHtml(String(e.lower))}`
          + ` to ${escapeHtml(String(e.upper))}</span>`;
      },
    },
    xAxis: { type: 'value', name: 'published value' },
    yAxis: { type: 'category', data: labels,
      axisLabel: { width: 210, overflow: 'truncate' } },
    series: [
      {
        name: '95% confidence interval', type: 'custom', silent: true,
        renderItem: (params, api) => {
          const estimate = charted[api.value(0)];
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
        data: charted.map((e, i) => [i, e.value]),
      },
      {
        name: 'published estimate', type: 'scatter', symbolSize: 11,
        itemStyle: { color: '#38bdf8' },
        data: charted.map((e, i) => [e.value, i]),
      },
    ],
  }, {
    aria: `${charted.length} NDTMS estimates for this authority, each drawn `
      + 'as a point with the 95% confidence interval the source published '
      + 'for it.',
  }));
  }

  if (rest.length || other.length) {
    const tableHolder = el('div', {});
    container.append(tableHolder);
    replace(tableHolder, tableCard('NDTMS other published values', [
      { title: 'Dataset', field: 'dataset' },
      { title: 'Measure', field: 'measure' },
      { title: 'Period', field: 'time_period', width: 170 },
      { title: 'In publication', field: 'published_in', width: 120 },
      { title: 'Published as', field: 'value_text', width: 160 },
    ], [...rest, ...other], { height: 240 }));
  }
}

// --- contracts ---------------------------------------------------------------

function renderContracts(container, data, code) {
  const held = data.contracts || {};
  const notices = held.notices || [];

  replace(container, section(
    'Contracts let',
    `${num(held.total)} notices with this authority as buyer, of the `
    + `${num(notices.length)} shown here.`,
    el('div', { class: 'panel' },
      pinnedCaveat(held.caveats?.value, 'Read with the figures'),
      tableCard('Notices', [
        { title: 'Title', field: 'title' },
        { title: 'Published', field: 'date_published', width: 120,
          formatter: (c) => isoDate(c.getValue()) },
        { title: 'Supplier', field: 'supplier_name_raw' },
        { title: 'Value', field: 'value_core', width: 120,
          formatter: (c) => gbp(c.getValue()) },
        { title: 'Procedure', field: 'procedure_type', width: 120 },
        { title: 'PSR', field: 'psr_basis', width: 70,
          formatter: (c) => (c.getValue() ? 'yes' : '') },
        { title: 'Notice', field: 'notice_link', headerFilter: false,
          formatter: (c) => {
            const url = c.getValue();
            if (!url) return '';
            const row = c.getRow().getData();
            return el('a', { href: url, target: '_blank', rel: 'noopener noreferrer' },
              row.notice_link_basis === 'constructed' ? 'notice ↗ (built from id)' : 'notice ↗');
          } },
      ], notices, {
        height: 400,
        exportEndpoint: 'contracts',
        exportParams: { buyer_ons_code: code },
        total: held.total,
      }),
      provenanceFromRows(notices, {
        module: 'm01_procurement', tables: ['contracts', 'supplier_aliases'],
      }) || el('span', {}))));
}

// --- comparators (Modules 29-31) ---------------------------------------------

/* Rough sleeping, statutory homelessness and temporary accommodation —
 * requested and built specifically to sit beside this authority's own
 * substance-misuse evidence, because the two are widely documented as
 * overlapping populations. Three separate tables, three separate caveats,
 * never a combined figure: the whole point of a comparator is that the
 * reader draws the inference, not this page. */
function renderComparators(container, data) {
  const comparators = data.comparators || {};
  const roughSleeping = comparators.rough_sleeping?.rows || [];
  const statutoryHomelessness = comparators.statutory_homelessness?.rows || [];
  const temporaryAccommodation = comparators.temporary_accommodation?.rows || [];

  if (!roughSleeping.length && !statutoryHomelessness.length
    && !temporaryAccommodation.length) {
    replace(container, section(
      'Comparators',
      'Rough sleeping and homelessness figures for this authority, shown '
      + 'beside its substance-misuse evidence because the two populations '
      + 'are widely documented to overlap.',
      noData('rough sleeping and homelessness comparators',
        './start.sh run m29_rough_sleeping m30_statutory_homelessness m31_temporary_accommodation')));
    return;
  }

  replace(container, section(
    'Comparators',
    'Rough sleeping and homelessness figures for this authority, shown '
    + 'beside its substance-misuse evidence above because the two '
    + 'populations are widely documented to overlap — never combined, '
    + 'ratioed or scored against it.',
    el('div', { class: 'panel' },
      renderRoughSleeping(roughSleeping, comparators.rough_sleeping?.caveat),
      renderStatutoryHomelessness(statutoryHomelessness,
        comparators.statutory_homelessness?.caveat),
      renderTemporaryAccommodation(temporaryAccommodation,
        comparators.temporary_accommodation?.caveat))));
}

function renderRoughSleeping(rows, caveat) {
  if (!rows.length) return el('span', {});
  return el('div', { style: 'margin-bottom:20px;' },
    el('h3', { class: 'small muted', text: 'Rough sleeping (MHCLG annual snapshot)' }),
    pinnedCaveat(caveat, 'Read before comparing'),
    tableCard('Rough sleeping', [
      { title: 'Year', field: 'snapshot_year', width: 90 },
      { title: 'Estimated count', field: 'count_text', width: 140 },
      { title: 'Rate per 100k', field: 'rate_text', width: 130 },
    ], rows, { height: Math.min(300, 60 + rows.length * 32) }),
    provenanceFromRows(rows, {
      module: 'm29_rough_sleeping', tables: ['rough_sleeping_snapshot'],
    }) || el('span', {}));
}

function renderStatutoryHomelessness(rows, caveat) {
  if (!rows.length) return el('span', {});
  return el('div', { style: 'margin-bottom:20px;' },
    el('h3', { class: 'small muted', text: 'Statutory homelessness (MHCLG H-CLIC, quarterly)' }),
    pinnedCaveat(caveat, 'Read before comparing'),
    tableCard('Statutory homelessness', [
      { title: 'Quarter', field: 'quarter_label', width: 200 },
      { title: 'Households assessed', field: 'total_initial_assessments_text', width: 160 },
      { title: 'Owed a duty', field: 'total_owed_duty', width: 120 },
      { title: 'Prevention duty', field: 'prevention_duty_owed', width: 130 },
      { title: 'Relief duty', field: 'relief_duty_owed', width: 110 },
    ], rows, { height: Math.min(300, 60 + rows.length * 32) }),
    provenanceFromRows(rows, {
      module: 'm30_statutory_homelessness', tables: ['statutory_homelessness_snapshot'],
    }) || el('span', {}));
}

function renderTemporaryAccommodation(rows, caveat) {
  if (!rows.length) return el('span', {});
  return el('div', {},
    el('h3', { class: 'small muted', text: 'Temporary accommodation (MHCLG H-CLIC, quarterly)' }),
    pinnedCaveat(caveat, 'Read before comparing'),
    tableCard('Temporary accommodation', [
      { title: 'Quarter', field: 'quarter_label', width: 200 },
      { title: 'Households in TA', field: 'total_households_ta_text', width: 150 },
      { title: 'With children', field: 'households_ta_with_children', width: 130 },
      { title: 'Children in TA', field: 'children_in_ta', width: 130 },
    ], rows, { height: Math.min(300, 60 + rows.length * 32) }),
    provenanceFromRows(rows, {
      module: 'm31_temporary_accommodation', tables: ['temporary_accommodation_snapshot'],
    }) || el('span', {}));
}
