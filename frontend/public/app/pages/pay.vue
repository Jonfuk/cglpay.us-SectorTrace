<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { PayResponse, StatutoryPayRate } from '~/types/api'

type PayRow = Record<string, unknown>
type PayPayload = PayResponse & {
  charity_wage_series?: PayRow[]
  nhs_job_adverts?: PayRow[]
  provider_published_pay?: PayRow[]
  living_wage_accreditations?: PayRow[]
  gender_pay_gap_reports?: PayRow[]
  workforce_census?: PayRow[]
  ons_ashe_observations?: PayRow[]
  skills_for_care_estimates?: PayRow[]
  source_groups?: Array<{ key: string; label: string; count: number }>
  filters_available?: { roles?: string[]; pay_units?: string[] }
}

// Pay is a set of published signals, not a payroll dataset. The original page
// exposed eight evidence arrays; the first Nuxt pass rendered only statutory
// rates. Keep each source in its own panel so no unlike values are averaged or
// converted into a misleading pay score.
const api = usePublicApi()
const filters = useFilterState()
const source = computed({ get: () => String(filters.get('source') ?? ''), set: (v: string) => { void filters.set('source', v || undefined) } })
const role = computed({ get: () => String(filters.get('role') ?? ''), set: (v: string) => { void filters.set('role', v || undefined) } })
const payUnit = computed({ get: () => String(filters.get('pay_unit') ?? ''), set: (v: string) => { void filters.set('pay_unit', v || undefined) } })

const { data, pending, error } = await useDataRoute<PayResponse>('public-pay', (f) => api.pay({ query: f }))
const payload = computed(() => (data.value ?? null) as PayPayload | null)
const groups = computed(() => payload.value?.source_groups ?? [])
const availableRoles = computed(() => payload.value?.filters_available?.roles ?? [])

const rates = computed<StatutoryPayRate[]>(() => payload.value?.statutory_pay_rates ?? [])
const currentPeriod = computed(() => rates.value[0]?.period_label)
const currentRates = computed(() => rates.value.filter((row) => row.period_label === currentPeriod.value && row.band_label !== 'Under 18'))
const currentRateRows = computed<PayRow[]>(() => currentRates.value as unknown as PayRow[])
const genericRows = (key: keyof PayPayload): PayRow[] => (payload.value?.[key] as PayRow[] | undefined) ?? []
const cols = (keys: Array<[string, string, boolean?]>): Column<PayRow>[] => keys.map(([key, label, numeric]) => ({ key, label, numeric }))
const caveats = computed(() => Object.entries(payload.value?.caveats ?? {}).filter(([, text]) => Boolean(text)))

function value(row: PayRow, key: string): string {
  const item = row[key]
  return item === null || item === undefined || item === '' ? '—' : String(item)
}
function money(row: PayRow, key: string): string {
  const item = row[key]
  return typeof item === 'number' ? item.toLocaleString('en-GB', { style: 'currency', currency: 'GBP', maximumFractionDigits: 0 }) : value(row, key)
}
function clearFilters() { source.value = ''; role.value = ''; payUnit.value = '' }

useHead({ title: 'SectorTrace — Pay & benchmarks' })
</script>

<template>
  <section class="atlas-hero"><div><div class="atlas-kicker">Workforce · separate evidence layers</div><h1>Pay</h1><p class="atlas-lede">Explore published pay, advertised roles, statutory floors, and labour-market context. Each source answers a different question, so these figures are not combined into one pay score.</p><details class="atlas-read-first"><summary>How to read pay evidence</summary><p>Charity accounts provide an indicative wage measure; NHS Jobs records advertised vacancies; provider pages record what an organisation published; statutory rates are legal hourly floors.</p><p>None is payroll data. Labour-market benchmarks provide context only, and the portal does not calculate gaps, ratios, or a combined trend from unlike sources.</p></details></div></section>
  <section v-if="pending" class="atlas-panel p-6">Loading pay evidence…</section>
  <section v-else-if="error || !payload" class="atlas-panel p-6">Pay evidence is unavailable.</section>
  <template v-else>
    <section class="atlas-section atlas-panel atlas-panel-body"><div class="atlas-eyebrow">Pay evidence explorer</div><div class="flex flex-wrap items-end gap-3 mt-3"><label class="text-sm">Source<select v-model="source" class="block mt-1 px-2 py-1"><option value="">All sources</option><option v-for="group in groups" :key="group.key" :value="group.key">{{ group.label }} · {{ group.count }}</option></select></label><label class="text-sm">Role<input v-model="role" list="pay-role-options" class="block mt-1 px-2 py-1" placeholder="Any role"><datalist id="pay-role-options"><option v-for="item in availableRoles" :key="item" :value="item" /></datalist></label><label class="text-sm">Unit<select v-model="payUnit" class="block mt-1 px-2 py-1"><option value="">Any pay unit</option><option v-for="item in (payload.filters_available?.pay_units ?? [])" :key="item" :value="item">{{ item }}</option></select></label><button v-if="source || role || payUnit" type="button" class="atlas-button" @click="clearFilters">Clear filters</button></div><p class="atlas-footnote mt-3">Sources are never combined. Filter state is in the URL and can be shared.</p></section>

    <section v-if="genericRows('charity_wage_series').length" class="atlas-section atlas-panel atlas-panel-body"><h2>Indicative wage from charity accounts</h2><p class="atlas-footnote">Wages and salaries divided by an average employee count. This is not a pay scale, a median salary, or an individual employee’s earnings.</p><StEvidenceTable :columns="cols([['canonical_name', 'Provider'], ['financial_year_end', 'Year'], ['indicative_wage_per_head', 'Per head', true], ['indicative_wage_per_fte', 'Per FTE', true], ['employees_basis', 'Denominator']])" :rows="genericRows('charity_wage_series')" row-key="charity_number" /></section>

    <section v-if="genericRows('nhs_job_adverts').length" class="atlas-section atlas-panel atlas-panel-body"><h2>Advertised roles</h2><p class="atlas-footnote">NHS Jobs figures cover adverts whose employer field matched a known provider name. Providers advertising solely on their own sites are invisible here; every count is a floor.</p><StEvidenceTable :columns="cols([['canonical_name', 'Provider'], ['job_title', 'Role'], ['salary_raw', 'Published salary'], ['contract_type', 'Contract'], ['working_pattern', 'Pattern'], ['posted_date', 'Posted']])" :rows="genericRows('nhs_job_adverts').slice(0, 100)" row-key="job_reference" /></section>

    <section class="atlas-section atlas-panel atlas-panel-body"><h2>Published and statutory pay</h2><p class="atlas-footnote">Statutory rates are published hourly floors. Provider-owned pages and Living Wage checks remain separate records.</p><div v-if="currentRates.length" class="atlas-band"><h3>Current statutory rates</h3><StEvidenceTable :columns="cols([['period_label', 'Period'], ['band_label', 'Band'], ['band_role', 'Role'], ['value_text', 'Published value']])" :rows="currentRateRows" row-key="effective_from" /></div><div v-if="genericRows('provider_published_pay').length" class="atlas-band"><h3>Provider-published pay</h3><StEvidenceTable :columns="cols([['canonical_name', 'Provider'], ['role_title', 'Role'], ['value_text', 'Published value'], ['pay_unit', 'Unit'], ['source_url', 'Source']])" :rows="genericRows('provider_published_pay').slice(0, 100)" row-key="source_url" /></div><div v-if="genericRows('living_wage_accreditations').length" class="atlas-band"><h3>Living Wage Foundation checks</h3><StEvidenceTable :columns="cols([['canonical_name', 'Provider'], ['searched_variant', 'Checked name'], ['accredited', 'Result'], ['retrieved_at', 'Retrieved']])" :rows="genericRows('living_wage_accreditations')" row-key="canonical_name" /></div><div v-if="genericRows('gender_pay_gap_reports').length" class="atlas-band"><h3>Gender pay gap filings</h3><StEvidenceTable :columns="cols([['canonical_name', 'Employer'], ['reporting_year', 'Year'], ['mean_hourly_gap_percent', 'Mean gap %', true], ['median_hourly_gap_percent', 'Median gap %', true]])" :rows="genericRows('gender_pay_gap_reports')" row-key="canonical_name" /></div></section>

    <section v-if="genericRows('workforce_census').length" class="atlas-section atlas-panel atlas-panel-body"><h2>Workforce census</h2><p class="atlas-footnote">Segments and years are shown as published and are not differenced or combined.</p><StEvidenceTable :columns="cols([['census_year', 'Year'], ['metric', 'Metric'], ['workforce_segment', 'Segment'], ['value', 'Value'], ['unit', 'Unit'], ['verified', 'Verified']])" :rows="genericRows('workforce_census')" row-key="metric" /></section>

    <section v-if="genericRows('ons_ashe_observations').length || genericRows('skills_for_care_estimates').length" class="atlas-section atlas-panel atlas-panel-body"><h2>External comparators</h2><p class="atlas-footnote">ASHE and Skills for Care provide labour-market context only. They are not measures of what tracked providers pay.</p><div v-if="genericRows('ons_ashe_observations').length" class="atlas-band"><h3>ONS ASHE observations</h3><StEvidenceTable :columns="cols([['area_name', 'Area'], ['occupation_label', 'Occupation'], ['year', 'Year'], ['hourly_pay', 'Hourly pay', true]])" :rows="genericRows('ons_ashe_observations').slice(0, 100)" row-key="area_code" /></div><div v-if="genericRows('skills_for_care_estimates').length" class="atlas-band"><h3>Skills for Care estimates</h3><StEvidenceTable :columns="cols([['area', 'Area'], ['job_role', 'Role'], ['year', 'Year'], ['hourly_pay', 'Hourly pay', true], ['vacancy_rate', 'Vacancy', true]])" :rows="genericRows('skills_for_care_estimates').slice(0, 100)" row-key="area_code" /></div></section>

    <section v-if="caveats.length" class="atlas-section atlas-panel atlas-panel-body"><h2>How to read these figures</h2><div class="space-y-2"><p v-for="[key, text] in caveats" :key="key" class="atlas-caveat"><span aria-hidden="true">⚠</span> {{ text }}</p></div></section>
  </template>
</template>
