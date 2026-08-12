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

import { el, replace, sourceLink, exportUrl, ago, isoDate } from '/app.js';
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

/** The provenance drawer under a chart. Source, when it was fetched, and the
 *  hash of the payload it was parsed from. */
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

export function exportButton(endpoint, params = {}, label = 'Download CSV') {
  return el('a', {
    class: 'btn tiny', href: exportUrl(endpoint, params, 'csv'),
    title: 'Downloads with its provenance written into the file',
  }, label);
}

export function statCard({ value, label, sub, caveat: caveatText, plain = false,
                            unverified = false }) {
  const note = caveat(caveatText);
  return el('div', { class: `statcard${unverified ? ' unverified' : ''}` },
    el('div', { class: `value${plain ? ' plain' : ''}`, text: value }),
    el('div', { class: 'label' }, label, note ? note.button : null),
    sub ? el('div', { class: 'sub' }, sub) : null,
    unverified ? el('span', { class: 'badge unverified', text: 'AWAITING VERIFICATION' }) : null,
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

export function mountChart(container, option, { height = null, aria = null } = {}) {
  registerTheme();
  if (!window.echarts) {
    replace(container, errorCard('Charting library did not load.'));
    return null;
  }

  const holder = el('div', { class: `chart${height ? ` ${height}` : ''}` });
  const wrap = el('div', {
    class: 'chartwrap', role: 'img',
    'aria-label': aria || 'Chart',
  }, holder);
  replace(container, wrap);

  const chart = window.echarts.init(holder, 'sectorTrace');
  chart.setOption(option);

  const observer = new ResizeObserver(() => chart.resize());
  observer.observe(holder);
  observers.set(chart, observer);
  return chart;
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

export function table(container, columns, rows, { height = 420, rowClass = null } = {}) {
  if (!window.Tabulator) {
    // Degrade to a plain table rather than showing nothing.
    const head = el('tr', {}, columns.map((c) => el('th', { text: c.title })));
    const body = rows.slice(0, 200).map((r) =>
      el('tr', {}, columns.map((c) => el('td', { text: r[c.field] ?? '' }))));
    replace(container, el('table', {}, el('thead', {}, head), el('tbody', {}, body)));
    return null;
  }
  return new window.Tabulator(container, {
    data: rows,
    columns,
    height,
    layout: 'fitColumns',
    placeholder: 'No rows match these filters.',
    rowFormatter: rowClass ? (row) => {
      const cls = rowClass(row.getData());
      if (cls) row.getElement().classList.add(cls);
    } : undefined,
  });
}

export function tableCard(title, columns, rows, options = {}) {
  const holder = el('div', {});
  const card = el('div', { class: 'tablecard' },
    el('div', { class: 'toolbar' },
      el('h3', { text: title }),
      el('span', { class: 'spacer' }),
      options.exportEndpoint
        ? exportButton(options.exportEndpoint, options.exportParams || {})
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
