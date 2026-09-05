<script setup lang="ts">
import { computed } from 'vue'
import type { ContractNotice, ContractsResponse, MetaResponse, SummaryResponse } from '~/types/api'

// The landing page is deliberately data-rich. The first Nuxt prototype kept
// only four summary cards, which made the new portal look empty even though
// the legacy page already had the evidence briefing, verification funnel,
// freshness panels, explore index, and largest-notices context. These sections
// consume the same public API payloads and keep each evidence layer separate.
interface FreshnessRow {
  label: string
  table_name?: string
  retrieved_at: string | null
}
interface FreshnessResponse {
  tables: FreshnessRow[]
  caveat: string | null
}
interface ContractRollup extends ContractsResponse {
  value_concentration?: {
    median_value_gbp?: number | null
    mean_value_gbp?: number | null
    notices_over_1bn?: number | null
    share_over_1bn?: number | null
  }
  largest_matched_to_provider?: ContractNotice[]
}

const api = usePublicApi()

const { data: summary, pending, error } = await useAsyncData<SummaryResponse | null>(
  'public-summary', () => api.summary(), { default: () => null },
)
const { data: meta } = await useAsyncData<MetaResponse | null>(
  'public-meta', () => api.meta(), { default: () => null },
)
const { data: freshness } = await useAsyncData<FreshnessResponse | null>(
  'public-freshness', () => api.get<FreshnessResponse>('/freshness'), { default: () => null },
)
const { data: contracts } = await useAsyncData<ContractRollup | null>(
  'public-overview-contracts', () => api.contracts({ query: { limit: 10 } }), { default: () => null },
)

const sourceLabels: Record<string, string> = {
  contracts_finder: 'Contracts Finder',
  contracts_finder_csv_archive: 'Contracts Finder (historical CSV archive)',
  dhsc_public_health_grant: 'DHSC public health grant',
  find_a_tender: 'Find a Tender',
  ohid_fingertips: 'OHID Fingertips',
  ons_open_geography_portal: 'ONS geography portal',
}
const funnelStages = [['discovered', 'discovered'], ['undecided', 'undecided'], ['promoted', 'promoted'], ['evidence_rows', 'evidence rows']] as const

const explore = [
  ['/pay', 'Pay & benchmarks', 'Follow the workforce story from published pay to labour-market context.'],
  ['/contracts', 'Funding & contracts', 'See buyers, providers, notice values, and procurement patterns.'],
  ['/geography', 'Places', 'Choose a metric, explore local evidence, and open an authority page.'],
  ['/providers', 'Providers', 'Browse provider evidence across pay, contracts, claims, and safety.'],
  ['/treatment', 'Treatment data', 'Understand demand and activity figures with their uncertainty and limits.'],
  ['/pfd', 'Safety & legal', 'Explore coroners’ reports, concerns, and provider mentions responsibly.'],
  ['/claims', 'Evidence-backed claims', 'Find campaign-ready claims with the evidence behind them.'],
  ['/documents', 'Document search', 'Search published committee papers and partnership documents.'],
] as const

const metrics = computed(() => {
  const workforce = summary.value?.workforce as (SummaryResponse['workforce'] & {
    metrics?: Array<{ metric?: string; value?: number | null; unit?: string; verified?: number }>
  }) | undefined
  return workforce?.metrics ?? []
})

function number(value: unknown): string {
  return value === null || value === undefined || value === '' ? '—' : Number(value).toLocaleString('en-GB')
}
function money(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  return Number(value).toLocaleString('en-GB', { style: 'currency', currency: 'GBP', maximumFractionDigits: 0 })
}
function ago(stamp: string | null | undefined): string {
  if (!stamp) return 'never'
  const days = Math.max(0, Math.round((Date.now() - new Date(stamp).getTime()) / 86400000))
  return days === 0 ? 'today' : `${days}d ago`
}
function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${(value * 100).toFixed(1)}%`
}
function workforceValue(metric: string): string {
  const row = metrics.value.find((item) => item.metric === metric)
  return row?.value === null || row?.value === undefined ? '—' : `${row.value}${row.unit === 'percent' ? '%' : ''}`
}
function workforceVerified(metric: string): boolean {
  return metrics.value.find((item) => item.metric === metric)?.verified === 1
}

useHead({
  title: 'SectorTrace — Overview',
  meta: [{ name: 'description', content: 'Public-domain evidence for the substance misuse sector: providers, authorities, contracts, workforce, and treatment.' }],
})
</script>

<template>
  <section v-if="pending" class="atlas-panel p-6">Loading the latest evidence snapshot…</section>
  <section v-else-if="error || !summary" class="atlas-panel p-6">Overview figures are unavailable.</section>
  <template v-else>
    <section class="atlas-hero">
      <div>
        <div class="atlas-kicker">Accountability · England-wide evidence desk</div>
        <h1>Evidence for fair pay in England’s drug and alcohol treatment sector</h1>
        <p class="atlas-lede">Explore published evidence about pay, commissioning, providers, treatment activity, and workforce conditions. Every figure links to its source, retrieval date, and caveats; missing values are never guessed.</p>
        <div class="atlas-actions">
          <NuxtLink to="/coverage" class="atlas-button primary">How evidence is handled</NuxtLink>
          <NuxtLink to="/catalogue" class="atlas-button">Browse the catalogue</NuxtLink>
        </div>
        <details class="atlas-read-first">
          <summary>Read this first</summary>
          <p>This is a map of the evidence held by the portal, not a single scorecard. Pay, contracts, treatment activity, workforce figures, and safety evidence remain separate layers.</p>
          <p>A status such as unverified, not collected, or unavailable describes the evidence state. It does not mean zero.</p>
        </details>
      </div>
      <div class="atlas-hero-aside" aria-label="Coverage by region">
        <div v-for="region in summary.authorities.regions.slice(0, 3)" :key="String(region.region)" class="atlas-region">
          <strong>{{ number(region.authorities_with_contracts) }}/{{ number(region.authorities_total) }}</strong>
          <span>{{ region.region }} authorities appearing as contract buyers</span>
        </div>
      </div>
    </section>

    <section class="atlas-section">
      <div class="atlas-strip" aria-label="Evidence briefing">
        <div><strong>{{ number(summary.funnel?.evidence_rows) }}</strong><span> verified evidence rows</span></div>
        <div><strong>{{ number(summary.contracts.total_notices) }}</strong><span> procurement notices indexed</span></div>
        <div><strong>{{ number(summary.providers.total) }}</strong><span> providers tracked</span></div>
        <div><strong>{{ number(summary.contracts.matched_to_provider) }}</strong><span> matched to a known provider</span></div>
      </div>
      <p class="atlas-footnote mt-3">Scope: England-wide public evidence. Latest source retrieval: {{ summary.pipeline?.last_run ? String(summary.pipeline.last_run).slice(0, 10) : 'not available' }}. Coverage counts describe what is held and reviewed, not the quality or outcome of a service.</p>
    </section>

    <section class="atlas-section">
      <div class="atlas-section-head"><h2>Current snapshot</h2><p>A quick view of the evidence held today. These figures describe coverage and publication state; they are not a composite score.</p></div>
      <div class="atlas-panel atlas-panel-body">
        <div class="atlas-band"><h3>Coverage</h3><p>What the portal currently tracks across places, notices, and providers.</p><div class="atlas-grid">
          <div class="atlas-stat"><div class="atlas-stat-value">{{ number(summary.authorities.total) }}</div><div class="atlas-stat-label">local authorities tracked</div><div class="atlas-stat-sub">{{ number(summary.authorities.with_contracts) }} appear as a contract buyer</div></div>
          <div class="atlas-stat"><div class="atlas-stat-value">{{ number(summary.contracts.total_notices) }}</div><div class="atlas-stat-label">procurement notices indexed</div><div class="atlas-stat-sub">award and contract notices matching the sector keyword set</div></div>
          <div class="atlas-stat"><div class="atlas-stat-value">{{ number(summary.providers.total) }}</div><div class="atlas-stat-label">providers tracked</div><div class="atlas-stat-sub">Campaign subject: {{ summary.providers.target ?? '—' }}</div></div>
        </div></div>
        <div class="atlas-band"><h3>Evidence quality</h3><p>What has been reviewed and which values need careful interpretation.</p><div class="atlas-grid">
          <div class="atlas-stat"><div class="atlas-stat-value">{{ number(summary.funnel?.evidence_rows) }}</div><div class="atlas-stat-label">human-verified evidence rows</div><div class="atlas-stat-sub">documents promoted into the evidence base after review</div></div>
          <div class="atlas-stat"><div class="atlas-stat-value">{{ summary.contracts.value_is_concentrated ? 'not a total' : money(summary.contracts.total_value_gbp) }}</div><div class="atlas-stat-label">contract value</div><div class="atlas-stat-sub">{{ summary.contracts.value_is_concentrated ? 'dominated by framework ceilings — see Contracts' : 'published notice values' }}</div></div>
        </div><p class="atlas-caveat mt-4"><span aria-hidden="true">⚠</span> {{ summary.contracts.sum_caveat }}</p></div>
        <div class="atlas-band"><h3>Sector context</h3><p>Published workforce context, kept separate from the coverage counts above.</p><div class="atlas-grid">
          <div class="atlas-stat"><div class="atlas-stat-value" :class="{ 'text-amber-400': !workforceVerified('vacancy_rate') }">{{ workforceValue('vacancy_rate') }}</div><div class="atlas-stat-label">sector vacancy rate ({{ summary.workforce.latest_census_year ?? '—' }})</div><div class="atlas-stat-sub">{{ workforceVerified('vacancy_rate') ? 'Human-verified' : 'Unverified' }}</div></div>
          <div class="atlas-stat"><div class="atlas-stat-value" :class="{ 'text-amber-400': !workforceVerified('turnover_rate') }">{{ workforceValue('turnover_rate') }}</div><div class="atlas-stat-label">sector turnover rate ({{ summary.workforce.latest_census_year ?? '—' }})</div><div class="atlas-stat-sub">{{ workforceVerified('turnover_rate') ? 'Human-verified' : 'Unverified' }}</div></div>
          <div class="atlas-stat"><div class="atlas-stat-value">{{ summary.fingertips.latest_period ?? '—' }}</div><div class="atlas-stat-label">Fingertips period</div><div class="atlas-stat-sub">{{ number(summary.fingertips.indicators_collected) }} indicators collected</div></div>
        </div><p class="atlas-caveat mt-4"><span aria-hidden="true">⚠</span> {{ summary.workforce.caveat }}</p></div>
      </div>
    </section>

    <section class="atlas-section"><div class="atlas-section-head"><h2>Explore the evidence</h2><p>Choose a question to move from the snapshot into the evidence layer that can answer it.</p></div><div class="atlas-explore-grid">
      <NuxtLink v-for="item in explore" :key="item[0]" :to="item[0]" class="atlas-explore-card"><strong>{{ item[1] }}</strong><span>{{ item[2] }}</span><span aria-hidden="true">Open layer →</span></NuxtLink>
    </div></section>

    <section class="atlas-section"><div class="atlas-section-head"><h2>Evidence status</h2><p>Where the evidence comes from, how much has been verified, and when each source layer was last written.</p></div><div class="atlas-status-grid">
      <div class="atlas-panel atlas-panel-body"><h3>Sources and latest updates</h3><div class="atlas-source-list mt-3"><div v-for="source in (summary.pipeline?.sources ?? [])" :key="String(source.source_system)" class="atlas-source"><b>{{ sourceLabels[String(source.source_system)] ?? source.source_system }}</b><span>{{ ago(source.last_retrieved as string | null) }}</span></div></div><p class="atlas-footnote mt-4">Fingertips: {{ number(summary.fingertips.indicators_collected) }} indicators, latest period {{ summary.fingertips.latest_period ?? '—' }}.</p></div>
       <div class="atlas-panel atlas-panel-body"><h3>From candidate to evidence</h3><p class="atlas-footnote">How much of what the modules found has been verified by a person.</p><div class="atlas-flow mt-4"><div v-for="stage in funnelStages" :key="stage[0]" class="atlas-flow-row"><div class="atlas-flow-label"><span>{{ stage[1] }}</span><b>{{ number((summary.funnel as Record<string, unknown>)[stage[0]]) }}</b></div><div class="atlas-flow-bar"><div class="atlas-flow-fill" :style="{ width: `${Math.min(100, Number((summary.funnel as Record<string, unknown>)[stage[0]] ?? 0) / Math.max(1, Number(summary.funnel?.discovered ?? 1)) * 100)}%` }" /></div></div></div><p class="atlas-caveat mt-4"><span aria-hidden="true">⚠</span> {{ summary.funnel?.caveat }}</p></div>
      <div class="atlas-panel atlas-panel-body"><h3>Freshness</h3><p class="atlas-footnote">Days since each source table was last written. Never collected is shown as “never”, not zero.</p><div class="atlas-flow mt-4"><div v-for="table in (freshness?.tables ?? [])" :key="table.table_name ?? table.label" class="atlas-flow-row"><div class="atlas-flow-label"><span>{{ table.label }}</span><b>{{ ago(table.retrieved_at) }}</b></div><div class="atlas-flow-bar"><div class="atlas-flow-fill" :class="{ never: !table.retrieved_at }" :style="{ width: table.retrieved_at ? '100%' : '18%' }" /></div></div></div></div>
    </div></section>

     <section v-if="contracts?.largest_matched_to_provider?.length" class="atlas-section"><div class="atlas-section-head"><h2>The largest notices in the corpus</h2><p>Five highest published values matched to a tracked provider by exact supplier name. Read the caveats before treating any of these as sector spend.</p></div><div class="atlas-panel atlas-panel-body"><p class="atlas-caveat"><span aria-hidden="true">⚠</span> {{ contracts.caveats?.value_sum ?? summary.contracts.sum_caveat }}</p><p class="atlas-footnote mt-3">Corpus-wide: median notice {{ money(contracts.value_concentration?.median_value_gbp) }} · mean {{ money(contracts.value_concentration?.mean_value_gbp) }} · {{ number(contracts.value_concentration?.notices_over_1bn) }} notices above £1bn carry {{ pct(contracts.value_concentration?.share_over_1bn) }} of the total.</p><div class="atlas-notice-list mt-3"><div v-for="notice in contracts.largest_matched_to_provider.slice(0, 5)" :key="String(notice.notice_id ?? notice.title ?? 'notice')" class="atlas-notice"><div><strong>{{ notice.canonical_name ?? notice.supplier_name_raw ?? 'Provider not published' }}</strong><small>{{ notice.buyer_name ?? 'Buyer not published' }} · {{ notice.title ?? 'Untitled notice' }}</small></div><span class="atlas-notice-value">{{ money(notice.value_core) }}</span></div></div><p class="atlas-footnote mt-3">Matching is a floor. A notice may cover several years, several lots, or a framework nobody ever called off.</p></div></section>

    <section v-if="meta" class="atlas-section atlas-panel atlas-panel-body"><div class="atlas-eyebrow">Release identity</div><div class="atlas-grid mt-3"><div class="atlas-stat"><div class="atlas-stat-label">Build</div><div class="atlas-stat-sub font-mono">{{ meta.revision ?? '—' }}</div></div><div class="atlas-stat"><div class="atlas-stat-label">Schema</div><div class="atlas-stat-sub font-mono">{{ meta.schema.latest_migration ?? '—' }}</div></div><div class="atlas-stat"><div class="atlas-stat-label">Last fetch</div><div class="atlas-stat-sub font-mono">{{ meta.data.last_fetch_at ?? '—' }}</div></div></div></section>
  </template>
</template>
