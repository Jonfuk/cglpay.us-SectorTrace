<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { CompareResponse, ProviderRow, ProvidersResponse } from '~/types/api'

interface AuthorityOption { ons_code: string; name: string; region: string | null }
interface AuthoritiesResponse { authorities: AuthorityOption[] }
interface ProviderOption { provider_key: string; canonical_name: string }
interface CompareSeries { rows?: Array<Record<string, unknown>>; england?: Array<Record<string, unknown>>; indicators?: Array<Record<string, unknown>>; caveat?: string | null; caveats?: Record<string, string | null>; provenance?: Record<string, unknown>; [key: string]: unknown }
interface CompareEnvelope { authorities: AuthorityOption[]; providers: ProviderRow[]; series: Record<string, CompareSeries>; caveats?: { cross_layer?: string | null } }
interface ProviderLayer { caveat?: string | null; unit?: string | null; by_provider?: Record<string, Array<Record<string, unknown>>>; [key: string]: unknown }
interface ProviderCompare { providers: ProviderRow[]; layers: Record<string, ProviderLayer>; caveat?: string | null }
interface CompareWorkspace { authorities: AuthoritiesResponse; providers: ProvidersResponse; compare: CompareEnvelope | null; providerPay: ProviderCompare | null }
interface CompareRow extends Record<string, unknown> { row_key: string; entity_label: string; period: string | null; value: number | null; lower_ci_95: number | null; upper_ci_95: number | null; notices: number | null; status: string | null }

const api = usePublicApi()
const filters = useFilterState()
function list(value: string | string[] | undefined): string[] { return !value ? [] : Array.isArray(value) ? value : [value] }
const onsCodes = computed(() => list(filters.get('ons_code')))
const providerKeys = computed(() => list(filters.get('provider_key')))
const selectedCount = computed(() => onsCodes.value.length + providerKeys.value.length)

const { data, pending, error } = await useDataRoute<CompareWorkspace>('public-compare-workspace', async (f) => {
  const ons = list(f.ons_code)
  const providers = list(f.provider_key)
  const selected = ons.length + providers.length
  const [authorities, providerList] = await Promise.all([
    api.get<AuthoritiesResponse>('/authorities'),
    api.providers(),
  ])
  if (selected < 2) return { authorities, providers: providerList, compare: null, providerPay: null }
  const compare = await api.get<CompareEnvelope>('/compare', { query: f })
  let providerPay: ProviderCompare | null = null
  if (providers.length >= 2 && !ons.length) providerPay = await api.get<ProviderCompare>('/provider_compare', { query: { provider_key: providers.slice(0, 4) } })
  return { authorities, providers: providerList, compare, providerPay }
})

const authorityOptions = computed(() => data.value?.authorities.authorities ?? [])
const providerOptions = computed<ProviderOption[]>(() => (data.value?.providers.providers ?? []).flatMap((item) => item.provider_key ? [{ provider_key: item.provider_key, canonical_name: item.canonical_name ?? item.provider_key }] : []))
const selectedAuthorities = computed(() => onsCodes.value.map((code) => authorityOptions.value.find((item) => item.ons_code === code) ?? { ons_code: code, name: code, region: null }))
const selectedProviders = computed(() => providerKeys.value.map((key) => {
  const item = providerOptions.value.find((candidate) => candidate.provider_key === key)
  return { provider_key: key, canonical_name: item?.canonical_name ?? key }
}))
const series = computed(() => data.value?.compare?.series ?? {})
const seriesNames: Record<string, string> = { grant: 'Grant allocation', budget: 'Budgeted public health spend', treatment: 'Numbers in treatment', contracts: 'Contract value published' }

const commonColumns: Column<CompareRow>[] = [
  { key: 'entity_label', label: 'Authority / provider' }, { key: 'period', label: 'Year or period', mono: true },
  { key: 'value', label: 'Published value', numeric: true }, { key: 'notices', label: 'Notices', numeric: true },
  { key: 'status', label: 'Status' }, { key: 'lower_ci_95', label: 'Lower 95% CI', numeric: true }, { key: 'upper_ci_95', label: 'Upper 95% CI', numeric: true },
]

function add(key: 'ons_code' | 'provider_key', value: string): void {
  const current = list(filters.get(key))
  if (!current.includes(value)) void filters.set(key, [...current, value])
}
function remove(key: 'ons_code' | 'provider_key', value: string): void { void filters.set(key, list(filters.get(key)).filter((item) => item !== value)) }
function clear(): void { void filters.setAll({}) }
function entityLabel(row: Record<string, unknown>): string { return String(row.authority_name ?? row.provider_name ?? row.ons_code ?? row.provider_key ?? '—') }
function periodFor(kind: string, row: Record<string, unknown>): string | null { return String(row.financial_year ?? row.year ?? row.time_period ?? '') || null }
function valueFor(kind: string, row: Record<string, unknown>): number | null {
  const value = kind === 'contracts' ? row.value_gbp : kind === 'treatment' ? row.value : row.amount
  return typeof value === 'number' ? value : null
}
function compareRows(kind: string, source: CompareSeries): CompareRow[] {
  return (source.rows ?? []).map((row, index) => ({
    row_key: `${kind}-${row.ons_code ?? row.provider_key ?? index}-${periodFor(kind, row) ?? index}`,
    entity_label: entityLabel(row), period: periodFor(kind, row), value: valueFor(kind, row),
    notices: typeof row.count === 'number' ? row.count : null,
    status: typeof row.allocation_status === 'string' ? row.allocation_status : null,
    lower_ci_95: typeof row.lower_ci_95 === 'number' ? row.lower_ci_95 : null,
    upper_ci_95: typeof row.upper_ci_95 === 'number' ? row.upper_ci_95 : null,
  }))
}
function providerRows(layer: ProviderLayer, key: string): Array<Record<string, unknown>> { return (layer.by_provider?.[key] ?? []).slice(0, 8) }
function providerName(key: string): string { return providerOptions.value.find((item) => item.provider_key === key)?.canonical_name ?? key }
function providerLine(layer: string, row: Record<string, unknown>): string {
  if (layer === 'living_wage') return `${row.accredited ? 'Accredited' : 'Not accredited'}${row.employer_name ? ` — ${row.employer_name}` : ''}`
  if (layer === 'gender_pay_gap') return `${row.reporting_year_label ?? row.reporting_year ?? 'Year'}: mean ${row.diff_mean_hourly_percent ?? '—'}%, median ${row.diff_median_hourly_percent ?? '—'}%`
  if (layer === 'nhs_jobs') return `${row.job_title ?? 'Role'}: ${row.salary_raw ?? '—'}`
  return String(row.mention_text ?? row.salary_raw ?? 'Published pay row')
}

useHead({ title: 'SectorTrace — Compare evidence safely' })
</script>

<template>
  <section class="space-y-8">
    <div class="atlas-hero"><div><p class="atlas-kicker">Comparison workbench · reader-selected peers</p><h1>Compare evidence safely</h1><p class="atlas-lede">Choose peers, choose a published evidence layer, then read the source-specific series. The portal does not calculate differences or rankings.</p><div class="atlas-actions"><a class="atlas-button primary" href="#compare-picker">Choose peers</a><a class="atlas-button" href="#compare-results">Read the evidence</a></div></div><div class="atlas-hero-aside"><div class="atlas-region"><strong>{{ selectedCount }}</strong><span>selected entities</span></div><div class="atlas-region"><strong>{{ Object.keys(series).length || '—' }}</strong><span>separate evidence layers</span></div></div></div>
    <details class="atlas-read-first" open><summary>How comparisons work</summary><p>Each series uses one source and one kind of measure. Shared axes let you inspect peers; they do not turn unlike measures into one score.</p><p>This page does not calculate differences, rankings, ratios, or cross-layer scores.</p></details>

    <section id="compare-picker" class="atlas-section"><div class="atlas-section-head"><h2>Choose what to compare</h2><p>{{ selectedCount }} selected · choose at least two peers to draw shared axes.</p></div><div class="atlas-panel atlas-panel-body space-y-5"><div class="flex flex-wrap gap-2"><span v-for="item in selectedAuthorities" :key="item.ons_code" class="atlas-button primary">{{ item.name }} <button class="ml-2" type="button" :aria-label="`Remove ${item.name}`" @click="remove('ons_code', item.ons_code)">×</button></span><span v-for="item in selectedProviders" :key="item.provider_key" class="atlas-button primary">{{ item.canonical_name }} <button class="ml-2" type="button" :aria-label="`Remove ${item.canonical_name}`" @click="remove('provider_key', item.provider_key)">×</button></span><span v-if="!selectedCount" class="text-sm opacity-70">Nothing selected yet.</span></div><div class="grid gap-4 md:grid-cols-2"><label class="text-sm"><span class="block mb-1 opacity-70">Add an authority</span><select class="w-full rounded border px-3 py-2" @change="add('ons_code', ($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''"><option value="">Choose an authority…</option><option v-for="item in authorityOptions" :key="item.ons_code" :disabled="onsCodes.includes(item.ons_code)" :value="item.ons_code">{{ item.name }} · {{ item.ons_code }}</option></select></label><label class="text-sm"><span class="block mb-1 opacity-70">Add a provider</span><select class="w-full rounded border px-3 py-2" @change="add('provider_key', ($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''"><option value="">Choose a provider…</option><option v-for="item in providerOptions" :key="item.provider_key" :disabled="providerKeys.includes(item.provider_key)" :value="item.provider_key">{{ item.canonical_name }} · {{ item.provider_key }}</option></select></label></div><button v-if="selectedCount" class="atlas-button" type="button" @click="clear">Clear all selections</button></div></section>

    <StEmptyState v-if="selectedCount < 2" title="Select at least two to compare" message="Add two or more authorities or providers above to draw source-specific evidence series." />
    <div v-else-if="pending" class="text-sm opacity-60">Loading comparison…</div><StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else-if="data?.compare">
      <section id="compare-results" class="atlas-section"><div class="atlas-section-head"><h2>Evidence by layer</h2><p>Each table keeps one measure and its provenance context intact.</p></div><StCaveat v-if="data.compare.caveats?.cross_layer" :text="data.compare.caveats.cross_layer" /><div class="space-y-6 mt-5"><section v-for="(payload, kind) in series" :key="kind" class="atlas-panel atlas-panel-body space-y-4"><div><h3>{{ seriesNames[kind] ?? kind }}</h3><p class="text-sm opacity-70">{{ kind === 'grant' ? 'Public health grant allocation, as published per financial year.' : kind === 'budget' ? 'What each authority planned to spend, as reported.' : kind === 'treatment' ? 'Fingertips figures, with the confidence interval that belongs to each value.' : 'Values of notices published per year, as published in each notice.' }}</p></div><StCaveat v-if="payload.caveat" :text="payload.caveat" /><StEvidenceTable v-if="compareRows(kind, payload).length" :columns="commonColumns" :rows="compareRows(kind, payload)" row-key="row_key" /><StEmptyState v-else /></section></div></section>
      <section v-if="data.providerPay" class="atlas-section"><div class="atlas-section-head"><h2>Provider pay evidence side by side</h2><p>Provider-only comparisons have no common authority axis, so these layers stay as separate lists.</p></div><div class="atlas-panel atlas-panel-body space-y-5"><StCaveat v-if="data.providerPay.caveat" :text="data.providerPay.caveat" /><section v-for="(layer, key) in data.providerPay.layers" :key="key"><h3>{{ key === 'living_wage' ? 'Living Wage accreditation' : key === 'gender_pay_gap' ? 'Latest gender pay gap filing' : key === 'provider_pay' ? 'Pay published on provider sites' : 'Recent NHS Jobs adverts' }}</h3><div class="grid gap-3 md:grid-cols-2"><div v-for="providerKey in providerKeys.slice(0, 4)" :key="`${key}-${providerKey}`" class="border rounded p-3"><strong>{{ providerName(providerKey) }}</strong><ul class="mt-2 text-sm"><li v-for="(row, i) in providerRows(layer, providerKey)" :key="i">{{ providerLine(String(key), row) }}</li><li v-if="!providerRows(layer, providerKey).length" class="opacity-60">No rows in this layer — not evidence of a better or worse position.</li></ul></div></div></section></div></section>
    </template>
  </section>
</template>
