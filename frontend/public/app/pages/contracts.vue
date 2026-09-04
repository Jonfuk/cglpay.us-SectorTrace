<script setup lang="ts">
import type { Column } from '~/components/StEvidenceTable.vue'
import type { ContractNotice, ContractsResponse } from '~/types/api'

type RollupRow = Record<string, unknown>
type ContractPayload = ContractsResponse & {
  total?: number
  total_value_gbp?: number
  direct_award_count?: number
  matched_to_provider?: number
  value_concentration?: Record<string, unknown>
  date_range?: { earliest?: string; latest?: string }
  ending_soon?: { rows?: RollupRow[]; caveat?: string }
  by_year?: RollupRow[]
  by_provider?: RollupRow[]
  by_procedure_type?: RollupRow[]
  value_bands?: RollupRow[]
  top_buyers?: RollupRow[]
}
type CouncilSpendPayload = {
  total?: number
  payments?: RollupRow[]
  files?: RollupRow[]
  caveats?: Record<string, string | null>
}

const api = usePublicApi()
const filters = useFilterState()
const query = computed({
  get: () => String(filters.get('q') ?? ''),
  set: (v: string) => { void filters.set('q', v || undefined) },
})
const psrOnly = computed({
  get: () => filters.get('psr_only') === 'true',
  set: (v: boolean) => { void filters.set('psr_only', v ? 'true' : undefined) },
})

const { data, pending, error } = await useDataRoute<ContractPayload>(
  'public-contracts',
  (f) => api.contracts({ query: f }),
)
const { data: spending } = await useAsyncData<CouncilSpendPayload>(
  'public-council-spend',
  () => api.get<CouncilSpendPayload>('/council_spend', { query: { limit: 500 } }),
  { default: () => ({}) },
)

const payload = computed(() => data.value)
const notices = computed<ContractNotice[]>(() => payload.value?.notices ?? [])
const concentration = computed(() => payload.value?.value_concentration ?? {})
const rows = (key: keyof ContractPayload): RollupRow[] => (payload.value?.[key] as RollupRow[] | undefined) ?? []
const number = (key: string): string => {
  const value = concentration.value[key]
  return typeof value === 'number' ? value.toLocaleString('en-GB', { maximumFractionDigits: 1 }) : '—'
}
const money = (value: unknown): string => typeof value === 'number'
  ? value.toLocaleString('en-GB', { style: 'currency', currency: 'GBP', maximumFractionDigits: 0 })
  : value === null || value === undefined ? '—' : String(value)
const rollupColumns = (keys: Array<[string, string, boolean?]>): Column<RollupRow>[] =>
  keys.map(([key, label, numeric]) => ({ key, label, numeric }))

const noticeColumns: Column<ContractNotice>[] = [
  { key: 'date_published', label: 'Published', mono: true },
  { key: 'buyer_name', label: 'Buyer' },
  { key: 'supplier_name_raw', label: 'Supplier' },
  { key: 'title', label: 'Title' },
  { key: 'ocid', label: 'Lifecycle', mono: true, to: (row) => row.ocid ? `/contracts/process/${encodeURIComponent(String(row.ocid))}` : null },
  { key: 'value_core', label: 'Published value', numeric: true },
  { key: 'procedure_type', label: 'Procedure' },
  { key: 'notice_link', label: 'Notice', link: true },
  { key: 'source_url', label: 'Data source', link: true },
]

useHead({ title: 'SectorTrace — Contracts' })
</script>

<template>
  <section class="atlas-hero"><div><div class="atlas-kicker">Funding · procurement notices and payments</div><h1>Where public money is going</h1><p class="atlas-lede">Published notices are not payments or a clean sector-spend total. Values can be ceilings, framework values, or missing; buyer, provider, and date context matters.</p><details class="atlas-read-first"><summary>How to read a notice</summary><p>A notice records what was published at procurement stage. It may cover several years or lots, and a framework may never be called off.</p><p>Council payment files are shown separately because they record a different kind of published evidence.</p></details></div></section>

  <section v-if="pending" class="atlas-panel p-6">Loading contract evidence…</section>
  <section v-else-if="error || !payload" class="atlas-panel p-6">Contract evidence is unavailable.</section>
  <template v-else>
    <section class="atlas-section atlas-panel atlas-panel-body"><div class="atlas-eyebrow">Contracts workbench</div><p class="atlas-footnote">{{ payload.total?.toLocaleString('en-GB') ?? '0' }} published notices matched by the current filters. The middle notice is {{ money(concentration.median_value_gbp) }}; the mean is {{ money(concentration.mean_value_gbp) }}.</p><div class="flex flex-wrap items-end gap-3 mt-3"><label class="text-sm">Search buyer or supplier<input v-model.lazy="query" type="search" class="block mt-1 px-2 py-1 min-w-64" placeholder="Search notices…"></label><label class="text-sm flex items-center gap-2 pb-1"><input v-model="psrOnly" type="checkbox"> PSR notices only</label></div><p v-if="query" class="atlas-footnote mt-3">Search is applied server-side and remains in the shareable URL.</p></section>

    <section class="atlas-section"><div class="atlas-eyebrow">Money-flow snapshot</div><div class="atlas-grid atlas-grid-4 mt-3"><div class="atlas-stat"><strong>{{ payload.total?.toLocaleString('en-GB') ?? '—' }}</strong><span>published notices</span></div><div class="atlas-stat"><strong>{{ number('priced_notices') }}</strong><span>with a published value</span></div><div class="atlas-stat"><strong>{{ number('matched_to_provider') }}</strong><span>matched to a tracked provider</span></div><div class="atlas-stat"><strong>{{ money(payload.total_value_gbp) }}</strong><span>published values, not spend</span></div></div><p class="atlas-caveat mt-4"><span aria-hidden="true">⚠</span> {{ payload.caveats?.value_sum }}</p></section>

    <section class="atlas-section atlas-panel atlas-panel-body"><h2>Concentration and coverage</h2><div class="atlas-grid atlas-grid-4"><div><strong>{{ money(concentration.median_value_gbp) }}</strong><p class="atlas-footnote">median published value</p></div><div><strong>{{ money(concentration.mean_value_gbp) }}</strong><p class="atlas-footnote">mean published value</p></div><div><strong>{{ number('top_10_share') }}%</strong><p class="atlas-footnote">share held by top 10</p></div><div><strong>{{ number('share_over_1bn') }}%</strong><p class="atlas-footnote">share in notices over £1bn</p></div></div><p class="atlas-footnote mt-4">Dates span {{ payload.date_range?.earliest?.slice(0, 10) ?? '—' }} to {{ payload.date_range?.latest?.slice(0, 10) ?? '—' }}. This is the collection window, not the period contracts were awarded over.</p></section>

    <section class="atlas-section atlas-panel atlas-panel-body"><h2>Published patterns</h2><div class="atlas-band"><h3>By year</h3><StEvidenceTable :columns="rollupColumns([['year', 'Year'], ['count', 'Notices', true], ['value_gbp', 'Published value', true]])" :rows="rows('by_year')" row-key="year" /></div><div class="atlas-band"><h3>Value bands</h3><StEvidenceTable :columns="rollupColumns([['band_label', 'Band'], ['count', 'Notices', true]])" :rows="rows('value_bands')" row-key="band_label" /></div><div class="atlas-band"><h3>Procedure types</h3><StEvidenceTable :columns="rollupColumns([['procedure_type', 'Procedure'], ['count', 'Notices', true]])" :rows="rows('by_procedure_type').slice(0, 12)" row-key="procedure_type" /></div></section>

    <section class="atlas-section atlas-panel atlas-panel-body"><h2>Providers and buyers</h2><div class="atlas-band"><h3>Matched providers</h3><p class="atlas-footnote">Exact-name matching only. These totals are a floor; an unmatched notice is not evidence that no known provider was involved.</p><StEvidenceTable :columns="rollupColumns([['canonical_name', 'Provider'], ['count', 'Notices', true], ['value_gbp', 'Published value', true]])" :rows="rows('by_provider')" row-key="provider_key" /></div><div class="atlas-band"><h3>Largest buyers</h3><StEvidenceTable :columns="rollupColumns([['buyer_name', 'Buyer'], ['count', 'Notices', true], ['value_gbp', 'Published value', true]])" :rows="rows('top_buyers').slice(0, 15)" row-key="buyer_name" /></div></section>

    <section v-if="payload.ending_soon?.rows?.length" class="atlas-section atlas-panel atlas-panel-body"><h2>Published end dates ahead</h2><p class="atlas-footnote">{{ payload.ending_soon.caveat }}</p><StEvidenceTable :columns="rollupColumns([['quarter', 'Quarter'], ['count', 'Notices', true], ['matched', 'Matched providers', true]])" :rows="payload.ending_soon.rows" row-key="quarter" /></section>

    <section class="atlas-section atlas-panel atlas-panel-body"><div class="flex flex-wrap items-baseline justify-between gap-3"><div><h2>Notices</h2><p class="atlas-footnote">The current page behind the rollups, newest first. The full filtered set remains available through the public API.</p></div><span class="atlas-footnote">Showing {{ notices.length }} (offset {{ data?.page?.offset ?? 0 }})</span></div><StEvidenceTable v-if="notices.length" :columns="noticeColumns" :rows="notices" row-key="notice_id" /><StEmptyState v-else /></section>

    <section v-if="spending?.payments?.length" class="atlas-section atlas-panel atlas-panel-body"><h2>Published council payments</h2><p class="atlas-footnote">{{ spending.total?.toLocaleString('en-GB') }} payment lines in council spend-transparency files. These are actual published payments, separate from notice-stage contract values and authority budgets.</p><p class="atlas-caveat"><span aria-hidden="true">⚠</span> {{ spending.caveats?.payments }}</p><StEvidenceTable :columns="rollupColumns([['authority_name', 'Authority'], ['period', 'Period'], ['payee', 'Payee'], ['amount_text', 'Published amount', true], ['description', 'Description'], ['canonical_name', 'Matched provider'], ['source_url', 'Source']])" :rows="spending.payments.slice(0, 100)" row-key="row_index" /></section>
    <section v-if="spending?.files?.length" class="atlas-section atlas-panel atlas-panel-body"><h2>Transparency files</h2><p class="atlas-footnote">Unreadable files remain visible as gaps; they are never treated as zero.</p><StEvidenceTable :columns="rollupColumns([['authority_name', 'Authority'], ['file_format', 'Format'], ['parse_status', 'Status'], ['row_count', 'Rows', true], ['retrieved_at', 'Retrieved'], ['source_url', 'Source']])" :rows="spending.files.slice(0, 100)" row-key="source_url" /></section>

    <section class="atlas-section atlas-panel atlas-panel-body"><h2>How to read these figures</h2><div class="space-y-2"><p v-for="(text, key) in payload.caveats" :key="key" class="atlas-caveat"><span aria-hidden="true">⚠</span> {{ text }}</p></div></section>
  </template>
</template>
