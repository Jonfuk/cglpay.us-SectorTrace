/* Operator view for the provider research candidate and promotion layers. */
import { el } from './dom.js';

const $ = (id) => document.getElementById(id);

async function api(path, options) {
  const response = await fetch(path, options);
  let payload = null;
  try { payload = await response.json(); } catch (e) { /* non-JSON */ }
  if (!response.ok) throw new Error((payload && payload.error) || response.statusText);
  return payload;
}

function reviewer() {
  return ($('reviewer')?.value || '').trim();
}

function text(value) {
  return value === null || value === undefined || value === '' ? '—' : String(value);
}

function status(value) {
  return value === 'verified' ? 'verified evidence' : value === 'candidate' ? 'candidate' : 'not researched';
}

function renderCoverage(data) {
  const cells = data.matrix.flatMap((provider) => provider.cells);
  const verified = cells.filter((cell) => cell.status === 'verified').length;
  const candidates = cells.filter((cell) => cell.status === 'candidate').length;
  const missing = cells.filter((cell) => cell.status === 'not_researched').length;
  $('provider-research-coverage').replaceChildren(
    el('div', { class: 'card' }, el('div', { class: 'n', text: String(verified) }), el('div', { class: 'label', text: 'verified cells' })),
    el('div', { class: 'card' }, el('div', { class: 'n', text: String(candidates) }), el('div', { class: 'label', text: 'candidate cells' })),
    el('div', { class: 'card' }, el('div', { class: 'n', text: String(missing) }), el('div', { class: 'label', text: 'not researched cells' })),
    el('div', { class: 'card' }, el('div', { class: 'n', text: String(data.worklist.length) }), el('div', { class: 'label', text: 'worklist items' })));

  const table = el('table', { class: 'data-table' },
    el('thead', {}, el('tr', {}, el('th', { text: 'Provider' }), ...data.categories.map((category) => el('th', { text: category })))),
    el('tbody', {}, data.matrix.map((provider) => el('tr', {},
      el('th', { scope: 'row', text: provider.canonical_name }),
      ...provider.cells.map((cell) => el('td', { title: `${cell.items} item(s)` }, status(cell.status)))))));
  $('provider-research-matrix').replaceChildren(
    el('div', { class: 'panel' }, el('h2', { text: '13-provider coverage matrix' }), table));
}

function renderItems(items) {
  const rows = items.map((item) => {
    const promoteable = item.state === 'approved' && item.evidence_status !== 'no_evidence';
    const action = promoteable ? el('button', {
      class: 'btn', type: 'button', text: 'Promote',
      onclick: async () => {
        const name = reviewer();
        if (!name) return setStatus('Enter a reviewer name before promoting.', true);
        try {
          await api('/api/admin/provider-research/promote', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item_id: item.id, promoted_by: name }),
          });
          setStatus(`Promoted research item ${item.id}.`);
          await refresh();
        } catch (error) { setStatus(error.message, true); }
      },
    }) : null;
    return el('article', { class: 'panel' },
      el('div', { class: 'eyebrow', text: `${text(item.category)} · ${text(item.fact_type)}` }),
      el('h3', { text: text(item.question) }),
      el('p', { text: text(item.raw_finding || item.interpretation) }),
      el('p', { class: 'muted small', text: `Provider: ${item.provider_key} · status: ${item.state} · identity: ${item.identity_review_state} · evidence: ${item.evidence_review_state}` }),
      el('p', { class: 'small', text: `Destination: ${text(item.destination)} · source: ${text(item.source_url)}` }),
      action);
  });
  $('provider-research-items').replaceChildren(
    el('div', { class: 'panel' }, el('h2', { text: 'Ranked research worklist' }),
      rows.length ? rows : el('p', { class: 'muted', text: 'No research items have been ingested.' })));
}

function setStatus(message, bad = false) {
  const node = $('provider-research-status');
  node.textContent = message || '';
  node.className = bad ? 'small bad' : 'muted small';
}

async function refresh() {
  try {
    const [coverage, items] = await Promise.all([
      api('/api/admin/provider-research/coverage'),
      api('/api/admin/provider-research/items?limit=100'),
    ]);
    renderCoverage(coverage);
    renderItems(items.items || []);
    const pill = $('provider-research-pill');
    const pending = (items.items || []).filter((item) => item.state === 'candidate').length;
    pill.textContent = String(pending);
    pill.hidden = pending === 0;
  } catch (error) { setStatus(error.message, true); }
}

export function initProviderResearch() {
  document.addEventListener('tabshown', (event) => {
    if (event.detail.tab === 'provider-research') refresh();
  });
}
