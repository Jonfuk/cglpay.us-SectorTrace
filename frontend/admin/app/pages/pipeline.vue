<script setup lang="ts">
const dialog = useAdminDialog();
import { computed, onBeforeUnmount, ref } from 'vue';
import type { Column } from '~/components/AdminTable.vue';
import { TransportError } from '~/lib/transport';
import type {
  JobDetail,
  JobHead,
  JobsResponse,
  ModuleRow,
  ModulesResponse,
  RunRow,
  RunsResponse,
} from '~/types/admin';

// The pipeline page is a console, not a read-only dashboard. Browser-started
// runs use the same server job and runner as the CLI; the bounded log window
// keeps long crawls usable without growing the DOM without limit.
const api = useAdminApi();
const route = useRoute();
const view = computed(() => String(route.query.view || 'modules'));
const tabs = [
  { key: 'modules', label: 'Modules' },
  { key: 'jobs', label: 'Jobs & logs' },
  { key: 'waves', label: 'Dependency waves' },
  { key: 'history', label: 'Run ledger' },
  { key: 'compare', label: 'Compare runs' },
];
const logCursor = ref(-1);
async function follow(id: number) {
  clearPoll();
  logCursor.value = -1;
  currentJob.value = null;
  await pollJob(id);
}

const {
  data: modulesData,
  pending: modulesPending,
  error: modulesError,
  refresh: refreshModules,
} = await useAsyncData<ModulesResponse | null>(
  'admin-modules',
  () => api.modules(),
  { default: () => null },
);
const {
  data: jobsData,
  pending: jobsPending,
  error: jobsError,
  refresh: refreshJobs,
} = await useAsyncData<JobsResponse | null>('admin-jobs', () => api.jobs(), {
  default: () => null,
});
const {
  data: runsData,
  pending: runsPending,
  error: runsError,
  refresh: refreshRuns,
} = await useAsyncData<RunsResponse | null>(
  'admin-run-ledger',
  () => api.runLedger(),
  { default: () => null },
);

const modules = computed<ModuleRow[]>(() => modulesData.value?.modules ?? []);
const jobs = computed<JobHead[]>(() => jobsData.value?.jobs ?? []);
const runs = computed<RunRow[]>(() => runsData.value?.runs ?? []);
const selectedModule = ref(String(route.query.module || 'all'));
const since = ref('');
const limit = ref<number | undefined>();
const workers = ref<number | undefined>();
const dryRun = ref(false);
const busy = ref(false);
const status = ref('');
const statusLevel = ref<'ok' | 'warn' | 'bad'>('warn');
const currentJob = ref<JobDetail | null>(null);
let disposed = false;
let pollTimer: ReturnType<typeof setTimeout> | null = null;

function when(value: string | null | undefined): string {
  return value
    ? value.replace('T', ' ').replace(/\.\d+/, '').replace('+00:00', 'Z')
    : '—';
}

function failureCount(job: JobDetail | null): number {
  return job?.summary?.filter((row) => row.status === 'failed').length ?? 0;
}

function showError(error: unknown, fallback: string) {
  status.value = error instanceof TransportError ? error.message : fallback;
  statusLevel.value = 'bad';
}

function clearPoll() {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = null;
}

async function refreshAll() {
  await Promise.all([refreshModules(), refreshJobs(), refreshRuns()]);
}

async function pollJob(id: number): Promise<void> {
  if (disposed) return;
  if (document.hidden) {
    pollTimer = setTimeout(() => {
      void pollJob(id);
    }, 3000);
    return;
  }
  try {
    const job = await api.job(id, {
      noDedup: true,
      query: { after: logCursor.value },
    });
    if (disposed) return;
    const lines = currentJob.value?.id === id ? currentJob.value.log || [] : [];
    currentJob.value = {
      ...job,
      log: [...lines, ...(job.log || [])].slice(-500),
    };
    logCursor.value = job.next ?? logCursor.value;
    if (job.running || job.state === 'queued' || job.state === 'pending') {
      pollTimer = setTimeout(() => {
        void pollJob(id);
      }, 1000);
      return;
    }
    busy.value = false;
    status.value =
      job.state === 'failed'
        ? (job.error ?? 'Pipeline job failed.')
        : `${job.label ?? 'Pipeline job'} finished.`;
    statusLevel.value = job.state === 'failed' ? 'bad' : 'ok';
    await refreshAll();
  } catch (error) {
    busy.value = false;
    showError(error, 'The job could not be followed.');
  }
}

async function start(module: string, isDryRun = dryRun.value) {
  if (busy.value) return;
  if (
    module === 'all' &&
    !isDryRun &&
    !(await dialog.confirm(
      `Run all ${modules.value.length} modules against live public sources?\n\nThis is a full crawl and may take hours.`,
    ))
  )
    return;

  busy.value = true;
  status.value = isDryRun ? 'Starting dry run…' : 'Starting live run…';
  statusLevel.value = 'warn';
  currentJob.value = null;
  logCursor.value = -1;
  clearPoll();
  try {
    const job = await api.startRun({
      module,
      since: since.value.trim() || undefined,
      limit: limit.value,
      jobs: workers.value,
      dryRun: isDryRun,
    });
    currentJob.value = job;
    status.value = `Following job #${job.id}.`;
    void pollJob(job.id);
    await refreshJobs();
  } catch (error) {
    busy.value = false;
    showError(error, 'The pipeline run could not be started.');
    if (error instanceof TransportError && error.status === 409) {
      const body = error.body as Record<string, unknown> | undefined;
      const existing =
        typeof body?.job_id === 'number' ? body.job_id : undefined;
      if (existing) {
        status.value = `Another job is running; following #${existing}.`;
        busy.value = true;
        void pollJob(existing);
      }
    }
  }
}

const moduleColumns: Column<ModuleRow>[] = [
  { key: 'name', label: 'Module', mono: true },
  { key: 'wave', label: 'Wave', numeric: true },
  { key: 'cursor_value', label: 'Cursor', mono: true },
  { key: 'pending_review', label: 'Queue', numeric: true },
  { key: 'parse_failures', label: 'Failures', numeric: true },
];
const jobColumns: Column<JobHead>[] = [
  { key: 'id', label: 'ID', mono: true },
  { key: 'kind', label: 'Kind' },
  { key: 'label', label: 'Label' },
  { key: 'state', label: 'State' },
  { key: 'started_at', label: 'Started', mono: true },
];
const runColumns: Column<RunRow>[] = [
  { key: 'started_at', label: 'Started', mono: true },
  { key: 'origin', label: 'Origin' },
  { key: 'status', label: 'Status' },
  { key: 'modules_ok', label: 'OK', numeric: true },
  { key: 'modules_failed', label: 'Failed', numeric: true },
];

onBeforeUnmount(() => {
  disposed = true;
  clearPoll();
});
useHead({ title: 'SectorTrace — Pipeline' });
</script>

<template>
  <section class="space-y-6">
    <div>
      <h1 class="text-2xl font-semibold">Pipeline</h1>
      <p class="mt-2 max-w-3xl text-sm opacity-70">
        Start the same runner used by the CLI, monitor its bounded log, and see
        the cursor, review debt, and parse failures for every registered module.
        Live runs fetch public sources and may take hours.
      </p>
    </div>

    <UCard>
      <template #header
        ><span class="text-sm font-medium">Run controls</span></template
      >
      <div class="grid gap-4 md:grid-cols-4">
        <label class="text-sm space-y-1 md:col-span-2">
          <span class="opacity-70">Module</span>
          <select
            v-model="selectedModule"
            class="w-full border border-black/15 dark:border-white/15 rounded px-2 py-2 bg-transparent"
          >
            <option value="all">all modules (dependency order)</option>
            <option
              v-for="module in modules"
              :key="module.name"
              :value="module.name"
            >
              {{ module.name }}
            </option>
          </select>
        </label>
        <label class="text-sm space-y-1">
          <span class="opacity-70">Since (optional)</span>
          <input
            v-model="since"
            type="date"
            class="w-full border border-black/15 dark:border-white/15 rounded px-2 py-2 bg-transparent"
          />
        </label>
        <label class="text-sm space-y-1">
          <span class="opacity-70">Limit (optional)</span>
          <input
            v-model.number="limit"
            type="number"
            min="1"
            placeholder="all"
            class="w-full border border-black/15 dark:border-white/15 rounded px-2 py-2 bg-transparent"
          />
        </label>
        <label class="text-sm space-y-1">
          <span class="opacity-70">Workers (optional)</span>
          <input
            v-model.number="workers"
            type="number"
            min="1"
            placeholder="1"
            class="w-full border border-black/15 dark:border-white/15 rounded px-2 py-2 bg-transparent"
          />
        </label>
        <label class="flex items-center gap-2 text-sm md:col-span-2">
          <input
            v-model="dryRun"
            type="checkbox"
            class="accent-[var(--st-accent)]"
          />
          Dry run — fetch and parse without writing evidence
        </label>
        <div class="flex flex-wrap gap-2 md:col-span-2 md:justify-end">
          <UButton
            color="neutral"
            variant="outline"
            :disabled="busy"
            @click="start(selectedModule, true)"
            >Dry run</UButton
          >
          <UButton
            color="primary"
            :disabled="busy"
            @click="start(selectedModule, dryRun)"
            >{{ dryRun ? 'Start dry run' : 'Run now' }}</UButton
          >
        </div>
      </div>
      <p
        v-if="status"
        class="mt-4 text-sm"
        :class="
          statusLevel === 'bad'
            ? 'admin-error'
            : statusLevel === 'ok'
              ? 'text-[var(--st-positive)]'
              : 'opacity-70'
        "
      >
        {{ status }}
      </p>
    </UCard>

    <UCard v-if="currentJob">
      <template #header>
        <div class="flex items-center justify-between gap-3">
          <span class="text-sm font-medium"
            >Job #{{ currentJob.id }} · {{ currentJob.label }}</span
          >
          <StatusPill
            :label="currentJob.state ?? 'unknown'"
            :level="
              currentJob.state === 'failed'
                ? 'bad'
                : currentJob.running
                  ? 'warn'
                  : 'ok'
            "
          />
        </div>
      </template>
      <div class="grid gap-4 md:grid-cols-3 text-sm">
        <div>
          <span class="opacity-60">Started</span>
          <div class="font-mono text-xs">{{ when(currentJob.started_at) }}</div>
        </div>
        <div>
          <span class="opacity-60">Finished</span>
          <div class="font-mono text-xs">
            {{ when(currentJob.finished_at) }}
          </div>
        </div>
        <div>
          <span class="opacity-60">Result</span>
          <div>
            {{
              failureCount(currentJob)
                ? `${failureCount(currentJob)} module failures`
                : currentJob.running
                  ? 'Running…'
                  : !Array.isArray(currentJob.summary)
                    ? 'Summary unavailable'
                    : 'No module failures'
            }}
          </div>
        </div>
      </div>
      <p v-if="currentJob.error" class="mt-4 text-sm admin-error">
        {{ currentJob.error }}
      </p>
      <AdminLog
        v-if="currentJob.log?.length"
        :text="
          currentJob.log
            .map((line) => `${when(line.at)} ${line.text}`)
            .join('\n')
        "
      />
    </UCard>

    <AdminLocalTabs :tabs="tabs" :current="view" />
    <UCard v-if="view === 'modules'">
      <template #header
        ><span class="text-sm font-medium"
          >Registered modules ({{ modules.length }})</span
        ></template
      >
      <div v-if="modulesPending" class="text-sm opacity-60">
        Loading module registry…
      </div>
      <StEmptyState v-else-if="modulesError" variant="unavailable" />
      <template v-else>
        <AdminRows
          v-if="modules.length"
          :columns="moduleColumns.map((c) => c.key)"
          :rows="modules"
          ><template #actions="{ row }"
            ><div class="admin-actions">
              <UButton size="xs" :disabled="busy" @click="start(row.name)"
                >Run</UButton
              ><UButton
                size="xs"
                color="neutral"
                variant="outline"
                :disabled="busy"
                @click="start(row.name, true)"
                >Dry run</UButton
              >
            </div></template
          ></AdminRows
        >
        <StEmptyState v-else title="No modules registered" />
        <div v-if="modules.length" class="mt-4 flex flex-wrap gap-2">
          <UButton
            size="sm"
            color="neutral"
            variant="outline"
            :disabled="busy"
            @click="start('all', true)"
            >Dry run all</UButton
          >
          <UButton
            size="sm"
            color="primary"
            :disabled="busy"
            @click="start('all', false)"
            >Run all</UButton
          >
        </div>
      </template>
    </UCard>

    <UCard v-if="view === 'jobs'">
      <template #header
        ><span class="text-sm font-medium"
          >Jobs<span v-if="jobsData?.running">
            · running #{{ jobsData.running }}</span
          ></span
        ></template
      >
      <div v-if="jobsPending" class="text-sm opacity-60">Loading jobs…</div>
      <StEmptyState v-else-if="jobsError" variant="unavailable" /><AdminRows
        v-else-if="jobs.length"
        :columns="jobColumns.map((c) => c.key)"
        :rows="jobs"
        ><template #actions="{ row }"
          ><UButton
            size="xs"
            color="neutral"
            variant="outline"
            @click="follow(row.id)"
            >Follow job</UButton
          ></template
        ></AdminRows
      >
      <StEmptyState
        v-else
        title="No jobs"
        message="No jobs have run in this process."
      />
    </UCard>

    <UCard v-if="view === 'history'">
      <template #header
        ><span class="text-sm font-medium">Recent runs</span></template
      >
      <div v-if="runsPending" class="text-sm opacity-60">
        Loading run ledger…
      </div>
      <StEmptyState v-else-if="runsError" variant="unavailable" /><AdminTable
        v-else-if="runs.length"
        :columns="runColumns"
        :rows="runs"
        row-key="run_id"
      />
      <StEmptyState v-else title="No runs recorded" />
    </UCard>
    <LazyAdminRunComparison v-if="view === 'compare'" />
    <LazyAdminResourcePanel
      v-if="view === 'waves'"
      title="Dependency waves and current state"
      path="/api/admin/mission-control"
    />
  </section>
</template>
