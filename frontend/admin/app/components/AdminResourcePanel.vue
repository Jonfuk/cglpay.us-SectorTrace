<script setup lang="ts">
const props = defineProps<{
  title: string;
  path: string;
  query?: Record<string, string | number | boolean | undefined | null>;
  field?: string;
  columns?: string[];
}>();
const resource = useOperatorResource(
  () => props.path,
  () => props.query || {},
);
const value = computed(() =>
  props.field ? resource.data.value?.[props.field] : resource.data.value,
);
defineExpose({ refresh: resource.refresh });
</script>
<template>
  <section class="admin-panel">
    <div class="flex justify-between gap-3 mb-4">
      <h2>{{ title }}</h2>
      <UButton
        size="xs"
        color="neutral"
        variant="ghost"
        :loading="resource.pending.value"
        @click="resource.refresh"
        >Refresh</UButton
      >
    </div>
    <p
      v-if="resource.pending.value && !resource.data.value"
      role="status"
      class="admin-note"
    >
      Loading {{ title.toLowerCase() }}…
    </p>
    <div v-if="resource.error.value" role="alert" class="admin-error">
      {{ resource.error.value }}
      <UButton
        size="xs"
        color="neutral"
        variant="outline"
        @click="resource.refresh"
        >Retry</UButton
      >
    </div>
    <template v-if="resource.data.value"
      ><p v-if="resource.error.value" class="admin-note">
        Showing the last successful response.
      </p>
      <AdminRows
        v-if="
          Array.isArray(value) && value.every((x) => x && typeof x === 'object')
        "
        :rows="value"
        :columns="columns" /><AdminRecord v-else :value="value"
    /></template>
  </section>
</template>
