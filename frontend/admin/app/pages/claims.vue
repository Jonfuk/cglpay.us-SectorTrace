<script setup lang="ts">
const dialog = useAdminDialog();
import { computed, ref, watch } from 'vue';
import type {
  Claim,
  ClaimCountsResponse,
  ClaimEvidenceResponse,
  ClaimEvidenceRow,
  ClaimsResponse,
} from '~/types/admin';
import { TransportError } from '~/lib/transport';

// Claims authoring is deliberately a thin client over the audited Python
// workflow. The browser can write a draft, edit it, attach one resolved
// evidence row at a time, and submit a named decision; it cannot bypass the
// server's draft/citation/decision rules or publish a claim anonymously.
const api = useAdminApi();
const filters = useFilterState();
const reviewer = useReviewer();
const toast = useToast();

const status = computed({
  get: () => (filters.get('status') as string) ?? 'all',
  set: (value: string) => {
    void filters.set('status', value === 'all' ? undefined : value);
  },
});

const { data: counts, refresh: refreshCounts } =
  await useAsyncData<ClaimCountsResponse | null>(
    'admin-claim-counts',
    () => api.claimCounts(),
    { default: () => null },
  );

const { data, pending, error, refresh } =
  await useDataRoute<ClaimsResponse | null>('admin-claims', (f) =>
    api.claims({ query: { status: (f.status as string) || 'all', ...f } }),
  );

const { data: evidenceData } = await useAsyncData<ClaimEvidenceResponse | null>(
  'admin-claim-evidence-tables',
  () => api.claimEvidence(),
  { default: () => null },
);

const items = computed<Claim[]>(() => data.value?.items ?? []);
const selectedId = ref<number | null>(null);
const editing = ref(false);
const busy = ref(false);
const form = ref({ claimText: '', caveats: '', note: '' });
const newForm = ref({ claimText: '', caveats: '', note: '' });

const selected = computed(
  () => items.value.find((claim) => claim.id === selectedId.value) ?? null,
);
const evidenceTables = computed(() => evidenceData.value?.tables ?? []);
const evidenceTable = ref('');
const evidenceQuery = ref('');
const evidenceRows = ref<ClaimEvidenceRow[]>([]);
const selectedEvidenceKey = ref('');
const evidenceBusy = ref(false);

watch(selected, (claim, previous) => {
  if (editing.value && claim?.id === previous?.id) return;
  if (!claim) {
    editing.value = false;
    return;
  }
  form.value = {
    claimText: claim.claim_text,
    caveats: claim.caveats ?? '',
    note: claim.note ?? '',
  };
  editing.value = false;
});

watch(evidenceTable, () => {
  evidenceQuery.value = '';
  evidenceRows.value = [];
  selectedEvidenceKey.value = '';
});

function requireReviewer(): boolean {
  if (reviewer.isSet.value) return true;
  toast.add({ title: 'Set your reviewer name first', color: 'warning' });
  return false;
}

function message(errorValue: unknown): string {
  return errorValue instanceof TransportError
    ? errorValue.message
    : String(errorValue);
}

async function afterWrite() {
  await Promise.all([refresh(), refreshCounts()]);
}

async function createClaim() {
  if (busy.value || !requireReviewer() || !newForm.value.claimText.trim())
    return;
  busy.value = true;
  try {
    const created = (await api.createClaim({
      claimText: newForm.value.claimText,
      caveats: newForm.value.caveats,
      note: newForm.value.note,
      createdBy: reviewer.name.value,
    })) as Claim;
    newForm.value = { claimText: '', caveats: '', note: '' };
    await afterWrite();
    selectedId.value = created.id;
    toast.add({ title: 'Draft claim created', color: 'success' });
  } catch (e) {
    toast.add({
      title: 'Create failed',
      description: message(e),
      color: 'error',
    });
  } finally {
    busy.value = false;
  }
}

onBeforeRouteUpdate(
  async () =>
    !editing.value ||
    (await dialog.confirm(
      'Discard your unsaved claim edits before changing this view?',
    )),
);

async function selectClaim(claim: Claim) {
  if (
    editing.value &&
    !(await dialog.confirm('Discard your unsaved claim edits?'))
  )
    return;
  selectedId.value = claim.id;
}

async function saveClaim() {
  if (busy.value || !selected.value || !requireReviewer()) return;
  busy.value = true;
  try {
    await api.updateClaim({
      claimId: selected.value.id,
      claimText: form.value.claimText,
      caveats: form.value.caveats,
      note: form.value.note,
    });
    editing.value = false;
    await afterWrite();
    toast.add({ title: 'Draft claim updated', color: 'success' });
  } catch (e) {
    toast.add({
      title: 'Update failed',
      description: message(e),
      color: 'error',
    });
  } finally {
    busy.value = false;
  }
}

async function searchEvidence() {
  if (!evidenceTable.value || !evidenceQuery.value.trim()) return;
  evidenceBusy.value = true;
  try {
    const result = await api.claimEvidence({
      query: {
        table: evidenceTable.value,
        q: evidenceQuery.value,
      },
    });
    evidenceRows.value = result.rows ?? [];
    selectedEvidenceKey.value = '';
  } catch (e) {
    toast.add({
      title: 'Evidence search failed',
      description: message(e),
      color: 'error',
    });
  } finally {
    evidenceBusy.value = false;
  }
}

async function citeSelected() {
  if (
    busy.value ||
    !selected.value ||
    !selectedEvidenceKey.value ||
    !requireReviewer()
  )
    return;
  busy.value = true;
  try {
    await api.citeClaim({
      claimId: selected.value.id,
      evidenceTable: evidenceTable.value,
      evidenceKey: selectedEvidenceKey.value,
      citedBy: reviewer.name.value,
    });
    await afterWrite();
    toast.add({ title: 'Evidence cited', color: 'success' });
  } catch (e) {
    toast.add({
      title: 'Citation failed',
      description: message(e),
      color: 'error',
    });
  } finally {
    busy.value = false;
  }
}

async function uncite(citation: Claim['citations'][number]) {
  if (busy.value || !selected.value || !requireReviewer()) return;
  busy.value = true;
  try {
    await api.unciteClaim({
      claimId: selected.value.id,
      evidenceTable: citation.evidence_table,
      evidenceKey: citation.evidence_key,
    });
    await afterWrite();
    toast.add({ title: 'Citation removed', color: 'success' });
  } catch (e) {
    toast.add({
      title: 'Remove citation failed',
      description: message(e),
      color: 'error',
    });
  } finally {
    busy.value = false;
  }
}

async function decide(decision: 'published' | 'rejected' | 'retracted') {
  if (busy.value || !selected.value || !requireReviewer()) return;
  const note = await dialog.prompt(`Optional note for ${decision}:`);
  if (note === null) return;
  busy.value = true;
  try {
    await api.decideClaim({
      claimId: selected.value.id,
      decision,
      decidedBy: reviewer.name.value,
      note,
    });
    await afterWrite();
    toast.add({ title: `Claim ${decision}`, color: 'success' });
  } catch (e) {
    toast.add({
      title: 'Decision failed',
      description: message(e),
      color: 'error',
    });
  } finally {
    busy.value = false;
  }
}

async function resetClaim() {
  if (busy.value || !selected.value || !requireReviewer()) return;
  if (
    !(await dialog.confirm(
      'Return this claim to draft? Its decision history stays recorded.',
    ))
  )
    return;
  busy.value = true;
  try {
    await api.resetClaim({ claimId: selected.value.id });
    await afterWrite();
    toast.add({ title: 'Claim returned to draft', color: 'success' });
  } catch (e) {
    toast.add({
      title: 'Reset failed',
      description: message(e),
      color: 'error',
    });
  } finally {
    busy.value = false;
  }
}

useUnsavedAdmin(
  () =>
    editing.value ||
    !!newForm.value.claimText ||
    !!newForm.value.caveats ||
    !!newForm.value.note,
);
useHead({ title: 'SectorTrace — Claims' });
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Claims</h1>
      <p class="opacity-70 max-w-3xl text-sm">
        Write campaign statements as drafts, attach evidence rows that resolve
        in the warehouse, and record every decision against a named reviewer.
        Published claims are the only claims visible on the public portal.
      </p>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
      <button
        v-for="key in ['all', 'draft', 'published', 'rejected', 'retracted']"
        :key="key"
        type="button"
        class="rounded border p-3 text-left"
        :class="
          status === key
            ? 'border-[var(--st-accent)] bg-[var(--st-accent)]/10'
            : 'border-black/10 dark:border-white/10'
        "
        @click="status = key"
      >
        <span class="block capitalize opacity-70">{{ key }}</span>
        <strong>{{
          key === 'all' ? (counts?.total ?? '—') : (counts?.[key] ?? '—')
        }}</strong>
      </button>
    </div>

    <UCard>
      <template #header
        ><span class="font-medium">New draft claim</span></template
      >
      <div class="space-y-3">
        <textarea
          aria-label="New claim text"
          v-model="newForm.claimText"
          rows="3"
          maxlength="5000"
          class="w-full border rounded p-2 bg-transparent"
          placeholder="State the claim exactly as a reader should see it."
        />
        <textarea
          aria-label="New claim caveats"
          v-model="newForm.caveats"
          rows="2"
          maxlength="2000"
          class="w-full border rounded p-2 bg-transparent"
          placeholder="Caveats — one line per limitation (optional)."
        />
        <input
          aria-label="New claim internal note"
          v-model="newForm.note"
          maxlength="2000"
          class="w-full border rounded p-2 bg-transparent"
          placeholder="Internal note (optional)"
        />
        <UButton
          :loading="busy"
          :disabled="!newForm.claimText.trim()"
          @click="createClaim"
          >Create draft</UButton
        >
      </div>
    </UCard>

    <div v-if="pending" class="text-sm opacity-60">Loading claims…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <div
      v-else
      class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]"
    >
      <UCard>
        <template #header
          ><span class="text-sm font-medium"
            >{{ data?.total ?? items.length }} claims</span
          ></template
        >
        <StEmptyState v-if="!items.length" />
        <ul v-else class="divide-y divide-black/5 dark:divide-white/5">
          <li
            v-for="claim in items"
            :key="claim.id"
            class="py-3 first:pt-0 last:pb-0"
          >
            <button
              type="button"
              class="w-full text-left space-y-1"
              @click="selectClaim(claim)"
            >
              <div class="flex items-start justify-between gap-3">
                <span class="font-medium line-clamp-3">{{
                  claim.claim_text
                }}</span>
                <StatusPill :label="claim.status" />
              </div>
              <span class="text-xs opacity-60"
                >#{{ claim.id }} · {{ claim.created_by }} ·
                {{ claim.citations.length }} citation(s)</span
              >
            </button>
          </li>
        </ul>
      </UCard>

      <UCard v-if="selected">
        <template #header>
          <div class="flex items-center justify-between gap-3">
            <span class="font-medium">Claim #{{ selected.id }}</span>
            <div class="flex gap-2">
              <UButton
                v-if="selected.status === 'draft' && !editing"
                size="xs"
                variant="outline"
                @click="editing = true"
                >Edit</UButton
              >
              <UButton
                v-if="selected.status === 'draft'"
                size="xs"
                color="primary"
                :loading="busy"
                @click="decide('published')"
                >Publish</UButton
              >
              <UButton
                v-if="selected.status === 'draft'"
                size="xs"
                color="neutral"
                variant="outline"
                :loading="busy"
                @click="decide('rejected')"
                >Reject</UButton
              >
              <UButton
                v-if="selected.status === 'published'"
                size="xs"
                color="neutral"
                variant="outline"
                :loading="busy"
                @click="decide('retracted')"
                >Retract</UButton
              >
              <UButton
                v-if="selected.status !== 'draft'"
                size="xs"
                color="neutral"
                variant="outline"
                :loading="busy"
                @click="resetClaim"
                >Reset to draft</UButton
              >
            </div>
          </div>
        </template>

        <div v-if="editing" class="space-y-3">
          <textarea
            aria-label="Edit claim text"
            v-model="form.claimText"
            rows="4"
            maxlength="5000"
            class="w-full border rounded p-2 bg-transparent"
          />
          <textarea
            aria-label="Edit claim caveats"
            v-model="form.caveats"
            rows="3"
            maxlength="2000"
            class="w-full border rounded p-2 bg-transparent"
            placeholder="Caveats"
          />
          <input
            aria-label="Edit claim internal note"
            v-model="form.note"
            maxlength="2000"
            class="w-full border rounded p-2 bg-transparent"
            placeholder="Internal note"
          />
          <div class="flex gap-2">
            <UButton :loading="busy" @click="saveClaim">Save draft</UButton>
            <UButton variant="outline" @click="editing = false">Cancel</UButton>
          </div>
        </div>
        <div v-else class="space-y-4">
          <p class="whitespace-pre-wrap">{{ selected.claim_text }}</p>
          <p
            v-if="selected.caveats"
            class="text-sm opacity-70 whitespace-pre-wrap"
          >
            Caveats: {{ selected.caveats }}
          </p>
          <p v-if="selected.note" class="text-sm opacity-70">
            Note: {{ selected.note }}
          </p>

          <div>
            <h2 class="text-sm font-medium mb-2">Citations</h2>
            <StEmptyState v-if="!selected.citations.length" />
            <ul v-else class="space-y-2 text-sm">
              <li
                v-for="citation in selected.citations"
                :key="`${citation.evidence_table}:${citation.evidence_key}`"
                class="border rounded p-2"
              >
                <div class="flex justify-between gap-2">
                  <span
                    >{{ citation.evidence_table }} ·
                    {{
                      citation.resolved?.label ?? citation.evidence_key
                    }}</span
                  >
                  <UButton
                    v-if="selected.status === 'draft'"
                    size="xs"
                    color="neutral"
                    variant="ghost"
                    :disabled="busy"
                    @click="uncite(citation)"
                    >Remove</UButton
                  >
                </div>
                <StLink
                  v-if="citation.resolved?.url"
                  :href="citation.resolved.url"
                  >{{ citation.resolved.url }}</StLink
                >
                <p
                  v-if="citation.resolved === null"
                  class="text-xs text-amber-700"
                >
                  This evidence row no longer resolves in the warehouse.
                </p>
              </li>
            </ul>
          </div>

          <div
            v-if="selected.status === 'draft'"
            class="border-t pt-4 space-y-3"
          >
            <h2 class="text-sm font-medium">Add a citation</h2>
            <div class="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
              <select
                v-model="evidenceTable"
                class="border rounded p-2 bg-transparent text-sm"
              >
                <option value="">Choose evidence table…</option>
                <option
                  v-for="table in evidenceTables"
                  :key="table"
                  :value="table"
                >
                  {{ table }}
                </option>
              </select>
              <input
                v-model="evidenceQuery"
                class="border rounded p-2 bg-transparent text-sm"
                placeholder="Search evidence"
                @keyup.enter="searchEvidence"
              />
              <UButton
                size="sm"
                :loading="evidenceBusy"
                :disabled="!evidenceTable || !evidenceQuery.trim()"
                @click="searchEvidence"
                >Search</UButton
              >
            </div>
            <select
              v-model="selectedEvidenceKey"
              class="w-full border rounded p-2 bg-transparent text-sm"
            >
              <option value="">Choose a resolved row…</option>
              <option
                v-for="row in evidenceRows"
                :key="row.key"
                :value="row.key"
              >
                {{ row.label }}
              </option>
            </select>
            <UButton
              size="sm"
              :loading="busy"
              :disabled="!selectedEvidenceKey"
              @click="citeSelected"
              >Cite selected row</UButton
            >
          </div>

          <details v-if="selected.decisions.length" class="text-sm">
            <summary class="cursor-pointer opacity-70">
              Decision history ({{ selected.decisions.length }})
            </summary>
            <ul class="mt-2 space-y-1 opacity-70">
              <li v-for="decision in selected.decisions" :key="decision.id">
                {{ decision.decision }} by {{ decision.decided_by }} ·
                {{ decision.decided_at
                }}<span v-if="decision.note"> — {{ decision.note }}</span>
              </li>
            </ul>
          </details>
        </div>
      </UCard>
      <UCard v-else class="lg:col-start-2">
        <StEmptyState
          title="Select a claim"
          message="Choose a claim to edit, cite, or decide it."
        />
      </UCard>
    </div>
    <AdminPager
      :total="data?.total"
      :limit="Number(filters.get('limit') || 50)"
      :offset="Number(filters.get('offset') || 0)"
    />
  </section>
</template>
