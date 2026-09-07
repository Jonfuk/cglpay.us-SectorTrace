<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { canonicalQuery } from '~/lib/transport'
import { publicQuery } from '~/lib/public-query'
import type { DocumentSearchHit, DocumentSearchPayload } from '~/types/documents'
const api = usePublicApi()
const filters = useFilterState()
const q = computed(() => String(filters.get('q') ?? ''))
const draft = ref(q.value)
watch(q, value => { draft.value = value })
const query = computed(() => ({ ...publicQuery('/document_search', filters.all()), limit: 50 }))
const signature = computed(() => canonicalQuery(query.value))
const { data, pending, error, refresh } = await useAsyncData('public-document-search', (_app, { signal }) => q.value.trim() ? api.get<DocumentSearchPayload>('/document_search', { query: query.value, signal }) : Promise.resolve(null), { watch: [signature] })
const documentId = computed(() => String(filters.get('document_id') ?? ''))
const elementId = computed(() => String(filters.get('element_id') ?? ''))
const pane = computed(() => filters.get('pane') === 'reader' ? 'secondary' : 'primary')
const offset = computed(() => Number(filters.get('offset') ?? 0))
const searchContext = computed(() => Object.fromEntries(Object.entries(filters.all()).filter(([key]) => ['q', 'source_system', 'document_type', 'year_from', 'year_to', 'since_retrieved_at', 'offset'].includes(key))))
function search() { return filters.setAll({ ...searchContext.value, q: draft.value.trim() || undefined, offset: undefined }) }
function setFilter(key: string, value: string) { return filters.setAll({ ...searchContext.value, [key]: value || undefined, offset: undefined }) }
function read(row: DocumentSearchHit) { return filters.setAll({ ...filters.all(), document_id: row.document_id, element_id: row.document_element_id, pane: 'reader' }) }
function closeReader() { return filters.setAll(searchContext.value) }
useHead({ title: 'Document search · SectorTrace' })
</script>
<template>
  <section class="space-y-6">
    <header class="st-page-header"><p class="atlas-eyebrow">Documents</p><h1>Document search</h1><p>Search public committee papers and Community Drug Partnership documents. Matches are passages for reading, not verified relationships.</p></header>
    <form class="st-search-form" @submit.prevent="search"><label class="st-query">Search document text<input v-model="draft" type="search" placeholder="Enter search words"></label><button type="submit" class="atlas-button primary">Search</button></form>
    <div class="st-document-filters"><label>Source<select :value="String(filters.get('source_system') ?? '')" @change="setFilter('source_system', ($event.target as HTMLSelectElement).value)"><option value="">All public document sources</option><option value="committee_paper_promotion">Committee papers</option><option value="cdp_document_promotion">Community Drug Partnership documents</option></select></label><label>Document type<select :value="String(filters.get('document_type') ?? '')" @change="setFilter('document_type', ($event.target as HTMLSelectElement).value)"><option value="">All types</option><option v-for="item in data?.facets?.document_type ?? []" :key="item.value" :value="item.value">{{ item.value }} ({{ item.count }})</option></select></label><label>Published from<input type="number" placeholder="Year" :value="filters.get('year_from')" @change="setFilter('year_from', ($event.target as HTMLInputElement).value)"></label><label>Published to<input type="number" placeholder="Year" :value="filters.get('year_to')" @change="setFilter('year_to', ($event.target as HTMLInputElement).value)"></label><button type="button" class="atlas-button" @click="filters.setAll({ q: q || undefined })">Clear filters</button></div>
      <StSplitWorkspace v-if="documentId" storage-key="documents" primary-label="Results" secondary-label="Reader" :pane="pane" @pane="value => filters.set('pane', value === 'secondary' ? 'reader' : 'list')">
        <template #primary><StDocumentSearchPane :query="q" :data="data" :pending="pending" :error="error" :offset="offset" :selected="elementId" @retry="refresh" @read="read" @page="value => filters.set('offset', String(value))" /></template>
        <template #secondary><div class="atlas-actions"><NuxtLink :to="{ path: `/documents/${encodeURIComponent(documentId)}`, query: { ...searchContext, element_id: elementId || undefined } }" class="atlas-button">Open reader</NuxtLink><button type="button" class="atlas-button" @click="closeReader">Close reader</button></div><StPassageReader :document-id="documentId" :element-id="elementId || undefined" embedded @select="value => filters.set('element_id', value)" /></template>
      </StSplitWorkspace>
      <StDocumentSearchPane v-else :query="q" :data="data" :pending="pending" :error="error" :offset="offset" @retry="refresh" @read="read" @page="value => filters.set('offset', String(value))" />
    <div class="atlas-actions"><NuxtLink to="/contracts">Contract notices</NuxtLink><NuxtLink to="/pfd">Safety and legal records</NuxtLink><NuxtLink to="/catalogue">Dataset catalogue</NuxtLink></div>
  </section>
</template>
