<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { ProviderRow, ProvidersResponse } from '~/types/api'

interface AuthorityOption { ons_code: string; name: string; region: string | null }
interface AuthoritiesResponse { authorities: AuthorityOption[] }
interface ProviderOption { provider_key: string; canonical_name: string }
interface CompareSeries { rows?: Array<Record<string, unknown>>; england?: Array<Record<string, unknown>>; indicators?: Array<Record<string, unknown>>; caveat?: string | null; caveats?: Record<string, string | null>; provenance?: Record<string, unknown>; [key: string]: unknown }
interface CompareEnvelope { authorities: AuthorityOption[]; providers: ProviderRow[]; series: Record<string, CompareSeries>; caveats?: { cross_layer?: string | null } }
interface ProviderLayer { caveat?: string | null; unit?: string | null; by_provider?: Record<string, Array<Record<string, unknown>>>; [key: string]: unknown }
interface ProviderCompare { providers: ProviderRow[]; layers: Record<string, ProviderLayer>; caveat?: string | null }
interface CompareWorkspace { authorities: AuthoritiesResponse; providers: ProvidersResponse; compare: CompareEnvelope | null; providerPay: ProviderCompare | null }
interface CompareRow extends Record<string, unknown> { row_key: string; entity_label: string }

const api = usePublicApi()
const filters = useFilterState()
function list(value: string | string[] | undefined): string[] { return !value ? [] : Array.isArray(value) ? value : [value] }
const onsCodes = computed(() => list(filters.get('ons_code')))
const providerKeys = computed(() => list(filters.get('provider_key')))
const selectedCount = computed(() => onsCodes.value.length + providerKeys.value.length)
const kind = computed(() => { const raw = filters.get('kind'); return raw === 'authority' || raw === 'provider' ? raw : onsCodes.value.length && !providerKeys.value.length ? 'authority' : providerKeys.value.length && !onsCodes.value.length ? 'provider' : '' })
const activeKeys = computed(() => kind.value === 'authority' ? onsCodes.value : kind.value === 'provider' ? providerKeys.value : [])
const selectionError = computed(() => !kind.value ? 'Choose authorities or providers for this comparison. Both saved groups remain available.' : activeKeys.value.length > 4 ? 'Choose no more than four peers. The saved selection has not been shortened.' : new Set(activeKeys.value).size !== activeKeys.value.length ? 'Remove repeated identifiers before comparing peers.' : '')
const lenses = computed(() => kind.value === 'authority' ? ['grant', 'budget', 'treatment', 'contracts'] : kind.value === 'provider' ? ['charity', 'provider_contracts', 'living_wage', 'gender_pay_gap', 'provider_pay', 'nhs_jobs'] : [])
const lens = computed(() => { const value = filters.get('lens'); return typeof value === 'string' && value ? value : lenses.value[0] ?? '' })
const payLens = computed(() => ['living_wage', 'gender_pay_gap', 'provider_pay', 'nhs_jobs'].includes(lens.value))
const { data: directories, error: directoryError, refresh: refreshDirectories } = await useAsyncData('compare-directories', async () => { const [authorities, providers] = await Promise.all([api.get<AuthoritiesResponse>('/authorities'), api.providers()]); return { authorities, providers } })

const { data, pending, error, refresh } = await useDataRoute<CompareWorkspace>('public-compare-workspace', async (f, signal) => {
  const ons = kind.value === 'authority' ? list(f.ons_code) : []
  const providers = kind.value === 'provider' ? list(f.provider_key) : []
  const selected = ons.length + providers.length
  const authorities = directories.value?.authorities ?? { authorities: [] }
  const providerList = directories.value?.providers ?? { providers: [] }
  if (selectionError.value || !lenses.value.includes(lens.value) || !selected || (payLens.value && selected < 2)) return { authorities, providers: providerList, compare: null, providerPay: null }
  const compare = payLens.value ? null : await api.get<CompareEnvelope>('/compare', { query: ons.length ? { ons_code: ons } : { provider_key: providers }, signal })
  let providerPay: ProviderCompare | null = null
  if (payLens.value) providerPay = await api.get<ProviderCompare>('/provider_compare', { query: { provider_key: providers }, signal })
  return { authorities, providers: providerList, compare, providerPay }
})

const authorityOptions = computed(() => directories.value?.authorities.authorities ?? [])
const providerOptions = computed<ProviderOption[]>(() => (directories.value?.providers.providers ?? []).flatMap((item) => item.provider_key ? [{ provider_key: item.provider_key, canonical_name: item.canonical_name ?? item.provider_key }] : []))
const selectedAuthorities = computed(() => onsCodes.value.map((code) => authorityOptions.value.find((item) => item.ons_code === code) ?? { ons_code: code, name: code, region: null }))
const selectedProviders = computed(() => providerKeys.value.map((key) => {
  const item = providerOptions.value.find((candidate) => candidate.provider_key === key)
  return { provider_key: key, canonical_name: item?.canonical_name ?? key }
}))
const series = computed(() => { const source = data.value?.compare?.series?.[lens.value]; return source ? { [lens.value]: source } : {} })
const providerLayers = computed(() => { const source = data.value?.providerPay?.layers?.[lens.value]; return source ? { [lens.value]: source } : {} })
const seriesNames: Record<string, string> = { grant: 'Grant allocation', budget: 'Budgeted public health spend', treatment: 'Numbers in treatment', contracts: 'Contract notice counts', provider_contracts: 'Contract notice counts', charity: 'Charity income and expenditure', living_wage: 'Living Wage name checks', gender_pay_gap: 'Latest gender pay gap filings', provider_pay: 'Provider-published pay', nhs_jobs: 'Recent job adverts' }

function sourceColumns(source: CompareSeries): Column<CompareRow>[] {
  const fields = [...new Set((source.rows ?? []).flatMap(row => Object.keys(row)))]
  return fields.map(key => ({ key, label: key.replaceAll('_', ' '), link: key === 'source_url', numeric: ['amount', 'value', 'count', 'total_income', 'total_expenditure', 'lower_ci_95', 'upper_ci_95'].includes(key) }))
}

function add(key: 'ons_code' | 'provider_key', value: string): void {
  const current = list(filters.get(key))
  if (!current.includes(value)) void filters.set(key, [...current, value])
}
function remove(key: 'ons_code' | 'provider_key', value: string): void { void filters.set(key, list(filters.get(key)).filter((item) => item !== value)) }
function clear(): void { void filters.setAll({ ...filters.all(), ons_code: undefined, provider_key: undefined }) }
function entityLabel(row: Record<string, unknown>): string { return String(row.authority_name ?? row.provider_name ?? row.canonical_name ?? row.ons_code ?? row.provider_key ?? 'Not supplied') }
function compareRows(kind: string, source: CompareSeries): CompareRow[] {
  return (source.rows ?? []).map((row, index) => ({ ...row, row_key: `${kind}-${index}`, entity_label: entityLabel(row) }))
}
function providerRows(layer: ProviderLayer, key: string): Array<Record<string, unknown>> { return layer.by_provider?.[key] ?? [] }
function providerName(key: string): string { return providerOptions.value.find((item) => item.provider_key === key)?.canonical_name ?? key }
function providerLine(layer: string, row: Record<string, unknown>): string {
  if (layer === 'living_wage') return `${row.accredited === true || row.accredited === 1 ? 'A matching accreditation entry was recorded' : row.accredited === false || row.accredited === 0 ? 'No matching entry was recorded in this check' : 'Check result not supplied'}${row.employer_name ? ` (${row.employer_name})` : ''}`
  if (layer === 'gender_pay_gap') return `${row.reporting_year_label ?? row.reporting_year ?? 'Year'}: mean ${row.diff_mean_hourly_percent ?? '—'}%, median ${row.diff_median_hourly_percent ?? '—'}%`
  if (layer === 'nhs_jobs') return `${row.job_title ?? 'Role'}: ${row.salary_raw ?? '—'}`
  return String(row.mention_text ?? row.salary_raw ?? 'Published pay row')
}

useHead({ title: 'Compare evidence · SectorTrace' })
</script>

<template>
  <section class="space-y-8">
    <div class="atlas-hero"><div><p class="atlas-kicker">Comparison workbench · reader-selected peers</p><h1>Compare evidence safely</h1><p class="atlas-lede">Choose peers, choose a published evidence layer, then read the source-specific series. The portal does not calculate differences or rankings.</p><div class="atlas-actions"><a class="atlas-button primary" href="#compare-picker">Choose peers</a><a class="atlas-button" href="#compare-results">Read the evidence</a></div></div><div class="atlas-hero-aside"><div class="atlas-region"><strong>{{ selectedCount }}</strong><span>selected entities</span></div><div class="atlas-region"><strong>{{ Object.keys(series).length || '—' }}</strong><span>separate evidence layers</span></div></div></div>
    <details class="atlas-read-first" open><summary>How comparisons work</summary><p>Each series uses one source and one kind of measure. Periods, units and source limitations stay attached to each observation.</p><p>This page does not calculate differences, rankings, ratios, or cross-layer scores.</p></details>

    <StEvidenceState v-if="directoryError" :error="directoryError" @retry="refreshDirectories" /><section id="compare-picker" class="atlas-section"><div class="atlas-section-head"><h2>Choose what to compare</h2><p>{{ selectedCount }} saved selections. Compare 2–4 peers of one type, or start with one peer.</p></div><div class="atlas-panel atlas-panel-body space-y-5"><div class="flex flex-wrap gap-2"><span v-for="item in selectedAuthorities" :key="item.ons_code" class="atlas-button primary">{{ item.name }} <button class="ml-2" type="button" :aria-label="`Remove ${item.name}`" @click="remove('ons_code', item.ons_code)">×</button></span><span v-for="item in selectedProviders" :key="item.provider_key" class="atlas-button primary">{{ item.canonical_name }} <button class="ml-2" type="button" :aria-label="`Remove ${item.canonical_name}`" @click="remove('provider_key', item.provider_key)">×</button></span><span v-if="!selectedCount" class="text-sm opacity-70">Nothing selected yet.</span></div><div class="grid gap-4 md:grid-cols-2"><label class="text-sm"><span class="block mb-1 opacity-70">Add an authority</span><select class="w-full rounded border px-3 py-2" @change="add('ons_code', ($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''"><option value="">Choose an authority…</option><option v-for="item in authorityOptions" :key="item.ons_code" :disabled="onsCodes.includes(item.ons_code)" :value="item.ons_code">{{ item.name }} · {{ item.ons_code }}</option></select></label><label class="text-sm"><span class="block mb-1 opacity-70">Add a provider</span><select class="w-full rounded border px-3 py-2" @change="add('provider_key', ($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''"><option value="">Choose a provider…</option><option v-for="item in providerOptions" :key="item.provider_key" :disabled="providerKeys.includes(item.provider_key)" :value="item.provider_key">{{ item.canonical_name }} · {{ item.provider_key }}</option></select></label></div><button v-if="selectedCount" class="atlas-button" type="button" @click="clear">Clear all selections</button></div></section>

    <div class="flex flex-wrap gap-3" role="group" aria-label="Comparison entity type"><button type="button" class="atlas-button" :aria-pressed="kind === 'authority'" @click="filters.setAll({ ...filters.all(), kind: 'authority', lens: undefined })">Compare authorities</button><button type="button" class="atlas-button" :aria-pressed="kind === 'provider'" @click="filters.setAll({ ...filters.all(), kind: 'provider', lens: undefined })">Compare providers</button></div><p v-if="filters.get('year_from') || filters.get('year_to')" class="atlas-footnote">Retained year bounds do not filter these comparison endpoints. Each row keeps its supplied reporting period.</p><label v-if="kind" class="grid gap-2">Evidence source<select class="atlas-button" :value="lens" @change="filters.set('lens', ($event.target as HTMLSelectElement).value)"><option v-if="!lenses.includes(lens)" :value="lens">Unsupported saved source: {{ lens }}</option><option v-for="source in lenses" :key="source" :value="source">{{ seriesNames[source] }}</option></select></label><p v-if="selectionError" role="status">{{ selectionError }}</p><p v-else-if="!lenses.includes(lens)" role="status">Choose a supported evidence source.</p><p v-else-if="!activeKeys.length" role="status">Add an authority or provider to start a comparison.</p><p v-else-if="activeKeys.length === 1" role="status">One peer is selected. Add another to compare. Provider pay sources require at least two peers before they can be requested.</p>
    <div v-if="pending" class="text-sm opacity-60">Loading comparison…</div><StEvidenceState v-else-if="error" :error="error" @retry="refresh" />
    <template v-else-if="!selectionError && (data?.compare || data?.providerPay)">
      <section v-if="data.compare" id="compare-results" class="atlas-section"><div class="atlas-section-head"><h2>Evidence by layer</h2><p>Each table keeps one measure and its provenance context intact.</p></div><StCaveat v-if="data.compare?.caveats?.cross_layer" :text="data.compare?.caveats.cross_layer" /><div class="space-y-6 mt-5"><section v-for="(payload, kind) in series" :key="kind" class="atlas-panel atlas-panel-body space-y-4"><div><h3>{{ seriesNames[kind] ?? kind }}</h3><p class="text-sm opacity-70">{{ kind === 'grant' ? 'Public health grant allocation, as published per financial year.' : kind === 'budget' ? 'What each authority planned to spend, as reported.' : kind === 'treatment' ? 'Fingertips figures, with the confidence interval that belongs to each value.' : kind === 'charity' ? 'Income and expenditure as filed, retaining the supplied financial year end.' : 'Returned notice counts and source aggregates by publication year. Values are not payments or a headline contract total.' }}</p></div><StCaveat v-if="payload.caveat" :text="payload.caveat" /><StEvidenceTable v-if="compareRows(String(kind), payload).length" :caption="`${seriesNames[kind] ?? kind} returned observations`" :columns="sourceColumns(payload)" :rows="compareRows(String(kind), payload)" row-key="row_key" /><p v-else-if="!Array.isArray(payload.rows)" role="status">The selected source did not supply a row array.</p><StEmptyState v-else /><p v-for="peer in activeKeys.filter(id => !(payload.rows ?? []).some(row => row[kind === 'charity' || kind === 'provider_contracts' ? 'provider_key' : 'ons_code'] === id))" :key="peer" role="status">{{ peer }}: no observations were returned in this source.</p><details><summary>Source context and caveats</summary><pre>{{ JSON.stringify({ ...payload, rows: undefined }, null, 2) }}</pre><p>Aggregate provenance can contain up to six source URLs and the latest retrieval across the selection. It is not per-row provenance.</p></details></section></div></section>
      <section v-if="data.providerPay" class="atlas-section"><div class="atlas-section-head"><h2>Provider pay evidence side by side</h2><p>Provider-only comparisons have no common authority axis, so these layers stay as separate lists.</p></div><div class="atlas-panel atlas-panel-body space-y-5"><StCaveat v-if="data.providerPay.caveat" :text="data.providerPay.caveat" /><section v-for="(layer, key) in providerLayers" :key="key"><StCaveat v-if="layer.caveat" :text="layer.caveat" /><p>{{ layer.unit ?? 'Unit not supplied' }}</p><h3>{{ key === 'living_wage' ? 'Living Wage accreditation' : key === 'gender_pay_gap' ? 'Latest gender pay gap filing' : key === 'provider_pay' ? 'Pay published on provider sites' : 'Recent NHS Jobs adverts' }}</h3><div class="grid gap-3 md:grid-cols-2"><div v-for="providerKey in providerKeys" :key="`${key}-${providerKey}`" class="border rounded p-3"><strong>{{ providerName(providerKey) }}</strong><ul class="mt-2 text-sm"><li v-for="(row, i) in providerRows(layer, providerKey)" :key="i" class="space-y-2"><p>{{ providerLine(String(key), row) }}</p><details><summary>Original record and source</summary><dl><template v-for="(value, field) in row" :key="field"><dt>{{ String(field).replaceAll('_', ' ') }}</dt><dd>{{ value == null ? 'Not supplied' : value }}</dd></template></dl><StProvenance :provenance="row" /></details></li><li v-if="!Array.isArray(layer.by_provider?.[providerKey])" role="status">The source did not supply a row array for this peer.</li><li v-else-if="!providerRows(layer, providerKey).length" class="opacity-60">No rows were returned for this peer in this source. This does not establish a better or worse position.</li></ul></div></div></section></div></section>
    </template>
  </section>
</template>
