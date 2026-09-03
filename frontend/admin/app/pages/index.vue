<script setup lang="ts">
// Mission-control foundation. It confirms the admin data path (typed admin
// client -> same-origin transport) reaches `/api/v1/meta`; the full operator
// dashboards are ported in later stages against the legacy modules as oracles.
interface MetaLike {
  environment?: string
  backend?: string
  schema?: { latest_migration?: number | null }
}

const api = useAdminApi()
const { data: meta, pending, error } = await useAsyncData<MetaLike | null>(
  'admin-meta',
  () => api.v1<MetaLike>('/meta'),
  { default: () => null },
)

useHead({ title: 'SectorTrace — Operations' })
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold">Mission control</h1>

    <UCard>
      <template #header>
        <span class="text-sm font-medium">Warehouse identity</span>
      </template>
      <div v-if="pending" class="text-sm opacity-60">Loading…</div>
      <div v-else-if="error" class="text-sm text-red-600">Unavailable.</div>
      <dl v-else-if="meta" class="grid grid-cols-3 gap-4 text-sm">
        <div>
          <dt class="opacity-60">Environment</dt>
          <dd class="font-mono">{{ meta.environment ?? '—' }}</dd>
        </div>
        <div>
          <dt class="opacity-60">Backend</dt>
          <dd class="font-mono">{{ meta.backend ?? '—' }}</dd>
        </div>
        <div>
          <dt class="opacity-60">Schema</dt>
          <dd class="font-mono">{{ meta.schema?.latest_migration ?? '—' }}</dd>
        </div>
      </dl>
    </UCard>
  </section>
</template>
