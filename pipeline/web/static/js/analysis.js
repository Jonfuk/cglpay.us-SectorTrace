const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const get = async path => { const response = await fetch(path); if (!response.ok) throw new Error(await response.text()); return response.json(); };
const post = async (path, body = {}) => { const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}); if (!response.ok) throw new Error(await response.text()); return response.json(); };
const row = value => `<div class="small">${esc(value)}</div>`;
const money = micros => micros == null ? '—' : `£${(Number(micros || 0) / 1000000).toFixed(4)}`;
const time = value => value ? new Date(value).toLocaleString('en-GB', {dateStyle: 'medium', timeStyle: 'short'}) : '—';
const terminal = new Set(['cancelled', 'complete', 'failed', 'interrupted']);
const proposalFilter = {value: 'pending'};
let proposalItems = [];
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
  const executorNote = run.control_plane_only && status === 'queued' ? '<div class="warn">Run control is connected. Processing remains queued until the analysis worker is configured.</div>' : '';
  const staleHeartbeatNote = run.control_plane_only && status === 'running' ? '<div class="warn">The worker heartbeat is stale while this run is active. Check the worker container if progress does not resume.</div>' : '';
  const errorDetail = run.error_detail || (run.domains || []).find(item => item.error_detail)?.error_detail;
  const failureNote = errorDetail ? `<div class="error"><strong>Failure:</strong> ${esc(errorDetail)}</div>` : '';
  target.innerHTML = `<div class="run-summary">${executorNote}${staleHeartbeatNote}${failureNote}
    <div class="run-summary-head"><div><strong>${esc(run.run_kind)} run</strong>${row(`${run.status} · ${run.current_stage || 'queued'} · ${run.run_id}`)}</div><div class="actions">${runActions(run)}</div></div>
    <div class="progress-track" aria-label="${esc(pct)} percent complete"><span style="width:${Math.min(100, Math.max(0, pct))}%"></span></div>
    <div class="run-metrics"><span><strong>${esc(pct)}%</strong> complete</span><span><strong>${esc(run.completed_domains || 0)}/${esc(run.total_domains || 0)}</strong> domains</span><span><strong>${esc(run.model_calls || 0)}</strong> calls / estimate <strong>${esc(run.estimated_calls ?? '—')}</strong></span><span><strong>${esc(money(run.cost_micros))}</strong> spent / estimate <strong>${esc(money(run.estimated_cost_micros))}</strong></span><span>ceiling <strong>${esc(run.cost_ceiling_micros ? money(run.cost_ceiling_micros) : 'none')}</strong></span></div>
    <details><summary>Domain detail</summary><div class="run-domains">${domains || '<div class="empty">No domains selected.</div>'}</div></details>
  </div>`;
}

function renderHistory(items) {
  const target = document.querySelector('#analysis-run-history');
  if (!items.length) { target.innerHTML = '<div class="empty">No run history.</div>'; return; }
  target.innerHTML = `<div class="densewrap"><table class="dense"><thead><tr><th>Started</th><th>Run</th><th>Status</th><th>Progress</th><th>Cost</th><th>Action</th></tr></thead><tbody>${items.map(run => `<tr><td>${esc(time(run.started_at))}</td><td><strong>${esc(run.run_kind)}</strong><div class="small mono">${esc(run.run_id)}</div></td><td><span class="badge ${terminal.has(run.status) ? '' : 'pending'}">${esc(run.status)}</span></td><td>${esc(run.progress_percent)}% (${esc(run.completed_domains)}/${esc(run.total_domains)})</td><td>${esc(money(run.cost_micros))}</td><td>${run.status === 'cancelled' || run.status === 'failed' || run.status === 'interrupted' ? `<button class="btn" data-run-action="resume" data-run-id="${esc(run.run_id)}">Resume</button>` : runActions(run)}</td></tr>`).join('')}</tbody></table></div>`;
}

function renderReleases(items) {
  const target = document.querySelector('#analysis-releases');
  if (!items.length) { target.innerHTML = '<div class="empty">No releases.</div>'; return; }
  target.innerHTML = `<div class="densewrap"><table class="dense"><thead><tr><th>Created</th><th>Release</th><th>Status</th><th>Actions</th></tr></thead><tbody>${items.map(release => `<tr><td>${esc(time(release.created_at))}</td><td><strong>${esc(release.release_id)}</strong><div class="small mono">${esc(release.manifest_sha256)}</div></td><td><span class="badge ${release.status === 'active' ? 'approved' : release.status === 'rolled_back' ? 'rejected' : 'pending'}">${esc(release.status)}</span></td><td><div class="actions"><button class="btn approve" data-release-action="activate" data-release-id="${esc(release.release_id)}" ${release.status === 'active' || release.status === 'rolled_back' ? 'disabled' : ''}>Activate</button><button class="btn reject" data-release-action="rollback" data-release-id="${esc(release.release_id)}" ${release.status === 'rolled_back' ? 'disabled' : ''}>Rollback</button><button class="btn" data-graph-action="rebuild" data-release-id="${esc(release.release_id)}">Queue graph</button><a class="btn" href="/api/admin/analysis/reports/${encodeURIComponent(release.release_id)}" download>JSON</a><a class="btn" href="/api/admin/analysis/reports/${encodeURIComponent(release.release_id)}?format=csv" download>CSV</a><a class="btn" href="/api/admin/analysis/reports/${encodeURIComponent(release.release_id)}?format=html" target="_blank" rel="noopener">Printable HTML</a></div></td></tr>`).join('')}</tbody></table></div>`;
}

function proposalTrigger(value) {
  try { return JSON.stringify(JSON.parse(value || '{}'), null, 2); }
  catch (_) { return String(value || '{}'); }
}

function proposalBadge(status) {
  return status === 'accepted' ? 'approved' : status === 'dismissed' ? 'rejected' : 'pending';
}

function renderProposals(items) {
  proposalItems = Array.isArray(items) ? items : [];
  const target = document.querySelector('#analysis-proposals');
  const filtered = proposalItems.filter(item => proposalFilter.value === 'all'
    || (proposalFilter.value === 'pending' ? item.status === 'pending' : item.status !== 'pending'));
  const pending = proposalItems.filter(item => item.status === 'pending').length;
  if (!proposalItems.length) { target.innerHTML = '<div class="empty">No adaptation proposals recorded.</div>'; return; }
  const summary = `<div class="proposal-summary small"><strong>${esc(pending)}</strong> pending · <strong>${esc(proposalItems.length)}</strong> shown in the operations window</div>`;
  if (!filtered.length) { target.innerHTML = `${summary}<div class="empty">No proposals match this filter.</div>`; return; }
  target.innerHTML = `${summary}<div class="densewrap"><table class="dense proposal-table"><thead><tr><th>Created</th><th>Proposal</th><th>Scope</th><th>Trigger</th><th>Status</th><th>Decision</th></tr></thead><tbody>${filtered.map(proposal => {
    const status = proposal.status || 'pending';
    const decision = status === 'pending' ? `<div class="actions"><button class="btn approve" data-proposal-action="accept" data-proposal-id="${esc(proposal.proposal_id)}">Accept</button><button class="btn" data-proposal-action="defer" data-proposal-id="${esc(proposal.proposal_id)}">Defer</button><button class="btn reject" data-proposal-action="dismiss" data-proposal-id="${esc(proposal.proposal_id)}">Dismiss</button></div>` : row(proposal.decided_at ? `Decided ${time(proposal.decided_at)}` : 'Decision recorded');
    const reason = proposal.admin_reason ? row(`Reason: ${proposal.admin_reason}`) : '';
    return `<tr><td>${esc(time(proposal.created_at))}</td><td><strong>${esc(proposal.proposal_type)}</strong>${row(proposal.proposal_id)}</td><td>${row(proposal.domain_id || 'All domains')}${row(proposal.release_id || 'No release')}</td><td><details><summary>View trigger</summary><pre class="context">${esc(proposalTrigger(proposal.trigger_json))}</pre>${proposal.automatic_action ? row(`Suggested safe action: ${proposal.automatic_action}`) : ''}</details></td><td><span class="badge ${proposalBadge(status)}">${esc(status)}</span>${reason}</td><td>${decision}</td></tr>`;
  }).join('')}</tbody></table></div>`;
}

function renderModelCalls(items) {
  const target = document.querySelector('#analysis-model-calls');
  if (!items.length) { target.innerHTML = '<div class="empty">No model calls recorded.</div>'; return; }
  target.innerHTML = `<div class="densewrap"><table class="dense model-call-table"><thead><tr><th>Created</th><th>Run / domain</th><th>Model</th><th>Status</th><th>Cost</th><th>Error</th></tr></thead><tbody>${items.map(call => {
    const status = call.status || 'unknown';
    const badge = status === 'ok' ? 'approved' : status === 'unavailable' || status === 'error' || status === 'invalid_json' ? 'rejected' : 'pending';
    return `<tr><td>${esc(time(call.created_at))}</td><td>${row(call.run_id || 'No run')}${row(call.domain_id || '—')}</td><td>${esc(call.model_id)}${row(call.cached ? 'cached' : `${call.latency_ms ?? '—'} ms`)}</td><td><span class="badge ${badge}">${esc(status)}</span></td><td>${esc(money(call.cost_micros))}</td><td>${call.error_detail ? `<div class="error">${esc(call.error_detail)}</div>` : '—'}</td></tr>`;
  }).join('')}</tbody></table></div>`;
}

function renderOverview(overview, domains, operations, models) {
  const executorLabels = {worker_online: 'Worker online', worker_offline: 'Worker offline', control_plane_only: 'Control plane only'};
  const worker = overview.worker || {};
  document.querySelector('#analysis-executor').textContent = executorLabels[overview.executor] || overview.executor || 'Unknown executor';
  document.querySelector('#analysis-executor').title = worker.worker_id ? `${worker.worker_id} · ${worker.status || 'unknown'}` : 'No analysis worker heartbeat has been received';
  renderDomainOptions(domains.domains);
  renderRun(overview.latest_run, document.querySelector('#analysis-current-run'));
  renderHistory(operations.runs || []);
  renderReleases(models.releases || []);
  renderProposals(operations.proposals || []);
  renderModelCalls(operations.model_calls || []);
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
    const [overview, domains, themes, signals, operations, models, structured, links, graph, prevalence] = await Promise.all([
      get('/api/admin/analysis/overview'), get('/api/admin/analysis/domains'),
      get('/api/admin/analysis/themes?limit=12'), get('/api/admin/analysis/signals?limit=20'),
      get('/api/admin/analysis/operations'), get('/api/admin/analysis/models'),
      get('/api/admin/analysis/structured?limit=1'), get('/api/admin/analysis/links?limit=1'),
      get('/api/admin/analysis/graph'), get('/api/admin/analysis/prevalence?limit=1')]);
    renderOverview(overview, domains, operations, models);
    document.querySelector('#analysis-cards').innerHTML = Object.entries(overview.counts).map(([key, value]) => `<div class="card"><strong>${esc(value)}</strong><span>${esc(key.replaceAll('_', ' '))}</span></div>`).join('');
    document.querySelector('#analysis-domains').innerHTML = domains.domains.map(item => `<div class="listrow"><strong>${esc(item.domain_id)}</strong>${row(item.status)}${row(item.source_tables.join(', '))}</div>`).join('');
    document.querySelector('#analysis-themes').innerHTML = themes.themes.length ? themes.themes.map(item => `<div class="listrow"><strong>${esc(item.theme_key)}</strong>${row(`${item.status} · ${item.passage_count} passages`)}</div>`).join('') : row('No emerging themes recorded.');
    document.querySelector('#analysis-signals').innerHTML = signals.signals.length ? signals.signals.map(item => `<div class="listrow"><strong>${esc(item.signal_type)}</strong>${row(`${item.domain_id} · ${item.subject_id} · ${item.direction}`)}</div>`).join('') : row('No automated signals recorded.');
    const pending = graph.pending || 0;
    const latestPrevalence = prevalence.prevalence?.[0];
    document.querySelector('#analysis-output-summary').innerHTML = `<div class="run-metrics"><span><strong>${esc(structured.structured?.length || 0)}</strong> structured sample</span><span><strong>${esc(links.links?.length || 0)}</strong> link sample</span><span><strong>${esc(pending)}</strong> graph queued</span><span><strong>${esc(latestPrevalence ? `${latestPrevalence.positives}/${latestPrevalence.positives + latestPrevalence.negatives}` : '—')}</strong> latest narrative prevalence sample</span></div>`;
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
document.querySelector('#analysis-proposal-filter').addEventListener('change', event => {
  proposalFilter.value = event.target.value;
  renderProposals(proposalItems);
});
document.addEventListener('click', async event => {
  const button = event.target.closest('[data-run-action]');
  if (!button) return;
  button.disabled = true;
  try { await actionRun(button.dataset.runAction, button.dataset.runId); await load(); }
  catch (error) { document.querySelector('#analysis-action-message').textContent = error.message; document.querySelector('#analysis-action-message').className = 'error'; }
  finally { button.disabled = false; }
});

document.addEventListener('click', async event => {
  const button = event.target.closest('[data-proposal-action]');
  if (!button) return;
  const action = button.dataset.proposalAction;
  const label = action === 'accept' ? 'accept' : action === 'dismiss' ? 'dismiss' : 'defer';
  const reason = window.prompt(`Reason to ${label} this proposal (optional):`);
  if (reason === null) return;
  button.disabled = true;
  try {
    await post(`/api/admin/analysis/proposals/${action}`, {proposal_id: button.dataset.proposalId, reason: reason || null});
    document.querySelector('#analysis-action-message').className = 'small';
    document.querySelector('#analysis-action-message').textContent = `Proposal ${button.dataset.proposalId} marked ${action === 'accept' ? 'accepted' : action === 'dismiss' ? 'dismissed' : 'deferred'}.`;
    await load();
  } catch (error) {
    document.querySelector('#analysis-action-message').textContent = error.message;
    document.querySelector('#analysis-action-message').className = 'error';
  } finally { button.disabled = false; }
});

document.addEventListener('click', async event => {
  const button = event.target.closest('[data-graph-action]');
  if (!button) return;
  button.disabled = true;
  try {
    await post('/api/admin/analysis/graph/rebuild', {release_id: button.dataset.releaseId});
    document.querySelector('#analysis-action-message').textContent = `Graph projection queued for ${button.dataset.releaseId}.`;
    await load();
  } catch (error) {
    document.querySelector('#analysis-action-message').textContent = error.message;
    document.querySelector('#analysis-action-message').className = 'error';
  } finally { button.disabled = false; }
});

document.addEventListener('click', async event => {
  const button = event.target.closest('[data-release-action]');
  if (!button) return;
  button.disabled = true;
  try {
    const action = button.dataset.releaseAction;
    const body = action === 'rollback' ? {reason: window.prompt('Reason for rollback (optional):') || null} : {};
    await post(`/api/admin/analysis/releases/${encodeURIComponent(button.dataset.releaseId)}/${action}`, body);
    document.querySelector('#analysis-action-message').textContent = `${action === 'activate' ? 'Activated' : 'Rolled back'} ${button.dataset.releaseId}.`;
    await load();
  } catch (error) { document.querySelector('#analysis-action-message').textContent = error.message; document.querySelector('#analysis-action-message').className = 'error'; }
  finally { button.disabled = false; }
});

load();
