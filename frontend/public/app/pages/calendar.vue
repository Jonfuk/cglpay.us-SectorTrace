<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { CalendarResponse, CalendarRow } from '~/types/api'

// Publication calendar route. Per-source release cadence, last publication, and
// overdue/unknown status. Stated cadence is registry metadata; observed cadence
// is measured — the two are kept as separate fields and never combined, and a
// next-expected date is a projection, not a promise. Parity target: legacy
// `public/js/pages/calendar.js`.
const api = usePublicApi()

const { data, pending, error } = await useDataRoute<CalendarResponse>(
  'public-calendar',
  () => api.calendar(),
)

const datasets = computed<CalendarRow[]>(() => data.value?.datasets ?? [])

const columns: Column<CalendarRow>[] = [
  { key: 'title', label: 'Dataset' },
  { key: 'publisher', label: 'Publisher' },
  { key: 'stated_cadence', label: 'Stated cadence' },
  { key: 'cadence_basis', label: 'Basis' },
  { key: 'last_publication', label: 'Last published', mono: true },
  { key: 'next_expected', label: 'Next expected', mono: true },
  { key: 'status', label: 'Status' },
]

useHead({ title: 'SectorTrace — Publication calendar' })
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Publication calendar</h1>
      <p class="opacity-70 max-w-2xl">
        When each source last published and when it is next expected. Stated and
        observed cadences are shown separately; a next-expected date is a
        projection, not a commitment by the publisher.
      </p>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading the calendar…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <UCard v-else>
      <template #header>
        <span class="text-sm font-medium">
          {{ datasets.length }} sources<template v-if="data?.as_of"> · as of {{ data.as_of }}</template>
        </span>
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
  </section>
</template>
