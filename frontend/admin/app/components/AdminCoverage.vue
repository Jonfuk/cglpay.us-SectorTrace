<script setup lang="ts">
import type { AdminRecord } from '~/lib/operator';
const props = defineProps<{ tier: string }>();
const data = useOperatorResource('/api/admin/coverage', () => ({
  tier: props.tier,
}));
const q = ref('');
const rows = computed<AdminRecord[]>(() =>
  (data.data.value?.authorities || []).filter((r: AdminRecord) =>
    `${r.name} ${r.ons_code} ${r.region}`
      .toLowerCase()
      .includes(q.value.toLowerCase()),
  ),
);
const columns = computed<AdminRecord[]>(() => data.data.value?.columns || []);
</script>
<template>
  <section class="admin-panel">
    <div class="admin-actions justify-between mb-4">
      <h2>Coverage matrix</h2>
      <label class="admin-field"
        >Filter authority<input v-model="q" type="search"
      /></label>
    </div>
    <p v-if="data.error.value" class="admin-error">{{ data.error.value }}</p>
    <p v-if="data.pending.value" class="admin-note">Loading coverage…</p>
    <template v-if="data.data.value">
      <p class="admin-note mb-4" v-if="tier === 'upper'">
        {{ data.data.value.authority_count }} authorities responsible for public
        health. Districts are excluded because they have no treatment
        commissioning role.
      </p>
      <p class="admin-note mb-4" v-else>
        All {{ data.data.value.authority_count }} authorities. Districts will
        have no records in many columns by design; this does not establish an
        evidence gap.
      </p>
      <div class="admin-scroll">
        <table>
          <caption class="sr-only">
            Recorded rows by authority and evidence source. Each column is a
            separate evidence layer.
          </caption>
          <thead>
            <tr>
              <th scope="col">Authority</th>
              <th scope="col">Region</th>
              <th v-for="column in columns" :key="column.label" scope="col">
                <span>{{ column.label }}</span
                ><span class="block admin-note">{{
                  column.missing
                    ? 'Unavailable'
                    : `${column.covered} / ${data.data.value.authority_count} authorities`
                }}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.ons_code">
              <th scope="row" class="!bg-transparent">
                {{ row.name
                }}<span class="admin-note font-mono block">{{
                  row.ons_code
                }}</span>
              </th>
              <td>{{ row.region ?? '—' }}</td>
              <td v-for="column in columns" :key="column.label">
                <span v-if="column.missing" class="admin-note">Unavailable</span
                ><span v-else-if="row.cells?.[column.label] != null">{{
                  row.cells[column.label]
                }}</span
                ><span v-else class="admin-note">No recorded rows</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!rows.length" class="admin-note mt-4">
        No authorities match this filter.
      </p>
      <details class="mt-4">
        <summary>Coverage definitions and metadata</summary>
        <AdminRecord
          :value="
            Object.fromEntries(
              Object.entries(data.data.value).filter(
                ([k]) => k !== 'authorities',
              ),
            )
          "
        />
      </details>
    </template>
  </section>
</template>
