<script setup lang="ts">
import { type AdminRecord } from '~/lib/operator';
const props = defineProps<{
  item: AdminRecord;
  resolvable?: AdminRecord;
  note?: string;
}>();
const emit = defineEmits<{ resolved: [] }>();
const reviewer = useReviewer(),
  dialog = useAdminDialog(),
  action = useOperatorAction();
const url = ref('');
const source = useOperatorResource(
  () => `/api/review/${props.item.id}/sidecar`,
);
const history = useOperatorResource(() => `/api/review/${props.item.id}`);
const context = computed(() => {
  try {
    return typeof props.item.context_json === 'string'
      ? JSON.parse(props.item.context_json)
      : props.item.context_json || props.item.context;
  } catch {
    return props.item.context_json;
  }
});
async function resolve() {
  if (
    !reviewer.isSet.value ||
    !(await dialog.confirm(
      'Check this URL and record the resolution for the next pipeline run?',
    ))
  )
    return;
  if (
    await action.run('/api/review/resolve', {
      id: props.item.id,
      url: url.value,
      resolved_by: reviewer.name.value,
      note: props.note || undefined,
    })
  )
    emit('resolved');
}
</script>
<template>
  <div class="space-y-5">
    <div class="admin-actions">
      <StatusPill :label="item.status" /><span class="admin-note font-mono"
        >#{{ item.id }} · {{ item.module }}</span
      >
    </div>
    <h2 class="break-words">{{ item.raw_value }}</h2>
    <p class="admin-note">{{ item.item_type }}</p>
    <div v-if="source.error.value" class="admin-error">
      {{ source.error.value }}
    </div>
    <section v-if="source.data.value" class="admin-panel">
      <h3 class="mb-3">Source and provenance</h3>
      <blockquote
        v-if="source.data.value.source?.excerpt"
        class="whitespace-pre-wrap leading-relaxed"
      >
        {{ source.data.value.source.excerpt }}
      </blockquote>
      <StLink :href="source.data.value.source?.url" /><AdminRecord
        :value="{
          retrieved_at: source.data.value.source?.retrieved_at,
          payload_sha256: source.data.value.source?.payload_sha256,
          note: source.data.value.source?.note,
        }"
      />
      <p class="admin-note mt-3">{{ source.data.value.caveat }}</p>
      <details v-if="source.data.value.candidates?.supported" class="mt-4">
        <summary>
          Suggested name matches · nothing selected automatically
        </summary>
        <AdminRows
          :rows="source.data.value.candidates.ranking || []"
        /><AdminRecord :value="source.data.value.candidates.suppressed" />
      </details>
    </section>
    <details open>
      <summary class="font-medium">Record context</summary>
      <AdminRecord :value="context" />
    </details>
    <section v-if="resolvable && item.status === 'pending'" class="admin-panel">
      <h3>{{ resolvable.label }}</h3>
      <p class="admin-note">{{ resolvable.help }}</p>
      <label class="admin-field mt-3"
        >Confirmed URL<input v-model="url" type="url" placeholder="https://…"
      /></label>
      <div class="admin-actions mt-3">
        <UButton
          color="neutral"
          variant="outline"
          :disabled="!url || action.busy.value"
          @click="action.run('/api/check-url', { url })"
          >Check URL</UButton
        ><UButton
          :disabled="!url || !reviewer.isSet.value || action.busy.value"
          @click="resolve"
          >Save resolution</UButton
        >
      </div>
      <AdminRecord v-if="action.result.value" :value="action.result.value" />
      <p v-if="action.error.value" class="admin-error">
        {{ action.error.value }}
      </p>
    </section>
    <details>
      <summary class="font-medium">Decision history</summary>
      <p v-if="history.error.value" class="admin-error">
        {{ history.error.value }}
      </p>
      <AdminRows
        :rows="history.data.value?.decisions || []"
        :columns="[
          'decision',
          'status_before',
          'decided_by',
          'decided_at',
          'note',
        ]"
      />
    </details>
  </div>
</template>
