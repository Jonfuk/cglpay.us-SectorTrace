<script setup lang="ts">
import { downloadEvidenceCsv, downloadEvidenceJson } from '~/lib/evidence-export'
interface LinkArchive { held?: boolean; bytes?: number; verified?: boolean | null; sha256?: string | null; computed_sha256?: string | null; note?: string; [key: string]: unknown }
interface LinkDetail { url: string; state?: string; state_label?: string; last_checked?: string | null; last_http_status?: number | null; observed_in?: string | null; archive?: LinkArchive; note?: string | null; caveat?: string | null; [key: string]: unknown }
interface LinkOverview { states?: string[]; by_state?: Record<string, number>; note?: string | null; [key: string]: unknown }
const api = usePublicApi()
const filters = useFilterState()
const route = useRoute()
const notebook = useNotebook()
const value = computed(() => filters.get('url'))
const url = computed(() => Array.isArray(value.value) ? value.value[0] ?? '' : value.value ?? '')
const draft = ref(url.value)
watch(url, current => { draft.value = current })
const valid = computed(() => { if (Array.isArray(value.value) || !url.value) return false; try { return ['http:', 'https:'].includes(new URL(url.value).protocol) } catch { return false } })
const signature = computed(() => JSON.stringify({ url: url.value, valid: valid.value }))
const { data, pending, error, refresh } = await useAsyncData('public-recorded-source-link', async (_app, { signal }) => {
  const key = signature.value
  const response = valid.value ? await api.get<LinkDetail>('/source_link', { query: { url: url.value }, signal }) : null
  return { key, response }
}, { watch: [signature] })
const current = computed(() => !pending.value && !error.value && data.value?.key === signature.value ? data.value.response : null)
const { data: overview, pending: overviewPending, error: overviewError, execute: loadOverview } = await useAsyncData('public-recorded-link-overview', (_app, { signal }) => api.get<LinkOverview>('/source_link', { signal }), { immediate: false })
const feedback = ref('')
const limitations = 'This is recorded collection metadata, not a live availability test. Archive hashes and verification flags describe the returned archive record. Its separate retrieval date is not supplied, so the latest link-check date cannot authenticate its age or an older cited observation. No public archive download is supplied.'
function context() { return { endpoint: '/api/v1/source_link', request: { url: url.value }, view: `#${route.fullPath}`, scope: 'one-returned-recorded-source-link-response', limitations } }
function download(kind: 'json' | 'csv') { if (!current.value) return; if (kind === 'csv') downloadEvidenceCsv('recorded-source-link', [current.value]); else downloadEvidenceJson('recorded-source-link', [current.value], context()) }
function save() { if (!current.value) return; feedback.value = notebook.add({ title: `Recorded source link: ${current.value.url}`, href: `#${route.fullPath}`, note: JSON.stringify({ ...context(), record: current.value }, null, 2) }) ? 'Recorded source reference saved in this browser.' : 'The reference remains in memory. Browser storage could not be updated. Export it before leaving.' }
function submit() { feedback.value = ''; return filters.set('url', draft.value.trim() || undefined) }
function clear() { draft.value = ''; feedback.value = ''; return filters.set('url', undefined) }
function exportOverview() { if (overview.value) downloadEvidenceJson('recorded-source-link-counts', [overview.value], { endpoint: '/api/v1/source_link', scope: 'warehouse-cited-row-counts', limitations: 'Counts are cited rows, not distinct URLs or current availability. No cross-state total is calculated.' }) }
useHead({ title: 'Source links · SectorTrace' })
</script>
<template>
  <section class="space-y-6">
    <header class="st-page-header"><p class="atlas-eyebrow">Verification tools</p><h1>Source links</h1><p>Inspect recorded source availability and archive metadata for an exact URL. This tool does not contact the publisher.</p></header>
    <form class="flex flex-wrap items-end gap-3" @submit.prevent="submit"><label class="grid gap-2 min-w-0 flex-1">Source URL<input v-model="draft" type="url" class="atlas-button w-full min-w-0" placeholder="https://example.org/source"></label><button type="submit" class="atlas-button">Check recorded status</button><button v-if="value" type="button" class="atlas-button" @click="clear">Clear</button></form>
    <p v-if="value && !valid" role="status">Supply exactly one valid HTTP or HTTPS source URL. Repeated URL values are not combined.</p>
    <StEvidenceState v-if="valid" :pending="pending" :error="error" @retry="refresh"><section v-if="current" class="atlas-panel atlas-panel-body space-y-4" aria-label="Recorded source status">
      <h2>Recorded source status</h2><StLink :href="current.url">Open original source</StLink><p class="break-all">{{ current.url }}</p>
      <dl class="st-link-fields"><dt>Recorded state</dt><dd>{{ current.state?.replaceAll('_', ' ') ?? 'Not supplied' }}</dd><dt>State explanation</dt><dd>{{ current.state_label ?? 'Not supplied' }}</dd><dt>Last recorded check</dt><dd>{{ current.last_checked ?? 'Not supplied' }}</dd><dt>Recorded HTTP status</dt><dd>{{ current.last_http_status ?? 'Not supplied' }}</dd><dt>Archive file held</dt><dd>{{ current.archive?.held === true ? 'Held' : current.archive?.held === false ? 'Not held' : 'Not supplied' }}</dd><dt>Archive byte count</dt><dd>{{ current.archive?.bytes ?? 'Not supplied' }}</dd><dt>Archive checksum check</dt><dd>{{ current.archive?.verified === true ? 'Matching checksum reported by the API' : current.archive?.verified === false ? 'Checksum mismatch reported by the API' : 'No verification result supplied' }}</dd><dt>Recorded archive SHA-256</dt><dd>{{ current.archive?.sha256 ?? 'Not supplied' }}</dd><dt>Computed archive SHA-256</dt><dd>{{ current.archive?.computed_sha256 ?? 'Not supplied' }}</dd></dl>
      <p class="atlas-caveat">{{ limitations }}</p><StCaveat v-if="current.caveat" :text="current.caveat" /><p v-if="current.note" class="whitespace-pre-wrap">{{ current.note }}</p><p v-if="current.archive?.note" class="whitespace-pre-wrap">{{ current.archive.note }}</p>
      <details><summary>Complete returned metadata</summary><pre>{{ JSON.stringify(current, null, 2) }}</pre></details>
      <div class="flex flex-wrap gap-2"><button type="button" class="atlas-button" @click="download('json')">Download recorded status JSON</button><button type="button" class="atlas-button" @click="download('csv')">Download recorded status CSV</button><button type="button" class="atlas-button" @click="save">Save recorded reference</button></div><p class="atlas-footnote">Keep the JSON with the CSV for the request and provenance limitations. Neither file contains archived source bytes.</p><p v-if="feedback" role="status">{{ feedback }}</p>
    </section></StEvidenceState>
    <details><summary>Warehouse cited-row counts</summary><p class="atlas-footnote">Counts describe cited rows, not distinct URLs or current availability. Loading this summary does not check any publisher.</p><button type="button" class="atlas-button" @click="loadOverview()">Load recorded counts</button><StEvidenceState :pending="overviewPending" :error="overviewError" @retry="loadOverview()"><template v-if="overview"><p>{{ overview.note }}</p><div class="overflow-x-auto" role="region" aria-label="Recorded link-state counts" tabindex="0"><table><thead><tr><th>Recorded state</th><th>Cited rows</th></tr></thead><tbody><tr v-for="state in overview.states ?? Object.keys(overview.by_state ?? {})" :key="state"><td>{{ state.replaceAll('_', ' ') }}</td><td>{{ overview.by_state?.[state] ?? 'Not supplied' }}</td></tr></tbody></table></div><button type="button" class="atlas-button" @click="exportOverview">Download recorded counts JSON</button><details><summary>Complete count metadata</summary><pre>{{ JSON.stringify(overview, null, 2) }}</pre></details></template></StEvidenceState></details>
  </section>
</template>
<style scoped>
.st-link-fields { display: grid; grid-template-columns: minmax(100px, 1fr) minmax(0, 2fr); gap: 12px; }
.st-link-fields dt { color: var(--text-muted); }
.st-link-fields dd, pre { overflow-wrap: anywhere; white-space: pre-wrap; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border-subtle); }
th:last-child, td:last-child { text-align: right; font-variant-numeric: tabular-nums; }
</style>
