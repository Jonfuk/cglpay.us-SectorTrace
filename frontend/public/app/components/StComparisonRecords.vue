<script setup lang="ts">
import { connectionText } from '~/lib/connections'
import { downloadEvidenceCsv, downloadEvidenceJson } from '~/lib/evidence-export'
const props = defineProps<{ rows?: Record<string, unknown>[] | null; scope: string; title: string; context: Record<string, unknown> }>()
const filters = useFilterState()
const route = useRoute()
const notebook = useNotebook()
const get = (key: string) => { const value = filters.get(key); return Array.isArray(value) ? value[0] ?? '' : value ?? '' }
const offsetKey = computed(() => `offset_${props.scope}`)
const offset = computed(() => /^\d+$/.test(get(offsetKey.value)) ? Number(get(offsetKey.value)) : 0)
const records = computed(() => Array.isArray(props.rows) ? props.rows : null)
const displayed = computed(() => (records.value ?? []).slice(offset.value, offset.value + 25))
const fields = computed(() => [...new Set(displayed.value.flatMap(row => Object.keys(row)))])
const inspecting = computed(() => get('record_scope') === props.scope)
const selected = computed(() => {
  if (!inspecting.value || !/^\d+$/.test(get('record_index'))) return undefined
  const row = records.value?.[Number(get('record_index'))]
  return row && JSON.stringify(row) === get('record_snapshot') ? row : undefined
})
const status = ref('')
let trigger: HTMLElement | null = null
async function inspect(index: number, event: Event) { trigger = event.currentTarget as HTMLElement; await filters.setAll({ ...filters.all(), record_scope: props.scope, record_index: String(index), record_snapshot: JSON.stringify(records.value?.[index]) }); await nextTick(); document.querySelector<HTMLElement>('.st-inspector-heading')?.focus() }
async function close() { await filters.setAll({ ...filters.all(), record_scope: undefined, record_index: undefined, record_snapshot: undefined }); await nextTick(); if (trigger?.isConnected) trigger.focus() }
function exportContext(scope: string) { return { ...props.context, scope, table_scope: props.scope, local_offset: offset.value, returned_rows: records.value?.length ?? null, view: `#${route.fullPath}` } }
function download(kind: 'csv' | 'json' | 'references') { if (kind === 'csv') downloadEvidenceCsv('comparison-displayed-records', displayed.value); else downloadEvidenceJson(kind === 'references' ? 'comparison-source-reference' : 'comparison-displayed-records', kind === 'references' ? records.value ?? [] : displayed.value, exportContext(kind === 'references' ? 'complete-returned-selected-source-table' : 'displayed-table-page')) }
function save() { if (!selected.value) return; status.value = notebook.add({ title: `${props.title} record`, href: `#${route.fullPath}`, note: JSON.stringify({ ...exportContext('selected-record'), record: selected.value }, null, 2) }) ? 'Comparison record saved to this browser’s notebook.' : 'This browser could not save the reference.' }
function value(row: Record<string, unknown>, field: string) { const item = row[field]; return typeof item === 'number' && ['amount', 'value', 'count', 'total_income', 'total_expenditure', 'lower_ci_95', 'upper_ci_95'].includes(field) ? item.toLocaleString('en-GB') : connectionText(item) }
</script>
<template>
  <section class="space-y-4" :aria-label="`${title} records`"><p v-if="!records" role="status">The source did not supply a row array for this table.</p><template v-else><div class="flex flex-wrap gap-2"><button type="button" class="atlas-button" @click="download('csv')">Download displayed records CSV</button><button type="button" class="atlas-button" @click="download('json')">Download displayed records JSON</button><button type="button" class="atlas-button" @click="download('references')">Download source reference JSON</button></div><p class="atlas-footnote">Displayed downloads cover this table page. The source reference contains all returned rows for this table with source context and caveats. Keep it with the CSV.</p><p>{{ displayed.length }} displayed records of {{ records.length }} returned, starting at offset {{ offset }}.</p>
    <div class="st-inspector-layout" :class="{ 'has-inspector': inspecting }"><div class="space-y-3"><div v-if="displayed.length" class="overflow-x-auto" tabindex="0" role="region" :aria-label="`${title} returned observations`"><table><thead><tr><th scope="col">Inspection</th><th v-for="field in fields" :key="field" scope="col">{{ field.replaceAll('_', ' ') }}</th></tr></thead><tbody><tr v-for="(row, index) in displayed" :key="index"><td><button type="button" class="atlas-button" @click="inspect(offset + index, $event)">Inspect record {{ offset + index + 1 }}</button></td><td v-for="field in fields" :key="field"><StLink v-if="field === 'source_url'" :href="typeof row[field] === 'string' ? row[field] as string : null" /><template v-else>{{ value(row, field) }}</template></td></tr></tbody></table></div><p v-else role="status">No records are present on this table page. Missing observations are not zero.</p><nav class="flex gap-2" :aria-label="`${title} record pages`"><button type="button" class="atlas-button" :disabled="!offset" @click="filters.set(offsetKey, String(Math.max(0, offset - 25)))">Previous page</button><button type="button" class="atlas-button" :disabled="offset + 25 >= records.length" @click="filters.set(offsetKey, String(offset + 25))">Next page</button><button v-if="offset" type="button" class="atlas-button" @click="filters.set(offsetKey, undefined)">First page</button></nav></div>
    <StInspector v-if="inspecting" title="Comparison record" @close="close"><template v-if="selected"><h3>{{ title }}</h3><dl><template v-for="(item, field) in selected" :key="field"><dt>{{ String(field).replaceAll('_', ' ') }}</dt><dd>{{ connectionText(item) }}</dd></template></dl><StProvenance :provenance="selected" /><p class="atlas-footnote">Record provenance is shown only where supplied. Aggregate source context is separate and cannot establish this row’s retrieval date or payload hash.</p><details><summary>Selected source context</summary><pre>{{ JSON.stringify(context, null, 2) }}</pre></details><button type="button" class="atlas-button" @click="save">Save comparison record</button><p role="status">{{ status }}</p></template><p v-else role="status">The saved record is missing or changed. No replacement has been selected.</p></StInspector></div>
  </template></section>
</template>
<style scoped>th, td { text-align: left; vertical-align: top; padding: 10px; min-width: 140px; border-bottom: 1px solid var(--border-subtle); } dt { margin-top: 10px; color: var(--text-muted); } dd, pre { white-space: pre-wrap; overflow-wrap: anywhere; }</style>
