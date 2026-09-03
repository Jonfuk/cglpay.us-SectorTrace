<script setup lang="ts">
import { computed, ref } from 'vue'
import type { CandidateCountsResponse, CandidateItem, CandidatesListingResponse } from '~/types/admin'
import { TransportError } from '~/lib/transport'

// Candidates — discovery candidates awaiting a human decision, with the
// promote/reject actions. Nothing is promoted to evidence without a person:
// every action records the named reviewer, promote is one-at-a-time (it fetches
// and archives the document, so a list would make pretending cheap), and each
// action is confirmed before it is sent. Parity target: legacy admin
// `candidates.js`. The kind is URL-authoritative (?kind=).
const api = useAdminApi()
const filters = useFilterState()
const reviewer = useReviewer()
const toast = useToast()

const kind = computed({
  get: () => (filters.get('kind') as string) ?? 'cdp_document',
  set: (v: string) => { void filters.set('kind', v || undefined) },
})

const { data: counts, refresh: refreshCounts } = await useAsyncData<CandidateCountsResponse | null>(
  'admin-candidate-counts',
  () => api.candidateCounts(),
  { default: () => null },
)

const kindNames = computed(() => Object.keys(counts.value?.kinds ?? {}))

const { data, pending, error, refresh } = await useDataRoute<CandidatesListingResponse | null>(
  'admin-candidates',
  (f) => api.candidates({ query: { kind: (f.kind as string) || 'cdp_document', ...f } }),
)

const items = computed<CandidateItem[]>(() => data.value?.items ?? [])

// One in-flight action at a time per row, keyed by url.
const busy = ref<string | null>(null)

function requireReviewer(): boolean {
  if (reviewer.isSet.value) return true
  toast.add({ title: 'Set your reviewer name first', color: 'warning' })
  return false
}

async function afterWrite() {
  await Promise.all([refresh(), refreshCounts()])
}

async function promote(item: CandidateItem) {
  if (!item.url || !requireReviewer()) return
  if (!window.confirm(
    `Promote this candidate into the evidence base?\n\n${item.url}\n\nThis fetches and archives the document. It is not automatic and cannot be batched.`,
  )) return
  busy.value = item.url
  try {
    await api.promoteCandidate({ kind: kind.value, url: item.url, promotedBy: reviewer.name.value })
    toast.add({ title: 'Promoted', color: 'success' })
    await afterWrite()
  } catch (e) {
    toast.add({ title: 'Promote failed', description: e instanceof TransportError ? e.message : String(e), color: 'error' })
  } finally {
    busy.value = null
  }
}

async function reject(item: CandidateItem) {
  if (!item.url || !requireReviewer()) return
  const note = window.prompt(`Reject this candidate? Optional reason:\n\n${item.url}`)
  if (note === null) return // cancelled
  busy.value = item.url
  try {
    await api.rejectCandidate({ kind: kind.value, url: item.url, rejectedBy: reviewer.name.value, note: note || undefined })
    toast.add({ title: 'Rejected', color: 'success' })
    await afterWrite()
  } catch (e) {
    toast.add({ title: 'Reject failed', description: e instanceof TransportError ? e.message : String(e), color: 'error' })
  } finally {
    busy.value = null
  }
}

useHead({ title: 'SectorTrace — Candidates' })
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold">Candidates</h1>
    <p class="opacity-70 max-w-2xl text-sm">
      Discovery candidates awaiting a human decision. Nothing is promoted to
      evidence without a person; promote fetches and archives the document, one
      at a time, recorded against the named reviewer.
    </p>

    <div v-if="kindNames.length" class="flex items-center gap-3">
      <label class="text-sm opacity-70" for="kind">Kind</label>
      <select
        id="kind"
        v-model="kind"
        class="text-sm border border-black/15 dark:border-white/15 rounded px-2 py-1 bg-transparent"
      >
        <option v-for="k in kindNames" :key="k" :value="k">
          {{ k }} ({{ counts?.kinds[k]?.undecided ?? 0 }} undecided)
        </option>
      </select>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading candidates…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <UCard v-else>
      <template #header>
        <span class="text-sm font-medium">
          {{ data?.total ?? items.length }} {{ data?.status ?? '' }} · {{ kind }}
        </span>
      </template>

      <StEmptyState v-if="!items.length" />
      <ul v-else class="divide-y divide-black/5 dark:divide-white/5">
        <li v-for="item in items" :key="item.url ?? ''" class="py-3 flex items-start gap-4">
          <div class="min-w-0 flex-1 space-y-1">
            <div class="text-sm font-medium">{{ item.authority_name ?? '—' }}</div>
            <StLink :href="item.url">{{ item.url ?? '—' }}</StLink>
          </div>
          <div class="flex gap-2 shrink-0">
            <UButton
              size="xs"
              color="primary"
              :loading="busy === item.url"
              :disabled="busy !== null"
              @click="promote(item)"
            >Promote</UButton>
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
