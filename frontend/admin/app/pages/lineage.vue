<script setup lang="ts">
import type { AdminRecord } from '~/lib/operator';
const graph = useOperatorResource('/api/admin/lineage');
const q = ref(''),
  kinds = ref<string[]>([]),
  selected = ref('');
watch(graph.data, (data) => {
  if (data && !kinds.value.length) kinds.value = [...data.node_kinds];
});
const nodes = computed<AdminRecord[]>(() =>
  (graph.data.value?.nodes || []).filter(
    (n: AdminRecord) =>
      kinds.value.includes(n.kind) &&
      JSON.stringify(n).toLowerCase().includes(q.value.toLowerCase()),
  ),
);
const node = computed(() =>
  graph.data.value?.nodes?.find((n: AdminRecord) => n.id === selected.value),
);
const edges = computed<AdminRecord[]>(() =>
  (graph.data.value?.edges || []).filter(
    (e: AdminRecord) =>
      e.source === selected.value ||
      e.target === selected.value ||
      e.from === selected.value ||
      e.to === selected.value,
  ),
);
useHead({ title: 'SectorTrace — Data lineage' });
</script>
<template>
  <section>
    <AdminPageHeader
      title="Data lineage"
      description="Trace relationships from sources through modules and tables to exports. Every edge comes from the recorded catalogue."
      eyebrow="Data · Dependencies"
    />
    <div class="admin-filters">
      <label class="grow">Find a node<input v-model="q" type="search" /></label
      ><label
        v-for="kind in graph.data.value?.node_kinds"
        :key="kind"
        class="!flex items-center"
        ><input v-model="kinds" type="checkbox" :value="kind" />{{
          kind
        }}</label
      >
    </div>
    <p v-if="graph.error.value" class="admin-error">{{ graph.error.value }}</p>
    <div class="admin-detail" :data-focused="!!node">
      <div class="admin-queue admin-panel">
        <button
          v-for="n in nodes"
          :key="n.id"
          class="admin-nav-link w-full text-left"
          :aria-current="selected === n.id ? 'page' : undefined"
          @click="selected = n.id"
        >
          {{ n.label || n.name || n.id
          }}<span class="admin-note ml-auto">{{ n.kind }}</span>
        </button>
      </div>
      <section class="admin-detail-pane admin-panel">
        <UButton
          v-if="node"
          class="admin-mobile-back mb-3"
          color="neutral"
          variant="ghost"
          @click="selected = ''"
          >← Nodes</UButton
        ><template v-if="node"
          ><h2>{{ node.label || node.id }}</h2>
          <AdminRecord :value="node" />
          <h3 class="mt-5 mb-3">Upstream and downstream</h3>
          <AdminRows :rows="edges"
            ><template #actions="{ row }"
              ><UButton
                size="xs"
                variant="outline"
                color="neutral"
                @click="
                  selected =
                    (row.source || row.from) === selected
                      ? row.target || row.to
                      : row.source || row.from
                "
                >Follow relationship</UButton
              ></template
            ></AdminRows
          ></template
        >
        <p v-else class="admin-note">
          Choose a node to inspect what feeds it and what it feeds.
        </p>
      </section>
    </div>
    <p class="admin-note mt-4">{{ graph.data.value?.note }}</p>
  </section>
</template>
