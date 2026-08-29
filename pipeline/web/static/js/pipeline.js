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

/* BETA-101: run-to-run comparison. A per-module diff between two runs —
 * status, rows, review items, failures, duration and freshness effect —
 * straight from the immutable ledger. Read-only; nothing here is polled,
 * because a comparison of two past runs does not change. */
const RC_CHANGE_CLASS = {
  added: 'rc-change-added', removed: 'rc-change-removed',
  regressed: 'rc-change-regressed',
};

function rcWhen(iso) {
  return (iso || '').replace('T', ' ').replace(/\..*/, '').replace('+00:00', '');
}
function rcMs(ms) {
  if (ms == null) return '—';
  if (Math.abs(ms) < 1000) return `${ms} ms`;
  const s = ms / 1000;
  return Math.abs(s) < 90 ? `${s.toFixed(1)} s` : `${(s / 60).toFixed(1)} min`;
}
function rcDelta(n, { ms = false } = {}) {
  if (n == null) return el('span', { class: 'muted small', text: '—' });
  if (n === 0) return el('span', { class: 'muted small', text: '0' });
  const text = ms ? rcMs(n) : String(n);
  return el('span', {
    class: `small ${n > 0 ? 'rc-delta-pos' : ''}`,
    text: n > 0 ? text : text.replace(/^-/, '−'),
  });
}

async function rcPopulatePickers() {
  const a = $('rc-a');
  const b = $('rc-b');
  if (!a || !b || a.dataset.filled) return;
  let data;
  try { data = await api('/api/admin/run-ledger?limit=30'); }
  catch (e) { return; }
  const runs = data.runs || [];
  const opt = (value, text) => el('option', { value, text });
  const label = (r) => `${rcWhen(r.finished_at || r.started_at)} · ${r.origin} · `
    + `${r.status}${r.dry_run ? ' · dry' : ''} · ${r.module_selector || 'all'}`;
  a.replaceChildren(opt('', 'auto — second newest run'),
    ...runs.map((r) => opt(r.run_id, label(r))));
  b.replaceChildren(opt('', 'auto — newest run'),
    ...runs.map((r) => opt(r.run_id, label(r))));
  a.dataset.filled = '1';
}

async function loadRunComparison() {
  const holder = $('run-comparison');
  if (!holder) return;
  await rcPopulatePickers();

  const a = $('rc-a')?.value || '';
  const b = $('rc-b')?.value || '';
  const query = new URLSearchParams();
  if (a) query.set('a', a);
  if (b) query.set('b', b);

  let data;
  try { data = await api(`/api/admin/run-comparison${query.toString() ? `?${query}` : ''}`); }
  catch (e) {
    holder.replaceChildren(el('p', { class: 'muted small',
      text: e.status === 404 ? (e.message || 'Need at least two recorded runs to compare.')
        : 'Comparison unavailable.' }));
    return;
  }

  const head = (r, tag) => el('div', { class: 'small' },
    el('strong', { text: `${tag}: ` }),
    el('span', { class: 'mono', text: (r.run_id || '').slice(0, 8) }),
    el('span', { text: ` ${r.origin} · ${r.status} · ${rcWhen(r.started_at)} · `
      + `${rcMs(r.duration_ms)}` }),
    r.revision ? el('span', { class: 'muted mono', text: ` ${r.revision.slice(0, 10)}` }) : null);

  const t = data.totals || {};
  const badge = (text, kind) => el('span', { class: `badge ${kind || 'type'}`, text });
  const totals = el('div', { class: 'rc-totals' },
    badge(`A→B rows +${t.rows_added || 0} / −${t.rows_removed || 0}`, 'approved'),
    t.status_regressions ? badge(`${t.status_regressions} regressed`, 'rejected') : null,
    t.status_recoveries ? badge(`${t.status_recoveries} recovered`, 'approved') : null,
    t.modules_only_in_a ? badge(`${t.modules_only_in_a} only in A`, 'muted') : null,
    t.modules_only_in_b ? badge(`${t.modules_only_in_b} only in B`, 'muted') : null,
    badge(`review Δ ${t.review_delta_total > 0 ? '+' : ''}${t.review_delta_total || 0}`, 'type'),
    badge(`failures Δ ${t.failures_delta_total > 0 ? '+' : ''}${t.failures_delta_total || 0}`, 'type'),
    badge(`duration Δ ${rcMs(t.duration_delta_ms)}`, 'type'));

  const rows = (data.modules || []).map((m) => el('tr', {},
    el('td', { class: 'mono small', text: m.module }),
    el('td', {}, el('span', {
      class: `badge ${m.change === 'unchanged' ? 'muted' : 'type'} ${RC_CHANGE_CLASS[m.change] || ''}`,
      text: m.change })),
    el('td', { class: 'small', text: `${m.status_a} → ${m.status_b}` }),
    el('td', { class: 'rc-num' }, rcDelta(m.rows_delta)),
    el('td', { class: 'rc-num' }, rcDelta(m.review_delta)),
    el('td', { class: 'rc-num' }, rcDelta(m.failures_delta)),
    el('td', { class: 'rc-num' }, rcDelta(m.elapsed_delta_ms, { ms: true })),
    el('td', { class: 'muted small', text: m.freshness_effect })));

  holder.replaceChildren(
    head(data.run_a, 'A'), head(data.run_b, 'B'),
    el('p', { class: 'muted small', text: data.note }),
    totals,
    el('table', {}, el('thead', {}, el('tr', {},
      el('th', { text: 'module' }), el('th', { text: 'change' }),
      el('th', { text: 'status A → B' }), el('th', { text: 'rows Δ' }),
      el('th', { text: 'review Δ' }), el('th', { text: 'failures Δ' }),
      el('th', { text: 'duration Δ' }), el('th', { text: 'freshness effect' }))),
      el('tbody', {}, rows.length ? rows
        : el('tr', {}, el('td', { colspan: '8', class: 'empty',
            text: 'The two runs touched no modules in common.' })))));
}

/* BETA-102: the pipeline & data-lineage graph — one typed graph over the
 * module registry, the dataset catalogue, the live foreign keys and the
 * export tab registry. Every edge is derived. Read-only, fetched once and
 * explored in the DOM (no vendored graph library, no canvas). */
const LIN_STATE = { graph: null, kinds: new Set(['source', 'module', 'table', 'export']), q: '', focus: null };
const LIN_REL_IN = {
  collected_by: 'collected by', depends_on: 'depended on by',
  writes: 'written by', references: 'referenced by', exported_by: 'reads',
};
const LIN_REL_OUT = {
  collected_by: 'feeds', depends_on: 'depends on', writes: 'writes',
  references: 'references', exported_by: 'exported by',
};

function linKindBadge(kind) {
  return el('span', { class: `badge ${kind === 'module' ? 'approved'
    : kind === 'source' ? 'type' : kind === 'export' ? 'pending' : 'muted'}`, text: kind });
}

function linRenderList() {
  const holder = $('lineage-list');
  if (!holder || !LIN_STATE.graph) return;
  const q = LIN_STATE.q.toLowerCase();
  const nodes = LIN_STATE.graph.nodes.filter((n) =>
    LIN_STATE.kinds.has(n.kind) && (!q || n.label.toLowerCase().includes(q)));
  holder.replaceChildren(el('ul', { class: 'lin-nodes' },
    ...nodes.slice(0, 400).map((n) => el('li', {
      class: n.id === LIN_STATE.focus ? 'is-focus' : '',
      onclick: () => { LIN_STATE.focus = n.id; linRenderList(); linRenderDetail(); },
    }, linKindBadge(n.kind), el('span', { class: 'mono small', text: ` ${n.label}` }),
      n.consumer_count
        ? el('span', { class: 'muted small', text: ` ·${n.consumer_count} consumer${n.consumer_count === 1 ? '' : 's'}` })
        : null)),
    nodes.length > 400 ? el('li', { class: 'muted small', text: `+${nodes.length - 400} more — narrow the search` }) : null));
}

function linRenderDetail() {
  const holder = $('lineage-detail');
  const g = LIN_STATE.graph;
  if (!holder || !g) return;
  const node = g.nodes.find((n) => n.id === LIN_STATE.focus);
  if (!node) { holder.replaceChildren(el('span', { class: 'muted small', text: 'Pick a node.' })); return; }

  const label = (id) => (g.nodes.find((n) => n.id === id) || {}).label || id.split(':').pop();
  const link = (id) => el('a', { href: '#', class: 'linklike',
    onclick: (e) => { e.preventDefault(); LIN_STATE.focus = id; linRenderList(); linRenderDetail(); } },
    label(id));

  const outs = g.edges.filter((e) => e.source === node.id);
  const ins = g.edges.filter((e) => e.target === node.id);
  const group = (edges, dir) => {
    const byRel = {};
    for (const e of edges) (byRel[e.rel] ??= []).push(dir === 'out' ? e.target : e.source);
    return Object.entries(byRel).map(([rel, ids]) => el('div', { class: 'lin-rel' },
      el('span', { class: 'lin-rel-label', text: (dir === 'out' ? LIN_REL_OUT : LIN_REL_IN)[rel] || rel }),
      el('span', {}, ...ids.map((id, i) => el('span', {}, i ? ', ' : '', link(id))))));
  };

  const facts = [];
  if (node.kind === 'module') {
    facts.push(`wave ${node.wave ?? '—'}`);
    if (node.last_run) facts.push(`last run ${node.last_run.status}${node.last_run.rows != null ? ` · ${node.last_run.rows} rows` : ''}`);
    else facts.push('never run in the ledger window');
    if (node.pending_review) facts.push(`${node.pending_review} pending review`);
    if (node.parse_failures) facts.push(`${node.parse_failures} parse failures`);
    if (node.missing_dependencies?.length) facts.push(`missing deps: ${node.missing_dependencies.join(', ')}`);
  } else if (node.kind === 'table') {
    facts.push(node.present ? `${node.rows ?? '?'} rows` : 'not in this schema');
    if (node.restricted) facts.push('restricted_ — never on the portal');
  } else if (node.kind === 'source') {
    facts.push(node.publisher);
    facts.push(`cadence: ${node.cadence}`);
    if (node.licence) facts.push(`licence: ${node.licence}`);
  } else if (node.kind === 'export') {
    facts.push(node.description);
    facts.push(`${node.columns} columns`);
  }

  holder.replaceChildren(...[
    el('div', { class: 'lin-detail-head' }, linKindBadge(node.kind),
      el('strong', { class: 'mono', text: ` ${node.label}` })),
    el('p', { class: 'muted small', text: facts.filter(Boolean).join(' · ') }),
    node.kind === 'source' && node.official_url
      ? el('p', { class: 'small' }, el('a', { href: node.official_url, target: '_blank', rel: 'noopener', text: node.official_url }))
      : null,
    ins.length ? el('div', { class: 'lin-dir' }, el('h4', { class: 'small', text: 'Upstream / consumers' }), ...group(ins, 'in')) : null,
    outs.length ? el('div', { class: 'lin-dir' }, el('h4', { class: 'small', text: 'Downstream' }), ...group(outs, 'out')) : null,
    el('p', { class: 'muted small', text: g.note }),
  ].filter(Boolean));
}

async function loadLineage() {
  const holder = $('lineage-list');
  if (!holder || LIN_STATE.graph) return;
  let data;
  try { data = await api('/api/admin/lineage'); }
  catch (e) { holder.replaceChildren(el('p', { class: 'muted small', text: 'Lineage unavailable.' })); return; }
  LIN_STATE.graph = data;

  const kindWrap = $('lin-kinds');
  if (kindWrap && !kindWrap.dataset.filled) {
    kindWrap.replaceChildren(...data.node_kinds.map((k) => {
      const box = el('input', { type: 'checkbox', checked: true,
        onchange: (e) => { e.target.checked ? LIN_STATE.kinds.add(k) : LIN_STATE.kinds.delete(k); linRenderList(); } });
      return el('label', { class: 'small' }, box, ` ${k} (${data.counts.by_kind[k] || 0})`);
    }));
    kindWrap.dataset.filled = '1';
  }
  const search = $('lin-search');
  if (search && !search.dataset.wired) {
    search.addEventListener('input', () => { LIN_STATE.q = search.value; linRenderList(); });
    search.dataset.wired = '1';
  }
  linRenderList();
  linRenderDetail();
}

/* BETA-103: parser replay sandbox. Replay a stdlib parser against one
 * archived object in memory and diff the proposed output against the stored
 * active version. Read-only — nothing is written. Runs on demand only. */
async function loadParserReplay() {
  const holder = $('parser-replay');
  const doc = $('rp-doc')?.value.trim();
  if (!holder || !doc) return;
  holder.replaceChildren(el('p', { class: 'muted small', text: 'Replaying…' }));
  let data;
  try {
    const q = new URLSearchParams({ document_id: doc });
    if ($('rp-parser').value) q.set('parser', $('rp-parser').value);
    data = await api(`/api/admin/parser-replay?${q}`);
  } catch (e) {
    holder.replaceChildren(el('p', { class: 'bad small', text: e.message || 'Replay failed.' }));
    return;
  }

  const nodes = [
    el('p', { class: 'muted small', text: data.note }),
    el('p', { class: 'small' },
      el('strong', { text: 'Stored: ' }),
      el('span', { text: `${data.stored.parser} — ${data.stored.element_count} elements, ${data.stored.table_count} tables, ${data.stored.warnings.length} warnings` })),
  ];
  if (!data.available) {
    nodes.push(el('p', { class: 'small', text: `Replay not available: ${data.reason}` }));
  } else if (data.proposed.error) {
    nodes.push(el('p', { class: 'bad small', text: `Proposed parse errored: ${data.proposed.error}` }));
  } else {
    nodes.push(
      el('p', { class: 'small' },
        el('strong', { text: 'Proposed: ' }),
        el('span', { text: `${data.parser} — ${data.proposed.element_count} elements, ${data.proposed.table_count} tables, ${data.proposed.warnings.length} warnings ` }),
        el('span', { class: `badge ${data.archive.verified ? 'approved' : 'pending'}`,
          text: data.archive.verified ? 'archive sha256 verified' : 'archive sha256 unchecked' })),
      el('p', { class: 'small',
        text: `Δ elements: +${data.diff.elements.added} / −${data.diff.elements.removed} / ~${data.diff.elements.changed}`
          + ` · tables ${data.diff.tables.stored} → ${data.diff.tables.proposed}` }),
      data.diff.text_changes.length
        ? el('table', {}, el('thead', {}, el('tr', {},
            el('th', { text: 'seq' }), el('th', { text: 'kind' }),
            el('th', { text: 'stored' }), el('th', { text: 'proposed' }))),
            el('tbody', {}, ...data.diff.text_changes.slice(0, 60).map((t) => el('tr', {},
              el('td', { class: 'mono small', text: String(t.sequence) }),
              el('td', { class: 'small', text: t.kind }),
              el('td', { class: 'small', text: (t.stored || '').slice(0, 120) }),
              el('td', { class: 'small', text: (t.proposed || '').slice(0, 120) })))))
        : el('p', { class: 'muted small', text: 'No element text differs.' }));
  }
  holder.replaceChildren(...nodes);
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

  for (const id of ['rc-a', 'rc-b']) {
    $(id)?.addEventListener('change', loadRunComparison);
  }
  // BETA-102: fetch the lineage graph the first time its panel is opened.
  $('lineage-panel')?.addEventListener('toggle', (event) => {
    if (event.target.open) loadLineage();
  });
  // BETA-103: parser replay runs only when the button is pressed.
  $('rp-run')?.addEventListener('click', loadParserReplay);

  document.addEventListener('tabshown', (event) => {
    if (event.detail.tab !== 'pipeline') return;
    loadModules();
    loadHistory();
    loadMissionControl();
    loadRunComparison();
    if ($('lineage-panel')?.open) loadLineage();
  });

  // app.js is a classic script and has already routed the opening hash by the
  // time this module -- deferred, like every module -- runs, so the first
  // 'tabshown' for the tab we are on has been and gone. Opening straight to
  // #pipeline has to work.
  if ($('tab-pipeline').classList.contains('active')) {
    loadModules();
    loadMissionControl();
    loadRunComparison();
  }

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
