<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { ProviderTimelineResponse, TimelineEvent } from '~/types/api'

type Row = Record<string, unknown>

interface ProviderWorkspace extends ProviderTimelineResponse {
  provider: (Record<string, unknown> & { provider_key?: string; canonical_name?: string; is_target?: number; notes?: string | null; status?: string | null; superseded_by?: string | null }) | null
  cqc_locations?: Row[]
  entity_edges?: Row[]
  tribunal_cases?: Row[]
  charity_finance?: Row[]
  cqc_inspections?: Row[]
  disclosure?: { gaps?: Row[]; disclosed?: Row[]; not_searched?: Row[]; topics?: string[] }
  filings?: Row[]
  pfd_mentions?: Row[]
  caveats?: Record<string, string | null>
}
interface LineageResponse {
  edges?: Row[]
  chain?: Row[]
  identifiers?: Row[]
  caveat?: string | null
}

const route = useRoute()
const api = usePublicApi()
const key = computed(() => String(route.params.key ?? ''))

const { data, pending, error } = await useAsyncData<ProviderWorkspace | null>(
  () => `provider-${key.value}`,
  () => api.providerTimeline(key.value) as Promise<ProviderWorkspace>,
  { default: () => null, watch: [key] },
)
const { data: lineage } = await useAsyncData<LineageResponse | null>(
  () => `provider-lineage-${key.value}`,
  () => api.get<LineageResponse>(`/providers/${encodeURIComponent(key.value)}/lineage`),
  { default: () => null, watch: [key], lazy: true },
)

const provider = computed(() => data.value?.provider)
const providerName = computed(() => provider.value?.canonical_name ?? key.value)
const events = computed(() => data.value?.events ?? [])
const locations = computed(() => data.value?.cqc_locations ?? [])
const inspections = computed(() => data.value?.cqc_inspections ?? [])
const finance = computed(() => data.value?.charity_finance ?? [])
const pfd = computed(() => data.value?.pfd_mentions ?? [])
const filings = computed(() => data.value?.filings ?? [])
const tribunals = computed(() => data.value?.tribunal_cases ?? [])
const edges = computed(() => data.value?.entity_edges ?? [])
const disclosure = computed(() => data.value?.disclosure)
const lineageEdges = computed(() => lineage.value?.edges ?? [])
const lineageChain = computed(() => lineage.value?.chain ?? [])
const lineageIdentifiers = computed(() => lineage.value?.identifiers ?? [])
const lineageForward = computed(() => lineageEdges.value.filter((edge) => edge.direction !== 'predecessor'))
const lineagePredecessors = computed(() => lineageEdges.value.filter((edge) => edge.direction === 'predecessor'))

const links = computed(() => [
  { to: '/providers', label: 'All providers' },
  { to: `/compare?provider_key=${encodeURIComponent(key.value)}`, label: 'Compare providers' },
  { to: `/relationships?provider_key=${encodeURIComponent(key.value)}`, label: 'Who commissions it' },
  { to: `/coverage?provider_key=${encodeURIComponent(key.value)}`, label: 'View coverage history' },
])

const inventory = computed(() => [
  { label: 'CQC locations', count: locations.value.length },
  { label: 'Dated records', count: events.value.length },
  { label: 'Filed accounts', count: finance.value.length },
  { label: 'Safety/legal', count: pfd.value.length + tribunals.value.length },
])
const indexed = (rows: Row[], prefix: string): Row[] => rows.map((row, index) => ({ ...row, row_key: `${prefix}-${index}-${String(row.date ?? row.report_date ?? row.filing_date ?? '')}` }))

const timelineColumns: Column<Row>[] = [
  { key: 'date', label: 'Date', mono: true }, { key: 'event_type', label: 'Type' },
  { key: 'label', label: 'Evidence' }, { key: 'value_summary', label: 'Detail' },
  { key: 'notice_link', label: 'Notice', link: true }, { key: 'source_url', label: 'Source', link: true },
]
const edgeColumns: Column<Row>[] = [
  { key: 'relationship', label: 'Relationship' }, { key: 'target_type', label: 'Entity type' },
  { key: 'target_id', label: 'Identifier', mono: true }, { key: 'target_label', label: 'Name' },
  { key: 'basis', label: 'Verification basis' }, { key: 'source_url', label: 'Source', link: true },
]
const locationColumns: Column<Row>[] = [
  { key: 'location_name', label: 'Location' }, { key: 'local_authority_raw', label: 'Local authority' },
  { key: 'overall_rating', label: 'Rating' }, { key: 'overall_rating_date', label: 'Rating date', mono: true },
  { key: 'registration_status', label: 'Registration' }, { key: 'source_url', label: 'Source', link: true },
]
const inspectionColumns: Column<Row>[] = [
  { key: 'location_name', label: 'Location' }, { key: 'report_date', label: 'Report date', mono: true },
  { key: 'first_visit_date', label: 'First visit', mono: true }, { key: 'source_url', label: 'Source', link: true },
]
const financeColumns: Column<Row>[] = [
  { key: 'financial_year_end', label: 'Year end', mono: true }, { key: 'total_income', label: 'Total income', numeric: true },
  { key: 'total_expenditure', label: 'Total expenditure', numeric: true }, { key: 'income_from_govt_contracts', label: 'Government contracts', numeric: true },
  { key: 'income_from_govt_grants', label: 'Government grants', numeric: true }, { key: 'source_url', label: 'Source', link: true },
]
const filingColumns: Column<Row>[] = [
  { key: 'filing_date', label: 'Filed', mono: true }, { key: 'category', label: 'Category' },
  { key: 'subcategory', label: 'Subcategory' }, { key: 'description', label: 'Description' },
  { key: 'document_url', label: 'Document', link: true },
]
const pfdColumns: Column<Row>[] = [
  { key: 'report_date', label: 'Report date', mono: true }, { key: 'mention_type', label: 'Match type' },
  { key: 'matched_name', label: 'Matched name' }, { key: 'coroner_area', label: 'Coroner area' },
  { key: 'report_url', label: 'Report', link: true },
]
const tribunalColumns: Column<Row>[] = [
  { key: 'case_number', label: 'Case' }, { key: 'decision_date', label: 'Decided', mono: true },
  { key: 'outcome', label: 'Outcome' }, { key: 'outcome_confidence', label: 'Confidence' },
  { key: 'provider_match_basis', label: 'Match basis' }, { key: 'source_url', label: 'Source', link: true },
]
const disclosureColumns: Column<Row>[] = [
  { key: 'financial_year_end', label: 'Year end', mono: true }, { key: 'topic', label: 'Topic' },
  { key: 'status', label: 'Search result' }, { key: 'search_terms', label: 'Terms searched' },
]

const timelineRows = computed(() => indexed(events.value as Row[], 'event'))
const edgeRows = computed(() => indexed(edges.value, 'edge'))
const locationRows = computed(() => indexed(locations.value, 'location'))
const inspectionRows = computed(() => indexed(inspections.value, 'inspection'))
const financeRows = computed(() => indexed(finance.value, 'finance'))
const filingRows = computed(() => indexed(filings.value, 'filing'))
const pfdRows = computed(() => indexed(pfd.value, 'pfd'))
const tribunalRows = computed(() => indexed(tribunals.value, 'tribunal'))
const disclosureRows = computed(() => {
  const searched = new Map((disclosure.value?.gaps ?? []).map((row) => [`${row.financial_year_end}|${row.topic}`, row]))
  const disclosed = new Set((disclosure.value?.disclosed ?? []).map((row) => `${row.financial_year_end}|${row.topic}`))
  const notSearched = new Set((disclosure.value?.not_searched ?? []).map((row) => String(row.financial_year_end)))
  return indexed((disclosure.value?.topics ?? []).flatMap((topic) => {
    const years = [...new Set([...searched.keys(), ...disclosed].filter((value) => value.endsWith(`|${topic}`)).map((value) => value.split('|')[0]))]
    return years.map((year) => {
      const row = searched.get(`${year}|${topic}`)
      return { financial_year_end: year, topic, status: notSearched.has(year) ? 'Report not searched' : row ? 'Terms did not match' : 'Terms matched', search_terms: row?.search_terms ?? '—' }
    })
  }), 'disclosure')
})

function caveat(name: string): string | null | undefined { return data.value?.caveats?.[name] }

useHead(() => ({ title: `SectorTrace — ${providerName.value}` }))
</script>

<template>
  <section class="space-y-8">
    <div class="atlas-hero"><div><p class="atlas-kicker">Provider evidence workspace · coverage is not performance</p><h1>{{ providerName }} <span v-if="provider?.is_target" class="atlas-badge">★ campaign subject</span></h1><p class="atlas-lede">{{ provider?.status && provider.status !== 'active' ? provider.status : 'Active provider record' }} · provider key {{ key }}</p><p v-if="provider?.notes" class="text-sm opacity-75">{{ provider.notes }}</p><div class="atlas-actions"><NuxtLink v-for="link in links" :key="link.to" :to="link.to" class="atlas-button" :class="{ primary: link.label === 'Compare providers' }">{{ link.label }}</NuxtLink></div></div><div class="atlas-hero-aside"><div class="atlas-region"><strong>{{ events.length }}</strong><span>dated records</span></div><div class="atlas-region"><strong>{{ locations.length }}</strong><span>CQC locations held</span></div></div></div>

    <div v-if="pending" class="text-sm opacity-60">Loading provider evidence…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else-if="data">
      <details class="atlas-read-first" open><summary>Read this page first</summary><p>This workspace brings together published records held for one organisation. Partial evidence describes the warehouse's coverage, not the provider itself. A name match or a missing row is not by itself a verified relationship or a finding.</p></details>

      <section id="inventory" class="atlas-section"><div class="atlas-section-head"><h2>Evidence inventory</h2><p>Counts describe records held for this provider, not its scale or performance.</p></div><div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><div v-for="item in inventory" :key="item.label" class="atlas-panel atlas-panel-body"><div class="atlas-stat-value">{{ item.count }}</div><div class="atlas-stat-label">{{ item.label }}</div><div class="atlas-stat-sub">records held</div></div></div></section>

      <section v-if="lineage && (lineageEdges.length || lineageChain.length > 1 || lineageIdentifiers.length)" id="lineage" class="atlas-section"><div class="atlas-section-head"><h2>Verified identity lineage</h2><p>The administrative record of this organisation’s identity; it does not describe continuity of services, staff, or contracts.</p></div><div class="atlas-panel atlas-panel-body space-y-4"><StCaveat :text="lineage.caveat" /><p v-if="lineageChain.length > 1" class="text-sm">{{ lineageChain.map((node) => node.canonical_name ?? node.provider_key).join(' → ') }}</p><ul v-if="lineageEdges.length" class="list-disc pl-5 text-sm"><li v-for="(edge, index) in lineageEdges" :key="index">{{ edge.direction === 'predecessor' ? `${edge.canonical_name ?? edge.provider_key} ${edge.relationship ?? 'predecessor'} this entity` : `${edge.relationship ?? 'lifecycle change'} ${edge.canonical_name ?? edge.provider_key ?? ''}` }} <span class="opacity-60">— {{ edge.basis }}</span></li></ul><p v-if="lineageIdentifiers.length" class="text-xs opacity-70">Verified identifiers: {{ lineageIdentifiers.map((item) => `${item.scheme} ${item.identifier}${item.role ? ` (${item.role})` : ''}`).join('; ') }}</p></div></section>

      <section id="graph" class="atlas-section"><div class="atlas-section-head"><h2>Evidence graph links</h2><p>Other entity edges held for this provider. Name matches remain labelled as such and are not treated as verified relationships.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="edgeColumns" :rows="edgeRows" row-key="row_key" /><StEmptyState v-if="!edgeRows.length" title="No entity links held" /><StCaveat :text="caveat('cqc_coverage')" /></div></section>

      <section id="timeline" class="atlas-section"><div class="atlas-section-head"><h2>Evidence timeline</h2><p>{{ events.length }} dated records, newest first. Contract events link to the published notice where available.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="timelineColumns" :rows="timelineRows" row-key="row_key" /><StEmptyState v-if="!timelineRows.length" title="No dated evidence" /></div></section>

      <section id="cqc" class="atlas-section"><div class="atlas-section-head"><h2>CQC registrations</h2><p>{{ locations.length }} registered locations held for this provider.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="locationColumns" :rows="locationRows" row-key="row_key" /><StEmptyState v-if="!locationRows.length" title="No CQC locations" /><StCaveat :text="caveat('cqc_coverage')" /></div></section>
      <section id="cqc-reports" class="atlas-section"><div class="atlas-section-head"><h2>CQC inspection history</h2><p>{{ inspections.length }} published inspection reports across the registered locations.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="inspectionColumns" :rows="inspectionRows" row-key="row_key" /><StEmptyState v-if="!inspectionRows.length" title="No CQC inspection reports" /><StCaveat :text="caveat('cqc_inspection_dates')" /></div></section>

      <section id="finance" class="atlas-section"><div class="atlas-section-head"><h2>Charity finance</h2><p>Filed accounts keep income, expenditure and government income in their original fields.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="financeColumns" :rows="financeRows" row-key="row_key" /><StEmptyState v-if="!financeRows.length" title="No charity financials" /><StCaveat :text="caveat('charity_share')" /></div></section>

      <section id="disclosure" class="atlas-section"><div class="atlas-section-head"><h2>Annual report disclosure</h2><p>Search results by topic and year. A non-match is a prompt to check the report, not proof that a topic was absent.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="disclosureColumns" :rows="disclosureRows" row-key="row_key" /><StEmptyState v-if="!disclosureRows.length" title="No annual-report disclosure rows" /></div></section>
      <section id="filings" class="atlas-section"><div class="atlas-section-head"><h2>Company filing history</h2><p>{{ filings.length }} Companies House filing records held.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="filingColumns" :rows="filingRows" row-key="row_key" /><StEmptyState v-if="!filingRows.length" title="No company filings" /><StCaveat :text="caveat('filing_records')" /></div></section>

      <section id="pfd" class="atlas-section"><div class="atlas-section-head"><h2>Coroners' reports mentioning this provider</h2><p>Sent to the provider and named in report text remain separate match types.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="pfdColumns" :rows="pfdRows" row-key="row_key" /><StEmptyState v-if="!pfdRows.length" title="No PFD mentions" /><StCaveat :text="caveat('pfd_mentions')" /></div></section>
      <section id="tribunals" class="atlas-section"><div class="atlas-section-head"><h2>Employment tribunal cases</h2><p>{{ tribunals.length }} judgments naming this provider.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="tribunalColumns" :rows="tribunalRows" row-key="row_key" /><StEmptyState v-if="!tribunalRows.length" title="No tribunal cases" /><StCaveat :text="caveat('tribunal_component')" /></div></section>
    </template>
  </section>
</template>
