<script setup lang="ts">
import type { DiscrepancyResponse } from '~/types/api'
import { downloadEvidenceJson } from '~/lib/evidence-export'
const api = usePublicApi()
const filters = useFilterState()
const route = useRoute()
const scalar = (key: string) => { const value = filters.get(key); return Array.isArray(value) ? value[0] ?? '' : value ?? '' }
const valid = computed(() => {
  const values = ['provider_key', 'ons_code'].flatMap(key => { const value = filters.get(key); return value == null ? [] : Array.isArray(value) ? value : [value] })
  return values.length === 1 && !!values[0]?.trim()
})
const query = computed(() => ({ provider_key: scalar('provider_key') || undefined, ons_code: scalar('ons_code') || undefined }))
const signature = computed(() => JSON.stringify({ query: query.value, valid: valid.value }))
const { data, pending, error, refresh } = await useAsyncData('public-source-discrepancies', async (_app, { signal }) => {
  const key = signature.value
  if (!valid.value) return { key, response: null }
  const response = await api.get<DiscrepancyResponse>('/discrepancies', { query: query.value, signal })
  return { key, response }
}, { watch: [signature] })
const current = computed(() => !pending.value && !error.value && data.value?.key === signature.value ? data.value.response : null)
const differences = computed(() => Array.isArray(current.value?.discrepancies) ? current.value.discrepancies : null)
const agreed = computed(() => Array.isArray(current.value?.agreed) ? current.value.agreed : null)
const offset = computed(() => /^\d+$/.test(scalar('offset')) ? Number(scalar('offset')) : 0)
const displayed = computed(() => (differences.value ?? []).slice(offset.value, offset.value + 25))
const limitations = 'The response uses as_of for several date meanings. Identity observations use retrieval dates, including aggregate latest retrievals for some authority sources. CQC comparisons use rating dates. These are not interchangeable. No payload hashes are returned. A CQC location source URL does not authenticate the separate bulk-rating source.'
const context = computed(() => ({ endpoint: '/api/v1/discrepancies', request: query.value, entity: current.value?.entity ?? null, note: current.value?.note ?? null, caveat: current.value?.caveat ?? null, limitations, view: `#${route.fullPath}` }))
function choose(key: string, value: string) { return filters.setAll({ [key]: value || undefined }) }
function download() { if (current.value) downloadEvidenceJson('source-comparison-response', [current.value], { ...context.value, scope: 'one-complete-returned-entity-comparison-response' }) }
useHead({ title: 'Source discrepancies · SectorTrace' })
</script>
<template>
  <section class="space-y-6">
    <header class="st-page-header"><p class="atlas-eyebrow">Verification tools</p><h1>Source discrepancies</h1><p>Read differing source observations for one provider or authority. This view does not decide which value is right.</p></header>
    <div class="grid gap-4 md:grid-cols-2"><StEntityPicker kind="provider" :model-value="scalar('provider_key')" label="Provider" empty-label="Choose a provider" @update:model-value="choose('provider_key', $event)" /><StEntityPicker kind="authority" :model-value="scalar('ons_code')" label="Authority" empty-label="Choose an authority" @update:model-value="choose('ons_code', $event)" /></div>
    <p v-if="!valid" role="status">Choose exactly one provider or authority. Mixed or repeated identifiers are not compared together.</p>
    <StEvidenceState v-else :pending="pending" :error="error" @retry="refresh"><template v-if="current">
      <h2>{{ current.entity?.name ?? current.entity?.id ?? 'Entity name not supplied' }}</h2>
      <StCaveat v-if="current.caveat" :text="current.caveat" />
      <p class="atlas-caveat">{{ limitations }}</p>
      <p>Reported checks: {{ current.checked ?? 'Not supplied' }}. This is not a count of sources, observations or fields with complete evidence.</p>
      <button type="button" class="atlas-button" @click="download">Download returned comparison JSON</button>
      <details v-if="current.note"><summary>Original comparison note</summary><p class="whitespace-pre-wrap">{{ current.note }}</p></details>
      <h2>Differing observations</h2>
      <p v-if="!differences" role="status">The differing-observation array was not supplied.</p>
      <p v-else-if="!differences.length" role="status">No differing observations were returned. This does not establish agreement or complete source coverage.</p>
      <template v-else><p>Returned comparison records: {{ differences.length }}. Showing up to 25 records from offset {{ offset }}.</p><section v-for="(record, index) in displayed" :key="index" class="atlas-panel atlas-panel-body space-y-3"><h3>{{ record.label ?? record.id ?? 'Field not supplied' }}</h3><StComparisonRecords :rows="record.observations" :scope="`discrepancy:${offset + index}`" :title="String(record.label ?? record.id ?? 'Source observations')" :context="{ ...context, comparison_record: { ...record, observations: undefined }, date_field: 'as_of', date_meaning: record.id?.startsWith('cqc_rating:') ? 'rating date' : 'retrieval date or aggregate latest retrieval' }" /></section><nav aria-label="Discrepancy comparison pages" class="flex gap-2"><button type="button" class="atlas-button" :disabled="!offset" @click="filters.set('offset', String(Math.max(0, offset - 25)))">Previous comparisons</button><button type="button" class="atlas-button" :disabled="offset + 25 >= differences.length" @click="filters.set('offset', String(offset + 25))">Next comparisons</button><button v-if="offset" type="button" class="atlas-button" @click="filters.set('offset', undefined)">First comparisons</button></nav></template>
      <h2>Other checked fields</h2><p>The API groups fields with one distinct value and fields with no observations under agreed. One named source does not establish agreement between sources. These rows omit observation dates and source URLs.</p>
      <StComparisonRecords :rows="agreed" scope="discrepancy:other" title="Other checked fields" :context="{ ...context, limitations: 'One distinct value or no observations. Source names are retained but dates and source URLs are omitted from these rows.' }" />
    </template></StEvidenceState>
  </section>
</template>
