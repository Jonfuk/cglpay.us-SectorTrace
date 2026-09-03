<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { TreatmentMetric, TreatmentResponse } from '~/types/api'

// Treatment route. A catalogue of treatment metrics shown BEFORE any chart is
// drawn: each metric's definition, the exact periods held, whether a 95% CI is
// published, and its coverage — so a reader sees what the evidence is and is not
// before it is visualised. Parity target: legacy `public/js/pages/treatment.js`.
const api = usePublicApi()

const { data, pending, error } = await useDataRoute<TreatmentResponse>(
  'public-treatment',
  () => api.treatment(),
)

const metrics = computed<TreatmentMetric[]>(() => data.value?.metrics ?? [])

const columns: Column<TreatmentMetric>[] = [
  { key: 'name', label: 'Metric' },
  { key: 'substance', label: 'Substance' },
  { key: 'unit', label: 'Unit' },
  { key: 'period_count', label: 'Periods', numeric: true },
  { key: 'authority_count', label: 'Authorities', numeric: true },
  { key: 'source_url', label: 'Source', link: true },
]

useHead({ title: 'SectorTrace — Treatment' })
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Treatment</h1>
      <p class="opacity-70 max-w-2xl">
        The treatment metrics held, with their definitions and coverage. What is
        measured is a count of treatment, never a measure of need.
      </p>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading treatment metrics…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <UCard>
        <template #header>
          <span class="text-sm font-medium">{{ metrics.length }} metrics</span>
        </template>
        <StEvidenceTable
          v-if="metrics.length"
          :columns="columns"
          :rows="metrics"
          row-key="key"
        />
        <StEmptyState v-else />
        <template v-if="data?.caveat" #footer>
          <StCaveat :text="data.caveat" />
        </template>
      </UCard>
    </template>
  </section>
</template>
