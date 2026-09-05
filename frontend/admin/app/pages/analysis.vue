<script setup lang="ts">
const dialog = useAdminDialog();
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { TransportError } from '~/lib/transport';
import type {
  AnalysisDomain,
  AnalysisModelsResponse,
  AnalysisOperationsResponse,
  AnalysisOverviewResponse,
  AnalysisRun,
  AnalysisProposal,
  AnalysisRelease,
} from '~/types/admin';

type Row = Record<string, unknown>;
interface AnalysisDashboard {
  overview: AnalysisOverviewResponse;
  domains: AnalysisDomain[];
  coverage: Row[];
  signals: Row[];
  structured: Row[];
  themes: Row[];
  links: Row[];
  graph: Row;
  models: AnalysisModelsResponse;
  prevalence: Row[];
  operations: AnalysisOperationsResponse;
  degraded: boolean;
  overviewAvailable: boolean;
}

// Analysis is an operator control surface. Automated signals stay inside this
// page; release activation, proposal decisions and graph projection remain
// explicit human actions and are never exposed through the public app.
const api = useAdminApi();
const route = useRoute();
const view = computed(() => String(route.query.view || 'runs'));
const tabs = [
  { key: 'runs', label: 'Runs & domains' },
  { key: 'proposals', label: 'Proposals' },
  { key: 'releases', label: 'Releases & reports' },
  { key: 'outputs', label: 'Inspect outputs' },
  { key: 'models', label: 'Model calls' },
];
const output = ref('signals'),
  outputDomain = ref(''),
  outputRelease = ref('');
const selectedRun = ref('');
const toast = useToast();
const { data, pending, error, refresh } =
  await useAsyncData<AnalysisDashboard | null>(
    'admin-analysis-dashboard',
    async () => {
      // Keep the control plane useful when a projection is slow, and avoid
      // opening eleven database-backed requests at once on the small VPS.
      let degraded = false;
      let overviewAvailable = true;
      const safe = async <T,>(request: Promise<T>, fallback: T): Promise<T> => {
        try {
          return await request;
        } catch {
          degraded = true;
          return fallback;
        }
      };
      const overviewValue = await safe(
        api.analysisOverview().catch((error) => {
          overviewAvailable = false;
          throw error;
        }),
        {
          active_release: null,
        },
      );
      const domainsValue = await safe(api.analysisDomains(), {
        domains: [] as AnalysisDomain[],
      });
      const coverageValue = { coverage: [] as Row[] };
      const signalsValue = { signals: [] as Row[] };
      const structuredValue = { structured: [] as Row[] };
      const themesValue =
        view.value === 'outputs'
          ? await safe(api.analysisThemes({ query: { limit: 20 } }), {
              themes: [] as Row[],
            })
          : { themes: [] as Row[] };
      const linksValue = { links: [] as Row[] };
      const graphValue = {};
      const modelsValue =
        view.value === 'releases'
          ? await safe(api.analysisModels(), {
              releases: [] as AnalysisRelease[],
            })
          : { releases: [] as AnalysisRelease[] };
      const prevalenceValue = { prevalence: [] as Row[] };
      const operationsValue =
        view.value === 'runs' || view.value === 'proposals'
          ? await safe(api.analysisOperations(), { runs: [], proposals: [] })
          : { runs: [], proposals: [] };
      return {
        overview: overviewValue,
        domains: domainsValue.domains,
        coverage: coverageValue.coverage,
        signals: signalsValue.signals,
        structured: structuredValue.structured,
        themes: themesValue.themes,
        links: linksValue.links,
        graph: graphValue,
        models: modelsValue,
        prevalence: prevalenceValue.prevalence,
        operations: operationsValue,
        degraded,
        overviewAvailable,
      };
    },
    {
      watch: [view],
      default: () => ({
        overview: { active_release: null },
        domains: [],
        coverage: [],
        signals: [],
        structured: [],
        themes: [],
        links: [],
        graph: {},
        models: {},
        prevalence: [],
        operations: { runs: [], proposals: [] },
        degraded: true,
        overviewAvailable: false,
      }),
    },
  );

const overview = computed(() => data.value?.overview);
const domains = computed(() => data.value?.domains ?? []);
const run = computed<AnalysisRun | null>(
  () => (overview.value?.latest_run as AnalysisRun | null | undefined) ?? null,
);
const runs = computed<AnalysisRun[]>(() => data.value?.operations.runs ?? []);
const proposals = computed<AnalysisProposal[]>(
  () => data.value?.operations.proposals ?? [],
);
const releases = computed<AnalysisRelease[]>(
  () => data.value?.models.releases ?? [],
);
const selectedDomains = ref<string[]>([]);
const runKind = ref('complete');
const costCeiling = ref<number | undefined>();
const busy = ref(false);
const message = ref('');
const messageLevel = ref<'ok' | 'bad' | 'warn'>('warn');
const proposalFilter = ref('pending');
const reasons = reactive<Record<string, string>>({});
let disposed = false;
let pollTimer: ReturnType<typeof setTimeout> | null = null;

let initializedDomains = false;
watch(
  domains,
  (items) => {
    if (!initializedDomains && items.length) {
      selectedDomains.value = items.map((item) => item.domain_id);
      initializedDomains = true;
    }
  },
  { immediate: true },
);

function value(row: Row | null | undefined, key: string): string {
  const item = row?.[key];
  if (item === null || item === undefined || item === '') return '—';
  if (Array.isArray(item)) return item.join(', ');
  if (typeof item === 'object') return JSON.stringify(item);
  return String(item);
}

function when(value_: unknown): string {
  if (!value_) return '—';
  const date = new Date(String(value_));
  return Number.isNaN(date.getTime())
    ? String(value_)
    : date.toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' });
}

function money(micros: unknown): string {
  if (micros === null || micros === undefined) return '—';
  const value_ = Number(micros);
  return Number.isFinite(value_) ? `£${(value_ / 1_000_000).toFixed(4)}` : '—';
}

function terminal(status: string | null | undefined): boolean {
  return ['cancelled', 'complete', 'failed', 'interrupted'].includes(
    status ?? '',
  );
}

function level(
  status: string | null | undefined,
): 'ok' | 'warn' | 'bad' | 'neutral' {
  if (status === 'complete' || status === 'ok') return 'ok';
  if (status === 'failed' || status === 'rolled_back') return 'bad';
  if (terminal(status)) return 'neutral';
  return 'warn';
}

function setMessage(text: string, kind: 'ok' | 'bad' | 'warn' = 'warn') {
  message.value = text;
  messageLevel.value = kind;
}

function stopPolling() {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = null;
}

async function pollRun(runId: string): Promise<void> {
  if (disposed) return;
  if (document.hidden) {
    pollTimer = setTimeout(() => {
      void pollRun(runId);
    }, 3000);
    return;
  }
  try {
    const current = await api.analysisRuns({ query: { limit: 20 } });
    if (disposed) return;
    const latest = current.runs.find((item) => item.run_id === runId);
    if (latest && data.value) data.value.overview.latest_run = latest;
    if (latest && !terminal(latest.status)) {
      pollTimer = setTimeout(() => {
        void pollRun(runId);
      }, 3000);
      return;
    }
    await refresh();
    busy.value = false;
  } catch (e) {
    busy.value = false;
    setMessage(
      e instanceof TransportError
        ? e.message
        : 'Analysis run status is unavailable.',
      'bad',
    );
  }
}

async function startRun() {
  if (busy.value || !selectedDomains.value.length) return;
  if (
    !(await dialog.confirm(
      `Queue a ${runKind.value} analysis run for ${selectedDomains.value.length} domain(s)?`,
    ))
  )
    return;
  busy.value = true;
  setMessage('Queueing analysis run…');
  try {
    const started = await api.startAnalysisRun({
      runKind: runKind.value,
      domains: selectedDomains.value,
      costCeilingMicros: costCeiling.value
        ? Math.round(costCeiling.value * 1_000_000)
        : 0,
    });
    setMessage(`Run ${started.run_id} queued.`, 'ok');
    void pollRun(started.run_id);
    await refresh();
  } catch (e) {
    busy.value = false;
    setMessage(
      e instanceof TransportError
        ? e.message
        : 'Analysis run could not be queued.',
      'bad',
    );
  }
}

async function runAction(action: 'cancel' | 'resume', runId: string) {
  if (busy.value) return;
  if (
    !(await dialog.confirm(
      `${action === 'cancel' ? 'Stop' : 'Resume'} analysis run ${runId}?`,
    ))
  )
    return;
  busy.value = true;
  try {
    await api.analysisRunAction(runId, action);
    setMessage(action === 'cancel' ? 'Stop requested.' : 'Run resumed.', 'ok');
    await refresh();
  } catch (e) {
    setMessage(
      e instanceof TransportError ? e.message : 'Analysis run action failed.',
      'bad',
    );
  } finally {
    busy.value = false;
  }
}

async function decideProposal(
  action: 'accept' | 'defer' | 'dismiss',
  proposal: AnalysisProposal,
) {
  if (busy.value) return;
  const key = `proposal:${proposal.proposal_id}:${action}`;
  const reason = await dialog.prompt(
    `Reason to ${action} this proposal (optional):`,
    reasons[key] || '',
  );
  if (reason === null) return;
  reasons[key] = reason;
  busy.value = true;
  try {
    await api.decideAnalysisProposal(
      proposal.proposal_id,
      action,
      reason || undefined,
    );
    delete reasons[key];
    toast.add({ title: `Proposal ${action}ed`, color: 'success' });
    await refresh();
  } catch (e) {
    toast.add({
      title: 'Proposal action failed',
      description: e instanceof TransportError ? e.message : String(e),
      color: 'error',
    });
  } finally {
    busy.value = false;
  }
}

async function releaseAction(
  action: 'activate' | 'rollback',
  release: AnalysisRelease,
) {
  if (busy.value) return;
  const key = `release:${release.release_id}:${action}`;
  const reason =
    action === 'rollback'
      ? await dialog.prompt(
          'Reason for rollback (optional):',
          reasons[key] || '',
        )
      : null;
  if (action === 'rollback' && reason === null) return;
  if (reason !== null) reasons[key] = reason;
  if (
    !(await dialog.confirm(
      `${action === 'activate' ? 'Activate' : 'Roll back'} release ${release.release_id}?`,
    ))
  )
    return;
  busy.value = true;
  try {
    if (action === 'activate')
      await api.activateAnalysisRelease(release.release_id);
    else
      await api.rollbackAnalysisRelease(
        release.release_id,
        reason || undefined,
      );
    delete reasons[key];
    toast.add({
      title: `${action === 'activate' ? 'Release activated' : 'Release rolled back'}`,
      color: 'success',
    });
    await refresh();
  } catch (e) {
    toast.add({
      title: 'Release action failed',
      description: e instanceof TransportError ? e.message : String(e),
      color: 'error',
    });
  } finally {
    busy.value = false;
  }
}

async function rebuildGraph(releaseId?: string) {
  if (busy.value) return;
  if (
    !(await dialog.confirm(
      `Queue graph projection${releaseId ? ` for ${releaseId}` : ''}?`,
    ))
  )
    return;
  busy.value = true;
  try {
    await api.rebuildAnalysisGraph(releaseId);
    toast.add({ title: 'Graph projection queued', color: 'success' });
    await refresh();
  } catch (e) {
    toast.add({
      title: 'Graph rebuild failed',
      description: e instanceof TransportError ? e.message : String(e),
      color: 'error',
    });
  } finally {
    busy.value = false;
  }
}

async function promoteTheme(id: string) {
  if (
    busy.value ||
    !(await dialog.confirm(
      'Promote this eligible theme to its analysis workflow? This does not publish evidence.',
    ))
  )
    return;
  busy.value = true;
  try {
    await api.promoteAnalysisTheme(id);
    await refresh();
  } catch (e) {
    setMessage(String(e), 'bad');
  } finally {
    busy.value = false;
  }
}
const filteredProposals = computed(() =>
  proposals.value.filter(
    (item) =>
      proposalFilter.value === 'all' ||
      (proposalFilter.value === 'pending'
        ? item.status === 'pending'
        : item.status !== 'pending'),
  ),
);
useAdminPolling(async () => {
  if (!busy.value && run.value?.status && !terminal(run.value.status)) {
    try {
      const current = await api.analysisOverview();
      if (data.value && !disposed) data.value.overview = current;
    } catch (e) {
      setMessage(
        e instanceof Error ? e.message : 'Run status unavailable',
        'bad',
      );
    }
  }
}, 3000);
onBeforeUnmount(() => {
  disposed = true;
  stopPolling();
});
useHead({ title: 'SectorTrace — Analysis' });
</script>

<template>
  <section class="space-y-6">
    <div>
      <h1 class="text-2xl font-semibold">Analysis platform</h1>
      <p class="mt-2 max-w-3xl text-sm opacity-70">
        Control-plane view of automated signals, releases, worker state, and
        adaptation proposals. These outputs are admin-only and are not evidence
        until a separate human workflow accepts them.
      </p>
    </div>

    <AdminLocalTabs :tabs="tabs" :current="view" />
    <div v-if="pending" class="text-sm opacity-60">
      Loading analysis platform…
    </div>
    <template v-else-if="data">
      <p v-if="data.degraded || error" class="text-sm admin-note">
        Some analysis projections are temporarily unavailable; the control plane
        is showing the data that loaded. Refresh before taking an action.
      </p>
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <UCard v-for="(count, key) in overview?.counts ?? {}" :key="key">
          <div class="text-2xl font-semibold">{{ count }}</div>
          <div class="text-xs opacity-60 capitalize">
            {{ String(key).replaceAll('_', ' ') }}
          </div>
        </UCard>
      </div>

      <UCard>
        <template #header
          ><span class="text-sm font-medium"
            >Analysis run control</span
          ></template
        >
        <div class="grid gap-4 md:grid-cols-4">
          <label class="text-sm space-y-1"
            ><span class="opacity-70">Run kind</span
            ><select
              v-model="runKind"
              class="w-full border border-black/15 dark:border-white/15 rounded px-2 py-2 bg-transparent"
            >
              <option value="complete">complete</option>
              <option value="discovery">discovery</option>
              <option value="optimization">optimization</option>
              <option value="pilot">pilot</option>
            </select></label
          >
          <label class="text-sm space-y-1"
            ><span class="opacity-70">Cost ceiling (£, optional)</span
            ><input
              v-model.number="costCeiling"
              type="number"
              min="0"
              step="0.01"
              placeholder="none"
              class="w-full border border-black/15 dark:border-white/15 rounded px-2 py-2 bg-transparent"
          /></label>
          <div class="md:col-span-2 flex items-end gap-2">
            <UButton
              color="primary"
              :disabled="busy || !selectedDomains.length"
              @click="
                () => {
                  void startRun();
                }
              "
              >{{ busy ? 'Working…' : 'Queue analysis run' }}</UButton
            ><UButton
              color="neutral"
              variant="outline"
              @click="
                () => {
                  void refresh();
                }
              "
              >Refresh</UButton
            >
          </div>
        </div>
        <div class="mt-4 flex flex-wrap gap-2">
          <label
            v-for="domain in domains"
            :key="domain.domain_id"
            class="flex items-center gap-2 text-xs border border-black/10 dark:border-white/10 rounded px-2 py-1"
            ><input
              v-model="selectedDomains"
              type="checkbox"
              :value="domain.domain_id"
            />{{ domain.domain_id }}</label
          >
        </div>
        <p
          v-if="message"
          class="mt-3 text-sm"
          :class="
            messageLevel === 'bad'
              ? 'admin-error'
              : messageLevel === 'ok'
                ? 'text-[var(--st-positive)]'
                : 'opacity-70'
          "
        >
          {{ message }}
        </p>
      </UCard>

      <UCard>
        <template #header
          ><div class="flex items-center justify-between gap-3">
            <span class="text-sm font-medium">Current run</span
            ><StatusPill
              :label="
                !data.overviewAvailable
                  ? 'Unavailable'
                  : (run?.status ?? 'No run')
              "
              :level="level(run?.status)"
            /></div
        ></template>
        <StEmptyState
          v-if="!data.overviewAvailable"
          variant="unavailable"
          title="Run status unavailable"
        />
        <StEmptyState
          v-else-if="!run"
          title="No analysis run"
          message="No analysis run has been started."
        />
        <template v-else>
          <div class="flex flex-wrap gap-3 text-sm">
            <span class="font-mono">{{ run.run_id }}</span
            ><span>{{ run.run_kind }}</span
            ><span>{{ run.current_stage ?? 'queued' }}</span
            ><span
              >{{ run.completed_domains ?? '—' }}/{{
                run.total_domains ?? '—'
              }}
              domains</span
            ><span>{{
              run.progress_percent == null
                ? 'Progress unavailable'
                : run.progress_percent + '%'
            }}</span
            ><span
              >{{ money(run.cost_micros) }} spent /
              {{ money(run.estimated_cost_micros) }} estimated</span
            >
          </div>
          <div class="mt-3 h-2 rounded bg-black/10 dark:bg-white/10">
            <div
              class="h-2 rounded bg-[var(--st-accent)]"
              :style="{
                width: `${Math.min(100, Math.max(0, run.progress_percent ?? 0))}%`,
              }"
            />
          </div>
          <p v-if="run.error_detail" class="mt-3 text-sm admin-error">
            {{ run.error_detail }}
          </p>
          <div class="mt-4 flex gap-2">
            <UButton
              v-if="run.status && !terminal(run.status)"
              color="neutral"
              variant="outline"
              :disabled="busy"
              @click="runAction('cancel', run.run_id)"
              >Stop run</UButton
            ><UButton
              v-if="
                run.status === 'cancelled' ||
                run.status === 'failed' ||
                run.status === 'interrupted'
              "
              color="primary"
              :disabled="busy"
              @click="runAction('resume', run.run_id)"
              >Resume</UButton
            >
          </div>
        </template>
      </UCard>

      <UCard v-if="view === 'runs'"
        ><template #header
          ><span class="text-sm font-medium">Analysis domains</span></template
        ><AdminTable
          :columns="[
            { key: 'domain_id', label: 'Domain', mono: true },
            { key: 'status', label: 'Status' },
            { key: 'prerequisite_status', label: 'Prerequisites' },
            { key: 'rows_processed', label: 'Processed', numeric: true },
            { key: 'rows_written', label: 'Written', numeric: true },
          ]"
          :rows="domains"
          row-key="domain_id"
      /></UCard>

      <div v-if="view === 'outputs'" class="grid gap-6 lg:grid-cols-2">
        <UCard
          ><template #header
            ><span class="text-sm font-medium"
              >Emerging themes ({{ data.themes.length }})</span
            ></template
          >
          <ul
            v-if="data.themes.length"
            class="divide-y divide-black/5 dark:divide-white/5 text-sm"
          >
            <li
              v-for="(item, i) in data.themes"
              :key="i"
              class="py-2 flex items-center justify-between gap-3"
            >
              <span
                ><strong>{{ value(item, 'theme_key') }}</strong> ·
                {{ value(item, 'status') }} ·
                {{ value(item, 'passage_count') }} passages</span
              ><UButton
                v-if="item.status === 'promotion_ready'"
                size="xs"
                color="primary"
                @click="promoteTheme(String(item.theme_id))"
                >Promote</UButton
              >
            </li>
          </ul>
          <StEmptyState v-else title="No emerging themes"
        /></UCard>
      </div>

      <UCard v-if="view === 'proposals'"
        ><template #header
          ><div class="flex items-center justify-between gap-3">
            <span class="text-sm font-medium">Adaptation proposals</span
            ><select
              v-model="proposalFilter"
              class="text-xs border border-black/15 dark:border-white/15 rounded px-2 py-1 bg-transparent"
            >
              <option value="pending">Pending</option>
              <option value="all">All</option>
              <option value="decided">Decided</option>
            </select>
          </div></template
        ><StEmptyState v-if="!filteredProposals.length" title="No proposals" />
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr
                class="text-left border-b border-black/15 dark:border-white/15"
              >
                <th class="py-2 pr-4">Proposal</th>
                <th class="py-2 pr-4">Scope</th>
                <th class="py-2 pr-4">Status</th>
                <th class="py-2">Decision</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="proposal in filteredProposals"
                :key="proposal.proposal_id"
                class="border-b border-black/5 dark:border-white/5 align-top"
              >
                <td class="py-2 pr-4">
                  <div class="font-medium">{{ proposal.proposal_type }}</div>
                  <div class="font-mono text-xs opacity-60">
                    {{ proposal.proposal_id }}
                  </div>
                  <div class="text-xs opacity-60">
                    {{ when(proposal.created_at) }}
                  </div>
                  <details>
                    <summary>View trigger</summary>
                    <AdminRecord :value="proposal" />
                  </details>
                </td>
                <td class="py-2 pr-4">
                  {{ proposal.domain_id ?? 'All domains' }}
                  <div class="text-xs opacity-60">
                    {{ proposal.automatic_action ?? '—' }}
                  </div>
                </td>
                <td class="py-2 pr-4">
                  <StatusPill
                    :label="proposal.status ?? 'pending'"
                    :level="level(proposal.status)"
                  />
                </td>
                <td class="py-2">
                  <div v-if="proposal.status === 'pending'" class="flex gap-2">
                    <UButton
                      size="xs"
                      color="primary"
                      @click="decideProposal('accept', proposal)"
                      >Accept</UButton
                    ><UButton
                      size="xs"
                      color="neutral"
                      variant="outline"
                      @click="decideProposal('defer', proposal)"
                      >Defer</UButton
                    ><UButton
                      size="xs"
                      color="error"
                      variant="outline"
                      @click="decideProposal('dismiss', proposal)"
                      >Dismiss</UButton
                    >
                  </div>
                  <span v-else class="text-xs opacity-60">{{
                    proposal.admin_reason ?? 'Decision recorded'
                  }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div></UCard
      >

      <UCard v-if="view === 'releases'"
        ><template #header
          ><span class="text-sm font-medium">Releases</span></template
        ><StEmptyState v-if="!releases.length" title="No releases" />
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr
                class="text-left border-b border-black/15 dark:border-white/15"
              >
                <th class="py-2 pr-4">Created</th>
                <th class="py-2 pr-4">Release</th>
                <th class="py-2 pr-4">Status</th>
                <th class="py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="release in releases"
                :key="release.release_id"
                class="border-b border-black/5 dark:border-white/5"
              >
                <td class="py-2 pr-4">{{ when(release.created_at) }}</td>
                <td class="py-2 pr-4 font-mono text-xs">
                  {{ release.release_id }}
                  <div class="opacity-60">{{ release.manifest_sha256 }}</div>
                </td>
                <td class="py-2 pr-4">
                  <StatusPill
                    :label="release.status ?? 'unknown'"
                    :level="level(release.status)"
                  />
                </td>
                <td class="py-2">
                  <div class="flex flex-wrap gap-2">
                    <UButton
                      v-if="
                        release.status !== 'active' &&
                        release.status !== 'rolled_back'
                      "
                      size="xs"
                      color="primary"
                      @click="releaseAction('activate', release)"
                      >Activate</UButton
                    ><UButton
                      v-if="release.status !== 'rolled_back'"
                      size="xs"
                      color="error"
                      variant="outline"
                      @click="releaseAction('rollback', release)"
                      >Rollback</UButton
                    ><UButton
                      size="xs"
                      color="neutral"
                      variant="outline"
                      @click="rebuildGraph(release.release_id)"
                      >Queue graph</UButton
                    ><a
                      :href="`/api/admin/analysis/reports/${encodeURIComponent(release.release_id)}`"
                      class="text-xs text-[var(--st-accent)] underline self-center"
                      >JSON</a
                    ><a
                      :href="`/api/admin/analysis/reports/${encodeURIComponent(release.release_id)}?format=csv`"
                      class="text-xs underline"
                      >CSV</a
                    ><a
                      :href="`/api/admin/analysis/reports/${encodeURIComponent(release.release_id)}?format=html`"
                      target="_blank"
                      rel="noopener"
                      class="text-xs underline"
                      >Printable HTML</a
                    >
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div></UCard
      >

      <template v-if="view === 'runs'"
        ><section class="admin-panel">
          <h2>Run history</h2>
          <AdminRows
            :rows="runs"
            :columns="[
              'run_id',
              'run_kind',
              'status',
              'started_at',
              'current_stage',
            ]"
            ><template #actions="{ row }"
              ><UButton
                size="xs"
                color="neutral"
                variant="outline"
                @click="selectedRun = row.run_id"
                >Inspect run</UButton
              ><UButton
                v-if="
                  ['cancelled', 'failed', 'interrupted'].includes(row.status)
                "
                size="xs"
                :disabled="busy"
                @click="runAction('resume', row.run_id)"
                >Resume</UButton
              ></template
            ></AdminRows
          >
        </section>
        <LazyAdminResourcePanel
          v-if="selectedRun"
          title="Run detail"
          :path="`/api/admin/analysis/runs/${encodeURIComponent(selectedRun)}`"
      /></template>
      <template v-if="view === 'outputs'"
        ><div class="admin-filters">
          <label
            >Output<select v-model="output">
              <option
                v-for="name in [
                  'signals',
                  'structured',
                  'topics',
                  'themes',
                  'links',
                  'entities',
                  'coverage',
                  'prevalence',
                  'graph',
                ]"
                :key="name"
              >
                {{ name }}
              </option>
            </select></label
          ><label>Domain<input v-model.lazy="outputDomain" /></label
          ><label>Release<input v-model.lazy="outputRelease" /></label>
        </div>
        <LazyAdminResourcePanel
          :key="output"
          :title="'Inspect ' + output"
          :path="'/api/admin/analysis/' + output"
          :query="{
            limit: 100,
            domain_id: outputDomain,
            release_id: outputRelease,
          }"
        /><UButton
          v-if="output === 'graph'"
          color="neutral"
          variant="outline"
          :disabled="busy"
          @click="rebuildGraph(outputRelease || undefined)"
          >Queue graph projection</UButton
        ></template
      >
      <LazyAdminResourcePanel
        v-if="view === 'models'"
        title="Model calls, input manifests and operational gates"
        path="/api/admin/analysis/operations"
      />
      <LazyAdminResourcePanel
        v-if="view === 'releases'"
        title="Release manifests and program versions"
        path="/api/admin/analysis/models"
      />
      <p class="text-xs opacity-60">{{ overview?.quality_boundary }}</p>
    </template>
    <StEmptyState v-else variant="unavailable" />
  </section>
</template>
