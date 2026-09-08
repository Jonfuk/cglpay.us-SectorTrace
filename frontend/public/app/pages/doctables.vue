<script setup lang="ts">
import { downloadEvidenceJson } from '~/lib/evidence-export'
interface TableRow { document_table_id?: string; element_id?: string; page_number?: number | null; row_count?: number | null; column_count?: number | null; extraction_status?: string; preview?: unknown[][]; [key: string]: unknown }
interface Response {
  document?: { document_id?: string; title?: string | null; source_url?: string | null; retrieved_at?: string | null }
  tables?: TableRow[]
  grid?: unknown[][]
  document_table_id?: string
  element_id?: string
  page_number?: number | null
  extraction_status?: string
  caption?: string | null
  markdown?: string | null
  context?: Record<string, unknown>[]
  note?: string
  [key: string]: unknown
}
const api = usePublicApi()
const filters = useFilterState()
const route = useRoute()
const scalar = (key: string) => { const value = filters.get(key); return Array.isArray(value) ? value[0] ?? '' : value ?? '' }
const tableId = computed(() => scalar('table_id'))
const documentId = computed(() => scalar('document_id'))
const valid = computed(() => !['table_id', 'document_id'].some(key => Array.isArray(filters.get(key))) && !!(tableId.value.trim() || documentId.value.trim()))
// A table ID is the exact lookup. An accompanying document ID is checked against
// the returned parent rather than silently replacing an old table with an active one.
const query = computed(() => tableId.value ? { table_id: tableId.value } : { document_id: documentId.value })
const signature = computed(() => JSON.stringify({ query: query.value, parent: documentId.value, valid: valid.value }))
const { data, pending, error, refresh } = await useAsyncData('public-extracted-tables', async (_app, { signal }) => {
  const key = signature.value
  const response = valid.value ? await api.get<Response>('/document_tables', { query: query.value, signal }) : null
  return { key, response }
}, { watch: [signature] })
const current = computed(() => !pending.value && !error.value && data.value?.key === signature.value ? data.value.response : null)
const mismatch = computed(() => !!(tableId.value && documentId.value && current.value && current.value.document?.document_id !== documentId.value))
const tables = computed(() => Array.isArray(current.value?.tables) ? current.value.tables : null)
const grid = computed(() => Array.isArray(current.value?.grid) && current.value.grid.every(Array.isArray) ? current.value.grid : null)
const offset = computed(() => /^\d+$/.test(scalar('offset')) && Number.isSafeInteger(Number(scalar('offset'))) ? Number(scalar('offset')) : 0)
const shownTables = computed(() => (tables.value ?? []).slice(offset.value, offset.value + 10))
const shownGrid = computed(() => (grid.value ?? []).slice(offset.value, offset.value + 50))
const draftKind = ref(tableId.value ? 'table_id' : 'document_id')
const draftId = ref(tableId.value || documentId.value)
watch(signature, () => { draftKind.value = tableId.value ? 'table_id' : 'document_id'; draftId.value = tableId.value || documentId.value })
const limitations = 'Document lists use the active parse and show at most three preview rows per table. Exact table IDs can refer to an older parse. The API converts null cells to empty strings, other cells to text and omits malformed non-row entries. Empty cells therefore cannot distinguish an original blank from a null. Surrounding excerpts are shortened to 280 characters each. The suggested caption is a nearby heading, title or caption selected by the API. Raw file hashes and the parse version ID are not returned.'
const context = computed(() => ({ endpoint: '/api/v1/document_tables', request: query.value, document: current.value?.document ?? null, note: current.value?.note ?? null, limitations, view: '#' + route.fullPath }))
function download() { if (current.value && !mismatch.value) downloadEvidenceJson('extracted-table-response', [current.value], { ...context.value, scope: tableId.value ? 'complete-returned-table-detail' : 'complete-returned-active-parse-table-list-with-previews' }) }
function openTable(id: string) { return filters.setAll({ document_id: current.value?.document?.document_id, table_id: id }) }
function csv() {
  if (!grid.value || mismatch.value) return
  const cell = (value: unknown) => {
    const text = value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value)
    const safe = /^[\s]*[=+@-]|^[\t\r\n]/u.test(text) ? "'" + text : text
    return '"' + safe.replaceAll('"', '""') + '"'
  }
  const blob = new Blob(['\uFEFF', grid.value.map(row => row.map(cell).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'returned-table-grid.csv'
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
function cellText(value: unknown) { return value === '' ? 'Empty cell' : value == null ? 'Null cell' : typeof value === 'object' ? JSON.stringify(value) : String(value) }
useHead({ title: 'Document tables · SectorTrace' })
</script>
<template>
  <section class="space-y-6">
    <header class="st-page-header"><p class="atlas-eyebrow">Verification tools</p><h1>Document tables</h1><p>Inspect extracted grids alongside their document and surrounding text. Check the source before using a cell as evidence.</p></header>
    <form class="flex flex-wrap items-end gap-3" @submit.prevent="filters.setAll({ [draftKind]: draftId })"><label>Lookup<select v-model="draftKind" class="block rounded border p-2"><option value="document_id">Document ID</option><option value="table_id">Exact table ID</option></select></label><label class="min-w-0 flex-1">Identifier<input v-model="draftId" required class="block w-full rounded border p-2"></label><button class="atlas-button primary" type="submit">Open tables</button></form>
    <p v-if="!valid" role="status">Supply a document or exact table identifier. Repeated identifiers are not supported.</p>
    <StEvidenceState v-else :pending="pending" :error="error" @retry="refresh"><template v-if="current">
      <p v-if="mismatch" role="alert">The returned table does not establish a match to the requested document. Check the identifiers. No replacement table has been selected.</p>
      <template v-else>
        <h2>{{ current.document?.title ?? current.document?.document_id ?? 'Document not supplied' }}</h2>
        <p>Retrieved: {{ current.document?.retrieved_at ?? 'Not supplied' }}</p>
        <div class="flex flex-wrap gap-3"><StLink v-if="current.document?.source_url" :href="current.document.source_url">Open original source</StLink><NuxtLink v-if="current.document?.document_id" :to="{ path: '/documents/' + encodeURIComponent(current.document.document_id), query: { element_id: current.element_id || undefined } }">Open document reader</NuxtLink><NuxtLink v-if="current.document?.source_url" :to="{ path: '/links', query: { url: current.document.source_url } }">Inspect recorded source link</NuxtLink></div>
        <p class="atlas-caveat">{{ limitations }}</p>
        <p v-if="tableId">The document reader uses the active parse. An older table element may no longer resolve there.</p>
        <button type="button" class="atlas-button" @click="download">Download returned tables JSON</button>
        <details v-if="current.note"><summary>Original extraction note</summary><p class="whitespace-pre-wrap">{{ current.note }}</p></details>
        <template v-if="!tableId">
          <p v-if="!tables" role="status">The table list was not supplied.</p><p v-else-if="!tables.length" role="status">No tables were returned for the active parse. This does not establish that the source document contains no tables.</p>
          <template v-else>
            <p>{{ tables.length }} returned tables. Showing up to 10 from offset {{ offset }}.</p>
            <section v-for="(table, index) in shownTables" :key="index" class="atlas-panel atlas-panel-body space-y-3">
              <h3>Table {{ offset + index + 1 }} · page {{ table.page_number ?? 'Not supplied' }}</h3>
              <p>Extraction status: {{ table.extraction_status ?? 'Not supplied' }}. Reported dimensions: {{ table.row_count ?? 'Not supplied' }} rows, {{ table.column_count ?? 'Not supplied' }} columns.</p>
              <p>Preview only, up to three rows. Reported dimensions may be calculated by the API when stored dimensions are absent.</p>
              <div v-if="Array.isArray(table.preview) && table.preview.length" class="st-grid" role="region" :aria-label="'Table ' + (offset + index + 1) + ' preview'" tabindex="0"><table><caption class="sr-only">Extracted preview without inferred headers</caption><tbody><tr v-for="(row, ri) in table.preview" :key="ri"><td v-for="(cell, ci) in row" :key="ci" :class="{ 'opacity-60 italic': cell === '' || cell == null }">{{ cellText(cell) }}</td></tr></tbody></table></div>
              <p v-else>No preview grid supplied. Open the table for its extraction text and status.</p>
              <button v-if="table.document_table_id" type="button" class="atlas-button" @click="openTable(table.document_table_id)">Open exact table {{ offset + index + 1 }}</button>
            </section>
          </template>
        </template>
        <template v-else>
          <h2>Exact table {{ current.document_table_id ?? tableId }}</h2><p>Page: {{ current.page_number ?? 'Not supplied' }}. Extraction status: {{ current.extraction_status ?? 'Not supplied' }}.</p>
          <p v-if="current.caption">Suggested caption: {{ current.caption }}</p>
          <p v-if="!grid" role="status">A valid grid array was not supplied.</p><p v-else-if="!grid.length" role="status">No structured cells were returned. Any extraction text is shown below.</p>
          <template v-else><p>{{ grid.length }} returned grid rows. Showing up to 50 from offset {{ offset }}. Empty cell and Null cell are display markers, not source text. Row lengths are preserved and no headers are inferred.</p>
            <button type="button" class="atlas-button" @click="csv">Download full returned grid CSV</button><p>CSV has no added header. Formula-like text is prefixed with an apostrophe for spreadsheet safety. Keep the JSON download for unaltered values and source context.</p>
            <div class="st-grid" role="region" aria-label="Returned extracted grid" tabindex="0"><table><caption class="sr-only">Returned extracted cells without inferred headers</caption><tbody><tr v-for="(row, ri) in shownGrid" :key="ri"><td v-for="(cell, ci) in row" :key="ci" :class="{ 'opacity-60 italic': cell === '' || cell == null }">{{ cellText(cell) }}</td></tr></tbody></table></div>
          </template>
          <details v-if="current.markdown != null"><summary>Extraction text as returned</summary><pre class="whitespace-pre-wrap break-words">{{ current.markdown }}</pre></details>
          <h2>Surrounding excerpts</h2><StComparisonRecords :rows="current.context" scope="table:context" title="Surrounding excerpts" :context="context" />
        </template>
        <nav v-if="(tableId ? grid?.length : tables?.length)" aria-label="Extracted table pages" class="flex gap-2"><button type="button" class="atlas-button" :disabled="!offset" @click="filters.set('offset', String(Math.max(0, offset - (tableId ? 50 : 10))))">Previous page</button><button type="button" class="atlas-button" :disabled="offset + (tableId ? 50 : 10) >= (tableId ? grid?.length ?? 0 : tables?.length ?? 0)" @click="filters.set('offset', String(offset + (tableId ? 50 : 10)))">Next page</button><button v-if="offset" type="button" class="atlas-button" @click="filters.set('offset', undefined)">First page</button></nav>
      </template>
    </template></StEvidenceState>
  </section>
</template>
<style scoped>
.st-grid { overflow: auto; max-width: 100%; }
.st-grid table { border-collapse: collapse; }
.st-grid td { padding: 10px 12px; border: 1px solid var(--st-border, #555); vertical-align: top; white-space: pre-wrap; min-width: 100px; max-width: 480px; overflow-wrap: anywhere; }
</style>
