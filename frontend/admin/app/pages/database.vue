<script setup lang="ts">
import { type AdminRecord, textValue, safeUrl } from '~/lib/operator';
const route = useRoute(),
  filters = useFilterState(),
  dialog = useAdminDialog();
const schema = useOperatorResource('/api/schema'),
  graph = useOperatorResource('/api/admin/schema-graph');
const search = ref(''),
  revealed = ref(new Set<string>());
const name = computed(() => String(route.query.table || ''));
const params = computed(
  () =>
    ({
      limit: 50,
      offset: 0,
      ...route.query,
      reveal: revealed.value.has(name.value) ? '1' : undefined,
    }) as Record<string, string | number | undefined>,
);
const table = useOperatorResource(
  () => `/api/table/${encodeURIComponent(name.value)}`,
  params,
  false,
);
watch(
  [name, params],
  () => {
    table.data.value = null;
    if (name.value) void table.refresh();
  },
  { immediate: true },
);
const objects = computed<AdminRecord[]>(() =>
  (schema.data.value?.objects || []).filter((o: AdminRecord) =>
    o.name.toLowerCase().includes(search.value.toLowerCase()),
  ),
);
const definition = computed(() =>
  graph.data.value?.tables?.find((t: AdminRecord) => t.name === name.value),
);
const jumps: Record<string, string> = {
  buyer_ons_code: 'authorities',
  authority_ons_code: 'authorities',
  ons_code: 'authorities',
  provider_key: 'providers',
  company_number: 'companies',
  local_authority_ons_code: 'authorities',
  parent_code: 'authorities',
  supplier_key: 'providers',
  charity_number: 'charity_financials',
  indicator_id: 'fingertips_indicators',
};
function target(column: string) {
  const destination =
    definition.value?.columns?.find((c: AdminRecord) => c.name === column)?.fk
      ?.table || jumps[column];
  return destination !== name.value &&
    schema.data.value?.objects?.some((o: AdminRecord) => o.name === destination)
    ? destination
    : undefined;
}
function sortable(column: string) {
  void filters.setAll({
    ...filters.all(),
    order_by: column,
    dir:
      route.query.order_by === column && route.query.dir !== 'desc'
        ? 'desc'
        : 'asc',
    offset: undefined,
  });
}
async function reveal() {
  if (
    await dialog.confirm(
      `Reveal restricted rows from ${name.value} in this session? These records may contain personal data.`,
    )
  )
    revealed.value.add(name.value);
}
useHead({ title: 'SectorTrace — Database' });
</script>
<template>
  <section>
    <AdminPageHeader
      title="Database"
      description="Browse warehouse tables and views through the read-only connection. Source values remain exactly as stored."
      eyebrow="Data · Warehouse explorer"
    />
    <div class="admin-detail" :data-focused="!!name">
      <aside class="admin-queue admin-panel">
        <label class="admin-field"
          >Find a table or view<input
            v-model="search"
            type="search"
            placeholder="Table name…"
        /></label>
        <p v-if="schema.error.value" class="admin-error">
          {{ schema.error.value }}
        </p>
        <NuxtLink
          v-for="object in objects"
          :key="object.name"
          :to="{ path: '/database', query: { table: object.name } }"
          class="admin-nav-link"
          :aria-current="name === object.name ? 'page' : undefined"
          ><span class="truncate">{{ object.name }}</span
          ><span class="admin-note ml-auto">{{ object.type }}</span></NuxtLink
        >
      </aside>
      <div class="admin-detail-pane min-w-0">
        <template v-if="name"
          ><NuxtLink to="/database" class="admin-mobile-back mb-3"
            >← Tables</NuxtLink
          >
          <h2 class="break-words mb-4">{{ name }}</h2>
          <form class="admin-filters" @submit.prevent="table.refresh">
            <label class="grow"
              >Search rows<input
                type="search"
                :value="route.query.q || ''"
                @change="
                  filters.setAll({
                    ...filters.all(),
                    q: ($event.target as HTMLInputElement).value,
                    offset: undefined,
                  })
                " /></label
            ><UButton
              type="submit"
              color="neutral"
              variant="outline"
              :loading="table.pending.value"
              >Refresh</UButton
            >
          </form>
          <div v-if="table.error.value" class="admin-error" role="alert">
            {{ table.error.value
            }}<UButton
              v-if="name.startsWith('restricted_') && !revealed.has(name)"
              class="mt-3"
              color="neutral"
              variant="outline"
              @click="reveal"
              >Reveal restricted rows</UButton
            >
          </div>
          <p v-if="table.pending.value" class="admin-note">Loading rows…</p>
          <template v-if="table.data.value"
            ><StatusPill
              v-if="table.data.value.restricted"
              label="Restricted · revealed for this session"
              level="warn"
            /><AdminPager
              :total="table.data.value.total"
              :limit="table.data.value.limit"
              :offset="table.data.value.offset"
            />
            <div class="admin-scroll">
              <table>
                <thead>
                  <tr>
                    <th
                      v-for="(column, i) in table.data.value.columns"
                      :key="i"
                    >
                      <button
                        @click="
                          sortable(
                            typeof column === 'string' ? column : column.name,
                          )
                        "
                      >
                        {{ typeof column === 'string' ? column : column.name }}
                        {{
                          route.query.order_by ===
                          (typeof column === 'string' ? column : column.name)
                            ? route.query.dir === 'desc'
                              ? '↓'
                              : '↑'
                            : '↕'
                        }}
                      </button>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, ri) in table.data.value.rows" :key="ri">
                    <td v-for="(value, ci) in row" :key="ci">
                      <NuxtLink
                        v-if="
                          value != null &&
                          target(
                            typeof table.data.value.columns[ci] === 'string'
                              ? table.data.value.columns[ci]
                              : table.data.value.columns[ci].name,
                          )
                        "
                        :to="{
                          path: '/database',
                          query: {
                            table: target(
                              typeof table.data.value.columns[ci] === 'string'
                                ? table.data.value.columns[ci]
                                : table.data.value.columns[ci].name,
                            ),
                            q: String(value),
                          },
                        }"
                        >{{ textValue(value) }}</NuxtLink
                      ><StLink
                        v-else-if="safeUrl(value)"
                        :href="String(value)"
                      />
                      <details v-else-if="textValue(value).length > 180">
                        <summary>{{ textValue(value).slice(0, 100) }}…</summary>
                        <pre>{{ textValue(value) }}</pre>
                      </details>
                      <span v-else>{{ textValue(value) }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-if="!table.data.value.rows?.length" class="admin-note py-4">
              No rows in this view.
            </p></template
          >
          <details v-if="definition" class="admin-panel mt-5">
            <summary>Columns, keys and relationships</summary>
            <p class="admin-note">{{ definition.description }}</p>
            <AdminRows :rows="definition.columns || []" /></details
        ></template>
        <p v-else class="admin-note">
          Choose a table to inspect its rows and schema.
        </p>
      </div>
    </div>
  </section>
</template>
