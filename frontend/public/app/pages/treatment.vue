<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { TreatmentMetric, TreatmentResponse } from '~/types/api'

interface AuthorityOption { ons_code: string; name: string; region: string | null }
interface AuthoritiesResponse { authorities: AuthorityOption[] }
interface FingertipsIndicator { indicator_id: number; indicator_name: string; topic: string; unit: string | null; source_url: string | null; retrieved_at: string | null }
interface FingertipsSeriesRow { indicator_id: number; ons_code: string; authority_name: string | null; time_period: string | null; value: number | null; lower_ci_95: number | null; upper_ci_95: number | null; value_note: string | null; [key: string]: unknown }
interface FingertipsResponse { indicators: FingertipsIndicator[]; series: FingertipsSeriesRow[]; [key: string]: unknown }
interface NdtmsDataset { table_ref: string; rows: number; authorities: number; publications: number; label: string }
interface NdtmsEstimate { dataset: string | null; measure: string | null; time_period: string | null; value: number | null; value_text: string | null; lower: number | null; upper: number | null; published_in: string | null; has_interval: boolean; [key: string]: unknown }
interface NdtmsResponse { datasets: NdtmsDataset[]; estimates?: NdtmsEstimate[]; other_rows?: NdtmsEstimate[]; authority?: { name: string | null } | null; caveats?: { estimates?: string | null; coverage?: string | null }; [key: string]: unknown }
interface TreatmentWorkspace { metrics: TreatmentResponse; authorities: AuthoritiesResponse; fingertips: FingertipsResponse; ndtms: NdtmsResponse }

const api = usePublicApi()
const filters = useFilterState()
const topic = computed(() => String(filters.get('topic') || 'numbers_in_treatment'))
const authorityCode = computed(() => {
  const value = filters.get('ons_code')
  return Array.isArray(value) ? value[0] : value
})
const metricSearch = ref('')

const { data, pending, error } = await useDataRoute<TreatmentWorkspace>(
  'public-treatment-workspace',
  async (f) => {
    const selectedTopic = typeof f.topic === 'string' && f.topic ? f.topic : 'numbers_in_treatment'
    const selectedAuthority = typeof f.ons_code === 'string' ? f.ons_code : undefined
    const [metrics, authorities, fingertips, ndtms] = await Promise.all([
      api.treatment(),
      api.get<AuthoritiesResponse>('/authorities'),
      api.get<FingertipsResponse>('/fingertips', { query: { topic: selectedTopic, ons_code: selectedAuthority } }),
      api.get<NdtmsResponse>('/ndtms', { query: { ons_code: selectedAuthority } }),
    ])
    return { metrics, authorities, fingertips, ndtms }
  },
)

const topics = [
  ['numbers_in_treatment', 'Numbers in treatment'],
  ['successful_completions', 'Successful completions'],
  ['waiting_times', 'Waiting times'],
  ['prevalence', 'Prevalence'],
  ['treatment_need', 'Treatment need'],
  ['harm', 'Harm'],
] as const
const metrics = computed(() => data.value?.metrics.metrics ?? [])
const filteredMetrics = computed(() => {
  const q = metricSearch.value.trim().toLowerCase()
  if (!q) return metrics.value
  return metrics.value.filter((metric) => `${metric.name ?? ''} ${metric.topic ?? ''} ${metric.unit ?? ''} ${metric.definition ?? ''}`.toLowerCase().includes(q))
})
const authorities = computed(() => data.value?.authorities.authorities ?? [])
const indicators = computed(() => data.value?.fingertips.indicators ?? [])
const series = computed(() => data.value?.fingertips.series ?? [])
const ndtmsDatasets = computed(() => data.value?.ndtms.datasets ?? [])
const ndtmsEstimates = computed(() => data.value?.ndtms.estimates ?? [])

const metricColumns: Column<TreatmentMetric>[] = [
  { key: 'name', label: 'Metric' }, { key: 'substance', label: 'Substance' }, { key: 'unit', label: 'Unit' },
  { key: 'period_count', label: 'Periods', numeric: true }, { key: 'authority_count', label: 'Authorities', numeric: true },
  { key: 'has_confidence_interval', label: '95% CI' },
]
const seriesColumns: Column<FingertipsSeriesRow>[] = [
  { key: 'indicator_name', label: 'Indicator' }, { key: 'authority_name', label: 'Authority' },
  { key: 'time_period', label: 'Period', mono: true }, { key: 'value', label: 'Published value', numeric: true },
  { key: 'lower_ci_95', label: 'Lower 95% CI', numeric: true }, { key: 'upper_ci_95', label: 'Upper 95% CI', numeric: true },
]
const ndtmsColumns: Column<NdtmsEstimate>[] = [
  { key: 'dataset', label: 'Dataset' }, { key: 'measure', label: 'Measure' }, { key: 'time_period', label: 'Period', mono: true },
  { key: 'published_in', label: 'Publication' }, { key: 'value_text', label: 'Published as' },
]

function chooseTopic(value: string): void { void filters.set('topic', value) }
function chooseAuthority(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  void filters.set('ons_code', value || undefined)
}
function seriesRows(): FingertipsSeriesRow[] {
  const names = new Map(indicators.value.map((row) => [row.indicator_id, row.indicator_name]))
  return series.value.map((row) => ({ ...row, indicator_name: names.get(row.indicator_id) ?? `Indicator ${row.indicator_id}` }))
}

useHead({ title: 'SectorTrace — Treatment data' })
</script>

<template>
  <section class="space-y-8">
    <div class="atlas-hero">
      <div>
        <p class="atlas-kicker">Service access · published indicators</p>
        <h1>Understand treatment data</h1>
        <p class="atlas-lede">Explore published treatment indicators by local authority and against the England figure. Demand, activity and outcomes remain separate measures.</p>
        <div class="atlas-actions"><a class="atlas-button primary" href="#treatment-explorer">Explore the indicators</a><a class="atlas-button" href="#treatment-catalogue">Read the catalogue</a></div>
      </div>
      <div class="atlas-hero-aside">
        <div class="atlas-region"><strong>{{ data?.metrics.count ?? '—' }}</strong><span>published treatment metrics</span></div>
        <div class="atlas-region"><strong>{{ data?.fingertips.series.length ? 'England + local' : '—' }}</strong><span>comparison context, where published</span></div>
      </div>
    </div>

    <details class="atlas-read-first" open>
      <summary>What treatment data can answer</summary>
      <p>The figures show published indicators and estimates. They cannot show unmet need by subtracting one measure from another.</p>
      <p>A blank, suppressed value, or missing confidence interval is not zero and is shown separately from a published value.</p>
    </details>

    <div v-if="pending" class="text-sm opacity-60">Loading treatment evidence…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <section id="treatment-explorer" class="atlas-section">
        <div class="atlas-section-head"><h2>Choose an indicator and authority</h2><p>Start with national context, then select an authority for its local series.</p></div>
        <div class="atlas-panel atlas-panel-body space-y-5">
          <div class="flex flex-wrap gap-2" role="tablist" aria-label="Treatment topics">
            <button v-for="item in topics" :key="item[0]" type="button" class="atlas-button" :class="topic === item[0] ? 'primary' : ''" :aria-pressed="topic === item[0]" @click="chooseTopic(item[0])">{{ item[1] }}</button>
          </div>
          <label class="block max-w-xl text-sm"><span class="block mb-1 opacity-70">Local authority</span><select class="w-full rounded border px-3 py-2" aria-label="Local authority" :value="authorityCode ?? ''" @change="chooseAuthority"><option value="">All authorities</option><option v-for="authority in authorities" :key="authority.ons_code" :value="authority.ons_code">{{ authority.name }}{{ authority.region ? ` · ${authority.region}` : '' }}</option></select></label>
          <div class="atlas-caveat"><span>What must not be computed here</span> — prevalence and treatment numbers use different estimation methods and populations. This pipeline does not calculate unmet need by subtracting one from the other.</div>
          <div v-if="indicators.length" class="atlas-band"><h3>{{ indicators[0].indicator_name }}</h3><p>{{ indicators[0].unit || 'Unit published with the indicator' }} · {{ authorityCode ? 'Selected authority and England are shown.' : 'Authority values are shown with their published context.' }}</p></div>
          <StEvidenceTable v-if="seriesRows().length" :columns="seriesColumns" :rows="seriesRows()" row-key="indicator_id" />
          <StEmptyState v-else />
          <StCaveat v-if="data?.metrics.caveat" :text="data.metrics.caveat" />
        </div>
      </section>

      <section id="treatment-catalogue" class="atlas-section">
        <div class="atlas-section-head"><h2>Treatment metric catalogue</h2><p>Definitions, periods held, confidence-interval availability and authority coverage — before a chart.</p></div>
        <div class="atlas-panel atlas-panel-body space-y-4">
          <input v-model="metricSearch" type="search" class="w-full rounded border px-3 py-2" placeholder="Search metrics by name, unit or definition" aria-label="Search treatment metrics">
          <p class="text-sm opacity-70">{{ filteredMetrics.length }} of {{ metrics.length }} metrics</p>
          <StEvidenceTable v-if="filteredMetrics.length" :columns="metricColumns" :rows="filteredMetrics" row-key="key" />
          <StEmptyState v-else />
          <details v-for="metric in filteredMetrics" :key="`${metric.key}-definition`" class="border-t pt-3 text-sm"><summary class="cursor-pointer">{{ metric.name }} · {{ metric.source ?? 'published source' }}</summary><p class="mt-2 opacity-70">{{ metric.definition || 'No definition was supplied in the published catalogue.' }}</p><p class="opacity-70">{{ metric.period_count ? `${metric.period_count} periods` : 'No periods published' }} · {{ metric.authority_count.toLocaleString('en-GB') }} authorities · {{ metric.england_available ? 'England figure available' : 'England figure not held' }}</p><a v-if="metric.source_url" class="underline" :href="metric.source_url" target="_blank" rel="noopener noreferrer">Source ↗</a></details>
        </div>
      </section>

      <section class="atlas-section">
        <div class="atlas-section-head"><h2>NDTMS estimates</h2><p>Modelled estimates of opiate and crack use, alcohol dependency, and deaths in treatment, published with 95% confidence intervals.</p></div>
        <div class="atlas-panel atlas-panel-body space-y-4">
          <div class="atlas-caveat"><span>These are estimates, not counts</span> — published intervals and disclosure markers stay visible.</div>
          <p v-if="data?.ndtms.caveats?.coverage" class="text-sm opacity-70">{{ data.ndtms.caveats.coverage }}</p>
          <template v-if="authorityCode && ndtmsEstimates.length"><StEvidenceTable :columns="ndtmsColumns" :rows="ndtmsEstimates" row-key="dataset" /></template>
          <template v-else-if="ndtmsDatasets.length"><p class="text-sm">Choose an authority above to see its estimates. The catalogue currently holds data across {{ Math.max(...ndtmsDatasets.map((item) => item.authorities)).toLocaleString('en-GB') }} authorities.</p><StEvidenceTable :columns="[{ key: 'label', label: 'Publication' }, { key: 'rows', label: 'Values', numeric: true }, { key: 'authorities', label: 'Authorities', numeric: true }, { key: 'publications', label: 'Editions', numeric: true }]" :rows="ndtmsDatasets" row-key="table_ref" /></template>
          <StEmptyState v-else />
        </div>
      </section>
    </template>
  </section>
</template>
