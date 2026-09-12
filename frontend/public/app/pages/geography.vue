<script setup lang="ts">
import type { GeographyFeature, GeographyResponse } from '~/types/api'
import { atlasKeys, authorityObservations, validLocation, type AtlasLayer } from '~/lib/places'
type Row = Record<string, unknown>
interface Authority { ons_code: string; name: string; region?: string | null }
interface LayerPayload { key: string; features: Row[]; year?: string | number | null; years: string[]; caveats: string[]; unit?: string | null }
const api = usePublicApi()
const filters = useFilterState()
const metric = computed(() => String(filters.get('metric') ?? ''))
const year = computed(() => String(filters.get('year') ?? ''))
const search = computed({ get: () => String(filters.get('q') ?? ''), set: value => { void filters.set('q', value || undefined) } })
const inspectId = computed(() => String(filters.get('inspect') ?? ''))
const locationId = computed(() => String(filters.get('location_id') ?? ''))
const showMap = computed(() => filters.get('view') !== 'table' && filters.get('view') !== 'data')
const draft = ref(metric.value)
watch(metric, value => { draft.value = value })
const registry = await useAsyncData('public-atlas-registry', (_app, { signal }) => api.get<{ layers: AtlasLayer[] }>('/atlas_layers', { signal }))
const directory = await useAsyncData('places-authorities', (_app, { signal }) => api.get<{ authorities: Authority[] }>('/authorities', { signal }))
const layers = computed(() => (registry.data.value?.layers ?? []).filter(row => (atlasKeys as readonly string[]).includes(row.key)))
const active = computed(() => layers.value.find(row => row.key === metric.value))
const preview = computed(() => layers.value.find(row => row.key === draft.value))
const signature = computed(() => active.value ? `${active.value.key}:${active.value.kind === 'choropleth' && active.value.key !== 'contract_value' ? year.value : ''}` : '')
const { data, pending, error, refresh } = await useAsyncData<LayerPayload | null>('public-places-layer', async (_app, { signal }) => {
  const layer = active.value
  if (!layer) return null
  if (layer.kind === 'choropleth') {
    const result = await api.geography({ query: { metric: layer.key, year: layer.key !== 'contract_value' ? year.value || undefined : undefined }, signal }) as GeographyResponse & { available_years?: string[] }
    return { key: layer.key, features: result.features, year: result.year, years: result.available_years ?? [], caveats: [layer.caveat, result.caveat].filter((value): value is string => Boolean(value)), unit: result.unit }
  }
  const response = await api.get<{ layers: Record<string, { features: Row[]; caveats: string[] }> }>('/layers', { signal })
  const result = response.layers[layer.key]
  if (!result) throw new Error('Selected layer unavailable')
  return { key: layer.key, features: result.features, years: [], caveats: result.caveats, unit: layer.unit }
}, { watch: [signature] })
const current = computed(() => !pending.value && !error.value && data.value?.key === metric.value ? data.value : null)
const pointLayer = computed(() => active.value?.kind === 'points')
const features = computed<GeographyFeature[]>(() => pointLayer.value ? [] : (current.value?.features ?? []).map(row => ({ ...row, value: active.value?.key === 'coverage' ? row.kinds_held : row.value }) as GeographyFeature))
const observations = computed(() => authorityObservations(features.value))
const locations = computed(() => (current.value?.features ?? []).filter(validLocation))
const selectedLocation = computed(() => (current.value?.features ?? []).find(row => row.location_id === locationId.value))
const authorities = computed(() => {
  const rows = new Map((directory.data.value?.authorities ?? []).map(row => [row.ons_code, row]))
  for (const row of features.value) if (row.ons_code && !rows.has(row.ons_code)) rows.set(row.ons_code, { ons_code: row.ons_code, name: row.authority_name ?? row.ons_code, region: row.region })
  return [...rows.values()].sort((a, b) => a.name.localeCompare(b.name, 'en-GB'))
})
const selectedAuthority = computed(() => authorities.value.find(row => row.ons_code === inspectId.value))
const filteredAuthorities = computed(() => authorities.value.filter(row => `${row.name} ${row.ons_code}`.toLocaleLowerCase('en-GB').includes(search.value.toLocaleLowerCase('en-GB'))))
const filteredLocations = computed(() => (current.value?.features ?? []).filter(row => `${row.location_name ?? ''} ${row.location_id ?? ''}`.toLocaleLowerCase('en-GB').includes(search.value.toLocaleLowerCase('en-GB'))))
let trigger: HTMLElement | null = null
async function inspect(code: string, event?: Event) { trigger = event?.currentTarget as HTMLElement ?? null; await filters.setAll({ ...filters.all(), inspect: code, location_id: undefined }); await nextTick(); document.querySelector<HTMLElement>('.st-inspector-heading')?.focus() }
async function inspectLocation(id: string, event?: Event) { trigger = event?.currentTarget as HTMLElement ?? null; await filters.setAll({ ...filters.all(), location_id: id, inspect: undefined }); await nextTick(); document.querySelector<HTMLElement>('.st-inspector-heading')?.focus() }
async function close() { await filters.setAll({ ...filters.all(), inspect: undefined, location_id: undefined }); await nextTick(); trigger?.focus() }
function activate() { return filters.setAll({ ...filters.all(), metric: draft.value || undefined, year: undefined, location_id: undefined }) }
function value(value: unknown) { return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('en-GB') : 'Missing value' }
useHead({ title: 'Places · SectorTrace' })
</script>
<template>
  <section class="space-y-6">
    <header class="st-page-header"><p class="atlas-eyebrow">Explore</p><h1>Places</h1><p>Choose one evidence layer and inspect its published records. The starting map is a neutral authority locator.</p></header>
    <form class="st-place-controls" @submit.prevent="activate"><label>Evidence layer<select v-model="draft"><option value="">Authority locator</option><option v-for="layer in layers" :key="layer.key" :value="layer.key">{{ layer.label }}</option></select></label><button type="submit" class="atlas-button primary">Show layer</button><div role="group" aria-label="Places view"><button type="button" class="atlas-button" :aria-pressed="showMap" @click="filters.set('view', 'map')">Map</button><button type="button" class="atlas-button" :aria-pressed="!showMap" @click="filters.set('view', 'table')">Data</button></div></form>
    <StEvidenceState v-if="registry.error.value" :error="registry.error.value" @retry="registry.refresh()" />
    <div v-if="preview" class="st-layer-preview"><h2>{{ preview.label }}</h2><p>{{ preview.legend }}</p><p>Unit: {{ preview.unit }}. Periods are supplied by the selected layer after loading.</p><StCaveat :text="preview.caveat" /><p v-if="draft !== metric" class="atlas-footnote">Preview only. Select Show layer to apply this choice.</p></div>
    <p v-if="metric && !active && !registry.pending.value" role="status">The requested layer is unavailable. Choose a supported layer or the authority locator.</p>
    <div v-if="active" class="st-place-controls"><p><strong>Active layer: {{ active.label }}</strong><br>Unit: {{ current?.unit ?? active.unit }}<br>Period: {{ current?.year ?? (active.kind === 'choropleth' && active.key !== 'contract_value' ? 'Not supplied' : 'No single period supplied') }}</p><label v-if="current?.years.length">Source period<select :value="year || String(current.year ?? '')" @change="filters.set('year', ($event.target as HTMLSelectElement).value)"><option v-for="period in current.years" :key="period" :value="period">{{ period }}</option></select></label></div>
    <p v-if="year && (active?.kind !== 'choropleth' || active.key === 'contract_value')" class="atlas-footnote">The year in this link does not apply to this layer and is not sent to its request.</p>
    <StEvidenceState v-if="pending || error" :pending="pending" :error="error" @retry="refresh" />
    <StCaveat v-for="(caveat, index) in current?.caveats ?? []" :key="index" :text="caveat" />
    <p v-if="observations.ambiguous.length" role="status">{{ observations.ambiguous.length }} authorities have multiple returned observations. They remain listed individually and are not assigned a map value.</p>
    <div class="st-directory-workspace" :class="{ 'has-inspector': inspectId || locationId }"><div class="min-w-0">
      <GeographyMap v-if="showMap" :features="features" :locator="!current || pointLayer" :metric-label="active?.label" :selected="inspectId" :point-layer="pointLayer" :locations="pointLayer ? locations : []" :selected-location="locationId" @select="code => inspect(code)" @select-location="id => inspectLocation(id)" />
      <label class="st-directory-search">{{ pointLayer ? 'Find a returned registration' : 'Find an authority' }}<input v-model="search" type="search" placeholder="Name or identifier"></label><p class="atlas-footnote">Search narrows this list only. The map and its classification retain the full returned layer.</p>
      <template v-if="pointLayer"><p v-if="!current">No location records are loaded for this selection.</p><p v-else role="status" class="atlas-footnote">{{ current?.features.length ?? 0 }} location records returned. {{ locations.length }} have valid coordinates for this map. {{ filteredLocations.length }} match the list search. This is CQC registration evidence, not a map of all treatment services.</p><ul class="st-directory-list"><li v-for="(row, index) in filteredLocations" :key="String(row.location_id ?? index)" :class="{ selected: row.location_id === locationId }"><div><strong>{{ row.location_name ?? 'Name not supplied' }}</strong><p>{{ row.location_id }} · {{ row.region ?? 'Region not supplied' }} · {{ row.overall_rating ?? 'Rating not supplied' }}</p></div><button v-if="row.location_id" type="button" class="atlas-button" :aria-label="`Inspect registration ${row.location_name ?? row.location_id}`" @click="inspectLocation(String(row.location_id), $event)">Inspect</button></li></ul></template>
      <template v-else><StEvidenceState v-if="directory.error.value" :error="directory.error.value" @retry="directory.refresh()" /><p role="status" class="atlas-footnote">{{ filteredAuthorities.length }} of {{ authorities.length }} authority identities in this list.</p><ul class="st-directory-list"><li v-for="row in filteredAuthorities" :key="row.ons_code" :class="{ selected: row.ons_code === inspectId }"><div><NuxtLink :to="`/authorities/${encodeURIComponent(row.ons_code)}`">{{ row.name }}</NuxtLink><p>{{ row.ons_code }} · {{ row.region ?? 'Region not supplied' }}</p><template v-if="current"><p v-for="(observation, index) in observations.grouped.get(row.ons_code) ?? []" :key="index">{{ value(observation.value) }} · {{ observation.financial_year ?? current.year ?? 'Period not supplied' }}<span v-if="observation.allocation_status"> · {{ observation.allocation_status }}</span></p><p v-if="!observations.grouped.has(row.ons_code)">No observation returned</p><p v-else-if="observations.ambiguous.includes(row.ons_code)">Multiple observations, no map value selected</p></template></div><button type="button" class="atlas-button" :aria-label="`Inspect ${row.name}`" @click="inspect(row.ons_code, $event)">Inspect</button></li></ul></template>
      <p v-if="!pending && ((pointLayer && !filteredLocations.length) || (!pointLayer && !filteredAuthorities.length))">No matching records in this list.</p>
    </div><StInspector v-if="inspectId || locationId" :title="locationId ? String(selectedLocation?.location_name ?? 'Registration unavailable') : selectedAuthority?.name ?? inspectId" @close="close"><template v-if="locationId"><p v-if="!selectedLocation">The selected registration is not in this returned layer. No replacement record has been selected.</p><template v-else><p>Location identifier {{ selectedLocation.location_id }}</p><p>Rating: {{ selectedLocation.overall_rating ?? 'Not supplied' }}</p><p>Rating origin and source dates are not supplied by this map response.</p><StProvenance :provenance="{}" /><NuxtLink v-if="selectedLocation.ons_code" :to="`/authorities/${encodeURIComponent(String(selectedLocation.ons_code))}`" class="atlas-button">Open authority</NuxtLink><NuxtLink :to="{ path: '/cqc', query: { authority_ons_code: selectedLocation.ons_code ? String(selectedLocation.ons_code) : undefined } }" class="atlas-button">Explore CQC registrations</NuxtLink></template></template><LazyStAuthorityInspectorContent v-else :code="inspectId" /></StInspector></div>
  </section>
</template>
