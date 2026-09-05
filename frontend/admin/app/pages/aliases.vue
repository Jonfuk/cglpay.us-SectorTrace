<script setup lang="ts">
import type { AdminRecord } from '~/lib/operator';
const route = useRoute(),
  filters = useFilterState(),
  reviewer = useReviewer(),
  dialog = useAdminDialog();
const scheme = computed(() => String(route.query.scheme || 'buyer'));
const list = useOperatorResource('/api/admin/aliases', () => ({
  scheme: scheme.value,
}));
const action = useOperatorAction(),
  forms = ref<Record<string, { id: string; reason: string }>>({});
watch(list.data, (data) => {
  for (const row of data?.items || [])
    forms.value[row.unmatched_name] ||= { id: '', reason: '' };
});
async function decide(row: AdminRecord, status: string) {
  if (
    action.busy.value ||
    !reviewer.isSet.value ||
    !(await dialog.confirm(
      `Record ${status} for “${row.unmatched_name}”? Similarity suggestions are never applied automatically.`,
    ))
  )
    return;
  const form = forms.value[row.unmatched_name]!,
    previous = (row.decisions || [])
      .filter((d: AdminRecord) => d.status === 'accepted')
      .at(-1);
  if (
    await action.run('/api/admin/aliases/decide', {
      unmatched_name: row.unmatched_name,
      target_scheme: scheme.value,
      status,
      decided_by: reviewer.name.value,
      canonical_id: status === 'accepted' ? form.id : undefined,
      reason: form.reason || null,
      supersedes_id: previous?.decision_id,
    })
  ) {
    forms.value[row.unmatched_name] = { id: '', reason: '' };
    await list.refresh();
  }
}
useUnsavedAdmin(() =>
  Object.values(forms.value).some((form) => !!form.id || !!form.reason),
);
useHead({ title: 'SectorTrace — Alias resolution' });
</script>
<template>
  <section>
    <AdminPageHeader
      title="Alias resolution"
      description="Resolve unmatched names through explicit, append-only decisions. A correction supersedes the previous decision."
      eyebrow="Quality · Identity resolution"
    />
    <div class="admin-filters">
      <label
        >Scheme<select
          :value="scheme"
          @change="
            filters.set('scheme', ($event.target as HTMLSelectElement).value)
          "
        >
          <option value="buyer">Buyer → authority</option>
          <option value="provider">Company → provider</option>
        </select></label
      ><UButton color="neutral" variant="outline" @click="list.refresh"
        >Refresh</UButton
      >
    </div>
    <p v-if="list.error.value || action.error.value" class="admin-error">
      {{ list.error.value || action.error.value }}
    </p>
    <div class="space-y-4">
      <section
        v-for="row in list.data.value?.items"
        :key="row.unmatched_name"
        class="admin-panel"
      >
        <div class="admin-actions justify-between">
          <h2>{{ row.unmatched_name }}</h2>
          <StatusPill
            :label="row.resolved ? 'Resolved' : 'Unresolved'"
            :level="row.resolved ? 'ok' : 'neutral'"
          />
        </div>
        <form
          v-if="forms[row.unmatched_name]"
          class="admin-filters mt-4"
          @submit.prevent="decide(row, 'accepted')"
        >
          <label
            >{{ scheme === 'buyer' ? 'Authority ONS code' : 'Provider key'
            }}<input v-model="forms[row.unmatched_name]!.id" required /></label
          ><label class="grow"
            >Reason<input v-model="forms[row.unmatched_name]!.reason" /></label
          ><UButton
            type="submit"
            :disabled="action.busy.value || !reviewer.isSet.value"
            >Accept mapping</UButton
          ><UButton
            color="error"
            variant="outline"
            :disabled="action.busy.value || !reviewer.isSet.value"
            @click="decide(row, 'rejected')"
            >Reject</UButton
          >
        </form>
        <details>
          <summary>Evidence and decision history</summary>
          <AdminRecord :value="row" />
        </details>
      </section>
      <p
        v-if="list.data.value && !list.data.value.items?.length"
        class="admin-note"
      >
        No unmatched names for this scheme.
      </p>
    </div>
  </section>
</template>
