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
          truncate, shareButton, findingBlock, evidenceMeta, revealOnScroll } from '/js/components.js';

/* BETA-070 workforce pay explorer.
 *
 * The page already grouped pay evidence into source-specific panels; this adds
 * a control strip that narrows those panels by source group, role text and pay
 * unit, with the state carried in the hash query so a filtered view is a link.
 * It combines nothing: `source` picks exactly one group to show, `role` is a
 * substring match per source, `pay_unit` keeps rows explicitly carrying that
 * unit. Counts on the chips are the server's post-filter `source_groups`
 * index, not a figure to quote. */

const EXPLORER_KEYS = ['source', 'role', 'pay_unit'];

function readExplorer(params) {
  const q = params || new URLSearchParams(location.hash.split('?')[1] || '');
  return {
    source: q.get('source') || '',
    role: q.get('role') || '',
    pay_unit: q.get('pay_unit') || '',
  };
}

function setExplorer(patch) {
  const q = new URLSearchParams(location.hash.split('?')[1] || '');
  for (const [k, v] of Object.entries(patch)) {
    if (v) q.set(k, v); else q.delete(k);
  }
  const query = q.toString();
  location.hash = `#/pay${query ? `?${query}` : ''}`;
}

function explorerStrip(data, current) {
  const groups = data.source_groups || [];
  const avail = data.filters_available || { roles: [], pay_units: [] };
  const total = groups.reduce((n, g) => n + (g.count || 0), 0);

  const chip = (key, label, count, active) => el('button', {
    type: 'button',
    class: `filter-chip${active ? ' is-active' : ''}`,
    'aria-pressed': String(active),
    onclick: () => setExplorer({ source: key }),
  }, `${label} · ${num(count)}`);

  const roleList = el('datalist', { id: 'pay-role-options' },
    ...(avail.roles || []).map((r) => el('option', { value: r })));

  const roleInput = el('input', {
    type: 'search', list: 'pay-role-options', value: current.role,
    placeholder: 'Any role', 'aria-label': 'Filter by role text',
    onchange: (e) => setExplorer({ role: e.target.value.trim() }),
  });

  const unitSelect = el('select', {
    'aria-label': 'Pay unit',
    onchange: (e) => setExplorer({ pay_unit: e.target.value }),
  },
    el('option', { value: '', text: 'Any pay unit' }),
    ...(avail.pay_units || []).map((u) =>
      el('option', { value: u, text: u[0].toUpperCase() + u.slice(1), selected: current.pay_unit === u })));

  const activeBits = [];
  if (current.source) {
    const g = groups.find((x) => x.key === current.source);
    activeBits.push(`Source: ${g ? g.label : current.source}`);
  }
  if (current.role) activeBits.push(`Role: ${current.role}`);
  if (current.pay_unit) activeBits.push(`Unit: ${current.pay_unit}`);

  return el('div', { class: 'pay-explorer', role: 'region', 'aria-label': 'Pay evidence explorer' },
    el('div', { class: 'pay-explorer-groups' },
      chip('', 'All sources', total, !current.source),
      ...groups.map((g) => chip(g.key, g.label, g.count, current.source === g.key))),
    el('div', { class: 'pay-explorer-fields' },
      el('label', {}, 'Role ', roleInput), roleList,
      el('label', {}, 'Unit ', unitSelect),
      activeBits.length
        ? el('button', { type: 'button', class: 'filter-clear',
            onclick: () => setExplorer({ source: '', role: '', pay_unit: '' }) }, 'Clear explorer')
        : null),
    activeBits.length
      ? el('p', { class: 'small muted', text: `Showing ${activeBits.join(' · ')}. Sources are never combined.` })
      : null);
}

function takeaway(status, statusClass, text) {
  return el('div', { class: 'takeaway' },
    el('span', { class: 'badge ' + statusClass, text: status }),
    el('p', { text: text }));
}

function scrollToLayer(id) {
  const target = document.getElementById(id);
  if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

export async function render(main, { params = null } = {}) {
  const charts = [];
  const explorer = readExplorer(params);
  let data;
  try {
    data = await fetchJSON('pay', { ...filterParams(), ...explorer });
  } catch (error) {
    replace(main, errorCard(error, () => render(main, { params })));
    return () => {};
  }
  // When a single source group is selected the page shows only that group's
  // section — "focused", the word in the objective. `null` shows all four.
  const only = explorer.source || null;
  const show = (id) => !only || only === id;

  const page = el('div', {},
    el('div', { class: 'hero hero-animated' },
      el('h1', { text: 'Pay & benchmarks' }),
      el('p', { class: 'lede' },
        'Explore published pay, advertised roles and statutory floors. Each source layer answers a different question, so they are not combined into one pay score.'),
      el('div', { class: 'hero-actions' },
        shareButton({
          title: 'SectorTrace pay evidence',
          text: 'Explore this selected SectorTrace pay evidence view with its source and caveat context.',
          label: 'Share selected view',
        })),
      el('nav', { class: 'section-links', 'aria-label': 'Pay evidence layers' },
        el('button', { type: 'button', onclick: () => scrollToLayer('wage') }, 'Indicative wage'),
        el('button', { type: 'button', onclick: () => scrollToLayer('adverts') }, 'Advertised roles'),
        el('button', { type: 'button', onclick: () => scrollToLayer('published-pay') }, 'Published & statutory pay'),
        el('button', { type: 'button', onclick: () => scrollToLayer('benchmarks') }, 'External comparators'))),
    explorerStrip(data, explorer),
    (() => {
      const meta = evidenceMeta(data);
      return findingBlock({
        finding: 'Pay evidence is a set of published signals rather than a payroll measure: provider pages, advertised roles, statutory floors, and benchmarks answer different questions.',
        value: `${num(Object.values(data).filter(Array.isArray).reduce((n, rows) => n + rows.length, 0))} published rows`,
        evidenceStatus: meta.sources.length || meta.retrievedAt ? 'Published' : null,
        timing: { kind: meta.retrievedAt ? 'current' : 'snapshot', date: meta.retrievedAt?.slice(0, 10) },
        sources: meta.sources, retrievedAt: meta.retrievedAt?.slice(0, 10),
        caveat: 'None of these layers is payroll data, and the portal does not combine unlike sources into a pay score.',
      });
    })(),
    el('details', { class: 'read-first' },
      el('summary', { text: 'How to read pay evidence' }),
      el('p', { text: 'Charity accounts provide an indicative wage measure; NHS Jobs records advertised vacancies; provider pages record what an organisation published; statutory rates are legal hourly floors.' }),
      el('p', { text: 'None is payroll data. Labour-market benchmarks provide context only, and the portal does not calculate gaps, ratios, or a combined trend from unlike sources.' })),
    show('indicative_wage') ? el('div', { id: 'wage' }) : null,
    show('advertised_roles') ? el('div', { id: 'adverts' }) : null,
    show('published_statutory') ? el('div', { id: 'published-pay' }) : null,
    show('external_comparators') ? el('div', { id: 'benchmarks' }) : null,
    only === 'workforce_census' ? el('div', { id: 'census' }) : null,
    only && !['indicative_wage', 'advertised_roles', 'published_statutory',
             'external_comparators', 'workforce_census'].includes(only)
      ? el('p', { class: 'small muted', text: 'Unknown source group.' }) : null);
  replace(main, page);

  if (show('indicative_wage')) renderWage(page.querySelector('#wage'), data, charts);
  if (show('advertised_roles')) renderAdverts(page.querySelector('#adverts'), data, charts);
  if (show('published_statutory')) renderPublishedPay(page.querySelector('#published-pay'), data, charts);
  if (show('external_comparators')) renderBenchmarks(page.querySelector('#benchmarks'), data);
  if (only === 'workforce_census') renderCensus(page.querySelector('#census'), data);

  revealOnScroll(page);
  return () => disposeCharts(charts);
}

// --- workforce census (BETA-070: was fetched but unrendered on this page) ---

function renderCensus(container, data) {
  const rows = data.workforce_census || [];
  const note = data.census_all_unverified
    ? data.caveats?.census_unverified_note
    : (data.census_verified_count < data.census_total
        ? data.caveats?.census_partly_verified_note
        : data.caveats?.census_comparability_note);
  replace(container, section(
    'Workforce census measures',
    'Published workforce metrics (vacancy, turnover and similar) as recorded '
    + 'by the source. Segments and years are not differenced or combined.',
    pinnedCaveat(note, 'How to read the census'),
    rows.length ? tableCard('Workforce census', [
      { title: 'Year', field: 'census_year' },
      { title: 'Metric', field: 'metric' },
      { title: 'Segment', field: 'workforce_segment' },
      { title: 'Value', field: 'value' },
      { title: 'Unit', field: 'unit' },
      { title: 'Verified', field: 'verified', formatter: (c) => c.getValue() ? 'yes' : 'not checked' },
    ], rows, { height: 320 }) : noData('workforce census metrics', './start.sh run m06_workforce_census'),
    provenanceFromRows(rows, { tables: ['workforce_census_metrics'], module: 'm06_workforce_census' })));
}

// --- 2c. provider-published and statutory pay evidence ---------------------

function renderPublishedPay(container, data, charts) {
  const rates = data.statutory_pay_rates || [];
  const published = data.provider_published_pay || [];
  const accreditations = data.living_wage_accreditations || [];
  const genderPayGap = data.gender_pay_gap_reports || [];
  const genderPayGapHolder = el('div', {});

  // `rates` is already ordered by effective_from DESC, period_label DESC
  // (public_queries.pay), so the first row's period is the current one.
  // Under-18s are excluded from the current period specifically: they
  // cannot legally be recruited into a CQC-regulated adult substance
  // misuse service, so that row never applies to this sector's workforce.
  const currentPeriod = rates[0]?.period_label;
  const currentRates = rates.filter(
    (r) => r.period_label === currentPeriod && r.band_label !== 'Under 18');

  replace(container, section(
    'Published pay and employment evidence',
    'Statutory hourly rates, provider-owned pages, Living Wage Foundation checks and gender pay gap filings. These are separate records, not a combined comparison.',
    takeaway(published.length ? 'Published records' : 'No published rows',
      published.length ? 'good' : 'neutral',
      published.length
        ? 'Provider-owned pages record what an organisation published. They are not payroll evidence.'
        : 'No provider-published pay rows match the current filters; this does not establish that none exist.'),
    el('div', { class: 'grid two' },
      el('div', { class: 'panel' },
        el('h3', { text: 'Statutory minimum rates' }),
        pinnedCaveat(data.caveats?.statutory_pay_rates_note, 'Hourly floors only'),
        currentRates.length ? tableCard('Published rates', [
          { title: 'Period', field: 'period_label' },
          { title: 'Band', field: 'band_label' },
          { title: 'Role', field: 'band_role' },
          { title: 'Published value', field: 'value_text' },
        ], currentRates, { height: 240 }) : noData('statutory pay rates', './start.sh run m17_statutory_pay_rates'),
        provenanceFromRows(currentRates, { tables: ['statutory_pay_rates'], module: 'm17_statutory_pay_rates' })),
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
      genderPayGap.length ? genderPayGapHolder
        : noData('matched gender pay gap filings', './start.sh run m20_gender_pay_gap'),
      provenanceFromRows(genderPayGap, { tables: ['gender_pay_gap_reports'], module: 'm20_gender_pay_gap' }))));

  if (!genderPayGap.length) return;

  charts.push(mountChart(genderPayGapHolder, {
    legend: { top: 0 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
      valueFormatter: (v) => (v == null ? '—' : `${v}%`) },
    xAxis: {
      type: 'category',
      data: genderPayGap.map((r) => `${truncate(r.canonical_name || r.employer_name || '—', 20)} · ${r.reporting_year_label || '—'}`),
      axisLabel: { rotate: 20 },
    },
    yAxis: { type: 'value', name: 'hourly pay gap (%)', axisLabel: { formatter: (v) => `${v}%` } },
    series: [
      { name: 'Median hourly gap', type: 'bar', data: genderPayGap.map((r) => r.diff_median_hourly_percent) },
      { name: 'Mean hourly gap', type: 'bar', data: genderPayGap.map((r) => r.diff_mean_hourly_percent) },
    ],
  }, {
    height: 'short',
    aria: 'Bar chart of median and mean hourly gender pay gap percentages for '
      + 'each matched gender pay gap filing, by provider and reporting year.',
  }));
}

// --- 2d. contextual comparators ---------------------------------------------

function renderBenchmarks(container, data) {
  const ashe = data.ons_ashe_observations || [];
  // Rows with no hourly pay figure carry nothing this table can show —
  // annual-only estimates are still readable in the export, just not here.
  const skills = (data.skills_for_care_estimates || []).filter((r) => r.hourly_pay != null);

  replace(container, section(
    'Context only: external comparators',
    'Published labour-market benchmarks that provide context beside compatible evidence. They are not direct sector pay measures and are not combined with the evidence above.',
    takeaway((ashe.length || skills.length) ? 'Context only' : 'No comparator rows', 'neutral',
      'These sources are not combined with provider, account or advert evidence, and the portal does not calculate gaps, ratios or trends from them.'),
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
    takeaway(rows.length ? 'Published accounts' : 'No account rows',
      rows.length ? 'good' : 'neutral',
      rows.length
        ? 'This is an indicative account-based measure, not a salary, payslip or payroll average.'
        : 'No charity-account rows match the current filters; missing rows are not estimated.'),
    el('div', { class: 'panel' },
      holder,
      // Pinned, not collapsible. This figure reads like a salary and is not
      // one, and the difference is the single most misquotable thing here.
      pinnedCaveat(data.caveats?.indicative_wage_note, 'This is not a salary'),
      el('details', { class: 'context-note' },
        el('summary', { text: 'What this does not show' }),
        el('p', { text: 'It does not show an individual salary, a pay scale, or a direct provider comparison across different workforces and accounting periods.' })),
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

  // Newest report first. The chart above reads `rows` in ascending year order
  // for its x-axis, so the table gets its own sorted copy rather than a
  // mutation of the array the chart already built its series from.
  const newestFirst = [...rows].sort(
    (a, b) => (b.financial_year_end || '').localeCompare(a.financial_year_end || ''));
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
  ], newestFirst, { exportEndpoint: 'pay', exportParams: filterParams(), height: 300 }));
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
    takeaway(adverts.length ? 'Advertised roles' : 'No advert rows',
      adverts.length ? 'good' : 'neutral',
      adverts.length
        ? 'These figures describe NHS Jobs vacancies, not payroll pay or the whole recruitment market.'
        : 'No NHS Jobs rows match the current filters; this does not establish that no roles were advertised elsewhere.'),
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.nhs_jobs_floor_note, 'These counts are a floor'),
      el('details', { class: 'context-note' },
        el('summary', { text: 'What this does not show' }),
        el('p', { text: 'It does not show every vacancy, every employer, a completed appointment, or the pay received by the successful applicant.' })),
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

