<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { AuthorityResponse } from '~/types/api'

type Row = Record<string, unknown>

interface AuthorityWorkspace extends AuthorityResponse {
  coverage?: { labels?: string[]; cells?: Record<string, number>; caveat?: string | null }
  budget_detail?: { rows?: Row[]; caveat?: string | null }
  treatment?: {
    fingertips?: { indicators?: Row[]; series?: Row[]; england_series?: Row[]; caveat?: string | null }
    ndtms?: { estimates?: Row[]; other_rows?: Row[]; caveats?: Record<string, string | null>; [key: string]: unknown }
  }
  contracts?: { notices?: Row[]; total?: number; caveats?: Record<string, string | null>; [key: string]: unknown }
  comparators?: {
    rough_sleeping?: { rows?: Row[]; caveat?: string | null }
    statutory_homelessness?: { rows?: Row[]; caveat?: string | null }
    temporary_accommodation?: { rows?: Row[]; breakdown?: Row[]; caveat?: string | null; breakdown_caveat?: string | null }
  }
}

const route = useRoute()
const api = usePublicApi()
const code = computed(() => String(route.params.code ?? ''))
const filters = useFilterState()
const selectedBudgetYear = computed({ get: () => String(filters.get('budget_year') ?? ''), set: value => { void filters.set('budget_year', value || undefined) } })
const lenses = [
  { key: 'overview', label: 'Overview' }, { key: 'commissioning', label: 'Commissioning' },
  { key: 'funding', label: 'Funding' }, { key: 'treatment', label: 'Treatment' },
  { key: 'contracts', label: 'Contracts' }, { key: 'context', label: 'Context' }, { key: 'history', label: 'History' },
]
const lens = computed(() => String(filters.get('lens') ?? 'overview'))
const validLens = computed(() => lenses.some(item => item.key === lens.value))
const selectedIndicator = computed({ get: () => String(filters.get('indicator_id') ?? ''), set: value => { void filters.set('indicator_id', value || undefined) } })


const { data, pending, error, refresh } = await useAsyncData<AuthorityWorkspace | null>(
  () => `authority-${code.value}`,
  (_app, { signal }) => api.authority(code.value, { signal }) as Promise<AuthorityWorkspace>,
  { default: () => null, watch: [code] },
)

const authority = computed(() => data.value?.authority)
const name = computed(() => authority.value?.name ?? code.value)
const coverageCells = computed(() => data.value?.coverage?.cells ?? {})
const grantRows = computed(() => data.value?.grant?.rows ?? [])
const budgetRows = computed(() => data.value?.budget?.rows ?? [])
const budgetDetailRows = computed(() => data.value?.budget_detail?.rows ?? [])
const budgetYears = computed(() => [...new Set(budgetDetailRows.value.map((row) => String(row.financial_year ?? '')).filter(Boolean))])
const activeBudgetYear = computed(() => selectedBudgetYear.value || budgetYears.value[budgetYears.value.length - 1] || '')
const activeBudgetDetail = computed(() => budgetDetailRows.value.filter((row) => String(row.financial_year ?? '') === activeBudgetYear.value))
const fingertips = computed(() => data.value?.treatment?.fingertips)
const ndtms = computed(() => data.value?.treatment?.ndtms)
const contracts = computed(() => data.value?.contracts)

const links = computed(() => [
  { to: '/geography', label: 'Back to places' },
  { to: `/compare?ons_code=${encodeURIComponent(code.value)}`, label: 'Compare this authority' },
  { to: `/relationships?ons_code=${encodeURIComponent(code.value)}`, label: 'Explore relationships' },
  { to: `/coverage?ons_code=${encodeURIComponent(code.value)}`, label: 'View coverage history' },
])

const grantColumns: Column<Row>[] = [
  { key: 'financial_year', label: 'Financial year', mono: true },
  { key: 'grant_type', label: 'Grant type' },
  { key: 'allocation_status', label: 'Status' },
  { key: 'amount', label: 'Published amount', numeric: true },
  { key: 'unit', label: 'Unit' },
  { key: 'source_url', label: 'Source', link: true },
]
const budgetColumns: Column<Row>[] = [
  { key: 'financial_year', label: 'Financial year', mono: true },
  { key: 'amount', label: 'Budgeted spend (GBP)', numeric: true },
]
const budgetDetailColumns: Column<Row>[] = [
  { key: 'section', label: 'Section' },
  { key: 'line_code', label: 'Line code', mono: true },
  { key: 'line_number', label: 'Line', mono: true },
  { key: 'column_label', label: 'Column' },
  { key: 'amount', label: 'Amount (GBP)', numeric: true },
  { key: 'value_text', label: 'Published text' },
]
const fingertipsColumns: Column<Row>[] = [
  { key: 'authority_name', label: 'Series' },
  { key: 'indicator_name', label: 'Indicator' },
  { key: 'time_period', label: 'Period', mono: true },
  { key: 'unit', label: 'Unit' }, { key: 'value', label: 'Value', numeric: true }, { key: 'value_note', label: 'Source note' },
  { key: 'lower_ci_95', label: 'Lower 95% CI', numeric: true },
  { key: 'upper_ci_95', label: 'Upper 95% CI', numeric: true },
  { key: 'source_url', label: 'Source', link: true },
]
const ndtmsColumns: Column<Row>[] = [
  { key: 'dataset', label: 'Dataset' },
  { key: 'time_period', label: 'Observation period', mono: true }, { key: 'published_in', label: 'Publication', mono: true },
  { key: 'measure', label: 'Measure' },
  { key: 'value_text', label: 'Published value' },
  { key: 'lower', label: 'Lower bound', numeric: true },
  { key: 'upper', label: 'Upper bound', numeric: true },
  { key: 'source_url', label: 'Source', link: true },
]
const ndtmsOtherColumns: Column<Row>[] = [
  { key: 'dataset', label: 'Dataset' },
  { key: 'time_period', label: 'Observation period', mono: true }, { key: 'published_in', label: 'Publication', mono: true },
  { key: 'measure', label: 'Measure' },
  { key: 'value_text', label: 'Published value' },
  { key: 'source_url', label: 'Source', link: true },
]
const contractColumns: Column<Row>[] = [
  { key: 'date_published', label: 'Published', mono: true },
  { key: 'title', label: 'Notice' },
  { key: 'supplier_name_raw', label: 'Supplier' },
  { key: 'value_core', label: 'Published value', numeric: true },
  { key: 'procedure_type', label: 'Procedure' },
  { key: 'currency', label: 'Currency' }, { key: 'ocid', label: 'Procurement process', to: row => row.ocid ? `/contracts/process/${encodeURIComponent(String(row.ocid))}` : null }, { key: 'notice_link', label: 'Notice', link: true }, { key: 'notice_link_basis', label: 'Link basis' },
  { key: 'source_url', label: 'Source', link: true },
]
const roughColumns: Column<Row>[] = [
  { key: 'snapshot_year', label: 'Year', mono: true },
  { key: 'count', label: 'Count', numeric: true },
  { key: 'count_text', label: 'Published text' },
  { key: 'rate_per_100k', label: 'Published rate per 100,000', numeric: true }, { key: 'rate_text', label: 'Published rate text' },
]
const homelessnessColumns: Column<Row>[] = [
  { key: 'quarter_label', label: 'Quarter', mono: true },
  { key: 'total_initial_assessments', label: 'Initial assessments', numeric: true }, { key: 'total_initial_assessments_text', label: 'Published assessment text' },
  { key: 'total_owed_duty', label: 'Owed duty', numeric: true }, { key: 'total_owed_duty_text', label: 'Published duty text' },
  { key: 'prevention_duty_owed', label: 'Prevention duty', numeric: true },
  { key: 'relief_duty_owed', label: 'Relief duty', numeric: true },
]
const temporaryColumns: Column<Row>[] = [
  { key: 'quarter_label', label: 'Quarter', mono: true },
  { key: 'total_households_ta', label: 'Households in temporary accommodation', numeric: true }, { key: 'total_households_ta_text', label: 'Published household text' },
  { key: 'households_ta_with_children', label: 'With children', numeric: true },
  { key: 'children_in_ta', label: 'Children in TA', numeric: true },
]
const temporaryBreakdownColumns: Column<Row>[] = [
  { key: 'quarter_label', label: 'Quarter', mono: true },
  { key: 'measure', label: 'Measure' },
  { key: 'households_text', label: 'Households' }, { key: 'unit', label: 'Unit' },
  { key: 'source_url', label: 'Source', link: true },
]

const coverageRows = computed<Row[]>(() => (data.value?.coverage?.labels ?? Object.keys(coverageCells.value)).map((dataset) => ({ dataset, rows: coverageCells.value[dataset] ?? null })))
const indexed = (rows: Row[], prefix: string): Row[] => rows.map((row, index) => ({ ...row, row_key: `${prefix}-${index}-${String(row.financial_year ?? row.time_period ?? row.notice_id ?? '')}` }))
const grantTableRows = computed(() => indexed(grantRows.value, 'grant'))
const budgetTableRows = computed(() => indexed(budgetRows.value, 'budget'))
const detailTableRows = computed(() => indexed(activeBudgetDetail.value, 'detail'))
const indicatorNames = computed(() => new Map((fingertips.value?.indicators ?? []).map((row) => [String(row.indicator_id), row.indicator_name])))
const fingertipsTableRows = computed(() => indexed((fingertips.value?.series ?? []).filter(row => !selectedIndicator.value || String(row.indicator_id) === selectedIndicator.value).map((row) => ({ ...row, indicator_name: indicatorNames.value.get(String(row.indicator_id)) ?? row.indicator_id })), 'fingertips'))
const fingertipsEnglandRows = computed(() => indexed((fingertips.value?.england_series ?? []).filter(row => !selectedIndicator.value || String(row.indicator_id) === selectedIndicator.value).map((row) => ({ ...row, authority_name: 'England', indicator_name: indicatorNames.value.get(String(row.indicator_id)) ?? row.indicator_id })), 'england'))
const ndtmsTableRows = computed(() => indexed(ndtms.value?.estimates ?? [], 'ndtms'))
const ndtmsOtherTableRows = computed(() => indexed(ndtms.value?.other_rows ?? [], 'ndtms-other'))
const contractTableRows = computed(() => indexed(contracts.value?.notices ?? [], 'contract'))

const holdingNames: Record<string, string> = { 'CDP docs': 'Community Drug Partnership documents', 'CDP cands': 'CDP document candidates', Papers: 'Committee papers', 'Paper cands': 'Committee paper candidates', 'FOI cands': 'FOI candidates', 'Spend files': 'Council spending files' }
function holdingLink(dataset: string) {
  const target: Record<string, string> = { Grant: 'funding', Budget: 'funding', Contracts: 'contracts', NDTMS: 'treatment', Fingertips: 'treatment', 'Spend files': 'funding' }
  if (target[dataset]) return { path: route.path, query: { lens: target[dataset] } }
  if (dataset === 'CQC') return { path: '/cqc', query: { authority_ons_code: code.value } }
  return { path: '/coverage', query: { lens: 'history', ons_code: code.value } }
}
function caveat(key: string): string | null | undefined { return data.value?.caveats?.[key] }
function comparatorRows(key: 'rough_sleeping' | 'statutory_homelessness' | 'temporary_accommodation'): Row[] { return data.value?.comparators?.[key]?.rows ?? [] }
function comparatorCaveat(key: 'rough_sleeping' | 'statutory_homelessness' | 'temporary_accommodation'): string | null | undefined { return data.value?.comparators?.[key]?.caveat }

useHead(() => ({ title: `${name.value} · SectorTrace` }))
</script>

<template>
  <section class="st-profile space-y-8">
    <header class="st-page-header"><p class="atlas-eyebrow">Authority</p><h1>{{ name }}</h1><p>ONS code {{ code }}<span v-if="authority?.type"> · {{ authority.type }}</span><span v-if="authority?.region"> · {{ authority.region }}</span></p><div class="atlas-actions"><NuxtLink v-for="link in links" :key="link.to" :to="link.to" class="atlas-button">{{ link.label }}</NuxtLink></div></header>
    <StProfileLenses :items="lenses" :selected="lens" label="Authority evidence views" />
    <p v-if="!validLens" role="status">The requested authority view is unavailable. <NuxtLink :to="{ path: route.path, query: { lens: 'overview' } }">Open Overview</NuxtLink>.</p>
    <StEvidenceState :pending="pending" :error="error" :empty="!authority" empty-title="Authority unavailable" message="No authority identity was returned for this ONS code." @retry="refresh">
      <template v-if="data && validLens">
      <section v-if="lens === 'overview'" class="atlas-section" aria-label="Authority location"><h2>Authority boundary</h2><p>This is an identity locator. No metric is selected. Historical authorities are not combined with their successors.</p><GeographyMap :features="[]" :selected="code" locator focus-selected /><NuxtLink :to="{ path: '/geography', query: { inspect: code } }" class="atlas-button">Open in Places</NuxtLink></section>
      <LazyStProfileConnections v-if="lens === 'overview' || lens === 'commissioning'" :authority-code="code" />
      <section v-if="lens === 'overview'" id="coverage" class="atlas-section"><h2>Evidence held</h2><p>Each row describes one returned collection. Candidate records are finding aids awaiting review, not promoted evidence.</p><ul class="st-holdings-list"><li v-for="row in coverageRows" :key="String(row.dataset)"><NuxtLink :to="holdingLink(String(row.dataset))">{{ holdingNames[String(row.dataset)] ?? row.dataset }}</NuxtLink><span>{{ row.rows === null ? 'Not supplied' : Number(row.rows).toLocaleString('en-GB') }}</span></li></ul><StCaveat :text="data.coverage?.caveat" /></section>
      <section v-if="lens === 'history'" class="atlas-section"><h2>Source periods and procurement dates</h2><p>Coverage periods describe evidence held. Procurement dates describe published events. These timelines have different meanings and are kept separate.</p><div class="atlas-actions"><NuxtLink :to="{ path: '/coverage', query: { lens: 'history', ons_code: code } }" class="atlas-button">View source coverage periods</NuxtLink><NuxtLink :to="{ path: '/diary', query: { buyer_ons_code: code } }" class="atlas-button">View procurement dates</NuxtLink></div></section>
      <LazyStProfilePayments v-if="lens === 'funding'" :authority-code="code" />
      <section v-if="lens === 'funding'" id="grant-budget" class="atlas-section">
        <div class="atlas-section-head"><h2>Grant allocation and planned spend</h2><p>Ring-fenced drug and alcohol allocations are part of the total grant. They are not added to it. Allocations and budgeted spend describe different records.</p></div>
        <div class="grid gap-5 lg:grid-cols-2">
          <div class="atlas-panel atlas-panel-body space-y-4"><div><h3>Public health grant allocations</h3><p class="text-sm opacity-70">{{ grantRows.length }} rows · values are published in the stated unit.</p></div><StEvidenceTable caption="Public health grant allocations" source-details :columns="grantColumns" :rows="grantTableRows" row-key="row_key" /><StCaveat :text="caveat('grant_not_budget')" /></div>
          <div class="atlas-panel atlas-panel-body space-y-4"><div><h3>Budgeted public-health spend</h3><p class="text-sm opacity-70">Amounts are the authority's reported budget total for each year.</p></div><p class="atlas-footnote">This response supplies aggregated budget rows without row-level source URLs or hashes. They are not borrowed from the grant records.</p><StEvidenceTable :columns="budgetColumns" :rows="budgetTableRows" row-key="row_key" /><StCaveat :text="caveat('grant_not_budget')" /></div>
        </div>
      </section>

      <section v-if="lens === 'funding'" id="budget-detail" class="atlas-section">
        <div class="atlas-section-head"><h2>Budget detail</h2><p>Published lines behind the annual budget totals. Amounts are in GBP where the source denomination was readable.</p></div>
        <div class="atlas-panel atlas-panel-body space-y-4"><label class="text-sm"><span class="block mb-1 opacity-70">Financial year</span><select v-model="selectedBudgetYear" class="rounded border px-3 py-2"><option value="">Latest available</option><option v-for="year in budgetYears" :key="year" :value="year">{{ year }}</option></select></label><p class="atlas-footnote">Budget detail in this response does not include source URLs or hashes.</p><StEvidenceTable :columns="budgetDetailColumns" :rows="detailTableRows" row-key="row_key" /><StEmptyState v-if="!detailTableRows.length" title="No budget detail for this year" /><StCaveat :text="caveat('budget_detail')" /></div>
      </section>

      <section v-if="lens === 'treatment'" id="treatment" class="atlas-section">
        <div class="atlas-section-head"><h2>Treatment evidence</h2><p>Fingertips series and NDTMS estimates remain separate, including their intervals and source periods.</p></div>
        <label class="st-directory-search">Fingertips measure<select v-model="selectedIndicator"><option value="">All returned measures</option><option v-for="item in fingertips?.indicators ?? []" :key="String(item.indicator_id)" :value="String(item.indicator_id)">{{ item.indicator_name ?? item.indicator_id }}</option></select></label><NuxtLink :to="{ path: '/treatment', query: { ons_code: code, indicator_id: selectedIndicator || undefined, topic: 'numbers_in_treatment' } }" class="atlas-button">Explore treatment measures</NuxtLink><div class="space-y-5">
          <div class="atlas-panel atlas-panel-body space-y-4"><div><h3>Fingertips: numbers in treatment</h3><p class="text-sm opacity-70">{{ fingertips?.indicators?.length ?? 0 }} indicators · {{ fingertips?.series?.length ?? 0 }} local observations.</p></div><StEvidenceTable caption="Fingertips observations" source-details :columns="fingertipsColumns" :rows="fingertipsTableRows" row-key="row_key" /><StEmptyState v-if="!fingertipsTableRows.length" title="No Fingertips observations" /><details v-if="fingertipsEnglandRows.length"><summary class="text-sm opacity-70 cursor-pointer">England reference series ({{ fingertipsEnglandRows.length }} rows)</summary><div class="mt-3"><StEvidenceTable caption="Fingertips observations" source-details :columns="fingertipsColumns" :rows="fingertipsEnglandRows" row-key="row_key" /></div></details><StCaveat :text="fingertips?.caveat" /></div>
          <div class="atlas-panel atlas-panel-body space-y-4"><div><h3>NDTMS estimates</h3><p class="text-sm opacity-70">Estimates retain the point value and any bounds published with it.</p></div><StEvidenceTable caption="NDTMS estimates" source-details :columns="ndtmsColumns" :rows="ndtmsTableRows" row-key="row_key" /><StEmptyState v-if="!ndtmsTableRows.length" title="No NDTMS estimates" /><details v-if="ndtmsOtherTableRows.length"><summary class="text-sm opacity-70 cursor-pointer">Other NDTMS authority fields ({{ ndtmsOtherTableRows.length }} rows)</summary><div class="mt-3"><StEvidenceTable caption="Other NDTMS observations" source-details :columns="ndtmsOtherColumns" :rows="ndtmsOtherTableRows" row-key="row_key" /></div></details><StCaveat v-for="(text, key) in ndtms?.caveats" :key="key" :text="text" /></div>
        </div>
      </section>

      <section v-if="lens === 'contracts'" id="contracts" class="atlas-section">
        <div class="atlas-section-head"><h2>Contract notices</h2><p>{{ contracts?.notices?.length ?? 'Not supplied' }} notices returned of {{ contracts?.total ?? 'an unspecified number of' }} matching records. The profile is capped at 200 notices. Values describe published notices and do not establish payments.</p></div>
        <div class="atlas-panel atlas-panel-body space-y-4"><NuxtLink :to="{ path: '/contracts', query: { buyer_ons_code: code } }" class="atlas-button">Explore matching notices</NuxtLink><StEvidenceTable caption="Published procurement notices" source-details :columns="contractColumns" :rows="contractTableRows" row-key="row_key" /><StEmptyState v-if="!contractTableRows.length" title="No contract notices" /><StCaveat v-for="(text, key) in contracts?.caveats" :key="key" :text="text" /></div>
      </section>

      <section v-if="lens === 'context'" id="comparators" class="atlas-section">
        <div class="atlas-section-head"><h2>Contextual statistics</h2><p>Related public statistics are provided as context only and are never combined with this authority's treatment evidence.</p></div>
        <div class="space-y-5">
          <div class="atlas-panel atlas-panel-body space-y-4"><h3>Rough sleeping</h3><p class="atlas-footnote">The estimation method for each observation is not supplied in this response. Check the source before comparing years or areas.</p><StEvidenceTable caption="Rough sleeping observations" source-details :columns="roughColumns" :rows="indexed(comparatorRows('rough_sleeping'), 'rough')" row-key="row_key" /><StEmptyState v-if="!comparatorRows('rough_sleeping').length" title="No rough-sleeping rows collected" /><StCaveat :text="comparatorCaveat('rough_sleeping')" /></div>
          <div class="atlas-panel atlas-panel-body space-y-4"><h3>Statutory homelessness</h3><StEvidenceTable caption="Statutory homelessness observations" source-details :columns="homelessnessColumns" :rows="indexed(comparatorRows('statutory_homelessness'), 'homelessness')" row-key="row_key" /><StEmptyState v-if="!comparatorRows('statutory_homelessness').length" title="No statutory-homelessness rows collected" /><StCaveat :text="comparatorCaveat('statutory_homelessness')" /></div>
          <div class="atlas-panel atlas-panel-body space-y-4"><h3>Temporary accommodation</h3><p class="atlas-footnote">Published contextual totals. No rate, ranking or change between quarters is computed here.</p><StEvidenceTable caption="Temporary accommodation observations" source-details :columns="temporaryColumns" :rows="indexed(comparatorRows('temporary_accommodation'), 'ta')" row-key="row_key" /><StEmptyState v-if="!comparatorRows('temporary_accommodation').length" title="No temporary-accommodation rows collected" /><details v-if="data.comparators?.temporary_accommodation?.breakdown?.length"><summary class="text-sm opacity-70 cursor-pointer">Bed-and-breakfast breakdown</summary><div class="mt-3"><StEvidenceTable caption="Temporary accommodation breakdown" source-details :columns="temporaryBreakdownColumns" :rows="indexed(data.comparators.temporary_accommodation.breakdown, 'ta-breakdown')" row-key="row_key" /></div><StCaveat :text="data.comparators.temporary_accommodation.breakdown_caveat" /></details><StCaveat :text="comparatorCaveat('temporary_accommodation')" /></div>
        </div>
      </section>
      </template>
    </StEvidenceState>
  </section>
</template>
