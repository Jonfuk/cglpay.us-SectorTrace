/* Pay evidence — the centre of the campaign case, and the page most likely to
 * be quoted out of context.
 *
 * Every figure here has a documented way of being misread, so each section
 * carries a caveat that cannot be dismissed rather than one behind a click.
 * The indicative wage in particular is not a salary and the page says so in
 * the same eyeline as the chart.
 */
'use strict';

import { el, replace, fetchJSON, filterParams, num, gbp, isoDate } from '/app.js';
import { section, pinnedCaveat, noData, errorCard, mountChart, disposeCharts,
          provenanceFromRows, provenance, tableCard, symbolFor, escapeHtml,
          truncate } from '/js/components.js';

export async function render(main) {
  const charts = [];
  let data;
  try {
    data = await fetchJSON('pay', filterParams());
  } catch (error) {
    replace(main, errorCard(error.message, () => render(main)));
    return () => {};
  }

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Pay evidence' }),
      el('p', { class: 'lede' },
        'Published pay evidence and labour-market comparators, kept in their ',
        'own layers. None is a payroll, and this portal does not turn unlike ',
        'sources into a single pay figure.')),
    el('div', { id: 'wage' }),
    el('div', { id: 'adverts' }),
    el('div', { id: 'published-pay' }),
    el('div', { id: 'benchmarks' }),
    el('div', { id: 'census' }));
  replace(main, page);

  renderWage(page.querySelector('#wage'), data, charts);
  renderAdverts(page.querySelector('#adverts'), data, charts);
  renderPublishedPay(page.querySelector('#published-pay'), data);
  renderBenchmarks(page.querySelector('#benchmarks'), data);
  renderCensus(page.querySelector('#census'), data, charts);

  return () => disposeCharts(charts);
}

// --- 2c. provider-published and statutory pay evidence ---------------------

function renderPublishedPay(container, data) {
  const rates = data.statutory_pay_rates || [];
  const published = data.provider_published_pay || [];
  const accreditations = data.living_wage_accreditations || [];
  const genderPayGap = data.gender_pay_gap_reports || [];

  replace(container, section(
    'Published pay and employment evidence',
    'Statutory hourly rates, provider-owned pages, Living Wage Foundation checks and gender pay gap filings. These are separate records, not a combined comparison.',
    el('div', { class: 'grid two' },
      el('div', { class: 'panel' },
        el('h3', { text: 'Statutory minimum rates' }),
        pinnedCaveat(data.caveats?.statutory_pay_rates_note, 'Hourly floors only'),
        rates.length ? tableCard('Published rates', [
          { title: 'Period', field: 'period_label' },
          { title: 'Band', field: 'band_label' },
          { title: 'Role', field: 'band_role' },
          { title: 'Rate (hourly)', field: 'amount', formatter: (c) => gbp(c.getValue(), { compact: false }) },
          { title: 'Published value', field: 'value_text' },
        ], rates, { height: 280 }) : noData('statutory pay rates', './start.sh run m17_statutory_pay_rates'),
        provenanceFromRows(rates, { tables: ['statutory_pay_rates'], module: 'm17_statutory_pay_rates' })),
      el('div', { class: 'panel' },
        el('h3', { text: 'Living Wage Foundation checks' }),
        pinnedCaveat(data.caveats?.living_wage_note, 'How to read “not found”'),
        accreditations.length ? tableCard('Accreditation checks', [
          { title: 'Provider', field: 'canonical_name' },
          { title: 'Checked name', field: 'searched_variant' },
          { title: 'Result', field: 'accredited', formatter: (c) => c.getValue() ? 'Exact name found on register' : 'Not found under checked name' },
          { title: 'Register name', field: 'employer_name' },
          { title: 'Retrieved', field: 'retrieved_at', formatter: (c) => isoDate(c.getValue()) },
        ], accreditations, { height: 280 }) : noData('Living Wage Foundation checks', './start.sh run m18_living_wage'),
        provenanceFromRows(accreditations, { tables: ['living_wage_accreditations'], module: 'm18_living_wage' }))),
    el('div', { class: 'panel' },
      el('h3', { text: 'Pay published on provider-owned pages' }),
      pinnedCaveat(data.caveats?.provider_published_pay_note, 'An offer is not a payroll'),
      published.length ? tableCard('Provider-published pay', [
        { title: 'Provider', field: 'canonical_name' },
        { title: 'Page section', field: 'section' },
        { title: 'Published pay', field: 'salary_raw' },
        { title: 'Period', field: 'salary_period' },
        { title: 'Context', field: 'mention_text' },
      ], published, { height: 320 }) : noData('provider-owned pay pages', './start.sh run m22_provider_pay_pages'),
      provenanceFromRows(published, { tables: ['provider_pay_mentions'], module: 'm22_provider_pay_pages' })),
    el('div', { class: 'panel' },
      el('h3', { text: 'Gender pay gap filings' }),
      pinnedCaveat(data.caveats?.gender_pay_gap_note, 'Missing is not zero'),
      genderPayGap.length ? tableCard('Matched filings', [
        { title: 'Provider', field: 'canonical_name' },
        { title: 'Reporting year', field: 'reporting_year_label' },
        { title: 'Employer', field: 'employer_name' },
        { title: 'Median hourly gap', field: 'diff_median_hourly_percent', formatter: (c) => c.getValue() == null ? '—' : `${c.getValue()}%` },
        { title: 'Mean hourly gap', field: 'diff_mean_hourly_percent', formatter: (c) => c.getValue() == null ? '—' : `${c.getValue()}%` },
        { title: 'Employer size', field: 'employer_size' },
      ], genderPayGap, { height: 320 }) : noData('matched gender pay gap filings', './start.sh run m20_gender_pay_gap'),
      provenanceFromRows(genderPayGap, { tables: ['gender_pay_gap_reports'], module: 'm20_gender_pay_gap' }))));
}

// --- 2d. contextual comparators ---------------------------------------------

function renderBenchmarks(container, data) {
  const ashe = data.ons_ashe_observations || [];
  const skills = data.skills_for_care_estimates || [];

  replace(container, section(
    'Pay and workforce comparators',
    'Published benchmarks for the labour market. They can be read beside compatible evidence, but this portal does not calculate gaps, ratios or trends from them.',
    el('div', { class: 'grid two' },
      el('div', { class: 'panel' },
        el('h3', { text: 'ONS ASHE median hourly pay' }),
        pinnedCaveat(data.caveats?.ashe_note, 'Survey comparator, not a calculated gap'),
        ashe.length ? tableCard('ASHE observations', [
          { title: 'Year', field: 'time' },
          { title: 'Dimension', field: 'dimension_kind' },
          { title: 'Group', field: 'dimension_label' },
          { title: 'Geography', field: 'geography_label' },
          { title: 'Median hourly pay', field: 'value', formatter: (c) => gbp(c.getValue(), { compact: false }) },
          { title: 'Unit', field: 'unit_of_measure' },
        ], ashe, { height: 320 }) : noData('ONS ASHE observations', './start.sh run m21_ons_ashe'),
        provenanceFromRows(ashe, { tables: ['ons_ashe_observations'], module: 'm21_ons_ashe' })),
      el('div', { class: 'panel' },
        el('h3', { text: 'Skills for Care estimates' }),
        pinnedCaveat(data.caveats?.skills_for_care_note, 'Labour-market comparator only'),
        skills.length ? tableCard('National estimates', [
          { title: 'Year', field: 'year' },
          { title: 'Sector', field: 'sector' },
          { title: 'Service', field: 'service' },
          { title: 'Role', field: 'job_role' },
          { title: 'Hourly pay', field: 'hourly_pay', formatter: (c) => gbp(c.getValue(), { compact: false }) },
          { title: 'FTE annual pay', field: 'fte_annual_pay', formatter: (c) => gbp(c.getValue(), { compact: false }) },
          { title: 'Turnover', field: 'turnover_rate', formatter: (c) => c.getValue() == null ? '—' : `${c.getValue()}%` },
        ], skills, { height: 320 }) : noData('Skills for Care estimates', './start.sh run m25_skills_for_care'),
        provenanceFromRows(skills, { tables: ['skills_for_care_estimates'], module: 'm25_skills_for_care' })))));
}

// --- 2a. indicative wage per employee ----------------------------------------

function renderWage(container, data, charts) {
  const rows = data.charity_wage_series || [];
  const holder = el('div', {});

  replace(container, section(
    'Indicative wage per employee',
    'Wages and salaries from published charity accounts, over the average '
    + 'employee count in the same accounts.',
    el('div', { class: 'panel' },
      holder,
      // Pinned, not collapsible. This figure reads like a salary and is not
      // one, and the difference is the single most misquotable thing here.
      pinnedCaveat(data.caveats?.indicative_wage_note, 'This is not a salary'),
      provenanceFromRows(rows, { tables: ['charity_financials'], module: 'm03_charity_finance' }))));

  if (!rows.length) {
    replace(holder, noData('charity accounts', './start.sh run m03_charity_finance'));
    return;
  }

  const providers = [...new Set(rows.map((r) => r.canonical_name || r.charity_number))];
  const years = [...new Set(rows.map((r) => r.financial_year_end))].sort();

  const seriesFor = (field, suffix) => providers.map((name, index) => ({
    name: `${name} — ${suffix}`,
    type: 'line',
    symbol: symbolFor(index),
    lineStyle: suffix.includes('FTE') ? { type: 'dashed' } : {},
    connectNulls: true,
    data: years.map((year) => {
      const row = rows.find((r) =>
        (r.canonical_name || r.charity_number) === name && r.financial_year_end === year);
      return row ? row[field] : null;
    }),
  }));

  charts.push(mountChart(holder, {
    legend: { top: 0, type: 'scroll' },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => (v === null ? '—' : gbp(v, { compact: false })),
    },
    xAxis: { type: 'category', data: years.map(isoDate) },
    yAxis: { type: 'value', name: '£ per employee', axisLabel: { formatter: (v) => gbp(v) } },
    series: [...seriesFor('indicative_wage_per_head', 'per head'),
      ...seriesFor('indicative_wage_per_fte', 'per FTE')],
  }, {
    aria: 'Line chart of indicative wage per employee by financial year. '
      + 'Headcount and full-time-equivalent denominators are shown separately '
      + 'because they differ materially.',
  }));

  container.append(tableCard('Charity accounts — wages and employees', [
    { title: 'Provider', field: 'canonical_name' },
    { title: 'Charity no.', field: 'charity_number' },
    { title: 'Year end', field: 'financial_year_end' },
    { title: 'Wages & salaries', field: 'wages_and_salaries',
      formatter: (c) => gbp(c.getValue(), { compact: false }) },
    { title: 'Avg employees', field: 'average_employees' },
    { title: 'Avg FTE', field: 'average_employees_fte' },
    { title: 'Per head', field: 'indicative_wage_per_head',
      formatter: (c) => gbp(c.getValue(), { compact: false }) },
    { title: 'Per FTE', field: 'indicative_wage_per_fte',
      formatter: (c) => gbp(c.getValue(), { compact: false }) },
  ], rows, { exportEndpoint: 'pay', exportParams: filterParams(), height: 300 }));
}

// --- 2b. NHS Jobs advertised pay ---------------------------------------------

function renderAdverts(container, data, charts) {
  const adverts = data.nhs_job_adverts || [];
  const bands = data.nhs_job_by_band || [];
  const repeats = data.repeat_advertised_roles || [];
  const scatterHolder = el('div', {});
  const bandHolder = el('div', {});

  replace(container, section(
    'Advertised pay (NHS Jobs)',
    'Salaries as advertised, not as paid. One advert is one vacancy the '
    + 'employer chose to publish on NHS Jobs.',
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.nhs_jobs_floor_note, 'These counts are a floor'),
      el('div', { class: 'grid two' },
        el('div', {}, el('h3', { text: 'Advertised salary distribution' }), bandHolder),
        el('div', {}, el('h3', { text: 'Adverts over time' }), scatterHolder)),
      provenanceFromRows(adverts, { tables: ['nhs_job_adverts'], module: 'm16_nhs_jobs' }))));

  if (!adverts.length) {
    replace(bandHolder, noData('NHS Jobs adverts', './start.sh run m16_nhs_jobs'));
    replace(scatterHolder, noData('NHS Jobs adverts', './start.sh run m16_nhs_jobs'));
    return;
  }

  charts.push(mountChart(bandHolder, {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'category', data: bands.map((b) => b.salary_band_label) },
    yAxis: { type: 'value', name: 'adverts' },
    series: [{ type: 'bar', data: bands.map((b) => b.count) }],
  }, {
    height: 'short',
    aria: 'Bar chart of advertised annual salary bands. Hourly-rate adverts '
      + 'are excluded because they cannot be banded against annual figures.',
  }));

  const annual = adverts.filter((a) => a.salary_period === 'year' && a.salary_min);
  const byProvider = [...new Set(annual.map((a) => a.canonical_name || a.provider_key))];

  charts.push(mountChart(scatterHolder, {
    legend: { top: 0, type: 'scroll' },
    tooltip: {
      formatter: (p) => {
        const row = p.data[2];
        return [
          `<strong>${escapeHtml(row.job_title || '')}</strong>`,
          escapeHtml(row.canonical_name || row.provider_key || ''),
          escapeHtml(row.salary_raw || ''),
          escapeHtml(isoDate(row.posted_date)),
        ].join('<br>');
      },
    },
    xAxis: { type: 'time', name: 'posted' },
    yAxis: { type: 'value', name: 'advertised minimum (£)', axisLabel: { formatter: (v) => gbp(v) } },
    series: byProvider.map((name, index) => ({
      name,
      type: 'scatter',
      symbol: symbolFor(index),
      symbolSize: 9,
      data: annual
        .filter((a) => (a.canonical_name || a.provider_key) === name)
        .map((a) => [a.posted_date, a.salary_min, a]),
    })),
  }, {
    height: 'short',
    aria: 'Scatter chart of advertised minimum salary against the date each '
      + 'advert was posted.',
  }));

  if (repeats.length) {
    container.append(tableCard('Repeatedly advertised roles', [
      { title: 'Provider', field: 'provider_key' },
      { title: 'Role (normalised)', field: 'job_title_normalised' },
      { title: 'Adverts', field: 'advert_count' },
      { title: 'First posted', field: 'first_posted_date', formatter: (c) => isoDate(c.getValue()) },
      { title: 'Last posted', field: 'last_posted_date', formatter: (c) => isoDate(c.getValue()) },
      { title: 'Lowest advertised', field: 'lowest_advertised', formatter: (c) => gbp(c.getValue(), { compact: false }) },
      { title: 'Highest advertised', field: 'highest_advertised', formatter: (c) => gbp(c.getValue(), { compact: false }) },
    ], repeats, { height: 280 }));
    container.append(el('p', { class: 'small muted' },
      'A role advertised repeatedly is a role advertised repeatedly. It is '
      + 'consistent with turnover, with growth, and with a post that was '
      + 'never filled — this pipeline does not distinguish between them.'));
  }
}

// --- 2c. workforce census ----------------------------------------------------

/** The verification caveat that is true right now, or none once all of them
 *  have been checked.
 *
 *  Three states rather than two, because a census metric became something a
 *  person can check one at a time (migration 0033) and a corpus that is partly
 *  checked is the state it will be in for most of its life. */
function censusCaveat(data) {
  const total = data.census_total ?? (data.workforce_census || []).length;
  const verified = data.census_verified_count ?? 0;
  if (!total || verified >= total) return null;
  return verified === 0
    ? pinnedCaveat(data.caveats?.census_unverified_note,
                    'Every figure below is unverified')
    : pinnedCaveat(data.caveats?.census_partly_verified_note,
                    `${verified} of ${total} figures below `
                    + `${verified === 1 ? 'has' : 'have'} been checked`);
}

function renderCensus(container, data, charts) {
  const rows = data.workforce_census || [];
  const holder = el('div', {});

  replace(container, section(
    'Workforce census indicators',
    'Vacancy, turnover and headcount measures as published in the sector '
    + 'workforce census.',
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.census_comparability_note, 'Not comparable between years'),
      // Pinned until nothing below is unverified, not until something is
      // verified. The chart draws every figure whatever its flag, so the
      // caveat that used to vanish the moment one figure was checked would
      // have left the other sixty-seven on screen with nothing said about
      // them. The verified count goes in the heading so the reader can see
      // which way the number is moving.
      censusCaveat(data),
      holder,
      provenanceFromRows(rows, { tables: ['workforce_census_metrics'], module: 'm06_workforce_census' }))));

  if (!rows.length) {
    replace(holder, noData('workforce census metrics', './start.sh run m06_workforce_census'));
    return;
  }

  const years = [...new Set(rows.map((r) => r.census_year))].sort();
  const metrics = [...new Set(rows.map((r) => r.metric))];

  charts.push(mountChart(holder, {
    legend: { top: 0 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: years },
    yAxis: { type: 'value' },
    series: metrics.map((metric, index) => ({
      name: metric,
      type: 'bar',
      symbol: symbolFor(index),
      data: years.map((year) => {
        const matching = rows.filter((r) => r.census_year === year && r.metric === metric);
        // One bar per (year, metric). Where the census reports several
        // segments, the highest is shown and the table below carries them all
        // — averaging segments would invent a figure the census never
        // published.
        return matching.length ? Math.max(...matching.map((m) => m.value ?? 0)) : null;
      }),
    })),
  }, {
    // The screen-reader description carries the verification state too. A
    // caveat that only exists as a visual panel beside the chart is a caveat
    // half the audience does not get.
    aria: 'Grouped bar chart of workforce census metrics by census year. '
      + `${data.census_verified_count ?? 0} of `
      + `${data.census_total ?? rows.length} figures have been checked against `
      + 'the page they were parsed from; the rest are unverified. Figures are '
      + 'not comparable between census years.',
  }));

  container.append(tableCard('Census metrics', [
    { title: 'Year', field: 'census_year' },
    { title: 'Metric', field: 'metric' },
    { title: 'Segment', field: 'workforce_segment' },
    { title: 'Value', field: 'value' },
    { title: 'Unit', field: 'unit' },
    { title: 'Verified', field: 'verified',
      formatter: (c) => (c.getValue() ? 'yes' : 'AWAITING VERIFICATION') },
    { title: 'Source page', field: 'source_page' },
  ], rows, {
    height: 320,
    rowClass: (row) => (row.verified ? null : 'unverified-row'),
  }));
}
