<script setup lang="ts">
import type { Notice } from '~/types/contracts'
const props = defineProps<{ row: Notice; processId?: string; processResponse?: boolean }>()
const route = useRoute()
const notebook = useNotebook()
const saved = ref('')
const process = computed(() => props.row.ocid ?? props.processId)
const fields = [['notice_id', 'Notice identifier'], ['notice_type_raw', 'Notice type'], ['buyer_name', 'Buyer'], ['supplier_name_raw', 'Supplier as published'], ['date_published', 'Published'], ['date_start', 'Published start date'], ['date_end', 'Published end date'], ['value_core', 'Published core value'], ['value_max', 'Published maximum value'], ['currency', 'Currency'], ['procedure_type', 'Procedure'], ['psr_basis', 'PSR basis'], ['psr_direct_award_option', 'PSR direct award option']] as const
const noticeLink = computed(() => props.row.notice_link ?? props.row.notice_web_url)
function save() {
  const note = [...fields.map(([key, label]) => `${label}: ${props.row[key] ?? 'Not supplied'}`), `Source: ${props.row.source_url ?? 'Not supplied'}`, `Retrieved: ${props.row.retrieved_at ?? 'Not supplied'}`, `SHA-256: ${props.row.payload_sha256 ?? 'Not supplied'}`, 'Notice values are not payments. This link restores a returned result window.'].join('\n')
  saved.value = notebook.add({ title: props.row.title ?? props.row.notice_id ?? 'Procurement notice', href: `#${route.fullPath}`, note }) ? 'Notice saved to this browser’s notebook.' : 'This browser could not save the notice.'
}
</script>
<template>
  <article class="space-y-4">
    <h3>{{ row.title ?? 'Title not supplied' }}</h3>
    <dl class="st-notice-fields"><template v-for="[key, label] in fields" :key="key"><dt>{{ label }}</dt><dd>{{ typeof row[key] === 'number' ? row[key].toLocaleString('en-GB', { maximumFractionDigits: 20 }) : row[key] ?? 'Not supplied' }}</dd></template></dl>
    <template v-if="row.suppliers"><h4>Suppliers named in this notice</h4><ul><li v-for="(supplier, index) in row.suppliers" :key="index">{{ supplier.name }} · {{ supplier.is_tracked_provider ? 'Matches a tracked provider name' : 'No tracked provider name match returned' }}</li></ul></template>
    <p class="atlas-footnote">This response supplies no provider key for this notice. Supplier names and match flags do not supply a profile identifier.</p>
    <p v-if="!processResponse" class="atlas-footnote">Notice type is not supplied by the list response. Open the procurement process, where available, for the source-defined stages.</p>
    <StProvenance :provenance="{ ...row, published_at: row.date_published }" />
    <p v-if="processResponse" class="atlas-footnote">The process response does not supply a payload hash. Its notice link may be published or constructed, and this response does not distinguish the two.</p>
    <p v-else class="atlas-footnote">Notice link basis: {{ row.notice_link_basis === 'constructed' ? 'constructed from the notice identifier' : row.notice_link_basis === 'published' ? 'published by the source' : 'not supplied' }}. Cite the data source and its hash as provenance.</p>
    <div class="st-inspector-actions"><StLink v-if="noticeLink" :href="noticeLink" class="atlas-button">Open notice</StLink><NuxtLink v-if="row.buyer_ons_code" class="atlas-button" :to="`/authorities/${encodeURIComponent(row.buyer_ons_code)}`">Open buyer profile</NuxtLink><NuxtLink v-if="process && !processResponse" class="atlas-button" :to="{ path: `/contracts/process/${encodeURIComponent(process)}`, query: { from: `#${route.fullPath}`, notice_id: row.notice_id ?? undefined } }">Open procurement process</NuxtLink><NuxtLink v-if="process" class="atlas-button" :to="{ path: '/revisions', query: { kind: 'ocds', ocid: process } }">Check process revisions</NuxtLink><NuxtLink v-if="process" class="atlas-button" :to="{ path: '/diary', query: { ocid: process } }">Open procurement dates</NuxtLink><button type="button" class="atlas-button" @click="save">Save notice</button></div><p role="status">{{ saved }}</p>
  </article>
</template>
<style scoped>
.st-notice-fields { display: grid; grid-template-columns: minmax(90px, .8fr) minmax(0, 1.2fr); gap: 12px; font-size: 13px; }
.st-notice-fields dt { color: var(--text-muted); }
.st-notice-fields dd { overflow-wrap: anywhere; }
</style>
