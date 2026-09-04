<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { GeographyFeature, GeographyResponse } from '~/types/api'

// Places route. One value per authority for the chosen metric. The choropleth
// loads MapLibre and a content-addressed PMTiles boundary archive only when
// selected; the same per-authority values render as a sortable evidence table.
// Parity target: legacy `public/js/pages/geography.js`.
const api = usePublicApi()
const filters = useFilterState()

const metric = computed({
  get: () => (filters.get('metric') as string) ?? '',
  set: (v: string) => { void filters.set('metric', v || undefined) },
})

const metricOptions = [
  { value: 'grant_total', label: 'Public health grant total' },
  { value: 'grant_per_head', label: 'Public health grant per head' },
  { value: 'budget_public_health', label: 'Public health budget' },
  { value: 'treatment_numbers', label: 'People in treatment' },
  { value: 'contract_value', label: 'Published contract value' },
]

// Table vs map view. The map (MapLibre) is only mounted when chosen, so its
// chunk is never fetched on the table view — keeping MapLibre off every path
// that does not use it. The choice is URL-authoritative.
const view = computed({
  get: () => (filters.get('view') === 'map' ? 'map' : 'table'),
  set: (v: string) => { void filters.set('view', v === 'map' ? 'map' : undefined) },
})

const { data, pending, error } = await useDataRoute<GeographyResponse>(
  'public-geography',
  (f) => api.geography({ query: f }),
)

const features = computed<GeographyFeature[]>(() =>
  [...(data.value?.features ?? [])].sort((a, b) => (b.value ?? -Infinity) - (a.value ?? -Infinity)),
)

const columns = computed<Column<GeographyFeature>[]>(() => [
  {
    key: 'authority_name',
    label: 'Authority',
    to: (row) => (row.ons_code ? `/authorities/${row.ons_code}` : null),
  },
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
        One value per local authority, as a table or a choropleth of the
        authority boundaries. The map colours each authority by the same value
        the table shows.
      </p>
    </div>

    <div class="flex flex-wrap items-center gap-3">
      <label class="text-sm flex items-center gap-2">
        <span class="opacity-70">Measure</span>
        <select
          :value="metric || 'grant_total'"
          class="rounded border border-black/15 dark:border-white/15 bg-transparent px-2 py-1"
          @change="metric = ($event.target as HTMLSelectElement).value"
        >
          <option v-for="option in metricOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
      <div class="inline-flex rounded border border-black/15 dark:border-white/15 text-sm overflow-hidden">
      <button
        type="button"
        class="px-3 py-1"
        :class="view === 'table' ? 'bg-[var(--st-accent)] text-white' : 'opacity-70'"
        @click="view = 'table'"
      >Table</button>
      <button
        type="button"
        class="px-3 py-1"
        :class="view === 'map' ? 'bg-[var(--st-accent)] text-white' : 'opacity-70'"
        @click="view = 'map'"
      >Map</button>
      </div>
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

      <GeographyMap
        v-if="view === 'map'"
        :features="features"
        :metric-label="data?.metric_label"
      />

      <UCard v-else>
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
