<script setup lang="ts">
import { computed } from 'vue'
import type { CandidateCountsResponse, HealthResponse } from '~/types/admin'

// Mission control — the operator's at-a-glance overview. It pulls the health
// payload and candidate counts and surfaces the numbers an operator acts on:
// unapplied migrations, undecided candidates awaiting a human decision.
const api = useAdminApi()

const { data: health, pending: healthPending } = await useAsyncData<HealthResponse | null>(
  'admin-overview-health',
  () => api.health(),
  { default: () => null },
)
const { data: counts, pending: countsPending } = await useAsyncData<CandidateCountsResponse | null>(
  'admin-overview-counts',
  () => api.candidateCounts(),
  { default: () => null },
)

const unapplied = computed(() => health.value?.warehouse?.unapplied ?? [])
const totalUndecided = computed(() => {
  const kinds = counts.value?.kinds ?? {}
  return Object.values(kinds).reduce((sum, k) => sum + (k.undecided ?? 0), 0)
})

useHead({ title: 'SectorTrace — Operations' })
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold">Mission control</h1>

    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <UCard>
        <div class="text-xs uppercase tracking-wide opacity-60">Backend</div>
        <div class="text-lg font-medium">
          {{ healthPending ? '…' : (health?.warehouse?.backend ?? '—') }}
        </div>
      </UCard>
      <UCard>
        <div class="text-xs uppercase tracking-wide opacity-60">Unapplied migrations</div>
        <div class="text-lg font-medium">
          <StatusPill
            :label="healthPending ? '…' : unapplied.length"
            :level="unapplied.length ? 'warn' : 'ok'"
          />
        </div>
      </UCard>
      <UCard>
        <div class="text-xs uppercase tracking-wide opacity-60">Undecided candidates</div>
        <div class="text-lg font-medium">
          <StatusPill
            :label="countsPending ? '…' : totalUndecided"
            :level="totalUndecided ? 'warn' : 'neutral'"
          />
        </div>
      </UCard>
      <UCard>
        <div class="text-xs uppercase tracking-wide opacity-60">Extensions</div>
        <div class="text-lg font-medium">
          {{ healthPending ? '…' : (health?.extensions?.filter((e) => e.installed).length ?? 0) }}
          installed
        </div>
      </UCard>
    </div>

    <div class="flex flex-wrap gap-2">
      <NuxtLink
        to="/review"
        class="text-sm border border-black/15 dark:border-white/15 rounded px-3 py-1 hover:bg-black/5 dark:hover:bg-white/5"
      >Review queue →</NuxtLink>
      <NuxtLink
        to="/candidates"
        class="text-sm border border-black/15 dark:border-white/15 rounded px-3 py-1 hover:bg-black/5 dark:hover:bg-white/5"
      >Candidates →</NuxtLink>
      <NuxtLink
        to="/health"
        class="text-sm border border-black/15 dark:border-white/15 rounded px-3 py-1 hover:bg-black/5 dark:hover:bg-white/5"
      >Full health →</NuxtLink>
    </div>
  </section>
</template>
