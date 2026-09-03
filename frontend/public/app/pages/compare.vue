<script setup lang="ts">
import { computed } from 'vue'
import type { CompareResponse } from '~/types/api'

// Compare route. Parallel series for two or more authorities or providers, side
// by side. The comparison never combines the entities into a single ranked
// figure — each keeps its own series and provenance. Entities are read from the
// URL as repeated `?provider_key=` / `?ons_code=`. Parity target: legacy
// `public/js/pages/compare.js`.
const api = usePublicApi()
const filters = useFilterState()

function asList(v: string | string[] | undefined): string[] {
  if (!v) return []
  return Array.isArray(v) ? v : [v]
}

const providerKeys = computed(() => asList(filters.get('provider_key')))
const onsCodes = computed(() => asList(filters.get('ons_code')))
const selected = computed(() => providerKeys.value.length + onsCodes.value.length)

const { data, pending, error } = await useDataRoute<CompareResponse | null>(
  'public-compare',
  (f) => {
    const n = asList(f.provider_key).length + asList(f.ons_code).length
    if (n < 2) return Promise.resolve(null)
    return api.compare({ query: f })
  },
)

const authorities = computed(() => data.value?.authorities ?? [])
const providers = computed(() => data.value?.providers ?? [])
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Compare</h1>
      <p class="opacity-70 max-w-2xl">
        Two or more authorities or providers side by side. Each keeps its own
        series; nothing is combined into a single ranked figure.
      </p>
    </div>

    <StEmptyState
      v-if="selected < 2"
      title="Select at least two to compare"
      message="Add two or more entities (?provider_key=…&provider_key=… or ?ons_code=…) to compare them."
    />
    <div v-else-if="pending" class="text-sm opacity-60">Loading comparison…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <UCard v-if="authorities.length">
        <template #header>
          <span class="text-sm font-medium">Authorities ({{ authorities.length }})</span>
        </template>
        <ul class="text-sm space-y-1">
          <li v-for="(a, i) in authorities" :key="i">
            {{ (a as Record<string, unknown>).name ?? (a as Record<string, unknown>).ons_code }}
          </li>
        </ul>
      </UCard>

      <UCard v-if="providers.length">
        <template #header>
          <span class="text-sm font-medium">Providers ({{ providers.length }})</span>
        </template>
        <ul class="text-sm space-y-1">
          <li v-for="(p, i) in providers" :key="i">
            {{ (p as Record<string, unknown>).provider_name ?? (p as Record<string, unknown>).canonical_name ?? (p as Record<string, unknown>).provider_key }}
          </li>
        </ul>
      </UCard>

      <StEmptyState
        v-if="!authorities.length && !providers.length"
      />
    </template>
  </section>
</template>
