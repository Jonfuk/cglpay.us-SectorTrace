/* Contract diary and milestone calendar (BETA-098).
 *
 * Procurement lifecycle records as a dated agenda — notice published, award,
 * contract period start/end. Every date is transcribed from the notice; an
 * "ends" event is the period as published, never a prediction of renewal or
 * completion.
 *
 * State is the query: `#/diary?provider=cgl` / `?buyer=E08000025` / `?ocid=...` / `&year=2025`.
 */
'use strict';

import { el, replace, fetchJSON, gbp } from '/app.js';
import { section, pinnedCaveat, noData, errorCard, findingBlock } from '/js/components.js';

const KIND_CLASS = {
  published: 'dy-published', award: 'dy-award',
  period_start: 'dy-start', period_end: 'dy-end',
};

function readQuery(params) {
  const q = params || new URLSearchParams(location.hash.split('?')[1] || '');
  return {
    provider: q.get('provider') || '', buyer: q.get('buyer') || '',
    ocid: q.get('ocid') || '', year: q.get('year') || '',
  };
}

function apiParams(cur) {
  const p = {};
  if (cur.provider) p.provider_key = cur.provider;
  if (cur.buyer) p.buyer_ons_code = cur.buyer;
  if (cur.ocid) p.ocid = cur.ocid;
  if (cur.year) p.year = cur.year;
  return p;
}

function monthName(ym) {
  const [y, m] = ym.split('-');
  return new Date(Number(y), Number(m) - 1, 1)
    .toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
}

function overview(months) {
  const max = Math.max(1, ...months.map((m) => m.count));
  return el('div', { class: 'dy-overview' },
    ...months.map((m) => el('a', {
      class: 'dy-bar', href: `#dy-${m.month}`, title: `${monthName(m.month)}: ${m.count}`,
    },
      el('span', { class: 'dy-bar-fill', style: `height:${Math.round((m.count / max) * 40) + 4}px` }),
      el('span', { class: 'dy-bar-label small muted', text: m.month.slice(2) }))));
}

function eventRow(e) {
  return el('div', { class: `dy-event ${KIND_CLASS[e.kind] || ''}` },
    el('span', { class: 'dy-date mono', text: e.date }),
    el('span', { class: 'dy-kind', text: e.kind_label }),
    el('a', { class: 'dy-title', href: `#/contracts?ocid=${encodeURIComponent(e.ocid || '')}`, text: e.title }),
    e.supplier ? el('span', { class: 'small muted', text: ` ${e.supplier}` }) : null,
    e.value_core != null ? el('span', { class: 'small', text: ` ${gbp(e.value_core)}` }) : null);
}

export async function render(main, { params = null } = {}) {
  const cur = readQuery(params);
  const scoped = cur.provider || cur.buyer || cur.ocid;

  const yInput = el('input', { value: cur.year, placeholder: 'year (optional)', class: 'dy-year',
    'aria-label': 'year' });
  const idInput = el('input', { value: cur.provider || cur.buyer || cur.ocid, class: 'dy-id',
    placeholder: 'provider_key, buyer ONS code, or ocid', 'aria-label': 'scope id' });
  const kindSel = el('select', {},
    el('option', { value: 'provider', text: 'provider', selected: !!cur.provider }),
    el('option', { value: 'buyer', text: 'buyer authority', selected: !!cur.buyer }),
    el('option', { value: 'ocid', text: 'OCDS process', selected: !!cur.ocid }));
  const go = () => {
    const q = new URLSearchParams();
    q.set(kindSel.value, idInput.value.trim());
    if (yInput.value.trim()) q.set('year', yInput.value.trim());
    location.hash = `#/diary?${q}`;
  };

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Contract diary' }),
      el('p', { class: 'lede', text:
        'Procurement lifecycle records as a dated agenda. Every date is '
        + 'transcribed from the notice — an “ends” date is the contract '
        + 'period as published, not a prediction that it will be renewed or '
        + 're-tendered.' })),
    el('div', { class: 'panel dy-controls' }, kindSel, idInput, yInput,
      el('button', { class: 'btn primary', type: 'button', onclick: go }, 'Build diary')));

  if (!scoped) {
    page.append(el('div', { class: 'panel' },
      pinnedCaveat('Scope the diary to a provider, a buyer authority, or a '
        + 'single OCDS process id.', 'How to use this')));
    replace(main, page);
    return () => {};
  }

  let data;
  try {
    data = await fetchJSON('contract_diary', apiParams(cur));
  } catch (error) {
    page.append(el('div', { class: 'section' }, errorCard(error, () => render(main, { params }))));
    replace(main, page);
    return () => {};
  }

  const byKind = data.counts.by_kind || {};
  const groups = new Map();
  for (const e of data.events) {
    const ym = e.date.slice(0, 7);
    if (!groups.has(ym)) groups.set(ym, []);
    groups.get(ym).push(e);
  }

  page.append(...[
    findingBlock({
      finding: 'Every event is a date the notice carries. Nothing here '
        + 'forecasts a renewal, a re-tender or a completion.',
      value: `${data.events.length} event${data.events.length === 1 ? '' : 's'} · `
        + data.kinds.filter((k) => byKind[k]).map((k) => `${byKind[k]} ${k}`).join(' · '),
      evidenceStatus: 'Dates as published',
      caveat: data.caveat,
      sources: ['the OCDS notices directly'],
    }),
    data.months.length ? el('div', { class: 'panel' },
      section('At a glance', 'Events per month.', overview(data.months))) : null,
    el('div', { class: 'panel' },
      pinnedCaveat(data.note, 'Read this with the diary'),
      ...(data.events.length
        ? [...groups.entries()].map(([ym, evs]) => el('div', { class: 'dy-month', id: `dy-${ym}` },
            el('h3', { text: monthName(ym) }),
            ...evs.map(eventRow)))
        : [noData('a dated procurement event for this scope')]),
      data.truncated ? el('p', { class: 'small muted', text: 'Capped — narrow the scope or add a year.' }) : null),
  ].filter(Boolean));

  replace(main, page);
  return () => {};
}
