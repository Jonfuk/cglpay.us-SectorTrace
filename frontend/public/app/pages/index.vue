<script setup lang="ts">
import type { MetaResponse, SummaryResponse } from '~/types/api'

// Overview route. Renders the landing-page figures from `/api/v1/summary` with
// the shared evidence kit: every figure keeps its caveat, a missing value shows
// as an em dash rather than a zero, and an unavailable load reads distinctly
// from an empty result. Parity target: legacy `public/js/pages/overview.js`.
const api = usePublicApi()

// ssr:false, so this runs in the browser. Mutable warehouse figures are fetched
// here, never baked into the static shell.
const { data: summary, pending, error } = await useAsyncData<SummaryResponse | null>(
  'public-summary',
  () => api.summary(),
  { default: () => null },
)

// Release identity is small and independent; a separate keyed fetch keeps it
// off the critical figures path and feeds the Vapor BuildIdentity component.
const { data: meta } = await useAsyncData<MetaResponse | null>(
  'public-meta',
  () => api.meta(),
  { default: () => null },
)

useHead({
  title: 'SectorTrace — Overview',
  meta: [
    {
      name: 'description',
      content:
        'Public-domain evidence for the substance misuse sector: providers, authorities, contracts, workforce, and treatment indicators, each with full provenance and caveats.',
    },
  ],
})
</script>

<template>
  <section class="space-y-8">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Evidence atlas</h1>
      <p class="opacity-70 max-w-2xl">
        A defensible view of the substance misuse sector. Nothing here is
        inferred: every figure traces to exact public-domain bytes, and each
        carries the caveat that bounds how it may be read.
      </p>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading the latest figures…</div>

    <StEmptyState
      v-else-if="error || !summary"
      variant="unavailable"
      title="Overview figures are unavailable"
    />

    <template v-else>
      <UCard>
        <template #header>
          <span class="text-sm font-medium">Providers &amp; authorities</span>
        </template>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-6">
          <StStat label="Providers" :value="summary.providers.total" />
          <StStat label="Target provider" :value="summary.providers.target" :format="false" />
          <StStat label="Authorities" :value="summary.authorities.total" />
          <StStat
            label="Authorities with contracts"
            :value="summary.authorities.with_contracts"
          />
        </div>
      </UCard>

      <UCard>
        <template #header>
          <span class="text-sm font-medium">Contracts</span>
        </template>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-6">
          <StStat label="Notices" :value="summary.contracts.total_notices" />
          <StStat
            label="Total value (GBP)"
            :value="summary.contracts.total_value_gbp"
            :caveat="summary.contracts.sum_caveat"
          />
          <StStat label="Direct awards" :value="summary.contracts.direct_awards" />
          <StStat
            label="Matched to a provider"
            :value="summary.contracts.matched_to_provider"
          />
        </div>
        <template #footer>
          <StCaveat :text="summary.contracts.caveat" />
        </template>
      </UCard>

      <UCard>
        <template #header>
          <span class="text-sm font-medium">Workforce &amp; treatment</span>
        </template>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-6">
          <StStat
            label="Latest census year"
            :value="summary.workforce.latest_census_year"
            :format="false"
            :caveat="summary.workforce.caveat"
          />
          <StStat
            label="Fingertips period"
            :value="summary.fingertips.latest_period"
            :format="false"
          />
          <StStat
            label="Indicators collected"
            :value="summary.fingertips.indicators_collected"
          />
        </div>
      </UCard>

      <UCard v-if="meta">
        <template #header>
          <span class="text-sm font-medium">Release identity</span>
        </template>
        <BuildIdentity
          :revision="meta.revision"
          :migration="meta.schema.latest_migration"
          :last-fetch="meta.data.last_fetch_at"
        />
      </UCard>
    </template>
  </section>
</template>
