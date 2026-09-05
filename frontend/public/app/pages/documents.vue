<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DocumentHit, DocumentSearchResponse } from '~/types/api'

interface Facet { value: string; count: number }
interface DocumentExplorerResponse extends DocumentSearchResponse {
  results: DocumentHit[]
  total: number
  offset: number
  limit: number
  query: string
  facets: { source_system: Facet[]; document_type: Facet[] }
  caveat: string | null
}
interface DocumentElement { document_element_id: string; page_number: number | null; text: string | null; is_anchor?: boolean }
interface DocumentContext { title: string | null; document_type: string | null; source_system: string | null; published_at: string | null; retrieved_at: string | null; source_url: string | null; element_count: number; elements: DocumentElement[]; anchor_element_id?: string | null; has_more_before?: boolean; has_more_after?: boolean; caveat?: string | null }

const api = usePublicApi()
const filters = useFilterState()
const q = computed(() => String(filters.get('q') || ''))
const draft = ref(q.value)
const selected = ref<{ id: string; element: string | null } | null>(null)
const context = ref<DocumentContext | null>(null)
const contextPending = ref(false)
const contextError = ref<unknown>(null)

const { data, pending, error } = await useDataRoute<DocumentExplorerResponse | null>(
  'public-document-search',
  (f) => {
    const query = typeof f.q === 'string' ? f.q.trim() : ''
    if (!query) return Promise.resolve(null)
    return api.get<DocumentExplorerResponse>('/document_search', { query: { ...f, q: query, limit: 50 } })
  },
)

const results = computed(() => data.value?.results ?? [])
const facets = computed(() => data.value?.facets)
const offset = computed(() => Number(filters.get('offset') || 0))
const shownTo = computed(() => offset.value + results.value.length)
const hasMore = computed(() => shownTo.value < (data.value?.total ?? 0))

function searchNow(): void {
  selected.value = null
  context.value = null
  void filters.setAll({ q: draft.value.trim() || undefined, offset: undefined, source_system: undefined, document_type: undefined, year_from: undefined, year_to: undefined })
}
function setFilter(key: string, value: string): void { void filters.setAll({ ...filters.all(), [key]: value || undefined, offset: undefined }) }
function setYear(key: string, value: string): void { void filters.set(key, value || undefined) }
function more(): void { void filters.set('offset', String(shownTo.value)) }
function facetLabel(row: Facet): string { return `${row.value} (${row.count.toLocaleString('en-GB')})` }
function elementId(result: DocumentHit): string | number | null | undefined {
  const value = result.document_element_id
  return typeof value === 'string' || typeof value === 'number' ? value : undefined
}
async function openContext(documentId: string | number | null | undefined, elementId_: string | number | null | undefined): Promise<void> {
  if (!documentId || !elementId_) return
  selected.value = { id: String(documentId), element: String(elementId_) }
  contextPending.value = true
  contextError.value = null
  try {
    context.value = await api.get<DocumentContext>(`/documents/${encodeURIComponent(String(documentId))}`, { query: { element_id: String(elementId_), context: 8 } })
  } catch (err) { contextError.value = err }
  finally { contextPending.value = false }
}
async function moveContext(element: string | undefined): Promise<void> {
  if (!selected.value || !element) return
  await openContext(selected.value.id, element)
}
function titleFor(result: DocumentHit): string { return result.title || `${result.document_type || 'Document'} page ${result.page_number ?? ''}`.trim() }

useHead({ title: 'SectorTrace — Document search' })
</script>

<template>
  <section class="space-y-8">
    <div class="atlas-hero">
      <div>
        <p class="atlas-kicker">Document search · published text</p>
        <h1>Document search</h1>
        <p class="atlas-lede">Search the text of published committee papers and community drug partnership documents. This is not a search of the whole warehouse — structured evidence has its own pages.</p>
        <div class="atlas-actions"><a class="atlas-button primary" href="#document-search">Search the corpus</a><a class="atlas-button" href="#document-scope">Read the scope</a></div>
      </div>
      <div class="atlas-hero-aside"><div class="atlas-region"><strong>{{ data?.total?.toLocaleString('en-GB') ?? '—' }}</strong><span>{{ q ? 'matching pages' : 'search when ready' }}</span></div><div class="atlas-region"><strong>2</strong><span>published document streams</span></div></div>
    </div>

    <div id="document-scope" class="atlas-caveat"><span>What this searches</span> — only council committee papers and community drug partnership documents. A result is a page containing the term, not a finding. PFD reports, tribunal judgments and structured tables have separate routes.</div>

    <section id="document-search" class="atlas-section"><div class="atlas-section-head"><h2>Search the document corpus</h2><p>The query and scope filters form a shareable link.</p></div><div class="atlas-panel atlas-panel-body space-y-4"><form class="flex flex-wrap gap-2" @submit.prevent="searchNow"><input v-model="draft" class="min-w-0 flex-1 rounded border px-3 py-2" type="search" placeholder="Search committee papers and partnership documents" aria-label="Search document text"><button class="atlas-button primary" type="submit">Search</button></form><div class="grid gap-3 md:grid-cols-4"><label class="text-sm"><span class="block mb-1 opacity-70">Source</span><select class="w-full rounded border px-3 py-2" :value="String(filters.get('source_system') || '')" @change="setFilter('source_system', ($event.target as HTMLSelectElement).value)"><option value="">All sources</option><option v-for="item in facets?.source_system ?? []" :key="item.value" :value="item.value">{{ facetLabel(item) }}</option></select></label><label class="text-sm"><span class="block mb-1 opacity-70">Document type</span><select class="w-full rounded border px-3 py-2" :value="String(filters.get('document_type') || '')" @change="setFilter('document_type', ($event.target as HTMLSelectElement).value)"><option value="">All document types</option><option v-for="item in facets?.document_type ?? []" :key="item.value" :value="item.value">{{ facetLabel(item) }}</option></select></label><label class="text-sm"><span class="block mb-1 opacity-70">Published from</span><input class="w-full rounded border px-3 py-2" type="number" min="1990" max="2100" placeholder="Year" :value="String(filters.get('year_from') || '')" @change="setYear('year_from', ($event.target as HTMLInputElement).value)"></label><label class="text-sm"><span class="block mb-1 opacity-70">Published to</span><input class="w-full rounded border px-3 py-2" type="number" min="1990" max="2100" placeholder="Year" :value="String(filters.get('year_to') || '')" @change="setYear('year_to', ($event.target as HTMLInputElement).value)"></label></div><button v-if="filters.get('source_system') || filters.get('document_type') || filters.get('year_from') || filters.get('year_to')" class="atlas-button" type="button" @click="filters.setAll({ q: q || undefined })">Clear filters</button></div></section>

    <div v-if="!q.trim()" class="atlas-panel atlas-panel-body"><p>Enter a search term above to see matching pages.</p></div>
    <div v-else-if="pending" class="text-sm opacity-60">Searching…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <section v-if="selected" class="atlas-section"><div class="atlas-section-head"><h2>Reading room</h2><p>A bounded window around one matched passage. The whole source remains the citation target.</p></div><div class="atlas-panel atlas-panel-body"><div v-if="contextPending" class="text-sm opacity-60">Loading passage…</div><StEmptyState v-else-if="contextError" variant="unavailable" /><template v-else-if="context"><div class="grid gap-5 md:grid-cols-[minmax(0,0.35fr)_minmax(0,0.65fr)]"><div class="space-y-3"><h3>{{ context.title || selected.id }}</h3><dl class="text-sm opacity-70"><dt>Type</dt><dd>{{ context.document_type || '—' }}</dd><dt>Source</dt><dd>{{ context.source_system || '—' }}</dd><dt>Published</dt><dd>{{ context.published_at || '—' }}</dd><dt>Retrieved</dt><dd>{{ context.retrieved_at || '—' }}</dd><dt>Elements</dt><dd>{{ context.element_count.toLocaleString('en-GB') }}</dd></dl><a v-if="context.source_url" class="underline" :href="context.source_url" target="_blank" rel="noopener noreferrer">Open the source document ↗</a><button class="atlas-button" type="button" @click="selected = null; context = null">← Back to results</button></div><div class="space-y-3"><div class="flex gap-2"><button class="atlas-button" type="button" :disabled="!context.has_more_before" @click="moveContext(context.elements[0]?.document_element_id)">↑ Earlier</button><button class="atlas-button" type="button" :disabled="!context.has_more_after" @click="moveContext(context.elements[context.elements.length - 1]?.document_element_id)">Later ↓</button></div><article v-for="element in context.elements" :key="element.document_element_id" class="border-l-2 pl-3" :class="element.is_anchor ? 'border-[var(--st-teal)]' : 'border-[var(--st-line)]'"><p class="text-sm whitespace-pre-wrap">{{ element.text || '—' }}</p><small class="opacity-60">{{ element.page_number ? `Page ${element.page_number}` : 'Document element' }}</small></article></div></div><StCaveat v-if="context.caveat" :text="context.caveat" /></template></div></section>

      <section class="atlas-section"><div class="atlas-section-head"><h2>Results for “{{ q }}”</h2><p>{{ hasMore ? `Showing ${offset.toLocaleString('en-GB')}–${shownTo.toLocaleString('en-GB')} of ${data?.total.toLocaleString('en-GB')} matching pages.` : `${results.length.toLocaleString('en-GB')} matching pages.` }}</p></div><div class="space-y-3"><article v-for="result in results" :key="`${result.document_id}-${result.document_element_id}`" class="atlas-panel atlas-panel-body space-y-3"><div class="flex flex-wrap justify-between gap-3"><div><h3>{{ titleFor(result) }}</h3><p class="text-sm opacity-70">{{ result.document_type || 'Document' }}{{ result.page_number ? ` · page ${result.page_number}` : '' }}{{ result.source_system ? ` · ${result.source_system}` : '' }}</p></div><span class="text-sm opacity-60">{{ result.published_at || result.retrieved_at || 'date not published' }}</span></div><p class="text-sm whitespace-pre-wrap">{{ result.snippet || result.text || 'No extractable passage was returned.' }}</p><div class="flex flex-wrap gap-2"><button v-if="result.document_id && elementId(result)" class="atlas-button" type="button" @click="openContext(result.document_id, elementId(result))">Open in reading room</button><a v-if="result.source_url" class="atlas-button" :href="result.source_url" target="_blank" rel="noopener noreferrer">Read the source page ↗</a></div></article><StEmptyState v-if="!results.length" /></div><button v-if="hasMore" class="atlas-button primary" type="button" @click="more">Show more</button><StCaveat v-if="data?.caveat" :text="data.caveat" /></section>
    </template>
  </section>
</template>
