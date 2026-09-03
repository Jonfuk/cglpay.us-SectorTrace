<script setup lang="ts">
import { computed } from 'vue'
import type { HealthResponse } from '~/types/admin'

// Health — the operator warehouse/extension/graph/document status detail.
// Parity target: legacy admin `health.js`.
const api = useAdminApi()

const { data, pending, error } = await useAsyncData<HealthResponse | null>(
  'admin-health',
  () => api.health(),
  { default: () => null },
)

const extensions = computed(() => data.value?.extensions ?? [])
const unapplied = computed(() => data.value?.warehouse?.unapplied ?? [])

useHead({ title: 'SectorTrace — Health' })
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold">Health</h1>

    <div v-if="pending" class="text-sm opacity-60">Loading health…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <UCard>
        <template #header><span class="text-sm font-medium">Warehouse</span></template>
        <dl class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <dt class="opacity-60">Backend</dt>
            <dd class="font-mono">{{ data?.warehouse?.backend ?? '—' }}</dd>
          </div>
          <div>
            <dt class="opacity-60">Applied migrations</dt>
            <dd class="font-mono">{{ data?.warehouse?.applied_migrations?.length ?? '—' }}</dd>
          </div>
          <div>
            <dt class="opacity-60">Unapplied</dt>
            <dd>
              <StatusPill :label="unapplied.length" :level="unapplied.length ? 'warn' : 'ok'" />
            </dd>
          </div>
          <div>
            <dt class="opacity-60">Size (bytes)</dt>
            <dd class="font-mono">{{ data?.warehouse?.bytes?.toLocaleString('en-GB') ?? '—' }}</dd>
          </div>
        </dl>
      </UCard>

      <UCard>
        <template #header><span class="text-sm font-medium">Extensions</span></template>
        <ul class="flex flex-wrap gap-2">
          <li v-for="ext in extensions" :key="ext.name">
            <StatusPill :label="ext.name" :level="ext.installed ? 'ok' : 'bad'" />
          </li>
        </ul>
      </UCard>
    </template>
  </section>
</template>
