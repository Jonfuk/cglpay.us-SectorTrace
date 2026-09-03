<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { DocumentHit, DocumentSearchResponse } from '~/types/api'

// Documents route. Full-text search over the document corpus. The query is
// URL-authoritative (`?q=`), so a search is a shareable link. An empty query is
// a prompt, not an empty result — the corpus is not searched until asked.
// Parity target: legacy `public/js/pages/documents.js`.
const api = usePublicApi()
const filters = useFilterState()

const q = computed({
  get: () => (filters.get('q') as string) ?? '',
  set: (v: string) => { void filters.set('q', v || undefined) },
})

const { data, pending, error } = await useDataRoute<DocumentSearchResponse | null>(
  'public-documents',
  (f) => {
    const query = (f.q as string) ?? ''
    // Do not search on an empty query — "not searched" is distinct from
    // "searched and found nothing", and only the latter is an empty result.
    if (!query.trim()) return Promise.resolve(null)
    return api.documentSearch({ query: f })
  },
)

const results = computed<DocumentHit[]>(() => data.value?.results ?? [])

const columns: Column<DocumentHit>[] = [
  { key: 'title', label: 'Title' },
  { key: 'source_system', label: 'Source' },
  { key: 'document_type', label: 'Type' },
  { key: 'retrieved_at', label: 'Retrieved', mono: true },
  { key: 'source_url', label: 'Document', link: true },
]

useHead({ title: 'SectorTrace — Documents' })
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Documents</h1>
      <p class="opacity-70 max-w-2xl">
        Search the document corpus. Every result links to the exact archived
        source.
      </p>
    </div>

    <input
      v-model.lazy="q"
      type="search"
      placeholder="Search documents…"
      class="text-sm border border-black/15 dark:border-white/15 rounded px-3 py-1.5 bg-transparent w-full max-w-md"
    >

    <div v-if="!q.trim()" class="text-sm opacity-60">
      Enter a search term to look through the corpus.
    </div>
    <div v-else-if="pending" class="text-sm opacity-60">Searching…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <UCard v-else>
      <template #header>
        <span class="text-sm font-medium">{{ results.length }} results</span>
      </template>
      <StEvidenceTable
        v-if="results.length"
        :columns="columns"
        :rows="results"
        row-key="document_id"
      />
      <StEmptyState v-else />
    </UCard>
  </section>
</template>
