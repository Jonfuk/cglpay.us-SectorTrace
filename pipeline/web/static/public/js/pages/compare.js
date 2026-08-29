/* Compare — two or more authorities or providers on shared axes (W-11).
 *
 * "How does my authority compare?" is the campaign's central question, and
 * this is the answer in the only shape this pipeline may give it: the reader
 * picks the peers. Each chart draws one kind of figure from one kind of
 * document on a shared axis — the grant axis, the budget axis, the treatment
 * axis, the contracts axis — and never across layers. Comparison is the
 * first thing this portal does that is an inference; the caveats pinned on
 * every chart are why it stays the reader's inference rather than this
 * project's.
 *
 * The URL is the comparison: `#/compare?ons_code=...&ons_code=...&provider_key=...`,
 * named as the API names its parameters, so a comparison is a shareable
 * address and the page rewrites it as entities are added and removed.
 */
'use strict';

import { el, replace, fetchJSON, num, gbp, isoDate, sourceLink,
          typeaheadKeyboard } from '/app.js';
import { section, pinnedCaveat, noData, errorCard, mountChart, disposeCharts,
          provenanceFromRows, provenance, symbolFor, escapeHtml,
          shareButton, findingBlock, tableCard } from '/js/components.js';

export async function render(main, { params = null } = {}) {
  const charts = [];
  const state = {
    ons: (params ? params.getAll('ons_code') : [])
      .filter((code) => /^[A-Z][0-9]{8}$/.test(code)),
    providers: (params ? params.getAll('provider_key') : []).filter(Boolean),
  };

  const chips = el('div', { class: 'compare-chips' });
  const picker = el('div', {});
  const content = el('div', {});

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('p', {}, el('a', { href: '#/authorities' }, '← Authority pages')),
      el('h1', { text: 'Compare evidence safely' }),
      el('p', { class: 'lede' },
        'Choose peers, choose a published evidence layer, then read the '
        + 'source-specific chart. The portal does not calculate differences or rankings.'),
      el('div', { class: 'hero-actions' },
        shareButton({
          title: 'SectorTrace comparison',
          text: 'Compare published SectorTrace evidence with its caveats.',
          label: 'Share comparison',
        }))),
    el('details', { class: 'read-first' },
      el('summary', { text: 'How comparisons work' }),
      el('p', { text: 'Each chart uses one source and one kind of measure. Shared axes let you inspect peers; they do not turn unlike measures into one score.' })),
    el('div', { id: 'compare-caveat' }),
    el('div', { id: 'compare-picker' }),
    content);
  replace(main, page);

  const caveatHolder = page.querySelector('#compare-caveat');
  const pickerHolder = page.querySelector('#compare-picker');

  let data = null;
  if (state.ons.length || state.providers.length) {
    try {
      data = await fetchJSON('compare', {
        ons_code: state.ons.length ? state.ons : undefined,
        provider_key: state.providers.length ? state.providers : undefined,
      });
    } catch (error) {
      replace(content, errorCard(error, () => render(main, { params })));
      return () => {};
    }
  }

  // The cross-layer caveat is the reason this page exists: four charts, four
  // kinds of figure, and the page's only claim is that they share axes with
  // their peers, never with each other.
  if (data?.caveats?.cross_layer) {
    replace(caveatHolder, pinnedCaveat(data.caveats.cross_layer,
      'What this page may and may not do'));
  }

  await renderPicker(pickerHolder, chips, state, data);

  if (!data || (!state.ons.length && !state.providers.length)) {
    replace(content, el('div', { class: 'section' },
      el('div', { class: 'panel' },
        el('p', { text: 'Pick two or more authorities or providers above to '
          + 'draw them on shared axes.' }))));
    return () => {};
  }

  replace(content, el('div', {}));
  const contentHolder = content.firstElementChild;
  const seriesRows = Object.values(data.series || {});
  const sources = [...new Set(seriesRows.flatMap((series) => series.provenance?.sources || []).filter(Boolean))];
  const retrievedAt = seriesRows.map((series) => series.provenance?.retrieved_at).filter(Boolean).sort().pop() || null;
  const comparisonFinding = findingBlock({
    finding: 'Comparison keeps peers on shared axes within each evidence layer; it does not calculate a difference, ranking, or cross-layer score.',
    value: `${state.ons.length + state.providers.length} selected entities`, evidenceStatus: sources.length || retrievedAt ? 'Published' : null,
    timing: { kind: retrievedAt ? 'current' : 'snapshot', date: retrievedAt?.slice(0, 10) },
    sources, retrievedAt: retrievedAt?.slice(0, 10),
    caveat: data.caveats?.cross_layer || 'Choose peers explicitly and read each source-specific caveat before drawing a conclusion.',
  });
  if (comparisonFinding) contentHolder.append(comparisonFinding);

  if (data.series.grant) {
    renderYearsChart(contentHolder, 'Grant allocation',
      'The public health grant allocation, as published per financial year.',
      data.series.grant, charts, {
        entity: 'authority_name', value: 'amount',
        caveat: data.series.grant.caveat,
        module: 'm11_public_health_grant', tables: ['public_health_grants'],
        indicative: true,
      });
  }
  if (data.series.budget) {
    renderYearsChart(contentHolder, 'Budgeted public health spend',
      'What each authority planned to spend, as reported to MHCLG.',
      data.series.budget, charts, {
        entity: 'authority_name', value: 'amount',
        caveat: data.series.budget.caveat,
        module: 'm13_la_budgets', tables: ['la_revenue_budgets'],
        provenanceMeta: data.series.budget.provenance,
      });
  }
  if (data.series.treatment) {
    renderTreatment(contentHolder, data.series.treatment, charts);
  }
  if (data.series.contracts) {
    renderYearsChart(contentHolder, 'Contract value published',
      'The value of notices published per year, as published in the notice.',
      data.series.contracts, charts, {
        entity: 'authority_name', value: 'value_gbp',
        caveat: null,
        module: 'm01_procurement', tables: ['contracts'],
        provenanceMeta: data.series.contracts.provenance,
        extraCaveats: [data.series.contracts.caveats?.value,
          data.series.contracts.caveats?.window],
      });
  }
  if (data.series.charity) {
    renderCharity(contentHolder, data.series.charity, charts);
  }
  if (data.series.provider_contracts) {
    renderYearsChart(contentHolder, 'Contracts held by providers',
      'The value of notices matched to each provider, per publication year.',
      data.series.provider_contracts, charts, {
        entity: 'provider_name', value: 'value_gbp',
        caveat: null,
        module: 'm01_procurement', tables: ['contracts', 'supplier_aliases'],
        provenanceMeta: data.series.provider_contracts.provenance,
        extraCaveats: [data.series.provider_contracts.caveats?.provider_match,
          data.series.provider_contracts.caveats?.window],
      });
  }

  // BETA-045: when the selection is providers only (2-4), the pay-evidence
  // layers that have no authority counterpart and no shared time axis are
  // laid out side by side — as tables, because "unlike measures must not be
  // collapsed" and a chart would invite exactly that.
  if (state.providers.length >= 2 && !state.ons.length) {
    await renderProviderPayLayers(contentHolder, state.providers);
  }

  return () => disposeCharts(charts);
}

async function renderProviderPayLayers(container, providerKeys) {
  const keys = providerKeys.slice(0, 4);
  const truncated = providerKeys.length > 4;
  let data;
  try {
    data = await fetchJSON('provider_compare', { provider_key: keys });
  } catch (error) {
    container.append(section('Pay evidence side by side', null,
      errorCard(error, () => {})));
    return;
  }
  const order = data.providers.map((p) => p.provider_key);
  const name = new Map(data.providers.map((p) => [p.provider_key, p.canonical_name]));

  const layerBlock = (title, layer, rowsFor) => {
    const parts = [pinnedCaveat(layer.caveat, `${title} — read before comparing`),
      el('p', { class: 'small muted', text: `Unit: ${layer.unit}` })];
    for (const key of order) {
      const rows = (layer.by_provider && layer.by_provider[key]) || [];
      parts.push(el('div', { class: 'panel' },
        el('h4', { text: name.get(key) || key }),
        rows.length
          ? el('ul', { class: 'small' }, ...rows.slice(0, 8).map(rowsFor))
          : el('p', { class: 'small muted', text: 'No rows in this layer for this provider — not evidence of a better or worse position.' }),
        rows.length > 8
          ? el('p', { class: 'small muted', text: `…and ${num(rows.length - 8)} more` })
          : null));
    }
    return section(title, null, ...parts);
  };

  container.append(el('div', { class: 'section' },
    el('h2', { text: 'Pay evidence side by side' }),
    pinnedCaveat(data.caveat, 'What this side-by-side may and may not do'),
    truncated
      ? el('p', { class: 'small muted', text: `Showing the first four providers you picked; the endpoint accepts at most four.` })
      : null));

  container.append(layerBlock('Living Wage accreditation', data.layers.living_wage,
    (r) => el('li', { text: `${r.accredited ? 'Accredited' : 'Not accredited'}`
      + `${r.employer_name ? ` — matched to "${r.employer_name}" (${r.match_basis || 'match'})` : ''}`
      + `${r.retrieved_at ? `, checked ${isoDate(r.retrieved_at)}` : ''}` })));

  container.append(layerBlock('Latest gender pay gap filing', data.layers.gender_pay_gap,
    (r) => el('li', {}, `${r.reporting_year_label || r.reporting_year}: `
      + `mean hourly gap ${fmtPct(r.diff_mean_hourly_percent)}, `
      + `median ${fmtPct(r.diff_median_hourly_percent)}`
      + `${r.employer_size ? ` (${r.employer_size})` : ''} `,
      r.written_statement_url ? sourceLink(r.written_statement_url, 'statement') : null)));

  container.append(layerBlock('Pay published on the provider’s own site', data.layers.provider_pay,
    (r) => el('li', {}, `${(r.mention_text || r.salary_raw || '').trim()}`
      + `${r.salary_period ? ` — per ${r.salary_period}` : ''}`
      + `${r.salary_basis ? `, ${r.salary_basis}` : ''} `,
      r.source_url ? sourceLink(r.source_url, 'page') : null)));

  container.append(layerBlock('Recent NHS Jobs adverts', data.layers.nhs_jobs,
    (r) => el('li', {}, `${r.job_title || 'role'}: ${r.salary_raw || '—'}`
      + `${r.posted_date ? ` (posted ${isoDate(r.posted_date)})` : ''} `,
      r.advert_url ? sourceLink(r.advert_url, 'advert') : null)));
}

function fmtPct(value) {
  return value === null || value === undefined ? '—' : `${value}%`;
}

/* The pickers and the selection chips. The URL is the state: every add and
 * remove rewrites the hash and lets the router re-render the page, so a
 * comparison is always the address it is shown at. */
async function renderPicker(holder, chips, state, data) {
  let authorities = [];
  let providers = [];
  try {
    authorities = (await fetchJSON('authorities')).authorities || [];
    providers = (await fetchJSON('providers')).providers || [];
  } catch (e) { /* the pickers fall back to the selected entities only */ }

  // Names for the chips and the lists. The payload names the selected
  // entities even when the full lists did not load.
  const names = new Map();
  for (const a of authorities) names.set(a.ons_code, a.name);
  for (const p of providers) names.set(p.provider_key, p.canonical_name);
  for (const a of data?.authorities || []) names.set(a.ons_code, a.name);
  for (const p of data?.providers || []) names.set(p.provider_key, p.canonical_name);

  const remove = (param, value) => {
    const params = new URLSearchParams(location.hash.split('?')[1] || '');
    const rest = params.getAll(param).filter((v) => v !== value);
    params.delete(param);
    for (const v of rest) params.append(param, v);
    const query = params.toString();
    location.hash = `#/compare${query ? `?${query}` : ''}`;
  };

  for (const code of state.ons) {
    chips.append(el('span', { class: 'chip' }, names.get(code) || code, ' ',
      el('button', {
        type: 'button', class: 'chip-remove',
        'aria-label': `Remove ${names.get(code) || code}`,
        onclick: () => remove('ons_code', code),
      }, '×')));
  }
  for (const key of state.providers) {
    chips.append(el('span', { class: 'chip' }, names.get(key) || key, ' ',
      el('button', {
        type: 'button', class: 'chip-remove',
        'aria-label': `Remove ${names.get(key) || key}`,
        onclick: () => remove('provider_key', key),
      }, '×')));
  }

  const selected = state.ons.length + state.providers.length;
  replace(holder, section('Choose what to compare',
    `${num(selected)} selected · choose at least two peers to draw a shared axis.`,
    el('div', { class: 'panel' },
      chips.children.length ? chips : el('p', { class: 'small muted',
        text: 'Nothing selected yet — the charts appear once there are two '
          + 'authorities or providers to draw.' }),
      selected ? el('div', { class: 'section-links' },
        el('button', {
          type: 'button', text: 'Clear all selections',
          onclick: () => { location.hash = '#/compare'; },
        })) : null,
      el('div', { class: 'compare-pickers' },
        authorityPicker(state, authorities),
        providerPicker(state, providers)))));
}

/* The typeahead pattern from the treatment page, one per kind of entity.
 * Picking navigates: the hash is rewritten with the new selection and the
 * router re-renders, so there is no local state to fall out of step. */
function authorityPicker(state, authorities) {
  const input = el('input', { type: 'search', id: 'compare-add-authority',
    placeholder: 'Add an authority', 'aria-label': 'Add an authority to compare',
    autocomplete: 'off', role: 'combobox', 'aria-expanded': 'false',
    'aria-controls': 'compare-add-authority-list' });
  const list = el('ul', { id: 'compare-add-authority-list', class: 'typeahead-list',
    hidden: true, role: 'listbox' });
  const fuse = window.Fuse
    ? new window.Fuse(authorities, { keys: ['name', 'ons_code'], threshold: 0.4 })
    : null;
  const resetKeyboard = typeaheadKeyboard(input, list);

  const pick = (code) => {
    if (state.ons.includes(code)) return;
    input.value = '';
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    appendToUrl('ons_code', code);
  };
  const show = () => {
    const term = input.value.trim();
    const all = authorities.filter((a) => !state.ons.includes(a.ons_code));
    const matches = !term ? all.slice(0, 8)
      : fuse ? fuse.search(term).slice(0, 8).map((r) => r.item)
        : all.filter((a) =>
          a.name.toLowerCase().includes(term.toLowerCase())).slice(0, 8);
    replace(list, matches.map((a) => el('li', {
      role: 'option', onmousedown: () => pick(a.ons_code),
    }, `${a.name} · ${a.ons_code}`)));
    resetKeyboard();
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
  };
  input.addEventListener('focus', show);
  input.addEventListener('input', show);
  input.addEventListener('blur', () => setTimeout(() => { list.hidden = true; }, 120));
  return el('div', { class: 'typeahead' }, input, list);
}

function providerPicker(state, providers) {
  const input = el('input', { type: 'search', id: 'compare-add-provider',
    placeholder: 'Add a provider', 'aria-label': 'Add a provider to compare',
    autocomplete: 'off', role: 'combobox', 'aria-expanded': 'false',
    'aria-controls': 'compare-add-provider-list' });
  const list = el('ul', { id: 'compare-add-provider-list', class: 'typeahead-list',
    hidden: true, role: 'listbox' });
  const fuse = window.Fuse
    ? new window.Fuse(providers, { keys: ['canonical_name', 'provider_key'],
      threshold: 0.4 })
    : null;
  const resetKeyboard = typeaheadKeyboard(input, list);

  const pick = (key) => {
    if (state.providers.includes(key)) return;
    input.value = '';
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    appendToUrl('provider_key', key);
  };
  const show = () => {
    const term = input.value.trim();
    const all = providers.filter((p) => !state.providers.includes(p.provider_key));
    const matches = !term ? all.slice(0, 8)
      : fuse ? fuse.search(term).slice(0, 8).map((r) => r.item)
        : all.filter((p) =>
          p.canonical_name.toLowerCase().includes(term.toLowerCase())).slice(0, 8);
    replace(list, matches.map((p) => el('li', {
      role: 'option', onmousedown: () => pick(p.provider_key),
    }, p.canonical_name)));
    resetKeyboard();
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
  };
  input.addEventListener('focus', show);
  input.addEventListener('input', show);
  input.addEventListener('blur', () => setTimeout(() => { list.hidden = true; }, 120));
  return el('div', { class: 'typeahead' }, input, list);
}

function appendToUrl(param, value) {
  const params = new URLSearchParams(location.hash.split('?')[1] || '');
  params.append(param, value);
  location.hash = `#/compare?${params.toString()}`;
}

// --- the charts --------------------------------------------------------------

/* One shared axis, one entity per series. The axis carries one kind of
 * figure; the caveat pinned beside it is the same caveat the figure carries
 * wherever else it is drawn. */
function renderYearsChart(container, title, description, series, charts, opts) {
  const holder = el('div', {});
  const tableHolder = el('div', {});
  const rows = series.rows || [];
  const entities = [...new Set(rows.map((r) => r[opts.entity]))];
  const years = [...new Set(rows.map((r) => r.year))].sort();

  container.append(section(title, description,
    el('div', { class: 'panel' },
      opts.caveat ? pinnedCaveat(opts.caveat, 'Read this with the chart') : null,
      (opts.extraCaveats || []).filter(Boolean)
        .map((text) => pinnedCaveat(text, 'Read this with the chart')),
      indicativeNote(opts, rows),
      holder,
      tableHolder,
      provenanceMeta(opts, rows) || el('span', {}))));

  if (!entities.length || !years.length) {
    replace(holder, noData(`${title.toLowerCase()} series`, null));
    return;
  }

  replace(tableHolder, tableCard('Values behind the chart',
    yearsTableColumns(opts, rows), rows, { height: 280 }));

  const byEntityYear = new Map(rows.map((r) =>
    [`${r[opts.entity]}\u0000${r.year}`, r]));

  const palette = ['#2dd4bf', '#f59e0b', '#60a5fa', '#f472b6',
    '#a3e635', '#c084fc', '#f87171', '#34d399'];

  charts.push(mountChart(holder, {
    grid: { left: 8, right: 24, top: 60, bottom: 8, containLabel: true },
    legend: { top: 30, type: 'scroll' },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const year = params[0].axisValue;
        const lines = [`<strong>${escapeHtml(year)}</strong>`];
        for (const p of params) {
          const row = byEntityYear.get(`${p.seriesName}\u0000${year}`);
          if (!row) continue;
          lines.push(`<br>${escapeHtml(p.seriesName)}: `
            + `${opts.value === 'value_gbp' ? gbp(row.value_gbp) : gbp(row.amount)}`
            + (row.count !== undefined
              ? ` <span style="color:#8b949e">(${num(row.count)} notices)</span>` : ''));
        }
        return lines.join('');
      },
    },
    xAxis: { type: 'category', data: years },
    yAxis: { type: 'value', axisLabel: { formatter: (v) => gbp(v) } },
    series: entities.map((name, index) => ({
      name, type: 'line', symbol: symbolFor(index), symbolSize: 8,
      connectNulls: true, itemStyle: { color: palette[index % palette.length] },
      data: years.map((year) => {
        const row = byEntityYear.get(`${name}\u0000${year}`);
        return row ? (opts.value === 'value_gbp' ? row.value_gbp : row.amount) : null;
      }),
    })),
  }, {
    aria: `Line chart of ${title.toLowerCase()} by year for `
      + `${entities.join(', ')}.`,
  }));
}

/* Later grant years are published as indicative and revised afterwards, and
 * the geography page's warning applies here too: reading a fall between a
 * confirmed year and an indicative one as a cut is the mistake it exists to
 * prevent. */
function indicativeNote(opts, rows) {
  if (!opts.indicative) return null;
  const indicative = rows.filter((r) => r.allocation_status === 'indicative');
  if (!indicative.length) return null;
  const year = [...new Set(indicative.map((r) => r.financial_year))].sort().pop();
  return pinnedCaveat(
    `Allocations for ${year} are published as indicative and are revised `
    + 'later. Do not compare an indicative year with a confirmed one.',
    'Indicative allocation');
}

/* The same rows the chart draws, as a table — every chart-bearing page but
 * this one already pairs a chart with its rows (BETA-018's frontend audit
 * flagged the gap). Columns are derived from `opts`/the rows themselves
 * rather than hard-coded per series, since `renderYearsChart` is shared by
 * five differently-shaped series (grant, budget, contracts, provider
 * contracts). */
function yearsTableColumns(opts, rows) {
  const columns = [
    { title: opts.entity === 'provider_name' ? 'Provider' : 'Authority', field: opts.entity },
    { title: 'Year', field: 'year', width: 90 },
    {
      title: opts.value === 'value_gbp' ? 'Value' : 'Amount', field: opts.value,
      width: 130, formatter: (c) => gbp(c.getValue(), { compact: false }),
    },
  ];
  if (rows.some((r) => r.count !== undefined)) {
    columns.push({ title: 'Notices', field: 'count', width: 90 });
  }
  if (rows.some((r) => r.allocation_status)) {
    columns.push({ title: 'Status', field: 'allocation_status', width: 130 });
  }
  return columns;
}

function provenanceMeta(opts, rows) {
  if (rows.some((r) => r.source_url)) {
    return provenanceFromRows(rows, { module: opts.module, tables: opts.tables });
  }
  return provenance({
    sources: opts.provenanceMeta?.sources || [],
    retrievedAt: opts.provenanceMeta?.retrieved_at || null,
    module: opts.module, tables: opts.tables,
  });
}

/* Treatment: one chart per indicator, the series the treatment page draws —
 * each authority as a line with its paired confidence band, and the England
 * figure the sources publish beside them. The band rule is the treatment
 * page's own: only figures the source published an interval for are drawn
 * with one. */
function renderTreatment(container, data, charts) {
  const indicators = data.indicators || [];
  const holder = el('div', {});
  const rows = data.rows || [];
  const england = data.england || [];

  container.append(section('Numbers in treatment',
    'The Fingertips figures each authority publishes, on one axis per '
    + 'indicator, with the confidence interval that belongs to each value.',
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveat, 'Read this with the chart'),
      holder,
      provenanceFromRows(rows, {
        module: 'm12_fingertips',
        tables: ['fingertips_indicators', 'fingertips_la_values'],
      }) || el('span', {}))));

  if (!rows.length && !england.length) {
    replace(holder, noData('treatment series', './start.sh run m12_fingertips'));
    return;
  }

  const seriesByIndicator = rows.reduce((map, row) => {
    if (!map.has(row.indicator_id)) map.set(row.indicator_id, []);
    map.get(row.indicator_id).push(row);
    return map;
  }, new Map());

  const palette = ['#2dd4bf', '#f59e0b', '#60a5fa', '#f472b6',
    '#a3e635', '#c084fc', '#f87171', '#34d399'];

  for (const indicator of indicators) {
    const indicatorRows = seriesByIndicator.get(indicator.indicator_id) || [];
    const englandRows = england.filter((r) => r.indicator_id === indicator.indicator_id);
    if (!indicatorRows.length && !englandRows.length) continue;

    const periods = [...new Set([...indicatorRows, ...englandRows]
      .map((r) => r.time_period))]
      .sort((a, b) => String(a).localeCompare(String(b)));
    const authorities = [...new Set(indicatorRows.map((r) => r.authority_name))];

    const series = [];
    authorities.forEach((name, index) => {
      const byPeriod = new Map(indicatorRows.filter((r) => r.authority_name === name)
        .map((r) => [r.time_period, r]));
      const values = periods.map((p) => byPeriod.get(p)?.value ?? null);
      const lower = periods.map((p) => byPeriod.get(p)?.lower_ci_95 ?? null);
      const upper = periods.map((p) => byPeriod.get(p)?.upper_ci_95 ?? null);
      const stack = `ci-${index}`;
      if (lower.some((v) => v !== null)) {
        series.push({
          name: `lower 95% CI · ${name}`, type: 'line', stack, symbol: 'none',
          lineStyle: { opacity: 0 }, areaStyle: { opacity: 0 }, silent: true,
          data: lower,
        }, {
          name: `95% CI · ${name}`, type: 'line', stack, symbol: 'none',
          lineStyle: { opacity: 0 },
          areaStyle: { color: `rgba(${ciRgb(palette[index % palette.length])}, 0.18)` },
          data: periods.map((p, i) => (upper[i] === null || lower[i] === null
            ? null : upper[i] - lower[i])),
        });
      }
      series.push({
        name, type: 'line', symbol: symbolFor(index), symbolSize: 8,
        connectNulls: true,
        itemStyle: { color: palette[index % palette.length] },
        data: values,
      });
    });

    if (englandRows.length) {
      const englandByPeriod = new Map(englandRows.map((r) => [r.time_period, r.value]));
      series.push({
        name: 'England', type: 'line', symbol: 'diamond', symbolSize: 7,
        lineStyle: { type: 'dashed', width: 2 },
        data: periods.map((p) => englandByPeriod.get(p) ?? null),
      });
    }

    const chartHolder = el('div', {});
    holder.append(chartHolder);
    charts.push(mountChart(chartHolder, {
      title: {
        text: indicator.indicator_name, subtext: indicator.unit || '',
        left: 0, top: 0, textStyle: { fontSize: 15 },
        subtextStyle: { color: '#8b949e' },
      },
      grid: { top: 76 },
      legend: { top: 46, type: 'scroll',
        data: series.map((s) => s.name).filter((n) => !n.startsWith('lower 95% CI')) },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: periods },
      yAxis: { type: 'value', name: indicator.unit || '' },
      series,
    }, {
      aria: `Line chart of ${indicator.indicator_name} for `
        + `${authorities.join(', ')} with the confidence intervals the source `
        + 'published, compared with the England figure.',
    }));

    const tableRows = [
      ...indicatorRows,
      ...englandRows.map((r) => ({ ...r, authority_name: 'England' })),
    ];
    holder.append(tableCard(`${indicator.indicator_name} — values behind the chart`, [
      { title: 'Authority', field: 'authority_name' },
      { title: 'Period', field: 'time_period', width: 110 },
      { title: 'Value', field: 'value', width: 100 },
      { title: 'Lower 95%', field: 'lower_ci_95', width: 110 },
      { title: 'Upper 95%', field: 'upper_ci_95', width: 110 },
      { title: 'Note', field: 'value_note' },
    ], tableRows, { height: 260 }));
  }
}

function ciRgb(hex) {
  const value = parseInt(hex.slice(1), 16);
  return `${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}`;
}

/* Charity accounts: income and expenditure per year end, one provider per
 * colour, the two series sharing an axis because they are one source's
 * figures. */
function renderCharity(container, data, charts) {
  const holder = el('div', {});
  const tableHolder = el('div', {});
  const rows = data.rows || [];
  const providers = [...new Set(rows.map((r) => r.provider_key))];
  const years = [...new Set(rows.map((r) => r.financial_year_end))].sort();

  container.append(section('Charity income and expenditure',
    'As filed in each provider\'s registered accounts, per financial year end.',
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveat, 'Read this with the chart'),
      holder,
      tableHolder,
      provenanceFromRows(rows, {
        module: 'm03_charity_finance', tables: ['charity_financials'],
      }) || el('span', {}))));

  if (!providers.length || !years.length) {
    replace(holder, noData('charity accounts', './start.sh run m03_charity_finance'));
    return;
  }

  replace(tableHolder, tableCard('Values behind the chart', [
    { title: 'Provider', field: 'canonical_name' },
    { title: 'Year end', field: 'financial_year_end', width: 110 },
    {
      title: 'Income', field: 'total_income', width: 130,
      formatter: (c) => gbp(c.getValue(), { compact: false }),
    },
    {
      title: 'Expenditure', field: 'total_expenditure', width: 130,
      formatter: (c) => gbp(c.getValue(), { compact: false }),
    },
  ], rows, { height: 260 }));

  const byKey = new Map(rows.map((r) =>
    [`${r.provider_key}\u0000${r.financial_year_end}`, r]));
  const palette = ['#2dd4bf', '#f59e0b', '#60a5fa', '#f472b6',
    '#a3e635', '#c084fc', '#f87171', '#34d399'];

  const series = [];
  providers.forEach((key, index) => {
    const colour = palette[index % palette.length];
    const value = (field) => years.map((year) => {
      const row = byKey.get(`${key}\u0000${year}`);
      return row ? row[field] : null;
    });
    series.push({
      name: `${key} income`, type: 'line', symbol: symbolFor(index),
      symbolSize: 8, connectNulls: true, itemStyle: { color: colour },
      data: value('total_income'),
    }, {
      name: `${key} expenditure`, type: 'line', symbol: symbolFor(index),
      symbolSize: 8, connectNulls: true,
      itemStyle: { color: colour, opacity: 0.55 }, lineStyle: { type: 'dashed' },
      data: value('total_expenditure'),
    });
  });

  charts.push(mountChart(holder, {
    grid: { left: 8, right: 24, top: 60, bottom: 8, containLabel: true },
    legend: { top: 30, type: 'scroll' },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const year = params[0].axisValue;
        return `<strong>${escapeHtml(year)}</strong>`
          + params.map((p) => `<br>${escapeHtml(p.seriesName)}: ${gbp(p.value)}`)
            .join('');
      },
    },
    xAxis: { type: 'category', data: years },
    yAxis: { type: 'value', axisLabel: { formatter: (v) => gbp(v) } },
    series,
  }, {
    aria: 'Line chart of charity income and expenditure per financial year '
      + `end for ${providers.join(', ')}.`,
  }));
}
