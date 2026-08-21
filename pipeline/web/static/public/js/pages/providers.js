/* Providers — the comparison list, and the per-provider deep dive.
 *
 * Both live here because the deep dive is the list with one row expanded into
 * everything the warehouse holds about it: a dated evidence stream, the entity
 * graph, CQC registrations and tribunal cases.
 *
 * The entity graph is the part to be careful with. Some of its edges are
 * `name_only_unconfirmed` — a name that matched, which is not the same as a
 * relationship that exists — and those are drawn as dashed warning-coloured
 * lines rather than as facts.
 */
'use strict';

import { el, replace, fetchJSON, num, gbp, pct, isoDate, sourceLink } from '/app.js';
import { section, pinnedCaveat, caveat, noData, errorCard, mountChart,
          disposeCharts, provenance, tableCard, escapeHtml, truncate,
          statCard, exportButton, registerLink, registerLinks, shareButton,
          findingBlock, evidenceMeta } from '/js/components.js';

export async function render(main, { path }) {
  const key = path.startsWith('/providers/') ? path.slice('/providers/'.length) : null;
  return key ? renderOne(main, key) : renderList(main);
}

// --- the list ----------------------------------------------------------------

async function renderList(main) {
  const charts = [];
  let providers;
  try {
    providers = (await fetchJSON('providers')).providers || [];
  } catch (error) {
    replace(main, errorCard(error.message, () => renderList(main)));
    return () => {};
  }

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Find provider evidence' }),
      el('p', { class: 'lede' },
        `Browse ${num(providers.length)} tracked organisations, then open a `
        + 'provider workbench to see the published evidence held for it.'),
      el('div', { class: 'hero-actions' },
        shareButton({
          title: 'SectorTrace provider directory',
          text: 'Browse the SectorTrace provider evidence directory.',
          label: 'Share this directory',
        }))),
    el('div', { id: 'cards' }),
    el('div', { id: 'chart' }),
    el('div', { id: 'table' }));
  replace(main, page);

  replace(page.querySelector('#cards'), section(
    'Provider directory',
    'Open a provider to see what evidence is held. “Partial evidence” means '
      + 'some sources have rows; it does not describe the provider itself.',
    el('div', { class: 'grid cards' }, providers.slice(0, 8).map((p) => el('a', {
      href: `#/providers/${p.provider_key}`,
      style: 'text-decoration:none;color:inherit;',
    }, statCard({
      value: p.canonical_name,
      plain: true,
      label: providerStatus(p),
      sub: `${num(p.cqc_locations)} CQC locations · ${num(p.contract_count)} contracts`,
    }))))));

  const holder = el('div', {});
  replace(page.querySelector('#chart'), section(
    'Evidence held per provider',
    'How much of each kind of record the warehouse holds. A low count is a '
    + 'statement about coverage, not about the provider.',
    el('div', { class: 'panel' }, holder)));

  const named = providers.filter((p) =>
    p.cqc_locations || p.tribunal_count || p.contract_count || p.nhs_job_advert_count);

  if (named.length) {
    const providerChart = mountChart(holder, {
      legend: { top: 0 },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      xAxis: { type: 'value', name: 'records' },
      yAxis: { type: 'category', data: named.map((p) => p.canonical_name) },
      series: [
        { name: 'CQC locations', type: 'bar', stack: 'x', data: named.map((p) => p.cqc_locations) },
        { name: 'Tribunal cases', type: 'bar', stack: 'x', data: named.map((p) => p.tribunal_count) },
        { name: 'Contract notices', type: 'bar', stack: 'x', data: named.map((p) => p.contract_count) },
        { name: 'NHS Jobs adverts', type: 'bar', stack: 'x', data: named.map((p) => p.nhs_job_advert_count) },
      ],
    }, {
      height: 'tall',
      aria: 'Stacked bar chart of how many records of each type the warehouse '
        + 'holds for each provider.',
    });
    charts.push(providerChart);
    providerChart?.on('click', (params) => {
      const provider = named[params.dataIndex];
      if (provider?.provider_key) location.hash = `#/providers/${encodeURIComponent(provider.provider_key)}`;
    });
  } else {
    replace(holder, noData('provider evidence', './start.sh run all'));
  }

  replace(page.querySelector('#table'), tableCard('All providers', [
    { title: 'Provider', field: 'canonical_name', formatter: (c) => el('a', {
      href: `#/providers/${encodeURIComponent(c.getRow().getData().provider_key)}`,
      text: c.getValue(),
    }) },
    { title: 'Campaign subject', field: 'is_target', width: 140,
      formatter: (c) => (c.getValue() ? '★ yes' : '') },
    { title: 'Contracts', field: 'contract_count', width: 100 },
    { title: 'Contract value', field: 'contract_value_gbp', width: 130,
      formatter: (c) => gbp(c.getValue()) },
    { title: 'CQC locations', field: 'cqc_locations', width: 120 },
    { title: 'Tribunals', field: 'tribunal_count', width: 100 },
    { title: 'NHS adverts', field: 'nhs_job_advert_count', width: 110 },
    { title: 'Charity income', field: 'charity_income_latest', width: 130,
      formatter: (c) => gbp(c.getValue()) },
    // Tabulator formatters may return a DOM node, so these stay text nodes
    // built by el() like everything else on this page -- no HTML string is
    // assembled from a warehouse value to make a link.
    { title: 'Companies House', field: 'company_number', width: 190,
      formatter: (c) => registerLink('company_number', c.getValue()) || '' },
    { title: 'Charity Commission', field: 'charity_number', width: 200,
      formatter: (c) => registerLink('charity_number', c.getValue()) || '' },
  ], providers, { height: 380, exportEndpoint: 'providers' }));

  return () => disposeCharts(charts);
}

// --- the deep dive -----------------------------------------------------------

async function renderOne(main, key) {
  const charts = [];
  let data;
  try {
    data = await fetchJSON(`providers/${encodeURIComponent(key)}/timeline`);
  } catch (error) {
    replace(main, errorCard(error.message, () => renderOne(main, key)));
    return () => {};
  }

  const provider = data.provider || {};
  const page = el('div', {},
    el('div', { class: 'hero' },
      el('p', {}, el('a', { href: '#/providers' }, '← All providers'),
        ' · ', el('a', { href: `#/compare?provider_key=${key}` },
          'Compare with other providers →')),
      el('h1', {}, provider.canonical_name || key,
        provider.is_target ? ' ' : null,
        provider.is_target ? el('span', { class: 'badge target', text: '★ CAMPAIGN SUBJECT' }) : null),
      provider.notes ? el('p', { class: 'lede', text: provider.notes }) : null,
      // Built from the entity edges the timeline already carries rather than
      // from a new query: an `identified_by` edge is a scheme and an
      // identifier, which is exactly what a register lookup takes.
      registerLinks((data.entity_edges || [])
        .filter((e) => e.source_id === key)
        .map((e) => ({ scheme: e.target_type, identifier: e.target_id }))),
      el('div', { class: 'hero-actions' },
        shareButton({
          title: `SectorTrace — ${provider.canonical_name || key}`,
          text: 'Explore the published provider evidence in SectorTrace.',
          label: 'Share this provider',
        }))),
    (() => {
      const meta = evidenceMeta(data);
      return findingBlock({
        finding: 'This provider workbench brings together the published records held for one organisation; partial evidence describes coverage in the warehouse, not the provider itself.',
        value: provider.canonical_name || key, evidenceStatus: meta.sources.length || meta.retrievedAt ? 'Published' : null,
        timing: { kind: meta.retrievedAt ? 'current' : 'snapshot', date: meta.retrievedAt?.slice(0, 10) },
        sources: meta.sources, retrievedAt: meta.retrievedAt?.slice(0, 10),
        caveat: 'Entity links and name matches are shown with their verification status; a missing record is not evidence that an event did not occur.',
      });
    })(),
    el('div', { id: 'inventory' }),
    el('div', { id: 'timeline' }),
    el('div', { id: 'graph' }),
    el('div', { id: 'cqc' }),
    el('div', { id: 'cqc-reports' }),
    el('div', { id: 'finance' }),
    el('div', { id: 'disclosure' }),
    el('div', { id: 'filings' }),
    el('div', { id: 'pfd' }),
    el('div', { id: 'tribunals' }));
  replace(main, page);

  renderInventory(page.querySelector('#inventory'), data);
  renderTimeline(page.querySelector('#timeline'), data);
  renderGraph(page.querySelector('#graph'), data, charts, key);
  renderCqc(page.querySelector('#cqc'), data);
  renderCqcReports(page.querySelector('#cqc-reports'), data, charts);
  renderCharityFinance(page.querySelector('#finance'), data, charts);
  renderDisclosure(page.querySelector('#disclosure'), data, charts);
  renderFilings(page.querySelector('#filings'), data);
  renderPfd(page.querySelector('#pfd'), data);
  renderTribunals(page.querySelector('#tribunals'), data);

  return () => disposeCharts(charts);
}

function providerStatus(provider) {
  const records = ['cqc_locations', 'tribunal_count', 'contract_count',
    'nhs_job_advert_count'].reduce((sum, key) => sum + (provider[key] || 0), 0);
  if (!records) return 'no current evidence';
  return provider.is_target ? '★ campaign subject · partial evidence' : 'partial evidence';
}

function renderInventory(container, data) {
  const items = [
    ['CQC locations', (data.cqc_locations || []).length],
    ['Contracts', (data.events || []).filter((e) => e.event_type === 'contract_award').length],
    ['Safety/legal', (data.pfd_mentions || []).length + (data.tribunal_cases || []).length],
    ['Financial evidence', (data.charity_finance || []).length],
  ];
  const rowsFor = {
    'CQC locations': (data.cqc_locations || []).map((row) => ({ location: row.location_name, rating: row.overall_rating || 'Not rated', inspected: row.overall_rating_date || 'Not inspected', source: row.source_url || '—' })),
    Contracts: (data.events || []).filter((row) => row.event_type === 'contract_award').map((row) => ({ date: row.date, evidence: row.label, detail: row.value_summary || '—', source: row.notice_link || row.source_url || '—' })),
    'Safety/legal': [...(data.pfd_mentions || []).map((row) => ({ date: row.report_date, evidence: 'Coroners’ report mention', detail: row.mention_type || '—', source: row.report_url || '—' })), ...(data.tribunal_cases || []).map((row) => ({ date: row.decision_date, evidence: 'Employment tribunal case', detail: row.outcome || '—', source: row.source_url || '—' }))],
    'Financial evidence': (data.charity_finance || []).map((row) => ({ date: row.financial_year_end, evidence: 'Filed accounts', detail: row.total_income == null ? 'Income not published' : `Income £${Number(row.total_income).toLocaleString('en-GB')}`, source: row.source_url || '—' })),
  };
  const columnsFor = {
    'CQC locations': [{ title: 'Location', field: 'location' }, { title: 'Rating', field: 'rating' }, { title: 'Inspected', field: 'inspected' }, { title: 'Source', field: 'source' }],
    Contracts: [{ title: 'Date', field: 'date' }, { title: 'Evidence', field: 'evidence' }, { title: 'Detail', field: 'detail' }, { title: 'Source', field: 'source' }],
    'Safety/legal': [{ title: 'Date', field: 'date' }, { title: 'Evidence', field: 'evidence' }, { title: 'Detail', field: 'detail' }, { title: 'Source', field: 'source' }],
    'Financial evidence': [{ title: 'Year end', field: 'date' }, { title: 'Evidence', field: 'evidence' }, { title: 'Detail', field: 'detail' }, { title: 'Source', field: 'source' }],
  };
  const cards = items.map(([label, count]) => {
    const card = statCard({ value: num(count), label, sub: count ? 'records held · click to inspect' : 'not collected or not matched' });
    if (!count) return card;
    card.classList.add('evidence-summary-card'); card.tabIndex = 0; card.setAttribute('role', 'button');
    const open = () => openEvidenceModal(label, rowsFor[label] || [], columnsFor[label] || []);
    card.addEventListener('click', open);
    card.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); } });
    return card;
  });
  replace(container, section(
    'Evidence inventory',
    'Counts describe the records held for this provider, not its performance or scale.',
    el('div', { class: 'grid cards' }, cards)));
}

function openEvidenceModal(title, rows, columns) {
  const dialog = el('dialog', { class: 'evidence-modal', 'aria-labelledby': 'evidence-modal-title' },
    el('div', { class: 'evidence-modal-head' }, el('div', {}, el('span', { class: 'eyebrow', text: 'Provider evidence' }), el('h2', { id: 'evidence-modal-title', text: title })), el('button', { class: 'btn ghost', type: 'button', 'aria-label': 'Close evidence table', onclick: () => dialog.close() }, 'Close')),
    el('p', { class: 'small muted', text: `${num(rows.length)} records, newest first.` }),
    tableCard(`${title} — newest first`, columns, rows.slice().sort((a, b) => String(b.date || b.inspected || '').localeCompare(String(a.date || a.inspected || ''))), { height: 520 }));
  document.body.append(dialog); dialog.addEventListener('close', () => dialog.remove(), { once: true }); dialog.showModal();
}

function renderTimeline(container, data) {
  const events = data.events || [];
  const list = el('ul', { class: 'timeline' });
  const ordered = events.slice().sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));
  let visible = 15;
  const draw = () => replace(list, ordered.slice(0, visible).map((event) => {
    const note = event.caveat ? caveat(event.caveat) : null;
    return el('li', { class: event.event_type },
      el('div', { class: 'when', text: isoDate(event.date) }),
      el('div', { class: 'what' }, event.label || event.event_type,
        note ? note.button : null),
      event.value_summary
        ? el('div', { class: 'detail', text: truncate(event.value_summary, 160) }) : null,
      // A contract event links to the notice, not to the API page it was
      // parsed from — that one is a paginated cursor. Everything else has
      // only the one address.
      event.notice_link
        ? el('div', { class: 'small' }, sourceLink(event.notice_link,
            event.notice_link_basis === 'constructed' ? 'notice ↗ (built from id)' : 'notice ↗'))
        : (event.source_url
          ? el('div', { class: 'small' }, sourceLink(event.source_url, 'source ↗')) : null),
      note ? note.body : null);
  }));
  draw();
  const more = el('button', { class: 'btn ghost', type: 'button', text: 'Load more evidence' });
  more.addEventListener('click', () => { visible += 15; draw(); if (visible >= ordered.length) more.hidden = true; });
  more.hidden = ordered.length <= 15;

  replace(container, section(
    'Evidence timeline',
    `${num(events.length)} dated records, newest first. Each carries the `
    + 'document it came from.',
    el('div', { class: 'panel' },
      events.length ? [list, more] : noData('dated evidence', './start.sh run all'))));
}

function renderGraph(container, data, charts, key) {
  const edges = data.entity_edges || [];
  const holder = el('div', {});

  replace(container, section(
    'Entity graph',
    'Company registrations, charity numbers, CQC registrations and contract '
    + 'relationships connected to this provider.',
    el('div', { class: 'panel' },
      edges.some((e) => e.basis === 'name_only_unconfirmed')
        ? pinnedCaveat(
          'Dashed edges matched on name alone. A name that coincides is not a '
          + 'relationship that exists, and nothing here has been confirmed '
          + 'against a register.', 'Unconfirmed edges')
        : null,
      holder)));

  if (!edges.length) {
    replace(holder, noData('entity relationships', './start.sh run m04_companies'));
    return;
  }

  const nodes = new Map();
  const addNode = (id, label, type) => {
    if (!id || nodes.has(id)) return;
    nodes.set(id, {
      id, name: truncate(label || id, 28), category: type || 'other',
      symbolSize: id === key ? 42 : 22,
      itemStyle: id === key ? { color: '#f59e0b' } : undefined,
    });
  };

  for (const edge of edges) {
    addNode(edge.source_id, edge.source_id, edge.source_type);
    addNode(edge.target_id, edge.target_label, edge.target_type);
  }

  const categories = [...new Set([...nodes.values()].map((n) => n.category))]
    .map((name) => ({ name }));

  charts.push(mountChart(holder, {
    legend: { top: 0, data: categories.map((c) => c.name) },
    tooltip: {
      formatter: (p) => (p.dataType === 'edge'
        ? `${escapeHtml(p.data.relationship || '')}<br><span style="color:#8b949e">`
          + `${escapeHtml(p.data.basis || '')}</span>`
        : `<strong>${escapeHtml(p.data.name)}</strong><br>`
          + `<span style="color:#8b949e">${escapeHtml(p.data.category)}</span>`),
    },
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      categories,
      force: { repulsion: 260, edgeLength: 130 },
      label: { show: true, color: '#e6edf3', position: 'right', fontSize: 11 },
      edgeLabel: { show: false },
      data: [...nodes.values()].map((n) => ({
        ...n, category: categories.findIndex((c) => c.name === n.category),
      })),
      links: edges.map((e) => ({
        source: e.source_id,
        target: e.target_id,
        relationship: e.relationship,
        basis: e.basis,
        lineStyle: e.basis === 'name_only_unconfirmed'
          ? { type: 'dashed', color: '#f59e0b', opacity: 0.8 }
          : { color: '#30363d', opacity: 0.7 },
      })),
    }],
  }, {
    height: 'tall',
    aria: `Force-directed graph of ${nodes.size} entities connected to this `
      + `provider by ${edges.length} relationships. Dashed edges are matched on `
      + 'name only and are unconfirmed.',
  }));
}

function renderCqc(container, data) {
  const locations = data.cqc_locations || [];
  const ratingClass = (rating) => {
    const value = (rating || '').toLowerCase();
    if (value === 'outstanding' || value === 'good') return 'good';
    if (value.includes('inadequate') || value.includes('requires')) return 'bad';
    return 'neutral';
  };

  const inspections = data.cqc_inspections || [];
  const latestReport = new Map();
  for (const report of inspections) if (!latestReport.has(report.location_id)) latestReport.set(report.location_id, report);
  replace(container, section(
    'CQC registrations',
    `${num(locations.length)} registered locations.`,
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.cqc_coverage, 'This is not a service map'),
      locations.length
        ? el('div', { style: 'display:flex;flex-wrap:wrap;gap:8px;' },
          locations.map((l) => {
            const report = latestReport.get(l.location_id);
            // m26_cqc_directory backfills a rating here only when the CQC
            // API supplied none at all for this location -- see its module
            // docstring. Marked '*' rather than shown silently: it is CQC's
            // own bulk export, not the per-location record m05_cqc fetched.
            const fromBulk = l.rating_source === 'bulk_export';
            const label = `${l.overall_rating || 'not rated'}${fromBulk ? '*' : ''}`;
            // No fetched report is not a reason to leave the badge dead:
            // every location has a real, stable page on CQC's own site
            // (confirmed present as a URL column in both bulk files this
            // pipeline reads), which is where the report actually lives.
            // Not a guess at the report's own path -- report_uri's own
            // handling above is why this deliberately does not try that.
            return el('a', {
              class: `badge ${ratingClass(l.overall_rating)}`,
              title: `${l.location_name} — ${label}`
                + (fromBulk ? ' (from CQC’s bulk ratings export; the API has no rating on record)' : '')
                + (report ? '' : ' — links to the CQC location page, not a specific report'),
              href: report ? cqcReportHref(report) : cqcLocationHref(l.location_id),
              target: '_blank', rel: 'noopener noreferrer',
            }, `${truncate(l.location_name, 34)} · ${label}`);
          }))
        : noData('CQC locations', './start.sh run m05_cqc'))));
}

function cqcLocationHref(locationId) {
  return `https://www.cqc.org.uk/location/${encodeURIComponent(locationId)}`;
}

function cqcReportHref(report) {
  const uri = String(report.report_uri || '');
  const apiRoot = 'https://api.cqc.org.uk/public/v1';
  const reportPath = (path) => path.startsWith('/public/v1/')
    ? path
    : `/public/v1${path.startsWith('/') ? path : `/${path}`}`;

  if (/^https?:\/\//i.test(uri)) {
    try {
      const parsed = new URL(uri);
      // A URL already hosted somewhere other than the syndication API is a
      // real, ready-to-use link -- m26_cqc_directory's scraped report_uri
      // values are exactly this (a location's own cqc.org.uk page), and
      // forcing them onto api.cqc.org.uk the way the API's *own*
      // report_uri values need normalising produces a dead link (confirmed
      // live: api.cqc.org.uk/public/v1/location/.../reports/... 404s).
      if (parsed.hostname !== 'api.cqc.org.uk') return uri;
      return `${apiRoot}${parsed.pathname.startsWith('/public/v1/')
        ? parsed.pathname.slice('/public/v1'.length)
        : reportPath(parsed.pathname).slice('/public/v1'.length)}${parsed.search}${parsed.hash}`;
    } catch (_) {
      // Fall through to the documented report-path handling below.
    }
  }
  if (uri) return `${apiRoot}${reportPath(uri).slice('/public/v1'.length)}`;
  return report.location_id
    ? `${apiRoot}/locations/${encodeURIComponent(report.location_id)}`
    : `${apiRoot}/reports`;
}

/* W-24: inspection history from cqc_location_reports. A report date is when
 * an inspection report was published, not when a rating changed. */
function renderCqcReports(container, data, charts) {
  const inspections = data.cqc_inspections || [];
  const holder = el('div', {});

  const years = {};
  for (const row of inspections) {
    const year = String(row.report_date || '').slice(0, 4);
    if (year && /^\d{4}$/.test(year)) {
      years[year] = (years[year] || 0) + 1;
    }
  }
  const byYear = Object.entries(years).sort(([a], [b]) => a.localeCompare(b));

  replace(container, section(
    'CQC inspection history',
    `${num(inspections.length)} published inspection reports across `
    + `${num(new Set(inspections.map((r) => r.location_name)).size)} locations.`,
    el('div', { class: 'grid two' },
      el('div', { class: 'panel' },
        el('h3', { text: 'Reports per year' }), holder,
        pinnedCaveat(data.caveats?.cqc_inspection_dates,
          'A report date is an inspection published')),
      el('div', { class: 'panel' },
        el('h3', { text: 'The reports' }),
        inspections.length
          ? tableCard('Inspection reports', [
            { title: 'Location', field: 'location_name' },
            { title: 'Report date', field: 'report_date', width: 130 },
            { title: 'First visit', field: 'first_visit_date', width: 130 },
          ], inspections, { height: 300 })
          : noData('CQC inspection reports', './start.sh run m05_cqc')))));

  if (byYear.length) {
    charts.push(mountChart(holder, {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      xAxis: { type: 'category', data: byYear.map(([year]) => year) },
      yAxis: { type: 'value', name: 'reports' },
      series: [{
        type: 'bar', data: byYear.map(([, n]) => n), itemStyle: { color: '#38bdf8' },
      }],
    }, {
      height: 'short',
      aria: 'Bar chart of CQC inspection reports per year for this provider.',
    }));
  } else {
    replace(holder, noData('CQC inspection reports', './start.sh run m05_cqc'));
  }
}

/* W-24: charity finance. Income against expenditure per year, and the
 * government share of that year's own income. The share is within one row
 * of one source, which the caveat states in terms — combining it with
 * procurement values is the arithmetic this pipeline refuses. */
function renderCharityFinance(container, data, charts) {
  const rows = data.charity_finance || [];
  const incomeHolder = el('div', {});
  const shareHolder = el('div', {});

  replace(container, section(
    'Charity finance',
    'Filed accounts, one row per financial year. The government share is a '
    + 'share of that year\'s own total income.',
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.charity_share,
        'What may and may not be computed here'),
      el('div', { class: 'grid two' },
        el('div', { class: 'panel' },
          el('h3', { text: 'Income and expenditure' }), incomeHolder),
        el('div', { class: 'panel' },
          el('h3', { text: 'Government contracts and grants as a share of income' }),
          shareHolder)))));

  if (!rows.length) {
    replace(incomeHolder, noData('charity financials', './start.sh run m03_charity_finance'));
    return;
  }

  const years = rows.map((r) => String(r.financial_year_end || '').slice(0, 4));
  charts.push(mountChart(incomeHolder, {
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    xAxis: { type: 'category', data: years },
    yAxis: { type: 'value', name: '£' },
    series: [
      { name: 'income', type: 'bar', data: rows.map((r) => r.total_income),
        itemStyle: { color: '#38bdf8' } },
      { name: 'expenditure', type: 'bar', data: rows.map((r) => r.total_expenditure),
        itemStyle: { color: '#30363d' } },
    ],
  }, {
    height: 'short',
    aria: 'Bar chart of total income and expenditure per financial year for '
      + 'this provider.',
  }));

  charts.push(mountChart(shareHolder, {
    tooltip: {
      trigger: 'axis',
      formatter: (params) => params.map((p) =>
        `<strong>${escapeHtml(p.seriesName)}</strong> — ${pct(p.value)}`
      ).join('<br>'),
    },
    legend: { top: 0 },
    xAxis: { type: 'category', data: years },
    yAxis: { type: 'value', name: 'share of income', axisLabel: { formatter: '{value}%' } },
    series: [
      { name: 'government contracts', type: 'bar',
        data: rows.map((r) => r.govt_contracts_share == null ? null : +(r.govt_contracts_share * 100).toFixed(1)),
        itemStyle: { color: '#f59e0b' } },
      { name: 'government grants', type: 'bar',
        data: rows.map((r) => r.govt_grants_share == null ? null : +(r.govt_grants_share * 100).toFixed(1)),
        itemStyle: { color: '#a78bfa' } },
    ],
  }, {
    height: 'short',
    aria: 'Bar chart of government contract and grant income as a share of '
      + 'each year\'s total income, within the same row of the filed accounts.',
  }));
}

/* W-24: what a report does not discuss. The matrix distinguishes three
 * states and the caveat pins the weakest one: "not matched" means the
 * search terms did not appear in the extracted text, which is a statement
 * about the PDF and the terms, not about the provider. */
function renderDisclosure(container, data, charts) {
  const disclosure = data.disclosure || {};
  const gaps = disclosure.gaps || [];
  const disclosed = disclosure.disclosed || [];
  const notSearched = disclosure.not_searched || [];
  const topics = disclosure.topics || [];
  const years = [...new Set([
    ...gaps.map((g) => g.financial_year_end),
    ...disclosed.map((d) => d.financial_year_end),
    ...notSearched.map((n) => n.financial_year_end),
  ])].sort();
  const holder = el('div', {});

  const gapCaveat = gaps.find((g) => g.caveat)?.caveat;
  const gapByKey = new Map(gaps.map((g) => [`${g.financial_year_end}|${g.topic}`, g]));
  const notSearchedYears = new Set(notSearched.map((n) => n.financial_year_end));

  replace(container, section(
    'Annual report disclosure',
    'What each annual report appears not to discuss, by topic and year. '
    + 'Every cell is a prompt to look, not a finding in itself.',
    el('div', { class: 'panel' },
      gapCaveat ? pinnedCaveat(gapCaveat, 'Read before citing a gap') : null,
      holder)));

  if (!topics.length) {
    replace(holder, noData('annual report disclosure', './start.sh run m14_annual_reports'));
    return;
  }

  const cellData = [];
  for (const year of years) {
    for (const topic of topics) {
      const gap = gapByKey.get(`${year}|${topic}`);
      let value = 2; // disclosed: the terms matched
      if (notSearchedYears.has(year)) value = 0; // the report was never searched
      else if (gap) value = 1; // searched, and the terms did not match
      cellData.push([years.indexOf(year), topics.indexOf(topic), value]);
    }
  }

  charts.push(mountChart(holder, {
    tooltip: {
      formatter: (p) => {
        const topic = topics[p.value[1]];
        const year = years[p.value[0]];
        const gap = gapByKey.get(`${year}|${topic}`);
        if (gap) {
          return `<strong>${escapeHtml(topic)}</strong>, ${escapeHtml(year)}`
            + `<br><span style="color:#f59e0b">terms did not match</span><br>`
            + `<span style="color:#8b949e">${escapeHtml(gap.search_terms)}</span>`;
        }
        if (notSearchedYears.has(year)) {
          return `<strong>${escapeHtml(topic)}</strong>, ${escapeHtml(year)}`
            + `<br><span style="color:#8b949e">annual report not searched</span>`;
        }
        return `<strong>${escapeHtml(topic)}</strong>, ${escapeHtml(year)}`
          + `<br><span style="color:#34d399">terms matched</span>`;
      },
    },
    xAxis: { type: 'category', data: years, splitArea: { show: true } },
    yAxis: { type: 'category', data: topics, splitArea: { show: true } },
    visualMap: {
      min: 0, max: 2, show: false,
      inRange: { color: ['#21262d', '#f59e0b', '#34d399'] },
    },
    series: [{
      type: 'heatmap', data: cellData,
      label: { show: false },
      emphasis: { itemStyle: { borderColor: '#e6edf3', borderWidth: 1 } },
    }],
  }, {
    height: 'tall',
    aria: 'Heatmap of annual report disclosure by topic and year. Amber cells '
      + 'are topics whose search terms did not match; green cells matched; '
      + 'dark cells are years whose report was never searched.',
  }));
}

/* W-24: the filing history. Each row links to the document itself on
 * Companies House's document API; the caveat says a filing is a record of a
 * document, not a statement about the provider. */
function renderFilings(container, data) {
  const filings = data.filings || [];

  replace(container, section(
    'Company filing history',
    `${num(filings.length)} documents filed at Companies House.`,
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.filing_records, 'A filing is not a finding'),
      filings.length
        ? tableCard('Filings', [
          { title: 'Filed', field: 'filing_date', width: 110,
            formatter: (c) => isoDate(c.getValue()) },
          { title: 'Category', field: 'category', width: 130 },
          { title: 'Subcategory', field: 'subcategory', width: 130 },
          { title: 'Description', field: 'description' },
          { title: 'Document', field: 'document_url', width: 100, headerFilter: false,
            formatter: (c) => (c.getValue()
              ? el('a', { href: c.getValue(), target: '_blank', rel: 'noopener noreferrer' },
                'document ↗')
              : '') },
        ], filings, { height: 380 })
        : noData('company filings', './start.sh run m04_companies'))));
}

/* W-25's deep-dive half: the reports that mention this provider. Sent and
 * named stay visibly different rows, and the caveat says the two are never
 * added. Each report links to the coroner's published page. */
function renderPfd(container, data) {
  const mentions = data.pfd_mentions || [];
  const sent = mentions.filter((m) => m.mention_type === 'recipient');
  const named = mentions.filter((m) => m.mention_type === 'body_text');

  const row = (m) => el('li', { class: m.mention_type },
    el('div', { class: 'when', text: m.report_date || '—' }),
    el('div', { class: 'what' },
      m.mention_type === 'recipient'
        ? `Report sent to this provider (matched: ${m.matched_name || 'unknown'})`
        : `Report names this provider (matched: ${m.matched_name || 'unknown'})`,
      el('div', { class: 'small' }, sourceLink(m.report_url, 'report ↗'))),
    el('div', { class: 'detail', text: m.coroner_area || '' }));

  replace(container, section(
    'Coroners\' reports mentioning this provider',
    `${num(sent.length)} reports addressed to this provider; `
    + `${num(named.length)} naming it in the text. Two different facts, `
    + 'shown separately and never added together.',
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.pfd_mentions, 'Sent and named are different facts'),
      mentions.length
        ? el('ul', { class: 'timeline' }, mentions.map(row))
        : noData('PFD mentions', './start.sh run m08_pfd_reports'))));
}

function renderTribunals(container, data) {
  const cases = data.tribunal_cases || [];
  replace(container, section(
    'Employment tribunal cases',
    `${num(cases.length)} judgments naming this provider.`,
    el('div', { class: 'panel' },
      pinnedCaveat(data.caveats?.tribunal_component, 'Read before counting these'),
      cases.length
        ? tableCard('Cases', [
          { title: 'Case', field: 'case_number', width: 150 },
          { title: 'Decided', field: 'decision_date', width: 120,
            formatter: (c) => isoDate(c.getValue()) },
          { title: 'Outcome', field: 'outcome' },
          { title: 'Confidence', field: 'outcome_confidence', width: 120 },
          { title: 'Basis', field: 'provider_match_basis', width: 130 },
          { title: 'Venue', field: 'hearing_venue_raw' },
        ], cases, { height: 320 })
        : noData('tribunal judgments', './start.sh run m02_tribunals'))));
}
