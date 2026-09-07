<script setup lang="ts">
import { pathInputError, verifiedNode, verifiedPathLimitations, verifiedProfile, type VerifiedPath } from '~/lib/verified-path'
import { connectionText } from '~/lib/connections'
import { downloadEvidenceCsv, downloadEvidenceJson } from '~/lib/evidence-export'
const api = usePublicApi()
const filters = useFilterState()
const route = useRoute()
const notebook = useNotebook()
const get = (key: string) => { const value = filters.get(key); return Array.isArray(value) ? value[0] ?? '' : value ?? '' }
const query = computed(() => ({ from_type: get('from_type') || 'provider', from_id: get('from_id'), to_type: get('to_type') || 'authority', to_id: get('to_id'), max_hops: get('max_hops') || '6' }))
const draft = reactive({ ...query.value })
watch(query, value => Object.assign(draft, value))
const invalid = computed(() => pathInputError(query.value))
const signature = computed(() => JSON.stringify(query.value))
const { data, pending, error, refresh } = await useAsyncData('public-verified-path', async (_app, { signal }) => {
  if (invalid.value) return null
  const key = signature.value
  return { key, response: await api.get<VerifiedPath>('/relationship_path', { query: query.value, signal }) }
}, { watch: [signature] })
const current = computed(() => data.value?.key === signature.value ? data.value.response : null)
const hops = computed(() => Array.isArray(current.value?.path) ? current.value.path : null)
const nodes = computed(() => Array.isArray(current.value?.nodes) ? current.value.nodes : [])
const selected = computed(() => { const hop = /^[1-9]\d*$/.test(get('hop')) ? hops.value?.[Number(get('hop')) - 1] : undefined; return hop && (!get('hop_record') || get('hop_record') === JSON.stringify(hop)) ? hop : undefined })
const selection = computed(() => Boolean(get('hop')))
const name = (id: string | null | undefined) => verifiedNode(nodes.value, id)?.label ?? id ?? 'Node identifier not supplied'
const wide = ref(false)
let media: MediaQueryList | undefined
function updateViewport() { wide.value = media?.matches ?? false }
onMounted(() => { media = matchMedia('(min-width: 900px)'); updateViewport(); media.addEventListener('change', updateViewport) })
onBeforeUnmount(() => media?.removeEventListener('change', updateViewport))
const view = computed(() => get('view') || (wide.value ? 'diagram' : 'data'))
const status = ref('')
let trigger: HTMLElement | SVGElement | null = null
async function submit() { status.value = ''; await filters.setAll({ ...filters.all(), ...draft, hop: undefined, hop_record: undefined }) }
function changeKind(side: 'from' | 'to', kind: string) { draft[`${side}_type`] = kind; draft[`${side}_id`] = '' }
async function inspect(index: number, event: Event) { trigger = event.currentTarget as HTMLElement | SVGElement; await filters.setAll({ ...filters.all(), hop: String(index + 1), hop_record: JSON.stringify(hops.value?.[index]) }); await nextTick(); document.querySelector<HTMLElement>('.st-inspector-heading')?.focus() }
async function close() { await filters.setAll({ ...filters.all(), hop: undefined, hop_record: undefined }); await nextTick(); if (trigger?.isConnected) trigger.focus() }
const scope = computed(() => ({ endpoint: '/api/v1/relationship_path', request: query.value, scope: 'complete-returned-bounded-path-response', limitations: verifiedPathLimitations, view: `#${route.fullPath}` }))
const annotation = computed(() => `${verifiedPathLimitations}\nRequest ${JSON.stringify(query.value)}.\n${current.value?.note ?? 'Source note not supplied.'}\n${(hops.value ?? []).map((hop, index) => `Hop ${index + 1}. From ${connectionText(hop.from)} to ${connectionText(hop.to)}. Recorded relationship ${connectionText(hop.relationship_label)} (${connectionText(hop.relationship)}). Basis ${connectionText(hop.basis)}. Source ${connectionText(hop.source_url)}. Retrieved ${connectionText(hop.retrieved_at)}.`).join('\n')}\nView ${import.meta.client ? window.location.origin + window.location.pathname : ''}#${route.fullPath}`)
function download(csv = false) { if (!current.value) return; if (csv) downloadEvidenceCsv('verified-path-returned-hops', hops.value ?? []); else downloadEvidenceJson('verified-path-reference', [current.value], scope.value) }
function save() { if (!current.value) return; status.value = notebook.add({ title: 'Verified path reference', href: `#${route.fullPath}`, note: JSON.stringify({ ...scope.value, response: current.value }, null, 2) }) ? 'Path reference saved to this browser’s notebook.' : 'This browser could not save the reference.' }
useHead({ title: 'Verified paths · SectorTrace' })
</script>
<template>
  <section class="space-y-6"><header class="st-page-header"><p class="atlas-eyebrow">Connections</p><h1>Verified paths</h1><p>A bounded search through relationships whose recorded basis passes the endpoint’s verification rules. Inspect the evidence for every returned hop.</p></header><StConnectionsNav />
    <form class="space-y-4" @submit.prevent="submit"><div class="grid gap-6 md:grid-cols-2"><StPathEndpoint label="Start" :kind="draft.from_type" :identifier="draft.from_id" @kind="changeKind('from', $event)" @identifier="draft.from_id = $event" /><StPathEndpoint label="End" :kind="draft.to_type" :identifier="draft.to_id" @kind="changeKind('to', $event)" @identifier="draft.to_id = $event" /></div><label class="flex items-center gap-3">Maximum hops<select v-model="draft.max_hops" class="atlas-button"><option v-if="!/^[1-6]$/.test(draft.max_hops)" :value="draft.max_hops">Unsupported saved bound: {{ draft.max_hops }}</option><option v-for="bound in 6" :key="bound" :value="String(bound)">{{ bound }}</option></select></label><button type="submit" class="atlas-button">Find verified path</button></form>
    <p class="atlas-caveat">{{ verifiedPathLimitations }}</p><p v-if="get('provider_key') || get('ons_code') || get('year_from') || get('year_to')" class="atlas-footnote">Retained provider, authority and year filters do not alter this search. Only the two submitted endpoints and hop bound apply.</p>
    <p v-if="invalid" role="status">{{ invalid }}</p><StEvidenceState v-else :pending="pending" :error="error" @retry="refresh"><template v-if="current"><p>{{ current.note ?? 'The response did not supply a verification note.' }}</p><dl class="grid gap-3 md:grid-cols-3"><div><dt>Returned hop bound</dt><dd>{{ connectionText(current.max_hops) }}</dd></div><div><dt>Verified-only response flag</dt><dd>{{ connectionText(current.verified_only) }}</dd></div><div><dt>Returned hops</dt><dd>{{ connectionText(current.hops) }}</dd></div></dl>
      <div class="flex flex-wrap gap-2"><button type="button" class="atlas-button" @click="download()">Download path reference JSON</button><button v-if="hops" type="button" class="atlas-button" @click="download(true)">Download returned hops CSV</button><button type="button" class="atlas-button" @click="save">Save path reference</button></div><p class="atlas-footnote">The JSON reference includes the complete returned response, request and limitations. CSV contains only returned hop records. Keep the JSON reference with it.</p><p role="status">{{ status }}</p>
      <StEvidenceState v-if="current.found === false" empty empty-title="No verified path returned" message="No path was returned under this search’s limits. This does not establish that the entities are unconnected." /><p v-if="current.reason" class="atlas-caveat">{{ current.reason }}</p><p v-if="current.found !== true && current.found !== false" role="status">The response did not supply a path-found result.</p>
      <template v-if="current.found === true"><p v-if="!hops" role="status">The path array was not supplied. This is not a zero-hop result.</p><template v-else><p v-if="!hops.length && current.hops === 0">The response returns zero hops. It does not establish a relationship between distinct entities.</p><p v-else-if="!hops.length" role="status">No hop records were supplied for this result.</p><p v-if="!Array.isArray(current.nodes)" role="status">The node array was not supplied. Profile identities cannot be reconstructed from node strings.</p>
      <div class="flex gap-2" role="group" aria-label="Path presentation"><button type="button" class="atlas-button" :aria-pressed="view === 'diagram'" @click="filters.set('view', 'diagram')">Diagram</button><button type="button" class="atlas-button" :aria-pressed="view === 'data'" @click="filters.set('view', 'data')">Data</button></div><p v-if="!['diagram', 'data'].includes(view)" role="status">The saved presentation is unsupported. The ordered evidence list remains available.</p>
      <div class="st-inspector-layout" :class="{ 'has-inspector': selection }"><div class="space-y-4"><NuxtErrorBoundary v-if="view === 'diagram' && hops.length"><LazyStVerifiedPathDiagram :hops="hops" :nodes="nodes" :selected="selected ? get('hop') : ''" :annotation="annotation" @inspect="inspect" /><template #error="{ clearError }"><p role="status">The diagram is unavailable. The ordered evidence list remains available.</p><button type="button" class="atlas-button" @click="clearError">Retry diagram</button></template></NuxtErrorBoundary>
      <ol class="space-y-4" aria-label="Returned path evidence"><li v-for="(hop, index) in hops" :key="index" class="st-path-hop"><h2>Hop {{ index + 1 }}</h2><p>{{ name(hop.from) }} to {{ name(hop.to) }}</p><p>Recorded relationship: {{ hop.relationship_label ?? hop.relationship ?? 'Not supplied' }}</p><p>Basis: {{ hop.basis ?? 'Not supplied' }}</p><StProvenance :provenance="hop" /><button type="button" class="atlas-button" @click="inspect(index, $event)">Inspect hop {{ index + 1 }}</button></li></ol>
      <details><summary>Returned node records</summary><ul><li v-for="(node, index) in nodes" :key="index">{{ connectionText(node) }}</li></ul></details></div>
      <StInspector v-if="selection" :title="`Path hop ${get('hop')}`" @close="close"><template v-if="selected"><h3>Returned hop metadata</h3><dl><template v-for="(value, key) in selected" :key="key"><dt>{{ String(key).replaceAll('_', ' ') }}</dt><dd>{{ connectionText(value) }}</dd></template></dl><StProvenance :provenance="selected" /><p class="atlas-footnote">{{ verifiedPathLimitations }}</p><div v-for="side in ['from', 'to'] as const" :key="side" class="space-y-2"><h3>{{ side === 'from' ? 'Hop start' : 'Hop end' }}</h3><p>{{ name(selected[side]) }}</p><NuxtLink v-if="verifiedProfile(verifiedNode(nodes, selected[side]))" :to="verifiedProfile(verifiedNode(nodes, selected[side]))!">Open {{ side === 'from' ? 'hop start' : 'hop end' }} profile</NuxtLink><p v-else class="atlas-footnote">No unambiguous public provider or authority identifier is available for this node.</p></div></template><p v-else role="status">The saved hop does not identify a returned record. No replacement has been selected.</p></StInspector></div>
      </template></template></template><p v-else role="status">The path response was not supplied.</p></StEvidenceState>
  </section>
</template>
<style scoped>.st-path-hop { padding: 16px; border: 1px solid var(--border-subtle); border-radius: 4px; } dt { color: var(--text-muted); margin-top: 10px; } dd, li { overflow-wrap: anywhere; }</style>
