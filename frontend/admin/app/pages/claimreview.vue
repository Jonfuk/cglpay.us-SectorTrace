<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ClaimCandidate, ClaimCandidatesResponse } from '~/types/admin'
import { TransportError } from '~/lib/transport'

// Claim review — the semantic claim-candidate adjudication queue. Each candidate
// is approved or rejected by a named human; nothing becomes a published claim
// without that decision. Read + decide only, mirroring the server contract.
// Parity target: legacy admin `claimreview.js`. Status is URL-authoritative.
const api = useAdminApi()
const filters = useFilterState()
const reviewer = useReviewer()
const toast = useToast()

const status = computed({
  get: () => (filters.get('status') as string) ?? 'undecided',
  set: (v: string) => { void filters.set('status', v || undefined) },
})

const { data, pending, error, refresh } = await useDataRoute<ClaimCandidatesResponse | null>(
  'admin-claim-candidates',
  (f) => api.claimCandidates({ query: { status: (f.status as string) || 'undecided', ...f } }),
)

const candidates = computed<ClaimCandidate[]>(() => data.value?.candidates ?? [])
const busy = ref<string | null>(null)

async function decide(c: ClaimCandidate, decision: 'approved' | 'rejected') {
  if (!reviewer.isSet.value) {
    toast.add({ title: 'Set your reviewer name first', color: 'warning' })
    return
  }
  const verb = decision === 'approved' ? 'Approve' : 'Reject'
  if (!window.confirm(`${verb} this claim candidate?\n\n${c.subject_hint} — ${c.predicate} — ${c.object_literal ?? c.object_concept_id ?? ''}`)) return
  busy.value = c.claim_candidate_id
  try {
    await api.decideClaimCandidate({ claimCandidateId: c.claim_candidate_id, decision, decidedBy: reviewer.name.value })
    toast.add({ title: `${verb}d`, color: 'success' })
    await refresh()
  } catch (e) {
    toast.add({ title: `${verb} failed`, description: e instanceof TransportError ? e.message : String(e), color: 'error' })
  } finally {
    busy.value = null
  }
}

useHead({ title: 'SectorTrace — Claim review' })
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold">Claim review</h1>
    <p class="opacity-70 max-w-2xl text-sm">
      Candidate claims extracted from documents, each adjudicated by a person.
      Nothing becomes a published claim without a human decision.
    </p>

    <div class="flex items-center gap-3">
      <label class="text-sm opacity-70" for="status">Status</label>
      <select
        id="status"
        v-model="status"
        class="text-sm border border-black/15 dark:border-white/15 rounded px-2 py-1 bg-transparent"
      >
        <option value="undecided">Undecided</option>
        <option value="approved">Approved</option>
        <option value="rejected">Rejected</option>
      </select>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading claim candidates…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <UCard v-else>
      <template #header>
        <span class="text-sm font-medium">{{ data?.total ?? candidates.length }} candidates</span>
      </template>

      <StEmptyState v-if="!candidates.length" />
      <ul v-else class="divide-y divide-black/5 dark:divide-white/5">
        <li v-for="c in candidates" :key="c.claim_candidate_id" class="py-3 flex items-start gap-4">
          <div class="min-w-0 flex-1 space-y-1">
            <div class="text-sm">
              <span class="font-medium">{{ c.subject_hint ?? '—' }}</span>
              <span class="opacity-60 mx-1">{{ c.predicate }}</span>
              <span class="font-medium">{{ c.object_literal ?? c.object_concept_id ?? '—' }}</span>
            </div>
            <p v-if="c.evidence_span" class="text-xs opacity-70">“{{ c.evidence_span }}”</p>
            <StatusPill :label="c.status" />
          </div>
          <div v-if="c.status === 'undecided'" class="flex gap-2 shrink-0">
            <UButton size="xs" color="primary" :loading="busy === c.claim_candidate_id" :disabled="busy !== null" @click="decide(c, 'approved')">Approve</UButton>
            <UButton size="xs" color="neutral" variant="outline" :disabled="busy !== null" @click="decide(c, 'rejected')">Reject</UButton>
          </div>
        </li>
      </ul>
      <template v-if="data?.caveat" #footer>
        <p class="text-xs opacity-60">{{ data.caveat }}</p>
      </template>
    </UCard>
  </section>
</template>
