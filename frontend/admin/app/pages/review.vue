<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/AdminTable.vue'
import type { ReviewItem, ReviewItemsResponse } from '~/types/admin'

// Review — the review queue: items a human must adjudicate. Read-only in this
// stage (the decide actions land later). Status is URL-authoritative (?status=).
// Parity target: legacy admin `review`/`shell` review tab.
const api = useAdminApi()
const filters = useFilterState()

const status = computed({
  get: () => (filters.get('status') as string) ?? 'pending',
  set: (v: string) => { void filters.set('status', v || undefined) },
})

const { data, pending, error } = await useDataRoute<ReviewItemsResponse | null>(
  'admin-review',
  (f) => api.reviewItems({ query: { status: (f.status as string) || 'pending', ...f } }),
)

const items = computed<ReviewItem[]>(() => data.value?.items ?? [])

const columns: Column<ReviewItem>[] = [
  { key: 'id', label: 'ID', mono: true },
  { key: 'module', label: 'Module' },
  { key: 'item_type', label: 'Type' },
  { key: 'raw_value', label: 'Value' },
  { key: 'status', label: 'Status' },
]

useHead({ title: 'SectorTrace — Review queue' })
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold">Review queue</h1>

    <div class="flex items-center gap-3">
      <label class="text-sm opacity-70" for="status">Status</label>
      <select
        id="status"
        v-model="status"
        class="text-sm border border-black/15 dark:border-white/15 rounded px-2 py-1 bg-transparent"
      >
        <option value="pending">Pending</option>
        <option value="resolved">Resolved</option>
        <option value="all">All</option>
      </select>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading review queue…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <UCard v-else>
      <template #header>
        <span class="text-sm font-medium">{{ data?.total ?? items.length }} items</span>
      </template>
      <AdminTable v-if="items.length" :columns="columns" :rows="items" row-key="id" />
      <StEmptyState v-else />
    </UCard>
  </section>
</template>
