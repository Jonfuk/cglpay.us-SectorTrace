<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ReviewItem, ReviewItemsResponse } from '~/types/admin'
import { TransportError } from '~/lib/transport'

// Review — the review queue with the decide actions (approve / reject). Every
// decision records the named reviewer; the server refuses a decision nobody is
// attached to. Read + decide only — this never acts on the decision itself,
// mirroring the server contract. Parity target: legacy admin review tab. Status
// is URL-authoritative (?status=).
const api = useAdminApi()
const filters = useFilterState()
const reviewer = useReviewer()
const toast = useToast()

const status = computed({
  get: () => (filters.get('status') as string) ?? 'pending',
  set: (v: string) => { void filters.set('status', v || undefined) },
})

const { data, pending, error, refresh } = await useDataRoute<ReviewItemsResponse | null>(
  'admin-review',
  (f) => api.reviewItems({ query: { status: (f.status as string) || 'pending', ...f } }),
)

const items = computed<ReviewItem[]>(() => data.value?.items ?? [])
const busy = ref<number | null>(null)

async function decide(item: ReviewItem, decision: 'approved' | 'rejected') {
  if (!reviewer.isSet.value) {
    toast.add({ title: 'Set your reviewer name first', color: 'warning' })
    return
  }
  const verb = decision === 'approved' ? 'Approve' : 'Reject'
  if (!window.confirm(`${verb} review item #${item.id}?\n\n${item.raw_value ?? ''}`)) return
  busy.value = item.id
  try {
    await api.decideReview({ id: item.id, decision, decidedBy: reviewer.name.value })
    toast.add({ title: `${verb}d`, color: 'success' })
    await refresh()
  } catch (e) {
    toast.add({ title: `${verb} failed`, description: e instanceof TransportError ? e.message : String(e), color: 'error' })
  } finally {
    busy.value = null
  }
}

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
        <option value="approved">Approved</option>
        <option value="rejected">Rejected</option>
        <option value="all">All</option>
      </select>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading review queue…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <UCard v-else>
      <template #header>
        <span class="text-sm font-medium">{{ data?.total ?? items.length }} items</span>
      </template>

      <StEmptyState v-if="!items.length" />
      <ul v-else class="divide-y divide-black/5 dark:divide-white/5">
        <li v-for="item in items" :key="item.id" class="py-3 flex items-start gap-4">
          <div class="min-w-0 flex-1 space-y-1">
            <div class="text-sm">
              <span class="font-mono opacity-60">#{{ item.id }}</span>
              <span class="ml-2">{{ item.raw_value ?? '—' }}</span>
            </div>
            <div class="text-xs opacity-60">
              {{ item.module ?? '—' }} · {{ item.item_type ?? '—' }} ·
              <StatusPill :label="item.status" />
            </div>
          </div>
          <div v-if="item.status === 'pending'" class="flex gap-2 shrink-0">
            <UButton
              size="xs"
              color="primary"
              :loading="busy === item.id"
              :disabled="busy !== null"
              @click="decide(item, 'approved')"
            >Approve</UButton>
            <UButton
              size="xs"
              color="neutral"
              variant="outline"
              :disabled="busy !== null"
              @click="decide(item, 'rejected')"
            >Reject</UButton>
          </div>
        </li>
      </ul>
    </UCard>
  </section>
</template>
