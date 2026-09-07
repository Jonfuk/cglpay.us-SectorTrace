<script setup lang="ts">
import type { Column } from '~/components/StEvidenceTable.vue'
import { payLenses, payQuery, payRows, type PayPayload, type PayRow } from '~/lib/pay-lenses'
const filters = useFilterState()
const api = usePublicApi()
const get = (key: string) => { const value = filters.get(key); return Array.isArray(value) ? value[0] ?? '' : value ?? '' }
const active = computed(() => payLenses.find(lens => lens.key === get('lens')))
const sourceKeys = new Set(payLenses.map(lens => lens.group))
const invalid = computed(() => Boolean((get('lens') && !active.value) || (get('source') && !sourceKeys.has(get('source')))))
const retained = computed(() => Object.fromEntries(['source', 'provider_key', 'year_from', 'year_to', 'role', 'pay_unit'].map(key => [key, get(key) || undefined])))
const query = computed(() => payQuery(active.value, retained.value))
const invalidYear = computed(() => active.value?.years && (['year_from', 'year_to'].some(key => get(key) && !/^\d{4}$/.test(get(key))) || Boolean(get('year_from') && get('year_to') && get('year_from') > get('year_to'))))
const invalidUnit = computed(() => active.value?.unit && get('pay_unit') && !['hourly', 'annual', 'other'].includes(get('pay_unit')))
const signature = computed(() => `${JSON.stringify(query.value)}:${invalid.value}:${Boolean(invalidYear.value)}:${Boolean(invalidUnit.value)}`)
const { data, pending, error, refresh } = await useAsyncData('public-pay-questions', async (_app, { signal }) => {
  if (invalid.value || invalidYear.value || invalidUnit.value) return null
  const key = signature.value
  return { key, payload: await api.get<PayPayload>('/pay', { query: query.value, signal }) }
}, { watch: [signature] })
const payload = computed(() => !pending.value && !error.value && data.value?.key === signature.value ? data.value.payload : null)
const groups = computed(() => payload.value?.source_groups ?? [])
const available = (group: string, array: string) => groups.value.some(item => item.key === group && (!item.arrays || item.arrays.includes(array)))
const questions = computed(() => get('source') && !active.value ? payLenses.filter(lens => lens.group === get('source')) : payLenses)
const observations = computed(() => active.value ? payRows(payload.value, active.value.array) : null)
const caveats = computed(() => Object.fromEntries((active.value?.caveats ?? []).map(key => [key, payload.value?.caveats?.[key] ?? null])))
let update = Promise.resolve()
function setFilter(key: string, value: string) {
  const next = update.then(async () => { await filters.setAll({ ...filters.all(), [key]: value || undefined, pay_offset: undefined, record: undefined }); await nextTick() })
  update = next.catch(() => {})
  return next
}
function choose(key: string) { const lens = payLenses.find(item => item.key === key); return filters.setAll({ ...filters.all(), lens: lens?.key, source: lens?.group, record: undefined, pay_offset: undefined }) }
const repeatRows = computed(() => payRows(payload.value, 'repeat_advertised_roles'))
const repeatColumns: Column<PayRow>[] = [{ key: 'job_title_normalised', label: 'Normalised role name' }, { key: 'employer_name_raw', label: 'Employer as published' }, { key: 'advert_count', label: 'Grouped adverts', numeric: true }, { key: 'first_posted_date', label: 'First posted' }, { key: 'last_posted_date', label: 'Last posted' }, { key: 'distinct_salary_periods', label: 'Distinct salary periods', numeric: true }, { key: 'job_references', label: 'Source job references' }]
useHead({ title: 'Pay and workforce · SectorTrace' })
</script>
<template>
  <section class="space-y-6"><header class="st-page-header"><p class="atlas-eyebrow">Evidence</p><h1>Pay and workforce</h1><p>Choose a question, then read the source’s figures, periods and limitations.</p></header><p class="atlas-caveat">Accounts, advertised offers, statutory rates and workforce estimates describe different populations and periods. They are not combined into a pay score, converted between pay periods or attributed across sources.</p>
    <div v-if="invalid" role="status" class="atlas-panel atlas-panel-body"><h2>This pay view is not recognised</h2><button type="button" class="atlas-button" @click="filters.setAll({ provider_key: get('provider_key') || undefined })">Choose a supported question</button></div>
    <template v-else><div v-if="active" class="space-y-3"><button type="button" class="atlas-button" @click="filters.setAll({ ...filters.all(), lens: undefined, source: undefined, record: undefined, pay_offset: undefined })">All pay and workforce questions</button><h2>{{ active.title }}</h2><p>{{ active.description }}</p></div>
      <section v-if="active" class="atlas-panel atlas-panel-body space-y-3" aria-label="Pay source filters"><div class="st-pay-filters"><StEntityPicker v-if="active.provider" kind="provider" label="Provider" empty-label="All returned providers" :model-value="get('provider_key')" @update:model-value="setFilter('provider_key', $event)" /><template v-if="active.years"><label>Account year from<input type="text" inputmode="numeric" maxlength="4" :value="get('year_from')" @change="setFilter('year_from', ($event.target as HTMLInputElement).value)"></label><label>Account year to<input type="text" inputmode="numeric" maxlength="4" :value="get('year_to')" @change="setFilter('year_to', ($event.target as HTMLInputElement).value)"></label></template><label v-if="active.role">Role or source label contains<input type="search" :value="get('role')" list="pay-source-roles" @change="setFilter('role', ($event.target as HTMLInputElement).value)"><datalist id="pay-source-roles"><option v-for="role in payload?.filters_available?.roles ?? []" :key="role" :value="role" /></datalist></label><label v-if="active.unit">Pay unit<select :value="get('pay_unit')" @change="setFilter('pay_unit', ($event.target as HTMLSelectElement).value)"><option value="">All source units</option><option v-if="get('pay_unit') && !(payload?.filters_available?.pay_units ?? []).includes(get('pay_unit'))" :value="get('pay_unit')">{{ get('pay_unit') }}</option><option v-for="unit in payload?.filters_available?.pay_units ?? []" :key="unit" :value="unit">{{ unit }}</option></select></label></div>
      <p v-if="!active.provider && get('provider_key')" class="atlas-footnote">The provider selection {{ get('provider_key') }} is retained in this link but does not filter or identify these observations.</p><p v-if="!active.years && (get('year_from') || get('year_to'))" class="atlas-footnote">Account-year bounds are retained for the charity view and do not filter this source.</p><p v-if="(!active.role && get('role')) || (!active.unit && get('pay_unit'))" class="atlas-footnote">Role or pay-unit selections unsupported by this question are retained in the link and are not applied.</p><p v-if="active.role" class="atlas-footnote">Role suggestions come from the current API provider/year scope before role and unit filtering. Suggestions can belong to another source in that response.</p><button type="button" class="atlas-button" @click="filters.setAll({ lens: active.key, source: active.group })">Clear source filters</button></section>
      <p v-if="invalidYear" role="status">Use four-digit account years, with the first year no later than the last.</p><p v-else-if="invalidUnit" role="status">The pay unit is not recognised. Choose a unit supplied by the source filter.</p>
      <StEvidenceState v-else :pending="pending" :error="error" @retry="refresh"><template v-if="!active"><p v-if="get('source')" class="atlas-footnote">Questions within the selected source group. <button class="atlas-button" type="button" @click="filters.set('source', undefined)">Show every question</button></p><ul class="st-pay-questions"><li v-for="lens in questions" :key="lens.key"><h2>{{ lens.question }}</h2><p>{{ lens.description }}</p><button class="atlas-button" type="button" :disabled="!available(lens.group, lens.array)" @click="choose(lens.key)">Read {{ lens.title.toLowerCase() }}</button><p v-if="!available(lens.group, lens.array)" class="atlas-footnote">This source group is not supplied by the response.</p></li></ul></template><template v-else-if="payload"><p v-if="!available(active.group, active.array)" role="status">The selected evidence array is not declared in this response’s source groups.</p><p v-else-if="observations === null" role="status">The selected source array was not supplied. This is not an empty dataset.</p><template v-else><StPayRecords :key="active.key" :lens="active" :rows="observations" :query="query" :caveats="caveats" /><section v-if="active.key === 'adverts'" class="space-y-3"><h2>Repeat-advertised-role candidates</h2><p>These groups are candidates for reading the named adverts. They are not a vacancy count or a finding about recruitment. Mixed salary periods are not compared.</p><p v-if="get('pay_unit')" class="atlas-footnote">A pay-unit filter removes these mixed-source-period groups. Clear the unit to read the returned candidates.</p><StEvidenceTable v-else :columns="repeatColumns" :rows="repeatRows" caption="Returned repeat-advertised-role candidates" /><p v-if="!get('pay_unit') && !repeatRows?.length">No candidate groups were returned.</p><p class="atlas-footnote">The grouped response does not supply per-advert URLs, retrieval dates or hashes. Inspect individual adverts for the metadata actually returned.</p></section><StCaveat v-for="(text, key) in caveats" :key="key" :text="text" /></template></template></StEvidenceState>
    </template>
  </section>
</template>
<style scoped>
.st-pay-questions { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: 20px; }
.st-pay-questions li { padding: 20px; border: 1px solid var(--border-subtle); background: var(--surface-panel); }
.st-pay-questions h2 { font-size: 18px; margin-bottom: 12px; }
.st-pay-questions p { font-size: 13px; color: var(--text-muted); margin-bottom: 16px; }
.st-pay-filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 230px), 1fr)); gap: 16px; }
.st-pay-filters label { display: grid; gap: 6px; min-width: 0; font-size: 13px; }
.st-pay-filters input, .st-pay-filters select { min-width: 0; width: 100%; min-height: 44px; padding: 8px 10px; border: 1px solid var(--border-control); border-radius: 4px; }
</style>
