/* Temporal coverage navigator (BETA-097).
 *
 * For one selected provider or authority, exactly which periods each source
 * holds — so a gap is visible before a section is opened. Nothing is
 * gap-filled: a year cell is filled only where the source actually holds
 * that period, and an empty cell reads "not collected", never zero.
 *
 * State is the query: `#/timeline?provider=cgl` or `#/timeline?authority=E09000007`.
 */
'use strict';

import { el, replace, fetchJSON } from '/app.js';
import { section, pinnedCaveat, noData, errorCard, findingBlock } from '/js/components.js';

function readQuery(params) {
  const q = params || new URLSearchParams(location.hash.split('?')[1] || '');
  if (q.get('authority')) return { kind: 'authority', id: q.get('authority') };
  return { kind: 'provider', id: q.get('provider') || '' };
}

function setQuery(kind, id) {
  if (!id) { location.hash = '#/timeline'; return; }
  location.hash = `#/timeline?${kind === 'authority' ? 'authority' : 'provider'}=${encodeURIComponent(id)}`;
}

function picker(cur) {
  const draft = { ...cur };
  const kindSel = el('select', { onchange: (e) => { draft.kind = e.target.value; } },
    el('option', { value: 'provider', text: 'provider', selected: cur.kind === 'provider' }),
    el('option', { value: 'authority', text: 'authority', selected: cur.kind === 'authority' }));
  const idInput = el('input', { value: cur.id, placeholder: cur.kind === 'authority' ? 'ONS code' : 'provider_key',
    'aria-label': 'entity id', onchange: (e) => { draft.id = e.target.value.trim(); } });
  return el('div', { class: 'tl-picker' }, kindSel, idInput,
    el('button', { class: 'btn primary', type: 'button',
      onclick: () => setQuery(draft.kind, draft.id) }, 'Show coverage'));
}

function yearGridRow(source, years) {
  const held = new Set(source.periods.map((p) => (String(p).match(/(?:19|20)\d{2}/) || [])[0]).filter(Boolean));
  return el('div', { class: 'tl-row' },
    el('a', { class: 'tl-source', href: source.link, text: source.title }),
    el('div', { class: 'tl-cells' },
      ...years.map((y) => {
        const on = held.has(String(y));
        return on
          ? el('a', { class: 'tl-cell tl-held', href: source.link, title: `${source.title} · ${y}`, text: String(y).slice(2) })
          : el('span', { class: 'tl-cell tl-gap', title: `${source.title} · ${y}: not collected`, 'aria-label': `${y} not collected`, text: '·' });
      })));
}

function periodChipsRow(source) {
  return el('div', { class: 'tl-row' },
    el('a', { class: 'tl-source', href: source.link, text: source.title }),
    source.periods.length
      ? el('div', { class: 'tl-chips' },
          ...source.periods.map((p) => el('a', { class: 'tl-chip', href: source.link, text: String(p) })))
      : el('span', { class: 'tl-none small muted', text: 'nothing held for this entity' }));
}

export async function render(main, { params = null } = {}) {
  const cur = readQuery(params);

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Coverage timeline' }),
      el('p', { class: 'lede', text:
        'Which periods each source actually holds for one provider or '
        + 'authority. A gap here is a real gap — nothing is filled in — so a '
        + 'blank cell means "not collected", never a published zero.' })),
    el('div', { class: 'panel' }, picker(cur)));

  if (!cur.id) {
    page.append(el('div', { class: 'panel' },
      pinnedCaveat('Give a provider_key or an authority ONS code.', 'How to use this')));
    replace(main, page);
    return () => {};
  }

  let data;
  try {
    data = await fetchJSON('coverage_timeline',
      cur.kind === 'authority' ? { ons_code: cur.id } : { provider_key: cur.id });
  } catch (error) {
    page.append(el('div', { class: 'section' }, errorCard(error, () => render(main, { params }))));
    replace(main, page);
    return () => {};
  }

  const yearSources = data.sources.filter((s) => /year/.test(s.period_kind));
  const periodSources = data.sources.filter((s) => !/year/.test(s.period_kind));

  page.append(...[
    findingBlock({
      finding: 'Each row is the periods this warehouse holds for '
        + `${data.entity.name} — never gap-filled. An empty cell is "not `
        + 'collected or not published", not a zero.',
      value: `${data.held_count} of ${data.sources.length} sources hold data`,
      evidenceStatus: 'Coverage as held',
      caveat: data.caveat,
      sources: [data.entity.kind === 'authority'
        ? `#/authorities/${data.entity.id}` : `#/providers/${data.entity.id}`],
    }),
    el('div', { class: 'panel' },
      section('By year', data.span
        ? `${data.span.min}–${data.span.max}. Filled = a period held (click to open); · = not collected.`
        : 'No dated data held for this entity from any year-based source.',
        ...(data.years.length
          ? [
              el('div', { class: 'tl-row tl-head' },
                el('span', { class: 'tl-source', text: '' }),
                el('div', { class: 'tl-cells' },
                  ...data.years.map((y) => el('span', { class: 'tl-cell tl-year', text: String(y).slice(2) })))),
              ...yearSources.map((s) => yearGridRow(s, data.years)),
            ]
          : [noData('any dated coverage for this entity')]))),
    periodSources.length
      ? el('div', { class: 'panel' },
          section('Other periods', 'Sources whose periods are not plain years.',
            ...periodSources.map(periodChipsRow)))
      : null,
    el('div', { class: 'panel' }, pinnedCaveat(data.note, 'Read this with the grid')),
  ].filter(Boolean));

  replace(main, page);
  return () => {};
}
