<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { ProviderRow } from '~/types/api'

// Providers route. Every provider with the counts that make them comparable.
// Contract counts join through supplier aliases (a supplier's name in a notice
// is whatever the buyer typed), so counting on raw names would undercount — the
// API already handles that; the page renders the comparable counts. Parity
// target: legacy `public/js/pages/providers.js`.
const api = usePublicApi()
const filters = useFilterState()

const search = computed({
  get: () => (filters.get('q') as string) ?? '',
  set: (v: string) => { void filters.set('q', v || undefined) },
})

const { data, pending, error } = await useDataRoute<ProviderRow[]>(
  'public-providers',
  () => api.providers(),
)

// Client-side name filter over the bounded provider list (the endpoint returns
// the full comparable set). URL-authoritative so the filtered view is a link.
const rows = computed<ProviderRow[]>(() => {
  const all = data.value ?? []
  const q = search.value.trim().toLowerCase()
  if (!q) return all
  return all.filter((r) => (r.canonical_name ?? '').toLowerCase().includes(q))
})

// Columns are derived from the first row's keys beyond the name, so the table
// reflects whatever comparable counts the API returns without hard-coding a
// shape that could drift. Name first, then up to five count columns.
const columns = computed<Column<ProviderRow>[]>(() => {
  const first = (data.value ?? [])[0]
  const cols: Column<ProviderRow>[] = [{ key: 'canonical_name', label: 'Provider' }]
  if (!first) return cols
  const numericKeys = Object.keys(first).filter(
    (k) => k !== 'canonical_name' && k !== 'provider_key' && typeof first[k] === 'number',
  )
  for (const k of numericKeys.slice(0, 5)) {
    cols.push({ key: k, label: k.replace(/_/g, ' '), numeric: true })
  }
  return cols
})

useHead({ title: 'SectorTrace — Providers' })
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Providers</h1>
      <p class="opacity-70 max-w-2xl">
        Providers and the counts that make them comparable. Contract counts are
        matched through supplier aliases, so they are a floor, not a total.
      </p>
    </div>

    <input
      v-model.lazy="search"
      type="search"
      placeholder="Filter by name…"
      class="text-sm border border-black/15 dark:border-white/15 rounded px-3 py-1.5 bg-transparent min-w-64"
    >

    <div v-if="pending" class="text-sm opacity-60">Loading providers…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <UCard v-else>
      <template #header>
        <span class="text-sm font-medium">{{ rows.length }} providers</span>
      </template>
      <StEvidenceTable
        v-if="rows.length"
        :columns="columns"
        :rows="rows"
        row-key="provider_key"
      />
      <StEmptyState v-else />
    </UCard>
  </section>
</template>
