<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { CoverageDataset, CoverageResponse } from '~/types/api'

// Coverage-timeline route. Which datasets hold a chosen entity (a provider or
// authority), and for which periods. A dataset that does not hold the entity is
// "not present in this dataset", never "the entity does not exist". The entity
// is read from the URL (?provider_key= or ?ons_code=). Parity target: legacy
// `public/js/pages/coverage.js`.
const api = usePublicApi()
const filters = useFilterState()

const hasEntity = computed(
  () => !!(filters.get('provider_key') || filters.get('ons_code')),
)

const { data, pending, error } = await useDataRoute<CoverageResponse | null>(
  'public-coverage',
  (f) => {
    if (!f.provider_key && !f.ons_code) return Promise.resolve(null)
    return api.coverage({ query: f })
  },
)

const datasets = computed<CoverageDataset[]>(() => data.value?.datasets ?? [])

const columns: Column<CoverageDataset>[] = [
  { key: 'title', label: 'Dataset' },
  { key: 'period_kind', label: 'Period kind' },
  { key: 'held', label: 'Held' },
  { key: 'link', label: 'Open', link: true },
]

useHead({ title: 'SectorTrace — Data coverage' })
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Data coverage</h1>
      <p class="opacity-70 max-w-2xl">
        Which datasets hold this entity, and for which periods. A dataset not
        holding it means the entity is absent from that source, not that it does
        not exist.
      </p>
    </div>

    <StEmptyState
      v-if="!hasEntity"
      title="Choose an entity"
      message="Open this view from a provider or authority to see which datasets cover it."
    />
    <div v-else-if="pending" class="text-sm opacity-60">Loading coverage…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <UCard v-else>
      <template #header>
        <span class="text-sm font-medium">
          {{ data?.entity?.name ?? data?.entity?.id ?? 'Coverage' }}
        </span>
      </template>
      <StEvidenceTable
        v-if="datasets.length"
        :columns="columns"
        :rows="datasets"
        row-key="dataset_id"
      />
      <StEmptyState v-else />
    </UCard>
  </section>
</template>
