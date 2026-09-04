<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { ProviderTimelineResponse, TimelineEvent } from '~/types/api'

// Standalone timeline — a provider's dated events, addressable by
// `?provider_key=`. The same data the provider detail page shows in context;
// this route makes it a shareable link on its own. Parity target: legacy
// `public/js/pages/timeline.js`.
const api = usePublicApi()
const filters = useFilterState()

const providerKey = computed(() => (filters.get('provider_key') as string) ?? '')

const { data, pending, error } = await useDataRoute<ProviderTimelineResponse | null>(
  'public-timeline',
  (f) => {
    const key = (f.provider_key as string) ?? ''
    if (!key) return Promise.resolve(null)
    return api.providerTimeline(key)
  },
)

const events = computed<TimelineEvent[]>(() => data.value?.events ?? [])
const columns: Column<TimelineEvent>[] = [
  { key: 'date', label: 'Date', mono: true },
  { key: 'label', label: 'Event' },
  { key: 'value_summary', label: 'Detail' },
  { key: 'source_url', label: 'Source', link: true },
]

useHead({ title: 'SectorTrace — Timeline' })
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold">Timeline</h1>
    <StEmptyState
      v-if="!providerKey"
      title="Choose a provider"
      message="Open this view from a provider to see its dated event timeline."
    />
    <div v-else-if="pending" class="text-sm opacity-60">Loading timeline…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <UCard v-else>
      <template #header>
        <span class="text-sm font-medium">{{ events.length }} events</span>
      </template>
      <StEvidenceTable v-if="events.length" :columns="columns" :rows="events" />
      <StEmptyState v-else />
    </UCard>
  </section>
</template>
