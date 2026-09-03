<script setup lang="ts">
import { computed } from 'vue'
import type { DocumentTable, DocumentTablesResponse } from '~/types/api'

// Document tables route. The tables a parser extracted from one document, each
// grid shown exactly as the parser wrote it — no re-interpretation. Document is
// read from the URL (?document_id=). Parity target: legacy
// `public/js/pages/doctables.js`.
const api = usePublicApi()
const filters = useFilterState()

const documentId = computed(() => (filters.get('document_id') as string) ?? '')

const { data, pending, error } = await useDataRoute<DocumentTablesResponse | null>(
  'public-doctables',
  (f) => {
    if (!f.document_id) return Promise.resolve(null)
    return api.documentTables({ query: f })
  },
)

const tables = computed<DocumentTable[]>(() => data.value?.tables ?? [])

useHead({ title: 'SectorTrace — Document tables' })
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Document tables</h1>
      <p class="opacity-70 max-w-2xl">
        The tables a parser extracted from a document. Each grid is exactly what
        the parser wrote — nothing is re-interpreted here.
      </p>
    </div>

    <StEmptyState
      v-if="!documentId"
      title="Choose a document"
      message="Open this view from a document to see the tables extracted from it."
    />
    <div v-else-if="pending" class="text-sm opacity-60">Loading tables…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <div v-if="data?.document" class="space-y-1">
        <p class="text-sm font-medium">{{ data.document.title ?? data.document.document_id }}</p>
        <StLink :href="data.document.source_url">{{ data.document.source_url ?? '—' }}</StLink>
      </div>

      <StEmptyState v-if="!tables.length" />
      <UCard v-for="t in tables" v-else :key="t.document_table_id">
        <template #header>
          <span class="text-sm font-medium">
            Page {{ t.page_number ?? '—' }} · {{ t.row_count ?? '?' }}×{{ t.column_count ?? '?' }}
            <span class="opacity-60">· {{ t.extraction_status }}</span>
          </span>
        </template>
        <div class="overflow-x-auto">
          <table class="text-xs border-collapse">
            <tbody>
              <tr v-for="(gridRow, ri) in t.preview" :key="ri" class="border-b border-black/5 dark:border-white/5">
                <td v-for="(cellVal, ci) in gridRow" :key="ci" class="py-1 pr-3 align-top">
                  {{ cellVal }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </UCard>
    </template>
  </section>
</template>
