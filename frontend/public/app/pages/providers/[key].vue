<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { ProviderTimelineResponse, TimelineEvent } from '~/types/api'

// Provider detail — the entry point for a single provider's entity-driven
// evidence. It renders the provider's dated event timeline and links out to the
// parameter-driven views (coverage, contract diary, discrepancies,
// relationships) scoped to this provider. Parity target: the detail view of
// legacy `public/js/pages/providers.js` plus `/providers/{key}/timeline`.
const route = useRoute()
const api = usePublicApi()

const key = computed(() => String(route.params.key ?? ''))

const { data, pending, error } = await useAsyncData<ProviderTimelineResponse | null>(
  () => `provider-${key.value}`,
  () => api.providerTimeline(key.value),
  { default: () => null, watch: [key] },
)

const providerName = computed<string>(() => {
  const p = data.value?.provider as Record<string, unknown> | null
  return (p?.canonical_name as string) ?? key.value
})

const events = computed<TimelineEvent[]>(() => data.value?.events ?? [])

const columns: Column<TimelineEvent>[] = [
  { key: 'date', label: 'Date', mono: true },
  { key: 'label', label: 'Event' },
  { key: 'value_summary', label: 'Detail' },
  { key: 'source_url', label: 'Source', link: true },
]

// Entity-scoped links to the parameter-driven routes.
const scopedLinks = computed(() => [
  { to: `/coverage?provider_key=${encodeURIComponent(key.value)}`, label: 'Data coverage' },
  { to: `/diary?provider_key=${encodeURIComponent(key.value)}`, label: 'Contract diary' },
  { to: `/discrepancies?provider_key=${encodeURIComponent(key.value)}`, label: 'Source discrepancies' },
  { to: `/relationships?provider_key=${encodeURIComponent(key.value)}`, label: 'Relationships' },
])

useHead(() => ({ title: `SectorTrace — ${providerName.value}` }))
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <NuxtLink to="/providers" class="text-xs opacity-60 hover:opacity-100">← Providers</NuxtLink>
      <h1 class="text-2xl font-semibold">{{ providerName }}</h1>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading provider…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <nav class="flex flex-wrap gap-2">
        <NuxtLink
          v-for="link in scopedLinks"
          :key="link.to"
          :to="link.to"
          class="text-sm border border-black/15 dark:border-white/15 rounded px-3 py-1 hover:bg-black/5 dark:hover:bg-white/5"
        >
          {{ link.label }}
        </NuxtLink>
      </nav>

      <UCard>
        <template #header>
          <span class="text-sm font-medium">Timeline</span>
        </template>
        <StEvidenceTable v-if="events.length" :columns="columns" :rows="events" />
        <StEmptyState v-else />
      </UCard>
    </template>
  </section>
</template>
