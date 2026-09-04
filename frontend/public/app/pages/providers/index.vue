<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { ProviderRow, ProvidersResponse } from '~/types/api'

const api = usePublicApi()
const filters = useFilterState()
const search = computed({
  get: () => String(filters.get('q') ?? ''),
  set: (value: string) => { void filters.set('q', value || undefined) },
})

const { data, pending, error } = await useDataRoute<ProvidersResponse>(
  'public-providers',
  () => api.providers(),
)

const allProviders = computed(() => data.value?.providers ?? [])
const rows = computed(() => {
  const needle = search.value.trim().toLowerCase()
  if (!needle) return allProviders.value
  return allProviders.value.filter((row) => String(row.canonical_name ?? '').toLowerCase().includes(needle))
})
const count = (row: ProviderRow, key: string): number => typeof row[key] === 'number' ? Number(row[key]) : 0
const total = (key: string) => allProviders.value.reduce((sum, row) => sum + count(row, key), 0)
const topProviders = computed(() => allProviders.value.slice(0, 8))
const activeProviders = computed(() => allProviders.value.filter((row) => !row.status || row.status === 'active').length)
const target = computed(() => allProviders.value.find((row) => row.is_target))

const providerColumns: Column<ProviderRow>[] = [
  { key: 'canonical_name', label: 'Provider', to: (row) => row.provider_key ? `/providers/${row.provider_key}` : null },
  { key: 'status', label: 'Status' },
  { key: 'contract_count', label: 'Contracts', numeric: true },
  { key: 'contract_value_gbp', label: 'Published value', numeric: true },
  { key: 'cqc_locations', label: 'CQC locations', numeric: true },
  { key: 'tribunal_count', label: 'Tribunals', numeric: true },
  { key: 'nhs_job_advert_count', label: 'NHS adverts', numeric: true },
  { key: 'charity_income_latest', label: 'Latest charity income', numeric: true },
]
const evidenceColumns: Column<ProviderRow>[] = [
  { key: 'canonical_name', label: 'Provider', to: (row) => row.provider_key ? `/providers/${row.provider_key}` : null },
  { key: 'cqc_locations', label: 'CQC', numeric: true },
  { key: 'tribunal_count', label: 'Tribunals', numeric: true },
  { key: 'contract_count', label: 'Contracts', numeric: true },
  { key: 'nhs_job_advert_count', label: 'NHS adverts', numeric: true },
]

useHead({ title: 'SectorTrace — Providers' })
</script>

<template>
  <section class="atlas-hero">
    <div>
      <div class="atlas-kicker">Provider directory · entity evidence</div>
      <h1>Find provider evidence</h1>
      <p class="atlas-lede">Browse tracked organisations, then open a provider workbench to see the published evidence held for that identity.</p>
      <details class="atlas-read-first"><summary>How to read provider coverage</summary><p>Counts describe records in this warehouse, not provider size, performance, or absence of an event.</p><p>Contract counts use verified supplier aliases. A missing match is not evidence that a provider was not involved.</p></details>
    </div>
    <div class="atlas-hero-aside"><div class="atlas-stat"><strong>{{ allProviders.length.toLocaleString('en-GB') }}</strong><span>tracked organisations</span></div><div class="atlas-stat"><strong>{{ activeProviders.toLocaleString('en-GB') }}</strong><span>active identities</span></div></div>
  </section>

  <section v-if="pending" class="atlas-panel p-6">Loading provider evidence…</section>
  <section v-else-if="error" class="atlas-panel p-6">Provider evidence is unavailable.</section>
  <template v-else>
    <section class="atlas-section atlas-panel atlas-panel-body"><div class="atlas-eyebrow">Directory controls</div><div class="flex flex-wrap items-end gap-3 mt-3"><label class="text-sm">Filter by provider name<input v-model.lazy="search" type="search" class="block mt-1 px-2 py-1 min-w-64" placeholder="Search providers…"></label><span class="atlas-footnote">Showing {{ rows.length.toLocaleString('en-GB') }} of {{ allProviders.length.toLocaleString('en-GB') }}</span></div></section>

    <section class="atlas-section"><div class="atlas-section-head"><h2>Provider directory</h2><p>Open a provider to see its evidence inventory, timeline, registrations, filings, and safety records.</p></div><div class="atlas-grid atlas-grid-4"><NuxtLink v-for="provider in topProviders" :key="String(provider.provider_key)" :to="`/providers/${provider.provider_key}`" class="atlas-panel atlas-panel-body atlas-card-link"><div class="atlas-eyebrow">{{ provider.is_target ? 'Campaign subject' : (provider.status && provider.status !== 'active' ? provider.status : 'Tracked identity') }}</div><h3>{{ provider.canonical_name }}</h3><p class="atlas-footnote">{{ count(provider, 'cqc_locations') }} CQC locations · {{ count(provider, 'contract_count') }} contracts</p></NuxtLink></div></section>

    <section class="atlas-section atlas-panel atlas-panel-body"><div class="atlas-section-head"><h2>Evidence held per provider</h2><p>Coverage by record type. A low count says what has been collected or matched, not what happened in the organisation.</p></div><div class="atlas-grid atlas-grid-4"><div class="atlas-stat"><strong>{{ total('cqc_locations').toLocaleString('en-GB') }}</strong><span>CQC locations</span></div><div class="atlas-stat"><strong>{{ total('contract_count').toLocaleString('en-GB') }}</strong><span>matched contract notices</span></div><div class="atlas-stat"><strong>{{ total('nhs_job_advert_count').toLocaleString('en-GB') }}</strong><span>NHS Jobs adverts</span></div><div class="atlas-stat"><strong>{{ total('tribunal_count').toLocaleString('en-GB') }}</strong><span>tribunal cases</span></div></div><StEvidenceTable class="mt-5" :columns="evidenceColumns" :rows="rows" row-key="provider_key" /></section>

    <section class="atlas-section atlas-panel atlas-panel-body"><div class="atlas-section-head"><h2>All providers</h2><p>The comparable provider view, including lifecycle status and the latest published financial or procurement context.</p></div><StEvidenceTable :columns="providerColumns" :rows="rows" row-key="provider_key" /><p v-if="!rows.length" class="atlas-footnote mt-4">No providers match this filter.</p></section>

    <section v-if="target" class="atlas-section atlas-panel atlas-panel-body"><h2>Campaign subject</h2><p class="atlas-footnote">The campaign subject is identified in the provider register; the evidence counts below remain coverage measures.</p><NuxtLink :to="`/providers/${target.provider_key}`" class="atlas-button mt-3">Open {{ target.canonical_name }}</NuxtLink></section>
    <section class="atlas-section atlas-panel atlas-panel-body"><h2>Reading the directory</h2><p class="atlas-caveat"><span aria-hidden="true">⚠</span> Contract totals are based on exact verified supplier aliases and published notice values. They are not provider revenue, payments, or sector spend.</p><p class="atlas-caveat"><span aria-hidden="true">⚠</span> CQC, tribunal, NHS Jobs, charity, and contract records are separate evidence layers. They are not combined into a provider score.</p></section>
  </template>
</template>
