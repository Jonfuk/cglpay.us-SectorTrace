<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { ChangeEvent, ChangesResponse } from '~/types/api'

// Changes route. A derived, filterable chronology of what the warehouse
// recorded changing — added/refreshed, reparsed, superseded, verified. It is
// read-only and adds no collection-time write path. A recorded change is not a
// claim that a fact changed; it is a record of what the warehouse observed.
// Parity target: legacy `public/js/pages/changes.js`.
const api = usePublicApi()
const filters = useFilterState()

const kind = computed({
  get: () => (filters.get('kind') as string) ?? '',
  set: (v: string) => { void filters.set('kind', v || undefined) },
})

const { data, pending, error } = await useDataRoute<ChangesResponse>(
  'public-changes',
  (f) => api.changes({ query: f }),
)

const events = computed<ChangeEvent[]>(() => data.value?.events ?? [])

const columns: Column<ChangeEvent>[] = [
  { key: 'at', label: 'When', mono: true },
  { key: 'kind', label: 'Kind' },
  { key: 'source', label: 'Source' },
  { key: 'evidence_type', label: 'Evidence type' },
]

useHead({ title: 'SectorTrace — Changes' })
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Changes</h1>
      <p class="opacity-70 max-w-2xl">
        What the warehouse recorded changing over time. This is a record of
        observations, not a claim that any underlying fact changed.
      </p>
    </div>

    <div class="flex items-center gap-3">
      <label class="text-sm opacity-70" for="change-kind">Kind</label>
      <input
        id="change-kind"
        v-model.lazy="kind"
        type="text"
        placeholder="e.g. refreshed"
        class="text-sm border border-black/15 dark:border-white/15 rounded px-2 py-1 bg-transparent"
      >
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading changes…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <UCard v-else>
      <template #header>
        <span class="text-sm font-medium">{{ events.length }} recorded changes</span>
      </template>
      <StEvidenceTable v-if="events.length" :columns="columns" :rows="events" />
      <StEmptyState v-else />
    </UCard>
  </section>
</template>
