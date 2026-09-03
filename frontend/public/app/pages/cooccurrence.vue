<script setup lang="ts">
import { computed } from 'vue'
import type { CooccurrenceRecord, CooccurrenceResponse } from '~/types/api'

// Co-occurrence route. Records naming two or more selected tracked entities
// together, with the exact passage or field. Co-occurrence is LOCATION in one
// record — never an asserted relationship. Entity keys are read from the URL as
// repeated `?key=`. Parity target: legacy `public/js/pages/cooccurrence.js`.
const api = usePublicApi()
const filters = useFilterState()

const keys = computed<string[]>(() => {
  const raw = filters.get('key')
  if (!raw) return []
  return Array.isArray(raw) ? raw : [raw]
})

const { data, pending, error } = await useDataRoute<CooccurrenceResponse | null>(
  'public-cooccurrence',
  (f) => {
    const k = f.key
    if (!k || (Array.isArray(k) && k.length < 2)) return Promise.resolve(null)
    return api.cooccurrence({ query: f })
  },
)

const results = computed<CooccurrenceRecord[]>(() => data.value?.results ?? [])
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Co-occurrence</h1>
      <p class="opacity-70 max-w-2xl">
        Records that name two or more selected entities together, with the exact
        passage. Appearing together in a record is location, not an asserted
        relationship between them.
      </p>
    </div>

    <StEmptyState
      v-if="keys.length < 2"
      title="Select at least two entities"
      message="Co-occurrence needs two or more entity keys (?key=…&key=…) to look for records naming them together."
    />
    <div v-else-if="pending" class="text-sm opacity-60">Searching records…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <UCard v-if="data?.entities?.length">
        <template #header>
          <span class="text-sm font-medium">Entities</span>
        </template>
        <ul class="text-sm space-y-1">
          <li v-for="e in data.entities" :key="e.key">
            {{ e.name ?? e.key }}
            <span class="opacity-60">· {{ e.variant_count }} verified variant(s)</span>
          </li>
        </ul>
      </UCard>

      <UCard>
        <template #header>
          <span class="text-sm font-medium">{{ results.length }} co-occurrence records</span>
        </template>
        <StEmptyState v-if="!results.length" />
        <ul v-else class="space-y-4">
          <li v-for="(r, i) in results" :key="i" class="space-y-1">
            <p class="text-sm font-medium">{{ r.title ?? r.record_id }}</p>
            <p class="text-xs opacity-60">{{ r.record_type }} · {{ r.source_system }}</p>
            <p class="text-sm opacity-80">{{ r.text ?? '—' }}</p>
          </li>
        </ul>
        <template v-if="data?.caveat" #footer>
          <StCaveat :text="data.caveat" />
        </template>
      </UCard>
    </template>
  </section>
</template>
