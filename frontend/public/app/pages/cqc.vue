<script setup lang="ts">
import type { CqcLocation, CqcResponse } from '~/types/api'
import { validLocation, type MapLocation } from '~/lib/places'
interface Facet { value: string; count: number }
interface CqcExplorerResponse extends CqcResponse {
  limit: number
  offset: number
  facets: { registration_status: Facet[]; overall_rating: Facet[]; service_type: Facet[] }
}
const api = usePublicApi()
const filters = useFilterState()
const filter = (key: string) => { const value = filters.get(key); return Array.isArray(value) ? value[0] ?? '' : value ?? '' }
const filterKeys = ['provider_key', 'authority_ons_code', 'registration_status', 'regulated_activity', 'service_type', 'rating'] as const
function integer(key: string, fallback: number, min: number, max = Number.MAX_SAFE_INTEGER) {
  const text = filter(key)
  const value = Number(text)
  return text && Number.isSafeInteger(value) ? Math.min(max, Math.max(min, value)) : fallback
}
const offset = computed(() => integer('offset', 0, 0))
const limit = computed(() => integer('limit', 100, 1, 500))
const query = computed(() => ({ ...Object.fromEntries(filterKeys.map(key => [key, filter(key) || undefined])), limit: limit.value, offset: offset.value }))
const signature = computed(() => JSON.stringify(query.value))
const locationId = computed(() => filter('location_id'))
const showMap = computed(() => filter('view') === 'map')
// Selection and presentation belong to the URL, but cannot change which page
// the server returns. A signature also prevents a superseded page being shown.
const { data, pending, error, refresh } = await useAsyncData('public-cqc-workspace', async (_app, { signal }) => {
  const key = signature.value
  const response = await api.get<CqcExplorerResponse>('/cqc_locations', { query: query.value, signal })
  return { key, response }
}, { watch: [signature] })
const current = computed(() => !pending.value && !error.value && data.value?.key === signature.value ? data.value.response : null)
const rows = computed(() => current.value?.results ?? [])
const located = computed(() => rows.value.filter((row): row is CqcLocation & MapLocation => validLocation(row)))
const selected = computed(() => rows.value.find(row => row.location_id === locationId.value))
const shownFrom = computed(() => (current.value?.offset ?? offset.value) + 1)
const shownTo = computed(() => (current.value?.offset ?? offset.value) + rows.value.length)
const facetFields = [
  { key: 'registration_status', facet: 'registration_status', label: 'Registration status' },
  { key: 'rating', facet: 'overall_rating', label: 'Overall rating' },
  { key: 'service_type', facet: 'service_type', label: 'Service type' },
] as const
function facetRows(key: keyof CqcExplorerResponse['facets']) { return current.value?.facets?.[key] ?? [] }
let filterWrite = Promise.resolve()
// Fast changes to separate controls must merge with the committed URL, not
// with the preceding render's query while its navigation is still pending.
function setFilter(key: string, value: string) {
  const write = filterWrite.then(async () => {
    await filters.setAll({ ...filters.all(), [key]: value || undefined, offset: undefined, location_id: undefined })
    await nextTick()
  })
  filterWrite = write.catch(() => {})
  return write
}
function reset() { return filters.setAll({ view: showMap.value ? 'map' : undefined }) }
function page(delta: number) { return filters.setAll({ ...filters.all(), offset: String(Math.max(0, offset.value + delta)), location_id: undefined }) }
let trigger: HTMLElement | null = null
async function inspect(id: string, event?: Event) {
  trigger = event?.currentTarget as HTMLElement ?? null
  await filters.set('location_id', id)
  await nextTick()
  document.querySelector<HTMLElement>('.st-inspector-heading')?.focus()
}
async function close() { await filters.set('location_id', undefined); await nextTick(); if (trigger?.isConnected) trigger.focus() }
function ratingOrigin(row: CqcLocation) { return row.rating_source === 'api' ? 'CQC API' : row.rating_source === 'bulk_export' ? 'CQC bulk export' : row.rating_source ?? 'Origin not supplied' }
useHead({ title: 'CQC registrations · SectorTrace' })
</script>

<template>
  <section class="space-y-6">
    <header class="st-page-header"><p class="atlas-eyebrow">Evidence</p><h1>CQC registrations</h1><p>Inspect published registration records for tracked providers, with CQC status, ratings and source dates.</p></header>
    <p class="atlas-caveat">CQC registration covers only certain regulated activities. Most community drug and alcohol provision is not registered. Location counts do not measure service coverage or quality.</p>
    <section class="atlas-panel atlas-panel-body space-y-4" aria-label="Registration filters">
      <div class="st-cqc-filters">
        <StEntityPicker kind="provider" :model-value="filter('provider_key')" label="Provider" empty-label="All tracked providers" @update:model-value="setFilter('provider_key', $event)" />
        <StEntityPicker kind="authority" :model-value="filter('authority_ons_code')" label="Authority" empty-label="All authorities" @update:model-value="setFilter('authority_ons_code', $event)" />
        <label>Regulated activity contains<input type="search" :value="filter('regulated_activity')" @change="setFilter('regulated_activity', ($event.target as HTMLInputElement).value)"></label>
        <label v-for="field in facetFields" :key="field.key">{{ field.label }}<select :value="filter(field.key)" @change="setFilter(field.key, ($event.target as HTMLSelectElement).value)"><option value="">Any</option><option v-if="filter(field.key) && !facetRows(field.facet).some(row => row.value === filter(field.key))" :value="filter(field.key)">{{ filter(field.key) }} (count unavailable)</option><option v-for="item in facetRows(field.facet)" :key="item.value" :value="item.value">{{ item.value }} ({{ item.count.toLocaleString('en-GB') }})</option></select></label>
      </div>
      <p class="atlas-footnote">Option counts cover all tracked registrations for the selected provider, or all tracked providers when none is selected. They do not apply the other filters. Activity searches keep commas as part of the published name.</p>
      <button class="atlas-button" type="button" @click="reset">Clear filters</button>
    </section>
    <div class="flex flex-wrap gap-2" role="group" aria-label="Registration view"><button class="atlas-button" type="button" :aria-pressed="!showMap" @click="filters.set('view', 'data')">Data</button><button class="atlas-button" type="button" :aria-pressed="showMap" @click="filters.set('view', 'map')">Map</button></div>
    <div class="st-directory-workspace" :class="{ 'has-inspector': locationId }">
      <div class="min-w-0 space-y-4">
        <StEvidenceState :pending="pending" :error="error" @retry="refresh">
          <template v-if="current">
            <p class="atlas-footnote" role="status">Matching registrations: {{ current.total.toLocaleString('en-GB') }} · Loaded records: {{ rows.length.toLocaleString('en-GB') }} · Mapped records: {{ located.length.toLocaleString('en-GB') }}</p>
            <p v-if="current.without_coordinate != null" class="atlas-footnote">{{ current.without_coordinate.toLocaleString('en-GB') }} matching registrations have a missing coordinate across all matching pages.</p>
            <p class="atlas-footnote">The map uses only valid coordinates in this loaded page. All loaded records remain in the list, including those without usable coordinates. Nearby groups represent loaded registrations.</p>
            <LazyGeographyMap v-if="showMap" :features="[]" locator point-layer :locations="located" :selected-location="locationId" @select-location="inspect" />
            <ul v-if="rows.length" class="st-directory-list st-cqc-list" aria-label="Loaded registrations">
              <li v-for="(row, index) in rows" :key="row.location_id ?? index" :class="{ selected: row.location_id === locationId }">
                <div><h2>{{ row.location_name ?? 'Name not supplied' }}</h2><p><NuxtLink v-if="row.provider_key" :to="`/providers/${encodeURIComponent(row.provider_key)}`">{{ row.provider_name ?? row.provider_key }}</NuxtLink><span v-else>{{ row.provider_name ?? 'Provider not supplied' }}</span> · {{ row.local_authority_raw ?? row.local_authority_ons_code ?? 'Authority not supplied' }}</p><p>{{ row.registration_status ?? 'Status not supplied' }} · {{ row.overall_rating ?? 'Rating not supplied' }}<span v-if="row.overall_rating"> · {{ ratingOrigin(row) }} · {{ row.overall_rating_date ?? 'Rating date not supplied' }}</span></p><p>{{ row.location_id ?? 'Identifier not supplied' }} · {{ validLocation(row) ? 'Located on this page’s map' : 'No usable coordinate' }}</p></div>
                <button v-if="row.location_id" class="atlas-button" type="button" :aria-label="`Inspect ${row.location_name ?? row.location_id}`" @click="inspect(row.location_id, $event)">Inspect</button>
              </li>
            </ul>
            <StEvidenceState v-else empty :empty-title="offset ? 'No records in this result window' : 'No matching registrations'" :message="offset ? 'The matching results may have changed. Return to the first page or change the filters.' : 'Try another selection or clear the active filters.'" />
            <nav class="flex flex-wrap gap-3 items-center" aria-label="Registration pages"><span class="atlas-footnote">{{ rows.length ? `Records ${shownFrom.toLocaleString('en-GB')} to ${shownTo.toLocaleString('en-GB')}` : 'No loaded records' }} · up to {{ current.limit ?? limit }} per page</span><button class="atlas-button" type="button" :disabled="offset === 0" @click="page(-limit)">Previous</button><button class="atlas-button" type="button" :disabled="shownTo >= current.total" @click="page(limit)">Next</button><button v-if="offset" class="atlas-button" type="button" @click="page(-offset)">First page</button></nav>
            <StCaveat v-if="current.caveat" :text="current.caveat" />
          </template>
        </StEvidenceState>
      </div>
      <StInspector v-if="locationId" :title="selected?.location_name ?? selected?.location_id ?? (pending ? 'Loading registration' : error ? 'Registration unavailable' : 'Registration not in this result window')" @close="close">
        <p v-if="pending" role="status">Loading the selected result window…</p>
        <p v-else-if="error">The result window could not load. Retry the evidence request to check this selection.</p>
        <LazyStCqcInspectorContent v-else-if="selected" :key="locationId" :row="selected" />
        <template v-else><p>Location {{ locationId }} is not in the returned page. The result window may have changed since this link was saved. No replacement record has been selected.</p><NuxtLink v-if="filter('provider_key')" class="atlas-button" :to="`/providers/${encodeURIComponent(filter('provider_key'))}`">Open selected provider</NuxtLink><button class="atlas-button" type="button" @click="close">Return to registrations</button></template>
      </StInspector>
    </div>
  </section>
</template>
<style scoped>
.st-cqc-filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 230px), 1fr)); gap: 16px; }
.st-cqc-filters label { display: grid; gap: 6px; min-width: 0; font-size: 13px; }
.st-cqc-filters input, .st-cqc-filters select { width: 100%; min-width: 0; min-height: 44px; padding: 8px 10px; border: 1px solid var(--border-control); border-radius: 4px; background: var(--surface-panel); }
.st-cqc-list h2 { font-size: 15px; margin: 0 0 4px; }
.st-cqc-list li > div { min-width: 0; overflow-wrap: anywhere; }
.st-cqc-list button { flex-shrink: 0; }
</style>
