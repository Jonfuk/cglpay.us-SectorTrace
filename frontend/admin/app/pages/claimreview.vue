<script setup lang="ts">
import type { AdminRecord } from '~/lib/operator';
const route = useRoute(),
  filters = useFilterState(),
  reviewer = useReviewer(),
  dialog = useAdminDialog();
const list = useOperatorResource(
  '/api/admin/claim-candidates',
  () =>
    ({ status: '', limit: 25, ...route.query }) as Record<
      string,
      string | number
    >,
);
const ontology = useOperatorResource('/api/admin/claim-ontology');
const focusedId = ref(''),
  action = useOperatorAction();
const form = reactive({
  decision: 'approved',
  reason_code: '',
  note: '',
  corrected_predicate: '',
  corrected_object_concept_id: '',
  corrected_object_literal: '',
});
const focused = computed(() =>
  list.data.value?.candidates?.find(
    (c: AdminRecord) => c.claim_candidate_id === focusedId.value,
  ),
);
async function choose(id: string) {
  if (
    (form.note ||
      form.corrected_predicate ||
      form.corrected_object_concept_id ||
      form.corrected_object_literal) &&
    !(await dialog.confirm('Discard unsaved candidate corrections?'))
  )
    return;
  Object.assign(form, {
    decision: 'approved',
    reason_code: '',
    note: '',
    corrected_predicate: '',
    corrected_object_concept_id: '',
    corrected_object_literal: '',
  });
  focusedId.value = id;
}
function setFilter(key: string, e: Event) {
  void filters.setAll({
    ...filters.all(),
    [key]: (e.target as HTMLInputElement).value,
    offset: undefined,
  });
}
async function decide() {
  if (
    action.busy.value ||
    !focused.value ||
    !reviewer.isSet.value ||
    !(await dialog.confirm(
      `Record ${form.decision} for this extracted claim candidate? This does not publish a claim or train a model.`,
    ))
  )
    return;
  const body = {
    claim_candidate_id: focusedId.value,
    decision: form.decision,
    decided_by: reviewer.name.value,
    reason_code: form.reason_code || null,
    note: form.note || null,
    ...(form.decision === 'corrected'
      ? {
          corrected_predicate: form.corrected_predicate || null,
          corrected_object_concept_id: form.corrected_object_concept_id || null,
          corrected_object_literal: form.corrected_object_literal || null,
        }
      : {}),
  };
  if (await action.run('/api/admin/claim-candidates/decide', body)) {
    form.note = '';
    form.corrected_predicate = '';
    form.corrected_object_concept_id = '';
    form.corrected_object_literal = '';
    form.reason_code = '';
    await list.refresh();
  }
}
useQueueFocus(focusedId);
useUnsavedAdmin(
  () =>
    !!form.note ||
    !!form.corrected_object_literal ||
    !!form.corrected_predicate ||
    !!form.corrected_object_concept_id ||
    !!form.reason_code,
);
useHead({ title: 'SectorTrace — Claim review' });
</script>
<template>
  <section class="admin-review-workspace" :data-focused="!!focused">
    <AdminPageHeader
      title="Claim review"
      description="Adjudicate one extracted subject–predicate–object candidate at a time. Decisions remain findings; this workspace never publishes evidence or trains a model."
      eyebrow="Review · Extracted candidates"
    />
    <div class="admin-filters">
      <label
        >Status<select
          :value="route.query.status || ''"
          @change="setFilter('status', $event)"
        >
          <option value="">All candidates</option>
          <option
            v-for="s in ['new', 'queued', 'accepted', 'dismissed']"
            :key="s"
          >
            {{ s }}
          </option>
        </select></label
      ><label
        >Predicate<select
          :value="route.query.predicate || ''"
          @change="setFilter('predicate', $event)"
        >
          <option value="">Any predicate</option>
          <option
            v-for="p in ontology.data.value?.predicates"
            :key="p.id"
            :value="p.id"
          >
            {{ p.label }}
          </option>
        </select></label
      ><label
        >Source system<input
          :value="route.query.source_system || ''"
          @change="setFilter('source_system', $event)" /></label
      ><label class="grow"
        >Search<input
          type="search"
          :value="route.query.q || ''"
          @change="setFilter('q', $event)"
      /></label>
    </div>
    <p v-if="list.error.value || action.error.value" class="admin-error">
      {{ list.error.value || action.error.value }}
    </p>
    <AdminPager
      :total="list.data.value?.total"
      :limit="25"
      :offset="Number(route.query.offset || 0)"
    />
    <div class="admin-detail" :data-focused="!!focused">
      <div class="admin-queue admin-panel !p-0">
        <button
          v-for="c in list.data.value?.candidates"
          :key="c.claim_candidate_id"
          class="admin-queue-row block w-full text-left"
          :data-active="focusedId === c.claim_candidate_id"
          @click="choose(c.claim_candidate_id)"
        >
          <span
            >{{ c.subject_hint }} · {{ c.predicate }} ·
            {{ c.object_literal ?? c.object_concept_id ?? '—' }}</span
          ><StatusPill class="mt-2" :label="c.status" />
        </button>
        <p v-if="!list.data.value?.candidates?.length" class="admin-note p-5">
          No candidates in this view.
        </p>
      </div>
      <div class="admin-detail-pane admin-panel">
        <template v-if="focused"
          ><UButton
            class="admin-mobile-back"
            color="neutral"
            variant="ghost"
            @click="focusedId = ''"
            >← Candidates</UButton
          >
          <h2>{{ focused.subject_hint }}</h2>
          <blockquote class="my-4 leading-relaxed whitespace-pre-wrap">
            {{ focused.evidence_span }}
          </blockquote>
          <AdminRecord :value="focused" />
          <form class="space-y-4 mt-5" @submit.prevent="decide">
            <label class="admin-field"
              >Decision<select v-model="form.decision">
                <option value="approved">Approve — triple is right</option>
                <option value="rejected">Reject — wrong</option>
                <option value="corrected">Correct — a field is wrong</option>
              </select></label
            ><label class="admin-field"
              >Reason code<select v-model="form.reason_code">
                <option value="">Optional reason</option>
                <option v-for="r in ontology.data.value?.reason_codes" :key="r">
                  {{ r }}
                </option>
              </select></label
            ><template v-if="form.decision === 'corrected'"
              ><label class="admin-field"
                >Corrected predicate<select v-model="form.corrected_predicate">
                  <option value="">Keep predicate</option>
                  <option
                    v-for="p in ontology.data.value?.predicates"
                    :key="p.id"
                    :value="p.id"
                  >
                    {{ p.label }}
                  </option>
                </select></label
              ><label class="admin-field"
                >Corrected object concept<select
                  v-model="form.corrected_object_concept_id"
                >
                  <option value="">Keep concept</option>
                  <option
                    v-for="c in ontology.data.value?.concepts"
                    :key="c.id"
                    :value="c.id"
                  >
                    {{ c.label }}
                  </option>
                </select></label
              ><label class="admin-field"
                >Corrected object literal<input
                  v-model="form.corrected_object_literal" /></label></template
            ><label class="admin-field"
              >Note<textarea
                v-model="form.note"
                rows="3"
                maxlength="2000"
              /></label
            ><UButton
              type="submit"
              :disabled="action.busy.value || !reviewer.isSet.value"
              >Record decision</UButton
            >
          </form>
          <AdminResourcePanel
            class="mt-5"
            title="Candidate details and history"
            :path="`/api/admin/claim-candidates/${encodeURIComponent(focusedId)}`"
        /></template>
        <p v-else class="admin-note">
          Choose a candidate to inspect its source and record a decision.
        </p>
      </div>
    </div>
    <details class="admin-panel mt-5">
      <summary>Training-readiness gate</summary>
      <AdminResourcePanel
        title="Gate information"
        path="/api/admin/claim-gate"
      />
    </details>
  </section>
</template>
