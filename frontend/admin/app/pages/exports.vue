<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/AdminTable.vue'
import type { ExportFile, ExportsResponse } from '~/types/admin'

// Exports — the export files the operator can download, with sizes. Read-only:
// building a new export is a write/job surface ported later. Parity target:
// legacy admin `exports.js`.
const api = useAdminApi()

const { data, pending, error } = await useAsyncData<ExportsResponse | null>(
  'admin-exports',
  () => api.exports(),
  { default: () => null },
)

const files = computed<ExportFile[]>(() => data.value?.files ?? [])

const columns: Column<ExportFile>[] = [
  { key: 'name', label: 'File' },
  { key: 'size', label: 'Bytes', numeric: true },
]

useHead({ title: 'SectorTrace — Exports' })
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold">Exports</h1>

    <div v-if="pending" class="text-sm opacity-60">Loading exports…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <UCard v-else>
      <template #header><span class="text-sm font-medium">{{ files.length }} files</span></template>
      <AdminTable v-if="files.length" :columns="columns" :rows="files" row-key="name" />
      <StEmptyState v-else title="No exports" message="No export files are available yet." />
    </UCard>
  </section>
</template>
