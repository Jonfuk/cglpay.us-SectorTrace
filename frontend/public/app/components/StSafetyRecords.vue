<script setup lang="ts">
import { safetyCell, safetyChronology, safetyDateGroup, safetyRecordKey, safetyText, type SafetyDefinition, type SafetyRow } from '~/lib/safety'
import { downloadEvidenceCsv, downloadEvidenceJson } from '~/lib/evidence-export'
const props = defineProps<{ definition: SafetyDefinition; rows: SafetyRow[]; query: Record<string, string | undefined>; caveats: Record<string, string | null>; truncated?: boolean }>()
const route = useRoute()
const filters = useFilterState()
const notebook = useNotebook()
const status = ref('')
const offsetKey = computed(() => `${props.definition.key}_offset`)
const offset = computed(() => { const value = Number(filters.get(offsetKey.value) ?? 0); return Number.isSafeInteger(value) && value >= 0 ? value : 0 })
const ordered = computed(() => props.definition.chronology ? safetyChronology(props.rows, props.definition.dateKey) : props.rows)
const displayed = computed(() => ordered.value.slice(offset.value, offset.value + 25))
const selection = computed(() => filters.get('safety_lane') === props.definition.key ? String(filters.get('safety_record') ?? '') : '')
const candidates = computed(() => selection.value ? props.rows.filter(row => safetyRecordKey(props.definition, row) === selection.value) : [])
const selected = computed(() => candidates.value.length === 1 ? candidates.value[0] : undefined)
const chronology = computed(() => props.definition.chronology && filters.get(`${props.definition.key}_view`) !== 'data')
const groupNames = { dated: 'Dated entries, newest first', 'other-date': 'Other published date text, retained without chronological placement', undated: 'Undated entries' }
const provenanceLimit = computed(() => props.definition.chronology ? 'This event response supplies a source link but no retrieval date, payload hash or separate record identifier. The selection uses the returned source, relationship, organisation, title, date and URL together. Identical entries remain ambiguous.' : 'This response does not include a payload hash. Text availability is not a finding about whether concerns existed.')
const label = (row: SafetyRow) => safetyText(row.title ?? row.report_ref ?? row.sab_name ?? row.notice_number ?? row.document_url)
const keyFor = (row: SafetyRow) => safetyRecordKey(props.definition, row)
let trigger: HTMLElement | null = null
async function inspect(row: SafetyRow, event: Event) {
  trigger = event.currentTarget as HTMLElement | null
  await filters.setAll({ ...filters.all(), safety_lane: props.definition.key, safety_record: keyFor(row) })
  await nextTick()
  document.querySelector<HTMLElement>('.st-inspector-heading')?.focus()
}
async function close() { await filters.setAll({ ...filters.all(), safety_lane: undefined, safety_record: undefined }); await nextTick(); if (trigger?.isConnected) trigger.focus() }
function scope() {
  return { scope: 'displayed-page-of-returned-source-array', endpoint: `/api/v1/${props.definition.endpoint}`, source_array: props.definition.array, request_filters: props.query, canonical_query: `/api/v1/${props.definition.endpoint}?${new URLSearchParams(Object.entries(props.query).filter((pair): pair is [string, string] => pair[1] !== undefined))}`, local_offset: offset.value, returned_rows_in_this_source: props.rows.length, displayed_rows: displayed.value.length, response_truncated: props.truncated ?? null, ordering: props.definition.chronology ? 'Recognised complete dates descending, other supplied date text, then undated. Original source dates preserved.' : 'Returned source order', retained_view: `#${route.fullPath}`, date_basis: props.definition.description, caveats: props.caveats, provenance_limitations: provenanceLimit.value, csv_notes: 'CSV protects formula-like text. JSON preserves original values.' }
}
function download(kind: 'json' | 'csv' | 'references') {
  const name = `safety-${props.definition.key}-displayed-rows`
  if (kind === 'csv') downloadEvidenceCsv(name, displayed.value)
  else if (kind === 'json') downloadEvidenceJson(name, displayed.value, scope())
  else downloadEvidenceJson(`${name}.provenance`, displayed.value.map(row => ({ record_identity: keyFor(row), source_url: row.source_url ?? null, report_url: row.report_url ?? null, document_url: row.document_url ?? null, retrieved_at: row.retrieved_at ?? null, payload_sha256: row.payload_sha256 ?? null, source_date: props.definition.dateKey ? row[props.definition.dateKey] ?? null : null, library_year: row.library_year ?? null, relationship: row.relationship ?? null, record: row })), scope())
}
function save() { if (selected.value) status.value = notebook.add({ title: `${props.definition.title}: ${label(selected.value)}`, href: `#${route.fullPath}`, note: JSON.stringify({ ...scope(), scope: 'selected-returned-source-record', record: selected.value }, null, 2) }) ? 'Evidence reference saved to this browser’s notebook.' : 'This browser could not save the reference.' }
watch(selection, () => { status.value = '' })
</script>
<template>
  <section class="space-y-4" :aria-label="definition.title">
    <h2>{{ definition.title }}</h2><p>{{ definition.description }}</p>
    <p class="atlas-footnote">{{ rows.length }} returned entries in this source. {{ displayed.length }} displayed.<span v-if="definition.chronology"> An organisation relationship is not a count of distinct incidents.</span></p>
    <div class="flex flex-wrap gap-2" role="group" :aria-label="`${definition.title} exports`"><button type="button" class="atlas-button" @click="download('json')">Download displayed rows JSON</button><button type="button" class="atlas-button" @click="download('csv')">Download displayed rows CSV</button><button type="button" class="atlas-button" @click="download('references')">Download reference manifest</button></div>
    <p class="atlas-footnote">Keep the reference manifest with the CSV. Downloads cover this displayed source page.</p>
    <div v-if="definition.chronology" class="flex gap-2" role="group" :aria-label="`${definition.title} presentation`"><button type="button" class="atlas-button" :aria-pressed="chronology" @click="filters.set(`${definition.key}_view`, 'chronology')">Chronology</button><button type="button" class="atlas-button" :aria-pressed="!chronology" @click="filters.set(`${definition.key}_view`, 'data')">Data</button></div>
    <div class="st-directory-workspace" :class="{ 'has-inspector': selection }"><div class="min-w-0 space-y-4">
      <ol v-if="chronology && displayed.length" class="st-safety-chronology" :aria-label="`${definition.title} chronology`"><li v-for="(row, index) in displayed" :key="`${keyFor(row)}:${index}`" :class="{ selected: keyFor(row) === selection }">
        <h3 v-if="index === 0 || safetyDateGroup(row, definition.dateKey) !== safetyDateGroup(displayed[index - 1]!, definition.dateKey)">{{ groupNames[safetyDateGroup(row, definition.dateKey)] }}</h3>
        <p class="atlas-footnote">{{ safetyText(row.date) }} · {{ safetyCell('relationship', row) }}</p><h4>{{ label(row) }}</h4><p>{{ safetyText(row.entity_name) }}</p><p v-if="row.result != null">Result as returned: {{ safetyText(row.result) }}</p>
        <button type="button" class="atlas-button" :aria-label="`Inspect ${label(row)}, ${safetyCell('relationship', row)}, displayed row ${index + 1}`" @click="inspect(row, $event)">Inspect source record</button>
      </li></ol>
      <div v-else-if="displayed.length" class="overflow-x-auto" role="region" :aria-label="`${definition.title} data`" tabindex="0"><table class="w-full text-sm"><caption class="text-left atlas-footnote">{{ definition.description }}</caption><thead><tr><th v-for="[key, title] in definition.columns" :key="key" scope="col">{{ title }}</th><th scope="col">Source</th></tr></thead><tbody><tr v-for="(row, index) in displayed" :key="`${keyFor(row)}:${index}`" :class="{ selected: keyFor(row) === selection }"><td v-for="[key] in definition.columns" :key="key">{{ safetyCell(key, row) }}</td><td><button type="button" class="atlas-button" :aria-label="`Inspect ${label(row)}, displayed row ${index + 1}`" @click="inspect(row, $event)">Inspect source record</button></td></tr></tbody></table></div>
      <StEvidenceState v-else empty :empty-title="offset ? 'No entries on this display page' : 'No entries returned for this source and selection'" message="This does not establish that no events occurred. Other sources and entries outside the response window remain separate." />
      <nav class="flex flex-wrap gap-3 items-center" :aria-label="`${definition.title} display pages`"><span class="atlas-footnote">{{ displayed.length ? `Rows ${offset + 1} to ${offset + displayed.length} of ${rows.length}` : 'No displayed rows' }}</span><button type="button" class="atlas-button" :disabled="!offset" @click="filters.set(offsetKey, String(Math.max(0, offset - 25)))">Previous</button><button type="button" class="atlas-button" :disabled="offset + displayed.length >= rows.length" @click="filters.set(offsetKey, String(offset + 25))">Next</button><button v-if="offset" type="button" class="atlas-button" @click="filters.set(offsetKey, undefined)">First page</button></nav>
    </div><StInspector v-if="selection" :title="selected ? label(selected) : 'Source record unavailable or ambiguous'" @close="close"><template v-if="selected"><p>{{ definition.title }}</p><p>{{ definition.description }}</p><dl class="st-safety-fields"><template v-for="(_value, key) in selected" :key="key"><dt>{{ String(key).replaceAll('_', ' ') }}</dt><dd>{{ safetyCell(String(key), selected) }}</dd></template></dl><StProvenance :provenance="selected" /><p class="atlas-footnote">{{ provenanceLimit }}</p><div class="st-inspector-actions"><StLink v-if="typeof selected.source_url === 'string'" :href="selected.source_url" class="atlas-button">Open supplied source</StLink><StLink v-if="typeof selected.report_url === 'string' && selected.report_url !== selected.source_url" :href="selected.report_url" class="atlas-button">Open supplied report</StLink><StLink v-if="typeof selected.document_url === 'string' && selected.document_url !== selected.source_url" :href="selected.document_url" class="atlas-button">Open supplied document</StLink><NuxtLink v-if="selected.entity_type === 'provider' && typeof selected.entity_key === 'string'" :to="`/providers/${encodeURIComponent(selected.entity_key)}`" class="atlas-button">Open supplied provider profile</NuxtLink><NuxtLink v-else-if="typeof selected.provider_key === 'string'" :to="`/providers/${encodeURIComponent(selected.provider_key)}`" class="atlas-button">Open supplied provider profile</NuxtLink><button type="button" class="atlas-button" @click="save">Save evidence reference</button></div><p role="status">{{ status }}</p></template><p v-else>The saved identifiers do not identify one entry in this returned source. No replacement has been selected.</p></StInspector></div>
    <p v-for="(text, key) in caveats" v-show="text" :key="key" class="atlas-caveat">{{ text }}</p>
  </section>
</template>
<style scoped>
th, td { padding: 8px; text-align: left; vertical-align: top; min-width: 125px; max-width: 350px; overflow-wrap: anywhere; border-bottom: 1px solid var(--border-subtle); }
th { color: var(--text-muted); font-weight: 500; }
.st-safety-chronology { list-style: none; padding: 0; }
.st-safety-chronology li { padding: 16px; border-left: 2px solid var(--border-subtle); margin-bottom: 12px; }
.st-safety-chronology h3 { margin-bottom: 16px; color: var(--text-muted); }
.st-safety-chronology h4 { font-weight: 600; }
.st-safety-chronology button { margin-top: 12px; }
.selected { background: var(--surface-elevated); }
.st-safety-fields { display: grid; grid-template-columns: minmax(95px, .8fr) minmax(0, 1.2fr); gap: 12px; margin: 16px 0; font-size: 13px; }
dt { color: var(--text-muted); } dd { overflow-wrap: anywhere; }
</style>
