/* The Claim review tab: the human-review labour BETA-034 is blocked on (BETA-047).
 *
 * A reviewer works one machine-extracted (subject, predicate, object) triple
 * at a time and records approve / reject / corrected against their name. The
 * backend functions already exist -- `pipeline/nlp/decisions.decide` (with
 * ontology-validated corrections), `decisions.history`, and
 * `pipeline/nlp/gate.check` for the training-readiness report. This tab is
 * the workbench over them, and it adds no policy of its own:
 *
 *   * one candidate per decision -- there is no bulk-approve control here;
 *   * a decision without a reviewer name is refused (server-side too);
 *   * nothing writes graph_claims, trains a classifier, or produces public
 *     output. The copy says so and the code has no path to it.
 *
 * An /api/admin/* tool, behind the operator's network-trust boundary.
 */
import { el } from './dom.js';

const $ = (id) => document.getElementById(id);

const PAGE = 25;
const state = {
  offset: 0,
  predicates: [],
  concepts: [],
  reasonCodes: [],
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

function reviewerName() {
  const field = $('reviewer');
  return field ? field.value.trim() : '';
}

function filters() {
  return {
    q: $('cr-q').value.trim(),
    status: $('cr-status').value,
    predicate: $('cr-predicate').value,
    source_system: $('cr-source').value,
  };
}

// --- the gate strip ---------------------------------------------------------

async function loadGate() {
  const box = $('claimreview-gate');
  let data;
  try { data = await api('/api/admin/claim-gate'); }
  catch (e) { box.hidden = true; return; }

  const chips = [
    el('span', { class: 'chip', text: data.ready ? 'gate: READY' : 'gate: not yet' }),
    el('span', { class: 'chip', text: `${data.n_decisions} decisions` }),
    el('span', { class: 'chip', text: `${data.n_decided_candidates} candidates decided` }),
  ];
  const inter = data.inter_reviewer || {};
  chips.push(el('span', { class: 'chip',
    text: `double-reviewed ${inter.double_reviewed ?? 0}${inter.assessed ? `, agreement ${inter.agreement}` : ' (not assessed)'}` }));

  const catRows = Object.entries(data.categories || {}).map(([name, c]) =>
    el('li', {},
      el('strong', { text: name }),
      ` — +${c.positive} / -${c.negative}, ${c.distinct_subjects} subjects, `
      + `${(c.years || []).length} years — `,
      el('span', { text: c.ready ? 'ready' : (c.shortfalls || []).join('; ') })));

  box.replaceChildren(
    el('div', { class: 'chips' }, ...chips),
    el('p', { class: 'small muted', style: 'margin:6px 0 2px',
      text: 'Per-category training readiness (034G). Closing the gate is reviewer labour, not code:' }),
    el('ul', { class: 'small' }, ...catRows),
    (data.blocking || []).length
      ? el('p', { class: 'small', text: `Blocking: ${data.blocking.join(' · ')}` })
      : null);
  box.hidden = false;
}

// --- the vocabularies for the correction form ------------------------------

async function loadOntology() {
  let data;
  try { data = await api('/api/admin/claim-ontology'); }
  catch (e) { return; }
  state.predicates = data.predicates || [];
  state.concepts = data.concepts || [];
  state.reasonCodes = data.reason_codes || [];

  const sel = $('cr-predicate');
  sel.replaceChildren(el('option', { value: '', text: 'Any predicate' }));
  for (const p of state.predicates) {
    sel.append(el('option', { value: p.id, text: `${p.label} (${p.id})` }));
  }
}

// --- one candidate + its decision form ------------------------------------

function decisionForm(candidate) {
  const wrap = el('div', { class: 'panel' });
  const status = el('div', { class: 'small' });

  const decision = el('select', { 'aria-label': 'Decision' },
    el('option', { value: 'approved', text: 'Approve — triple is right' }),
    el('option', { value: 'rejected', text: 'Reject — wrong, not salvageable' }),
    el('option', { value: 'corrected', text: 'Correct — real, but a field is wrong' }));

  const reason = el('select', { 'aria-label': 'Reason code' },
    el('option', { value: '', text: '(reason code, optional)' }),
    ...state.reasonCodes.map((r) => el('option', { value: r, text: r })));

  const correctedPredicate = el('select', { 'aria-label': 'Corrected predicate' },
    el('option', { value: '', text: '(keep predicate)' }),
    ...state.predicates.map((p) => el('option', { value: p.id, text: p.label })));
  const correctedConcept = el('select', { 'aria-label': 'Corrected object concept' },
    el('option', { value: '', text: '(keep object concept)' }),
    ...state.concepts.map((c) => el('option', { value: c.id, text: `${c.label} (${c.id})` })));
  const correctedLiteral = el('input', { type: 'text', 'aria-label': 'Corrected object literal', placeholder: 'corrected object literal' });

  const correctionRow = el('div', { class: 'runbar', hidden: true },
    correctedPredicate, correctedConcept, correctedLiteral);
  decision.addEventListener('change', () => {
    correctionRow.hidden = decision.value !== 'corrected';
  });

  const note = el('input', { type: 'text', 'aria-label': 'Note', placeholder: 'note (optional)' });
  const submit = el('button', { class: 'btn primary', type: 'submit', text: 'Record decision' });

  const form = el('form', { class: 'stack' },
    el('div', { class: 'runbar' }, decision, reason),
    correctionRow,
    el('div', { class: 'runbar' }, note, submit),
    status);

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const who = reviewerName();
    if (!who) { status.textContent = 'Enter your name in the Reviewer box above.'; return; }
    submit.disabled = true;
    status.textContent = 'Recording…';
    const body = {
      claim_candidate_id: candidate.claim_candidate_id,
      decision: decision.value,
      decided_by: who,
      reason_code: reason.value || null,
      note: note.value.trim() || null,
    };
    if (decision.value === 'corrected') {
      body.corrected_predicate = correctedPredicate.value || null;
      body.corrected_object_concept_id = correctedConcept.value || null;
      body.corrected_object_literal = correctedLiteral.value.trim() || null;
    }
    try {
      const result = await api('/api/admin/claim-candidates/decide', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      status.textContent = `Recorded: ${result.decision} → ${result.status}.`;
      loadGate();
      loadList();
    } catch (error) {
      status.textContent = `Refused: ${error.message}`;
      submit.disabled = false;
    }
  });

  wrap.replaceChildren(form);
  return wrap;
}

function candidateCard(candidate) {
  const objectText = candidate.object_concept_label
    ? `${candidate.object_concept_label} (${candidate.object_concept_id})`
    : (candidate.object_literal || '—');
  const meta = [candidate.source_system, candidate.document_type,
    `score ${candidate.relation_score}`, candidate.assertion_status,
    `status ${candidate.status}`].filter(Boolean).join(' · ');

  return el('article', { class: 'panel' },
    el('div', { class: 'row', style: 'justify-content:space-between;gap:8px;align-items:baseline' },
      el('strong', { text: candidate.predicate_label || candidate.predicate }),
      el('span', { class: 'muted small', text: meta })),
    el('p', { class: 'small' },
      el('em', { text: `subject: ${candidate.subject_hint || '(from mention)'}` }),
      ` — object: ${objectText}`),
    el('blockquote', { class: 'small', text: candidate.evidence_span || '' }),
    el('div', { class: 'row small', style: 'gap:12px;flex-wrap:wrap' },
      candidate.source_url
        ? el('a', { href: candidate.source_url, target: '_blank', rel: 'noopener' }, 'Source page')
        : null,
      candidate.last_decision
        ? el('span', { class: 'muted', text: `last: ${candidate.last_decision} by ${candidate.last_decided_by} (${candidate.decision_count})` })
        : el('span', { class: 'muted', text: 'no decision yet' })),
    decisionForm(candidate));
}

async function loadList() {
  const list = $('claimreview-list');
  const statusLine = $('claimreview-status');
  const f = filters();
  const params = new URLSearchParams({ offset: state.offset, limit: PAGE });
  if (f.q) params.set('q', f.q);
  if (f.status) params.set('status', f.status);
  if (f.predicate) params.set('predicate', f.predicate);
  if (f.source_system) params.set('source_system', f.source_system);

  statusLine.textContent = 'Loading…';
  let data;
  try { data = await api(`/api/admin/claim-candidates?${params}`); }
  catch (error) { statusLine.textContent = `Failed: ${error.message}`; return; }

  const rows = data.candidates || [];
  statusLine.textContent = data.total
    ? `${data.page.offset + 1}–${data.page.offset + rows.length} of ${data.total} candidates.`
    : 'No candidates match these filters.';
  list.replaceChildren(...rows.map(candidateCard));

  const pager = $('claimreview-pager');
  pager.replaceChildren();
  if (state.offset > 0) {
    pager.append(el('button', { class: 'btn', type: 'button',
      onclick: () => { state.offset = Math.max(0, state.offset - PAGE); loadList(); } }, '← Previous'));
  }
  if (data.page.offset + rows.length < data.total) {
    pager.append(el('button', { class: 'btn', type: 'button',
      onclick: () => { state.offset += PAGE; loadList(); } }, 'Next →'));
  }
}

export function initClaimReview() {
  const panel = $('tab-claimreview');
  if (!panel) return;

  $('claimreview-filters').addEventListener('submit', (event) => {
    event.preventDefault();
    state.offset = 0;
    loadList();
  });

  let loaded = false;
  const load = () => {
    if (loaded) return;
    loaded = true;
    loadOntology().then(loadList);
    loadGate();
  };
  const observer = new MutationObserver(() => {
    if (panel.classList.contains('active')) load();
  });
  observer.observe(panel, { attributes: true, attributeFilter: ['class'] });
  if (panel.classList.contains('active')) load();
}
