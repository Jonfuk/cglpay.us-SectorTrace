<script setup lang="ts">
import { onMounted, ref } from 'vue'
interface FreshnessResponse { tables: Array<{ label: string; retrieved_at: string | null }>; caveat?: string }
const api = usePublicApi()
const { data: freshness, error: freshnessError } = await useAsyncData('public-home-freshness', () => api.get<FreshnessResponse>('/freshness'))
const mapVisible = ref(false)
onMounted(() => { mapVisible.value = true })
const filters = useFilterState()
const inspectId = computed(() => String(filters.get('inspect') ?? ''))
const inspectName = ref('')
watch(inspectId, () => { inspectName.value = '' })
const categories = [
  ['/contracts', 'Contracts and payments', 'Read procurement notices, processes and published council payments.'],
  ['/pay', 'Pay and workforce', 'Inspect advertised pay, charity accounts and published workforce evidence.'],
  ['/treatment', 'Treatment', 'Choose a published measure and read its definition and uncertainty.'],
  ['/cqc', 'CQC registrations', 'Locate registered premises and inspect their source records.'],
  ['/pfd', 'Safety and legal', 'Read reports and cases in their separate source contexts.'],
  ['/documents', 'Documents', 'Search public committee papers and Community Drug Partnership documents.'],
] as const
useHead({ title: 'SectorTrace · Evidence for England’s substance misuse sector', meta: [{ name: 'description', content: 'Find providers, authorities and published evidence about England’s drug and alcohol treatment sector.' }] })
</script>
<template>
  <div>
  <div class="st-home-workspace" :class="{ 'has-inspector': inspectId }">
  <section class="st-home-entry">
    <div class="st-home-search"><p class="atlas-eyebrow">England's substance misuse sector</p><h1>Find sector evidence</h1><p>Start with a provider, an authority or a document. Follow the published records and check their sources.</p><StSearchForm /><div class="atlas-actions"><NuxtLink to="/providers">Browse providers</NuxtLink><NuxtLink to="/authorities">Browse authorities</NuxtLink></div></div>
    <section class="st-home-map" aria-label="Authority locator"><div class="st-map-heading"><h2>Locate an authority</h2><NuxtLink to="/authorities">Use the directory</NuxtLink></div><LazyGeographyMap v-if="mapVisible" :features="[]" :selected="inspectId" locator @select="code => filters.set('inspect', code)" /><p class="atlas-footnote">Authority boundaries for orientation. No metric or ranking is selected.</p></section>
  </section>
  <StInspector v-if="inspectId" :title="inspectName || `Authority ${inspectId}`" @close="filters.set('inspect', undefined)"><LazyStAuthorityInspectorContent :code="inspectId" @identity="value => inspectName = value" /></StInspector>
  </div>
  <section class="atlas-section"><header class="atlas-section-head"><h2>Explore the evidence</h2><p>Each source has its own scope, period and limitations.</p></header><div class="atlas-explore-grid"><NuxtLink v-for="[to, label, description] in categories" :key="to" :to="to" class="atlas-explore-card"><strong>{{ label }}</strong><span>{{ description }}</span></NuxtLink></div></section>
  <section class="atlas-section st-home-coverage"><div><h2>Evidence coverage</h2><p>Coverage describes the records held here. Missing records do not establish that an event never occurred.</p><div class="atlas-actions"><NuxtLink to="/coverage">Read the coverage guide</NuxtLink><NuxtLink to="/catalogue">Dataset catalogue</NuxtLink><NuxtLink to="/calendar">Publication calendar</NuxtLink></div></div><div><h3>Recorded retrievals</h3><p v-if="freshnessError" class="atlas-footnote">Retrieval information is unavailable.</p><ul v-else-if="freshness?.tables?.length" class="st-freshness-list"><li v-for="row in freshness.tables.slice(0, 4)" :key="row.label"><span>{{ row.label }}</span><span>{{ row.retrieved_at?.slice(0, 10) ?? 'Not supplied' }}</span></li></ul><p v-else class="atlas-footnote">No retrieval information is currently available.</p><p class="atlas-footnote">Retrieval dates describe recorded fetches, not publication dates or completeness.</p></div></section>
  </div>
</template>
