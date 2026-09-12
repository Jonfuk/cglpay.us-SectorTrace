<script setup lang="ts">
import type { ContractPayload, Notice } from '~/types/contracts'
import { downloadEvidenceJson } from '~/lib/evidence-export'
const props = defineProps<{ payload: ContractPayload; query: Record<string, string | number | boolean | undefined> }>()
const filters = useFilterState()
const route = useRoute()
const id = computed(() => String(filters.get('notice_id') ?? ''))
const selected = computed(() => props.payload.notices.filter(row => row.notice_id === id.value))
const pageOffset = computed(() => props.payload.page?.offset ?? Number(props.query.offset ?? 0))
const pageLimit = computed(() => props.payload.page?.limit ?? Number(props.query.limit ?? 100))
const end = computed(() => pageOffset.value + props.payload.notices.length)
let trigger: HTMLElement | null = null
async function inspect(row: Notice, event: Event) { trigger = event.currentTarget as HTMLElement; await filters.set('notice_id', row.notice_id ?? undefined); await nextTick(); document.querySelector<HTMLElement>('.st-inspector-heading')?.focus() }
async function close() { await filters.set('notice_id', undefined); await nextTick(); if (trigger?.isConnected) trigger.focus() }
function page(delta: number) { return filters.setAll({ ...filters.all(), offset: String(Math.max(0, pageOffset.value + delta)), notice_id: undefined }) }
function value(row: Notice) { return row.value_core == null ? 'Value not supplied' : `${row.value_core.toLocaleString('en-GB', { maximumFractionDigits: 20 })} ${row.currency ?? '(currency not supplied)'}` }
function exportPage() { downloadEvidenceJson('procurement-notices-returned-page', props.payload.notices, { scope: 'returned-page', endpoint: '/api/v1/contracts', filters: props.query, total_matching: props.payload.total ?? null, caveats: props.payload.caveats, page: props.payload.page, view: `#${route.fullPath}` }) }
const fullExport = computed(() => {
  const params = new URLSearchParams({ endpoint: 'contracts', format: 'csv' })
  for (const [key, value] of Object.entries(props.query)) if (!['limit', 'offset'].includes(key) && value !== undefined) params.set(key, String(value))
  return `/api/v1/export?${params}`
})
</script>
<template>
  <section class="space-y-4">
    <h2>Published notices</h2><p class="atlas-footnote">Matching records: {{ payload.total ?? 'Not supplied' }} · Returned notice rows: {{ payload.notices.length }}. A notice can name more than one supplier and appear on more than one row.</p>
    <div class="flex flex-wrap gap-2"><button type="button" class="atlas-button" @click="exportPage">Download returned page JSON</button><a :href="fullExport" class="atlas-button">Download all matching notice rows CSV</a></div>
    <p class="atlas-footnote">JSON contains this page and its scope. The CSV download requests all matching rows from the server with these notice filters.</p>
    <div class="st-directory-workspace" :class="{ 'has-inspector': id }">
      <div class="min-w-0 space-y-4">
        <ul v-if="payload.notices.length" class="st-directory-list st-notice-list" aria-label="Returned notice rows"><li v-for="(row, index) in payload.notices" :key="`${row.notice_id}-${index}`" :class="{ selected: row.notice_id === id }"><div><h3>{{ row.title ?? 'Title not supplied' }}</h3><p>{{ row.date_published ?? 'Publication date not supplied' }} · {{ row.notice_id ?? 'Identifier not supplied' }}</p><p><NuxtLink v-if="row.buyer_ons_code" :to="`/authorities/${encodeURIComponent(row.buyer_ons_code)}`">{{ row.buyer_name ?? row.buyer_ons_code }}</NuxtLink><span v-else>{{ row.buyer_name ?? 'Buyer not supplied' }}</span> · Supplier: {{ row.supplier_name_raw ?? 'Not supplied' }}</p><p>Published value: {{ value(row) }}</p><p>{{ row.procedure_type ?? 'Procedure not supplied' }}</p><NuxtLink v-if="row.ocid" :to="{ path: `/contracts/process/${encodeURIComponent(row.ocid)}`, query: { from: `#${route.fullPath}`, notice_id: row.notice_id ?? undefined } }">Open procurement process</NuxtLink></div><button v-if="row.notice_id" class="atlas-button" type="button" :aria-label="`Inspect notice ${row.notice_id} for ${row.supplier_name_raw ?? 'unnamed supplier'}`" @click="inspect(row, $event)">Inspect</button></li></ul>
        <StEvidenceState v-else empty :empty-title="pageOffset ? 'No notices in this result window' : 'No matching notices returned'" message="Change the filters or return to the first page. Missing evidence is not evidence that no procurement took place." />
        <nav class="flex flex-wrap gap-3 items-center" aria-label="Notice pages"><span class="atlas-footnote">{{ payload.notices.length ? `Rows ${pageOffset + 1} to ${end}` : 'No loaded rows' }} · up to {{ pageLimit }} per page</span><button type="button" class="atlas-button" :disabled="!pageOffset" @click="page(-pageLimit)">Previous</button><button type="button" class="atlas-button" :disabled="payload.total == null || end >= payload.total" @click="page(pageLimit)">Next</button><button v-if="pageOffset" type="button" class="atlas-button" @click="page(-pageOffset)">First page</button></nav>
      </div>
      <StInspector v-if="id" :title="selected[0]?.title ?? (selected.length ? id : 'Notice not in this result window')" @close="close"><template v-if="selected.length"><p v-if="selected.length > 1" class="atlas-footnote">{{ selected.length }} returned rows share this notice identifier. Each supplier row and its source details is retained below.</p><details v-for="(row, index) in selected" :key="index" :open="index === 0"><summary>Supplier row: {{ row.supplier_name_raw ?? 'Name not supplied' }}</summary><StNoticeRecord :row="row" /></details></template><p v-else>Notice {{ id }} is not in this returned page. The result window may have changed since the link was saved. No replacement has been selected.</p></StInspector>
    </div>
  </section>
</template>
<style scoped>
.st-notice-list h3 { font-size: 15px; margin-bottom: 6px; }
.st-notice-list li { align-items: start; }
.st-notice-list li > div { min-width: 0; overflow-wrap: anywhere; }
.st-notice-list button { flex-shrink: 0; }
</style>
