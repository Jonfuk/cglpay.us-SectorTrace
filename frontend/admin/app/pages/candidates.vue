<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/AdminTable.vue'
import type { CandidateCountsResponse, CandidateItem, CandidatesListingResponse } from '~/types/admin'

// Candidates — the discovery candidates awaiting a human decision. Read-only in
// this stage: this is the surface the whole promotion phase exists to move, but
// nothing is promoted without a person, so the promote/reject WRITE actions land
// in a later, carefully-guarded stage. Parity target: legacy admin
// `candidates.js`. The kind is URL-authoritative (?kind=).
const api = useAdminApi()
const filters = useFilterState()

const kind = computed({
  get: () => (filters.get('kind') as string) ?? 'cdp_document',
  set: (v: string) => { void filters.set('kind', v || undefined) },
})

const { data: counts } = await useAsyncData<CandidateCountsResponse | null>(
  'admin-candidate-counts',
  () => api.candidateCounts(),
  { default: () => null },
)

const kindNames = computed(() => Object.keys(counts.value?.kinds ?? {}))

const { data, pending, error } = await useDataRoute<CandidatesListingResponse | null>(
  'admin-candidates',
  (f) => api.candidates({ query: { kind: (f.kind as string) || 'cdp_document', ...f } }),
)

const items = computed<CandidateItem[]>(() => data.value?.items ?? [])

const columns: Column<CandidateItem>[] = [
  { key: 'authority_name', label: 'Authority' },
  { key: 'url', label: 'Source', link: true },
  { key: 'verified', label: 'Promoted', numeric: true },
  { key: 'rejected', label: 'Rejected', numeric: true },
]

useHead({ title: 'SectorTrace — Candidates' })
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold">Candidates</h1>
    <p class="opacity-70 max-w-2xl text-sm">
      Discovery candidates awaiting a human decision. Nothing is promoted to
      evidence without a person — this view is read-only; the promote/reject
      actions arrive in a later stage.
    </p>

    <div v-if="kindNames.length" class="flex items-center gap-3">
      <label class="text-sm opacity-70" for="kind">Kind</label>
      <select
        id="kind"
        v-model="kind"
        class="text-sm border border-black/15 dark:border-white/15 rounded px-2 py-1 bg-transparent"
      >
        <option v-for="k in kindNames" :key="k" :value="k">
          {{ k }} ({{ counts?.kinds[k]?.undecided ?? 0 }} undecided)
        </option>
      </select>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading candidates…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <UCard v-else>
      <template #header>
        <span class="text-sm font-medium">
          {{ data?.total ?? items.length }} {{ data?.status ?? '' }} · {{ kind }}
        </span>
      </template>
      <AdminTable v-if="items.length" :columns="columns" :rows="items" row-key="url" />
      <StEmptyState v-else />
    </UCard>
  </section>
</template>
