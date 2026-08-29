/* Source-link resilience checker (BETA-100).
 *
 * Whether an original source URL was live, redirected or gone the last time
 * this pipeline fetched it, and whether a checksum-verified archive copy is
 * held. No live request is made — the state is read from collection-time
 * metadata. The archive is provenance, never presented as the current page.
 *
 * State is the query: `#/links?url=https://...`.
 */
'use strict';

import { el, replace, fetchJSON, isoDate, sourceLink, num } from '/app.js';
import { section, pinnedCaveat, errorCard, findingBlock } from '/js/components.js';

const STATE_CLASS = {
  live_at_last_check: 'ok', redirected_at_last_check: 'unverified',
  gone_at_last_check: 'bad', error_at_last_check: 'bad',
  not_recorded: 'muted', unknown_url: 'muted',
};

function readUrl(params) {
  const q = params || new URLSearchParams(location.hash.split('?')[1] || '');
  return q.get('url') || '';
}

function archiveLine(a) {
  if (!a || !a.held) {
    return el('p', { class: 'small muted', text: a && a.note
      ? a.note : 'No archive copy is held for this URL.' });
  }
  const verified = a.verified === true ? 'checksum verified'
    : a.verified === false ? 'checksum MISMATCH'
      : 'too large to re-hash on request';
  return el('p', { class: 'small' },
    el('strong', { text: 'Archive copy held' }),
    el('span', { text: ` — ${num(a.bytes)} bytes, ${verified}` }),
    a.sha256 ? el('code', { class: 'lk-sha', text: ` ${a.sha256.slice(0, 16)}…` }) : null);
}

function overviewBlock(o) {
  const total = Object.values(o.by_state).reduce((s, n) => s + n, 0) || 1;
  return el('div', {},
    el('p', { class: 'small muted', text: o.note }),
    el('ul', { class: 'lk-overview' },
      ...o.states.filter((s) => o.by_state[s]).map((s) => el('li', {},
        el('span', { class: `badge ${STATE_CLASS[s] || 'muted'}`, text: s.replace(/_/g, ' ') }),
        el('span', { class: 'small', text: ` ${num(o.by_state[s])} (${Math.round((o.by_state[s] / total) * 100)}%)` })))));
}

export async function render(main, { params = null } = {}) {
  const url = readUrl(params);
  const input = el('input', { value: url, class: 'lk-input', type: 'url',
    placeholder: 'https://…  (a source URL cited in the warehouse)', 'aria-label': 'source URL' });
  const go = () => {
    const v = input.value.trim();
    location.hash = v ? `#/links?url=${encodeURIComponent(v)}` : '#/links';
  };

  const page = el('div', {},
    el('div', { class: 'hero' },
      el('h1', { text: 'Source-link resilience' }),
      el('p', { class: 'lede', text:
        'Whether a source URL was reachable the last time this pipeline '
        + 'fetched it, and whether a checksum-verified archive copy is held. '
        + 'No live request is made — this reads collection-time metadata. The '
        + 'archive is provenance, not the current publisher page.' })),
    el('div', { class: 'panel lk-controls' }, input,
      el('button', { class: 'btn primary', type: 'button', onclick: go }, 'Check URL')));

  let overview;
  try { overview = await fetchJSON('source_link', {}); }
  catch (_) { overview = null; }

  if (url) {
    let data;
    try { data = await fetchJSON('source_link', { url }); }
    catch (error) {
      page.append(el('div', { class: 'section' }, errorCard(error, () => render(main, { params }))));
      replace(main, page);
      return () => {};
    }
    page.append(
      findingBlock({
        finding: 'State is as of the last fetch date; no request was made now. '
          + 'An archive copy is the bytes fetched then, kept with its SHA-256.',
        value: data.state.replace(/_/g, ' '),
        evidenceStatus: 'Collection-time metadata',
        caveat: data.caveat,
        retrievedAt: data.last_checked,
      }),
      el('div', { class: 'panel' },
        section('This URL', null,
          el('p', {}, sourceLink(data.url, data.url)),
          el('p', {},
            el('span', { class: `badge ${STATE_CLASS[data.state] || 'muted'}`, text: data.state.replace(/_/g, ' ') }),
            el('span', { class: 'small', text: ` ${data.state_label}` })),
          el('p', { class: 'small muted', text:
            `Last checked ${isoDate(data.last_checked)}`
            + (data.last_http_status != null ? ` · HTTP ${data.last_http_status}` : '')
            + (data.observed_in ? ` · seen in ${data.observed_in}` : '') }),
          archiveLine(data.archive),
          pinnedCaveat(data.note, 'How this was determined'))));
  }

  if (overview) {
    page.append(el('div', { class: 'panel' },
      section('Across the warehouse', 'Cited rows by the HTTP status recorded at their last fetch.',
        overviewBlock(overview))));
  }

  replace(main, page);
  return () => {};
}
