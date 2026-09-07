<script setup lang="ts">
import type { AdminRecord } from '~/lib/operator';
const resource = useOperatorResource('/api/admin/validation-rules');
const query = ref(''),
  kinds = ref<string[]>([]);
let initialized = false;
watch(resource.data, (value) => {
  if (value && !initialized) {
    kinds.value = value.kinds || [];
    initialized = true;
  }
});
const rules = computed<AdminRecord[]>(() =>
  [
    ...(resource.data.value?.schema_rules || []),
    ...(resource.data.value?.observed_rules || []),
  ].filter(
    (rule) =>
      kinds.value.includes(rule.kind) &&
      `${rule.id} ${rule.title} ${rule.purpose}`
        .toLowerCase()
        .includes(query.value.toLowerCase()),
  ),
);
</script>

<template>
  <section class="admin-panel">
    <div class="admin-actions justify-between mb-4">
      <h2>Validation rules</h2>
      <UButton
        color="neutral"
        variant="outline"
        :loading="resource.pending.value"
        @click="resource.refresh"
        >Refresh</UButton
      >
    </div>
    <p v-if="resource.error.value" class="admin-error">
      {{ resource.error.value }}
    </p>
    <p class="admin-note mb-4">
      {{ resource.data.value?.note }} {{ resource.data.value?.redaction }}
    </p>
    <div class="admin-filters">
      <label class="grow"
        >Find a validation rule<input v-model="query" type="search"
      /></label>
      <label
        v-for="kind in resource.data.value?.kinds"
        :key="kind"
        class="!flex items-center"
        ><input v-model="kinds" type="checkbox" :value="kind" />{{
          kind.replaceAll('_', ' ')
        }}</label
      >
    </div>
    <article v-for="rule in rules" :key="rule.id" class="admin-panel mb-4">
      <div class="admin-actions mb-3">
        <StatusPill :label="rule.kind" /><span class="admin-note font-mono">{{
          rule.id
        }}</span>
      </div>
      <h3>{{ rule.title }}</h3>
      <p class="admin-description">{{ rule.purpose }}</p>
      <pre v-if="rule.detail" class="mt-3">{{ rule.detail }}</pre>
      <StatusPill
        v-if="rule.kind === 'provenance'"
        class="mt-3"
        :label="rule.enforced ? 'Enforced' : 'Not enforced'"
        :level="rule.enforced ? 'ok' : 'bad'"
      />
      <AdminRecord v-if="rule.counts" class="mt-3" :value="rule.counts" />
      <p v-if="rule.reasons?.length" class="admin-note mt-3">
        {{ rule.reasons.join('; ') }}
      </p>
      <details v-if="rule.examples?.length" class="mt-4">
        <summary>Representative failures · redacted shapes</summary>
        <AdminRows :rows="rule.examples" />
      </details>
    </article>
    <p v-if="resource.data.value && !rules.length" class="admin-note">
      No rules match these filters.
    </p>
  </section>
</template>
