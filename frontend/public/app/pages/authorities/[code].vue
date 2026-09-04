<script setup lang="ts">
import { computed, ref } from 'vue'
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
const selectedBudgetYear = ref('')

const { data, pending, error } = await useAsyncData<AuthorityWorkspace | null>(
  () => `authority-${code.value}`,
  () => api.authority(code.value) as Promise<AuthorityWorkspace>,
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
  { key: 'amount', label: 'Budgeted spend', numeric: true },
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
  { key: 'value', label: 'Value', numeric: true },
  { key: 'lower_ci_95', label: 'Lower 95% CI', numeric: true },
  { key: 'upper_ci_95', label: 'Upper 95% CI', numeric: true },
  { key: 'source_url', label: 'Source', link: true },
]
const ndtmsColumns: Column<Row>[] = [
  { key: 'dataset', label: 'Dataset' },
  { key: 'published_in', label: 'Published in', mono: true },
  { key: 'measure', label: 'Measure' },
  { key: 'value_text', label: 'Published value' },
  { key: 'lower', label: 'Lower bound', numeric: true },
  { key: 'upper', label: 'Upper bound', numeric: true },
  { key: 'source_url', label: 'Source', link: true },
]
const ndtmsOtherColumns: Column<Row>[] = [
  { key: 'dataset', label: 'Dataset' },
  { key: 'published_in', label: 'Published in', mono: true },
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
  { key: 'source_url', label: 'Source', link: true },
]
const roughColumns: Column<Row>[] = [
  { key: 'snapshot_year', label: 'Year', mono: true },
  { key: 'count', label: 'Count', numeric: true },
  { key: 'count_text', label: 'Published text' },
  { key: 'rate_per_100k', label: 'Rate per 100,000', numeric: true },
]
const homelessnessColumns: Column<Row>[] = [
  { key: 'quarter_label', label: 'Quarter', mono: true },
  { key: 'total_initial_assessments', label: 'Initial assessments', numeric: true },
  { key: 'total_owed_duty', label: 'Owed duty', numeric: true },
  { key: 'prevention_duty_owed', label: 'Prevention duty', numeric: true },
  { key: 'relief_duty_owed', label: 'Relief duty', numeric: true },
]
const temporaryColumns: Column<Row>[] = [
  { key: 'quarter_label', label: 'Quarter', mono: true },
  { key: 'total_households_ta', label: 'Households in TA', numeric: true },
  { key: 'households_ta_with_children', label: 'With children', numeric: true },
  { key: 'children_in_ta', label: 'Children in TA', numeric: true },
]
const temporaryBreakdownColumns: Column<Row>[] = [
  { key: 'quarter_label', label: 'Quarter', mono: true },
  { key: 'measure', label: 'Measure' },
  { key: 'households_text', label: 'Households' },
  { key: 'source_url', label: 'Source', link: true },
]

const coverageRows = computed<Row[]>(() => (data.value?.coverage?.labels ?? Object.keys(coverageCells.value)).map((dataset) => ({ dataset, rows: coverageCells.value[dataset] ?? 0 })))
const indexed = (rows: Row[], prefix: string): Row[] => rows.map((row, index) => ({ ...row, row_key: `${prefix}-${index}-${String(row.financial_year ?? row.time_period ?? row.notice_id ?? '')}` }))
const grantTableRows = computed(() => indexed(grantRows.value, 'grant'))
const budgetTableRows = computed(() => indexed(budgetRows.value, 'budget'))
const detailTableRows = computed(() => indexed(activeBudgetDetail.value, 'detail'))
const indicatorNames = computed(() => new Map((fingertips.value?.indicators ?? []).map((row) => [String(row.indicator_id), row.indicator_name])))
const fingertipsTableRows = computed(() => indexed((fingertips.value?.series ?? []).map((row) => ({ ...row, indicator_name: indicatorNames.value.get(String(row.indicator_id)) ?? row.indicator_id })), 'fingertips'))
const fingertipsEnglandRows = computed(() => indexed((fingertips.value?.england_series ?? []).map((row) => ({ ...row, authority_name: 'England', indicator_name: indicatorNames.value.get(String(row.indicator_id)) ?? row.indicator_id })), 'england'))
const ndtmsTableRows = computed(() => indexed(ndtms.value?.estimates ?? [], 'ndtms'))
const ndtmsOtherTableRows = computed(() => indexed(ndtms.value?.other_rows ?? [], 'ndtms-other'))
const contractTableRows = computed(() => indexed(contracts.value?.notices ?? [], 'contract'))

const latestBudget = computed(() => budgetRows.value[budgetRows.value.length - 1])
const latestGrant = computed(() => [...grantRows.value].reverse().find((row) => row.grant_type === 'allocation' || row.grant_type === 'total_consolidated_public_health_grant'))

function caveat(key: string): string | null | undefined { return data.value?.caveats?.[key] }
function comparatorRows(key: 'rough_sleeping' | 'statutory_homelessness' | 'temporary_accommodation'): Row[] { return data.value?.comparators?.[key]?.rows ?? [] }
function comparatorCaveat(key: 'rough_sleeping' | 'statutory_homelessness' | 'temporary_accommodation'): string | null | undefined { return data.value?.comparators?.[key]?.caveat }

useHead(() => ({ title: `SectorTrace — ${name.value}` }))
</script>

<template>
  <section class="space-y-8">
    <div class="atlas-hero">
      <div>
        <p class="atlas-kicker">Authority evidence workspace · published figures kept separate</p>
        <h1>{{ name }}</h1>
        <p v-if="authority" class="atlas-lede">{{ authority.type ?? 'Local authority' }}<span v-if="authority.region"> · {{ authority.region }}</span> · ONS code {{ authority.ons_code }}</p>
        <div class="atlas-actions">
          <NuxtLink v-for="link in links" :key="link.to" :to="link.to" class="atlas-button" :class="{ primary: link.label === 'Compare this authority' }">{{ link.label }}</NuxtLink>
        </div>
      </div>
      <div class="atlas-hero-aside">
        <div class="atlas-region"><strong>{{ coverageRows.length || '—' }}</strong><span>evidence layers indexed</span></div>
        <div class="atlas-region"><strong>{{ contracts?.total ?? '—' }}</strong><span>contract notices in window</span></div>
      </div>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading authority evidence…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else-if="data">
      <details class="atlas-read-first" open>
        <summary>Read this page first</summary>
        <p>Grant allocation, budgeted public-health spend, treatment estimates and contract notices are different evidence layers from different sources. They are shown side by side for inspection, never added, ranked, ratioed or substituted for one another.</p>
        <p>Rows carry the source's own wording and provenance in the API. A missing layer means the pipeline has not collected it for this authority; it is not evidence that the underlying activity is absent.</p>
      </details>

      <section id="coverage" class="atlas-section">
        <div class="atlas-section-head"><h2>Evidence inventory</h2><p>What the warehouse currently holds for {{ name }}.</p></div>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><div v-for="row in coverageRows" :key="String(row.dataset)" class="atlas-panel atlas-panel-body"><div class="atlas-stat-value">{{ row.rows }}</div><div class="atlas-stat-label">{{ row.dataset }} rows</div></div></div>
        <StCaveat :text="data.coverage?.caveat" />
      </section>

      <section id="grant-budget" class="atlas-section">
        <div class="atlas-section-head"><h2>Grant allocation and planned spend</h2><p>Two distinct financial views, held as separate tables.</p></div>
        <div class="grid gap-5 lg:grid-cols-2">
          <div class="atlas-panel atlas-panel-body space-y-4"><div><h3>Public health grant allocations</h3><p class="text-sm opacity-70">{{ grantRows.length }} rows · values are published in the stated unit.</p></div><div class="grid grid-cols-2 gap-3"><div class="atlas-stat"><div class="atlas-stat-value">{{ latestGrant?.amount ?? '—' }}</div><div class="atlas-stat-label">Latest allocation row</div></div><div class="atlas-stat"><div class="atlas-stat-value">{{ latestGrant?.financial_year ?? '—' }}</div><div class="atlas-stat-label">Financial year</div></div></div><StEvidenceTable :columns="grantColumns" :rows="grantTableRows" row-key="row_key" /><StCaveat :text="caveat('grant_not_budget')" /></div>
          <div class="atlas-panel atlas-panel-body space-y-4"><div><h3>Budgeted public-health spend</h3><p class="text-sm opacity-70">Amounts are the authority's reported budget total for each year.</p></div><div class="atlas-stat"><div class="atlas-stat-value">{{ latestBudget?.amount ?? '—' }}</div><div class="atlas-stat-label">Latest budgeted amount</div><div class="atlas-stat-sub">{{ latestBudget?.financial_year ?? '—' }}</div></div><StEvidenceTable :columns="budgetColumns" :rows="budgetTableRows" row-key="row_key" /><StCaveat :text="caveat('grant_not_budget')" /></div>
        </div>
      </section>

      <section id="budget-detail" class="atlas-section">
        <div class="atlas-section-head"><h2>Budget detail</h2><p>Published lines behind the annual budget totals. Amounts are in GBP where the source denomination was readable.</p></div>
        <div class="atlas-panel atlas-panel-body space-y-4"><label class="text-sm"><span class="block mb-1 opacity-70">Financial year</span><select v-model="selectedBudgetYear" class="rounded border px-3 py-2"><option value="">Latest available</option><option v-for="year in budgetYears" :key="year" :value="year">{{ year }}</option></select></label><StEvidenceTable :columns="budgetDetailColumns" :rows="detailTableRows" row-key="row_key" /><StEmptyState v-if="!detailTableRows.length" title="No budget detail for this year" /><StCaveat :text="caveat('budget_detail')" /></div>
      </section>

      <section id="treatment" class="atlas-section">
        <div class="atlas-section-head"><h2>Treatment evidence</h2><p>Fingertips series and NDTMS estimates remain separate, including their intervals and source periods.</p></div>
        <div class="space-y-5">
          <div class="atlas-panel atlas-panel-body space-y-4"><div><h3>Fingertips: numbers in treatment</h3><p class="text-sm opacity-70">{{ fingertips?.indicators?.length ?? 0 }} indicators · {{ fingertips?.series?.length ?? 0 }} local observations.</p></div><StEvidenceTable :columns="fingertipsColumns" :rows="fingertipsTableRows" row-key="row_key" /><StEmptyState v-if="!fingertipsTableRows.length" title="No Fingertips observations" /><details v-if="fingertipsEnglandRows.length"><summary class="text-sm opacity-70 cursor-pointer">England reference series ({{ fingertipsEnglandRows.length }} rows)</summary><div class="mt-3"><StEvidenceTable :columns="fingertipsColumns" :rows="fingertipsEnglandRows" row-key="row_key" /></div></details><StCaveat :text="fingertips?.caveat" /></div>
          <div class="atlas-panel atlas-panel-body space-y-4"><div><h3>NDTMS estimates</h3><p class="text-sm opacity-70">Estimates retain the point value and any bounds published with it.</p></div><StEvidenceTable :columns="ndtmsColumns" :rows="ndtmsTableRows" row-key="row_key" /><StEmptyState v-if="!ndtmsTableRows.length" title="No NDTMS estimates" /><details v-if="ndtmsOtherTableRows.length"><summary class="text-sm opacity-70 cursor-pointer">Other NDTMS authority fields ({{ ndtmsOtherTableRows.length }} rows)</summary><div class="mt-3"><StEvidenceTable :columns="ndtmsOtherColumns" :rows="ndtmsOtherTableRows" row-key="row_key" /></div></details><StCaveat v-for="(text, key) in ndtms?.caveats" :key="key" :text="text" /></div>
        </div>
      </section>

      <section id="contracts" class="atlas-section">
        <div class="atlas-section-head"><h2>Contract notices</h2><p>{{ contracts?.notices?.length ?? 0 }} notices shown from the collected window. Values are notice values, not spend.</p></div>
        <div class="atlas-panel atlas-panel-body space-y-4"><StEvidenceTable :columns="contractColumns" :rows="contractTableRows" row-key="row_key" /><StEmptyState v-if="!contractTableRows.length" title="No contract notices" /><StCaveat v-for="(text, key) in contracts?.caveats" :key="key" :text="text" /></div>
      </section>

      <section id="comparators" class="atlas-section">
        <div class="atlas-section-head"><h2>Context comparators</h2><p>Related public statistics are provided as context only and are never combined with this authority's treatment evidence.</p></div>
        <div class="space-y-5">
          <div class="atlas-panel atlas-panel-body space-y-4"><h3>Rough sleeping</h3><StEvidenceTable :columns="roughColumns" :rows="indexed(comparatorRows('rough_sleeping'), 'rough')" row-key="row_key" /><StEmptyState v-if="!comparatorRows('rough_sleeping').length" title="No rough-sleeping rows collected" /><StCaveat :text="comparatorCaveat('rough_sleeping')" /></div>
          <div class="atlas-panel atlas-panel-body space-y-4"><h3>Statutory homelessness</h3><StEvidenceTable :columns="homelessnessColumns" :rows="indexed(comparatorRows('statutory_homelessness'), 'homelessness')" row-key="row_key" /><StEmptyState v-if="!comparatorRows('statutory_homelessness').length" title="No statutory-homelessness rows collected" /><StCaveat :text="comparatorCaveat('statutory_homelessness')" /></div>
          <div class="atlas-panel atlas-panel-body space-y-4"><h3>Temporary accommodation</h3><StEvidenceTable :columns="temporaryColumns" :rows="indexed(comparatorRows('temporary_accommodation'), 'ta')" row-key="row_key" /><StEmptyState v-if="!comparatorRows('temporary_accommodation').length" title="No temporary-accommodation rows collected" /><details v-if="data.comparators?.temporary_accommodation?.breakdown?.length"><summary class="text-sm opacity-70 cursor-pointer">Bed-and-breakfast breakdown</summary><div class="mt-3"><StEvidenceTable :columns="temporaryBreakdownColumns" :rows="indexed(data.comparators.temporary_accommodation.breakdown, 'ta-breakdown')" row-key="row_key" /></div><StCaveat :text="data.comparators.temporary_accommodation.breakdown_caveat" /></details><StCaveat :text="comparatorCaveat('temporary_accommodation')" /></div>
        </div>
      </section>
    </template>
  </section>
</template>
