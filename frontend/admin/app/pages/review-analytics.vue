<script setup lang="ts">
const data = useOperatorResource('/api/admin/review-analytics');
const visible = computed(() => {
  const result = { ...data.data.value };
  if (Array.isArray(result.by_source))
    result.by_source = result.by_source.map((row) =>
      row.suppressed
        ? { ...row, total: `Suppressed (< ${result.min_group})` }
        : row,
    );
  if (Array.isArray(result.reason_codes))
    result.reason_codes = result.reason_codes.map((row) =>
      row.suppressed
        ? { ...row, n: `Suppressed (< ${result.min_group})` }
        : row,
    );
  return result;
});
useHead({ title: 'SectorTrace — Review analytics' });
</script>
<template>
  <section>
    <AdminPageHeader
      title="Review analytics"
      description="Review outcomes and age distributions, with the server's suppression rules preserved. These are workflow observations, not performance targets."
      eyebrow="Quality · Review outcomes"
      ><UButton color="neutral" variant="outline" @click="data.refresh"
        >Refresh</UButton
      ></AdminPageHeader
    >
    <p v-if="data.error.value" class="admin-error">{{ data.error.value }}</p>
    <template v-if="data.data.value"
      ><p class="admin-note mb-5">{{ data.data.value.note }}</p>
      <div v-for="(value, key) in visible" :key="key" class="admin-panel mb-5">
        <h2>{{ String(key).replaceAll('_', ' ') }}</h2>
        <AdminRows
          v-if="
            Array.isArray(value) &&
            value.every((x) => x && typeof x === 'object')
          "
          :rows="value"
        /><AdminRecord v-else :value="value" /></div
    ></template>
  </section>
</template>
