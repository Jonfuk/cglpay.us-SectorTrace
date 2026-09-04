<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { TransportError } from '~/lib/transport'
import type { AnalysisDomain, AnalysisModelsResponse, AnalysisOperationsResponse, AnalysisOverviewResponse, AnalysisRun, AnalysisProposal, AnalysisRelease } from '~/types/admin'

type Row = Record<string, unknown>
interface AnalysisDashboard {
  overview: AnalysisOverviewResponse
  domains: AnalysisDomain[]
  coverage: Row[]
  signals: Row[]
  structured: Row[]
  themes: Row[]
  links: Row[]
  graph: Row
  models: AnalysisModelsResponse
  prevalence: Row[]
  operations: AnalysisOperationsResponse
  degraded: boolean
}

// Analysis is an operator control surface. Automated signals stay inside this
// page; release activation, proposal decisions and graph projection remain
// explicit human actions and are never exposed through the public app.
const api = useAdminApi()
const toast = useToast()
const { data, pending, error, refresh } = await useAsyncData<AnalysisDashboard | null>(
  'admin-analysis-dashboard',
  async () => {
    // Keep the control plane useful when a projection is slow, and avoid
    // opening eleven database-backed requests at once on the small VPS.
    let degraded = false
    const safe = async <T>(request: Promise<T>, fallback: T): Promise<T> => {
      try { return await request } catch { degraded = true; return fallback }
    }
    const overviewValue = await safe(api.analysisOverview(), { active_release: null })
    const domainsValue = await safe(api.analysisDomains(), { domains: [] as AnalysisDomain[] })
    const coverageValue = await safe(api.analysisCoverage(), { coverage: [] as Row[] })
    const signalsValue = await safe(api.analysisSignals({ query: { limit: 20 } }), { signals: [] as Row[] })
    const structuredValue = await safe(api.analysisStructured({ query: { limit: 20 } }), { structured: [] as Row[] })
    const themesValue = await safe(api.analysisThemes({ query: { limit: 20 } }), { themes: [] as Row[] })
    const linksValue = await safe(api.analysisLinks({ query: { limit: 20 } }), { links: [] as Row[] })
    const graphValue = await safe(api.analysisGraph(), {})
    const modelsValue = await safe(api.analysisModels(), { releases: [] as AnalysisRelease[] })
    const prevalenceValue = await safe(api.analysisPrevalence({ query: { limit: 20 } }), { prevalence: [] as Row[] })
    const operationsValue = await safe(api.analysisOperations(), { runs: [], proposals: [] })
    return {
      overview: overviewValue, domains: domainsValue.domains, coverage: coverageValue.coverage,
      signals: signalsValue.signals, structured: structuredValue.structured,
      themes: themesValue.themes, links: linksValue.links, graph: graphValue, models: modelsValue,
      prevalence: prevalenceValue.prevalence, operations: operationsValue,
      degraded,
    }
  },
  { default: () => ({
    overview: { active_release: null }, domains: [], coverage: [], signals: [],
    structured: [], themes: [], links: [], graph: {}, models: {}, prevalence: [],
    operations: { runs: [], proposals: [] }, degraded: true,
  }) },
)

const overview = computed(() => data.value?.overview)
const domains = computed(() => data.value?.domains ?? [])
const run = computed<AnalysisRun | null>(() => (overview.value?.latest_run as AnalysisRun | null | undefined) ?? null)
const runs = computed<AnalysisRun[]>(() => data.value?.operations.runs ?? [])
const proposals = computed<AnalysisProposal[]>(() => data.value?.operations.proposals ?? [])
const releases = computed<AnalysisRelease[]>(() => data.value?.models.releases ?? [])
const selectedDomains = ref<string[]>([])
const runKind = ref('complete')
const costCeiling = ref<number | undefined>()
const busy = ref(false)
const message = ref('')
const messageLevel = ref<'ok' | 'bad' | 'warn'>('warn')
const proposalFilter = ref('pending')
let pollTimer: ReturnType<typeof setTimeout> | null = null

watch(domains, (items) => {
  if (!selectedDomains.value.length) selectedDomains.value = items.map((item) => item.domain_id)
}, { immediate: true })

function value(row: Row | null | undefined, key: string): string {
  const item = row?.[key]
  if (item === null || item === undefined || item === '') return '—'
  if (Array.isArray(item)) return item.join(', ')
  if (typeof item === 'object') return JSON.stringify(item)
  return String(item)
}

function when(value_: unknown): string {
  if (!value_) return '—'
  const date = new Date(String(value_))
  return Number.isNaN(date.getTime()) ? String(value_) : date.toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
}

function money(micros: unknown): string {
  const value_ = Number(micros)
  return Number.isFinite(value_) ? `£${(value_ / 1_000_000).toFixed(4)}` : '—'
}

function terminal(status: string | null | undefined): boolean {
  return ['cancelled', 'complete', 'failed', 'interrupted'].includes(status ?? '')
}

function level(status: string | null | undefined): 'ok' | 'warn' | 'bad' | 'neutral' {
  if (status === 'complete' || status === 'ok') return 'ok'
  if (status === 'failed' || status === 'rolled_back') return 'bad'
  if (terminal(status)) return 'neutral'
  return 'warn'
}

function setMessage(text: string, kind: 'ok' | 'bad' | 'warn' = 'warn') {
  message.value = text
  messageLevel.value = kind
}

function stopPolling() {
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = null
}

async function pollRun(runId: string): Promise<void> {
  try {
    const current = await api.analysisRuns({ query: { limit: 20 } })
    const latest = current.runs.find((item) => item.run_id === runId)
    if (latest && !terminal(latest.status)) {
      pollTimer = setTimeout(() => { void pollRun(runId) }, 3000)
      return
    }
    await refresh()
    busy.value = false
  } catch (e) {
    busy.value = false
    setMessage(e instanceof TransportError ? e.message : 'Analysis run status is unavailable.', 'bad')
  }
}

async function startRun() {
  if (busy.value || !selectedDomains.value.length) return
  if (!window.confirm(`Queue a ${runKind.value} analysis run for ${selectedDomains.value.length} domain(s)?`)) return
  busy.value = true
  setMessage('Queueing analysis run…')
  try {
    const started = await api.startAnalysisRun({
      runKind: runKind.value,
      domains: selectedDomains.value,
      costCeilingMicros: costCeiling.value ? Math.round(costCeiling.value * 1_000_000) : 0,
    })
    setMessage(`Run ${started.run_id} queued.`, 'ok')
    void pollRun(started.run_id)
    await refresh()
  } catch (e) {
    busy.value = false
    setMessage(e instanceof TransportError ? e.message : 'Analysis run could not be queued.', 'bad')
  }
}

async function runAction(action: 'cancel' | 'resume', runId: string) {
  if (!window.confirm(`${action === 'cancel' ? 'Stop' : 'Resume'} analysis run ${runId}?`)) return
  busy.value = true
  try {
    await api.analysisRunAction(runId, action)
    setMessage(action === 'cancel' ? 'Stop requested.' : 'Run resumed.', 'ok')
    await refresh()
  } catch (e) {
    setMessage(e instanceof TransportError ? e.message : 'Analysis run action failed.', 'bad')
  } finally { busy.value = false }
}

async function decideProposal(action: 'accept' | 'defer' | 'dismiss', proposal: AnalysisProposal) {
  const reason = window.prompt(`Reason to ${action} this proposal (optional):`)
  if (reason === null) return
  try {
    await api.decideAnalysisProposal(proposal.proposal_id, action, reason || undefined)
    toast.add({ title: `Proposal ${action}ed`, color: 'success' })
    await refresh()
  } catch (e) { toast.add({ title: 'Proposal action failed', description: e instanceof TransportError ? e.message : String(e), color: 'error' }) }
}

async function releaseAction(action: 'activate' | 'rollback', release: AnalysisRelease) {
  const reason = action === 'rollback' ? window.prompt('Reason for rollback (optional):') : null
  if (action === 'rollback' && reason === null) return
  if (!window.confirm(`${action === 'activate' ? 'Activate' : 'Roll back'} release ${release.release_id}?`)) return
  try {
    if (action === 'activate') await api.activateAnalysisRelease(release.release_id)
    else await api.rollbackAnalysisRelease(release.release_id, reason || undefined)
    toast.add({ title: `${action === 'activate' ? 'Release activated' : 'Release rolled back'}`, color: 'success' })
    await refresh()
  } catch (e) { toast.add({ title: 'Release action failed', description: e instanceof TransportError ? e.message : String(e), color: 'error' }) }
}

async function rebuildGraph(releaseId?: string) {
  if (!window.confirm(`Queue graph projection${releaseId ? ` for ${releaseId}` : ''}?`)) return
  try {
    await api.rebuildAnalysisGraph(releaseId)
    toast.add({ title: 'Graph projection queued', color: 'success' })
    await refresh()
  } catch (e) { toast.add({ title: 'Graph rebuild failed', description: e instanceof TransportError ? e.message : String(e), color: 'error' }) }
}

const filteredProposals = computed(() => proposals.value.filter((item) => proposalFilter.value === 'all' || (proposalFilter.value === 'pending' ? item.status === 'pending' : item.status !== 'pending')))
onBeforeUnmount(stopPolling)
useHead({ title: 'SectorTrace — Analysis' })
</script>

<template>
  <section class="space-y-6">
    <div>
      <h1 class="text-2xl font-semibold">Analysis platform</h1>
      <p class="mt-2 max-w-3xl text-sm opacity-70">Control-plane view of automated signals, releases, worker state, and adaptation proposals. These outputs are admin-only and are not evidence until a separate human workflow accepts them.</p>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading analysis platform…</div>
    <template v-else-if="data">
      <p v-if="data.degraded || error" class="text-sm text-amber-700 dark:text-amber-300">Some analysis projections are temporarily unavailable; the control plane is showing the data that loaded. Refresh before taking an action.</p>
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <UCard v-for="(count, key) in (overview?.counts ?? {})" :key="key">
          <div class="text-2xl font-semibold">{{ count }}</div><div class="text-xs opacity-60 capitalize">{{ String(key).replaceAll('_', ' ') }}</div>
        </UCard>
      </div>

      <UCard>
        <template #header><span class="text-sm font-medium">Analysis run control</span></template>
        <div class="grid gap-4 md:grid-cols-4">
          <label class="text-sm space-y-1"><span class="opacity-70">Run kind</span><select v-model="runKind" class="w-full border border-black/15 dark:border-white/15 rounded px-2 py-2 bg-transparent"><option value="complete">complete</option><option value="discovery">discovery</option><option value="optimization">optimization</option><option value="pilot">pilot</option></select></label>
          <label class="text-sm space-y-1"><span class="opacity-70">Cost ceiling (£, optional)</span><input v-model.number="costCeiling" type="number" min="0" step="0.01" placeholder="none" class="w-full border border-black/15 dark:border-white/15 rounded px-2 py-2 bg-transparent"></label>
          <div class="md:col-span-2 flex items-end gap-2"><UButton color="primary" :disabled="busy || !selectedDomains.length" @click="startRun">{{ busy ? 'Working…' : 'Queue analysis run' }}</UButton><UButton color="neutral" variant="outline" @click="refresh">Refresh</UButton></div>
        </div>
        <div class="mt-4 flex flex-wrap gap-2"><label v-for="domain in domains" :key="domain.domain_id" class="flex items-center gap-2 text-xs border border-black/10 dark:border-white/10 rounded px-2 py-1"><input v-model="selectedDomains" type="checkbox" :value="domain.domain_id">{{ domain.domain_id }}</label></div>
        <p v-if="message" class="mt-3 text-sm" :class="messageLevel === 'bad' ? 'text-red-700 dark:text-red-300' : messageLevel === 'ok' ? 'text-green-700 dark:text-green-300' : 'opacity-70'">{{ message }}</p>
      </UCard>

      <UCard>
        <template #header><div class="flex items-center justify-between gap-3"><span class="text-sm font-medium">Current run</span><StatusPill :label="run?.status ?? 'none'" :level="level(run?.status)" /></div></template>
        <StEmptyState v-if="!run" title="No analysis run" message="No analysis run has been started." />
        <template v-else>
          <div class="flex flex-wrap gap-3 text-sm"><span class="font-mono">{{ run.run_id }}</span><span>{{ run.run_kind }}</span><span>{{ run.current_stage ?? 'queued' }}</span><span>{{ run.completed_domains ?? 0 }}/{{ run.total_domains ?? 0 }} domains</span><span>{{ run.progress_percent ?? 0 }}%</span><span>{{ money(run.cost_micros) }} spent / {{ money(run.estimated_cost_micros) }} estimated</span></div>
          <div class="mt-3 h-2 rounded bg-black/10 dark:bg-white/10"><div class="h-2 rounded bg-[var(--st-accent)]" :style="{ width: `${Math.min(100, Math.max(0, run.progress_percent ?? 0))}%` }" /></div>
          <p v-if="run.error_detail" class="mt-3 text-sm text-red-700 dark:text-red-300">{{ run.error_detail }}</p>
          <div class="mt-4 flex gap-2"><UButton v-if="run.status && !terminal(run.status)" color="neutral" variant="outline" :disabled="busy" @click="runAction('cancel', run.run_id)">Stop run</UButton><UButton v-if="run.status === 'cancelled' || run.status === 'failed' || run.status === 'interrupted'" color="primary" :disabled="busy" @click="runAction('resume', run.run_id)">Resume</UButton></div>
        </template>
      </UCard>

      <UCard><template #header><span class="text-sm font-medium">Analysis domains</span></template><AdminTable :columns="[{ key: 'domain_id', label: 'Domain', mono: true }, { key: 'status', label: 'Status' }, { key: 'prerequisite_status', label: 'Prerequisites' }, { key: 'rows_processed', label: 'Processed', numeric: true }, { key: 'rows_written', label: 'Written', numeric: true }]" :rows="domains" row-key="domain_id" /></UCard>

      <div class="grid gap-6 lg:grid-cols-2">
        <UCard><template #header><span class="text-sm font-medium">Automated signals ({{ data.signals.length }})</span></template><ul v-if="data.signals.length" class="divide-y divide-black/5 dark:divide-white/5 text-sm"><li v-for="(item, i) in data.signals" :key="i" class="py-2"><strong>{{ value(item, 'signal_type') }}</strong> · {{ value(item, 'domain_id') }} · {{ value(item, 'direction') }} · {{ value(item, 'subject_id') }}</li></ul><StEmptyState v-else title="No automated signals" /></UCard>
        <UCard><template #header><span class="text-sm font-medium">Emerging themes ({{ data.themes.length }})</span></template><ul v-if="data.themes.length" class="divide-y divide-black/5 dark:divide-white/5 text-sm"><li v-for="(item, i) in data.themes" :key="i" class="py-2 flex items-center justify-between gap-3"><span><strong>{{ value(item, 'theme_key') }}</strong> · {{ value(item, 'status') }} · {{ value(item, 'passage_count') }} passages</span><UButton v-if="item.status === 'promotion_ready'" size="xs" color="primary" @click="api.promoteAnalysisTheme(String(item.theme_id)).then(refresh)">Promote</UButton></li></ul><StEmptyState v-else title="No emerging themes" /></UCard>
      </div>

      <UCard><template #header><div class="flex items-center justify-between gap-3"><span class="text-sm font-medium">Adaptation proposals</span><select v-model="proposalFilter" class="text-xs border border-black/15 dark:border-white/15 rounded px-2 py-1 bg-transparent"><option value="pending">Pending</option><option value="all">All</option><option value="decided">Decided</option></select></div></template><StEmptyState v-if="!filteredProposals.length" title="No proposals" /><div v-else class="overflow-x-auto"><table class="w-full text-sm"><thead><tr class="text-left border-b border-black/15 dark:border-white/15"><th class="py-2 pr-4">Proposal</th><th class="py-2 pr-4">Scope</th><th class="py-2 pr-4">Status</th><th class="py-2">Decision</th></tr></thead><tbody><tr v-for="proposal in filteredProposals" :key="proposal.proposal_id" class="border-b border-black/5 dark:border-white/5 align-top"><td class="py-2 pr-4"><div class="font-medium">{{ proposal.proposal_type }}</div><div class="font-mono text-xs opacity-60">{{ proposal.proposal_id }}</div><div class="text-xs opacity-60">{{ when(proposal.created_at) }}</div></td><td class="py-2 pr-4">{{ proposal.domain_id ?? 'All domains' }}<div class="text-xs opacity-60">{{ proposal.automatic_action ?? '—' }}</div></td><td class="py-2 pr-4"><StatusPill :label="proposal.status ?? 'pending'" :level="level(proposal.status)" /></td><td class="py-2"><div v-if="proposal.status === 'pending'" class="flex gap-2"><UButton size="xs" color="primary" @click="decideProposal('accept', proposal)">Accept</UButton><UButton size="xs" color="neutral" variant="outline" @click="decideProposal('defer', proposal)">Defer</UButton><UButton size="xs" color="error" variant="outline" @click="decideProposal('dismiss', proposal)">Dismiss</UButton></div><span v-else class="text-xs opacity-60">{{ proposal.admin_reason ?? 'Decision recorded' }}</span></td></tr></tbody></table></div></UCard>

      <UCard><template #header><span class="text-sm font-medium">Releases</span></template><StEmptyState v-if="!releases.length" title="No releases" /><div v-else class="overflow-x-auto"><table class="w-full text-sm"><thead><tr class="text-left border-b border-black/15 dark:border-white/15"><th class="py-2 pr-4">Created</th><th class="py-2 pr-4">Release</th><th class="py-2 pr-4">Status</th><th class="py-2">Actions</th></tr></thead><tbody><tr v-for="release in releases" :key="release.release_id" class="border-b border-black/5 dark:border-white/5"><td class="py-2 pr-4">{{ when(release.created_at) }}</td><td class="py-2 pr-4 font-mono text-xs">{{ release.release_id }}<div class="opacity-60">{{ release.manifest_sha256 }}</div></td><td class="py-2 pr-4"><StatusPill :label="release.status ?? 'unknown'" :level="level(release.status)" /></td><td class="py-2"><div class="flex flex-wrap gap-2"><UButton v-if="release.status !== 'active' && release.status !== 'rolled_back'" size="xs" color="primary" @click="releaseAction('activate', release)">Activate</UButton><UButton v-if="release.status !== 'rolled_back'" size="xs" color="error" variant="outline" @click="releaseAction('rollback', release)">Rollback</UButton><UButton size="xs" color="neutral" variant="outline" @click="rebuildGraph(release.release_id)">Queue graph</UButton><a :href="`/api/admin/analysis/reports/${encodeURIComponent(release.release_id)}`" class="text-xs text-[var(--st-accent)] underline self-center">JSON</a></div></td></tr></tbody></table></div></UCard>

      <div class="grid gap-6 lg:grid-cols-3"><UCard><template #header><span class="text-sm font-medium">Worker</span></template><StatusPill :label="overview?.executor ?? 'unknown'" :level="overview?.executor === 'worker_online' ? 'ok' : 'warn'" /><p class="mt-2 text-xs opacity-60">{{ value(overview?.worker as Row | undefined, 'worker_id') }} · {{ value(overview?.worker as Row | undefined, 'status') }}</p></UCard><UCard><template #header><span class="text-sm font-medium">Graph projection</span></template><div class="text-sm">{{ value(data.graph, 'pending') }} queued</div><p class="mt-2 text-xs opacity-60">Canonical claim isolation: {{ value(data.graph, 'canonical_claim_isolation') }}</p><UButton class="mt-3" size="xs" color="neutral" variant="outline" @click="rebuildGraph()">Queue latest graph</UButton></UCard><UCard><template #header><span class="text-sm font-medium">Output samples</span></template><div class="text-sm space-y-1"><div>{{ data.structured.length }} structured</div><div>{{ data.links.length }} links</div><div>{{ data.prevalence.length }} prevalence diagnostics</div><div>{{ data.coverage.length }} coverage domains</div></div></UCard></div>
      <p class="text-xs opacity-60">{{ overview?.quality_boundary }}</p>
    </template>
    <StEmptyState v-else variant="unavailable" />
  </section>
</template>
