<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { CatalogueDataset, CatalogueResponse } from '~/types/api'

// Catalogue route. Every dataset the portal serves, with measured row counts
// and freshness. No arithmetic crosses datasets and there is no headline total
// — the catalogue lists layers side by side, it does not sum them. Parity
// target: legacy `public/js/pages/catalogue.js`.
const api = usePublicApi()

const { data, pending, error } = await useDataRoute<CatalogueResponse>(
  'public-catalogue',
  () => api.catalogue(),
)

const datasets = computed<CatalogueDataset[]>(() => data.value?.datasets ?? [])

const columns: Column<CatalogueDataset>[] = [
  { key: 'title', label: 'Dataset' },
  { key: 'publisher', label: 'Publisher' },
  { key: 'evidence_layer_label', label: 'Layer' },
  { key: 'geography', label: 'Geography' },
  { key: 'row_count', label: 'Rows', numeric: true },
  { key: 'last_retrieved_at', label: 'Last fetched', mono: true },
  { key: 'official_url', label: 'Official source', link: true },
]

useHead({ title: 'SectorTrace — Catalogue' })
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Catalogue</h1>
      <p class="opacity-70 max-w-2xl">
        Every dataset served, with live row counts and freshness. Layers sit
        side by side; nothing is summed across them.
      </p>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading the catalogue…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <UCard>
        <template #header>
          <span class="text-sm font-medium">{{ data?.count ?? datasets.length }} datasets</span>
        </template>
        <StEvidenceTable
          v-if="datasets.length"
          :columns="columns"
          :rows="datasets"
          row-key="dataset_id"
        />
        <StEmptyState v-else />
        <template v-if="data?.caveat" #footer>
          <StCaveat :text="data.caveat" />
        </template>
      </UCard>
    </template>
  </section>
</template>
