<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { CqcLocation, CqcResponse } from '~/types/api'

// CQC route. CQC-registered locations, server-paginated. Parity target: legacy
// `public/js/pages/cqc.js`. The map/explorer view is a specialist stage; the
// registered locations render here as an evidence table with their ratings.
const api = usePublicApi()
const filters = useFilterState()

const search = computed({
  get: () => (filters.get('q') as string) ?? '',
  set: (v: string) => { void filters.set('q', v || undefined) },
})

const { data, pending, error } = await useDataRoute<CqcResponse>(
  'public-cqc',
  (f) => api.cqc({ query: f }),
)

const results = computed<CqcLocation[]>(() => data.value?.results ?? [])

const columns: Column<CqcLocation>[] = [
  { key: 'location_name', label: 'Location' },
  { key: 'provider_name', label: 'Provider' },
  { key: 'region', label: 'Region' },
  { key: 'overall_rating', label: 'Rating' },
  { key: 'registration_status', label: 'Status' },
  { key: 'source_url', label: 'Source', link: true },
]

useHead({ title: 'SectorTrace — CQC locations' })
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">CQC locations</h1>
      <p class="opacity-70 max-w-2xl">
        CQC-registered locations, as published by the regulator.
      </p>
    </div>

    <input
      v-model.lazy="search"
      type="search"
      placeholder="Search locations…"
      class="text-sm border border-black/15 dark:border-white/15 rounded px-3 py-1.5 bg-transparent min-w-64"
    >

    <div v-if="pending" class="text-sm opacity-60">Loading locations…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <UCard v-else>
      <template #header>
        <span class="text-sm font-medium">{{ data?.total ?? results.length }} locations</span>
      </template>
      <StEvidenceTable
        v-if="results.length"
        :columns="columns"
        :rows="results"
        row-key="location_id"
      />
      <StEmptyState v-else />
      <template v-if="data?.caveat" #footer>
        <StCaveat :text="data.caveat" />
      </template>
    </UCard>
  </section>
</template>
