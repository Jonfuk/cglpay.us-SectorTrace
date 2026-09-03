<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { RelationshipEdge, RelationshipsResponse } from '~/types/api'

// Relationships route. The entity relationship neighbourhood for a chosen
// centre (an authority or provider). Relationships carry dated evidence; the
// exact edge semantics are preserved (no aggregation into a single tie).
// Parity target: legacy `public/js/pages/relationships.js`.
const api = usePublicApi()

const { data, pending, error } = await useDataRoute<RelationshipsResponse>(
  'public-relationships',
  (f) => api.relationships({ query: f }),
)

const edges = computed<RelationshipEdge[]>(() => data.value?.edges ?? [])
const neighbours = computed(() => data.value?.neighbours ?? [])

const columns: Column<RelationshipEdge>[] = [
  { key: 'subject_entity_id', label: 'Subject', mono: true },
  { key: 'object_entity_id', label: 'Object', mono: true },
  { key: 'valid_from', label: 'From', mono: true },
  { key: 'valid_to', label: 'To', mono: true },
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
        <StEvidenceTable :columns="columns" :rows="edges" row-key="relationship_id" />
      </UCard>
    </template>
  </section>
</template>
