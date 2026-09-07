<script setup lang="ts">
import { getOperator, type AdminRecord } from '~/lib/operator';
const action = useOperatorAction(),
  dialog = useAdminDialog();
const form = reactive({
  seed: 'audit',
  source: 'review_queue',
  method: 'random',
  size: 25,
  stratify_by: '',
});
const sample = shallowRef<AdminRecord | null>(null);
const findings = ref<Record<string, { verdict: string; note: string }>>({});
const samples = useOperatorResource('/api/admin/qc-samples');
async function load(id: string, refreshing = false) {
  if (
    !refreshing &&
    dirty() &&
    !(await dialog.confirm(
      'Discard unsaved QC findings before opening another sample?',
    ))
  )
    return;
  try {
    sample.value = await getOperator(
      `/api/admin/qc-samples/${encodeURIComponent(id)}`,
    );
    if (!refreshing) findings.value = {};
    init();
  } catch (e) {
    action.error.value = String(e);
  }
}
function recordId(row: Record<string, unknown>) {
  return String(
    sample.value?.source === 'review_queue' ? row.id : row.decision_id,
  );
}
function init() {
  for (const row of sample.value?.records || [])
    findings.value[recordId(row)] ||= { verdict: 'agree', note: '' };
}
async function draw() {
  if (action.busy.value) return;
  if (
    dirty() &&
    !(await dialog.confirm(
      'Discard unsaved findings before drawing another sample?',
    ))
  )
    return;
  if (
    !(await dialog.confirm(
      'Record this reproducible QC sample? Existing review decisions will not change.',
    ))
  )
    return;
  const result = await action.run('/api/admin/qc-sample/draw', {
    ...form,
    stratify_by: form.method === 'stratified' ? form.stratify_by : undefined,
  });
  if (result) {
    sample.value = result;
    findings.value = {};
    init();
    void samples.refresh();
  }
}
async function append(id: string) {
  const sampleId = sample.value?.sample_id;
  if (
    await action.run('/api/admin/qc-finding', {
      sample_id: sampleId,
      record_ref: id,
      ...findings.value[id],
    })
  ) {
    findings.value[id] = { verdict: 'agree', note: '' };
    await load(sampleId, true);
  }
}
function dirty() {
  return Object.values(findings.value).some(
    (f) => !!f.note || f.verdict !== 'agree',
  );
}
useUnsavedAdmin(dirty);
useHead({ title: 'SectorTrace — QC sampling' });
</script>
<template>
  <section>
    <AdminPageHeader
      title="QC sampling"
      description="Draw a reproducible sample and append second-look findings. This never changes the original review decision."
      eyebrow="Quality · Second look"
    />
    <form class="admin-filters" @submit.prevent="draw">
      <label>Seed<input v-model="form.seed" required /></label
      ><label
        >Source<select v-model="form.source">
          <option>review_queue</option>
          <option>alias_decisions</option>
        </select></label
      ><label
        >Method<select v-model="form.method">
          <option>random</option>
          <option>stratified</option>
        </select></label
      ><label v-if="form.method === 'stratified'"
        >Stratify by<input
          v-model="form.stratify_by"
          required
          placeholder="module / item_type" /></label
      ><label
        >Size<input
          v-model.number="form.size"
          type="number"
          min="1"
          max="500"
          required /></label
      ><UButton type="submit" :loading="action.busy.value">Draw sample</UButton>
    </form>
    <p v-if="action.error.value" class="admin-error">
      {{ action.error.value }}
    </p>
    <details class="admin-panel mb-5">
      <summary>Previous samples</summary>
      <AdminRows :rows="samples.data.value?.samples || []"
        ><template #actions="{ row }"
          ><UButton
            size="xs"
            color="neutral"
            variant="outline"
            @click="load(row.sample_id)"
            >Open sample</UButton
          ></template
        ></AdminRows
      >
    </details>
    <section v-if="sample" class="admin-panel">
      <h2>Sample {{ sample.sample_id }}</h2>
      <p class="admin-note">
        {{ sample.sample_size }} of {{ sample.population_size }} · seed
        {{ sample.seed }} · {{ sample.method }} · {{ sample.reviewed }} reviewed
      </p>
      <p class="admin-note">{{ sample.note }}</p>
      <div
        v-for="row in sample.records"
        :key="recordId(row)"
        class="py-4 border-b border-black/10"
      >
        <details>
          <summary>
            {{ recordId(row) }} ·
            {{ row.raw_value || row.unmatched_name || row.canonical_name }}
          </summary>
          <AdminRecord :value="row" />
        </details>
        <form
          class="admin-actions mt-3"
          @submit.prevent="append(recordId(row))"
        >
          <label class="admin-field"
            >Verdict<select v-model="findings[recordId(row)]!.verdict">
              <option>agree</option>
              <option>disagree</option>
              <option>unclear</option>
            </select></label
          ><label class="admin-field grow"
            >Note<input v-model="findings[recordId(row)]!.note" /></label
          ><UButton type="submit" :disabled="action.busy.value"
            >Append finding</UButton
          >
        </form>
      </div>
      <details class="mt-4">
        <summary>Recorded findings</summary>
        <AdminRows :rows="sample.findings || []" />
      </details>
    </section>
  </section>
</template>
