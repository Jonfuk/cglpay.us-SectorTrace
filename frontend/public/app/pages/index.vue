<script setup lang="ts">
import type { MetaResponse } from '~/types/api'

// Overview route foundation. It exercises the full data path end-to-end:
// typed public API client -> same-origin transport (dedup + cancellation) ->
// `/api/v1/meta`. The evidence-dense overview content is ported in a later
// stage against the legacy `overview.js` oracle; this establishes the wiring
// and the release-identity display.
const api = usePublicApi()

// A build-time-static shell page: the title and frame are prerendered, and the
// mutable release identity is fetched in the browser (never baked into the
// static asset). `useAsyncData` is client-only here because ssr is disabled.
const { data: meta, pending, error } = await useAsyncData<MetaResponse | null>(
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
        'Public-domain evidence for the substance misuse sector: pay, contracts, providers, treatment, and documents, each with full provenance.',
    },
  ],
})
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Evidence atlas</h1>
      <p class="opacity-70 max-w-2xl">
        A defensible view of the substance misuse sector. Nothing here is
        inferred: every figure traces to exact public-domain bytes.
      </p>
    </div>

    <UCard>
      <template #header>
        <span class="text-sm font-medium">Release identity</span>
      </template>

      <div v-if="pending" class="text-sm opacity-60">Loading release identity…</div>
      <div v-else-if="error" class="text-sm text-red-600">
        Release identity is unavailable right now.
      </div>
      <BuildIdentity
        v-else-if="meta"
        :revision="meta.revision"
        :migration="meta.schema.latest_migration"
        :last-fetch="meta.data.last_fetch_at"
      />
    </UCard>
  </section>
</template>
