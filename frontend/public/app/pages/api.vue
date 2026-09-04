<script setup lang="ts">
// API documentation route. Stable, source-independent content — the public
// `/api/v1` surface and where to find its machine-readable contract. Parity
// target: legacy `public/api.html`. The authoritative, always-current schema is
// `/api/openapi.json`, served by the Python server; this page points at it
// rather than duplicating it.
const endpoints: Array<{ path: string; note: string }> = [
  { path: '/api/v1/meta', note: 'Release and data-version identity' },
  { path: '/api/v1/summary', note: 'Landing-page figures with caveats' },
  { path: '/api/v1/pay', note: 'Separate pay-evidence arrays' },
  { path: '/api/v1/contracts', note: 'Procurement notices and rollups' },
  { path: '/api/v1/providers', note: 'Providers with comparable counts' },
  { path: '/api/v1/authorities', note: 'Authorities and their ONS codes' },
  { path: '/api/v1/geography', note: 'One value per authority for a metric' },
  { path: '/api/v1/council_spend', note: 'Published council spending rows' },
  { path: '/api/v1/ndtms', note: 'NDTMS treatment statistics' },
  { path: '/api/v1/fingertips', note: 'Fingertips treatment indicators' },
  { path: '/api/v1/treatment_metrics', note: 'Treatment metric catalogue' },
  { path: '/api/v1/pfd', note: 'Prevention of Future Deaths reports' },
  { path: '/api/v1/safety', note: 'HSE enforcement evidence' },
  { path: '/api/v1/safety_legal', note: 'Separate safety and legal evidence layers' },
  { path: '/api/v1/cqc_locations', note: 'CQC registered locations' },
  { path: '/api/v1/claims', note: 'Published claims and citations' },
  { path: '/api/v1/freshness', note: 'Collection freshness by dataset' },
  { path: '/api/v1/compare', note: 'Parallel authority/provider comparisons' },
  { path: '/api/v1/layers', note: 'Map layer data' },
  { path: '/api/v1/atlas_layers', note: 'Closed atlas layer registry' },
  { path: '/api/v1/relationships', note: 'Commissioning relationship neighbourhood' },
  { path: '/api/v1/relationships/{id}', note: 'Dated events behind a relationship' },
  { path: '/api/v1/relationship_path', note: 'Shortest verified entity path' },
  { path: '/api/v1/document_tables', note: 'Extracted document tables' },
  { path: '/api/v1/source_link', note: 'Archived source-link state' },
  { path: '/api/v1/contract_diary', note: 'Dated procurement events' },
  { path: '/api/v1/discrepancies', note: 'Differences between source observations' },
  { path: '/api/v1/cooccurrence', note: 'Entities named in the same record' },
  { path: '/api/v1/coverage_timeline', note: 'Dataset coverage over time' },
  { path: '/api/v1/catalogue', note: 'Every dataset served, with freshness' },
  { path: '/api/v1/catalogue/{dataset_id}', note: 'One dataset and warehouse holdings' },
  { path: '/api/v1/publication_calendar', note: 'Stated and observed release cadence' },
  { path: '/api/v1/record_diff', note: 'Procurement or document version diff' },
  { path: '/api/v1/changes', note: 'Recorded warehouse changes' },
  { path: '/api/v1/provider_compare', note: 'Separate provider evidence comparison' },
  { path: '/api/v1/document_search', note: 'Full-text document search (?q=)' },
  { path: '/api/v1/boundaries', note: 'Authority boundary geometry (GeoJSON)' },
  { path: '/api/v1/export', note: 'Bulk evidence export' },
]

useHead({
  title: 'SectorTrace — API',
  meta: [{ name: 'description', content: 'The public SectorTrace evidence API and its OpenAPI contract.' }],
})
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">API</h1>
      <p class="opacity-70 max-w-2xl">
        Every figure in this portal is served over a public JSON API with full
        provenance. The authoritative, always-current schema is the OpenAPI
        document.
      </p>
    </div>

    <UCard>
      <template #header>
        <span class="text-sm font-medium">Machine-readable contract</span>
      </template>
      <!-- A hardcoded, same-origin internal path (not a source-derived value),
           so a plain anchor is correct here; StLink is for validating untrusted
           external URLs. -->
      <a
        href="/api/openapi.json"
        class="text-[var(--st-accent)] underline underline-offset-2 font-mono text-sm"
      >/api/openapi.json</a>
    </UCard>

    <UCard>
      <template #header>
        <span class="text-sm font-medium">Endpoints</span>
      </template>
      <ul class="divide-y divide-black/5 dark:divide-white/5">
        <li v-for="e in endpoints" :key="e.path" class="py-2 flex items-baseline gap-4">
          <code class="text-sm font-mono">{{ e.path }}</code>
          <span class="text-xs opacity-60">{{ e.note }}</span>
        </li>
      </ul>
    </UCard>
  </section>
</template>
