<script setup lang="ts">
import { safetyLane, safetyRelationships, safetySources, type SafetyRow } from '~/lib/safety'
import type { SafetyLegalPayload } from '~/types/safety'
const api = usePublicApi()
const filters = useFilterState()
const get = (key: string) => { const value = filters.get(key); return Array.isArray(value) ? value[0] ?? '' : value ?? '' }
const lens = computed(() => get('lens') || 'chronology')
const lenses = [{ key: 'chronology', label: 'Source chronology' }, { key: 'pfd', label: 'PFD report collection' }, { key: 'sar', label: 'SAR library collection' }, { key: 'hse', label: 'HSE register records' }]
const corpusSource = computed(() => lens.value === 'pfd' || lens.value === 'sar' || lens.value === 'hse' ? lens.value : null)
const invalid = computed(() => get('source') && !safetySources.some(item => item.key === get('source')) ? 'The selected source is not supported.' : get('relationship') && !Object.hasOwn(safetyRelationships, get('relationship')) ? 'The selected relationship is not supported.' : ['year_from', 'year_to'].some(key => get(key) && !/^\d{4}$/.test(get(key))) ? 'Year bounds must contain four digits.' : get('year_from') && get('year_to') && get('year_from') > get('year_to') ? 'The first year is after the last year.' : '')
const query = computed<Record<string, string | undefined>>(() => Object.fromEntries(['source', 'relationship', 'provider_key', 'year_from', 'year_to'].map(key => [key, get(key) || undefined])))
const signature = computed(() => JSON.stringify({ query: query.value, invalid: invalid.value, enabled: lens.value === 'chronology' }))
const { data, pending, error, refresh } = await useAsyncData('public-safety-source-chronology', async (_app, { signal }) => {
  if (lens.value !== 'chronology' || invalid.value) return null
  const key = signature.value
  return { key, response: await api.get<SafetyLegalPayload>('/safety_legal', { query: query.value, signal }) }
}, { watch: [signature] })
const current = computed(() => !pending.value && !error.value && data.value?.key === signature.value ? data.value.response : null)
const events = computed(() => Array.isArray(current.value?.events) ? current.value.events : null)
const lanes = computed(() => safetySources.filter(item => !get('source') || item.key === get('source')))
const unknownSources = computed(() => [...new Set((events.value ?? []).map(row => String(row.source)).filter(source => !safetySources.some(item => item.key === source)))])
const forSource = (source: string): SafetyRow[] => (events.value ?? []).filter(row => String(row.source) === source)
const yearFrom = ref(get('year_from'))
const yearTo = ref(get('year_to'))
watch(() => [get('year_from'), get('year_to')], () => { yearFrom.value = get('year_from'); yearTo.value = get('year_to') })
let update = Promise.resolve()
function change(values: Record<string, string | undefined>) {
  const next = update.then(async () => {
    const retained = Object.fromEntries(Object.entries(filters.all()).filter(([key]) => !key.endsWith('-events_offset')))
    await filters.setAll({ ...retained, ...values, safety_lane: undefined, safety_record: undefined })
    await nextTick()
  })
  update = next.catch(() => {})
  return next
}
useHead({ title: 'Safety and legal evidence · SectorTrace' })
</script>
<template>
  <section class="space-y-6"><header class="st-page-header"><p class="atlas-eyebrow">Evidence</p><h1>Safety and legal evidence</h1><p>Read reports, judgments and regulatory records in their own source context.</p></header><p class="atlas-caveat">Being named in a document is not a finding of fault. These sources describe different processes and do not form a combined measure of harm.</p>
    <nav class="flex flex-wrap gap-2" aria-label="Safety evidence views"><button v-for="item in lenses" :key="item.key" type="button" class="atlas-button" :aria-pressed="lens === item.key" @click="change({ lens: item.key })">{{ item.label }}</button></nav>
    <template v-if="lens === 'chronology'"><div class="st-safety-filters"><label>Source<select :value="get('source')" @change="change({ source: ($event.target as HTMLSelectElement).value || undefined })"><option value="">All sources in separate lanes</option><option v-if="get('source') && !safetySources.some(item => item.key === get('source'))" :value="get('source')">Unsupported source: {{ get('source') }}</option><option v-for="item in safetySources" :key="item.key" :value="item.key">{{ item.label }}</option></select></label><label>Relationship<select :value="get('relationship')" @change="change({ relationship: ($event.target as HTMLSelectElement).value || undefined })"><option value="">All supplied relationships</option><option v-if="get('relationship') && !Object.hasOwn(safetyRelationships, get('relationship'))" :value="get('relationship')">Unsupported relationship: {{ get('relationship') }}</option><option v-for="(label, key) in safetyRelationships" :key="key" :value="key">{{ label }}</option></select></label><StEntityPicker kind="provider" :model-value="get('provider_key')" empty-label="All tracked providers" @update:model-value="change({ provider_key: $event || undefined })" /></div>
      <form class="st-safety-filters" @submit.prevent="change({ year_from: yearFrom || undefined, year_to: yearTo || undefined })"><label>First source year<input v-model="yearFrom" inputmode="numeric" pattern="[0-9]{4}" maxlength="4"></label><label>Last source year<input v-model="yearTo" inputmode="numeric" pattern="[0-9]{4}" maxlength="4"></label><button type="submit" class="atlas-button">Apply year bounds</button></form>
      <p class="atlas-caveat">The year filter uses the first four characters of the source date. It can exclude reports written in other date formats and always excludes undated entries, including SAR records. Clear the year bounds to inspect those entries.</p><p v-if="get('ons_code') || get('authority_ons_code')" class="atlas-footnote">The retained authority selection does not filter this response. Coroner areas and safeguarding boards are not authority boundaries.</p>
      <button type="button" class="atlas-button" @click="change({ source: undefined, relationship: undefined, provider_key: undefined, year_from: undefined, year_to: undefined })">Clear chronology filters</button><p v-if="invalid" role="status">{{ invalid }} Correct the selection or clear the chronology filters. No broader request has been made.</p>
      <StEvidenceState v-else :pending="pending" :error="error" @retry="refresh"><template v-if="events"><p class="atlas-footnote">This response is capped at 2,000 entries across its selected sources. Counts below cover returned entries in each lane, not all matching evidence. There is no further response page. Selecting one source can expose entries omitted from a combined response.</p><p v-if="current?.truncated" class="atlas-caveat">The source response is truncated. Undated records may fall outside this window.</p><p v-if="current?.truncated == null" class="atlas-footnote">Response truncation status was not supplied.</p>
        <StSafetyRecords v-for="source in lanes" :key="source.key" :definition="safetyLane(source.key)" :rows="forSource(source.key)" :query="query" :caveats="{ [source.key]: current?.caveats?.[source.key] ?? null }" :truncated="current?.truncated" />
        <StSafetyRecords v-for="source in unknownSources" :key="`unknown-${source}`" :definition="safetyLane(source)" :rows="forSource(source)" :query="query" :caveats="{ source: 'This returned source is not in the supported source catalogue. Its original records are retained.' }" :truncated="current?.truncated" />
      </template><p v-else role="status">The source event array was not supplied. This is not an empty chronology.</p></StEvidenceState>
    </template>
    <LazyStSafetyCorpus v-else-if="corpusSource" :source="corpusSource" />
    <p v-else role="status">The saved Safety view is not supported. Choose a view above. No replacement has been selected.</p>
  </section>
</template>
<style scoped>
.st-safety-filters { display: flex; flex-wrap: wrap; align-items: end; gap: 16px; } label { display: grid; gap: 6px; font-size: 13px; max-width: 100%; } input, select { border: 1px solid var(--border-control); border-radius: 4px; background: var(--surface-base); color: var(--text-primary); padding: 9px; max-width: 100%; min-height: 44px; }
</style>
