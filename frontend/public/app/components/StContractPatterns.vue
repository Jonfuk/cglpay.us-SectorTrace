<script setup lang="ts">
import type { ContractPayload } from '~/types/contracts'
import { noticeCounts } from '~/lib/notice-counts'
import { downloadEvidenceJson } from '~/lib/evidence-export'
const props = defineProps<{ payload: ContractPayload; query: Record<string, string | number | boolean | undefined> }>()
const filters = useFilterState()
const route = useRoute()
const choices = [{ key: 'year', label: 'Publication year', field: 'year', series: 'by_year' }, { key: 'quarter', label: 'Publication quarter', field: 'quarter', series: 'by_quarter' }, { key: 'procedure', label: 'Procedure', field: 'procedure_type', series: 'by_procedure_type' }, { key: 'band', label: 'Published value band', field: 'band_label', series: 'value_bands' }] as const
const choice = computed(() => choices.find(row => row.key === filters.get('pattern')) ?? choices[0])
const rows = computed(() => noticeCounts(props.payload[choice.value.series] ?? [], choice.value.field))
const selectedKey = computed(() => String(filters.get('aggregate') ?? ''))
const selected = computed(() => rows.value.find(row => row.key === selectedKey.value))
const showChart = computed(() => filters.get('pattern_view') !== 'data')
const aggregateFilters = computed(() => Object.fromEntries(Object.entries(props.query).filter(([key]) => !['limit', 'offset'].includes(key))))
const annotation = computed(() => `Source: /api/v1/contracts. Measure: published notice counts, not awards. Scope: matching API aggregate. Filters: ${JSON.stringify(aggregateFilters.value)}. ${(Object.values(props.payload.caveats ?? {}).filter(Boolean) as string[]).join(' ')} View: ${import.meta.client ? window.location.origin : ''}/#${route.fullPath}`)
function selectPattern(value: string) { return filters.setAll({ ...filters.all(), pattern: value, aggregate: undefined }) }
function years(from: string, to: string) { return filters.setAll({ ...filters.all(), year_from: from, year_to: to, offset: undefined, aggregate: undefined, notice_id: undefined }) }
function download() { downloadEvidenceJson('notice-counts-returned-aggregate', (props.payload[choice.value.series] ?? []).map(row => ({ [choice.value.field]: row[choice.value.field] ?? null, count: row.count ?? null })), { scope: 'returned-api-aggregate', endpoint: '/api/v1/contracts', measure: choice.value.label, unit: 'published notice count', filters: aggregateFilters.value, caveats: props.payload.caveats, source_metadata: 'Individual source URLs, retrieval dates and hashes are not supplied for aggregate rows.', view: `#${route.fullPath}` }) }
</script>
<template>
  <section class="space-y-4"><h2>Published notice patterns</h2><p>These counts cover matching notice rows, not distinct awards, payments or completed contracts. One notice may appear on several supplier rows.</p><div class="flex flex-wrap gap-3 items-end"><label>Count notices by<select :value="choice.key" class="block" @change="selectPattern(($event.target as HTMLSelectElement).value)"><option v-for="item in choices" :key="item.key" :value="item.key">{{ item.label }}</option></select></label><div role="group" aria-label="Pattern view" class="flex gap-2"><button class="atlas-button" type="button" :aria-pressed="!showChart" @click="filters.set('pattern_view', 'data')">Data</button><button class="atlas-button" type="button" :aria-pressed="showChart" @click="filters.set('pattern_view', 'chart')">Chart</button></div><button class="atlas-button" type="button" @click="download">Download aggregate JSON</button></div>
    <p class="atlas-footnote">Publication dates describe when notices were published. Value bands cover notices with a numeric source value. Missing periods are not filled with zero. Procedure and band selection cannot filter the notice list.</p>
    <LazyStCountChart v-if="showChart" :title="`Notices by ${choice.label.toLowerCase()}`" :rows="rows" :horizontal="choice.key === 'procedure' || choice.key === 'band'" :year-brush="choice.key === 'year'" :selected="selectedKey" :annotation="annotation" @select="filters.set('aggregate', $event)" @years="years" />
    <div v-if="selectedKey" class="atlas-panel atlas-panel-body" role="status"><template v-if="selected"><h3>{{ selected.label }}</h3><p>Published notices: {{ selected.value ?? 'Not supplied' }}. This is a matching-source aggregate, independent of the loaded notice page.</p><button v-if="choice.key === 'year' && /^\d{4}$/.test(selected.label)" class="atlas-button" type="button" @click="years(selected.label, selected.label)">Apply this publication year</button><p v-else>The notice list has not been filtered by this selection.</p></template><p v-else>The selected aggregate is not in the returned categories.</p></div>
    <div class="overflow-x-auto" tabindex="0" role="region" aria-label="Notice count data"><table class="w-full text-sm"><caption class="text-left atlas-footnote">Every returned {{ choice.label.toLowerCase() }} category</caption><thead><tr><th scope="col" class="text-left p-2">{{ choice.label }}</th><th scope="col" class="text-right p-2">Notices</th><th scope="col" class="p-2">Inspect</th></tr></thead><tbody><tr v-for="row in rows" :key="row.key"><td class="p-2">{{ row.label }}</td><td class="p-2 text-right">{{ row.value ?? 'Not supplied' }}</td><td class="p-2"><button class="atlas-button" type="button" :aria-label="`Inspect aggregate ${row.label}`" @click="filters.set('aggregate', row.key)">Inspect</button></td></tr></tbody></table></div><p v-if="!rows.length">No count observations were returned for this selection.</p>
    <p class="atlas-footnote">These aggregate rows do not include individual source URLs, retrieval dates or hashes. Inspect notice rows for their own provenance.</p>
  </section>
</template>
<style scoped>
label { font-size: 13px; }
select { min-height: 44px; padding: 8px; border: 1px solid var(--border-control); }
</style>
