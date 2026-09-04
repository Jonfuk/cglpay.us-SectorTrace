<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type {
  CoverageResponse,
  FailuresResponse,
  FreshnessRow,
  HealthResponse,
  JobDetail,
  StorageRow,
} from '~/types/admin'

// Health deliberately keeps the slower archive/freshness scans separate from
// the cheap warehouse payload. They are still available on this page, but an
// operator does not pay several seconds of filesystem/table scans just to
// check migrations and extensions.
const api = useAdminApi()
const coverageTier = ref('upper')
const coverageFilter = ref('')
const freshness = ref<FreshnessRow[] | null>(null)
const storage = ref<StorageRow[] | null>(null)
const failures = ref<FailuresResponse | null>(null)
const scanBusy = ref<string | null>(null)
const integrityResult = ref('')

const { data, pending, error, refresh } = await useAsyncData<HealthResponse | null>(
  'admin-health',
  () => api.health(),
  { default: () => null },
)
const { data: coverage, pending: coveragePending, refresh: refreshCoverage } = await useAsyncData<CoverageResponse | null>(
  'admin-health-coverage',
  () => api.coverage({ query: { tier: coverageTier.value } }),
  { default: () => null },
)

const extensions = computed(() => data.value?.extensions ?? [])
const unapplied = computed(() => data.value?.warehouse?.unapplied ?? [])
const authorityRows = computed(() => {
  const query = coverageFilter.value.trim().toLowerCase()
  return (coverage.value?.authorities ?? []).filter((row) => !query
    || row.name.toLowerCase().includes(query)
    || row.ons_code.toLowerCase().includes(query)
    || (row.region ?? '').toLowerCase().includes(query))
})

watch(coverageTier, () => { void refreshCoverage() })

async function loadFreshness() {
  scanBusy.value = 'freshness'
  try { freshness.value = (await api.freshness()).freshness }
  finally { scanBusy.value = null }
}

async function loadStorage() {
  scanBusy.value = 'storage'
  try { storage.value = (await api.storage()).storage }
  finally { scanBusy.value = null }
}

async function loadFailures() {
  scanBusy.value = 'failures'
  try { failures.value = await api.failures({ query: { limit: 30 } }) }
  finally { scanBusy.value = null }
}

async function runIntegrity() {
  if (scanBusy.value) return
  scanBusy.value = 'integrity'
  integrityResult.value = 'checking…'
  try {
    let job: JobDetail = await api.startIntegrityCheck()
    while (job.running || job.state === 'queued' || job.state === 'pending') {
      await new Promise((resolve) => setTimeout(resolve, 700))
      job = await api.job(job.id)
    }
    const outcome = job.summary?.[0]
    integrityResult.value = job.state === 'failed'
      ? (job.error ?? 'Integrity check failed')
      : outcome?.checked
        ? `No problems found in ${String(outcome.checked)}`
        : 'Integrity check completed.'
    await refresh()
  } catch (e) {
    integrityResult.value = e instanceof Error ? e.message : String(e)
  } finally { scanBusy.value = null }
}

function value(record: Record<string, unknown> | undefined, key: string): string {
  const item = record?.[key]
  return item === null || item === undefined || item === '' ? '—' : String(item)
}

function bytes(n: number | undefined): string {
  if (!n) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = n
  let i = 0
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(i ? 1 : 0)} ${units[i]}`
}

useHead({ title: 'SectorTrace — Health' })
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold">Health</h1>

    <div v-if="pending" class="text-sm opacity-60">Loading health…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <UCard>
        <template #header><span class="text-sm font-medium">Warehouse</span></template>
        <dl class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div><dt class="opacity-60">Backend</dt><dd class="font-mono">{{ data?.warehouse?.backend ?? '—' }}</dd></div>
          <div><dt class="opacity-60">Applied migrations</dt><dd class="font-mono">{{ data?.warehouse?.applied_migrations?.length ?? '—' }}</dd></div>
          <div><dt class="opacity-60">Unapplied</dt><dd><StatusPill :label="unapplied.length" :level="unapplied.length ? 'warn' : 'ok'" /></dd></div>
          <div><dt class="opacity-60">Size</dt><dd class="font-mono">{{ bytes(data?.warehouse?.bytes) }}</dd></div>
        </dl>
        <p v-if="unapplied.length" class="mt-4 text-sm text-amber-700 dark:text-amber-400">Not applied to this warehouse: {{ unapplied.join(', ') }}</p>
      </UCard>

      <UCard>
        <template #header><span class="text-sm font-medium">Extensions and derived structures</span></template>
        <div class="flex flex-wrap gap-2">
          <StatusPill v-for="ext in extensions" :key="ext.name" :label="`${ext.name}: ${ext.installed ? 'installed' : 'missing'}`" :level="ext.installed ? 'ok' : 'bad'" />
        </div>
        <dl v-if="data?.graph || data?.documents" class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mt-5">
          <div v-if="data?.graph"><dt class="opacity-60">Graph run</dt><dd>{{ value(data.graph, 'last_run') }}</dd></div>
          <div v-if="data?.graph"><dt class="opacity-60">Graph entities</dt><dd>{{ value(data.graph, 'entity_count') }}</dd></div>
          <div v-if="data?.documents"><dt class="opacity-60">Documents parsed</dt><dd>{{ value(data.documents, 'parsed') }}</dd></div>
          <div v-if="data?.documents"><dt class="opacity-60">Documents failed</dt><dd>{{ value(data.documents, 'failed') }}</dd></div>
        </dl>
      </UCard>

      <UCard>
        <template #header>
          <div class="flex items-center justify-between gap-3"><span class="text-sm font-medium">Operational checks</span><StatusPill v-if="integrityResult" :label="integrityResult" :level="integrityResult.toLowerCase().includes('failed') ? 'bad' : 'ok'" /></div>
        </template>
        <div class="flex flex-wrap gap-2">
          <UButton size="sm" :loading="scanBusy === 'integrity'" :disabled="!!scanBusy" @click="runIntegrity">Check integrity</UButton>
          <UButton size="sm" variant="outline" :loading="scanBusy === 'freshness'" :disabled="!!scanBusy" @click="loadFreshness">Measure freshness</UButton>
          <UButton size="sm" variant="outline" :loading="scanBusy === 'storage'" :disabled="!!scanBusy" @click="loadStorage">Measure storage</UButton>
          <UButton size="sm" variant="outline" :loading="scanBusy === 'failures'" :disabled="!!scanBusy" @click="loadFailures">Load parse failures</UButton>
        </div>
        <div v-if="freshness" class="mt-5 overflow-x-auto"><h3 class="text-sm font-medium mb-2">Freshness</h3><AdminTable :columns="[{ key: 'table', label: 'Table', mono: true }, { key: 'rows', label: 'Rows', numeric: true }, { key: 'newest', label: 'Newest', mono: true }, { key: 'oldest', label: 'Oldest', mono: true }]" :rows="freshness" row-key="table" /></div>
        <div v-if="storage" class="mt-5 overflow-x-auto"><h3 class="text-sm font-medium mb-2">Storage</h3><AdminTable :columns="[{ key: 'path', label: 'Directory', mono: true }, { key: 'backend', label: 'Backend' }, { key: 'files', label: 'Files', numeric: true }, { key: 'bytes', label: 'Bytes', numeric: true }, { key: 'newest', label: 'Newest', mono: true }, { key: 'note', label: 'What it is' }]" :rows="storage" row-key="path" /></div>
        <div v-if="failures" class="mt-5 overflow-x-auto"><h3 class="text-sm font-medium mb-2">Parse failures</h3><AdminTable :columns="[{ key: 'module', label: 'Module', mono: true }, { key: 'field_name', label: 'Field', mono: true }, { key: 'reason', label: 'Reason' }, { key: 'raw_fragment', label: 'Raw fragment' }]" :rows="failures.rows ?? []" /></div>
      </UCard>

      <UCard>
        <template #header><div class="flex flex-wrap items-center justify-between gap-3"><span class="text-sm font-medium">Coverage matrix</span><div class="flex gap-2"><select v-model="coverageTier" class="text-sm border rounded px-2 py-1 bg-transparent"><option value="upper">Public-health authorities</option><option value="all">All authorities</option></select><input v-model="coverageFilter" type="search" placeholder="Filter authority" class="text-sm border rounded px-2 py-1 bg-transparent"></div></div></template>
        <div v-if="coveragePending" class="text-sm opacity-60">Loading coverage…</div>
        <template v-else-if="coverage">
          <p class="text-sm opacity-70 mb-4">{{ coverage.authority_count?.toLocaleString('en-GB') ?? 0 }} authorities in the {{ coverage.tier ?? coverageTier }} tier. A blank cell is a coverage gap, not a zero.</p>
          <div class="overflow-x-auto max-h-[38rem]"><table class="w-full text-xs border-collapse"><thead class="sticky top-0 bg-[var(--st-paper)] dark:bg-gray-950"><tr class="text-left border-b border-black/15 dark:border-white/15"><th class="py-2 pr-4">Authority</th><th class="py-2 pr-4">Region</th><th v-for="column in coverage.columns ?? []" :key="column.label" class="py-2 pr-4 whitespace-nowrap">{{ column.label }}<span class="block opacity-60">{{ column.covered ?? 0 }}/{{ coverage.authority_count ?? 0 }}</span></th></tr></thead><tbody><tr v-for="authority in authorityRows" :key="authority.ons_code" class="border-b border-black/5 dark:border-white/5"><td class="py-1 pr-4 whitespace-nowrap">{{ authority.name }} <span class="opacity-50 font-mono">{{ authority.ons_code }}</span></td><td class="py-1 pr-4">{{ authority.region ?? '—' }}</td><td v-for="column in coverage.columns ?? []" :key="column.label" class="py-1 pr-4 text-center">{{ authority.cells[column.label] ?? '—' }}</td></tr></tbody></table></div>
        </template>
      </UCard>
    </template>
  </section>
</template>
