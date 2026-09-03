<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { GeographyFeature, GeographyResponse } from '~/types/api'

// Places route. One value per authority for the chosen metric. The choropleth
// itself (MapLibre + the ~14 MB boundary geometry, to be served as PMTiles
// tiles) is a dedicated specialist stage; until then the same per-authority
// values render as a sortable evidence table, which is the data the map would
// colour. Parity target: legacy `public/js/pages/geography.js`.
const api = usePublicApi()
const filters = useFilterState()

const metric = computed({
  get: () => (filters.get('metric') as string) ?? '',
  set: (v: string) => { void filters.set('metric', v || undefined) },
})

const { data, pending, error } = await useDataRoute<GeographyResponse>(
  'public-geography',
  (f) => api.geography({ query: f }),
)

const features = computed<GeographyFeature[]>(() =>
  [...(data.value?.features ?? [])].sort((a, b) => (b.value ?? -Infinity) - (a.value ?? -Infinity)),
)

const columns = computed<Column<GeographyFeature>[]>(() => [
  { key: 'authority_name', label: 'Authority' },
  { key: 'region', label: 'Region' },
  { key: 'value', label: data.value?.metric_label ?? 'Value', numeric: true },
  { key: 'financial_year', label: 'Year', mono: true },
])

useHead({ title: 'SectorTrace — Places' })
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Places</h1>
      <p class="opacity-70 max-w-2xl">
        One value per local authority. The map view (vector boundary tiles)
        arrives in a later stage; the same values are shown here as a table.
      </p>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading authority values…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <div v-if="data" class="grid grid-cols-2 md:grid-cols-4 gap-6">
        <StStat :label="`${data.metric_label} (mean)`" :value="data.authority_mean" />
        <StStat label="Min" :value="data.min" />
        <StStat label="Max" :value="data.max" />
        <StStat label="Authorities" :value="features.length" />
      </div>

      <UCard>
        <template #header>
          <span class="text-sm font-medium">{{ data?.metric_label ?? 'Authority values' }}</span>
        </template>
        <StEvidenceTable
          v-if="features.length"
          :columns="columns"
          :rows="features"
          row-key="ons_code"
        />
        <StEmptyState v-else />
        <template v-if="data?.caveat" #footer>
          <StCaveat :text="data.caveat" />
        </template>
      </UCard>
    </template>
  </section>
</template>
