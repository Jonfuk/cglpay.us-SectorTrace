/* The Candidates tab: what three modules found, and what a person makes of it.
 *
 * The shape of this screen follows the shape of the decision it supports.
 * Promoting is one row at a time and opens the document first, because the act
 * being recorded is that somebody looked; there is no select-all, and the
 * server would refuse an array anyway. Rejecting is bulk, because deciding a
 * link is not what it looked like is something you can do from the list, and
 * being wrong leaves a candidate a candidate.
 *
 * The confidence and match-quality columns are shown but never sorted on by
 * default. `match_quality` is ModernGov's own textual ranking and `confidence`
 * counts matching signals; ordering a worklist by either would quietly turn a
 * triage aid into a recommendation.
 */
import { el } from './dom.js';

const $ = (id) => document.getElementById(id);

const state = {
  kind: 'cdp_document',
  status: 'undecided',
  authority: '',
  search: '',
  offset: 0,
  items: [],
  selected: new Set(),
  busy: false,
};

const KIND_LABELS = {
  cdp_document: 'CDP documents',
  committee_paper: 'Committee papers',
  foi_request: 'FOI requests',
};

async function api(path, options) {
  const response = await fetch(path, options);
  let payload = null;
  try { payload = await response.json(); } catch (e) { /* not JSON */ }
  if (!response.ok) {
    const error = new Error((payload && payload.error) || response.statusText);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function status(text, kind) {
  const node = $('candidate-status');
  if (!node) return;
  node.textContent = text || '';
  node.className = kind === 'bad' ? 'small bad' : (kind === 'good' ? 'small good' : 'muted small');
}

function reviewerName() {
  const field = document.getElementById('reviewer');
  return field ? field.value.trim() : '';
}

// --- the counts strip ---------------------------------------------------------

async function loadCounts() {
  let data;
  try { data = await api('/api/admin/candidates/counts'); }
  catch (e) { return status(e.message, 'bad'); }

  const strip = $('candidate-counts');
  strip.replaceChildren(...Object.entries(data.kinds).map(([kind, counts]) =>
    el('button', {
      class: kind === state.kind ? 'chip active' : 'chip',
      onclick: () => { state.kind = kind; state.offset = 0; state.authority = ''; refresh(); },
    },
      el('strong', { text: KIND_LABELS[kind] || kind }),
      el('span', { class: 'muted small', text: ` ${counts.undecided} undecided` }),
      el('span', { class: 'muted small', text: ` · ${counts.evidence_rows} promoted` }),
    )));

  const history = $('promotion-history');
  if (!data.promotions.length) {
    history.replaceChildren(el('p', {
      class: 'muted small',
      text: 'Nothing promoted yet. Every promotion is recorded here with who made it.',
    }));
    return;
  }
  history.replaceChildren(el('table', {},
    el('thead', {}, el('tr', {},
      el('th', { text: 'When' }), el('th', { text: 'Who' }),
      el('th', { text: 'Document' }), el('th', { text: 'Note' }))),
    el('tbody', {}, ...data.promotions.map((row) => el('tr', {},
      el('td', { class: 'small', text: row.promoted_at }),
      el('td', { class: 'small', text: row.promoted_by }),
      el('td', { class: 'small mono', text: row.candidate_url }),
      el('td', { class: 'small muted', text: row.note || '' }))))));
}

// --- the list -----------------------------------------------------------------

async function loadAuthorities() {
  const select = $('candidate-authority');
  let data;
  try { data = await api(`/api/admin/candidates/authorities?kind=${encodeURIComponent(state.kind)}`); }
  catch (e) { return; }

  select.replaceChildren(
    el('option', { value: '', text: 'All authorities' }),
    ...data.authorities.map((a) => el('option', {
      value: a.ons_code,
      text: `${a.name || a.ons_code} (${a.candidates})`,
    })));
  select.value = state.authority;
}

async function loadList() {
  const params = new URLSearchParams({
    kind: state.kind, status: state.status, offset: String(state.offset),
  });
  if (state.authority) params.set('authority', state.authority);
  if (state.search) params.set('q', state.search);

  let data;
  try { data = await api(`/api/admin/candidates?${params}`); }
  catch (e) { return status(e.message, 'bad'); }

  state.items = data.items;
  state.selected.clear();
  render(data);
}

function render(data) {
  const list = $('candidate-list');
  if (!data.items.length) {
    list.replaceChildren(el('p', { class: 'muted', text: 'Nothing here.' }));
    $('candidate-pager').replaceChildren();
    return;
  }

  list.replaceChildren(...data.items.map((item) => renderItem(item, data.requires)));

  const shown = data.offset + data.items.length;
  $('candidate-pager').replaceChildren(
    el('span', { class: 'muted small', text: `${data.offset + 1}–${shown} of ${data.total}` }),
    el('button', {
      class: 'btn', disabled: data.offset === 0,
      onclick: () => { state.offset = Math.max(0, state.offset - data.limit); loadList(); },
      text: 'Previous',
    }),
    el('button', {
      class: 'btn', disabled: shown >= data.total,
      onclick: () => { state.offset = state.offset + data.limit; loadList(); },
      text: 'Next',
    }));
}

function renderItem(item, requires) {
  const summary = Object.entries(item.summary)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => el('span', { class: 'muted small' }, `${key.replace(/_/g, ' ')}: ${value}`));

  const check = el('input', {
    type: 'checkbox',
    onchange: (event) => {
      if (event.target.checked) state.selected.add(item.url);
      else state.selected.delete(item.url);
      updateBulk();
    },
  });

  const decided = item.verified ? 'promoted' : (item.rejected ? 'rejected' : null);

  return el('div', { class: 'candidate' },
    el('div', { class: 'row' },
      check,
      el('strong', { text: item.summary.title || item.summary.report_title || '(untitled)' }),
      el('span', { class: 'spacer' }),
      decided ? el('span', { class: 'pill', text: decided }) : null,
      el('span', { class: 'muted small', text: item.authority_name || item.authority_ons_code || '' }),
    ),
    el('div', { class: 'row wrap' }, ...summary),
    el('div', { class: 'row' },
      // The document itself, opened in a new tab. Promoting without having
      // read it is the failure this whole screen is arranged against.
      el('a', { href: item.url, target: '_blank', rel: 'noopener noreferrer',
                 class: 'small mono', text: item.url }),
    ),
    el('div', { class: 'row' },
      el('span', { class: 'muted small',
                    text: `found on ${item.discovered.source_url || 'unknown'}` }),
    ),
    decided === 'promoted'
      ? el('div', { class: 'row' }, el('button', {
          class: 'btn', text: 'Reset',
          onclick: () => resetOne(item.url),
        }))
      : promoteControls(item, requires));
}

function promoteControls(item, requires) {
  const inputs = {};
  const fields = requires.map((name) => {
    const input = el('input', {
      type: 'text',
      placeholder: name === 'document_type' ? 'confirmed type, e.g. strategy' : name,
      value: name === 'document_type' ? (item.summary.document_type_guess || '') : '',
    });
    inputs[name] = input;
    return el('label', { class: 'small' }, `${name.replace(/_/g, ' ')} `, input);
  });

  const note = el('input', { type: 'text', placeholder: 'note (optional)' });

  return el('div', { class: 'row wrap' },
    ...fields,
    note,
    el('button', {
      class: 'btn primary', text: 'Promote',
      onclick: (event) => promoteOne(item, inputs, note.value, event.target),
    }),
    el('button', {
      class: 'btn', text: 'Reject',
      onclick: () => rejectMany([item.url]),
    }));
}

function updateBulk() {
  const button = $('candidate-reject-selected');
  button.disabled = state.selected.size === 0;
  button.textContent = state.selected.size
    ? `Reject ${state.selected.size} selected` : 'Reject selected';
}

// --- deciding -----------------------------------------------------------------

async function promoteOne(item, inputs, note, button) {
  const who = reviewerName();
  if (!who) {
    status('Put your name in the reviewer box first — promotions are attributed.', 'bad');
    return;
  }

  const fields = {};
  for (const [name, input] of Object.entries(inputs)) fields[name] = input.value;

  button.disabled = true;
  status(`fetching ${item.url}…`);
  try {
    const result = await api('/api/admin/candidates/promote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind: state.kind, url: item.url, promoted_by: who,
                              fields, note: note || null }),
    });
    status(`promoted — ${result.payload_sha256.slice(0, 12)}… archived`, 'good');
  } catch (e) {
    button.disabled = false;
    return status(e.message, 'bad');
  }
  await Promise.all([loadCounts(), loadList()]);
}

async function rejectMany(urls) {
  const who = reviewerName();
  if (!who) {
    status('Put your name in the reviewer box first — rejections are attributed.', 'bad');
    return;
  }
  try {
    const result = await api('/api/admin/candidates/reject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind: state.kind, urls, rejected_by: who }),
    });
    status(`rejected ${result.rejected}`, 'good');
  } catch (e) { return status(e.message, 'bad'); }
  await Promise.all([loadCounts(), loadList()]);
}

async function resetOne(url) {
  try {
    await api('/api/admin/candidates/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind: state.kind, url }),
    });
  } catch (e) { return status(e.message, 'bad'); }
  await Promise.all([loadCounts(), loadList()]);
}

// --- wiring -------------------------------------------------------------------

function refresh() {
  loadCounts();
  loadAuthorities();
  loadList();
}

export function initCandidates() {
  const panel = $('tab-candidates');
  if (!panel) return;

  $('candidate-status-filter').addEventListener('change', (event) => {
    state.status = event.target.value;
    state.offset = 0;
    loadList();
  });
  $('candidate-authority').addEventListener('change', (event) => {
    state.authority = event.target.value;
    state.offset = 0;
    loadList();
  });

  let timer = null;
  $('candidate-search').addEventListener('input', (event) => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      state.search = event.target.value.trim();
      state.offset = 0;
      loadList();
    }, 250);
  });

  $('candidate-reject-selected').addEventListener('click', () => {
    if (state.selected.size) rejectMany([...state.selected]);
  });

  // The tab strip is app.js's, and it shows panels by id. Loading on first
  // reveal rather than on page load keeps three queries off the critical path
  // of a page that usually opens on the queue.
  let loaded = false;
  const observer = new MutationObserver(() => {
    if (panel.classList.contains('active') && !loaded) { loaded = true; refresh(); }
  });
  observer.observe(panel, { attributes: true, attributeFilter: ['class'] });
  if (panel.classList.contains('active')) { loaded = true; refresh(); }
}
