/* Entity co-occurrence explorer (BETA-095).
 *
 * Documents and records in which two or more selected tracked entities are
 * named together, with the exact passage or structured field. Co-occurrence
 * is location — it locates source material — never a claim that the entities
 * are connected.
 *
 * State is the query: `#/cooccurrence?key=change_grow_live&key=turning_point`.
 */
'use strict';

import { el, replace, isoDate } from '/app.js';
import { section, pinnedCaveat, noData, errorCard, findingBlock } from '/js/components.js';

const TYPE_LABEL = {
  document: 'Document passages', coroner_report: 'Coroner reports',
  tribunal_case: 'Tribunal cases', procurement_notice: 'Procurement notices',
};

function readKeys(params) {
  const q = params || new URLSearchParams(location.hash.split('?')[1] || '');
  return q.getAll('key').filter(Boolean);
}

function setKeys(keys) {
  const q = new URLSearchParams();
  for (const k of keys) if (k) q.append('key', k);
  location.hash = `#/cooccurrence${q.toString() ? `?${q}` : ''}`;
}

function picker(keys) {
  const value = keys.join(', ');
  const input = el('input', { value, placeholder: 'two or more provider keys, comma-separated',
    'aria-label': 'entity keys', class: 'co-input' });
  return el('div', { class: 'co-picker' }, input,
    el('button', { class: 'btn primary', type: 'button',
      onclick: () => setKeys(input.value.split(',').map((s) => s.trim()).filter(Boolean)) },
      'Find co-occurrences'));
}

function resultRow(r) {
  const head = el('div', { class: 'co-result-head' },
    el('a', { class: 'co-title', href: r.link, text: r.title }),
    r.date ? el('span', { class: 'small muted', text: ` ${isoDate(r.date)}` }) : null,
    r.source_system ? el('span', { class: 'badge type', text: r.source_system }) : null);
  const body = r.text
    ? el('blockquote', { class: 'co-passage', text: r.text })
    : r.matched
      ? el('p', { class: 'small muted', text: Object.entries(r.matched)
          .map(([k, v]) => `${k}${v && v !== k ? ` ("${v}")` : ''}`).join(' · ') })
      : null;
  return el('div', { class: 'co-result' }, head, body,
    el('a', { class: 'linklike small', href: r.link, text: 'Open →' }));
}

export async function render(main, { params = null } = {}) {
  const keys = readKeys(params);

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Co-occurrence explorer' }),
      el('p', { class: 'lede', text:
        'Documents and records that name two or more selected entities in the '
        + 'same place. This locates source material — it is not a claim that '
        + 'the entities are connected.' })),
    el('div', { class: 'panel' }, picker(keys)));

  if (keys.length < 2) {
    page.append(el('div', { class: 'panel' },
      pinnedCaveat('Enter at least two provider/supplier keys (from a provider '
        + 'page URL), comma-separated.', 'How to use this')));
    replace(main, page);
    return () => {};
  }

  // `key` is a repeated parameter, which fetchJSON's object form cannot
  // express, so build the query directly.
  let data;
  try {
    const qs = keys.map((k) => `key=${encodeURIComponent(k)}`).join('&');
    const res = await fetch(`/api/v1/cooccurrence?${qs}`);
    data = await res.json();
    if (!res.ok) throw new Error(data.error || res.statusText);
  } catch (error) {
    page.append(el('div', { class: 'section' }, errorCard(error, () => render(main, { params }))));
    replace(main, page);
    return () => {};
  }

  const byType = data.counts.by_record_type || {};
  page.append(
    findingBlock({
      finding: 'Each row is one record naming every selected entity. '
        + 'Co-occurrence is location, not a relationship — two names in one '
        + 'passage may be a list, a comparison, or unrelated.',
      value: `${data.results.length} record${data.results.length === 1 ? '' : 's'} · `
        + data.entities.map((e) => e.name).join(' + '),
      evidenceStatus: 'Same-record co-occurrence',
      caveat: data.caveat,
      sources: ['verified name variants + confirmed mentions'],
    }),
    el('div', { class: 'panel' },
      pinnedCaveat(data.note, 'Read this with the results'),
      ...(data.results.length
        ? data.record_types.filter((t) => byType[t]).map((t) => section(
            `${TYPE_LABEL[t] || t} (${byType[t]})`, null,
            ...data.results.filter((r) => r.record_type === t).map(resultRow)))
        : [noData('a record naming all of those entities together')])));

  replace(main, page);
  return () => {};
}
