/* Source publication calendar (BETA-091). Each dataset's stated cadence (what
 * the publisher says) sits beside its observed interval (the median gap
 * between retrievals this warehouse holds — an estimate, never merged with the
 * stated figure), its last retrieval, a projected next-expected date and an
 * overdue/unknown status. "Overdue" here does not tell a stalled publisher
 * apart from a collection that has not run; it only says the freshness needs
 * explaining.
 */
'use strict';

import { el, replace, fetchJSON, num, isoDate } from '/app.js';
import { pinnedCaveat, noData, errorCard, tableCard, shareButton,
          findingBlock, evidenceHealthStrip } from '/js/components.js';

const STATUS_LABEL = {
  overdue: 'Overdue', due: 'Due', current: 'Current', unknown: 'Unknown',
};

function readQuery(params) {
  const q = params || new URLSearchParams(location.hash.split('?')[1] || '');
  return { status: q.get('status') || '' };
}
function setQuery(patch) {
  const q = new URLSearchParams(location.hash.split('?')[1] || '');
  for (const [k, v] of Object.entries(patch)) { if (v) q.set(k, v); else q.delete(k); }
  const s = q.toString();
  location.hash = `#/calendar${s ? `?${s}` : ''}`;
}

/* The stated side: the publisher's own words, with the transcribed period in
 * days when the registry asserts one. */
function statedText(d) {
  if (d.stated_cadence_days) return `${d.stated_cadence} · ~${num(d.stated_cadence_days)} d`;
  return d.stated_cadence || 'not stated';
}

/* The observed side: always flagged an estimate, always carrying its sample
 * size, and blank rather than guessed below three dated retrievals. */
function observedText(d) {
  if (!d.observed_interval_days) {
    return d.observed_sample
      ? `too few dated retrievals (n=${num(d.observed_sample)})`
      : 'none';
  }
  return `~${num(d.observed_interval_days)} d est. · n=${num(d.observed_sample)}`;
}

function statusText(d) {
  if (d.status === 'overdue' && d.overdue_by_days != null) {
    return `Overdue · +${num(d.overdue_by_days)} d`;
  }
  return STATUS_LABEL[d.status] || d.status;
}

export async function render(main, { params = null } = {}) {
  const current = readQuery(params);
  let data;
  try {
    data = await fetchJSON('publication_calendar');
  } catch (error) {
    replace(main, el('div', { class: 'section' }, errorCard(error, () => render(main, { params }))));
    return () => {};
  }

  const all = data.datasets || [];
  const shown = current.status ? all.filter((d) => d.status === current.status) : all;
  const byStatus = data.counts?.by_status || {};
  const byBasis = data.counts?.by_basis || {};
  const latest = all.map((d) => d.last_publication).filter(Boolean).sort().pop() || null;

  const chip = (key, label, count, active) => el('button', {
    type: 'button', class: `filter-chip${active ? ' is-active' : ''}`,
    'aria-pressed': String(active), onclick: () => setQuery({ status: key }),
  }, `${label} · ${num(count || 0)}`);

  const rows = shown.map((d) => ({
    _status: d.status,
    source: d.title,
    publisher: d.publisher,
    stated: statedText(d),
    observed: observedText(d),
    last: d.last_publication ? isoDate(d.last_publication) : 'never retrieved',
    next: d.next_expected ? isoDate(d.next_expected) : '—',
    status: statusText(d),
  }));

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Publication calendar' }),
      el('p', { class: 'lede', text:
        'How often each source releases, when it last did, and when the next '
        + 'release is due. The cadence a publisher states and the interval this '
        + 'warehouse has observed are shown separately — the observed figure is '
        + 'an estimate and the two are never combined.' }),
      el('div', { class: 'hero-actions' },
        shareButton({ title: 'SectorTrace — publication calendar',
          text: 'A SectorTrace view of each source’s release cadence and overdue status.',
          label: 'Share this view' }))),
    evidenceHealthStrip({
      scope: 'Every dataset in the portal catalogue, evaluated as of '
        + `${isoDate(data.as_of)}.`,
      retrievedAt: latest,
      verification: 'n/a',
      coverage: 'complete',
      limitation: 'A next-expected date is projected from the last retrieval '
        + 'held here, not from a publisher schedule.',
    }),
    findingBlock({
      finding: 'The stated cadence is the publisher’s. The observed interval '
        + 'is measured from retrieval history and labelled an estimate. They are '
        + 'kept in separate columns and never merged.',
      value: `${num(all.length)} sources · ${num(byBasis.stated || 0)} stated, `
        + `${num(byBasis.observed || 0)} observed, ${num(byBasis.unknown || 0)} unknown`,
      evidenceStatus: 'Derived',
      caveat: data.caveat,
    }),
    el('div', { class: 'panel' },
      pinnedCaveat(data.note, 'How this calendar is built'),
      el('h3', { text: 'Filter by status' }),
      el('div', { class: 'sl-chiprow' },
        chip('', 'All', all.length, !current.status),
        ...(data.statuses || []).map((s) =>
          chip(s, STATUS_LABEL[s] || s, byStatus[s], current.status === s))),
      rows.length
        ? tableCard('Sources by release cadence', [
            { title: 'Source', field: 'source', priority: 0 },
            { title: 'Publisher', field: 'publisher', priority: 3 },
            { title: 'Stated cadence', field: 'stated', priority: 2 },
            { title: 'Observed interval', field: 'observed', priority: 2 },
            { title: 'Last retrieval', field: 'last', priority: 1 },
            { title: 'Next expected', field: 'next', priority: 1 },
            { title: 'Status', field: 'status', priority: 0 },
          ], rows, {
            height: 640, total: rows.length,
            rowClass: (r) => `cal-row-${r._status}`,
          })
        : noData('sources with this status')));
  replace(main, page);
  return () => {};
}
