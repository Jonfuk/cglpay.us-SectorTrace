<script setup lang="ts">
import { computed } from 'vue'
import type { AdminSearchResponse } from '~/types/admin'

// Search — the operator search console over the warehouse (hybrid lexical +
// semantic). The query and mode are URL-authoritative. Parity target: legacy
// admin `search.js`.
const api = useAdminApi()
const filters = useFilterState()

const q = computed({
  get: () => (filters.get('q') as string) ?? '',
  set: (v: string) => { void filters.set('q', v || undefined) },
})
const mode = computed({
  get: () => (filters.get('mode') as string) ?? 'hybrid',
  set: (v: string) => { void filters.set('mode', v === 'hybrid' ? undefined : v) },
})

const { data, pending, error } = await useDataRoute<AdminSearchResponse | null>(
  'admin-search',
  (f) => {
    const query = (f.q as string) ?? ''
    if (!query.trim()) return Promise.resolve(null)
    return api.search({ query: f })
  },
)

const results = computed<Array<Record<string, unknown>>>(
  () => data.value?.results ?? data.value?.hits ?? [],
)

useHead({ title: 'SectorTrace — Search' })
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold">Search</h1>

    <div class="flex flex-wrap items-center gap-3">
      <input
        v-model.lazy="q"
        type="search"
        placeholder="Search the warehouse…"
        class="text-sm border border-black/15 dark:border-white/15 rounded px-3 py-1.5 bg-transparent min-w-72"
      >
      <select
        v-model="mode"
        class="text-sm border border-black/15 dark:border-white/15 rounded px-2 py-1 bg-transparent"
      >
        <option value="hybrid">Hybrid</option>
        <option value="semantic">Semantic</option>
        <option value="lexical">Lexical</option>
      </select>
    </div>

    <div v-if="!q.trim()" class="text-sm opacity-60">Enter a query to search.</div>
    <div v-else-if="pending" class="text-sm opacity-60">Searching…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <UCard v-else>
      <template #header><span class="text-sm font-medium">{{ results.length }} results</span></template>
      <StEmptyState v-if="!results.length" />
      <ul v-else class="divide-y divide-black/5 dark:divide-white/5">
        <li v-for="(r, i) in results" :key="i" class="py-2 text-sm">
          <div class="font-medium">{{ r.title ?? r.name ?? r.id ?? '—' }}</div>
          <div v-if="r.snippet || r.text" class="opacity-70">{{ r.snippet ?? r.text }}</div>
        </li>
      </ul>
    </UCard>
  </section>
</template>
