<script setup lang="ts">
import { computed } from 'vue'
import type {
  CandidateCountsResponse,
  CockpitResponse,
  HealthResponse,
  MissionControlResponse,
} from '~/types/admin'

// Mission control is a read model, not a second source of truth. The overview
// combines the small health/count payloads with the two existing operator
// workspaces so an operator can see what needs attention without opening three
// separate tabs. Every action card links to the workflow that makes the next
// decision; this page never decides or ranks evidence itself.
const api = useAdminApi()

const { data: health, pending: healthPending } = await useAsyncData<HealthResponse | null>(
  'admin-overview-health',
  () => api.health(),
  { default: () => null },
)
const { data: counts, pending: countsPending } = await useAsyncData<CandidateCountsResponse | null>(
  'admin-overview-counts',
  () => api.candidateCounts(),
  { default: () => null },
)
const { data: cockpit, pending: cockpitPending, error: cockpitError } = await useAsyncData<CockpitResponse | null>(
  'admin-overview-cockpit',
  () => api.cockpit(),
  { default: () => null },
)
const { data: mission, pending: missionPending, error: missionError } = await useAsyncData<MissionControlResponse | null>(
  'admin-overview-mission-control',
  () => api.missionControl(),
  { default: () => null },
)

const unapplied = computed(() => health.value?.warehouse?.unapplied ?? [])
const totalUndecided = computed(() => {
  const kinds = counts.value?.kinds ?? {}
  return Object.values(kinds).reduce((sum, k) => sum + (k.undecided ?? 0), 0)
})
const cards = computed(() => cockpit.value?.cards ?? [])
const waves = computed(() => mission.value?.waves ?? [])
const failures = computed(() => mission.value?.failure_summary ?? [])

function pathFor(link: string | null | undefined): string {
  if (!link) return '/'
  if (link.startsWith('#/')) return link.slice(1)
  if (link.startsWith('#')) return `/${link.slice(1)}`
  return link
}

function levelForPriority(priority: number): 'ok' | 'warn' | 'bad' | 'neutral' {
  if (priority >= 3) return 'bad'
  if (priority === 2) return 'warn'
  if (priority === 1) return 'neutral'
  return 'ok'
}

function statusLevel(status: string | null | undefined): 'ok' | 'warn' | 'bad' | 'neutral' {
  if (status === 'ok' || status === 'complete') return 'ok'
  if (status === 'failed') return 'bad'
  if (status === 'running' || status === 'queued' || status === 'pending') return 'warn'
  return 'neutral'
}

function when(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
}

useHead({ title: 'SectorTrace — Operations' })
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Mission control</h1>
      <p class="text-sm opacity-70 max-w-3xl">
        Operational state only: review pressure, run health, schema drift and
        coverage actions. Follow a card to inspect the underlying workflow;
        this overview never makes an evidence decision for you.
      </p>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <UCard>
        <div class="text-xs uppercase tracking-wide opacity-60">Backend</div>
        <div class="text-lg font-medium">{{ healthPending ? '…' : (health?.warehouse?.backend ?? '—') }}</div>
      </UCard>
      <UCard>
        <div class="text-xs uppercase tracking-wide opacity-60">Unapplied migrations</div>
        <div class="text-lg font-medium"><StatusPill :label="healthPending ? '…' : unapplied.length" :level="unapplied.length ? 'warn' : 'ok'" /></div>
      </UCard>
      <UCard>
        <div class="text-xs uppercase tracking-wide opacity-60">Undecided candidates</div>
        <div class="text-lg font-medium"><StatusPill :label="countsPending ? '…' : totalUndecided" :level="totalUndecided ? 'warn' : 'neutral'" /></div>
      </UCard>
      <UCard>
        <div class="text-xs uppercase tracking-wide opacity-60">Extensions</div>
        <div class="text-lg font-medium">{{ healthPending ? '…' : (health?.extensions?.filter((e) => e.installed).length ?? 0) }} installed</div>
      </UCard>
    </div>

    <UCard>
      <template #header>
        <div class="flex items-center justify-between gap-3">
          <div>
            <h2 class="font-medium">What needs attention</h2>
            <p class="text-xs opacity-60">Prioritised operational states from the existing cockpit API.</p>
          </div>
          <StatusPill
            :label="cockpitPending ? '…' : `${cockpit?.attention ?? 0} attention`"
            :level="(cockpit?.top_priority ?? 0) >= 3 ? 'bad' : (cockpit?.top_priority ?? 0) >= 2 ? 'warn' : 'ok'"
          />
        </div>
      </template>
      <div v-if="cockpitPending" class="text-sm opacity-60">Loading operational actions…</div>
      <StEmptyState v-else-if="cockpitError" variant="unavailable" />
      <div v-else class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <NuxtLink
          v-for="card in cards"
          :key="card.key"
          :to="pathFor(card.link)"
          class="rounded-lg border border-black/10 dark:border-white/10 p-4 space-y-2 hover:border-[var(--st-accent)] hover:bg-[var(--st-accent)]/5"
        >
          <div class="flex items-start justify-between gap-3">
            <span class="font-medium">{{ card.title }}</span>
            <StatusPill :label="card.priority >= 3 ? 'act now' : card.priority === 2 ? 'soon' : card.priority === 1 ? 'watch' : 'clear'" :level="levelForPriority(card.priority)" />
          </div>
          <div class="text-2xl font-semibold tabular-nums">{{ card.metric.toLocaleString('en-GB') }}</div>
          <p class="text-sm opacity-70">{{ card.reason }}</p>
          <span class="text-xs text-[var(--st-accent)]">Open workflow →</span>
        </NuxtLink>
      </div>
    </UCard>

    <UCard>
      <template #header>
        <div class="flex items-center justify-between gap-3">
          <div>
            <h2 class="font-medium">Pipeline mission control</h2>
            <p class="text-xs opacity-60">Module dependency waves, current run state and recent failures.</p>
          </div>
          <NuxtLink to="/pipeline" class="text-sm text-[var(--st-accent)] underline underline-offset-2">Open pipeline →</NuxtLink>
        </div>
      </template>
      <div v-if="missionPending" class="text-sm opacity-60">Loading pipeline state…</div>
      <StEmptyState v-else-if="missionError" variant="unavailable" />
      <template v-else>
        <div class="flex flex-wrap items-center gap-2 text-sm mb-4">
          <StatusPill :label="mission?.active ? `running · #${mission.active.id}` : 'no active run'" :level="mission?.active ? 'warn' : 'neutral'" />
          <StatusPill v-if="mission?.queued?.length" :label="`${mission.queued.length} queued`" level="warn" />
          <span v-if="mission?.last_run" class="opacity-60">Last run: {{ mission.last_run.origin ?? 'unknown' }} · {{ mission.last_run.status ?? '—' }} · {{ when(mission.last_run.finished_at ?? mission.last_run.started_at) }}</span>
          <span v-else class="opacity-60">No durable run recorded yet.</span>
        </div>

        <div class="space-y-4">
          <div v-for="wave in waves" :key="wave.wave">
            <h3 class="text-sm font-medium mb-2">Wave {{ wave.wave }}</h3>
            <div class="flex flex-wrap gap-2">
              <div v-for="module in wave.modules" :key="module.name" class="rounded border border-black/10 dark:border-white/10 px-2 py-1 text-xs">
                <span class="font-mono">{{ module.name }}</span>
                <StatusPill :label="module.last_run?.status ?? (mission?.never_run?.includes(module.name) ? 'never' : 'idle')" :level="statusLevel(module.last_run?.status)" />
                <StatusPill v-if="module.pending_review" :label="`${module.pending_review} review`" level="warn" />
                <StatusPill v-if="module.parse_failures" :label="`${module.parse_failures} failures`" level="bad" />
                <StatusPill v-if="module.missing_dependencies?.length" label="deps" level="bad" />
              </div>
            </div>
          </div>
        </div>

        <div v-if="failures.length" class="mt-5 overflow-x-auto">
          <h3 class="text-sm font-medium mb-2">Needs attention</h3>
          <table class="w-full text-sm border-collapse">
            <thead><tr class="text-left border-b border-black/15 dark:border-white/15"><th class="py-2 pr-4">Module</th><th class="py-2 pr-4">Parse failures</th><th class="py-2 pr-4">Review</th><th class="py-2">Last status</th></tr></thead>
            <tbody>
              <tr v-for="failure in failures" :key="failure.module" class="border-b border-black/5 dark:border-white/5">
                <td class="py-2 pr-4 font-mono text-xs">{{ failure.module }}</td>
                <td class="py-2 pr-4">{{ failure.parse_failures.toLocaleString('en-GB') }}</td>
                <td class="py-2 pr-4">{{ failure.pending_review.toLocaleString('en-GB') }}</td>
                <td class="py-2"><StatusPill :label="failure.last_status ?? '—'" :level="statusLevel(failure.last_status)" /></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="mt-5 text-sm opacity-60">No modules need attention.</p>
      </template>
    </UCard>

    <div class="flex flex-wrap gap-2">
      <NuxtLink v-for="item in [{ to: '/review', label: 'Review queue' }, { to: '/candidates', label: 'Candidates' }, { to: '/health', label: 'Full health' }]" :key="item.to" :to="item.to" class="text-sm border border-black/15 dark:border-white/15 rounded px-3 py-1 hover:bg-black/5 dark:hover:bg-white/5">{{ item.label }} →</NuxtLink>
    </div>
  </section>
</template>
