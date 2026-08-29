/* "What changed?" — a derived chronology of what the warehouse recorded
 * changing (BETA-090). Each event is one kind: release, refreshed, reparsed,
 * superseded or verified. A collection change, a parser change and a
 * human-review change are distinct kinds and their counts are never added.
 * This shows what THIS warehouse recorded changing, not what a source
 * published.
 */
'use strict';

import { el, replace, fetchJSON, num, isoDate } from '/app.js';
import { section, pinnedCaveat, noData, errorCard, tableCard, shareButton,
          findingBlock } from '/js/components.js';

const KIND_LABEL = {
  release: 'Release', refreshed: 'Refreshed', reparsed: 'Reparsed',
  superseded: 'Superseded', verified: 'Verified',
};

function readQuery(params) {
  const q = params || new URLSearchParams(location.hash.split('?')[1] || '');
  return { kind: q.get('kind') || '', source: q.get('source') || '' };
}
function setQuery(patch) {
  const q = new URLSearchParams(location.hash.split('?')[1] || '');
  for (const [k, v] of Object.entries(patch)) { if (v) q.set(k, v); else q.delete(k); }
  const s = q.toString();
  location.hash = `#/changes${s ? `?${s}` : ''}`;
}

export async function render(main, { params = null } = {}) {
  const current = readQuery(params);
  let data;
  try {
    data = await fetchJSON('changes', { kind: current.kind || undefined });
  } catch (error) {
    replace(main, el('div', { class: 'section' }, errorCard(error, () => render(main, { params }))));
    return () => {};
  }

  const events = current.source
    ? (data.events || []).filter((e) => e.source === current.source)
    : (data.events || []);
  const byKind = data.counts?.by_kind || {};
  const sources = [...new Set((data.events || []).map((e) => e.source).filter(Boolean))].sort();

  const chip = (key, label, count, active, patch) => el('button', {
    type: 'button', class: `filter-chip${active ? ' is-active' : ''}`,
    'aria-pressed': String(active), onclick: () => setQuery(patch),
  }, `${label} · ${num(count || 0)}`);

  const rows = events.map((e) => ({
    at: e.at ? isoDate(e.at) : 'undated',
    kind: KIND_LABEL[e.kind] || e.kind,
    source: e.source || '—',
    evidence_type: e.evidence_type || '—',
    detail: e.detail || '',
  }));

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'What changed?' }),
      el('p', { class: 'lede', text:
        'A chronology of what this warehouse recorded changing between '
        + 'collections and decisions — added or refreshed data, reparsed '
        + 'documents, verified provider lineage. It is not a record of what a '
        + 'source published.' }),
      el('div', { class: 'hero-actions' },
        shareButton({ title: 'SectorTrace — what changed',
          text: 'A SectorTrace chronology of recorded evidence changes.',
          label: 'Share this view' }))),
    findingBlock({
      finding: 'A collection change, a parser change and a human-review change '
        + 'are distinct kinds. Their counts are shown separately and are never '
        + 'added together.',
      value: `${num(events.length)} events`,
      evidenceStatus: 'Derived',
      caveat: data.caveat,
    }),
    el('div', { class: 'panel' },
      pinnedCaveat(data.note, 'How this feed is built'),
      el('h3', { text: 'Filter by kind' }),
      el('div', { class: 'sl-chiprow' },
        chip('', 'All kinds', Object.values(byKind).reduce((a, b) => a + b, 0), !current.kind, { kind: '' }),
        ...(data.kinds || []).map((k) =>
          chip(k, KIND_LABEL[k] || k, byKind[k], current.kind === k, { kind: k }))),
      sources.length > 1
        ? el('div', {},
            el('h3', { text: 'Filter by source' }),
            el('div', { class: 'sl-chiprow' },
              chip('', 'All sources', events.length, !current.source, { source: '' }),
              ...sources.map((s) => chip(s, s, (data.events || []).filter((e) => e.source === s).length,
                current.source === s, { source: s }))))
        : null,
      rows.length
        ? tableCard('Recorded changes', [
            { title: 'Date', field: 'at', priority: 0 },
            { title: 'Kind', field: 'kind', priority: 1 },
            { title: 'Source', field: 'source', priority: 2 },
            { title: 'Evidence type', field: 'evidence_type', priority: 3 },
            { title: 'What', field: 'detail', priority: 1 },
          ], rows, { height: 560, total: rows.length })
        : noData('recorded changes for this filter'),
      data.truncated
        ? el('p', { class: 'small muted', text: 'Capped; narrow the filters for the rest.' })
        : null));
  replace(main, page);
  return () => {};
}
