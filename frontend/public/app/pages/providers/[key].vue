<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { ProviderTimelineResponse } from '~/types/api'

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

const { data, pending, error, refresh } = await useAsyncData<ProviderWorkspace | null>(
  () => `provider-${key.value}`,
  (_app, { signal }) => api.providerTimeline(key.value, { signal }) as Promise<ProviderWorkspace>,
  { default: () => null, watch: [key] },
)
const { data: lineage, pending: lineagePending, error: lineageError, refresh: refreshLineage } = await useAsyncData<LineageResponse | null>(
  () => `provider-lineage-${key.value}`,
  (_app, { signal }) => api.get<LineageResponse>(`/providers/${encodeURIComponent(key.value)}/lineage`, { signal }),
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

const links = computed(() => [
  { to: '/providers', label: 'All providers' },
  { to: `/compare?provider_key=${encodeURIComponent(key.value)}`, label: 'Compare providers' },
  { to: `/relationships?provider_key=${encodeURIComponent(key.value)}`, label: 'Who commissions it' },
  { to: `/coverage?provider_key=${encodeURIComponent(key.value)}`, label: 'View coverage history' },
])

const lenses = [
  { key: 'overview', label: 'Overview' }, { key: 'contracts', label: 'Contracts' },
  { key: 'finance-pay', label: 'Finance and pay' }, { key: 'registrations', label: 'Registrations' },
  { key: 'safety-legal', label: 'Safety and legal' }, { key: 'connections', label: 'Connections' },
  { key: 'history', label: 'History' },
]
const lens = computed(() => String(route.query.lens ?? 'overview'))
const validLens = computed(() => lenses.some(item => item.key === lens.value))
const inventory = computed(() => [
  { label: 'CQC registration records', count: data.value?.cqc_locations?.length, lens: 'registrations' },
  { label: 'CQC inspection reports', count: data.value?.cqc_inspections?.length, lens: 'registrations' },
  { label: 'Charity finance records', count: data.value?.charity_finance?.length, lens: 'finance-pay' },
  { label: 'Company filing records', count: data.value?.filings?.length, lens: 'finance-pay' },
  { label: 'Employment tribunal judgments', count: data.value?.tribunal_cases?.length, lens: 'safety-legal' },
  { label: 'Dated records', count: data.value?.events?.length, lens: 'history' },
])
const adverts = computed(() => indexed(events.value.filter(row => row.event_type === 'nhs_job_advert') as Row[], 'advert'))
const indexed = (rows: Row[], prefix: string): Row[] => rows.map((row, index) => ({ ...row, row_key: `${prefix}-${index}-${String(row.date ?? row.report_date ?? row.filing_date ?? '')}` }))

const timelineColumns: Column<Row>[] = [
  { key: 'date', label: 'Date', mono: true }, { key: 'event_type', label: 'Type' },
  { key: 'label', label: 'Evidence' }, { key: 'value_summary', label: 'Detail' },
  { key: 'notice_link', label: 'Notice', link: true }, { key: 'source_url', label: 'Source', link: true },
]
const edgeColumns: Column<Row>[] = [
  { key: 'source_type', label: 'Source entity type' }, { key: 'source_id', label: 'Source entity identifier', mono: true },
  { key: 'relationship', label: 'Relationship' }, { key: 'target_type', label: 'Entity type' },
  { key: 'target_id', label: 'Identifier', mono: true }, { key: 'target_label', label: 'Name' },
  { key: 'basis', label: 'Verification basis' }, { key: 'source_url', label: 'Source', link: true },
]
const locationColumns: Column<Row>[] = [
  { key: 'location_name', label: 'Location' }, { key: 'local_authority_raw', label: 'Local authority' },
  { key: 'overall_rating', label: 'Rating' }, { key: 'overall_rating_date', label: 'Rating date', mono: true },
  { key: 'rating_source', label: 'Rating origin' }, { key: 'bulk_rating_source_url', label: 'Bulk rating source', link: true },
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
  { key: 'document_url', label: 'Document', link: true }, { key: 'source_url', label: 'Source', link: true }, { key: 'retrieved_at', label: 'Retrieved', mono: true },
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

// The API's legacy accounts summary replaces missing income with zero.
// The raw finance rows remain authoritative and are displayed in their lens.
const timelineRows = computed(() => indexed(events.value.map(row => row.event_type === 'charity_accounts' ? { ...row, value_summary: 'See the source figures in Finance and pay' } : row) as Row[], 'event'))
const edgeRows = computed(() => indexed(edges.value, 'edge'))
const locationRows = computed(() => indexed(locations.value, 'location'))
const inspectionRows = computed(() => indexed(inspections.value, 'inspection'))
const financeRows = computed(() => indexed(finance.value, 'finance'))
const filingRows = computed(() => indexed(filings.value, 'filing'))
const pfdRows = computed(() => indexed(pfd.value, 'pfd'))
const tribunalRows = computed(() => indexed(tribunals.value, 'tribunal'))
// Keep the response's three disclosure states separate. In particular a
// report never searched must survive even when no topic/year matches exist.
const disclosureRows = computed(() => indexed([
  ...(disclosure.value?.gaps ?? []).map(row => ({ ...row, status: 'Terms did not match' })),
  ...(disclosure.value?.disclosed ?? []).map(row => ({ ...row, status: 'Terms matched' })),
], 'disclosure'))
const unsearchedReports = computed(() => indexed(disclosure.value?.not_searched ?? [], 'unsearched'))

function caveat(name: string): string | null | undefined { return data.value?.caveats?.[name] }

useHead(() => ({ title: `${providerName.value} · SectorTrace` }))
</script>

<template>
  <section class="st-profile space-y-8">
    <header class="st-page-header"><p class="atlas-eyebrow">Provider</p><h1>{{ providerName }} <span v-if="provider?.is_target" class="atlas-badge">Campaign subject</span></h1><p>Provider key {{ key }}<span v-if="provider?.status"> · Recorded status {{ provider.status }}</span></p><p v-if="provider?.notes">{{ provider.notes }}</p><div class="atlas-actions"><NuxtLink v-for="link in links" :key="link.to" :to="link.to" class="atlas-button">{{ link.label }}</NuxtLink><NuxtLink v-if="provider?.canonical_name" :to="{ path: '/documents', query: { q: provider.canonical_name } }" class="atlas-button">Search documents for this name</NuxtLink></div></header>
    <StProfileLenses :items="lenses" :selected="lens" label="Provider evidence views" />
    <p v-if="!validLens" role="status">The requested provider view is unavailable. <NuxtLink :to="{ path: route.path, query: { lens: 'overview' } }">Open Overview</NuxtLink>.</p>
    <StEvidenceState :pending="pending" :error="error" :empty="!provider" empty-title="Provider unavailable" message="No provider identity was returned for this key." @retry="refresh">
      <template v-if="validLens">
      <section v-if="lens === 'overview'" id="inventory" class="atlas-section"><h2>Evidence held</h2><p>Each count describes one collection returned for this provider. Missing evidence does not establish an absence of activity.</p><ul class="st-holdings-list"><li v-for="item in inventory" :key="item.label"><NuxtLink :to="{ path: route.path, query: { lens: item.lens } }">{{ item.label }}</NuxtLink><span>{{ item.count === undefined ? 'Not supplied' : item.count.toLocaleString('en-GB') }}</span></li></ul><p>Coroners' reports retain their separate mention types in Safety and legal. Document name searches find text and do not establish provider relationships.</p><NuxtLink :to="{ path: route.path, query: { lens: 'connections' } }" class="atlas-button">View identity and connections</NuxtLink></section>
      <LazyStProfileNotices v-if="lens === 'contracts'" :provider-key="key" />
      <LazyStProfileConnections v-if="lens === 'connections'" :provider-key="key" />
      <section v-if="lens === 'finance-pay'" class="atlas-section"><h2>Pay evidence</h2><p>Advertised pay is an employer's offer on its publication date. Hourly and annual pay remain in their published form. Charity wage-per-head is not an average salary.</p><NuxtLink :to="{ path: '/pay', query: { provider_key: key } }" class="atlas-button">Explore pay evidence for this provider</NuxtLink><StEvidenceTable :columns="timelineColumns" :rows="adverts" row-key="row_key" /><StEmptyState v-if="!adverts.length" title="No dated job adverts held in this profile" /></section>
      <section v-if="lens === 'history'" class="atlas-section"><h2>Dates and coverage periods</h2><p>Events below retain their source's date meaning. A filed financial year end, publication date and tribunal decision date describe different events.</p><NuxtLink :to="{ path: '/coverage', query: { lens: 'history', provider_key: key } }" class="atlas-button">View source coverage periods</NuxtLink></section>
      <StEvidenceState v-if="lens === 'overview' || lens === 'connections'" :pending="lineagePending" :error="lineageError" @retry="refreshLineage">
      <section v-if="lineage && (lineageEdges.length || lineageChain.length > 1 || lineageIdentifiers.length)" id="lineage" class="atlas-section"><div class="atlas-section-head"><h2>Verified identity lineage</h2><p>The administrative record of this organisation’s identity. It does not describe continuity of services, staff, or contracts.</p></div><div class="atlas-panel atlas-panel-body space-y-4"><StCaveat :text="lineage.caveat" /><p v-if="lineageChain.length > 1" class="text-sm">{{ lineageChain.map((node) => node.canonical_name ?? node.provider_key).join(' → ') }}</p><ul v-if="lineageEdges.length" class="list-disc pl-5 text-sm"><li v-for="(edge, index) in lineageEdges" :key="index">{{ edge.direction === 'predecessor' ? `${edge.canonical_name ?? edge.provider_key} ${edge.relationship ?? 'predecessor'} this entity` : `${edge.relationship ?? 'lifecycle change'} ${edge.canonical_name ?? edge.provider_key ?? ''}` }} <span class="opacity-60"> · {{ edge.basis }}</span></li></ul><p v-if="lineageIdentifiers.length" class="text-xs opacity-70">Verified identifiers: {{ lineageIdentifiers.map((item) => `${item.scheme} ${item.identifier}${item.role ? ` (${item.role})` : ''}`).join(' · ') }}</p></div></section>

      </StEvidenceState>
      <section v-if="lens === 'connections'" id="graph" class="atlas-section"><div class="atlas-section-head"><h2>Recorded identity links</h2><p>Other entity edges held for this provider. Name matches remain labelled as such and are not treated as verified relationships.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="edgeColumns" :rows="edgeRows" row-key="row_key" /><StEmptyState v-if="!edgeRows.length" title="No entity links held" /><StCaveat :text="caveat('cqc_coverage')" /></div></section>

      <section v-if="lens === 'history'" id="timeline" class="atlas-section"><div class="atlas-section-head"><h2>Evidence timeline</h2><p>{{ events.length }} dated records, oldest first. Contract events link to the published notice where available.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="timelineColumns" :rows="timelineRows" row-key="row_key" /><StEmptyState v-if="!timelineRows.length" title="No dated evidence" /></div></section>

      <section v-if="lens === 'registrations'" id="cqc" class="atlas-section"><div class="atlas-section-head"><h2>CQC registrations</h2><p>{{ locations.length }} registered locations held for this provider.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="locationColumns" :rows="locationRows" row-key="row_key" /><StEmptyState v-if="!locationRows.length" title="No CQC locations" /><StCaveat :text="caveat('cqc_coverage')" /></div></section>
      <section v-if="lens === 'registrations'" id="cqc-reports" class="atlas-section"><div class="atlas-section-head"><h2>CQC inspection history</h2><p>{{ inspections.length }} published inspection reports across the registered locations.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="inspectionColumns" :rows="inspectionRows" row-key="row_key" /><StEmptyState v-if="!inspectionRows.length" title="No CQC inspection reports" /><StCaveat :text="caveat('cqc_inspection_dates')" /></div></section>

      <section v-if="lens === 'finance-pay'" id="finance" class="atlas-section"><div class="atlas-section-head"><h2>Charity finance</h2><p>Filed accounts keep income, expenditure and government income in their original fields.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="financeColumns" :rows="financeRows" row-key="row_key" /><StEmptyState v-if="!financeRows.length" title="No charity financials" /><StCaveat :text="caveat('charity_share')" /></div></section>

      <section v-if="lens === 'finance-pay'" id="disclosure" class="atlas-section"><div class="atlas-section-head"><h2>Annual report disclosure</h2><p>Search results by topic and year. A non-match is a prompt to check the report, not proof that a topic was absent.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="disclosureColumns" :rows="disclosureRows" row-key="row_key" /><StEmptyState v-if="!disclosureRows.length" title="No topic search results held" /><h3 v-if="unsearchedReports.length">Reports not searched</h3><StEvidenceTable v-if="unsearchedReports.length" :columns="[{ key: 'financial_year_end', label: 'Year end' }, { key: 'document_url', label: 'Report', link: true }]" :rows="unsearchedReports" row-key="row_key" /></div></section>
      <section v-if="lens === 'finance-pay'" id="filings" class="atlas-section"><div class="atlas-section-head"><h2>Company filing history</h2><p>{{ filings.length }} Companies House filing records held.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="filingColumns" :rows="filingRows" row-key="row_key" /><StEmptyState v-if="!filingRows.length" title="No company filings" /><StCaveat :text="caveat('filing_records')" /></div></section>

      <section v-if="lens === 'safety-legal'" id="pfd" class="atlas-section"><div class="atlas-section-head"><h2>Coroners' reports mentioning this provider</h2><p>Sent to the provider and named in report text remain separate match types.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="pfdColumns" :rows="pfdRows" row-key="row_key" /><StEmptyState v-if="!pfdRows.length" title="No PFD mentions" /><StCaveat :text="caveat('pfd_mentions')" /></div></section>
      <section v-if="lens === 'safety-legal'" id="tribunals" class="atlas-section"><div class="atlas-section-head"><h2>Employment tribunal cases</h2><p>{{ tribunals.length }} judgments naming this provider.</p></div><div class="atlas-panel atlas-panel-body"><StEvidenceTable :columns="tribunalColumns" :rows="tribunalRows" row-key="row_key" /><StEmptyState v-if="!tribunalRows.length" title="No tribunal cases" /><StCaveat :text="caveat('tribunal_component')" /></div></section>
      </template>
    </StEvidenceState>
  </section>
</template>
