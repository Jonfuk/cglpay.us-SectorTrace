<script setup lang="ts">
import type { ContractPayload, PaymentPayload } from '~/types/contracts'
const api = usePublicApi()
const filters = useFilterState()
const get = (key: string) => { const value = filters.get(key); return Array.isArray(value) ? value[0] ?? '' : value ?? '' }
const lens = computed(() => get('lens') || 'notices')
const validLens = computed(() => ['notices', 'patterns', 'payments'].includes(lens.value))
const payments = computed(() => lens.value === 'payments')
const authority = computed(() => payments.value ? get('authority_ons_code') || get('buyer_ons_code') : get('buyer_ons_code'))
const filterKeys = ['provider_key', 'buyer_ons_code', 'year_from', 'year_to', 'q', 'since_retrieved_at'] as const
const limit = computed(() => { const value = Number(get('limit') || (payments.value ? 500 : 100)); return Number.isSafeInteger(value) ? Math.min(5000, Math.max(1, value)) : 100 })
const offset = computed(() => { const value = Number(get('offset') || 0); return Number.isSafeInteger(value) ? Math.max(0, value) : 0 })
const query = computed<Record<string, string | number | boolean | undefined>>(() => payments.value
  ? { provider_key: get('provider_key') || undefined, authority_ons_code: authority.value || undefined, limit: limit.value }
  : { ...Object.fromEntries(filterKeys.map(key => [key, get(key) || undefined])), psr_only: ['true', '1'].includes(get('psr_only')), limit: limit.value, offset: offset.value })
const invalidYear = computed(() => !payments.value && (['year_from', 'year_to'].some(key => get(key) && !/^\d{4}$/.test(get(key))) || (get('year_from') && get('year_to') && get('year_from') > get('year_to'))))
const signature = computed(() => `${payments.value ? 'payments' : 'notices'}:${JSON.stringify(query.value)}:${validLens.value}:${Boolean(invalidYear.value)}`)
const { data, pending, error, refresh } = await useAsyncData('public-procurement-workspace', async (_app, { signal }) => {
  const key = signature.value
  if (!validLens.value || invalidYear.value) return null
  if (payments.value) return { key, kind: 'payments' as const, response: await api.get<PaymentPayload>('/council_spend', { query: query.value, signal }) }
  return { key, kind: 'notices' as const, response: await api.get<ContractPayload>('/contracts', { query: query.value, signal }) }
}, { watch: [signature] })
const current = computed(() => !pending.value && !error.value && data.value?.key === signature.value ? data.value : null)
const notices = computed(() => current.value?.kind === 'notices' ? current.value.response : null)
const spending = computed(() => current.value?.kind === 'payments' ? current.value.response : null)
let write = Promise.resolve()
function setFilter(key: string, value: string) {
  const next = write.then(async () => { await filters.setAll({ ...filters.all(), [key]: value || undefined, ...(key === 'authority_ons_code' ? { buyer_ons_code: undefined } : {}), offset: undefined, notice_id: undefined, file_url: undefined, row_index: undefined, payment_authority: undefined, aggregate: undefined }); await nextTick() })
  write = next.catch(() => {})
  return next
}
function setLens(value: string) { return filters.set('lens', value) }
const ignoredPaymentFilters = computed(() => ['q', 'year_from', 'year_to', 'since_retrieved_at', 'psr_only', 'offset'].filter(key => get(key)).length > 0)
useHead({ title: 'Contracts and payments · SectorTrace' })
</script>
<template>
  <section class="space-y-6">
    <header class="st-page-header"><p class="atlas-eyebrow">Evidence</p><h1>Contracts and payments</h1><p>Read published procurement notices and council payment records with their source context.</p></header>
    <p class="atlas-caveat">Notice values may be estimates, ceilings or framework values. They do not establish spending, provider income or the value of distinct awards. Council payment lines describe a separate source.</p>
    <nav class="st-lens-nav" aria-label="Procurement evidence views"><button v-for="[key, label] in [['notices', 'Notices'], ['patterns', 'Patterns'], ['payments', 'Payments']]" :key="key" class="atlas-button" type="button" :aria-pressed="lens === key" @click="setLens(key!)">{{ label }}</button></nav>
    <p v-if="!validLens" role="status">This evidence view is not recognised. Choose Notices, Patterns or Payments.</p>
    <template v-else>
      <section class="atlas-panel atlas-panel-body space-y-4" aria-label="Procurement filters"><div class="st-contract-filters"><StEntityPicker kind="provider" label="Provider" empty-label="All tracked and unmatched suppliers" :model-value="get('provider_key')" @update:model-value="setFilter('provider_key', $event)" /><StEntityPicker kind="authority" :label="payments ? 'Paying authority' : 'Buyer authority'" empty-label="All authorities and unmatched names" :model-value="authority" @update:model-value="setFilter(payments ? 'authority_ons_code' : 'buyer_ons_code', $event)" />
      <template v-if="!payments"><label>Search buyer or supplier name<input type="search" :value="get('q')" @change="setFilter('q', ($event.target as HTMLInputElement).value)"></label><label>Publication year from<input type="text" inputmode="numeric" maxlength="4" :value="get('year_from')" @change="setFilter('year_from', ($event.target as HTMLInputElement).value)"></label><label>Publication year to<input type="text" inputmode="numeric" maxlength="4" :value="get('year_to')" @change="setFilter('year_to', ($event.target as HTMLInputElement).value)"></label><label>Retrieved since (ISO date or timestamp)<input type="text" :value="get('since_retrieved_at')" @change="setFilter('since_retrieved_at', ($event.target as HTMLInputElement).value)"></label><label class="st-check"><input type="checkbox" :checked="['true', '1'].includes(get('psr_only'))" @change="setFilter('psr_only', ($event.target as HTMLInputElement).checked ? 'true' : '')">PSR notices only</label></template></div>
      <p v-if="payments" class="atlas-footnote">Authority and provider apply to payment lines. Files use authority only. No date filter applies.<span v-if="ignoredPaymentFilters"> Notice search, date and pagination selections are retained in the link for the notice views and are not applied to payments.</span></p><p v-else class="atlas-footnote">Name search checks buyer and supplier names, not notice titles. Year bounds use publication dates. Retrieved since uses the collection timestamp. PSR means a published Provider Selection Regime basis.</p><button class="atlas-button" type="button" @click="filters.setAll({ lens })">Clear filters</button></section>
      <p v-if="invalidYear" role="status">Use four-digit publication years, with the first year no later than the last.</p>
      <StEvidenceState v-else :pending="pending" :error="error" @retry="refresh"><template v-if="notices"><StContractNotices v-if="lens === 'notices'" :payload="notices" :query="query" /><LazyStContractPatterns v-else :payload="notices" :query="query" /><details><summary>Source limitations</summary><StCaveat v-for="(text, key) in notices.caveats ?? {}" :key="key" :text="text" /></details></template><LazyStCouncilPayments v-else-if="spending" :payload="spending" :query="query" /></StEvidenceState>
    </template>
  </section>
</template>
<style scoped>
.st-contract-filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 230px), 1fr)); gap: 16px; }
.st-contract-filters label { display: grid; gap: 6px; min-width: 0; font-size: 13px; }
.st-contract-filters input:not([type='checkbox']) { width: 100%; min-width: 0; min-height: 44px; padding: 8px 10px; border: 1px solid var(--border-control); border-radius: 4px; }
.st-contract-filters .st-check { display: flex; align-items: center; gap: 10px; min-height: 44px; }
</style>
