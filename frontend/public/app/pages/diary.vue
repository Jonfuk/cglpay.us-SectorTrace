<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { DiaryEvent, DiaryResponse } from '~/types/api'

// Contract-diary route. An entity's dated procurement events (a chronology of
// its notices). Coverage is whichever notices matched this scope by exact
// supplier name or buyer ONS code; a missing event means a missing or unmatched
// notice, not that nothing happened. Entity read from the URL. Parity target:
// legacy `public/js/pages/diary.js`.
const api = usePublicApi()
const filters = useFilterState()

const hasScope = computed(
  () => !!(filters.get('provider_key') || filters.get('buyer_ons_code') || filters.get('ocid')),
)

const { data, pending, error } = await useDataRoute<DiaryResponse | null>(
  'public-diary',
  (f) => {
    if (!f.provider_key && !f.buyer_ons_code && !f.ocid) return Promise.resolve(null)
    return api.diary({ query: f })
  },
)

const events = computed<DiaryEvent[]>(() => data.value?.events ?? [])

const columns: Column<DiaryEvent>[] = [
  { key: 'date', label: 'Date', mono: true },
  { key: 'kind_label', label: 'Kind' },
  { key: 'title', label: 'Title' },
  { key: 'buyer_name', label: 'Buyer' },
  { key: 'value_core', label: 'Value', numeric: true },
  { key: 'source_url', label: 'Source', link: true },
]

useHead({ title: 'SectorTrace — Contract diary' })
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Contract diary</h1>
      <p class="opacity-70 max-w-2xl">
        A dated chronology of an entity's procurement notices. A missing event
        means a missing or unmatched notice, not that nothing happened.
      </p>
    </div>

    <StEmptyState
      v-if="!hasScope"
      title="Choose an entity"
      message="Open this view from a provider or authority to see its contract diary."
    />
    <div v-else-if="pending" class="text-sm opacity-60">Loading diary…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <UCard v-else>
      <template #header>
        <span class="text-sm font-medium">{{ events.length }} events</span>
      </template>
      <StEvidenceTable
        v-if="events.length"
        :columns="columns"
        :rows="events"
        row-key="notice_id"
      />
      <StEmptyState v-else />
      <template v-if="data?.caveat" #footer>
        <StCaveat :text="data.caveat" />
      </template>
    </UCard>
  </section>
</template>
