<script setup lang="ts">
import { textValue, labelFor, safeUrl, type AdminRecord } from '~/lib/operator';
const props = defineProps<{ rows: AdminRecord[]; columns?: string[] }>();
const keys = computed(
  () =>
    props.columns || [
      ...new Set(props.rows.flatMap((row) => Object.keys(row))),
    ],
);
</script>
<template>
  <div class="admin-scroll">
    <p v-if="!rows.length" class="admin-note py-4">No records in this view.</p>
    <table v-else>
      <thead>
        <tr>
          <th v-for="key in keys" :key="key">{{ labelFor(key) }}</th>
          <th v-if="$slots.actions">Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in rows" :key="index">
          <td v-for="key in keys" :key="key">
            <StLink v-if="safeUrl(row[key])" :href="row[key]" />
            <details v-else-if="row[key] && typeof row[key] === 'object'">
              <summary>Inspect {{ labelFor(key) }}</summary>
              <AdminRecord :value="row[key]" />
            </details>
            <span v-else>{{ textValue(row[key]) }}</span>
          </td>
          <td v-if="$slots.actions"><slot name="actions" :row="row" /></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
