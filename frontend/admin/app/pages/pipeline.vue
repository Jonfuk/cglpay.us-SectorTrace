<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/AdminTable.vue'
import type { JobHead, JobsResponse, RunRow, RunsResponse } from '~/types/admin'

// Pipeline — the run console: in-process jobs and the durable run ledger.
// Read-only in this stage; starting/cancelling jobs is a write surface ported
// later. Parity target: legacy admin `pipeline.js`.
const api = useAdminApi()

const { data: jobsData, pending: jobsPending } = await useAsyncData<JobsResponse | null>(
  'admin-jobs',
  () => api.jobs(),
  { default: () => null },
)
const { data: runsData, pending: runsPending } = await useAsyncData<RunsResponse | null>(
  'admin-runs',
  () => api.runs(),
  { default: () => null },
)

const jobs = computed<JobHead[]>(() => jobsData.value?.jobs ?? [])
const runs = computed<RunRow[]>(() => runsData.value?.runs ?? [])

const jobColumns: Column<JobHead>[] = [
  { key: 'id', label: 'ID', mono: true },
  { key: 'kind', label: 'Kind' },
  { key: 'label', label: 'Label' },
  { key: 'state', label: 'State' },
  { key: 'started_at', label: 'Started', mono: true },
]
const runColumns: Column<RunRow>[] = [
  { key: 'started_at', label: 'Started', mono: true },
  { key: 'origin', label: 'Origin' },
  { key: 'status', label: 'Status' },
  { key: 'modules_ok', label: 'OK', numeric: true },
  { key: 'modules_failed', label: 'Failed', numeric: true },
]

useHead({ title: 'SectorTrace — Pipeline' })
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold">Pipeline</h1>

    <UCard>
      <template #header>
        <span class="text-sm font-medium">
          Jobs<span v-if="jobsData?.running"> · running #{{ jobsData.running }}</span>
        </span>
      </template>
      <div v-if="jobsPending" class="text-sm opacity-60">Loading jobs…</div>
      <AdminTable v-else-if="jobs.length" :columns="jobColumns" :rows="jobs" row-key="id" />
      <StEmptyState v-else title="No jobs" message="No jobs have run in this process." />
    </UCard>

    <UCard>
      <template #header><span class="text-sm font-medium">Recent runs</span></template>
      <div v-if="runsPending" class="text-sm opacity-60">Loading run ledger…</div>
      <AdminTable v-else-if="runs.length" :columns="runColumns" :rows="runs" row-key="run_id" />
      <StEmptyState v-else title="No runs recorded" />
    </UCard>
  </section>
</template>
