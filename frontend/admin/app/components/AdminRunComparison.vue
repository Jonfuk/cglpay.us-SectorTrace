<script setup lang="ts">
const runs = useOperatorResource('/api/admin/run-ledger', { limit: 100 });
const a = ref(''),
  b = ref('');
</script>
<template>
  <section>
    <form class="admin-filters" @submit.prevent>
      <label
        >Baseline<select v-model="a">
          <option value="">Automatic baseline</option>
          <option
            v-for="run in runs.data.value?.runs"
            :key="run.run_id"
            :value="run.run_id"
          >
            {{ run.started_at }} · {{ run.status }} · {{ run.run_id }}
          </option>
        </select></label
      ><label
        >Later run<select v-model="b">
          <option value="">Latest run</option>
          <option
            v-for="run in runs.data.value?.runs"
            :key="run.run_id"
            :value="run.run_id"
          >
            {{ run.started_at }} · {{ run.status }} · {{ run.run_id }}
          </option>
        </select></label
      >
    </form>
    <AdminResourcePanel
      title="Run comparison"
      path="/api/admin/run-comparison"
      :query="{ a: a || undefined, b: b || undefined }"
    />
  </section>
</template>
