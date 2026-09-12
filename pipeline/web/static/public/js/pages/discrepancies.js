/* Evidence discrepancy explorer (BETA-096).
 *
 * Where two or more public sources report a different value for the same
 * verified entity and field, both are shown side by side with their source
 * and date. Nothing is reconciled, ranked, or called an error — a
 * disagreement between sources is evidence context, not a mistake to fix.
 *
 * State is the query: `#/discrepancies?provider=cgl` or `?authority=E09000007`.
 */
'use strict';

import { el, replace, fetchJSON, isoDate, sourceLink } from '/app.js';
import { section, pinnedCaveat, noData, errorCard, findingBlock } from '/js/components.js';

function readQuery(params) {
  const q = params || new URLSearchParams(location.hash.split('?')[1] || '');
  if (q.get('authority')) return { kind: 'authority', id: q.get('authority') };
  return { kind: 'provider', id: q.get('provider') || '' };
}

function setQuery(kind, id) {
  if (!id) { location.hash = '#/discrepancies'; return; }
  location.hash = `#/discrepancies?${kind === 'authority' ? 'authority' : 'provider'}=${encodeURIComponent(id)}`;
}

function picker(cur) {
  const draft = { ...cur };
  const kindSel = el('select', { onchange: (e) => { draft.kind = e.target.value; } },
    el('option', { value: 'provider', text: 'provider', selected: cur.kind === 'provider' }),
    el('option', { value: 'authority', text: 'authority', selected: cur.kind === 'authority' }));
  const idInput = el('input', { value: cur.id, class: 'dx-input',
    placeholder: cur.kind === 'authority' ? 'ONS code' : 'provider_key',
    'aria-label': 'entity id', onchange: (e) => { draft.id = e.target.value.trim(); } });
  return el('div', { class: 'dx-picker' }, kindSel, idInput,
    el('button', { class: 'btn primary', type: 'button',
      onclick: () => setQuery(draft.kind, draft.id) }, 'Check sources'));
}

function discrepancyCard(d) {
  return el('div', { class: 'dx-card' },
    el('h3', { text: d.label }),
    el('table', { class: 'dx-table' },
      el('thead', {}, el('tr', {},
        el('th', { text: 'Source' }), el('th', { text: 'Value' }),
        el('th', { text: 'As of' }), el('th', { text: '' }))),
      el('tbody', {},
        ...d.observations.map((o) => el('tr', {},
          el('td', { class: 'small', text: o.source }),
          el('td', {}, el('code', { text: o.value })),
          el('td', { class: 'small muted', text: o.as_of ? isoDate(o.as_of) : '—' }),
          el('td', {}, o.source_url ? sourceLink(o.source_url, 'source ↗') : el('span', { text: '' })))))));
}

export async function render(main, { params = null } = {}) {
  const cur = readQuery(params);

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Evidence discrepancies' }),
      el('p', { class: 'lede', text:
        'Fields that public sources report differently for the same entity. '
        + 'Both values are shown; neither is corrected. A difference may be a '
        + 'spelling, a legal form, or a genuine disagreement — this view does '
        + 'not judge.' })),
    el('div', { class: 'panel' }, picker(cur)));

  if (!cur.id) {
    page.append(el('div', { class: 'panel' },
      pinnedCaveat('Give a provider_key or an authority ONS code.', 'How to use this')));
    replace(main, page);
    return () => {};
  }

  let data;
  try {
    data = await fetchJSON('discrepancies',
      cur.kind === 'authority' ? { ons_code: cur.id } : { provider_key: cur.id });
  } catch (error) {
    page.append(el('div', { class: 'section' }, errorCard(error, () => render(main, { params }))));
    replace(main, page);
    return () => {};
  }

  page.append(...[
    findingBlock({
      finding: 'Every card is a field two or more sources report differently '
        + `for ${data.entity.name}. Nothing here is reconciled and a difference `
        + 'is never called an error.',
      value: `${data.discrepancies.length} of ${data.checked} checked field${data.checked === 1 ? '' : 's'} disagree`,
      evidenceStatus: 'Sources as reported',
      caveat: data.caveat,
      sources: ['the source tables directly'],
    }),
    el('div', { class: 'panel' },
      pinnedCaveat(data.note, 'Read this with the cards'),
      ...(data.discrepancies.length
        ? data.discrepancies.map(discrepancyCard)
        : [noData('a field these sources disagree on')])),
    data.agreed.length
      ? el('div', { class: 'panel' },
          section('Fields the sources agree on', null,
            el('ul', { class: 'dx-agreed' },
              ...data.agreed.map((a) => el('li', {},
                el('strong', { text: `${a.label}: ` }),
                a.value ? el('code', { text: a.value }) : el('span', { class: 'muted', text: 'no source reports it' }),
                a.sources.length ? el('span', { class: 'small muted', text: ` (${a.sources.join(', ')})` }) : null)))))
      : null,
  ].filter(Boolean));

  replace(main, page);
  return () => {};
}
