/* The Candidates tab: what three modules found, and what a person makes of it.
 *
 * The shape of this screen follows the shape of the decision it supports.
 * Promoting opens the document first, because the act being recorded is that
 * somebody looked. Rejecting is bulk, because deciding a link is not what it
 * looked like is something you can do from the list, and being wrong leaves a
 * candidate a candidate.
 *
 * Promoting used to be one row and one click, with no batch path at all. The
 * result, after the screen had existed for a while: 2,462 undecided
 * candidates and zero promotions. Nothing had ever crossed into the evidence
 * base, because the only way across was a form filled in 2,462 times. A
 * safeguard that stops all traffic is not protecting anything.
 *
 * So there is a batch path now, and the thing it batches is the clicking:
 *
 *   * `state.opened` records which documents this session actually opened,
 *     from the anchor on the row. Only those can be promoted in a batch.
 *     Selected-but-unopened rows are listed with the reason and there is no
 *     override — the gate is the settled decision (CLAUDE.md 4, migration
 *     0030), and one that can be clicked past is decoration.
 *
 *   * The requests go one at a time, never Promise.all. Each promotion
 *     fetches a live document through the shared client, so a parallel batch
 *     would fight the per-host rate limit and the process-wide write slot.
 *
 *   * A failure is recorded against its row and the run continues. A dead
 *     link in position two must not abandon the remaining four.
 *
 * The server is unchanged and deliberately so: /api/admin/candidates/promote
 * still takes one URL and still refuses a list. What makes a promotion honest
 * is one fetch, one archived payload and one evidence_promotions row per
 * document, and that is still what happens.
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
  // Documents opened in this session. Deliberately not persisted: "I have
  // read this" is a claim about the person at the keyboard now, and a
  // localStorage key would let a batch inherit somebody else's reading, or
  // last week's.
  opened: new Set(),
  // url -> { fields: {name: input}, note: input }, so a batch can read what
  // each row's own form says rather than sending one set of values for all.
  forms: new Map(),
  busy: false,
};

// A browser will not open an unbounded number of tabs from one click, and a
// person will not read them either.
const OPEN_AT_ONCE = 10;

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

/** A link that reopens this tab filtered to one candidate.
 *
 * Built out of the kind and search controls rather than a new route: the
 * search box already matches on URL, so "the candidate I am asking you about"
 * is a filter this screen can already express. app.js owns the hash and only
 * writes review and database parameters into it, so these are read on arrival
 * and never written back — two writers on one hash is how a shared link ends
 * up pointing somewhere else.
 */
function candidateLink(item) {
  const params = new URLSearchParams({ kind: state.kind, q: item.url });
  return `${location.origin}${location.pathname}#candidates?${params}`;
}

function copyText(text) {
  // navigator.clipboard is undefined on plain http from another machine --
  // only localhost counts as a secure context -- and this UI is routinely
  // reached over the LAN.
  if (!navigator.clipboard) {
    window.prompt('Copy this link:', text);
    return;
  }
  navigator.clipboard.writeText(text).then(
    () => status('link copied', 'good'),
    () => window.prompt('Copy this link:', text));
}

// --- the counts strip ---------------------------------------------------------

async function loadCounts() {
  let data;
  try { data = await api('/api/admin/candidates/counts'); }
  catch (e) { return status(e.message, 'bad'); }

  // The tab strip carries the undecided total the way the review queue does.
  // A queue you have to open to discover the size of is a queue that gets
  // opened less often.
  const undecided = Object.values(data.kinds)
    .reduce((total, counts) => total + (counts.undecided || 0), 0);
  const pill = $('candidate-pill');
  if (pill) {
    pill.textContent = String(undecided);
    pill.hidden = undecided === 0;
  }

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
  // The inputs these pointed at are about to be replaced. `opened` survives:
  // it records what a person read, which paging away from does not undo.
  state.forms.clear();
  render(data);
}

function render(data) {
  const list = $('candidate-list');
  // The selection is cleared with every load, so the bulk bar has to be told;
  // otherwise its buttons keep the counts of a list that is gone.
  updateBulk();
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

  const openedPill = el('span', { class: 'pill opened', text: 'opened' });
  openedPill.hidden = !state.opened.has(item.url);

  // The document itself, opened in a new tab. Promoting without having read
  // it is the failure this whole screen is arranged against, so this is also
  // where a candidate becomes eligible for a batch: the click is the record
  // that somebody looked.
  const link = el('a', {
    href: item.url, target: '_blank', rel: 'noopener noreferrer',
    class: 'small mono', text: item.url,
    onclick: () => markOpened(item.url),
    // Middle-click and "open in new tab" are how a lot of people open a list.
    onauxclick: (event) => { if (event.button === 1) markOpened(item.url); },
  });

  const row = el('div', { class: 'candidate' },
    el('div', { class: 'row' },
      check,
      el('strong', { text: item.summary.title || item.summary.report_title || '(untitled)' }),
      el('span', { class: 'spacer' }),
      openedPill,
      decided ? el('span', { class: 'pill', text: decided }) : null,
      el('span', { class: 'muted small', text: item.authority_name || item.authority_ons_code || '' }),
    ),
    el('div', { class: 'row wrap' }, ...summary),
    el('div', { class: 'row' },
      link,
      el('span', { class: 'spacer' }),
      el('button', {
        class: 'btn ghost', title: 'Copy a link that reopens this list on this candidate',
        text: 'Link', onclick: () => copyText(candidateLink(item)),
      }),
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

  // What the batch reports against, and what it marks while it runs.
  row.dataset.url = item.url;
  return row;
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

  // Registered so "Fill into selected" and the batch can reach this row's own
  // values. Cleared with the list, in loadList.
  state.forms.set(item.url, { fields: inputs, note });

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

// --- what a batch may touch ---------------------------------------------------

function markOpened(url) {
  if (state.opened.has(url)) return;
  state.opened.add(url);
  const row = rowFor(url);
  if (row) {
    const pill = row.querySelector('.pill.opened');
    if (pill) pill.hidden = false;
  }
  updateBulk();
}

function rowFor(url) {
  return [...document.querySelectorAll('#candidate-list .candidate')]
    .find((node) => node.dataset.url === url) || null;
}

/** Split the selection into what a batch promote may send and what it may
 *  not, with the reason. Undecided-ness comes from the loaded item, so a row
 *  already promoted in this session is excluded without a round trip. */
function partitionSelection() {
  const ready = [];
  const blocked = [];
  for (const url of state.selected) {
    const item = state.items.find((candidate) => candidate.url === url);
    if (!item) continue;
    if (item.verified) blocked.push({ item, why: 'already promoted' });
    else if (!state.opened.has(url)) blocked.push({ item, why: 'not opened in this session' });
    else ready.push(item);
  }
  return { ready, blocked };
}

function updateBulk() {
  const count = state.selected.size;
  const { ready, blocked } = partitionSelection();

  const reject = $('candidate-reject-selected');
  reject.disabled = count === 0 || state.busy;
  reject.textContent = count ? `Reject ${count} selected` : 'Reject selected';

  const open = $('candidate-open-selected');
  open.disabled = count === 0 || state.busy;
  open.textContent = count
    ? `Open ${Math.min(count, OPEN_AT_ONCE)} selected` : 'Open selected';

  const promote = $('candidate-promote-opened');
  promote.disabled = ready.length === 0 || state.busy;
  promote.textContent = ready.length
    ? `Promote ${ready.length} opened` : 'Promote opened';

  $('candidate-fill-apply').disabled = count === 0 || state.busy;

  // Why the button says fewer than you selected. Named rather than counted:
  // "3 excluded" tells you nothing about which three.
  const note = $('candidate-batch');
  if (!blocked.length) {
    note.hidden = true;
    note.replaceChildren();
    return;
  }
  note.hidden = false;
  note.replaceChildren(
    el('p', { class: 'muted small' },
      `${blocked.length} selected candidate${blocked.length === 1 ? '' : 's'} `
      + 'cannot be promoted in a batch:'),
    el('ul', { class: 'small' }, ...blocked.map(({ item, why }) => el('li', {},
      el('span', { text: item.summary.title || item.summary.report_title || item.url }),
      el('span', { class: 'muted', text: ` — ${why}` })))),
    el('p', { class: 'muted small', text:
      'Open a document to make it promotable. Nothing here promotes a '
      + 'document nobody has looked at.' }));
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

/** Promote every opened candidate in the selection, one request at a time.
 *
 * Sequential on purpose. Each promotion fetches a live document through the
 * same client the modules use, so a parallel batch would queue behind the
 * per-host rate limit anyway and would fight the process-wide write slot
 * while doing it. One at a time is also what makes the progress line honest.
 *
 * A failure stops that candidate and nothing else: a dead link in position
 * two must not abandon the remaining four, and a candidate that failed is
 * still a candidate.
 */
async function promoteOpened() {
  const who = reviewerName();
  if (!who) {
    status('Put your name in the reviewer box first — promotions are attributed.', 'bad');
    return;
  }

  const { ready } = partitionSelection();
  if (!ready.length) return;

  // Each of these fetches a document from somebody else's server. Worth one
  // confirmation with the number in it.
  if (!confirm(`Promote ${ready.length} opened candidate${ready.length === 1 ? '' : 's'}? `
                + 'Each one fetches and archives the document.')) return;

  state.busy = true;
  updateBulk();

  const done = [];
  const failed = [];

  for (const [index, item] of ready.entries()) {
    const form = state.forms.get(item.url);
    const fields = {};
    for (const [name, input] of Object.entries(form ? form.fields : {})) {
      fields[name] = input.value;
    }
    const note = form && form.note.value ? form.note.value : null;

    const row = rowFor(item.url);
    if (row) row.classList.add('working');
    status(`${index + 1} of ${ready.length} — fetching ${item.url}…`);

    try {
      const result = await api('/api/admin/candidates/promote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind: state.kind, url: item.url, promoted_by: who,
                                fields, note }),
      });
      done.push({ item, sha: result.payload_sha256 });
    } catch (e) {
      failed.push({ item, why: e.message });
    } finally {
      if (row) row.classList.remove('working');
    }
  }

  state.busy = false;
  status(`promoted ${done.length} of ${ready.length}`, failed.length ? 'bad' : 'good');
  renderBatchResult(done, failed);
  await Promise.all([loadCounts(), loadList()]);
}

/** The run's outcome, kept on screen. Failures especially: a batch that
 *  reports only a total is a batch whose failures get discovered later. */
function renderBatchResult(done, failed) {
  const note = $('candidate-result');
  note.hidden = false;
  note.replaceChildren(
    el('p', { class: failed.length ? 'small bad' : 'small good' },
      `Promoted ${done.length}. Failed ${failed.length}.`),
    ...(failed.length
      ? [el('ul', { class: 'small' }, ...failed.map(({ item, why }) => el('li', {},
          el('span', { class: 'mono', text: item.url }),
          el('span', { class: 'muted', text: ` — ${why}` }))))]
      : []),
    ...(done.length
      ? [el('p', { class: 'muted small', text:
          `Archived: ${done.map((d) => d.sha.slice(0, 12)).join(', ')}` })]
      : []),
    el('button', {
      class: 'btn ghost', text: 'Dismiss',
      onclick: () => { note.hidden = true; note.replaceChildren(); },
    }));
}

/** Open the selected documents, so "read them, then promote them" is two
 *  clicks. Capped: browsers block a burst of tabs, and a person cannot read
 *  thirty of them anyway. */
function openSelected() {
  const urls = [...state.selected].slice(0, OPEN_AT_ONCE);
  let blocked = 0;
  for (const url of urls) {
    const win = window.open(url, '_blank', 'noopener');
    if (win) markOpened(url);
    else blocked += 1;
  }
  if (blocked) {
    status(`${blocked} tab${blocked === 1 ? '' : 's'} blocked by the browser — `
            + 'allow pop-ups for this page, or open them from the list.', 'bad');
  } else {
    status(`opened ${urls.length}`, 'good');
  }
}

/** Write one document type into every selected row's own input, so the value
 *  that will be sent is visible per row before anything runs. */
function fillTypeIntoSelected() {
  const value = $('candidate-fill-type').value.trim();
  if (!value) {
    status('Nothing to fill — put a document type in the box first.', 'bad');
    return;
  }
  let filled = 0;
  for (const url of state.selected) {
    const form = state.forms.get(url);
    if (!form || !form.fields.document_type) continue;
    form.fields.document_type.value = value;
    filled += 1;
  }
  status(filled ? `filled ${filled} row${filled === 1 ? '' : 's'}`
                 : 'no selected row asks for a document type');
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

/** Adopt `kind` and `q` from the hash, if this tab is what the hash names.
 *  Returns true when something changed, so the caller can avoid a second
 *  load of the list it was about to load anyway. */
function applyHash() {
  const [tab, query] = location.hash.slice(1).split('?');
  if (tab !== 'candidates' || !query) return false;
  const params = new URLSearchParams(query);
  const kind = params.get('kind');
  const search = params.get('q');
  let changed = false;
  if (kind && KIND_LABELS[kind] && kind !== state.kind) {
    state.kind = kind;
    state.offset = 0;
    changed = true;
  }
  if (search !== null && search !== state.search) {
    state.search = search;
    state.offset = 0;
    const box = $('candidate-search');
    if (box) box.value = search;
    changed = true;
  }
  return changed;
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
  $('candidate-open-selected').addEventListener('click', openSelected);
  $('candidate-promote-opened').addEventListener('click', promoteOpened);
  $('candidate-fill-apply').addEventListener('click', fillTypeIntoSelected);

  // The command palette asks for a kind by name. It sets the hash to reach
  // this tab and then says which list it meant; it does not reach in and set
  // state itself.
  document.addEventListener('candidates:kind', (event) => {
    const kind = event.detail && event.detail.kind;
    if (!kind || !KIND_LABELS[kind]) return;
    state.kind = kind;
    state.offset = 0;
    state.authority = '';
    refresh();
  });

  // The counts alone run on load, because they fill the tab-strip pill and a
  // count nobody can see until they open the tab is not a count. The list and
  // the authority facets still wait for the first reveal — that is the pair
  // that was worth keeping off the critical path of a page which usually
  // opens on the queue.
  loadCounts();

  // The tab strip is app.js's, and it shows panels by id.
  let loaded = false;

  // A pasted candidate link arrives as a hash change, and may arrive before
  // this tab has ever been revealed — in which case the reveal below loads it.
  window.addEventListener('hashchange', () => {
    if (applyHash() && loaded) loadList();
  });

  const observer = new MutationObserver(() => {
    if (panel.classList.contains('active') && !loaded) {
      loaded = true;
      applyHash();
      refresh();
    }
  });
  observer.observe(panel, { attributes: true, attributeFilter: ['class'] });
  if (panel.classList.contains('active')) {
    loaded = true;
    applyHash();
    refresh();
  }
}
