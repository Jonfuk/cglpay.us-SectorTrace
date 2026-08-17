/* The Claims tab: what the campaign says, and what it says it from.
 *
 * Workstream C (Phase 17). A claim is a statement written by a person,
 * linked to the evidence rows that support it, and decided by a named
 * reviewer — the same threshold migration 0030 sets for promotion, recorded
 * the same way. Nothing here is computed: the text is what was written, the
 * citations are rows that were picked, the caveats are lines about what may
 * not be computed from it.
 *
 * Three things shape the layout, and each is the act itself rather than
 * decoration:
 *
 *   * **Writing is drafting.** The form writes a claim as a draft. Every
 *     later status is a decision, and migration 0048 refuses a claim that is
 *     decided — or born decided — without a claim_verifications row behind
 *     it. Nothing on this screen can publish a claim without the reviewer
 *     box naming who decided it.
 *   * **Citations are picked, not typed.** The picker searches a citable
 *     evidence table and returns rows as {key, label, url} candidates, so
 *     the key a citation stores is the key of a row that existed when it was
 *     picked. The list still resolves each citation when it renders, because
 *     the warehouse can move between the picking and the deciding.
 *   * **Deciding is per claim.** Publishing, rejecting and retracting are
 *     one claim at a time, with the reviewer's name, and the history panel
 *     shows every decision — kept whether or not the claim is later reset,
 *     the same rule the census worklist follows.
 */
import { el } from './dom.js';

const $ = (id) => document.getElementById(id);

const state = {
  status: 'all',
  offset: 0,
  items: [],
  tables: [],
  busy: false,
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
  const node = $('claim-status');
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
  try { data = await api('/api/admin/claims/counts'); }
  catch (e) { return status(e.message, 'bad'); }

  const pill = $('claim-pill');
  if (pill) {
    pill.textContent = String(data.draft);
    pill.hidden = data.draft === 0;
  }

  $('claim-counts').replaceChildren(...Object.entries({
    draft: 'draft', published: 'published', rejected: 'rejected', retracted: 'retracted',
  }).map(([key, label]) =>
    el('button', {
      class: state.status === key ? 'chip active' : 'chip',
      onclick: () => {
        state.status = state.status === key ? 'all' : key;
        $('claim-status-filter').value = state.status;
        state.offset = 0;
        loadList();
        loadCounts();
      },
    },
      el('strong', { text: String(data[key] ?? 0) }),
      el('span', { class: 'muted small', text: ` ${label}` }),
    )));

  renderHistory(data.decisions || []);
}

function renderHistory(rows) {
  const history = $('claim-history');
  if (!rows.length) {
    history.replaceChildren(el('p', {
      class: 'muted small',
      text: 'No claim decided yet. Every decision is recorded here with who made it.',
    }));
    return;
  }
  history.replaceChildren(el('table', {},
    el('thead', {}, el('tr', {},
      el('th', { text: 'When' }), el('th', { text: 'Who' }),
      el('th', { text: 'Decision' }), el('th', { text: 'Claim' }),
      el('th', { text: 'Note' }))),
    el('tbody', {}, ...rows.map((row) => el('tr', {},
      el('td', { class: 'small', text: row.decided_at }),
      el('td', { class: 'small', text: row.decided_by }),
      el('td', { class: 'small', text: row.decision }),
      el('td', { class: 'small', text: (row.claim_text || '').slice(0, 80) }),
      el('td', { class: 'small muted', text: row.note || '' }))))));
}

// --- the worklist -------------------------------------------------------------

async function loadList() {
  const params = new URLSearchParams({
    status: state.status, offset: String(state.offset), limit: '50',
  });
  let data;
  try { data = await api(`/api/admin/claims?${params}`); }
  catch (e) { return status(e.message, 'bad'); }

  state.items = data.items;
  render(data);
}

function render(data) {
  const list = $('claim-list');
  if (!data.items.length) {
    list.replaceChildren(el('p', { class: 'muted', text: 'Nothing here.' }));
    $('claim-pager').replaceChildren();
    return;
  }

  list.replaceChildren(...data.items.map(renderItem));

  const shown = data.offset + data.items.length;
  $('claim-pager').replaceChildren(
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

function renderItem(item) {
  const isDraft = item.status === 'draft';

  const card = el('div', { class: 'candidate' },
    el('div', { class: 'row' },
      el('span', { class: 'pill', text: item.status }),
      el('span', { class: 'spacer' }),
      el('span', { class: 'muted small', text: `#${item.id} · written by ${item.created_by} · ${item.created_at}` })),
    el('blockquote', { class: 'small rawline', text: item.claim_text }),
    renderCaveats(item.caveats),
    renderCitations(item.citations, item.id, isDraft),
    renderDecisions(item.decisions),
    renderActions(item));

  card.dataset.id = String(item.id);
  return card;
}

function renderCaveats(caveats) {
  const lines = (caveats || '').split('\n').map((line) => line.trim()).filter(Boolean);
  if (!lines.length) return null;
  return el('div', { class: 'row wrap' },
    el('span', { class: 'muted small', text: 'You may not compute this from it: ' }),
    lines.map((line) => el('span', { class: 'muted small', text: `“${line}” ` })));
}

function renderCitations(citations, claimId, isDraft) {
  if (!citations || !citations.length) {
    return el('p', { class: 'muted small', text: 'No citations yet — a claim with nothing behind it is a claim nobody can check.' });
  }
  return el('div', {},
    ...citations.map((citation) => {
      const resolved = citation.resolved;
      const label = resolved ? resolved.label : `${citation.evidence_table}: ${citation.evidence_key}`;
      return el('div', { class: 'row' },
        el('span', { class: 'small', text: '⇢ ' }),
        resolved
          ? el('a', { href: resolved.url || '#', target: '_blank',
                      rel: 'noopener noreferrer', class: 'small', text: label })
          : el('span', { class: 'small muted', text: label }),
        el('span', { class: 'muted small', text: ` · ${citation.evidence_table}` }),
        resolved
          ? null
          : el('span', { class: 'small bad', text: ' — no longer in the warehouse' }),
        el('span', { class: 'spacer' }),
        isDraft
          ? el('button', {
              class: 'btn ghost tiny', text: 'Remove',
              onclick: () => unciteOne(citation, claimId),
            })
          : null);
    }));
}

function renderDecisions(decisions) {
  if (!decisions || !decisions.length) return null;
  return el('div', { class: 'row wrap' }, ...decisions.map((d) => el('span', {
    class: 'muted small',
    text: `${d.decision} by ${d.decided_by} at ${d.decided_at}${d.note ? ` — ${d.note}` : ''}`,
  })));
}

/* The actions a claim admits, by its status. Deciding is per claim and per
 * person: the reviewer box names who decided, and every button is disabled
 * without it. */
function renderActions(item) {
  const actions = [];

  if (item.status === 'draft') {
    actions.push(
      el('button', {
        class: 'btn primary', text: 'Publish',
        title: 'Approve this claim for the portal. Recorded under the reviewer name.',
        onclick: () => decideOne(item.id, 'published', null),
      }),
      el('button', {
        class: 'btn', text: 'Reject',
        title: 'Decide this claim cannot be made.',
        onclick: () => decideOne(item.id, 'rejected', null),
      }),
      el('button', {
        class: 'btn', text: 'Edit text',
        title: 'Rewrite the statement and caveats — drafts only.',
        onclick: () => editOne(item),
      }),
      citationPicker(item));
  } else if (item.status === 'published') {
    actions.push(
      el('button', {
        class: 'btn', text: 'Retract',
        title: 'Withdraw a published claim. Recorded under the reviewer name.',
        onclick: () => decideOne(item.id, 'retracted', null),
      }),
      el('button', {
        class: 'btn ghost', text: 'Reset to draft',
        onclick: () => resetOne(item.id),
      }));
  } else {
    actions.push(
      el('button', {
        class: 'btn ghost', text: 'Reset to draft',
        onclick: () => resetOne(item.id),
      }));
  }

  const box = el('div', { class: 'row wrap' }, ...actions);
  if (item.status === 'draft') {
    box.append(el('span', { class: 'muted small', text: 'the reviewer box names who decides' }));
  }
  return box;
}

function citationPicker(item) {
  return el('span', { class: 'citation-picker' },
    el('select', {
      class: 'small',
      'aria-label': 'Evidence table',
      onchange: (event) => {
        const picker = event.target.closest('.citation-picker');
        pickEvidence(picker, event.target.value);
      },
    }, el('option', { value: '', text: 'Cite evidence…' }),
      ...state.tables.map((table) => el('option', { value: table, text: table }))),
    el('input', {
      type: 'search', class: 'small', placeholder: 'search…', hidden: true,
      'aria-label': 'Search evidence',
      oninput: (event) => {
        const picker = event.target.closest('.citation-picker');
        pickEvidence(picker, picker.querySelector('select').value, event.target.value);
      },
    }),
    el('div', { class: 'evidence-hits' }));
}

async function pickEvidence(picker, table, term = '') {
  const input = picker.querySelector('input');
  const hits = picker.querySelector('.evidence-hits');
  if (!table) {
    input.hidden = true;
    hits.replaceChildren();
    return;
  }
  if (!term) {
    input.hidden = false;
    input.focus();
    hits.replaceChildren();
    return;
  }
  let rows = [];
  try {
    const data = await api(`/api/admin/claims/evidence?table=${encodeURIComponent(table)}&q=${encodeURIComponent(term)}&limit=8`);
    rows = data.rows || [];
  } catch (e) {
    hits.replaceChildren(el('span', { class: 'small bad', text: e.message }));
    return;
  }
  if (!rows.length) {
    hits.replaceChildren(el('span', { class: 'muted small', text: 'no matching rows' }));
    return;
  }
  hits.replaceChildren(...rows.map((row) => el('button', {
    class: 'btn ghost tiny', text: row.label.slice(0, 60),
    title: row.url || '',
    onclick: () => citeOne(picker, table, row),
  })));
}

// --- deciding -----------------------------------------------------------------

async function citeOne(picker, table, row) {
  const card = picker.closest('.candidate');
  const claimId = Number(card.dataset.id);
  const who = reviewerName();
  if (!who) {
    status('Put your name in the reviewer box first — citations are attributed.', 'bad');
    return;
  }
  try {
    await api('/api/admin/claims/cite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ claim_id: claimId, evidence_table: table,
                             evidence_key: row.key, cited_by: who }),
    });
    status(`cited ${row.label.slice(0, 40)}…`, 'good');
  } catch (e) { return status(e.message, 'bad'); }
  loadList();
}

async function unciteOne(citation, claimId) {
  try {
    await api('/api/admin/claims/uncite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ claim_id: claimId,
                             evidence_table: citation.evidence_table,
                             evidence_key: citation.evidence_key }),
    });
  } catch (e) { return status(e.message, 'bad'); }
  loadList();
}

async function decideOne(claimId, decision, note) {
  const who = reviewerName();
  if (!who) {
    status('Put your name in the reviewer box first — decisions are attributed.', 'bad');
    return;
  }
  const confirmText = {
    published: 'Publish this claim? It will appear on the public portal, under this reviewer name.',
    rejected: 'Reject this claim? The decision stays on record.',
    retracted: 'Retract this published claim? The decision stays on record.',
  }[decision];
  if (!confirm(confirmText)) return;

  try {
    await api('/api/admin/claims/decide', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ claim_id: claimId, decision, decided_by: who,
                             note: note || null }),
    });
    status(`claim ${decision}`, 'good');
  } catch (e) { return status(e.message, 'bad'); }
  await Promise.all([loadCounts(), loadList()]);
}

async function resetOne(claimId) {
  try {
    await api('/api/admin/claims/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ claim_id: claimId }),
    });
  } catch (e) { return status(e.message, 'bad'); }
  await Promise.all([loadCounts(), loadList()]);
}

function editOne(item) {
  const text = $('claim-new-text');
  const caveats = $('claim-new-caveats');
  const note = $('claim-new-note');
  text.value = item.claim_text;
  caveats.value = item.caveats || '';
  note.value = item.note || '';
  text.focus();
  $('claim-new').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  $('claim-create').dataset.editId = String(item.id);
  $('claim-create').textContent = 'Save draft';
}

async function createOrUpdate() {
  const text = $('claim-new-text').value;
  const caveats = $('claim-new-caveats').value;
  const note = $('claim-new-note').value;
  const who = reviewerName();
  if (!who) {
    status('Put your name in the reviewer box first — claims are attributed.', 'bad');
    return;
  }

  const editId = $('claim-create').dataset.editId;
  const path = editId ? '/api/admin/claims/update' : '/api/admin/claims/create';
  const body = editId
    ? { claim_id: Number(editId), claim_text: text, caveats, note: note || null }
    : { claim_text: text, caveats, note: note || null, created_by: who };

  try {
    await api(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    status(editId ? 'draft saved' : 'draft written', 'good');
  } catch (e) { return status(e.message, 'bad'); }

  delete $('claim-create').dataset.editId;
  $('claim-create').textContent = 'Write draft';
  $('claim-new-text').value = '';
  $('claim-new-caveats').value = '';
  $('claim-new-note').value = '';
  await Promise.all([loadCounts(), loadList()]);
}

// --- wiring -------------------------------------------------------------------

function refresh() {
  loadCounts();
  loadList();
}

export function initClaims() {
  const panel = $('tab-claims');
  if (!panel) return;

  (async () => {
    try {
      const data = await api('/api/admin/claims/evidence?table=&q=');
      state.tables = data.tables || [];
    } catch (e) { /* the picker's select will simply be empty */ }
  })();

  $('claim-status-filter').addEventListener('change', (event) => {
    state.status = event.target.value;
    state.offset = 0;
    loadList();
    loadCounts();
  });

  $('claim-create').addEventListener('click', createOrUpdate);

  // The counts alone run on load, because they fill the tab-strip pill.
  loadCounts();

  let loaded = false;
  const observer = new MutationObserver(() => {
    if (panel.classList.contains('active') && !loaded) {
      loaded = true;
      refresh();
    }
  });
  observer.observe(panel, { attributes: true, attributeFilter: ['class'] });
  if (panel.classList.contains('active')) {
    loaded = true;
    refresh();
  }
}
