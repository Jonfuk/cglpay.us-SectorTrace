<script setup lang="ts">
import { safetySupporting, safetyText, type SafetyRow } from '~/lib/safety'
import type { HseCorpus, PfdCorpus } from '~/types/safety'
import { downloadEvidenceJson } from '~/lib/evidence-export'
const props = defineProps<{ source: 'pfd' | 'sar' | 'hse' }>()
const api = usePublicApi()
const endpoint = computed(() => props.source === 'hse' ? 'safety' : 'pfd')
const { data, pending, error, refresh } = await useAsyncData(() => `public-safety-corpus-${endpoint.value}`, (_app, { signal }) => api.get<PfdCorpus & HseCorpus>(`/${endpoint.value}`, { signal }))
const corpus = computed(() => props.source === 'sar' ? data.value?.sar : data.value)
const definition = computed(() => safetySupporting[props.source]!)
const rows = computed(() => props.source === 'hse' ? data.value?.notices : corpus.value?.recent)
const caveats = computed(() => props.source === 'hse' ? { hse: data.value?.caveat ?? null } : corpus.value?.caveats ?? {})
const totals = computed(() => props.source === 'hse' ? [['Returned matched register notices', data.value?.total]] : props.source === 'pfd' ? [['Reports held', corpus.value?.totals?.reports], ['Reports with concern text held', corpus.value?.totals?.with_concerns], ['Metadata stubs without concern text', corpus.value?.totals?.stubs], ['Sent-to provider relationships', corpus.value?.mentions?.sent_to_providers], ['Named-in provider relationships', corpus.value?.mentions?.naming_providers], ['Distinct recipient organisations', corpus.value?.mentions?.recipient_organisations]] : [['Library documents held', corpus.value?.totals?.documents], ['Documents with extracted text', corpus.value?.totals?.with_text], ['Documents with a supplied board name', corpus.value?.totals?.with_board_name], ['Documents naming tracked providers', corpus.value?.mentions?.naming_providers]])
const summaries = computed(() => props.source === 'hse' ? [
  { key: 'by_type', title: 'Returned register notices by type', rows: data.value?.by_type, columns: [{ key: 'notice_type', label: 'Published notice type' }, { key: 'notice_count', label: 'Notices', numeric: true }] },
  { key: 'by_provider', title: 'Returned register notices by matched provider', rows: data.value?.by_provider, columns: [{ key: 'provider_name', label: 'Matched provider' }, { key: 'provider_key', label: 'Provider identifier' }, { key: 'notice_count', label: 'Notices', numeric: true }] },
] : [
  { key: 'by_year', title: props.source === 'pfd' ? 'Reports by parsed report year' : 'Documents by library year, not report date', rows: corpus.value?.by_year, columns: [{ key: 'year', label: props.source === 'pfd' ? 'Parsed report year' : 'Library year' }, { key: props.source === 'pfd' ? 'reports' : 'documents', label: props.source === 'pfd' ? 'Reports' : 'Documents', numeric: true }, { key: props.source === 'pfd' ? 'with_concerns' : 'with_text', label: 'With text held', numeric: true }] },
  { key: props.source === 'pfd' ? 'by_coroner_area' : 'by_board', title: props.source === 'pfd' ? 'Coroner areas, up to 25 returned' : 'Named boards, up to 25 returned', rows: props.source === 'pfd' ? corpus.value?.by_coroner_area : corpus.value?.by_board, columns: [{ key: props.source === 'pfd' ? 'coroner_area' : 'sab_name', label: props.source === 'pfd' ? 'Coroner area' : 'Board as supplied' }, { key: props.source === 'pfd' ? 'reports' : 'documents', label: props.source === 'pfd' ? 'Reports' : 'Documents', numeric: true }] },
  { key: 'concern_terms', title: 'Keyword occurrences, up to 25 returned', rows: corpus.value?.concern_terms, columns: [{ key: 'term', label: 'Keyword' }, { key: 'occurrences', label: 'Occurrences', numeric: true }] },
])
function downloadSummary(key: string, rows: SafetyRow[]) { downloadEvidenceJson(`safety-${props.source}-${key}`, rows, { scope: 'returned-unfiltered-source-summary', endpoint: `/api/v1/${endpoint.value}`, source_array: `${props.source === 'sar' ? 'sar.' : ''}${key}`, request_filters: {}, caveats: caveats.value, source_url: null, retrieved_at: null, payload_sha256: null, limitations: 'Aggregate rows do not include row-level source metadata. Keyword occurrences are reading aids, not counts of findings. Library years are not report dates.' }) }
</script>
<template>
  <section class="space-y-5" :aria-label="`${definition.title} corpus`"><p class="atlas-caveat">Unfiltered source collection. Source, relationship, provider and year selections from the chronology do not constrain this response.</p><StEvidenceState :pending="pending" :error="error" @retry="refresh">
    <template v-if="corpus"><h2>Source collection coverage</h2><p class="atlas-footnote">These supplied counts describe different subsets and counting units. They must not be added together.</p><dl class="st-safety-totals"><template v-for="([label, value], index) in totals" :key="index"><dt>{{ label }}</dt><dd>{{ safetyText(value) }}</dd></template></dl>
      <StSafetyRecords v-if="Array.isArray(rows)" :definition="definition" :rows="rows" :query="{}" :caveats="caveats" /><p v-else role="status">The source record array was not supplied. This is not an empty collection.</p>
      <template v-if="source === 'pfd'"><a class="atlas-button" href="/api/v1/export?endpoint=pfd&amp;format=csv">Download all held PFD reports CSV</a><p class="atlas-footnote">This server export covers the complete held PFD report collection. It does not include SAR documents or chronology relationships.</p></template>
      <p v-if="source !== 'hse'" class="atlas-caveat">Coroner areas and named safeguarding boards are not local authority boundaries. Keyword occurrences help find material to read. They are not findings or incident counts.</p>
      <section v-for="summary in summaries" :key="summary.key" class="space-y-3" :aria-label="summary.title"><h3>{{ summary.title }}</h3><template v-if="Array.isArray(summary.rows)"><StEvidenceTable :columns="summary.columns" :rows="summary.rows" :caption="summary.title" /><button type="button" class="atlas-button" @click="downloadSummary(summary.key, summary.rows)">Download this source summary JSON</button></template><p v-else role="status">This source summary was not supplied.</p></section>
    </template><p v-else role="status">This source collection was not supplied.</p>
  </StEvidenceState></section>
</template>
<style scoped>
.st-safety-totals { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; max-width: 650px; } dt { color: var(--text-muted); } dd { font-variant-numeric: tabular-nums; }
</style>
