<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { CqcLocation, CqcResponse } from '~/types/api'

interface Facet { value: string; count: number }
interface CqcExplorerResponse extends CqcResponse {
  limit: number
  offset: number
  facets: {
    registration_status: Facet[]
    overall_rating: Facet[]
    region: Facet[]
    service_type: Facet[]
  }
}

const api = usePublicApi()
const filters = useFilterState()
const values = ['provider_key', 'authority_ons_code', 'registration_status', 'regulated_activity', 'service_type', 'rating', 'offset'] as const
const filter = (key: string) => {
  const value = filters.get(key)
  return Array.isArray(value) ? value[0] ?? '' : value ?? ''
}
const search = computed({ get: () => filter('provider_key'), set: (value: string) => { void filters.set('provider_key', value || undefined) } })
const authority = computed({ get: () => filter('authority_ons_code'), set: (value: string) => { void filters.set('authority_ons_code', value || undefined) } })
const activity = computed({ get: () => filter('regulated_activity'), set: (value: string) => { void filters.set('regulated_activity', value || undefined) } })
const status = computed(() => filter('registration_status'))
const rating = computed(() => filter('rating'))
const serviceType = computed(() => filter('service_type'))
const offset = computed(() => Number(filter('offset') || 0))

const { data, pending, error } = await useDataRoute<CqcExplorerResponse>(
  'public-cqc-explorer',
  (f) => api.cqc({ query: { ...f, limit: 100 } }),
)

const rows = computed(() => data.value?.results ?? [])
const located = computed(() => rows.value.filter((row) => row.latitude != null && row.longitude != null))
const shownTo = computed(() => offset.value + rows.value.length)
const facets = computed(() => data.value?.facets)
const columns: Column<CqcLocation>[] = [
  { key: 'provider_name', label: 'Provider' }, { key: 'location_name', label: 'Location' },
  { key: 'local_authority_raw', label: 'Authority' }, { key: 'registration_status', label: 'Status' },
  { key: 'overall_rating', label: 'Rating' }, { key: 'rating_source', label: 'Rating source' },
  { key: 'service_types', label: 'Service types' }, { key: 'source_url', label: 'Source', link: true },
]

function setFilter(key: string, value: string): void {
  void filters.setAll({ ...filters.all(), [key]: value || undefined, offset: undefined })
}
function page(delta: number): void {
  const next = Math.max(0, offset.value + delta)
  void filters.set('offset', next ? String(next) : undefined)
}
function facetLabel(row: Facet): string { return `${row.value} (${row.count.toLocaleString('en-GB')})` }

useHead({ title: 'SectorTrace — CQC-registered locations' })
</script>

<template>
  <section class="space-y-8">
    <div class="atlas-hero">
      <div>
        <p class="atlas-kicker">Safety · regulated locations</p>
        <h1>CQC-registered locations</h1>
        <p class="atlas-lede">{{ data?.total?.toLocaleString('en-GB') ?? '—' }} locations of tracked providers are registered with the Care Quality Commission. This is a map of regulated locations — never a complete service map.</p>
        <div class="atlas-actions"><a class="atlas-button primary" href="#cqc-locations">Explore locations</a><a class="atlas-button" href="#cqc-method">Read the scope</a></div>
      </div>
      <div class="atlas-hero-aside"><div class="atlas-region"><strong>{{ data?.total?.toLocaleString('en-GB') ?? '—' }}</strong><span>tracked CQC registrations</span></div><div class="atlas-region"><strong>{{ located.length.toLocaleString('en-GB') }}</strong><span>located in this page of results</span></div></div>
    </div>

    <div id="cqc-method" class="atlas-caveat"><span>Read this before reading the map</span> — CQC registration covers only certain regulated activities. Most community drug and alcohol provision is not registered. A location count is neither coverage nor quality.</div>

    <div v-if="pending" class="text-sm opacity-60">Loading locations…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <section id="cqc-locations" class="atlas-section">
        <div class="atlas-section-head"><h2>Locations</h2><p>Filter the published CQC directory. The map and table show the same page of results.</p></div>
        <div class="atlas-panel atlas-panel-body space-y-5">
          <div class="grid gap-3 md:grid-cols-3">
            <label class="text-sm"><span class="block mb-1 opacity-70">Provider key</span><input v-model.lazy="search" class="w-full rounded border px-3 py-2" type="search" placeholder="Provider key"></label>
            <label class="text-sm"><span class="block mb-1 opacity-70">Authority ONS code</span><input v-model.lazy="authority" class="w-full rounded border px-3 py-2" type="search" placeholder="Authority ONS code"></label>
            <label class="text-sm"><span class="block mb-1 opacity-70">Regulated activity contains</span><input v-model.lazy="activity" class="w-full rounded border px-3 py-2" type="search" placeholder="Regulated activity"></label>
          </div>
          <div class="flex flex-wrap gap-3">
            <label class="text-sm"><span class="block mb-1 opacity-70">Registration status</span><select class="rounded border px-3 py-2" :value="status" @change="setFilter('registration_status', ($event.target as HTMLSelectElement).value)"><option value="">Any</option><option v-for="item in facets?.registration_status ?? []" :key="item.value" :value="item.value">{{ facetLabel(item) }}</option></select></label>
            <label class="text-sm"><span class="block mb-1 opacity-70">Overall rating</span><select class="rounded border px-3 py-2" :value="rating" @change="setFilter('rating', ($event.target as HTMLSelectElement).value)"><option value="">Any</option><option v-for="item in facets?.overall_rating ?? []" :key="item.value" :value="item.value">{{ facetLabel(item) }}</option></select></label>
            <label class="text-sm"><span class="block mb-1 opacity-70">Service type</span><select class="rounded border px-3 py-2" :value="serviceType" @change="setFilter('service_type', ($event.target as HTMLSelectElement).value)"><option value="">Any</option><option v-for="item in facets?.service_type ?? []" :key="item.value" :value="item.value">{{ facetLabel(item) }}</option></select></label>
          </div>
          <p v-if="data?.without_coordinate" class="text-sm opacity-70">{{ data.without_coordinate.toLocaleString('en-GB') }} matching location(s) have no coordinate and are listed in the table but not shown on the map.</p>
          <CqcMap :locations="rows" />
          <StEvidenceTable v-if="rows.length" :columns="columns" :rows="rows" row-key="location_id" />
          <StEmptyState v-else />
          <div class="flex flex-wrap items-center gap-3 text-sm"><span>{{ rows.length ? `${(offset + 1).toLocaleString('en-GB')}–${shownTo.toLocaleString('en-GB')} of ${data?.total.toLocaleString('en-GB')}` : 'No matching locations.' }}</span><button class="atlas-button" type="button" :disabled="offset === 0" @click="page(-100)">Previous</button><button class="atlas-button" type="button" :disabled="shownTo >= (data?.total ?? 0)" @click="page(100)">Next</button></div>
          <StCaveat v-if="data?.caveat" :text="data.caveat" />
        </div>
      </section>
    </template>
  </section>
</template>
