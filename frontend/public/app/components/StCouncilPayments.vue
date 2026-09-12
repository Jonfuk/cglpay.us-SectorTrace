<script setup lang="ts">
import type { PaymentPayload, Payment, EvidenceRow } from '~/types/contracts'
import type { Column } from '~/components/StEvidenceTable.vue'
import { downloadEvidenceJson } from '~/lib/evidence-export'
const props = defineProps<{ payload: PaymentPayload; query: Record<string, string | number | boolean | undefined> }>()
const filters = useFilterState()
const route = useRoute()
const notebook = useNotebook()
const saveStatus = ref('')
const local = computed(() => String(filters.get('payment_q') ?? ''))
const order = computed(() => String(filters.get('payment_sort') ?? 'returned'))
const selectedFile = computed(() => String(filters.get('file_url') ?? ''))
const selectedIndex = computed(() => String(filters.get('row_index') ?? ''))
const selectedAuthority = computed(() => String(filters.get('payment_authority') ?? ''))
const rows = computed(() => {
  const results = (props.payload.payments ?? []).filter(row => `${row.payee ?? ''} ${row.description ?? ''} ${row.period ?? ''}`.toLocaleLowerCase('en-GB').includes(local.value.toLocaleLowerCase('en-GB')))
  return order.value === 'payee' ? [...results].sort((a, b) => String(a.payee ?? '').localeCompare(String(b.payee ?? ''), 'en-GB')) : results
})
const candidates = computed(() => (props.payload.payments ?? []).filter(row => row.file_url === selectedFile.value && String(row.row_index) === selectedIndex.value && (!selectedAuthority.value || row.authority_ons_code === selectedAuthority.value)))
const selected = computed(() => candidates.value.length === 1 ? candidates.value[0] : undefined)
watch(selected, () => { saveStatus.value = '' })
const selectedSource = computed(() => (props.payload.files ?? []).find(row => row.file_url === selectedFile.value && row.authority_ons_code === selected.value?.authority_ons_code))
const inspecting = computed(() => Boolean(selectedFile.value))
let trigger: HTMLElement | null = null
async function inspect(row: Payment, event: Event) { trigger = event.currentTarget as HTMLElement; await filters.setAll({ ...filters.all(), file_url: row.file_url ?? undefined, row_index: row.row_index == null ? undefined : String(row.row_index), payment_authority: row.authority_ons_code ?? undefined }); await nextTick(); document.querySelector<HTMLElement>('.st-inspector-heading')?.focus() }
async function close() { await filters.setAll({ ...filters.all(), file_url: undefined, row_index: undefined, payment_authority: undefined }); await nextTick(); if (trigger?.isConnected) trigger.focus() }
function exportRows() { downloadEvidenceJson('council-payments-visible-returned-rows', rows.value, { scope: 'local-selection-of-returned-response', endpoint: '/api/v1/council_spend', filters: props.query, local_search: local.value, local_order: order.value, total_matching: props.payload.total ?? null, response_rows: props.payload.payments?.length ?? null, caveats: props.payload.caveats, view: `#${route.fullPath}` }) }
function exportFiles() { downloadEvidenceJson('council-transparency-files-returned', props.payload.files ?? [], { scope: 'returned-file-list', endpoint: '/api/v1/council_spend', authority_ons_code: props.query.authority_ons_code ?? null, provider_filter_applied: false, caveats: props.payload.caveats, view: `#${route.fullPath}` }) }
function savePayment() {
  if (!selected.value) return
  const note = JSON.stringify({ record: selected.value, scope: 'selected-row-from-returned-response', filters: props.query, caveats: props.payload.caveats }, null, 2)
  saveStatus.value = notebook.add({ title: `Published payment to ${selected.value.payee ?? 'unnamed payee'}`, href: `#${route.fullPath}`, note }) ? 'Payment reference saved to this browser’s notebook.' : 'This browser could not save the payment reference.'
}
const fileColumns: Column<EvidenceRow>[] = [{ key: 'authority_name', label: 'Authority' }, { key: 'file_format', label: 'Format' }, { key: 'parse_status', label: 'Parse status' }, { key: 'row_count', label: 'Reported rows', numeric: true }, { key: 'file_url', label: 'File', link: true }]
const details = [['authority_name', 'Authority'], ['period', 'Published period'], ['payee', 'Payee'], ['amount_text', 'Published amount'], ['amount', 'Parsed amount'], ['description', 'Description'], ['row_index', 'Source row']] as const
</script>
<template>
  <section class="space-y-5"><h2>Published council payments</h2><p>Payment lines come from council transparency files. Published periods, amounts and corrections remain as supplied. These rows are separate from procurement notices, grants and budgets.</p>
    <p class="atlas-footnote">Matching payment lines: {{ payload.total ?? 'Not supplied' }} · Returned lines: {{ payload.payments?.length ?? 'Not supplied' }} · Visible lines: {{ rows.length }}. This request asks for at most {{ query.limit }} lines. The endpoint offers no further-page or date filter.</p>
    <div class="flex flex-wrap gap-3 items-end"><label>Search returned payees, descriptions or periods<input type="search" :value="local" class="block" @change="filters.set('payment_q', ($event.target as HTMLInputElement).value || undefined)"></label><label>Order returned lines<select :value="order" class="block" @change="filters.set('payment_sort', ($event.target as HTMLSelectElement).value)"><option value="returned">Server order</option><option value="payee">Payee name</option></select></label><button type="button" class="atlas-button" @click="exportRows">Download visible payment rows JSON</button></div>
    <div class="st-directory-workspace" :class="{ 'has-inspector': inspecting }"><div class="min-w-0"><ul v-if="rows.length" class="st-directory-list" aria-label="Returned payment lines"><li v-for="(row, index) in rows" :key="`${row.file_url}-${row.row_index}-${index}`"><div><h3>{{ row.payee ?? 'Payee not supplied' }}</h3><p>{{ row.amount_text ?? 'Published amount not supplied' }} · {{ row.period ?? 'Period not supplied' }}</p><p>{{ row.authority_name ?? row.authority_ons_code ?? 'Authority not supplied' }} · Source row {{ row.row_index ?? 'Not supplied' }}</p><p>{{ row.description ?? 'Description not supplied' }}</p><NuxtLink v-if="row.provider_key" :to="`/providers/${encodeURIComponent(row.provider_key)}`">{{ row.canonical_name ?? row.provider_key }}</NuxtLink><p v-else>No matched provider identifier supplied</p></div><button v-if="row.file_url && row.row_index != null" type="button" class="atlas-button" :aria-label="`Inspect payment ${row.row_index} in ${row.file_url}`" @click="inspect(row, $event)">Inspect</button></li></ul><StEvidenceState v-else empty empty-title="No payment lines in this selection" message="Local search covers only returned lines. Check the file statuses for collection or parsing gaps." /></div>
      <StInspector v-if="inspecting" :title="selected?.payee ?? 'Payment not in this response'" @close="close"><template v-if="selected"><dl class="st-payment-details"><template v-for="[key, label] in details" :key="key"><dt>{{ label }}</dt><dd>{{ selected[key] ?? 'Not supplied' }}</dd></template></dl><p class="atlas-footnote">Published amount text is retained exactly. A missing parsed amount is not zero.</p><StProvenance :provenance="selected" /><StLink v-if="selected.file_url" :href="selected.file_url">Open transparency file</StLink><NuxtLink v-if="selected.authority_ons_code" class="atlas-button" :to="`/authorities/${encodeURIComponent(selected.authority_ons_code)}`">Open authority profile</NuxtLink><NuxtLink v-if="selected.provider_key" class="atlas-button" :to="`/providers/${encodeURIComponent(selected.provider_key)}`">Open matched provider</NuxtLink><p v-if="selectedSource" class="atlas-footnote">File parse status: {{ selectedSource.parse_status ?? 'Not supplied' }}</p><button type="button" class="atlas-button" @click="savePayment">Save payment reference</button><p role="status">{{ saveStatus }}</p><p class="atlas-footnote">This link identifies the authority, file and source row within the returned response. It may become unavailable after the result window changes.</p></template><p v-else>The selected authority, file and row do not identify one payment in this response. The record may be absent or ambiguous. No replacement payment has been selected.</p></StInspector>
    </div>
    <section class="space-y-3"><h2>Transparency files</h2><p>File coverage is filtered by authority only. The selected provider does not filter this list. Unreadable files remain visible as collection or parsing gaps.</p><button type="button" class="atlas-button" @click="exportFiles">Download returned file list JSON</button><StEvidenceTable :columns="fileColumns" :rows="payload.files" caption="Returned transparency files, independently of provider matching" source-details /><p v-if="!payload.files?.length">No file records were returned.</p></section>
    <StCaveat v-for="(text, key) in payload.caveats ?? {}" :key="key" :text="text" />
  </section>
</template>
<style scoped>
label { font-size: 13px; min-width: 0; max-width: 100%; }
input, select { min-height: 44px; padding: 8px; border: 1px solid var(--border-control); border-radius: 4px; max-width: 100%; }
.st-payment-details { display: grid; grid-template-columns: minmax(90px, .8fr) minmax(0, 1.2fr); gap: 12px; font-size: 13px; }
dt { color: var(--text-muted); }
dd, li > div { overflow-wrap: anywhere; min-width: 0; }
li button { flex-shrink: 0; }
</style>
