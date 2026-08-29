/* The Pipeline tab: what can be run, running it, and watching it happen.
 *
 * The thing this replaces is a terminal. That sets the bar -- if it shows less
 * than `pipeline run` shows, it is worse than the thing it replaces -- and it
 * also sets the honesty requirement: a run started here fetches from live
 * public sources under this project's contact email, and the page says so
 * rather than making it feel like clicking a button in an app.
 *
 * Polling, not server-sent events. A run is minutes to hours, the payload is a
 * handful of lines, and polling survives a closed laptop lid, a proxy, and a
 * server restart in a way a held-open connection does not. `after` is a line
 * index rather than a count, so the buffer dropping its oldest lines during a
 * long run cannot silently skip anything.
 */
import { el, store } from './dom.js';

const POLL_MS = 1_000;
const HISTORY_MS = 15_000;
// The log pane holds a window on the job, not the whole of it: the job keeps
// its own buffer server-side, and thousands of DOM lines make the tab crawl.
const MAX_LOG_NODES = 1_500;

const state = {
  following: null,     // job id being tailed
  next: -1,            // last line index received
  timer: null,
  historyTimer: null,
  modules: [],
  busy: false,         // a run is in progress, from this tab or another
  pinned: true,        // log scrolled to the bottom
};

const $ = (id) => document.getElementById(id);

async function api(path, options) {
  const response = await fetch(path, options);
  let payload = null;
  try { payload = await response.json(); } catch (e) { /* not JSON */ }
  if (!response.ok) {
    const error = new Error((payload && payload.error)
      || `${response.status} ${response.statusText}`);
    error.status = response.status;
    error.payload = payload || {};
    throw error;
  }
  return payload;
}

function status(text, kind) {
  const node = $('run-status');
  if (!node) return;
  node.textContent = text || '';
  node.className = kind === 'bad' ? 'small bad' : (kind === 'good' ? 'small good' : 'muted small');
}

// --- the module list ------------------------------------------------------------

function runArgs() {
  const since = $('run-since').value.trim();
  const limit = $('run-limit').value.trim();
  const jobs = $('run-jobs').value.trim();
  const args = {};
  if (since) args.since = since;
  if (limit) args.limit = Number(limit);
  if (jobs) args.jobs = Number(jobs);
  return args;
}

function renderModules() {
  const rows = state.modules.map((module) => {
    const warnings = [];
    if (module.missing_dependencies.length) {
      warnings.push(`runs before ${module.missing_dependencies.join(', ')} — `
        + 'it will use whatever they left behind');
    }
    if ($('run-since').value.trim() && !module.supports_since) {
      warnings.push('ignores "since" and will process its whole source');
    }

    return el('tr', {},
      el('td', {},
        el('div', { class: 'mono', text: module.name }),
        warnings.length
          ? el('div', { class: 'small bad', text: warnings.join('; ') })
          : (module.depends_note
            ? el('div', { class: 'muted small', text: module.depends_note })
            : null)),
      el('td', { class: 'muted small' },
        module.wave ? `wave ${module.wave}` : '—',
        module.depends_on.length
          ? el('div', { class: 'muted small', text: `after ${module.depends_on.join(', ')}` })
          : null),
      el('td', { class: 'muted small' },
        module.cursor_value
          ? el('span', { title: `updated ${module.cursor_updated_at || 'unknown'}`,
                          text: module.cursor_value })
          : 'never run'),
      el('td', { class: 'num' },
        module.pending_review
          ? el('span', { class: 'badge pending', text: String(module.pending_review) })
          : el('span', { class: 'muted', text: '0' })),
      el('td', { class: 'num' },
        module.parse_failures
          ? el('span', { class: 'badge rejected', text: String(module.parse_failures) })
          : el('span', { class: 'muted', text: '0' })),
      el('td', { class: 'act' },
        el('button', {
          class: 'btn', title: 'Fetch and parse, then roll it all back',
          disabled: state.busy,
          onclick: () => start({ module: module.name, dry_run: true, ...runArgs() }),
        }, 'Dry'),
        ' ',
        el('button', {
          class: 'btn primary', title: `Run ${module.name} now`,
          disabled: state.busy,
          onclick: () => start({ module: module.name, ...runArgs() }),
        }, 'Run')));
  });

  const table = el('table', {},
    el('thead', {}, el('tr', {},
      el('th', { text: 'Module' }), el('th', { text: 'Order' }),
      el('th', { text: 'Cursor' }), el('th', { class: 'num', text: 'Queue' }),
      el('th', { class: 'num', text: 'Failures' }), el('th', { text: '' }))),
    el('tbody', {}, rows.length ? rows
      : el('tr', {}, el('td', { colspan: '6', class: 'empty', text: 'No modules registered.' }))));

  $('module-list').replaceChildren(table);
  for (const button of document.querySelectorAll('#run-all, #dry-all')) {
    button.disabled = state.busy;
  }
}

async function loadModules() {
  try {
    const data = await api('/api/admin/modules');
    state.modules = data.modules;
  } catch (e) {
    return status(e.message, 'bad');
  }
  renderModules();
}

// --- starting a run --------------------------------------------------------------

async function start(body) {
  if (state.busy) return status('Something is already running.', 'bad');

  if (body.module === 'all' && !body.dry_run) {
    const count = state.modules.length;
    if (!window.confirm(
      `Run all ${count} modules against live public sources?\n\n`
      + 'This is a full crawl and takes hours. Dry run first if you only want '
      + 'to see what it would fetch.')) return;
  }

  status('starting…');
  let job;
  try {
    job = await api('/api/admin/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (e) {
    if (e.status === 409 && e.payload.job_id) {
      status(e.message, 'bad');
      follow(e.payload.job_id);
      return;
    }
    return status(e.message, 'bad');
  }

  status('');
  clearLog();
  adopt(job);
  loadHistory();
}

// --- following a job ---------------------------------------------------------------

function clearLog() {
  $('job-log').replaceChildren();
  state.next = -1;
  state.pinned = true;
}

function follow(jobId) {
  if (state.following === jobId) return;
  state.following = jobId;
  clearLog();
  tick();
}

/** Take the payload a run/poll returned and put it on the page. */
function adopt(job) {
  state.following = job.id;
  state.busy = job.running;
  setPill(job);

  $('job-label').textContent = `#${job.id} · ${job.label}`;
  const bits = [job.state];
  if (job.args && job.args.since) bits.push(`since ${job.args.since}`);
  if (job.args && job.args.limit) bits.push(`limit ${job.args.limit}`);
  if (job.args && job.args.jobs > 1) bits.push(`${job.args.jobs} at once`);
  bits.push(`started ${job.started_at.replace('T', ' ').replace('+00:00', 'Z')}`);
  if (job.dropped) bits.push(`${job.dropped} earlier lines dropped`);

  const failed = (job.summary || []).filter((row) => row.status === 'failed').length;
  if (failed) bits.push(`${failed} module${failed === 1 ? '' : 's'} failed`);

  const meta = [el('span', { class: failed ? 'small bad' : null, text: bits.join(' · ') })];
  if (job.summary) meta.push(summaryTable(job.summary));
  if (job.error) meta.push(el('div', { class: 'small bad', text: job.error }));
  $('job-meta').replaceChildren(...meta);

  appendLines(job.log || []);
  if (typeof job.next === 'number' && job.next > state.next) state.next = job.next;

  renderModules();
  if (!job.running) {
    stopPolling();
    // The counts and cursors the module list shows are exactly what a run
    // changes, so they are stale the moment one finishes.
    loadModules();
    loadHistory();
  } else {
    startPolling();
  }
}

function summaryTable(rows) {
  return el('table', { class: 'summary' },
    el('thead', {}, el('tr', {},
      el('th', { text: 'Module' }), el('th', { text: '' }),
      el('th', { class: 'num', text: 'Seconds' }), el('th', { class: 'num', text: 'Rows' }),
      el('th', { class: 'num', text: 'Queue' }), el('th', { class: 'num', text: 'Failures' }))),
    el('tbody', {}, rows.map((row) => el('tr', {},
      el('td', { class: 'mono', text: row.module }),
      el('td', {}, el('span', {
        class: `badge ${row.status === 'ok' ? 'approved' : 'rejected'}`,
        title: row.error || '', text: row.status })),
      el('td', { class: 'num', text: (row.elapsed || 0).toFixed(1) }),
      el('td', { class: 'num', text: String(row.rows ?? '—') }),
      el('td', { class: 'num', text: String(row.review ?? '—') }),
      el('td', { class: 'num', text: String(row.failures ?? '—') })))));
}

function appendLines(lines) {
  if (!lines.length) return;
  const pane = $('job-log');
  // Whether to keep the pane pinned is decided before it grows, or every
  // append scrolls away from whatever someone had scrolled back to read.
  state.pinned = pane.scrollTop + pane.clientHeight >= pane.scrollHeight - 24;

  pane.append(...lines.map((line) => el('div', {
    class: `logline ${line.level}`,
    title: line.at,
  }, line.text)));

  while (pane.childElementCount > MAX_LOG_NODES) pane.firstElementChild.remove();
  if (state.pinned) pane.scrollTop = pane.scrollHeight;
}

function setPill(job) {
  const pill = $('job-pill');
  if (!pill) return;
  pill.hidden = !job || !job.running;
  if (job && job.running) pill.textContent = 'running';
}

async function tick() {
  if (!state.following) return;
  try {
    adopt(await api(`/api/admin/jobs/${state.following}?after=${state.next}`));
  } catch (e) {
    // A job that has gone (server restarted) stops being followed rather than
    // repeating the error once a second for the rest of the session.
    stopPolling();
    state.following = null;
    state.busy = false;
    setPill(null);
    status(e.message, 'bad');
  }
}

function startPolling() {
  if (state.timer) return;
  state.timer = setInterval(tick, POLL_MS);
}

function stopPolling() {
  clearInterval(state.timer);
  state.timer = null;
}

// --- history -----------------------------------------------------------------------

/** A job's label, plus how many of its modules failed. */
function failedNote(job) {
  const failed = (job.summary || []).filter((row) => row.status === 'failed');
  if (!failed.length) return document.createTextNode(job.label);
  return el('span', {},
    job.label, ' ',
    el('span', {
      class: 'small bad',
      title: failed.map((row) => `${row.module}: ${row.error || 'failed'}`).join('\n'),
      text: `${failed.length} module${failed.length === 1 ? '' : 's'} failed`,
    }));
}

async function loadHistory() {
  let data;
  try { data = await api('/api/admin/jobs'); }
  catch (e) { return; }

  // Another tab, or a previous session of this one, may have started it.
  if (data.running && data.running !== state.following) follow(data.running);
  if (!data.running) {
    state.busy = false;
    setPill(null);
  }

  const rows = data.jobs.slice(0, 12).map((job) => el('tr', {
    class: 'clickable',
    onclick: () => { follow(job.id); },
  },
    el('td', { class: 'muted', text: `#${job.id}` }),
    el('td', {}, el('span', {
      class: `badge ${job.state === 'failed' ? 'rejected'
        : (job.running ? 'pending' : 'approved')}`,
      text: job.state })),
    // "finished" is true of the job even when every module in it failed, which
    // reads as success at a glance. The count is what someone is scanning for.
    el('td', {}, failedNote(job)),
    el('td', { class: 'muted small', text: (job.finished_at || job.started_at)
      .replace('T', ' ').replace('+00:00', 'Z') })));

  $('job-history').replaceChildren(el('table', {}, el('tbody', {},
    rows.length ? rows
      : el('tr', {}, el('td', { colspan: '4', class: 'empty', text: 'Nothing run yet.' })))));

  loadRunLedger();
}

/* BETA-082: mission control — one read model over the module registry, the
 * active job and the run ledger. Dependency waves, each module's last-run
 * status, and a failure summary. Read-only; polled like the rest. */
async function loadMissionControl() {
  const holder = $('mission-control');
  if (!holder) return;
  let data;
  try { data = await api('/api/admin/mission-control'); }
  catch (e) { return; }

  const dot = (module) => {
    const status = module.last_run?.status
      || (module.name && data.never_run.includes(module.name) ? 'never' : 'idle');
    const cls = status === 'ok' ? 'approved'
      : status === 'failed' ? 'rejected'
      : status === 'never' ? 'muted' : 'pending';
    return el('span', { class: `badge ${cls}`, title: status, text: status });
  };

  const waveBlocks = (data.waves || []).map((wave) => el('div', { class: 'mc-wave' },
    el('h3', { class: 'small', text: `Wave ${wave.wave || '—'}` }),
    el('ul', { class: 'mc-modules' },
      ...wave.modules.map((module) => el('li', {},
        dot(module),
        el('span', { class: 'mono small', text: ` ${module.name}` }),
        module.missing_dependencies?.length
          ? el('span', { class: 'badge rejected', title: 'missing dependencies', text: 'deps' })
          : null,
        module.parse_failures
          ? el('span', { class: 'badge pending', title: 'parse failures', text: `${module.parse_failures} fail` })
          : null,
        module.pending_review
          ? el('span', { class: 'badge type', title: 'pending review', text: `${module.pending_review} review` })
          : null)))));

  const failRows = (data.failure_summary || []).map((f) => el('tr', {},
    el('td', { class: 'mono small', text: f.module }),
    el('td', { class: 'small', text: String(f.parse_failures || 0) }),
    el('td', { class: 'small', text: String(f.pending_review || 0) }),
    el('td', { class: 'small', text: f.last_status || '—' })));

  const active = data.active;
  holder.replaceChildren(
    el('p', { class: 'muted small', text: data.note }),
    el('div', { class: 'mc-status' },
      el('span', { class: `badge ${active ? 'pending' : 'muted'}`,
        text: active ? `running: ${active.label || active.kind}` : 'no active run' }),
      data.last_run
        ? el('span', { class: 'muted small',
            text: `last run ${data.last_run.origin} · ${data.last_run.status}` })
        : null),
    el('div', { class: 'mc-waves' }, ...waveBlocks),
    failRows.length
      ? el('div', {}, el('h3', { class: 'small', text: 'Needs attention' }),
          el('table', {}, el('thead', {}, el('tr', {},
            el('th', { text: 'module' }), el('th', { text: 'parse fails' }),
            el('th', { text: 'review' }), el('th', { text: 'last status' }))),
            el('tbody', {}, ...failRows)))
      : el('p', { class: 'muted small', text: 'No modules need attention.' }));
}

/* BETA-058: the durable run ledger — every module-run, whatever started it. */
async function loadRunLedger() {
  const holder = $('run-ledger');
  if (!holder) return;
  let data;
  try { data = await api('/api/admin/run-ledger'); }
  catch (e) { return; }

  const when = (iso) => (iso || '').replace('T', ' ').replace(/\.\d+/, '').replace('+00:00', 'Z');
  const rows = (data.runs || []).map((r) => {
    const modules = r.status === 'running' ? `${r.modules_total ?? '?'} queued`
      : `${r.modules_ok ?? 0} ok${r.modules_failed ? ` / ${r.modules_failed} failed` : ''}`;
    return el('tr', {},
      el('td', {}, el('span', { class: 'badge type', text: r.origin })),
      el('td', {}, el('span', {
        class: `badge ${r.status === 'failed' ? 'rejected'
          : (r.status === 'running' ? 'pending' : 'approved')}`,
        text: r.status + (r.dry_run ? ' · dry' : '') })),
      el('td', { class: 'muted small', text: r.module_selector || '' }),
      el('td', { class: 'small', text: modules }),
      el('td', { class: 'muted small mono',
        title: r.revision || '', text: (r.revision || '').slice(0, 10) }),
      el('td', { class: 'muted small', text: when(r.finished_at || r.started_at) }));
  });

  holder.replaceChildren(el('table', {}, el('tbody', {},
    rows.length ? rows
      : el('tr', {}, el('td', { colspan: '6', class: 'empty',
          text: 'No runs recorded yet — the ledger starts at the next run.' })))));
}

// --- wiring --------------------------------------------------------------------------

export function initPipeline() {
  if (!$('module-list')) return;

  $('run-all').addEventListener('click', () => start({ module: 'all', ...runArgs() }));
  $('dry-all').addEventListener('click', () =>
    start({ module: 'all', dry_run: true, ...runArgs() }));

  // The "ignores since" warnings on the module list depend on this field.
  $('run-since').addEventListener('change', renderModules);

  for (const id of ['run-since', 'run-limit', 'run-jobs']) {
    const key = `cglpay.${id}`;
    $(id).value = store.get(key, $(id).value);
    $(id).addEventListener('change', () => store.set(key, $(id).value));
  }

  document.addEventListener('tabshown', (event) => {
    if (event.detail.tab !== 'pipeline') return;
    loadModules();
    loadHistory();
    loadMissionControl();
  });

  // app.js is a classic script and has already routed the opening hash by the
  // time this module -- deferred, like every module -- runs, so the first
  // 'tabshown' for the tab we are on has been and gone. Opening straight to
  // #pipeline has to work.
  if ($('tab-pipeline').classList.contains('active')) { loadModules(); loadMissionControl(); }

  // Once at load, whatever tab is showing: a run may already be going, and the
  // pill in the tab strip is how you find out without looking for it.
  loadHistory();
  state.historyTimer = setInterval(() => {
    if (state.busy || document.getElementById('tab-pipeline').classList.contains('active')) {
      loadHistory();
      if (document.getElementById('tab-pipeline').classList.contains('active')) loadMissionControl();
    }
  }, HISTORY_MS);
}
