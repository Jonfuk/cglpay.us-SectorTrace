<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import type { Column } from '~/components/AdminTable.vue'
import { TransportError } from '~/lib/transport'
import type { ExportFile, ExportsResponse, JobDetail } from '~/types/admin'

// Exports are local, reproducible artefacts. The page lists only files the
// server has enumerated and starts the same export job as the CLI; downloads
// therefore remain inside the server-side export-root guard.
const api = useAdminApi()
const targets = ['sheets', 'geojson', 'echarts', 'docs', 'bundle', 'all'] as const
const target = ref<(typeof targets)[number]>('all')
const busy = ref(false)
const status = ref('')
const statusLevel = ref<'ok' | 'warn' | 'bad'>('warn')
const currentJob = ref<JobDetail | null>(null)
let pollTimer: ReturnType<typeof setTimeout> | null = null

const { data, pending, error, refresh } = await useAsyncData<ExportsResponse | null>(
  'admin-exports', () => api.exports(), { default: () => null },
)
const files = computed<ExportFile[]>(() => data.value?.files ?? [])
const groups = computed(() => {
  const result = new Map<string, ExportFile[]>()
  for (const file of files.value) {
    const group = file.group || '(root)'
    if (!result.has(group)) result.set(group, [])
    result.get(group)?.push(file)
  }
  return [...result.entries()]
})

function when(value: string | null | undefined): string {
  return value ? value.replace('T', ' ').replace(/\.\d+/, '').replace('+00:00', 'Z') : '—'
}

function formatBytes(value: unknown): string {
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n) || n <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let amount = n
  let index = 0
  while (amount >= 1024 && index < units.length - 1) {
    amount /= 1024
    index += 1
  }
  return `${amount.toFixed(index ? 1 : 0)} ${units[index]}`
}

function download(path: string | undefined): string {
  return path ? `/api/admin/exports/file?path=${encodeURIComponent(path)}` : '#'
}

function staleness(group: string) {
  const groups = (data.value?.staleness as { groups?: Array<Record<string, unknown>> } | undefined)?.groups ?? []
  return groups.find((row) => row.group === group)
}

function clearPoll() {
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = null
}

async function pollJob(id: number): Promise<void> {
  try {
    const job = await api.job(id, { noDedup: true })
    currentJob.value = job
    if (job.running || job.state === 'queued' || job.state === 'pending') {
      pollTimer = setTimeout(() => { void pollJob(id) }, 1000)
      return
    }
    busy.value = false
    status.value = job.state === 'failed' ? (job.error ?? 'Export failed.') : 'Export completed.'
    statusLevel.value = job.state === 'failed' ? 'bad' : 'ok'
    await refresh()
  } catch (e) {
    busy.value = false
    status.value = e instanceof TransportError ? e.message : 'The export job could not be followed.'
    statusLevel.value = 'bad'
  }
}

async function startExport() {
  if (busy.value) return
  if (!window.confirm(`Write the ${target.value} export locally?`)) return
  busy.value = true
  currentJob.value = null
  clearPoll()
  status.value = `Starting ${target.value} export…`
  statusLevel.value = 'warn'
  try {
    const job = await api.startExport(target.value)
    currentJob.value = job
    status.value = `Following job #${job.id}.`
    void pollJob(job.id)
  } catch (e) {
    busy.value = false
    status.value = e instanceof TransportError ? e.message : 'The export could not be started.'
    statusLevel.value = 'bad'
  }
}

const columns: Column<ExportFile>[] = [
  { key: 'name', label: 'File' },
  { key: 'bytes', label: 'Bytes', numeric: true },
  { key: 'modified', label: 'Written', mono: true },
]

onBeforeUnmount(clearPoll)
useHead({ title: 'SectorTrace — Exports' })
</script>

<template>
  <section class="space-y-6">
    <div>
      <h1 class="text-2xl font-semibold">Exports</h1>
      <p class="mt-2 max-w-3xl text-sm opacity-70">
        Generate reproducible local artefacts with their provenance companions,
        then download only files enumerated by the export service.
      </p>
    </div>

    <UCard>
      <template #header><span class="text-sm font-medium">Generate an export</span></template>
      <div class="flex flex-wrap items-end gap-3">
        <label class="text-sm space-y-1">
          <span class="block opacity-70">Target</span>
          <select v-model="target" class="border border-black/15 dark:border-white/15 rounded px-2 py-2 bg-transparent">
            <option v-for="name in targets" :key="name" :value="name">{{ name }}</option>
          </select>
        </label>
        <UButton color="primary" :disabled="busy" @click="startExport">{{ busy ? 'Writing…' : 'Generate' }}</UButton>
      </div>
      <p v-if="status" class="mt-4 text-sm" :class="statusLevel === 'bad' ? 'text-red-700 dark:text-red-300' : statusLevel === 'ok' ? 'text-green-700 dark:text-green-300' : 'opacity-70'">{{ status }}</p>
      <div v-if="currentJob" class="mt-3 text-xs opacity-70">
        Job #{{ currentJob.id }} · {{ currentJob.state }} · started {{ when(currentJob.started_at) }}
      </div>
    </UCard>

    <div v-if="pending" class="text-sm opacity-60">Loading exports…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <UCard v-if="!files.length">
        <StEmptyState title="No exports" message="No export files are available yet. Generate one above." />
      </UCard>
      <UCard v-for="([group, groupFiles]) in groups" :key="group">
        <template #header>
          <div class="flex items-center justify-between gap-3">
            <span class="text-sm font-medium">{{ group }} · {{ groupFiles.length }} file{{ groupFiles.length === 1 ? '' : 's' }}</span>
            <span class="text-xs opacity-60">{{ formatBytes(groupFiles.reduce((sum, file) => sum + Number(file.bytes ?? file.size ?? 0), 0)) }}</span>
          </div>
        </template>
        <p v-if="staleness(group)?.stale" class="mb-4 text-sm text-amber-700 dark:text-amber-300">
          These files predate the last collection. Re-export before quoting figures.
        </p>
        <p v-else class="mb-4 text-xs opacity-60">Written after the last recorded pipeline activity.</p>
        <AdminTable :columns="columns" :rows="groupFiles" row-key="path" />
        <div class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
          <template v-for="file in groupFiles" :key="file.path">
            <a v-if="file.path" :href="download(file.path)" class="text-[var(--st-accent)] underline underline-offset-2">Download {{ file.name }}</a>
            <a v-if="file.provenance" :href="download(file.provenance)" class="text-[var(--st-accent)] underline underline-offset-2">Provenance</a>
          </template>
        </div>
      </UCard>
    </template>
  </section>
</template>
