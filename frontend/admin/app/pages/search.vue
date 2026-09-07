<script setup lang="ts">
import { safeUrl } from '~/lib/operator';
const route = useRoute(),
  filters = useFilterState();
const form = reactive({
  q: '',
  mode: 'hybrid',
  source_system: '',
  date_from: '',
  date_to: '',
  limit: '20',
});
watch(
  () => route.query,
  (q) => {
    for (const key of Object.keys(form) as (keyof typeof form)[])
      form[key] = String(
        q[key] || (key === 'mode' ? 'hybrid' : key === 'limit' ? '20' : ''),
      );
  },
  { immediate: true },
);
const resource = useOperatorResource(
  '/api/admin/search',
  () => ({
    ...(route.query as Record<string, string>),
    mode: String(route.query.mode || 'hybrid'),
  }),
  false,
);
watch(
  () => route.query,
  () => {
    if (route.query.q) void resource.refresh();
  },
  { immediate: true },
);
const metadata = computed(() => {
  const { results, hits, ...meta } = resource.data.value || {};
  return meta;
});
useHead({ title: 'SectorTrace — Search' });
</script>
<template>
  <section>
    <AdminPageHeader
      title="Search the archive"
      description="Inspect retrieval context and score components. Relevance is search behaviour, not evidence confidence."
      eyebrow="Evidence · Finding aid"
    />
    <form
      class="admin-filters"
      role="search"
      @submit.prevent="filters.setAll({ ...form })"
    >
      <label class="grow"
        >Search query<input
          v-model="form.q"
          type="search"
          required
          placeholder="Find a passage or document…" /></label
      ><label
        >Mode<select v-model="form.mode">
          <option value="hybrid">Hybrid</option>
          <option value="keyword">Keyword</option>
          <option value="semantic">Semantic</option>
        </select></label
      ><label
        >Source<select v-model="form.source_system">
          <option value="">All sources</option>
          <option value="committee_paper_promotion">Committee papers</option>
          <option value="cdp_document_promotion">Partnership documents</option>
        </select></label
      ><label
        >Published from<input v-model="form.date_from" type="date" /></label
      ><label>Published to<input v-model="form.date_to" type="date" /></label
      ><label
        >Results<select v-model="form.limit">
          <option>20</option>
          <option>50</option>
          <option>100</option>
        </select></label
      ><UButton type="submit">Search</UButton>
    </form>
    <p v-if="resource.pending.value" role="status" class="admin-note">
      Searching the archive…
    </p>
    <p v-if="resource.error.value" class="admin-error">
      {{ resource.error.value }}
    </p>
    <p v-if="!route.query.q" class="admin-note">Enter a query to begin.</p>
    <template v-if="resource.data.value"
      ><section class="admin-panel mb-5">
        <h2>Search context</h2>
        <AdminRecord :value="metadata" />
      </section>
      <article
        v-for="(row, i) in resource.data.value.results ||
        resource.data.value.hits ||
        []"
        :key="i"
        class="admin-panel mb-4"
      >
        <div class="admin-actions justify-between">
          <h2>{{ row.title || row.document_id }}</h2>
          <span class="admin-note"
            >{{ row.source_system }} · {{ row.document_type }}</span
          >
        </div>
        <p class="my-4 max-w-prose whitespace-pre-wrap">
          {{ row.snippet || row.text }}
        </p>
        <a
          v-if="safeUrl(row.source_url)"
          :href="row.source_url"
          target="_blank"
          rel="noopener noreferrer"
          >Open source ↗</a
        >
        <details class="mt-4">
          <summary>Provenance, page context and retrieval scores</summary>
          <AdminRecord :value="row" />
        </details>
      </article>
      <p
        v-if="
          !(resource.data.value.results || resource.data.value.hits || [])
            .length
        "
        class="admin-note"
      >
        No matching passages.
      </p></template
    >
  </section>
</template>
