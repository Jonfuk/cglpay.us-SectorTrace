<script setup lang="ts">
import { computed, ref } from 'vue'
import type { CensusItem, CensusListingResponse } from '~/types/admin'
import { TransportError } from '~/lib/transport'

// Workforce census verification. Each parsed metric is checked by a human
// against the archived source page and verified or rejected, recorded against
// the named reviewer. Verification never edits the figure — it only records
// whether the parse matches the source. Parity target: legacy admin `census.js`.
// Status is URL-authoritative (?status=).
const api = useAdminApi()
const filters = useFilterState()
const reviewer = useReviewer()
const toast = useToast()

const status = computed({
  get: () => (filters.get('status') as string) ?? 'unchecked',
  set: (v: string) => { void filters.set('status', v || undefined) },
})

const { data, pending, error, refresh } = await useDataRoute<CensusListingResponse | null>(
  'admin-census',
  (f) => api.census({ query: { status: (f.status as string) || 'unchecked', ...f } }),
)

const items = computed<CensusItem[]>(() => data.value?.items ?? [])
const busy = ref<string | null>(null)

function requireReviewer(): boolean {
  if (reviewer.isSet.value) return true
  toast.add({ title: 'Set your reviewer name first', color: 'warning' })
  return false
}

async function verify(item: CensusItem) {
  if (!requireReviewer()) return
  if (!window.confirm(`Verify this census figure matches its source?\n\n${item.metric} = ${item.value} ${item.unit ?? ''}`)) return
  busy.value = item.key
  try {
    await api.verifyCensus({ key: item.key, verifiedBy: reviewer.name.value })
    toast.add({ title: 'Verified', color: 'success' })
    await refresh()
  } catch (e) {
    toast.add({ title: 'Verify failed', description: e instanceof TransportError ? e.message : String(e), color: 'error' })
  } finally {
    busy.value = null
  }
}

async function reject(item: CensusItem) {
  if (!requireReviewer()) return
  const note = window.prompt(`Reject this census figure? Optional reason:\n\n${item.metric} = ${item.value}`)
  if (note === null) return
  busy.value = item.key
  try {
    await api.rejectCensus({ key: item.key, rejectedBy: reviewer.name.value, note: note || undefined })
    toast.add({ title: 'Rejected', color: 'success' })
    await refresh()
  } catch (e) {
    toast.add({ title: 'Reject failed', description: e instanceof TransportError ? e.message : String(e), color: 'error' })
  } finally {
    busy.value = null
  }
}

useHead({ title: 'SectorTrace — Census' })
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold">Workforce census</h1>
    <p class="opacity-70 max-w-2xl text-sm">
      Each parsed figure is checked against its archived source and verified or
      rejected. Verification records whether the parse matches the source — it
      never edits the figure.
    </p>

    <div class="flex items-center gap-3">
      <label class="text-sm opacity-70" for="status">Status</label>
      <select
        id="status"
        v-model="status"
        class="text-sm border border-black/15 dark:border-white/15 rounded px-2 py-1 bg-transparent"
      >
        <option value="unchecked">Unchecked</option>
        <option value="verified">Verified</option>
        <option value="rejected">Rejected</option>
      </select>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading census rows…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <UCard v-else>
      <template #header>
        <span class="text-sm font-medium">{{ data?.total ?? items.length }} rows · {{ status }}</span>
      </template>

      <StEmptyState v-if="!items.length" />
      <ul v-else class="divide-y divide-black/5 dark:divide-white/5">
        <li v-for="item in items" :key="item.key" class="py-3 flex items-start gap-4">
          <div class="min-w-0 flex-1 space-y-1">
            <div class="text-sm font-medium">
              {{ item.metric ?? '—' }}
              <span class="opacity-60">· {{ item.census_year ?? '—' }}</span>
            </div>
            <div class="text-sm">
              {{ item.value ?? '—' }} <span class="opacity-60">{{ item.unit ?? '' }}</span>
              <span v-if="item.workforce_segment" class="opacity-60"> · {{ item.workforce_segment }}</span>
            </div>
            <StLink :href="item.source?.source_url">source page</StLink>
          </div>
          <div v-if="status === 'unchecked'" class="flex gap-2 shrink-0">
            <UButton
              size="xs"
              color="primary"
              :loading="busy === item.key"
              :disabled="busy !== null"
              @click="verify(item)"
            >Verify</UButton>
            <UButton
              size="xs"
              color="neutral"
              variant="outline"
              :disabled="busy !== null"
              @click="reject(item)"
            >Reject</UButton>
          </div>
        </li>
      </ul>
    </UCard>
  </section>
</template>
