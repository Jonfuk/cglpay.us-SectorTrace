<script setup lang="ts">
import { computed } from 'vue'
import type { AnalysisOverviewResponse } from '~/types/admin'

// Analysis — the analysis platform overview: active release, worker state, and
// the quality boundary that keeps automated signals admin-only. Read-only.
// Parity target: legacy admin `analysis.js`.
const api = useAdminApi()

const { data, pending, error } = await useAsyncData<AnalysisOverviewResponse | null>(
  'admin-analysis-overview',
  () => api.analysisOverview(),
  { default: () => null },
)

const activeRelease = computed(() => data.value?.active_release ?? null)
const domains = computed(() => data.value?.domains ?? [])

useHead({ title: 'SectorTrace — Analysis' })
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold">Analysis platform</h1>

    <div v-if="pending" class="text-sm opacity-60">Loading analysis overview…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <UCard>
        <template #header><span class="text-sm font-medium">Active release</span></template>
        <div v-if="activeRelease" class="text-sm font-mono">
          {{ (activeRelease as Record<string, unknown>).release_id ?? 'active' }}
        </div>
        <StEmptyState v-else title="No active release" message="No analysis release is currently active." />
      </UCard>

      <UCard>
        <template #header><span class="text-sm font-medium">Executor</span></template>
        <StatusPill
          :label="data?.executor ?? '—'"
          :level="data?.executor === 'worker_online' ? 'ok' : 'warn'"
        />
      </UCard>

      <UCard v-if="domains.length">
        <template #header><span class="text-sm font-medium">Domains ({{ domains.length }})</span></template>
        <ul class="text-sm space-y-1">
          <li v-for="(d, i) in domains" :key="i">
            {{ (d as Record<string, unknown>).label ?? (d as Record<string, unknown>).domain_id ?? '—' }}
          </li>
        </ul>
      </UCard>

      <p v-if="data?.quality_boundary" class="text-xs opacity-60">
        {{ data.quality_boundary }}
      </p>
    </template>
  </section>
</template>
