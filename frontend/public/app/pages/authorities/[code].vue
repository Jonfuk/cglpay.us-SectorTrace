<script setup lang="ts">
import { computed } from 'vue'
import type { AuthorityResponse } from '~/types/api'

// Authority detail — the entry point for one local authority's evidence. It
// shows the authority's identity and links out to its parameter-driven views
// (coverage, contract diary by buyer ONS code, discrepancies). Parity target:
// legacy `public/js/pages/authority.js`.
const route = useRoute()
const api = usePublicApi()

const code = computed(() => String(route.params.code ?? ''))

const { data, pending, error } = await useAsyncData<AuthorityResponse | null>(
  () => `authority-${code.value}`,
  () => api.authority(code.value),
  { default: () => null, watch: [code] },
)

const name = computed<string>(() => data.value?.authority?.name ?? code.value)

const scopedLinks = computed(() => [
  { to: `/coverage?ons_code=${encodeURIComponent(code.value)}`, label: 'Data coverage' },
  { to: `/diary?buyer_ons_code=${encodeURIComponent(code.value)}`, label: 'Contract diary' },
  { to: `/discrepancies?ons_code=${encodeURIComponent(code.value)}`, label: 'Source discrepancies' },
])

useHead(() => ({ title: `SectorTrace — ${name.value}` }))
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <NuxtLink to="/geography" class="text-xs opacity-60 hover:opacity-100">← Places</NuxtLink>
      <h1 class="text-2xl font-semibold">{{ name }}</h1>
      <p v-if="data?.authority" class="text-sm opacity-60">
        {{ data.authority.type ?? '' }}<span v-if="data.authority.region"> · {{ data.authority.region }}</span>
      </p>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading authority…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <nav class="flex flex-wrap gap-2">
        <NuxtLink
          v-for="link in scopedLinks"
          :key="link.to"
          :to="link.to"
          class="text-sm border border-black/15 dark:border-white/15 rounded px-3 py-1 hover:bg-black/5 dark:hover:bg-white/5"
        >
          {{ link.label }}
        </NuxtLink>
      </nav>

      <UCard v-if="data?.caveats">
        <template #header>
          <span class="text-sm font-medium">How to read this authority's figures</span>
        </template>
        <div class="space-y-2">
          <StCaveat v-for="(text, key) in data.caveats" :key="key" :text="text" />
        </div>
      </UCard>
    </template>
  </section>
</template>
