/* The Census tab: 68 parsed figures, and the pages they were read off.
 *
 * This screen replaces a generated markdown worklist. That worklist paired
 * each parsed value with the line it came from and then printed one SQL
 * statement — `UPDATE workforce_census_metrics SET verified = 1 WHERE
 * census_year = 2023` — which set twenty flags at once, attributed to nobody,
 * with no record that any page had been read. Migration 0033 refuses that
 * statement now. This is what it refuses it in favour of.
 *
 * Two things shape the layout, and both are the check itself rather than
 * decoration:
 *
 *   * **The page is on screen, not linked.** m06 archived the extracted text
 *     of every page it read and nothing had ever displayed it. The line a
 *     value was parsed from can look perfectly good and still be a sentence
 *     about a different year; only the page around it says which. Expanding a
 *     page is what makes its figures verifiable here — the census equivalent
 *     of the Candidates tab requiring the document to be opened, and for the
 *     same reason: the act being recorded is that somebody looked.
 *
 *   * **Verifying is per figure; rejecting is bulk.** A wrong parse is visible
 *     from the line, and the cost of being wrong about a rejection is a figure
 *     that stays unchecked. A wrong verification is a number published under
 *     somebody's name.
 *
 * Nothing here fetches anything from the open web, unlike promotion. The
 * bytes were fetched, hashed and archived by m06; a verification is a
 * statement about them, which is why the audit rows carry
 * `checked_against_sha256` rather than a hash of their own.
 */
import { el } from './dom.js';

const $ = (id) => document.getElementById(id);

const state = {
  year: '',
  status: 'unchecked',
  offset: 0,
  items: [],
  selected: new Set(),
  // Pages expanded in this session, as `${year}/${page}`. Deliberately not
  // persisted, the same call candidates.js makes: "I have read this page" is a
  // claim about the person at the keyboard now, not about last week.
  opened: new Set(),
  // key -> note input, so a batch reads each row's own note.
  notes: new Map(),
  // `${year}/${page}` -> the fetched page payload, so re-expanding is free.
  pages: new Map(),
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
  const node = $('census-status');
  if (!node) return;
  node.textContent = text || '';
  node.className = kind === 'bad' ? 'small bad' : (kind === 'good' ? 'small good' : 'muted small');
}

function reviewerName() {
  const field = document.getElementById('reviewer');
  return field ? field.value.trim() : '';
}

function pageId(item) {
  return `${item.census_year}/${item.source_page}`;
}

// --- the counts strip ---------------------------------------------------------

async function loadCounts() {
  let data;
  try { data = await api('/api/admin/census/counts'); }
  catch (e) { return status(e.message, 'bad'); }

  const pill = $('census-pill');
  if (pill) {
    pill.textContent = String(data.unchecked);
    pill.hidden = data.unchecked === 0;
  }

  $('census-counts').replaceChildren(...data.years.map((year) =>
    el('button', {
      class: String(year.census_year) === String(state.year) ? 'chip active' : 'chip',
      onclick: () => {
        state.year = String(year.census_year) === String(state.year)
          ? '' : String(year.census_year);
        state.offset = 0;
        refresh();
      },
    },
      el('strong', { text: `Census ${year.census_year}` }),
      el('span', { class: 'muted small', text: ` ${year.unchecked} unchecked` }),
      el('span', { class: 'muted small', text: ` · ${year.verified} verified` }),
      el('span', { class: 'muted small', text: ` · ${year.rejected} rejected` }),
    )));

  renderStale(data.stale || []);
  renderHistory(data.decisions || []);
}

/* Figures whose source has moved under a verification that vouched for it.
 *
 * Loud rather than tucked away, because the failure mode is silent by nature:
 * a re-parse or a reissued PDF leaves the flag saying "checked" over a number
 * nobody checked, and the portal publishes it as verified. */
function renderStale(rows) {
  const box = $('census-stale');
  if (!rows.length) {
    box.hidden = true;
    box.replaceChildren();
    return;
  }
  box.hidden = false;
  box.replaceChildren(
    el('p', { class: 'small bad' },
      rows.length === 1
        ? '1 verified figure no longer matches what was checked:'
        : `${rows.length} verified figures no longer match what was checked:`),
    el('ul', { class: 'small' }, ...rows.map((row) => el('li', {},
      el('span', { text: `${row.census_year} ${row.metric}/${row.workforce_segment} — ` }),
      el('span', { class: 'muted', text: row.why.join('; ') }),
      el('span', { text: ' ' }),
      el('button', {
        class: 'btn ghost', text: 'Reset',
        onclick: () => resetOne(row.key),
      })))),
    el('p', { class: 'muted small', text:
      'A verification is a statement about the bytes it was taken against. '
      + 'Reset these and check them again rather than leaving the flag up.' }));
}

function renderHistory(rows) {
  const history = $('census-history');
  if (!rows.length) {
    history.replaceChildren(el('p', {
      class: 'muted small',
      text: 'Nothing checked yet. Every decision is recorded here with who made it.',
    }));
    return;
  }
  history.replaceChildren(el('table', {},
    el('thead', {}, el('tr', {},
      el('th', { text: 'When' }), el('th', { text: 'Who' }),
      el('th', { text: 'Decision' }), el('th', { text: 'Figure' }),
      el('th', { text: 'Note' }))),
    el('tbody', {}, ...rows.map((row) => el('tr', {},
      el('td', { class: 'small', text: row.decided_at }),
      el('td', { class: 'small', text: row.decided_by }),
      el('td', { class: 'small', text: row.decision }),
      el('td', { class: 'small', text:
        `${row.census_year} ${row.metric}/${row.workforce_segment} `
        + `= ${row.checked_value ?? '—'} ${row.checked_unit || ''}` }),
      el('td', { class: 'small muted', text: row.note || '' }))))));
}

// --- the worklist -------------------------------------------------------------

async function loadList() {
  const params = new URLSearchParams({
    status: state.status, offset: String(state.offset),
  });
  if (state.year) params.set('year', state.year);

  let data;
  try { data = await api(`/api/admin/census?${params}`); }
  catch (e) { return status(e.message, 'bad'); }

  state.items = data.items;
  state.selected.clear();
  // The inputs these point at are about to be replaced. `opened` survives: it
  // records which pages a person read, which paging away from does not undo.
  state.notes.clear();
  render(data);
}

function render(data) {
  const list = $('census-list');
  updateBulk();
  if (!data.items.length) {
    list.replaceChildren(el('p', { class: 'muted', text: 'Nothing here.' }));
    $('census-pager').replaceChildren();
    return;
  }

  list.replaceChildren(...data.items.map(renderItem));

  const shown = data.offset + data.items.length;
  $('census-pager').replaceChildren(
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
  const check = el('input', {
    type: 'checkbox',
    onchange: (event) => {
      if (event.target.checked) state.selected.add(item.key);
      else state.selected.delete(item.key);
      updateBulk();
    },
  });

  const decided = item.verified ? 'verified' : (item.rejected ? 'rejected' : null);

  const readPill = el('span', { class: 'pill opened', text: 'page read' });
  readPill.hidden = !state.opened.has(pageId(item));

  const value = item.value === null || item.value === undefined
    ? '—' : `${item.value}${item.unit === 'percent' ? '%' : ` ${item.unit || ''}`}`;

  const pageBox = el('div', { class: 'pagetext' });
  pageBox.hidden = true;

  const note = el('input', { type: 'text', placeholder: 'note (optional)' });
  state.notes.set(item.key, note);

  const row = el('div', { class: 'candidate' },
    el('div', { class: 'row' },
      check,
      el('strong', { text: `${item.metric} · ${item.workforce_segment}` }),
      el('span', { class: 'value', text: value }),
      el('span', { class: 'spacer' }),
      readPill,
      decided ? el('span', { class: 'pill', text: decided }) : null,
      el('span', { class: 'muted small', text: `census ${item.census_year}` }),
    ),
    // The line the number was parsed from, verbatim and never truncated. The
    // markdown worklist cut it at 240 characters, which is exactly where a
    // parse that had swallowed a neighbouring sentence stopped being visible.
    el('blockquote', { class: 'small rawline', text: item.raw_text }),
    el('div', { class: 'row' },
      el('button', {
        class: 'btn', text: `Read page ${item.source_page}`,
        title: 'The archived text of the page this figure was read from',
        onclick: (event) => togglePage(item, pageBox, event.target),
      }),
      el('span', { class: 'muted small', text:
        `${item.source.payload_sha256 ? item.source.payload_sha256.slice(0, 12) + '…' : 'no hash'} `
        + `· retrieved ${item.source.retrieved_at || 'unknown'}` }),
      el('span', { class: 'spacer' }),
      el('a', { href: item.source.source_url || '#', target: '_blank',
                 rel: 'noopener noreferrer', class: 'small mono',
                 text: 'source PDF' }),
    ),
    pageBox,
    ...(item.decisions.length
      ? [el('div', { class: 'row wrap' }, ...item.decisions.map((d) => el('span', {
          class: 'muted small',
          text: `${d.decision} by ${d.decided_by} at ${d.decided_at}`
                 + (d.note ? ` — ${d.note}` : ''),
        })))]
      : []),
    decided
      ? el('div', { class: 'row' }, el('button', {
          class: 'btn', text: 'Reset',
          onclick: () => resetOne(item.key),
        }))
      : el('div', { class: 'row wrap' },
          note,
          el('button', {
            class: 'btn primary', text: 'Verify',
            onclick: (event) => verifyOne(item, note.value, event.target),
          }),
          el('button', {
            class: 'btn', text: 'Reject',
            onclick: () => rejectMany([item.key], note.value),
          })));

  row.dataset.key = item.key;
  return row;
}

// --- the page a figure is checked against -------------------------------------

async function togglePage(item, box, button) {
  if (!box.hidden) {
    box.hidden = true;
    button.textContent = `Read page ${item.source_page}`;
    return;
  }

  const id = pageId(item);
  if (!state.pages.has(id)) {
    button.disabled = true;
    try {
      state.pages.set(id, await api(
        `/api/admin/census/page?year=${item.census_year}&page=${item.source_page}`));
    } catch (e) {
      button.disabled = false;
      return status(e.message, 'bad');
    }
    button.disabled = false;
  }

  const page = state.pages.get(id);
  box.replaceChildren(
    // `source_page` is a zero-based index into the extracted pages, which is
    // what m06 stored and what every existing figure carries. Said out loud
    // rather than quietly incremented here: a screen that renumbered for
    // display would disagree with the database, the exports and the portal.
    el('p', { class: 'muted small', text:
      `Archived text of extracted page ${page.page_number} `
      + `(page ${page.page_number + 1} in a PDF viewer, which counts from 1). `
      + `${page.metrics_on_page.length} figure`
      + `${page.metrics_on_page.length === 1 ? '' : 's'} were read off it.` }),
    el('pre', { class: 'small', text: page.page_text }));
  box.hidden = false;
  button.textContent = 'Hide page';

  markRead(id);
}

function markRead(id) {
  if (state.opened.has(id)) return;
  state.opened.add(id);
  // Every figure from this page becomes verifiable, not just the one whose
  // button was clicked — one page is read once and carries several figures,
  // which is why the worklist is ordered by page.
  for (const item of state.items) {
    if (pageId(item) !== id) continue;
    const row = rowFor(item.key);
    const pill = row && row.querySelector('.pill.opened');
    if (pill) pill.hidden = false;
  }
  updateBulk();
}

function rowFor(key) {
  return [...document.querySelectorAll('#census-list .candidate')]
    .find((node) => node.dataset.key === key) || null;
}

// --- what a batch may touch ---------------------------------------------------

function partitionSelection() {
  const ready = [];
  const blocked = [];
  for (const key of state.selected) {
    const item = state.items.find((row) => row.key === key);
    if (!item) continue;
    if (item.verified) blocked.push({ item, why: 'already verified' });
    else if (item.rejected) blocked.push({ item, why: 'rejected as a bad parse' });
    else if (!state.opened.has(pageId(item))) {
      blocked.push({ item, why: `page ${item.source_page} not read in this session` });
    } else ready.push(item);
  }
  return { ready, blocked };
}

function updateBulk() {
  const count = state.selected.size;
  const { ready, blocked } = partitionSelection();

  const reject = $('census-reject-selected');
  reject.disabled = count === 0 || state.busy;
  reject.textContent = count ? `Reject ${count} selected` : 'Reject selected';

  const verify = $('census-verify-read');
  verify.disabled = ready.length === 0 || state.busy;
  verify.textContent = ready.length
    ? `Verify ${ready.length} read` : 'Verify read';

  const note = $('census-batch');
  if (!blocked.length) {
    note.hidden = true;
    note.replaceChildren();
    return;
  }
  note.hidden = false;
  note.replaceChildren(
    el('p', { class: 'muted small' },
      `${blocked.length} selected figure${blocked.length === 1 ? '' : 's'} `
      + 'cannot be verified in a batch:'),
    el('ul', { class: 'small' }, ...blocked.map(({ item, why }) => el('li', {},
      el('span', { text: `${item.metric}/${item.workforce_segment}` }),
      el('span', { class: 'muted', text: ` — ${why}` })))),
    el('p', { class: 'muted small', text:
      'Read a page to make its figures verifiable. Nothing here verifies a '
      + 'figure off a page nobody has looked at.' }));
}

// --- deciding -----------------------------------------------------------------

async function verifyOne(item, note, button) {
  const who = reviewerName();
  if (!who) {
    status('Put your name in the reviewer box first — verifications are attributed.', 'bad');
    return;
  }
  if (!state.opened.has(pageId(item))) {
    status(`Read page ${item.source_page} first — a figure is verified against `
            + 'its page, not against its own parsed line.', 'bad');
    return;
  }

  button.disabled = true;
  try {
    await api('/api/admin/census/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: item.key, verified_by: who, note: note || null }),
    });
    status(`verified ${item.metric}/${item.workforce_segment}`, 'good');
  } catch (e) {
    button.disabled = false;
    return status(e.message, 'bad');
  }
  await Promise.all([loadCounts(), loadList()]);
}

/* Verify every read figure in the selection, one request at a time.
 *
 * Sequential like the candidate batch, though nothing here is fetched: what it
 * buys is that a failure stops that figure and nothing else, and that the
 * progress line is honest about where it got to. */
async function verifyRead() {
  const who = reviewerName();
  if (!who) {
    status('Put your name in the reviewer box first — verifications are attributed.', 'bad');
    return;
  }

  const { ready } = partitionSelection();
  if (!ready.length) return;
  if (!confirm(`Verify ${ready.length} figure${ready.length === 1 ? '' : 's'} `
                + 'read from their pages? Each one is recorded under your name.')) return;

  state.busy = true;
  updateBulk();

  const done = [];
  const failed = [];
  for (const [index, item] of ready.entries()) {
    const note = state.notes.get(item.key);
    const row = rowFor(item.key);
    if (row) row.classList.add('working');
    status(`${index + 1} of ${ready.length} — ${item.metric}/${item.workforce_segment}…`);
    try {
      await api('/api/admin/census/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          key: item.key, verified_by: who,
          note: note && note.value ? note.value : null,
        }),
      });
      done.push(item);
    } catch (e) {
      failed.push({ item, why: e.message });
    } finally {
      if (row) row.classList.remove('working');
    }
  }

  state.busy = false;
  status(`verified ${done.length} of ${ready.length}`, failed.length ? 'bad' : 'good');
  renderBatchResult(done, failed);
  await Promise.all([loadCounts(), loadList()]);
}

function renderBatchResult(done, failed) {
  const note = $('census-result');
  note.hidden = false;
  note.replaceChildren(
    el('p', { class: failed.length ? 'small bad' : 'small good' },
      `Verified ${done.length}. Failed ${failed.length}.`),
    ...(failed.length
      ? [el('ul', { class: 'small' }, ...failed.map(({ item, why }) => el('li', {},
          el('span', { text: `${item.metric}/${item.workforce_segment}` }),
          el('span', { class: 'muted', text: ` — ${why}` }))))]
      : []),
    el('button', {
      class: 'btn ghost', text: 'Dismiss',
      onclick: () => { note.hidden = true; note.replaceChildren(); },
    }));
}

async function rejectMany(keys, note) {
  const who = reviewerName();
  if (!who) {
    status('Put your name in the reviewer box first — rejections are attributed.', 'bad');
    return;
  }
  try {
    const result = await api('/api/admin/census/reject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keys, rejected_by: who, note: note || null }),
    });
    status(`rejected ${result.rejected} — filed against the parser too`, 'good');
  } catch (e) { return status(e.message, 'bad'); }
  await Promise.all([loadCounts(), loadList()]);
}

async function resetOne(key) {
  try {
    await api('/api/admin/census/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key }),
    });
  } catch (e) { return status(e.message, 'bad'); }
  await Promise.all([loadCounts(), loadList()]);
}

// --- wiring -------------------------------------------------------------------

function refresh() {
  loadCounts();
  loadList();
}

export function initCensus() {
  const panel = $('tab-census');
  if (!panel) return;

  $('census-status-filter').addEventListener('change', (event) => {
    state.status = event.target.value;
    state.offset = 0;
    loadList();
  });

  $('census-reject-selected').addEventListener('click', () => {
    if (state.selected.size) rejectMany([...state.selected], null);
  });
  $('census-verify-read').addEventListener('click', verifyRead);

  // The counts alone run on load, because they fill the tab-strip pill, and a
  // count nobody can see until they open the tab is not a count.
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
