/* Relationship pathfinder (BETA-093).
 *
 * The shortest *verified* path between two entities through the source-backed
 * entity graph. A neighbourhood view (#/relationships) says what surrounds
 * one entity; this says how two known entities are connected, and shows the
 * source behind every hop. Unconfirmed name-match edges are never followed.
 *
 * State is the query: `#/pathfinder?from_type=provider&from_id=cgl&to_type=authority&to_id=E09000007`.
 */
'use strict';

import { el, replace, fetchJSON, isoDate, sourceLink } from '/app.js';
import { section, pinnedCaveat, noData, errorCard, findingBlock } from '/js/components.js';

const KINDS = ['provider', 'authority', 'supplier'];

function readQuery(params) {
  const q = params || new URLSearchParams(location.hash.split('?')[1] || '');
  return {
    from_type: q.get('from_type') || 'provider', from_id: q.get('from_id') || '',
    to_type: q.get('to_type') || 'authority', to_id: q.get('to_id') || '',
  };
}

function setQuery(next) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(next)) if (v) q.set(k, v);
  location.hash = `#/pathfinder${q.toString() ? `?${q}` : ''}`;
}

function endpointRow(label, kind, id, onKind, onId) {
  return el('div', { class: 'pf-endpoint' },
    el('span', { class: 'pf-label', text: label }),
    el('select', { onchange: (e) => onKind(e.target.value) },
      ...KINDS.map((k) => el('option', { value: k, text: k, selected: k === kind }))),
    el('input', { value: id, placeholder: kind === 'authority' ? 'ONS code' : 'provider_key',
      'aria-label': `${label} id`, onchange: (e) => onId(e.target.value.trim()) }));
}

function chain(nodes) {
  const parts = [];
  nodes.forEach((n, i) => {
    if (i) parts.push(el('span', { class: 'pf-arrow', text: '→' }));
    parts.push(el('span', { class: 'pf-node' },
      el('span', { class: 'pf-node-type', text: n.type }),
      el('span', { text: ` ${n.label || n.id}` })));
  });
  return el('div', { class: 'pf-chain' }, ...parts);
}

export async function render(main, { params = null } = {}) {
  const cur = readQuery(params);
  const draft = { ...cur };

  const controls = el('div', { class: 'panel pf-controls' },
    endpointRow('From', draft.from_type, draft.from_id,
      (v) => { draft.from_type = v; }, (v) => { draft.from_id = v; }),
    endpointRow('To', draft.to_type, draft.to_id,
      (v) => { draft.to_type = v; }, (v) => { draft.to_id = v; }),
    el('button', { class: 'btn primary', type: 'button',
      onclick: () => setQuery(draft) }, 'Find path'));

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Relationship pathfinder' }),
      el('p', { class: 'lede', text:
        'The shortest verified path between two entities through source-backed '
        + 'graph edges. An unconfirmed name match is not a path — it is not '
        + 'followed.' })),
    controls);

  if (!cur.from_id || !cur.to_id) {
    page.append(el('div', { class: 'panel' },
      pinnedCaveat('Pick two entities and their kinds, then "Find path". Ids are '
        + 'a provider_key (from a provider page) or an authority ONS code.',
        'How to use this')));
    replace(main, page);
    return () => {};
  }

  let data;
  try {
    data = await fetchJSON('relationship_path', {
      from_type: cur.from_type, from_id: cur.from_id,
      to_type: cur.to_type, to_id: cur.to_id,
    });
  } catch (error) {
    page.append(el('div', { class: 'section' }, errorCard(error, () => render(main, { params }))));
    replace(main, page);
    return () => {};
  }

  if (!data.found) {
    page.append(el('div', { class: 'panel' },
      noData('a verified path between these two entities'),
      el('p', { class: 'small muted', text: data.reason || '' }),
      pinnedCaveat(data.note, 'How this search works')));
    replace(main, page);
    return () => {};
  }

  const rows = data.path.map((hop) => el('tr', {},
    el('td', { class: 'mono small', text: hop.from }),
    el('td', { class: 'small', text: hop.relationship_label }),
    el('td', {}, el('span', { class: 'pf-basis', text: hop.basis || '—' })),
    el('td', { class: 'mono small', text: hop.to }),
    el('td', {}, hop.source_url ? sourceLink(hop.source_url, 'source ↗') : el('span', { text: '—' })),
    el('td', { class: 'small muted', text: isoDate(hop.retrieved_at) })));

  page.append(
    findingBlock({
      finding: 'Every hop is an edge whose basis passed a review gate — a '
        + 'confirmed identifier or a confirmed alias, never an unreviewed name '
        + 'match. The path is the shortest; ties break on (relationship, node id).',
      value: `${data.hops} hop${data.hops === 1 ? '' : 's'}`,
      evidenceStatus: 'Verified path',
      caveat: data.note,
      retrievedAt: data.path[data.path.length - 1]?.retrieved_at,
    }),
    el('div', { class: 'panel' },
      section('Path', null,
        chain(data.nodes),
        el('table', { class: 'pf-table' },
          el('thead', {}, el('tr', {},
            el('th', { text: 'From' }), el('th', { text: 'Relationship' }),
            el('th', { text: 'Basis' }), el('th', { text: 'To' }),
            el('th', { text: 'Source' }), el('th', { text: 'Retrieved' }))),
          el('tbody', {}, ...rows)))));

  replace(main, page);
  return () => {};
}
