<script setup lang="ts">
import type { CqcLocation } from '~/types/api'
const props = defineProps<{ row: CqcLocation }>()
const route = useRoute()
const notebook = useNotebook()
const feedback = ref('')
const fields = [
  ['location_id', 'Location identifier'], ['provider_id', 'CQC provider identifier'],
  ['registration_status', 'Registration status'], ['registration_date', 'Registered'],
  ['last_inspection_date', 'Last inspection'], ['overall_rating', 'Overall rating'],
  ['overall_rating_date', 'Rating dated'], ['regulated_activities', 'Regulated activities'],
  ['service_types', 'Service types'], ['local_authority_raw', 'Published authority name'],
  ['local_authority_ons_code', 'Authority ONS code'], ['postal_code', 'Postcode'], ['region', 'Region'],
  ['latitude', 'Latitude'], ['longitude', 'Longitude'],
] as const
const origin = computed(() => props.row.rating_source === 'api' ? 'CQC API' : props.row.rating_source === 'bulk_export' ? 'CQC bulk export' : props.row.rating_source ?? 'Not supplied')
function save() {
  const row = props.row
  const note = [`Location: ${row.location_id}`, `Rating origin: ${origin.value}`, ...fields.map(([key, label]) => `${label}: ${row[key] ?? 'Not supplied'}`), `Source: ${row.source_url ?? 'Not supplied'}`, `Retrieved: ${row.retrieved_at ?? 'Not supplied'}`, 'This link restores a result window. Its contents may change.'].join('\n')
  feedback.value = notebook.add({ title: row.location_name ?? row.location_id ?? 'CQC registration', href: route.fullPath, note }) ? 'Registration saved to this browser’s notebook.' : 'The registration could not be saved in this browser.'
}
async function copy() {
  try { await navigator.clipboard.writeText(window.location.href); feedback.value = 'Result-window link copied.' }
  catch { feedback.value = 'Copy is unavailable. Copy the page address from your browser.' }
}
</script>
<template>
  <div class="space-y-4">
    <p class="atlas-footnote">CQC registration · {{ row.location_id }}</p>
    <p><NuxtLink v-if="row.provider_key" :to="`/providers/${encodeURIComponent(row.provider_key)}`">{{ row.provider_name ?? row.provider_key }}</NuxtLink><span v-else>{{ row.provider_name ?? 'Provider not supplied' }}</span></p>
    <dl class="st-cqc-record"><template v-for="[key, label] in fields" :key="key"><dt>{{ label }}</dt><dd>{{ row[key] ?? 'Not supplied' }}</dd></template><dt>Rating origin</dt><dd>{{ origin }}</dd></dl>
    <p v-if="row.rating_source === 'bulk_export'" class="atlas-footnote">The rating comes from CQC’s bulk export because the API supplied no rating. This response does not include the bulk rating’s source URL or retrieval date.</p>
    <StProvenance :provenance="row" />
    <p class="atlas-footnote">Source details describe the returned location record. Registration, inspection and rating dates above have separate meanings.</p>
    <div class="st-inspector-actions"><StLink v-if="row.source_url" :href="row.source_url" class="atlas-button">Open CQC source</StLink><NuxtLink v-if="row.provider_key" :to="`/providers/${encodeURIComponent(row.provider_key)}`" class="atlas-button">Open provider profile</NuxtLink><NuxtLink v-if="row.local_authority_ons_code" :to="`/authorities/${encodeURIComponent(row.local_authority_ons_code)}`" class="atlas-button">Open authority profile</NuxtLink><button type="button" class="atlas-button" @click="copy">Copy selection link</button><button type="button" class="atlas-button" @click="save">Save registration</button></div>
    <p class="atlas-footnote">Selection links restore these filters, this result page and the location identifier. They may become unavailable when the returned page changes.</p><p role="status">{{ feedback }}</p>
  </div>
</template>
<style scoped>
.st-cqc-record { display: grid; grid-template-columns: minmax(90px, .8fr) minmax(0, 1.2fr); gap: 12px; font-size: 13px; }
.st-cqc-record dt { color: var(--text-muted); }
.st-cqc-record dd { overflow-wrap: anywhere; }
</style>
