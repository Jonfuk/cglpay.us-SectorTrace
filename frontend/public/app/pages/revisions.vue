<script setup lang="ts">
import { downloadEvidenceJson } from '~/lib/evidence-export'
interface Row {
  kind?: string
  a?: Record<string, unknown>
  b?: Record<string, unknown>
  fields?: Record<string, unknown>[]
  meta?: Record<string, unknown>[]
  text_changes?: Record<string, unknown>[]
  counts?: Record<string, number | null>
  same_ocid?: boolean | null
  truncated?: boolean | null
  note?: string | null
  [key: string]: unknown
}
const api = usePublicApi()
const filters = useFilterState()
const route = useRoute()
const scalar = (key: string) => { const value = filters.get(key); return Array.isArray(value) ? value[0] ?? '' : value ?? '' }
const kind = computed(() => scalar('kind') || 'ocds')
const subject = computed(() => scalar(kind.value === 'document' ? 'document_id' : 'ocid'))
const valid = computed(() => {
  if (['kind', 'ocid', 'document_id', 'a', 'b'].some(key => Array.isArray(filters.get(key))) || !['ocds', 'document'].includes(kind.value)) return false
  if (scalar(kind.value === 'document' ? 'ocid' : 'document_id')) return false
  return subject.value.trim() ? !scalar('a') && !scalar('b') : !!scalar('a').trim() && !!scalar('b').trim()
})
const query = computed(() => ({ kind: kind.value, ocid: scalar('ocid') || undefined, document_id: scalar('document_id') || undefined, a: scalar('a') || undefined, b: scalar('b') || undefined }))
const signature = computed(() => JSON.stringify({ query: query.value, valid: valid.value }))
const draftKind = ref(kind.value)
const mode = ref(subject.value || !scalar('a') && !scalar('b') ? 'recent' : 'pair')
const draftSubject = ref(subject.value)
const draftA = ref(scalar('a'))
const draftB = ref(scalar('b'))
watch(signature, () => { draftKind.value = kind.value; mode.value = subject.value ? 'recent' : 'pair'; draftSubject.value = subject.value; draftA.value = scalar('a'); draftB.value = scalar('b') })
function compare() {
  return filters.setAll({ kind: draftKind.value, [draftKind.value === 'document' ? 'document_id' : 'ocid']: mode.value === 'recent' ? draftSubject.value : undefined, a: mode.value === 'pair' ? draftA.value : undefined, b: mode.value === 'pair' ? draftB.value : undefined })
}
const { data, pending, error, refresh } = await useAsyncData('public-revision-comparison', async (_app, { signal }) => {
  const key = signature.value
  const response = valid.value ? await api.get<Row>('/record_diff', { query: query.value, signal }) : null
  return { key, response }
}, { watch: [signature] })
const current = computed(() => !pending.value && !error.value && data.value?.key === signature.value ? data.value.response : null)
const limitations = computed(() => kind.value === 'ocds'
  ? 'The subject selector requests the two most recently published notices. Explicit A and B preserve your chosen order. The API compares selected fields using the first supplier row for each notice. It does not compare all supplier rows or establish a new award. Source and derived changes remain separate. Payload hashes are not returned.'
  : 'The subject selector requests the two most recently created parsed versions. Explicit A and B preserve your chosen order. Elements are aligned by sequence, so an insertion can shift later comparisons. Unchanged elements are omitted. The comparison is limited to 600 sequence positions. Parser creation dates are not publication or retrieval dates. Source URLs and raw payload hashes are not returned. A text hash describes parsed text, not the original file.')
const context = computed(() => ({ endpoint: '/api/v1/record_diff', request: query.value, a: current.value?.a ?? null, b: current.value?.b ?? null, note: current.value?.note ?? null, truncated: current.value?.truncated ?? null, limitations: limitations.value, view: '#' + route.fullPath }))
function download() { if (current.value) downloadEvidenceJson('revision-comparison', [current.value], { ...context.value, scope: 'complete-returned-comparison-response' }) }
const pair = computed(() => {
  const id = kind.value === 'ocds' ? 'notice_id' : 'document_version_id'
  const a = current.value?.a?.[id], b = current.value?.b?.[id]
  return typeof a === 'string' && a && typeof b === 'string' && b ? { kind: kind.value, a, b } : null
})
useHead({ title: 'Compare revisions · SectorTrace' })
</script>
<template>
  <section class="space-y-6">
    <header class="st-page-header"><p class="atlas-eyebrow">Verification tools</p><h1>Compare revisions</h1><p>Inspect two procurement notices or parsed document versions, keeping source fields and derived changes separate.</p></header>
    <form class="atlas-panel atlas-panel-body space-y-4" @submit.prevent="compare">
      <div class="grid gap-4 md:grid-cols-2">
        <label>Record kind<select v-model="draftKind" class="block w-full rounded border p-2"><option value="ocds">Procurement notice</option><option value="document">Parsed document</option></select></label>
        <label>Version selection<select v-model="mode" class="block w-full rounded border p-2"><option value="recent">Two most recent versions</option><option value="pair">Explicit A and B</option></select></label>
      </div>
      <label v-if="mode === 'recent'" class="block">{{ draftKind === 'ocds' ? 'OCID' : 'Document ID' }}<input v-model="draftSubject" required class="block w-full rounded border p-2"></label>
      <div v-else class="grid gap-4 md:grid-cols-2"><label>A identifier<input v-model="draftA" required class="block w-full rounded border p-2"></label><label>B identifier<input v-model="draftB" required class="block w-full rounded border p-2"></label></div>
      <p>Explicit pairs use notice IDs for procurement or document version IDs for parsed documents.</p>
      <button class="atlas-button primary" type="submit">Compare</button>
    </form>
    <p v-if="!valid" role="status">Supply one subject identifier or a complete A/B pair. Mixed or repeated selectors cannot be compared.</p>
    <StEvidenceState v-else :pending="pending" :error="error" @retry="refresh"><template v-if="current">
      <p class="atlas-caveat">{{ limitations }}</p>
      <div class="flex flex-wrap gap-2"><button type="button" class="atlas-button" @click="download">Download returned comparison JSON</button><button v-if="subject && pair" type="button" class="atlas-button" @click="filters.setAll(pair)">Use this exact A/B pair</button></div>
      <p v-if="subject">This subject link can select different versions after new records arrive. Use the exact A/B pair to retain these identifiers.</p>
      <h2>Version A</h2><StComparisonRecords :rows="current.a ? [current.a] : null" scope="revision:a" title="Version A" :context="context" />
      <h2>Version B</h2><StComparisonRecords :rows="current.b ? [current.b] : null" scope="revision:b" title="Version B" :context="context" />
      <details v-if="current.note"><summary>Original comparison note</summary><p class="whitespace-pre-wrap">{{ current.note }}</p></details>
      <template v-if="current.kind === 'ocds'">
        <p>Identity check: {{ current.same_ocid === true ? 'Same OCID reported' : current.same_ocid === false ? 'Different OCIDs reported' : 'Not supplied' }}.</p>
        <p>Reported source fields changed: {{ current.counts?.changed_source ?? 'Not supplied' }}. Reported derived fields changed: {{ current.counts?.changed_derived ?? 'Not supplied' }}.</p>
        <h2>Notice fields</h2><StComparisonRecords :rows="current.fields" scope="revision:fields" title="Notice fields" :context="context" />
      </template>
      <template v-else-if="current.kind === 'document'">
        <p>Reported element changes: {{ current.counts?.changed ?? 'Not supplied' }} changed, {{ current.counts?.added ?? 'Not supplied' }} added, {{ current.counts?.removed ?? 'Not supplied' }} removed.</p>
        <p role="status">{{ current.truncated === true ? 'The comparison is truncated. Counts and changes cover only the returned comparison window.' : current.truncated === false ? 'The API reports no truncation of its sequence comparison.' : 'Truncation status was not supplied. Full document coverage cannot be established.' }}</p>
        <h2>Parser and version metadata</h2><StComparisonRecords :rows="current.meta" scope="revision:metadata" title="Parser and version metadata" :context="context" />
        <p v-if="Array.isArray(current.text_changes) && !current.text_changes.length">No changed elements were returned. This does not establish that the original documents are identical.</p>
        <h2>Changed text elements</h2><StComparisonRecords :rows="current.text_changes" scope="revision:text" title="Changed text elements" :context="context" />
      </template>
      <p v-else role="status">The response kind was not recognised. The complete response remains available to download.</p>
    </template></StEvidenceState>
  </section>
</template>
