<script setup lang="ts">
const route = useRoute(),
  filters = useFilterState();
const data = useOperatorResource('/api/admin/failures', () => ({
  ...(route.query as Record<string, string>),
  limit: 50,
}));
function change(key: string, e: Event) {
  void filters.setAll({
    ...filters.all(),
    [key]: (e.target as HTMLInputElement).value,
    offset: undefined,
  });
}
</script>
<template>
  <section>
    <div class="admin-filters">
      <label
        >Module<select
          :value="route.query.module || ''"
          @change="change('module', $event)"
        >
          <option value="">All modules</option>
          <option v-for="module in data.data.value?.modules" :key="module">
            {{ module }}
          </option>
        </select></label
      ><label class="grow"
        >Search failure<input
          type="search"
          :value="route.query.q || ''"
          @change="change('q', $event)"
      /></label>
    </div>
    <p v-if="data.error.value" class="admin-error">{{ data.error.value }}</p>
    <AdminPager
      :total="data.data.value?.total"
      :limit="50"
      :offset="Number(route.query.offset || 0)"
    />
    <div class="admin-panel">
      <h2>Parse failures</h2>
      <AdminRows :rows="data.data.value?.rows || []" />
      <details>
        <summary>Grouped failures</summary>
        <AdminRows :rows="data.data.value?.groups || []" />
      </details>
    </div>
  </section>
</template>
