<script setup lang="ts">
import { computed, ref } from 'vue'
const api = usePublicApi()
const filters = useFilterState()
const provider = computed(() => String(filters.get('provider_key') ?? ''))
const authority = computed(() => String(filters.get('ons_code') ?? ''))
const lens = computed(() => String(filters.get('lens') ?? (provider.value || authority.value ? 'history' : 'guide')))
const kind = ref<'provider' | 'authority'>(authority.value ? 'authority' : 'provider')
const validEntity = computed(() => Boolean(provider.value) !== Boolean(authority.value))
const { data, pending, error, refresh } = await useAsyncData('public-coverage-history', (_app, { signal }) => lens.value === 'history' && validEntity.value ? api.coverage({ query: { provider_key: provider.value || undefined, ons_code: authority.value || undefined }, signal }) : Promise.resolve(null), { watch: [provider, authority, lens] })
interface Freshness { tables: Array<{ label: string; table_name?: string; retrieved_at: string | null }>; caveat?: string | null }
const freshness = await useAsyncData('public-coverage-freshness', (_app, { signal }) => lens.value === 'freshness' ? api.get<Freshness>('/freshness', { signal }) : Promise.resolve(null), { watch: [lens] })
function choose(id: string) { return filters.setAll({ lens: 'history', [kind.value === 'provider' ? 'provider_key' : 'ons_code']: id || undefined }) }
useHead({ title: 'Evidence coverage · SectorTrace' })
</script>
<template>
  <section class="space-y-6">
    <header class="st-page-header"><p class="atlas-eyebrow">Evidence coverage</p><h1>{{ lens === 'history' ? 'Coverage history' : lens === 'freshness' ? 'Source freshness' : 'Coverage guide' }}</h1><p>Understand what is held, where it came from and what it can establish.</p></header>
    <StCoverageNav />
    <template v-if="lens === 'history'">
      <div class="st-history-controls"><label>Entity type<select v-model="kind"><option value="provider">Provider</option><option value="authority">Authority</option></select></label><StEntityPicker :kind="kind" :model-value="kind === 'provider' ? provider : authority" @update:model-value="choose" /></div>
      <p v-if="provider && authority" role="status">This link selects both a provider and an authority. Choose one entity to view its coverage.</p>
      <p v-else-if="!validEntity">Choose an entity to see its held source periods.</p>
      <StEvidenceState v-else :pending="pending" :error="error" :empty="!data?.sources?.length" @retry="refresh">
        <h2>{{ data?.entity?.name ?? data?.entity?.id }}</h2><StCaveat :text="data?.caveat" /><p class="atlas-footnote">{{ data?.note }}</p>
        <div class="st-table-scroll" tabindex="0" role="region" aria-label="Held periods by source"><table class="st-coverage-table"><caption>Source-specific coverage periods</caption><thead><tr><th scope="col">Source</th><th scope="col">Period kind</th><th scope="col">Periods held</th><th scope="col">Evidence</th></tr></thead><tbody><tr v-for="source in data?.sources ?? []" :key="source.dataset_id"><th scope="row">{{ source.title }}</th><td>{{ source.period_kind ?? 'Not supplied' }}</td><td><span v-if="source.held">{{ source.periods.join(', ') }}</span><span v-else>No periods held in this response</span></td><td><StResearchLink v-if="source.link" :href="source.link">Open evidence</StResearchLink><span v-else>Not supplied</span></td></tr></tbody></table></div>
      </StEvidenceState>
    </template>
    <template v-else-if="lens === 'freshness'">
      <p>These dates describe recorded retrievals. They do not establish publication dates, current source availability or complete collection.</p>
      <StEvidenceState :pending="freshness.pending.value" :error="freshness.error.value" :empty="!freshness.data.value?.tables?.length" @retry="freshness.refresh()"><div class="st-table-scroll" tabindex="0" role="region" aria-label="Recorded source retrievals"><table class="st-coverage-table"><caption>Latest retrieval recorded by source table</caption><thead><tr><th scope="col">Source</th><th scope="col">Retrieved</th></tr></thead><tbody><tr v-for="row in freshness.data.value?.tables ?? []" :key="row.table_name ?? row.label"><th scope="row">{{ row.label }}</th><td>{{ row.retrieved_at ?? 'Not supplied in this response' }}</td></tr></tbody></table></div><StCaveat :text="freshness.data.value?.caveat" /></StEvidenceState>
    </template>
    <article v-else class="st-prose"><p v-if="lens !== 'guide'" role="status">The requested coverage view is unavailable. The guide is shown below.</p><h2>Evidence held and evidence missing</h2><p>SectorTrace records published evidence collected for England's substance misuse sector. A source may be absent because it has not been collected, could not be parsed or does not cover the selected entity. A blank is not zero and does not prove that an event never occurred.</p><h2>Keep each source in context</h2><p>Pay, charity finance, contracts, treatment activity and legal records describe different populations and periods. They are not combined into provider scores, staffing ratios or sector spending totals.</p><p>Procurement notice values may be estimates or framework ceilings. They are not payments or provider revenue. Charity wage-per-head observations are not average salaries. Advertised hourly pay is not converted into annual pay.</p><h2>Sources and provenance</h2><p>Source details show the URL, dates, identifiers and exact content hash when those fields are supplied by the public response. Missing metadata is stated explicitly. A source link's latest recorded retrieval does not establish the identity of older archived bytes.</p><h2>Dates and uncertainty</h2><p>Observation periods, publication dates and retrieval dates have different meanings. Published confidence intervals and suppression markers stay with their observations. Historical authority identities are not silently combined with successors.</p><h2>Using the coverage views</h2><p>Use the catalogue for source definitions and licences, history for an entity's held periods, freshness for recorded retrievals, and the publication calendar for stated schedules and observed patterns. Recorded changes describe the warehouse's observations.</p><div class="atlas-actions"><NuxtLink to="/providers" class="atlas-button">Find a provider</NuxtLink><NuxtLink to="/authorities" class="atlas-button">Find an authority</NuxtLink><NuxtLink to="/about" class="atlas-button">About the project</NuxtLink></div></article>
  </section>
</template>
