const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const get = async path => { const response = await fetch(path); if (!response.ok) throw new Error(await response.text()); return response.json(); };
const post = async (path, body = {}) => { const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}); if (!response.ok) throw new Error(await response.text()); return response.json(); };
const row = value => `<div class="small">${esc(value)}</div>`;
const money = micros => micros == null ? '—' : `£${(Number(micros || 0) / 1000000).toFixed(4)}`;
const time = value => value ? new Date(value).toLocaleString('en-GB', {dateStyle: 'medium', timeStyle: 'short'}) : '—';
const terminal = new Set(['cancelled', 'complete', 'failed', 'interrupted']);
let pollHandle = null;

function selectedDomains() {
  return [...document.querySelectorAll('#analysis-domain-options input:checked')].map(input => input.value);
}

function renderDomainOptions(domains) {
  if (document.querySelector('#analysis-domain-options input')) return;
  document.querySelector('#analysis-domain-options').innerHTML = domains.map(item =>
    `<label class="checkitem"><input type="checkbox" value="${esc(item.domain_id)}" checked><span>${esc(item.domain_id)}</span></label>`).join('');
}

function runActions(run) {
  if (!run || terminal.has(run.status)) return '';
  return `<button class="btn reject" data-run-action="cancel" data-run-id="${esc(run.run_id)}">Stop run</button>`;
}

function renderRun(run, target) {
  if (!run) { target.innerHTML = '<div class="empty">No analysis run has been started.</div>'; return; }
  const status = run.status || 'unknown';
  const pct = Number(run.progress_percent || 0);
  const domains = (run.domains || []).map(item => `<div class="listrow"><strong>${esc(item.domain_id)}</strong>${row(`${item.status} · ${item.rows_processed || 0} rows processed`)}</div>`).join('');
  target.innerHTML = `<div class="run-summary">
    <div class="run-summary-head"><div><strong>${esc(run.run_kind)} run</strong>${row(`${run.status} · ${run.current_stage || 'queued'} · ${run.run_id}`)}</div><div class="actions">${runActions(run)}</div></div>
    <div class="progress-track" aria-label="${esc(pct)} percent complete"><span style="width:${Math.min(100, Math.max(0, pct))}%"></span></div>
    <div class="run-metrics"><span><strong>${esc(pct)}%</strong> complete</span><span><strong>${esc(run.completed_domains || 0)}/${esc(run.total_domains || 0)}</strong> domains</span><span><strong>${esc(run.model_calls || 0)}</strong> model calls</span><span><strong>${esc(money(run.cost_micros))}</strong> spent</span><span>ceiling <strong>${esc(run.cost_ceiling_micros ? money(run.cost_ceiling_micros) : 'none')}</strong></span></div>
    <details><summary>Domain detail</summary><div class="run-domains">${domains || '<div class="empty">No domains selected.</div>'}</div></details>
  </div>`;
}

function renderHistory(items) {
  const target = document.querySelector('#analysis-run-history');
  if (!items.length) { target.innerHTML = '<div class="empty">No run history.</div>'; return; }
  target.innerHTML = `<div class="densewrap"><table class="dense"><thead><tr><th>Started</th><th>Run</th><th>Status</th><th>Progress</th><th>Cost</th><th>Action</th></tr></thead><tbody>${items.map(run => `<tr><td>${esc(time(run.started_at))}</td><td><strong>${esc(run.run_kind)}</strong><div class="small mono">${esc(run.run_id)}</div></td><td><span class="badge ${terminal.has(run.status) ? '' : 'pending'}">${esc(run.status)}</span></td><td>${esc(run.progress_percent)}% (${esc(run.completed_domains)}/${esc(run.total_domains)})</td><td>${esc(money(run.cost_micros))}</td><td>${run.status === 'cancelled' || run.status === 'failed' || run.status === 'interrupted' ? `<button class="btn" data-run-action="resume" data-run-id="${esc(run.run_id)}">Resume</button>` : runActions(run)}</td></tr>`).join('')}</tbody></table></div>`;
}

function renderOverview(overview, domains, operations) {
  document.querySelector('#analysis-executor').textContent = overview.executor === 'control_plane_only' ? 'Control plane ready' : (overview.executor || 'Unknown executor');
  renderDomainOptions(domains.domains);
  renderRun(overview.latest_run, document.querySelector('#analysis-current-run'));
  renderHistory(operations.runs || []);
  const active = overview.latest_run && !terminal.has(overview.latest_run.status);
  document.querySelector('#analysis-start').disabled = Boolean(active);
  if (pollHandle) window.clearTimeout(pollHandle);
  if (active) pollHandle = window.setTimeout(load, 3000);
}

async function actionRun(action, runId) {
  const result = await post(`/api/admin/analysis/runs/${encodeURIComponent(runId)}/${action}`);
  document.querySelector('#analysis-action-message').textContent = `${action === 'cancel' ? 'Stop requested' : 'Resume queued'} for ${runId}.`;
  return result;
}

async function load() {
  try {
    const [overview, domains, themes, signals, operations] = await Promise.all([
      get('/api/admin/analysis/overview'), get('/api/admin/analysis/domains'),
      get('/api/admin/analysis/themes?limit=12'), get('/api/admin/analysis/signals?limit=20'),
      get('/api/admin/analysis/operations')]);
    renderOverview(overview, domains, operations);
    document.querySelector('#analysis-cards').innerHTML = Object.entries(overview.counts).map(([key, value]) => `<div class="card"><strong>${esc(value)}</strong><span>${esc(key.replaceAll('_', ' '))}</span></div>`).join('');
    document.querySelector('#analysis-domains').innerHTML = domains.domains.map(item => `<div class="listrow"><strong>${esc(item.domain_id)}</strong>${row(item.status)}${row(item.source_tables.join(', '))}</div>`).join('');
    document.querySelector('#analysis-themes').innerHTML = themes.themes.length ? themes.themes.map(item => `<div class="listrow"><strong>${esc(item.theme_key)}</strong>${row(`${item.status} · ${item.passage_count} passages`)}</div>`).join('') : row('No emerging themes recorded.');
    document.querySelector('#analysis-signals').innerHTML = signals.signals.length ? signals.signals.map(item => `<div class="listrow"><strong>${esc(item.signal_type)}</strong>${row(`${item.domain_id} · ${item.subject_id} · ${item.direction}`)}</div>`).join('') : row('No automated signals recorded.');
  } catch (error) { document.querySelector('#analysis-action-message').textContent = error.message; document.querySelector('#analysis-action-message').className = 'error'; }
}

document.querySelector('#analysis-run-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = document.querySelector('#analysis-start');
  const message = document.querySelector('#analysis-action-message');
  button.disabled = true; message.className = 'small'; message.textContent = 'Starting run…';
  try {
    const ceiling = document.querySelector('#analysis-cost-ceiling').value;
    await post('/api/admin/analysis/runs', {run_kind: document.querySelector('#analysis-run-kind').value,
      domains: selectedDomains(), cost_ceiling_micros: ceiling ? Math.round(Number(ceiling) * 1000000) : 0});
    message.textContent = 'Run queued.'; await load();
  } catch (error) { message.className = 'error'; message.textContent = error.message; }
  finally { button.disabled = false; await load(); }
});

document.querySelector('#analysis-refresh').addEventListener('click', load);
document.addEventListener('click', async event => {
  const button = event.target.closest('[data-run-action]');
  if (!button) return;
  button.disabled = true;
  try { await actionRun(button.dataset.runAction, button.dataset.runId); await load(); }
  catch (error) { document.querySelector('#analysis-action-message').textContent = error.message; document.querySelector('#analysis-action-message').className = 'error'; }
  finally { button.disabled = false; }
});

load();
