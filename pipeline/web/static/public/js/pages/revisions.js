/* Record revision comparison (BETA-092).
 *
 * Two revisions of one record, diffed. `kind=ocds` compares two procurement
 * notices field by field and labels each changed field: a `source` field is
 * verbatim from the OCDS release (a publisher amendment); a `derived` field
 * is a match or normalisation this pipeline recomputed (the notice itself may
 * be unchanged). `kind=document` compares two parsed versions of one
 * document, element-aligned and text-aware. Source and derived change counts
 * are shown apart and never added.
 *
 * State is the query: `#/revisions?kind=ocds&ocid=...` or `&a=&b=`,
 * `#/revisions?kind=document&document_id=...`.
 */
'use strict';

import { el, replace, fetchJSON, isoDate } from '/app.js';
import { section, pinnedCaveat, noData, errorCard, findingBlock } from '/js/components.js';

function readQuery(params) {
  const q = params || new URLSearchParams(location.hash.split('?')[1] || '');
  return {
    kind: q.get('kind') || 'ocds',
    a: q.get('a') || '', b: q.get('b') || '',
    ocid: q.get('ocid') || '', document_id: q.get('document_id') || '',
  };
}

function setQuery(patch) {
  const q = new URLSearchParams(location.hash.split('?')[1] || '');
  for (const [k, v] of Object.entries(patch)) { if (v) q.set(k, v); else q.delete(k); }
  location.hash = `#/revisions${q.toString() ? `?${q}` : ''}`;
}

function form(current) {
  const kind = el('select', { onchange: (e) => setQuery({ kind: e.target.value, a: '', b: '', ocid: '', document_id: '' }) },
    el('option', { value: 'ocds', text: 'Procurement notice', selected: current.kind === 'ocds' }),
    el('option', { value: 'document', text: 'Parsed document', selected: current.kind === 'document' }));
  const key = current.kind === 'ocds' ? 'ocid' : 'document_id';
  const idInput = el('input', { value: current[key], placeholder: current.kind === 'ocds' ? 'OCID' : 'document_id',
    'aria-label': key });
  return el('div', { class: 'rev-form' }, kind, idInput,
    el('button', { class: 'btn', type: 'button',
      onclick: () => setQuery({ [key]: idInput.value.trim(), a: '', b: '' }) }, 'Compare'));
}

function classPill(cls) {
  return el('span', { class: `rev-class rev-class-${cls}`, text: cls });
}

function renderOcds(data) {
  const changed = data.fields.filter((f) => f.changed);
  return el('div', {},
    el('div', { class: 'rev-head' },
      el('div', {}, el('strong', { text: 'A · ' }), el('code', { text: data.a.notice_id }),
        el('span', { class: 'small muted', text: ` retrieved ${isoDate(data.a.retrieved_at)}` })),
      el('div', {}, el('strong', { text: 'B · ' }), el('code', { text: data.b.notice_id }),
        el('span', { class: 'small muted', text: ` retrieved ${isoDate(data.b.retrieved_at)}` })),
      data.same_ocid
        ? el('span', { class: 'badge', text: `same OCID · ${data.a.ocid}` })
        : el('span', { class: 'badge unverified', text: 'different OCIDs — not the same procurement' })),
    findingBlock({
      finding: 'A change to a source field is an amendment the publisher made. '
        + 'A change to a derived field is a normalisation this pipeline '
        + 'recomputed between collections. The two counts are never added.',
      value: `${data.counts.changed_source} source field${data.counts.changed_source === 1 ? '' : 's'} amended · `
        + `${data.counts.changed_derived} derived field${data.counts.changed_derived === 1 ? '' : 's'} recomputed`,
      evidenceStatus: 'Field-aware diff',
      caveat: data.note,
      sources: [data.b.source_url].filter(Boolean),
      retrievedAt: data.b.retrieved_at,
    }),
    el('table', { class: 'rev-table' },
      el('thead', {}, el('tr', {},
        el('th', { text: 'Field' }), el('th', { text: 'Class' }),
        el('th', { text: 'A' }), el('th', { text: 'B' }))),
      el('tbody', {},
        ...data.fields.map((f) => el('tr', { class: f.changed ? 'rev-changed' : '' },
          el('td', { class: 'mono small', text: f.field }),
          el('td', {}, classPill(f.class)),
          el('td', { class: 'small', text: f.a == null ? '—' : String(f.a) }),
          el('td', { class: 'small', text: f.b == null ? '—' : String(f.b) }))))),
    changed.length ? null : el('p', { class: 'small muted', text: 'No field differs between these two notices.' }));
}

function renderDocument(data) {
  const metaChanged = data.meta.filter((m) => m.changed);
  return el('div', {},
    el('div', { class: 'rev-head' },
      el('h2', { text: data.title || data.document_id }),
      el('div', {}, el('strong', { text: 'A · ' }),
        el('span', { class: 'small', text: `${data.a.parser} · ${isoDate(data.a.created_at)}` })),
      el('div', {}, el('strong', { text: 'B · ' }),
        el('span', { class: 'small', text: `${data.b.parser} · ${isoDate(data.b.created_at)}` }))),
    findingBlock({
      finding: 'A metadata change (parser, schema, config hash) explains a '
        + 'text change that is not a source amendment: the bytes are the same, '
        + 'the parser read them differently.',
      value: `${data.counts.changed} changed · ${data.counts.added} added · ${data.counts.removed} removed elements`,
      evidenceStatus: 'Text-aware diff',
      caveat: data.note,
      retrievedAt: data.b.created_at,
    }),
    metaChanged.length
      ? el('table', { class: 'rev-table' },
          el('thead', {}, el('tr', {}, el('th', { text: 'Version field' }),
            el('th', { text: 'A' }), el('th', { text: 'B' }))),
          el('tbody', {}, ...metaChanged.map((m) => el('tr', { class: 'rev-changed' },
            el('td', { class: 'mono small', text: m.field }),
            el('td', { class: 'small', text: m.a == null ? '—' : String(m.a) }),
            el('td', { class: 'small', text: m.b == null ? '—' : String(m.b) })))))
      : el('p', { class: 'small muted', text: 'No version metadata differs.' }),
    data.text_changes.length
      ? el('ol', { class: 'rev-elements' },
          ...data.text_changes.map((t) => el('li', { class: `rev-el rev-el-${t.kind}` },
            el('div', { class: 'small muted', text: `#${t.sequence} · ${t.element_type} · ${t.kind}` }),
            t.a != null ? el('div', { class: 'rev-was' }, el('span', { class: 'rev-tag', text: 'A ' }), t.a) : null,
            t.b != null ? el('div', { class: 'rev-now' }, el('span', { class: 'rev-tag', text: 'B ' }), t.b) : null)))
      : el('p', { class: 'small muted', text: 'The body text is identical between these versions.' }),
    data.truncated ? el('p', { class: 'small muted', text: 'Long document — element list capped.' }) : null);
}

export async function render(main, { params = null } = {}) {
  const current = readQuery(params);
  const hasTarget = (current.a && current.b) || current.ocid || current.document_id;

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Compare revisions' }),
      el('p', { class: 'lede', text:
        'Two revisions of one record, diffed — so a source amendment is not '
        + 'confused with a parser or normalisation change this pipeline made '
        + 'between collections.' })),
    el('div', { class: 'panel' }, form(current)));

  if (!hasTarget) {
    page.append(el('div', { class: 'panel' },
      pinnedCaveat('Give an OCID (procurement) or a document_id, or two explicit '
        + 'revision ids as a and b in the URL.', 'How to use this')));
    replace(main, page);
    return () => {};
  }

  let data;
  try {
    data = await fetchJSON('record_diff', {
      kind: current.kind,
      a: current.a || undefined, b: current.b || undefined,
      ocid: current.ocid || undefined, document_id: current.document_id || undefined,
    });
  } catch (error) {
    page.append(el('div', { class: 'section' }, errorCard(error, () => render(main, { params }))));
    replace(main, page);
    return () => {};
  }

  page.append(el('div', { class: 'panel' },
    section('Difference', null,
      data.kind === 'ocds' ? renderOcds(data)
        : data.kind === 'document' ? renderDocument(data)
          : noData('a comparable revision'))));
  replace(main, page);
  return () => {};
}
