/* Reusable pieces of the portal.
 *
 * The two that matter are `caveat()` and `provenance()`. This pipeline's
 * position is that a figure is defensible or it is not published, and the
 * portal is where that stops being a policy and becomes something a reader
 * can see. Both take their text from the API rather than holding a copy: a
 * caveat written into the frontend is one that will still be there after the
 * warehouse stops justifying it.
 */
'use strict';

import { el, replace, sourceLink, exportUrl, ago, isoDate, num } from '/app.js';
import { registerTheme, SYMBOLS } from '/js/theme.js';

let caveatSeq = 0;

/** An inline, expandable caveat. Never a modal — a warning that interrupts
 *  reading gets dismissed by reflex, and this one has to be readable at the
 *  moment someone is looking at the number it belongs to. */
export function caveat(text, { label = 'Read the caveat' } = {}) {
  if (!text) return null;
  const id = `caveat-${++caveatSeq}`;
  const body = el('div', { class: 'caveat-body', id, hidden: true, text });
  const button = el('button', {
    class: 'caveat-badge', type: 'button',
    'aria-expanded': 'false', 'aria-controls': id, title: label,
    onclick: () => {
      const open = body.hidden;
      body.hidden = !open;
      button.setAttribute('aria-expanded', String(open));
    },
  }, 'ⓘ');
  return { button, body };
}

/** A caveat that cannot be closed, for figures that are routinely misread. */
export function pinnedCaveat(text, lead = 'Read this with the figure') {
  if (!text) return null;
  return el('div', { class: 'caveat-pinned' },
    el('strong', { text: `${lead}: ` }), text);
}

/* Licence per source, mirrored from pipeline/licences.py.
 *
 * A copy, because this phase adds no route and the drawer is drawn from what
 * the page already knows — the module id it passes to provenance(). The copy
 * is held to the Python table by tests/test_licences.py, which fails on any
 * difference in either direction; edit both or neither.
 *
 * Most of it is OGL v3. The two entries that are not are the two most
 * quotable sources this pipeline holds, which is exactly why the drawer says
 * so rather than printing "public-domain source" over everything.
 */
const OGL_URL = 'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/';

const LICENCES = {
  ogl_v3: {
    name: 'Open Government Licence v3.0', url: OGL_URL,
    attribution: 'Contains public sector information licensed under the Open '
      + 'Government Licence v3.0.',
    caution: '',
  },
  ogl_v3_os: {
    name: 'Open Government Licence v3.0 (contains OS data)', url: OGL_URL,
    attribution: 'Contains public sector information licensed under the Open '
      + 'Government Licence v3.0. Contains OS data © Crown copyright and '
      + 'database right.',
    caution: '',
  },
  nhs_benchmarking: {
    name: 'NHS England / NHS Benchmarking Network — not OGL', url: null,
    attribution: 'NHS England / NHS Benchmarking Network content.',
    caution: 'Not open-licensed. Check the publisher’s terms before '
      + 'republishing any figure from it.',
  },
  authority_varies: {
    name: 'Varies by authority', url: null,
    attribution: 'Local authority publications; the publishing authority holds '
      + 'the rights.',
    caution: 'Most councils publish under OGL v3.0 and none of them is '
      + 'guaranteed to. Check the individual document before republishing it.',
  },
  charity_own: {
    name: 'The charity’s own copyright', url: null,
    attribution: 'Filed accounts from the public register of charities.',
    caution: 'A public record, not an open licence. Passages are held as '
      + 'evidence rather than republished wholesale.',
  },
  mysociety_mixed: {
    name: 'CC BY-SA (mySociety) with OGL v3.0 responses',
    url: 'https://creativecommons.org/licenses/by-sa/4.0/',
    attribution: 'Authority register and search data from mySociety '
      + '(WhatDoTheyKnow) under CC BY-SA; FOI responses generally OGL v3.0.',
    caution: 'Share-alike applies to the mySociety half. Council disclosure '
      + 'logs carry their own terms.',
  },
  nhs_jobs: {
    name: 'Crown copyright, advert content the employer’s', url: null,
    attribution: 'NHS Jobs service, Crown copyright.',
    caution: 'The text of each advert belongs to the employer that placed it.',
  },
  lwf_own: {
    name: 'Living Wage Foundation — charity-published register', url: null,
    attribution: 'Accredited employer list published by the Living Wage '
      + 'Foundation (a Citizens UK initiative).',
    caution: 'Not open-licensed. The list is factual data about which '
      + 'employers are accredited; check the foundation’s terms before '
      + 'republishing it in bulk.',
  },
  provider_own: {
    name: 'The provider’s own copyright', url: null,
    attribution: 'Pages published on the provider’s own website.',
    caution: 'A public website, not an open licence. Passages are held as '
      + 'evidence rather than republished wholesale.',
  },
  skills_for_care: {
    name: 'OGL v3.0 (ASC-WDS data, per the data.gov.uk catalogue)',
    url: OGL_URL,
    attribution: 'Adult Social Care Workforce Data Set (ASC-WDS) workforce '
      + 'estimates, published by Skills for Care.',
    caution: 'The data.gov.uk catalogue entry for ASC-WDS states OGL v3.0; '
      + 'the publisher’s own pages carry a site-wide copyright line. '
      + 'Official statistics under the Code of Practice for Statistics; '
      + 'check the publisher’s terms before republishing.',
  },
};

const MODULE_LICENCES = {
  m00_geography: 'ogl_v3_os',
  m01_procurement: 'ogl_v3',
  m02_tribunals: 'ogl_v3',
  m03_charity_finance: 'ogl_v3',
  m04_companies: 'ogl_v3',
  m05_cqc: 'ogl_v3',
  m06_workforce_census: 'nhs_benchmarking',
  m07_ndtms: 'ogl_v3',
  m08_pfd_reports: 'ogl_v3',
  m09_cdp_documents: 'authority_varies',
  m10_committee_papers: 'authority_varies',
  m11_public_health_grant: 'ogl_v3',
  m12_fingertips: 'ogl_v3',
  m13_la_budgets: 'ogl_v3',
  m14_annual_reports: 'charity_own',
  m15_foi: 'mysociety_mixed',
  m16_nhs_jobs: 'nhs_jobs',
  m17_statutory_pay_rates: 'ogl_v3',
  m18_living_wage: 'lwf_own',
  m19_data_gov_uk: 'ogl_v3',
  m20_gender_pay_gap: 'ogl_v3',
  m21_ons_ashe: 'ogl_v3',
  m22_provider_pay_pages: 'provider_own',
  m23_sector_universe: 'ogl_v3',
  m24_council_spend: 'authority_varies',
  m25_skills_for_care: 'skills_for_care',
  m26_cqc_directory: 'ogl_v3',
};

export function licenceFor(module) {
  return LICENCES[MODULE_LICENCES[module]] || null;
}

/** The provenance drawer under a chart. Source, when it was fetched, the
 *  licence its reuse is governed by, and the hash of the payload it was
 *  parsed from. */
export function provenance({ sources = [], retrievedAt = null, module = null,
                              hash = null, tables = [] } = {}) {
  const rows = [];
  const urls = [...new Set(sources.filter(Boolean))].slice(0, 6);
  if (urls.length) {
    rows.push(el('dt', { text: urls.length > 1 ? 'Sources' : 'Source' }));
    rows.push(el('dd', {}, urls.map((u, i) =>
      el('div', {}, sourceLink(u, u.length > 90 ? `${u.slice(0, 90)}…` : u), i < urls.length - 1 ? '' : ''))));
  }
  if (retrievedAt) {
    rows.push(el('dt', { text: 'Retrieved' }));
    rows.push(el('dd', {}, `${ago(retrievedAt)} (${retrievedAt})`));
  }
  if (tables.length) {
    rows.push(el('dt', { text: 'Warehouse tables' }));
    rows.push(el('dd', { class: 'mono', text: tables.join(', ') }));
  }
  if (module) {
    rows.push(el('dt', { text: 'Collected by' }));
    rows.push(el('dd', { class: 'mono', text: module }));

    // Beside the figure, not on a page about the portal. A citation whose
    // terms the reader cannot state is an unfinished one.
    const lic = licenceFor(module);
    if (lic) {
      rows.push(el('dt', { text: 'Licence' }));
      rows.push(el('dd', {},
        lic.url ? sourceLink(lic.url, lic.name) : lic.name,
        // The attribution wording is here to be copied, not summarised: it is
        // the condition of the licence, and a reuser who has to compose it
        // themselves composes it differently every time.
        el('div', { class: 'small muted', text: lic.attribution }),
        lic.caution ? el('div', { class: 'small licence-caution', text: lic.caution }) : null));
    }
  }
  if (hash) {
    rows.push(el('dt', { text: 'Payload SHA-256' }));
    rows.push(el('dd', {},
      el('span', { class: 'hash', text: `${String(hash).slice(0, 8)}…` }),
      ' ',
      el('button', {
        class: 'btn tiny', type: 'button',
        onclick: (e) => {
          navigator.clipboard?.writeText(String(hash));
          e.target.textContent = 'copied';
          setTimeout(() => { e.target.textContent = 'copy full hash'; }, 1500);
        },
      }, 'copy full hash')));
  }

  if (!rows.length) return null;
  return el('details', { class: 'provenance' },
    el('summary', { text: 'Where this came from' }),
    el('dl', {}, rows));
}

/** Pulls provenance out of a list of rows that carry it per-record, which is
 *  how nearly every table in this warehouse stores it. */
export function provenanceFromRows(rows, { module = null, tables = [] } = {}) {
  const list = Array.isArray(rows) ? rows : [];
  return provenance({
    sources: list.map((r) => r.source_url).filter(Boolean),
    retrievedAt: list.map((r) => r.retrieved_at).filter(Boolean).sort().pop() || null,
    hash: list.find((r) => r.payload_sha256)?.payload_sha256 || null,
    module, tables,
  });
}

/* Links into the registers a provider is on.
 *
 * The cheapest verification affordance there is, and the portal had none: the
 * warehouse holds company and charity numbers and rendered both as plain
 * text, so checking one meant a manual search. Every link is labelled *verify
 * at source*, which is the whole point of the wording — it is an offer to go
 * and check, not this project asserting that the register says what the
 * warehouse says.
 *
 * Both shapes were checked against the live registers on 2026-08-14 with real
 * identifiers from this warehouse, not taken from memory:
 *
 *   company_number 03861209 -> the Companies House profile for CHANGE, GROW, LIVE
 *   charity_number 1079327  -> one match, CHANGE, GROW, LIVE
 *   charity_number 234887   -> one match, TURNING POINT
 *
 * The Charity Commission's charity-details page is keyed by an internal
 * organisation number this pipeline does not store, so the link is the
 * register's own search on the registered charity number — which returns
 * exactly one match for a valid number. One click further and honest about
 * what it is, rather than a details URL built from an id we do not hold.
 *
 * CQC is deliberately absent. The public API publishes no profile URL for a
 * location (checked against 520 archived payloads, which contain no
 * cqc.org.uk address at all), and the shape could not be verified without
 * working around a bot block, which this project does not do. See
 * docs/upgrade-roadmap.md, W-15.
 */
const REGISTERS = {
  company_number: {
    label: 'Companies House',
    url: (id) => 'https://find-and-update.company-information.service.gov.uk/company/'
      + encodeURIComponent(id),
  },
  company: {
    label: 'Companies House',
    url: (id) => 'https://find-and-update.company-information.service.gov.uk/company/'
      + encodeURIComponent(id),
  },
  charity_number: {
    label: 'Charity Commission',
    url: (id) => 'https://register-of-charities.charitycommission.gov.uk/en/'
      + 'charity-search/-/results/page/1/delta/20/keywords/' + encodeURIComponent(id),
  },
};

export function registerLink(scheme, identifier) {
  const register = REGISTERS[scheme];
  if (!register || !identifier) return null;
  return el('a', {
    class: 'registerlink',
    href: register.url(identifier),
    target: '_blank', rel: 'noopener noreferrer',
    title: `Verify at source: ${register.label} record ${identifier}`,
  }, `${register.label} ${identifier} ↗`);
}

/** The line under a provider's name. `pairs` is [{scheme, identifier}], which
 *  is the shape the entity edges already arrive in. */
export function registerLinks(pairs) {
  const seen = new Set();
  const links = [];
  for (const { scheme, identifier } of pairs || []) {
    const link = registerLink(scheme, identifier);
    // Deduplicated on the register record, not on the scheme that named it.
    // A company number reaches this from two edges — `company_number` in the
    // identifier register and `company` from Companies House itself — and
    // they are one company, so keying on the scheme showed it twice.
    if (!link || seen.has(link.href)) continue;
    seen.add(link.href);
    links.push(link);
  }
  if (!links.length) return null;
  return el('p', { class: 'registers small' },
    el('span', { class: 'muted', text: 'Verify at source: ' }), links);
}

/* The download is not the table.
 *
 * A page asks for a window — 1,000 notices of 98,636 — and this button asks
 * the server for every row matching the same filters. Saying so on the button
 * matters because the previous behaviour was the opposite and silent: the CSV
 * carried the page's first 500 rows with nothing in the file admitting it.
 * `total`, where the caller knows it, puts the number the reader is about to
 * receive next to the number they can see. */
export function exportButton(endpoint, params = {}, label = 'Download CSV',
                             { total = null } = {}) {
  return el('a', {
    class: 'btn tiny', href: exportUrl(endpoint, params, 'csv'),
    title: total
      ? `Downloads all ${num(total)} rows matching these filters — not just the `
        + 'rows on this page — with its provenance written into the file'
      : 'Downloads every row matching these filters, with its provenance '
        + 'written into the file',
  }, label);
}

/** A share action that degrades to copying the current URL. The URL is the
 *   evidence state for the portal, so sharing it preserves the route and any
 *   filters without inventing a second representation of the page. */
export function shareButton({ title = 'SectorTrace', text = '',
                              url = window.location.href,
                              label = 'Share overview' } = {}) {
  const button = el('button', {
    class: 'btn ghost share-button', type: 'button',
    'aria-label': label,
    onclick: async () => {
      const original = button.textContent;
      try {
        if (navigator.share) {
          await navigator.share({ title, text, url });
          button.textContent = 'Shared';
        } else if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(`${text}\n${url}`.trim());
          button.textContent = 'Link copied';
        } else {
          button.textContent = 'Copy unavailable';
        }
      } catch (error) {
        // Closing the native share sheet is not a failure worth surfacing.
        if (error?.name === 'AbortError') return;
        button.textContent = 'Share failed';
      }
      setTimeout(() => { button.textContent = original; }, 1600);
    },
  }, label);
  return button;
}

// Public campaign vocabulary. Keeping this in one place means route cards,
// findings and workbench headers cannot drift into different labels.
export const CAMPAIGN_LENSES = Object.freeze({
  workforce: { label: 'Workforce', className: 'workforce', routes: ['#/pay', '#/providers'] },
  money: { label: 'Public money', className: 'money', routes: ['#/contracts', '#/geography'] },
  access: { label: 'Service access', className: 'access', routes: ['#/geography', '#/providers', '#/treatment', '#/coverage'] },
  safety: { label: 'Safety & legal', className: 'safety', routes: ['#/pfd', '#/claims'] },
  accountability: { label: 'Accountability', className: 'accountability', routes: ['#/coverage', '#/claims', '/api'] },
});

export function lensBadge(lens, { label = null } = {}) {
  const item = CAMPAIGN_LENSES[lens] || { label: lens, className: 'default' };
  if (!item.label) return null;
  return el('span', { class: `lens-badge lens-${item.className}`, text: label || item.label });
}

// Timing is deliberately explicit. Callers must provide the kind; no route
// can accidentally turn a warehouse retrieval timestamp into “Live”.
export function timingBadge({ kind = null, date = null } = {}) {
  const labels = {
    current: 'Current extract', snapshot: 'Dated snapshot',
    historical: 'Historical', live: 'Live',
  };
  if (!labels[kind]) return null;
  const suffix = date ? ` · ${date}` : '';
  return el('span', { class: `timing-badge timing-${kind}`, title: date || null,
    text: `${labels[kind]}${suffix}` });
}

/** Extract only explicit row metadata. This deliberately does not manufacture
 * a source or retrieval date from a module name or the browser clock. */
export function evidenceMeta(payload) {
  const rows = Object.values(payload || {}).flatMap((value) => Array.isArray(value) ? value : []);
  const sources = [...new Set(rows.map((row) => row?.source_url).filter(Boolean))].slice(0, 4);
  const retrievedAt = rows.map((row) => row?.retrieved_at).filter(Boolean).sort().pop() || null;
  return { sources, retrievedAt };
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text);
  const area = el('textarea', { class: 'clipboard-fallback', text });
  document.body.append(area); area.select();
  document.execCommand('copy'); area.remove();
}

export function copyBriefingButton({ finding, value = null, evidenceStatus,
                                     caveat: caveatText = null, sources = [],
                                     retrievedAt = null, url = window.location.href,
                                     label = 'Copy briefing bundle' } = {}) {
  if (!finding || !evidenceStatus || (!sources.length && !retrievedAt)) return null;
  const button = el('button', { class: 'btn ghost briefing-copy', type: 'button',
    'aria-label': label, onclick: async () => {
      const lines = [
        'SectorTrace briefing', `Finding: ${finding}`,
        value ? `Value: ${value}` : null, `Evidence: ${evidenceStatus}`,
        caveatText ? `Caveat: ${caveatText}` : null,
        sources.length ? `Source: ${sources.join('; ')}` : null,
        retrievedAt ? `Retrieved: ${retrievedAt}` : null, `URL: ${url}`,
      ].filter(Boolean);
      const original = button.textContent;
      try { await copyText(lines.join('\n')); button.textContent = 'Briefing copied'; }
      catch { button.textContent = 'Copy unavailable'; }
      setTimeout(() => { button.textContent = original; }, 1800);
    } }, label);
  return button;
}

export function findingBlock({ finding, value = null, evidenceStatus,
                               timing = null, caveat: caveatText = null,
                               sources = [], retrievedAt = null,
                               url = window.location.href } = {}) {
  const copy = copyBriefingButton({ finding, value, evidenceStatus,
    caveat: caveatText, sources, retrievedAt, url });
  if (!finding || !evidenceStatus || (!sources.length && !retrievedAt)) return null;
  return el('aside', { class: 'finding-block', 'aria-label': 'What this shows' },
    el('div', { class: 'finding-kicker' }, 'What this shows',
      timingBadge(timing || {}), el('span', { class: 'badge good', text: evidenceStatus })),
    el('p', { class: 'finding-text', text: finding }),
    caveatText ? el('p', { class: 'finding-caveat' }, el('strong', { text: 'Caveat: ' }), caveatText) : null,
    el('div', { class: 'finding-meta' },
      sources.length ? el('span', { text: `Source: ${sources[0]}` }) : null,
      retrievedAt ? el('span', { text: `Retrieved: ${retrievedAt}` }) : null,
      copy));
}

export function thinEvidenceControl({ count, threshold, checked = true, onChange,
                                      label = 'Include thin evidence' } = {}) {
  if (!Number.isFinite(Number(count)) || !Number.isFinite(Number(threshold))) return null;
  const input = el('input', { type: 'checkbox', checked, id: `thin-${++caveatSeq}` });
  input.addEventListener('change', () => onChange?.(input.checked));
  return el('label', { class: 'thin-evidence-control', title: `Thin evidence: fewer than ${threshold}` },
    input, `${label} (${num(count)} below ${num(threshold)})`);
}

export function statCard({ value, label, sub, caveat: caveatText, plain = false,
                            unverified = false, status = null,
                            statusClass = 'neutral', action = null }) {
  const note = caveat(caveatText);
  return el('div', { class: `statcard${unverified ? ' unverified' : ''}` },
    el('div', { class: `value${plain ? ' plain' : ''}`, text: value }),
    el('div', { class: 'label' }, label, note ? note.button : null),
    sub ? el('div', { class: 'sub' }, sub) : null,
    status ? el('span', { class: `badge ${statusClass}`, text: status }) : null,
    unverified ? el('span', { class: 'badge unverified', text: 'Not yet human-verified' }) : null,
    action ? el('div', { class: 'statcard-actions' }, action) : null,
    note ? note.body : null);
}

export function section(title, description, ...body) {
  return el('section', { class: 'section' },
    el('header', {},
      el('h2', { text: title }),
      description ? el('p', { text: description }) : null),
    ...body);
}

/** No data is a state worth rendering, not a section to hide. Says which
 *  module produces it and what to run — the reader may well be the person who
 *  can fix it. */
export function noData(what, command) {
  return el('div', { class: 'chart-empty' },
    el('strong', { text: `No ${what} in the warehouse yet.` }),
    command ? el('div', { class: 'small' }, 'Run ', el('code', { text: command })) : null);
}

export function errorCard(message, retry) {
  return el('div', { class: 'chart-error' },
    el('strong', { text: 'Could not load this.' }),
    el('span', { class: 'small', text: message }),
    retry ? el('button', { class: 'btn', onclick: retry }, 'Retry') : null);
}

/* Every chart resizes against its own container, not the window. The filter
 * bar wraps to a second row at some widths and the map's side panel collapses
 * — both change a chart's width without the window changing at all. */
const observers = new Map();

export function mountChart(container, option, { height = null, aria = null,
                                                 caption = null,
                                                 caveat: caveatText = null } = {}) {
  registerTheme();
  if (!window.echarts) {
    replace(container, errorCard('Charting library did not load.'));
    return null;
  }

  // role="img" sits on the chart itself rather than on the wrapper, because
  // the wrapper now also holds a button and the children of an img role are
  // presentational — a save button inside one is a button no screen reader
  // announces.
  const holder = el('div', {
    class: `chart${height ? ` ${height}` : ''}`,
    role: 'img', 'aria-label': aria || 'Chart',
  });
  const save = el('button', {
    class: 'btn tiny chart-save', type: 'button',
    title: 'Download this chart as an image, with its caption and caveat drawn into it',
    onclick: () => saveChartImage(chart, wrap, { caption, caveat: caveatText }, save),
  }, 'Save image');
  const wrap = el('div', { class: 'chartwrap' }, holder, save);
  replace(container, wrap);

  const chart = window.echarts.init(holder,
    document.documentElement.dataset.bsTheme === 'light' ? 'sectorTraceLight' : 'sectorTrace');
  chart.setOption(option);

  const observer = new ResizeObserver(() => chart.resize());
  observer.observe(holder);
  observers.set(chart, observer);
  return chart;
}

/* Saving a chart as an image.
 *
 * ECharts owns a canvas and will hand back a PNG of it, which is the easy
 * half and the wrong artefact on its own: the caption above the chart and the
 * caveat beside it are DOM siblings, and an image saved from the canvas keeps
 * neither. A figure that arrives somewhere without the caveat that governs it
 * is the exact failure this portal is built against, so the text is drawn
 * *into* the picture — where it cannot be cropped off by saving.
 *
 * The caption and caveat are read from the DOM around the chart rather than
 * passed in at every call site. That is deliberate: whatever the reader can
 * see next to the figure is what goes into the file, so the two cannot drift.
 * An explicit `caption`/`caveat` on mountChart overrides it.
 */
function chartContext(wrap, { caption, caveat }) {
  const panel = wrap.closest('.panel');
  const section = wrap.closest('.section');
  const heading = [
    section?.querySelector(':scope > header h2')?.textContent,
    panel?.querySelector(':scope > h3')?.textContent,
  ].filter(Boolean).join(' — ');

  // Nearest first: a caveat inside this chart's own panel belongs to this
  // chart. Only if there is none does the section-level one apply.
  const pinned = (root) => [...(root?.querySelectorAll('.caveat-pinned') || [])]
    .map((node) => node.textContent.replace(/\s+/g, ' ').trim())
    .filter(Boolean);
  const notes = caveat ? [caveat] : (pinned(panel).length ? pinned(panel) : pinned(section));

  return { title: caption || heading || 'SectorTrace', notes };
}

function wrapText(ctx, text, maxWidth) {
  const lines = [];
  let line = '';
  for (const word of String(text).split(/\s+/)) {
    const candidate = line ? `${line} ${word}` : word;
    if (line && ctx.measureText(candidate).width > maxWidth) {
      lines.push(line);
      line = word;
    } else {
      line = candidate;
    }
  }
  if (line) lines.push(line);
  return lines;
}

async function saveChartImage(chart, wrap, meta, button) {
  const label = button.textContent;
  try {
    const { title, notes } = chartContext(wrap, meta);
    const scale = 2;
    const source = chart.getDataURL({
      type: 'png', pixelRatio: scale, backgroundColor: '#0d1117',
    });
    const image = await new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error('the chart could not be rasterised'));
      img.src = source;
    });

    const pad = 24 * scale;
    const width = Math.max(image.width, 640 * scale);
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    const textWidth = width - pad * 2;

    // Measure before sizing: setting canvas.width resets the context, so the
    // fonts are established twice — once to lay the text out and once to draw.
    const fonts = {
      title: `700 ${17 * scale}px "Inter", system-ui, sans-serif`,
      note: `${12 * scale}px "Inter", system-ui, sans-serif`,
      foot: `${10.5 * scale}px ui-monospace, Consolas, monospace`,
    };
    ctx.font = fonts.title;
    const titleLines = wrapText(ctx, title, textWidth);
    ctx.font = fonts.note;
    const noteLines = notes.map((note) => wrapText(ctx, note, textWidth - 12 * scale));

    const titleHeight = titleLines.length * 24 * scale;
    const noteHeight = noteLines.reduce(
      (total, lines) => total + lines.length * 17 * scale + 14 * scale, 0);
    const footHeight = 22 * scale;
    canvas.width = width;
    canvas.height = pad + titleHeight + image.height + noteHeight + footHeight + pad;

    ctx.fillStyle = '#0d1117';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    let y = pad + 18 * scale;
    ctx.fillStyle = '#e6edf3';
    ctx.font = fonts.title;
    for (const line of titleLines) {
      ctx.fillText(line, pad, y);
      y += 24 * scale;
    }

    ctx.drawImage(image, (width - image.width) / 2, y - 6 * scale);
    y += image.height + 8 * scale;

    for (const lines of noteLines) {
      const blockHeight = lines.length * 17 * scale;
      ctx.fillStyle = '#f59e0b';
      ctx.fillRect(pad, y - 12 * scale, 3 * scale, blockHeight + 6 * scale);
      ctx.font = fonts.note;
      ctx.fillStyle = '#e6edf3';
      for (const line of lines) {
        ctx.fillText(line, pad + 12 * scale, y);
        y += 17 * scale;
      }
      y += 14 * scale;
    }

    ctx.font = fonts.foot;
    ctx.fillStyle = '#6e7681';
    ctx.fillText(
      `SectorTrace · ${location.href} · saved ${new Date().toISOString().slice(0, 10)}`,
      pad, canvas.height - pad + 6 * scale);

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
    const href = URL.createObjectURL(blob);
    const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
    const link = el('a', {
      href, download: `sectorTrace_${slug || 'chart'}_`
        + `${new Date().toISOString().slice(0, 10).replace(/-/g, '')}.png`,
    });
    link.click();
    // Revoked on the next turn of the loop: revoking synchronously races the
    // download the click just started.
    setTimeout(() => URL.revokeObjectURL(href), 10000);
    button.textContent = 'saved';
  } catch (error) {
    button.textContent = 'could not save';
  }
  setTimeout(() => { button.textContent = label; }, 2000);
}

export function disposeCharts(charts) {
  for (const chart of charts) {
    if (!chart) continue;
    observers.get(chart)?.disconnect();
    observers.delete(chart);
    chart.dispose();
  }
}

/** Symbol per series index, so colour is never the only difference. */
export function symbolFor(index) {
  return SYMBOLS[index % SYMBOLS.length];
}

/* Tabulator ships per-column search and paging and the portal configured
 * neither, so a reader looking for one buyer in 98,636 notices read rows until
 * the page ended. Both are on by default here rather than opted into per page:
 * a table added later inherits them, which is the whole reason this lives in
 * one function.
 *
 * A column opts out with `headerFilter: false` — worth doing for a cell whose
 * displayed text is a link label rather than the value behind it, where a
 * search box would filter on something the reader cannot see.
 */
export function table(container, columns, rows, { height = 420, rowClass = null } = {}) {
  if (!window.Tabulator) {
    // Degrade to a plain table rather than showing nothing — and say what was
    // dropped, because a table that silently stops at row 200 is the failure
    // this whole finding is about, in miniature.
    const head = el('tr', {}, columns.map((c) => el('th', { text: c.title })));
    const shown = rows.slice(0, 200);
    const body = shown.map((r) =>
      el('tr', {}, columns.map((c) => el('td', { text: r[c.field] ?? '' }))));
    replace(container,
      el('table', {}, el('thead', {}, head), el('tbody', {}, body)),
      rows.length > shown.length
        ? el('p', { class: 'small muted',
            text: `Showing ${num(shown.length)} of ${num(rows.length)} rows: the `
              + 'table library did not load, so there is no pager. The download '
              + 'carries what the server sent.' })
        : null);
    return null;
  }
  // Page size follows the height the caller budgeted, so a section that asked
  // for a short table still gets one and the pager lands where the table used
  // to end.
  const perPage = Math.max(8, Math.round((height - 96) / 30));
  return new window.Tabulator(container, {
    data: rows,
    columns: columns.map((column) => (
      column.headerFilter === undefined && column.field
        ? { ...column, headerFilter: 'input', headerFilterPlaceholder: 'search' }
        : column)),
    maxHeight: height,
    layout: 'fitColumns',
    pagination: true,
    paginationSize: perPage,
    paginationCounter: 'rows',
    placeholder: 'No rows match these filters.',
    rowFormatter: rowClass ? (row) => {
      const cls = rowClass(row.getData());
      if (cls) row.getElement().classList.add(cls);
    } : undefined,
  });
}

/** "1,000 of 98,636 rows" — said out loud rather than implied by a table that
 *  simply stops. `total` is the corpus behind the rows the page was given; the
 *  page has to pass it, because nothing in the table can know it. */
export function rowCount(shown, total = null) {
  if (total === null || total === undefined || total <= shown) {
    return `${num(shown)} row${shown === 1 ? '' : 's'}`;
  }
  return `${num(shown)} of ${num(total)} rows`;
}

export function tableCard(title, columns, rows, options = {}) {
  const holder = el('div', {});
  const truncated = options.total > rows.length;
  const card = el('div', { class: 'tablecard' },
    el('div', { class: 'toolbar' },
      el('h3', { text: title }),
      el('span', {
        class: `rowcount${truncated ? ' truncated' : ''}`,
        title: truncated
          ? 'The rest are in the warehouse and were not sent to this page. '
            + 'Narrow the filters to reach them.'
          : null,
        text: rowCount(rows.length, options.total),
      }),
      el('span', { class: 'spacer' }),
      options.exportEndpoint
        ? exportButton(options.exportEndpoint, options.exportParams || {},
                       'Download CSV', { total: options.total ?? rows.length })
        : null),
    holder);
  // Tabulator needs the element in the document before it measures.
  queueMicrotask(() => table(holder, columns, rows, options));
  return card;
}

export function truncate(text, length) {
  const value = String(text ?? '');
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

/* ECharts tooltip formatters take an HTML string, which is the one place in
 * this portal where warehouse text does not arrive as a text node. Everything
 * interpolated into one goes through here. */
export function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

export { isoDate };
