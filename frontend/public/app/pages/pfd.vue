<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { PfdReport, PfdResponse } from '~/types/api'

// Prevention of Future Deaths route. The sector-level view of the coroners'
// report corpus. Parity target: legacy `public/js/pages/pfd.js`.
const api = usePublicApi()

const { data, pending, error } = await useDataRoute<PfdResponse>('public-pfd', () => api.pfd())

const recent = computed<PfdReport[]>(() => data.value?.recent ?? [])

const columns: Column<PfdReport>[] = [
  { key: 'report_date', label: 'Date', mono: true },
  { key: 'coroner_area', label: 'Coroner area' },
  { key: 'categories', label: 'Categories' },
  { key: 'report_ref', label: 'Ref', mono: true },
  { key: 'report_url', label: 'Report', link: true },
]

useHead({ title: 'SectorTrace — Prevention of Future Deaths' })
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Prevention of Future Deaths</h1>
      <p class="opacity-70 max-w-2xl">
        The coroners' PFD report corpus at sector level. Each report links to the
        published source.
      </p>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading reports…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <UCard>
        <template #header>
          <span class="text-sm font-medium">Recent reports</span>
        </template>
        <StEvidenceTable
          v-if="recent.length"
          :columns="columns"
          :rows="recent"
          row-key="report_ref"
        />
        <StEmptyState v-else />
        <template v-if="data?.caveats" #footer>
          <div class="space-y-2">
            <StCaveat v-for="(text, key) in data.caveats" :key="key" :text="text" />
          </div>
        </template>
      </UCard>
    </template>
  </section>
</template>
