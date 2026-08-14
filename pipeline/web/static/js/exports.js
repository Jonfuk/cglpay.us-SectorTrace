/* The Exports tab: write the artefacts, see what is on disk, download one.
 *
 * Downloads are plain links to /api/admin/exports/file?path=…, with the path
 * taken from the listing the server just sent. Nothing here constructs a path
 * from user input, and the server would refuse it anyway -- it serves a file
 * only if it appears in a listing it computes for itself, so a path it did not
 * produce is not found rather than rejected. See pipeline/web/artefacts.py.
 *
 * Also the overrides table, which belongs here because it is the other thing
 * in this project that is a durable artefact of someone's judgement rather
 * than a fetch: "this council publishes there, checked by this person on this
 * date".
 */
import { el } from './dom.js';

const $ = (id) => document.getElementById(id);

const state = { busy: false, poll: null };

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

function bytes(n) {
  if (!n) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function status(text, kind) {
  const node = $('export-status');
  node.textContent = text || '';
  node.className = kind === 'bad' ? 'small bad' : (kind === 'good' ? 'small good' : 'muted small');
}

function setBusy(busy) {
  state.busy = busy;
  for (const button of document.querySelectorAll('[data-export]')) button.disabled = busy;
}

// --- writing ------------------------------------------------------------------

async function startExport(target) {
  if (state.busy) return;
  setBusy(true);
  status(`writing ${target}…`);

  let job;
  try {
    job = await api('/api/admin/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target }),
    });
  } catch (e) {
    setBusy(false);
    // 409 means a module run has the slot. That is correct: an export taken
    // while the tables are being rewritten matches no moment in time.
    return status(e.message, 'bad');
  }

  clearInterval(state.poll);
  state.poll = setInterval(async () => {
    let current;
    try { current = await api(`/api/admin/jobs/${job.id}`); }
    catch (e) { clearInterval(state.poll); setBusy(false); return status(e.message, 'bad'); }
    if (current.state === 'running') return;

    clearInterval(state.poll);
    setBusy(false);
    if (current.state === 'failed') {
      status(current.error || 'export failed', 'bad');
    } else {
      const written = (current.summary || []).reduce((n, row) => n + row.count, 0);
      status(`wrote ${written} file${written === 1 ? '' : 's'}`, 'good');
    }
    loadFiles();
  }, 500);
}

// --- the files ------------------------------------------------------------------

function downloadLink(entry, label) {
  return el('a', {
    href: `/api/admin/exports/file?path=${encodeURIComponent(entry)}`,
    // Same-origin download of a file the server enumerated; the browser is
    // told it is an attachment by the response headers.
    text: label,
  });
}

/* Whether these files predate the last thing that changed the warehouse.
 *
 * The line is written to be read by someone about to send one of these files
 * to a person outside the team, so it names the runs rather than showing a
 * badge: "stale" invites a shrug, "the sheets predate two runs of
 * m01_procurement" does not. Where the job record cannot name what changed —
 * a run started from the command line leaves no row — it says that instead of
 * implying nothing happened.
 */
function stalenessLine(group, active) {
  if (!group) return null;
  // Seconds, not microseconds: these stamps come from three different writers
  // and only one of them truncates.
  const when = (stamp) => String(stamp || '')
    .replace('T', ' ').replace(/\.\d+/, '').replace('+00:00', 'Z');

  if (!group.stale) {
    return el('p', { class: 'muted small',
      text: 'Written after the last thing the pipeline collected.' });
  }

  const runs = group.since || [];
  const named = runs.length
    ? `${runs.length} job${runs.length === 1 ? '' : 's'} finished since: `
      + runs.map((r) => r.label).join(', ') + '.'
    : 'The job record does not say what changed — a run started from the '
      + 'command line leaves no row in it.';

  return el('p', { class: 'warn small' },
    el('strong', { text: 'These files predate the last collection. ' }),
    `Oldest written ${when(group.oldest_file)}; ${(active || {}).what || 'the pipeline last ran'} `
      + `${when((active || {}).at)}. ${named} `
      + 'Re-export before quoting anything from these.');
}

async function loadFiles() {
  let data;
  try { data = await api('/api/admin/exports'); }
  catch (e) { return $('export-files').replaceChildren(
    el('div', { class: 'warn', text: e.message })); }

  $('export-root').textContent = data.root;

  if (!data.exists || !data.files.length) {
    return $('export-files').replaceChildren(el('div', { class: 'empty' },
      data.exists
        ? 'Nothing exported yet.'
        : 'No export directory yet — it is created by the first export.'));
  }

  // Grouped by the directory each target writes into, which is how someone
  // thinks about them: "the sheets", "the map layers".
  const groups = new Map();
  for (const file of data.files) {
    const key = file.group || '(root)';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(file);
  }

  const staleness = new Map(
    ((data.staleness || {}).groups || []).map((g) => [g.group, g]));

  const sections = [...groups.entries()].map(([group, files]) => el('div', {},
    el('h2', {}, group,
      el('span', { class: 'muted small',
        text: ` — ${files.length} file${files.length === 1 ? '' : 's'}, `
          + bytes(files.reduce((n, f) => n + f.bytes, 0)) })),
    stalenessLine(staleness.get(group), (data.staleness || {}).pipeline_last_active),
    el('table', {},
      el('thead', {}, el('tr', {},
        el('th', { text: 'File' }), el('th', { class: 'num', text: 'Size' }),
        el('th', { text: 'Written' }), el('th', { text: 'Provenance' }))),
      el('tbody', {}, files.map((file) => el('tr', {},
        el('td', {}, downloadLink(file.path, file.name)),
        el('td', { class: 'num', text: bytes(file.bytes) }),
        el('td', { class: 'muted small' },
          el('time', { datetime: file.modified, title: file.modified,
                        text: file.modified.replace('T', ' ').replace('+00:00', 'Z') })),
        el('td', {}, file.provenance
          ? downloadLink(file.provenance, 'provenance')
          : el('span', { class: 'muted small', text: '—' }))))))));

  $('export-files').replaceChildren(
    el('div', { class: 'muted small',
      text: `${data.files.length} files, ${bytes(data.bytes)} total.` }),
    ...sections);
}

// --- overrides --------------------------------------------------------------------

async function loadOverrides() {
  let data;
  try { data = await api('/api/overrides'); }
  catch (e) { return $('override-list').replaceChildren(
    el('div', { class: 'warn', text: e.message })); }

  const rows = data.overrides || [];
  $('override-list').replaceChildren(el('table', {},
    el('thead', {}, el('tr', {},
      el('th', { text: 'Authority' }), el('th', { text: 'Base URL' }),
      el('th', { text: 'Committee URL' }), el('th', { text: 'System' }),
      el('th', { text: 'Verified by' }), el('th', { text: 'When' }))),
    el('tbody', {}, rows.length
      ? rows.map((row) => el('tr', {},
        el('td', { class: 'mono small', text: row.ons_code }),
        el('td', {}, row.base_url ? link(row.base_url) : dash()),
        el('td', {}, row.committee_url ? link(row.committee_url) : dash()),
        el('td', { class: 'muted small', text: row.committee_system || '—' }),
        el('td', { class: 'small', text: row.verified_by || '—' }),
        el('td', { class: 'muted small', text: (row.verified_at || '').slice(0, 10) })))
      : el('tr', {}, el('td', { colspan: '6', class: 'empty',
          text: 'None yet. Resolving a committee or website review item records one.' })))));
}

function dash() {
  return el('span', { class: 'muted', text: '—' });
}

/** http(s) only. A value out of the warehouse does not get to decide what a
 *  click does — the same rule app.js follows. */
function link(value) {
  const text = String(value);
  if (!/^https?:\/\//i.test(text)) return document.createTextNode(text);
  return el('a', { href: text, target: '_blank', rel: 'noopener noreferrer',
                    class: 'small', text });
}

// --- wiring -------------------------------------------------------------------------

function loadAll() {
  loadFiles();
  loadOverrides();
}

export function initExports() {
  if (!$('export-files')) return;

  for (const button of document.querySelectorAll('[data-export]')) {
    button.addEventListener('click', () => startExport(button.dataset.export));
  }

  document.addEventListener('tabshown', (event) => {
    if (event.detail.tab === 'exports') loadAll();
  });

  if ($('tab-exports').classList.contains('active')) loadAll();
}
