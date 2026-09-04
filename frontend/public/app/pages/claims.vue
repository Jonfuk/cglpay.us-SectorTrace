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

function citationLabel(citation: ClaimRow['citations'][number]): string {
  return citation.resolved?.label ?? `${citation.table ?? 'Evidence'}: ${citation.key ?? '—'}`
}

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

        <details v-if="claim.citations?.length" class="mt-4 border-t border-black/10 dark:border-white/10 pt-3">
          <summary class="cursor-pointer text-sm font-medium">
            Supporting evidence ({{ claim.citations.length }})
          </summary>
          <ul class="mt-3 space-y-2 text-sm">
            <li v-for="(citation, i) in claim.citations" :key="`${citation.table}-${citation.key}-${i}`">
              <template v-if="citation.resolved">
                <StLink v-if="citation.resolved.url" :href="citation.resolved.url">
                  {{ citationLabel(citation) }}
                </StLink>
                <span v-else>{{ citationLabel(citation) }}</span>
                <span class="opacity-60"> · {{ citation.table ?? 'evidence' }}</span>
              </template>
              <span v-else class="opacity-70">
                {{ citation.table ?? 'Evidence' }}: {{ citation.key ?? '—' }} — cited row no longer held
              </span>
            </li>
          </ul>
        </details>

        <template #footer>
          <div class="text-xs opacity-60 flex flex-wrap gap-x-4 gap-y-1">
            <span>{{ claim.citations?.length ?? 0 }} citation(s)</span>
            <span v-if="claim.published_by ?? claim.created_by">approved by {{ claim.published_by ?? claim.created_by }}</span>
            <span v-if="claim.published_at ?? claim.created_at" class="font-mono">{{ claim.published_at ?? claim.created_at }}</span>
            <span v-if="claim.note">{{ claim.note }}</span>
          </div>
        </template>
      </UCard>

      <StCaveat v-if="data?.caveat" :text="data.caveat" />
    </template>
  </section>
</template>
