<script setup lang="ts">
import type { Column } from '~/components/StEvidenceTable.vue'
import type { ContractNotice, ContractsResponse } from '~/types/api'

// Contracts route. Procurement notices with their provenance and the caveats
// that bound how contract values may be read (never summed across notices).
// Parity target: legacy `public/js/pages/contracts.js`. Server pagination is
// preserved — the page renders one bounded page of notices, not the whole set.
const api = usePublicApi()
const filters = useFilterState()

// Free-text query and PSR-only are legacy URL filters. Kept URL-authoritative.
const query = computed({
  get: () => (filters.get('q') as string) ?? '',
  set: (v: string) => { void filters.set('q', v || undefined) },
})
const psrOnly = computed({
  get: () => filters.get('psr_only') === 'true',
  set: (v: boolean) => { void filters.set('psr_only', v ? 'true' : undefined) },
})

const { data, pending, error } = await useDataRoute<ContractsResponse>(
  'public-contracts',
  (f) => api.contracts({ query: f }),
)

const notices = computed<ContractNotice[]>(() => data.value?.notices ?? [])

const columns: Column<ContractNotice>[] = [
  { key: 'date_published', label: 'Published', mono: true },
  { key: 'buyer_name', label: 'Buyer' },
  { key: 'supplier_name_raw', label: 'Supplier' },
  { key: 'title', label: 'Title' },
  { key: 'value_core', label: 'Value', numeric: true },
  { key: 'source_url', label: 'Source', link: true },
]

useHead({ title: 'SectorTrace — Contracts' })
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Contracts</h1>
      <p class="opacity-70 max-w-2xl">
        Procurement notices as published. Values are per notice and must not be
        summed — a caveat that travels with every figure here.
      </p>
    </div>

    <div class="flex flex-wrap items-center gap-4">
      <input
        v-model.lazy="query"
        type="search"
        placeholder="Search notices…"
        class="text-sm border border-black/15 dark:border-white/15 rounded px-3 py-1.5 bg-transparent min-w-64"
      >
      <label class="text-sm opacity-70 flex items-center gap-2">
        <input v-model="psrOnly" type="checkbox">
        PSR notices only
      </label>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading notices…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <UCard>
        <template #header>
          <div class="flex items-center justify-between">
            <span class="text-sm font-medium">Notices</span>
            <span v-if="data?.page" class="text-xs opacity-60">
              Showing {{ data.page.returned }} (offset {{ data.page.offset }})
            </span>
          </div>
        </template>
        <StEvidenceTable
          v-if="notices.length"
          :columns="columns"
          :rows="notices"
          row-key="notice_id"
        />
        <StEmptyState v-else />
        <template v-if="data?.caveats" #footer>
          <div class="space-y-2">
            <StCaveat :text="data.caveats.value_sum" />
            <StCaveat :text="data.caveats.provider_match" />
          </div>
        </template>
      </UCard>
    </template>
  </section>
</template>
