<script setup lang="ts">
import { computed } from 'vue'
import type { ClaimRow, ClaimsResponse } from '~/types/api'

// Claims route. Published claims, each shown with its citations and its own
// caveats — a claim is never presented without the evidence it rests on.
// Parity target: legacy `public/js/pages/claims.js`.
const api = usePublicApi()

const { data, pending, error } = await useDataRoute<ClaimsResponse>(
  'public-claims',
  () => api.claims(),
)

const claims = computed<ClaimRow[]>(() => data.value?.claims ?? [])

useHead({ title: 'SectorTrace — Claims' })
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Claims</h1>
      <p class="opacity-70 max-w-2xl">
        Published claims, each with the citations it rests on and the caveats
        that bound it.
      </p>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading claims…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <StEmptyState v-if="!claims.length" />
      <UCard v-for="claim in claims" v-else :key="claim.id">
        <p class="text-base">{{ claim.claim_text ?? '—' }}</p>

        <div v-if="claim.caveats?.length" class="mt-3 space-y-1">
          <StCaveat v-for="(text, i) in claim.caveats" :key="i" :text="text" />
        </div>

        <template #footer>
          <div class="text-xs opacity-60 flex flex-wrap gap-x-4 gap-y-1">
            <span>{{ claim.citations?.length ?? 0 }} citation(s)</span>
            <span v-if="claim.created_by">by {{ claim.created_by }}</span>
            <span v-if="claim.created_at" class="font-mono">{{ claim.created_at }}</span>
          </div>
        </template>
      </UCard>

      <StCaveat v-if="data?.caveat" :text="data.caveat" />
    </template>
  </section>
</template>
