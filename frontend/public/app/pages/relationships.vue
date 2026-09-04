<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { RelationshipEdge, RelationshipsResponse } from '~/types/api'

// Relationships route. The entity relationship neighbourhood for a chosen
// centre (an authority or provider). Relationships carry dated evidence; the
// exact edge semantics are preserved (no aggregation into a single tie).
// Parity target: legacy `public/js/pages/relationships.js`.
const api = usePublicApi()
const filters = useFilterState()

interface EntityChoice { ons_code?: string | null; provider_key?: string | null; name?: string | null; canonical_name?: string | null }
interface RelationshipDetail { timeline?: Array<Record<string, unknown>>; caveat?: string | null; truncated?: boolean }

const { data: choices } = await useAsyncData('relationship-choices', async () => {
  const [authorityData, providerData] = await Promise.all([
    api.get<{ authorities?: EntityChoice[] }>('/authorities'),
    api.providers(),
  ])
  return { authorities: authorityData.authorities ?? [], providers: providerData.providers ?? [] }
}, { default: () => ({ authorities: [], providers: [] }) })

const { data, pending, error } = await useDataRoute<RelationshipsResponse>(
  'public-relationships',
  (f) => api.relationships({ query: f }),
)

const edges = computed<RelationshipEdge[]>(() => data.value?.edges ?? [])
const neighbours = computed(() => data.value?.neighbours ?? [])
const center = computed(() => data.value?.center ?? {})
const nodeNames = computed(() => new Map([
  [String(center.value.entity_id ?? ''), String(center.value.canonical_name ?? '—')],
  ...neighbours.value.map((node) => [String(node.entity_id ?? ''), String(node.canonical_name ?? '—')] as const),
]))
const displayEdges = computed(() => edges.value.map((edge) => ({
  ...edge,
  subject_name: nodeNames.value.get(String(edge.subject_entity_id)) ?? edge.subject_entity_id,
  object_name: nodeNames.value.get(String(edge.object_entity_id)) ?? edge.object_entity_id,
})))
const details = ref<Record<string, RelationshipDetail>>({})
const detailLoading = ref<string | null>(null)

const selectedAuthority = computed(() => String(filters.get('ons_code') ?? ''))
const selectedProvider = computed(() => String(filters.get('provider_key') ?? ''))

async function selectAuthority(value: string): Promise<void> {
  await filters.setAll(value ? { ons_code: value } : {})
}
async function selectProvider(value: string): Promise<void> {
  await filters.setAll(value ? { provider_key: value } : {})
}
async function loadDetail(id: string | null): Promise<void> {
  if (!id || details.value[id]) return
  detailLoading.value = id
  try { details.value[id] = await api.get<RelationshipDetail>(`/relationships/${id}`) }
  finally { detailLoading.value = null }
}

const columns: Column<RelationshipEdge>[] = [
  { key: 'subject_name', label: 'Subject' },
  { key: 'object_name', label: 'Object' },
  { key: 'valid_from', label: 'From', mono: true },
  { key: 'valid_to', label: 'To', mono: true },
  { key: 'confidence', label: 'Confidence' },
  { key: 'source_url', label: 'Source', link: true },
]

useHead({ title: 'SectorTrace — Relationships' })
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Relationships</h1>
      <p class="opacity-70 max-w-2xl">
        The dated relationships around an entity. Each edge keeps its own
        evidence and validity window; nothing is collapsed into a single tie.
      </p>
    </div>

    <div v-if="pending" class="text-sm opacity-60">Loading relationships…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <UCard>
        <template #header><span class="text-sm font-medium">Choose an authority or provider</span></template>
        <div class="flex flex-wrap gap-4 items-end">
          <label class="text-sm grid gap-1"><span class="opacity-70">Authority</span><select :value="selectedAuthority" class="rounded border border-black/15 dark:border-white/15 bg-transparent px-2 py-1" @change="selectAuthority(($event.target as HTMLSelectElement).value)"><option value="">Choose an authority…</option><option v-for="item in choices.authorities" :key="item.ons_code" :value="item.ons_code ?? ''">{{ item.name }} · {{ item.ons_code }}</option></select></label>
          <label class="text-sm grid gap-1"><span class="opacity-70">Provider</span><select :value="selectedProvider" class="rounded border border-black/15 dark:border-white/15 bg-transparent px-2 py-1" @change="selectProvider(($event.target as HTMLSelectElement).value)"><option value="">Choose a provider…</option><option v-for="item in choices.providers" :key="item.provider_key" :value="item.provider_key ?? ''">{{ item.canonical_name }} · {{ item.provider_key }}</option></select></label>
          <button v-if="selectedAuthority || selectedProvider" type="button" class="text-sm underline" @click="filters.setAll({})">Clear</button>
        </div>
      </UCard>
      <StEmptyState
        v-if="!edges.length"
        title="No relationships to show"
        message="Choose an entity (via a provider or authority link) to see its relationship neighbourhood."
      />
      <UCard v-else>
        <template #header>
          <span class="text-sm font-medium">
            {{ edges.length }} edge(s), {{ neighbours.length }} neighbour(s)
          </span>
        </template>
        <StEvidenceTable :columns="columns" :rows="displayEdges" row-key="relationship_id" />
        <div class="mt-4 space-y-2 border-t border-black/10 dark:border-white/10 pt-3">
          <details v-for="edge in edges" :key="`detail-${edge.relationship_id}`" @toggle="loadDetail(edge.relationship_id)">
            <summary class="cursor-pointer text-sm">Show dated contract events for {{ nodeNames.get(String(edge.subject_entity_id)) }} → {{ nodeNames.get(String(edge.object_entity_id)) }}</summary>
            <div class="mt-2 text-sm">
              <span v-if="detailLoading === edge.relationship_id" class="opacity-60">Loading events…</span>
              <template v-else-if="edge.relationship_id && details[edge.relationship_id]">
                <StCaveat :text="details[edge.relationship_id].caveat" />
                <p v-if="details[edge.relationship_id].truncated" class="opacity-70">Showing a bounded timeline; use Contracts for the complete notice set.</p>
                <ul class="list-disc pl-5"><li v-for="(event, index) in details[edge.relationship_id].timeline ?? []" :key="index">{{ event.date ?? event.valid_from ?? 'Undated' }} · {{ event.title ?? event.notice_id ?? 'Contract event' }}<StLink v-if="event.source_url" :href="String(event.source_url)" /></li></ul>
              </template>
            </div>
          </details>
        </div>
      </UCard>
    </template>
  </section>
</template>
