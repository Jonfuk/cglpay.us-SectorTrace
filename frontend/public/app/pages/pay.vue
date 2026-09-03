<script setup lang="ts">
import type { Column } from '~/components/StEvidenceTable.vue'
import type { PayResponse, StatutoryPayRate } from '~/types/api'

// Pay route. The campaign's central, most caveat-heavy evidence. Evidence
// layers stay SEPARATE arrays — nothing here is combined into a rate, ratio, or
// score. Parity target: legacy `public/js/pages/pay.js`. This stage renders the
// statutory pay-rate series with provenance and the full caveat set; the other
// pay arrays are added in a follow-up while keeping each layer distinct.
const api = usePublicApi()
const filters = useFilterState()

// `pay_unit` is one of the legacy filters (hourly / annual / other). It narrows
// rows; it never combines sources. Bound to the URL so the filtered view is a
// link.
const payUnit = computed({
  get: () => (filters.get('pay_unit') as string) ?? '',
  set: (v: string) => { void filters.set('pay_unit', v || undefined) },
})

const { data, pending, error } = await useDataRoute<PayResponse>('public-pay', (f) =>
  api.pay({ query: f }),
)

const rates = computed<StatutoryPayRate[]>(() => data.value?.statutory_pay_rates ?? [])

const columns: Column<StatutoryPayRate>[] = [
  { key: 'period_label', label: 'Period' },
  { key: 'effective_from', label: 'Effective from', mono: true },
  { key: 'band_label', label: 'Band' },
  { key: 'band_role', label: 'Role' },
  { key: 'value_text', label: 'Rate' },
  { key: 'source_url', label: 'Source', link: true },
]

useHead({ title: 'SectorTrace — Pay' })
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Pay</h1>
      <p class="opacity-70 max-w-2xl">
        Every pay signal is kept in its own evidence layer. Nothing is averaged
        across sources or turned into a single rate.
      </p>
    </div>

    <div class="flex items-center gap-3">
      <label class="text-sm opacity-70" for="pay-unit">Pay unit</label>
      <select
        id="pay-unit"
        v-model="payUnit"
        class="text-sm border border-black/15 dark:border-white/15 rounded px-2 py-1 bg-transparent"
      >
        <option value="">All</option>
        <option value="hourly">Hourly</option>
        <option value="annual">Annual</option>
        <option value="other">Other</option>
      </select>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading pay evidence…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <UCard>
        <template #header>
          <span class="text-sm font-medium">Statutory pay rates</span>
        </template>
        <StEvidenceTable
          v-if="rates.length"
          :columns="columns"
          :rows="rates"
          row-key="effective_from"
        />
        <StEmptyState v-else />
      </UCard>

      <UCard v-if="data?.caveats">
        <template #header>
          <span class="text-sm font-medium">How to read these figures</span>
        </template>
        <div class="space-y-2">
          <StCaveat v-for="(text, key) in data.caveats" :key="key" :text="text" />
        </div>
      </UCard>
    </template>
  </section>
</template>
