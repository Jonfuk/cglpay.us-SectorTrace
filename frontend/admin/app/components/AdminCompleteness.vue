<script setup lang="ts">
const data = useOperatorResource('/api/admin/completeness');
</script>
<template>
  <section class="admin-panel">
    <h2>Coverage actions</h2>
    <p v-if="data.error.value" class="admin-error">{{ data.error.value }}</p>
    <p class="admin-note mb-4">{{ data.data.value?.caveat }}</p>
    <AdminRows
      :rows="data.data.value?.datasets || []"
      :columns="[
        'title',
        'evidence_layer',
        'row_count',
        'pending_review',
        'reason',
        'reason_note',
      ]"
      ><template #actions="{ row }"
        ><NuxtLink
          v-if="row.action?.kind === 'review'"
          :to="{ path: '/review', query: { module: row.action.target } }"
          >{{ row.action.label }}</NuxtLink
        ><NuxtLink
          v-else-if="row.action?.kind === 'run'"
          :to="{ path: '/pipeline', query: { module: row.action.target } }"
          >{{ row.action.label }}</NuxtLink
        >
        <details v-else>
          <summary>{{ row.action?.label || 'Dataset details' }}</summary>
          <AdminRecord :value="row" /></details></template
    ></AdminRows>
  </section>
</template>
