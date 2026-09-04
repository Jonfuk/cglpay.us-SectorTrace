<script setup lang="ts">
import { computed } from 'vue'
import type { PathNode, PathResponse } from '~/types/api'

// Pathfinder — the shortest VERIFIED path between two entities. Unconfirmed
// name-match edges are excluded and the traversal is hop-bounded; a path is a
// chain of verified edges, never an asserted relationship strength. Endpoints
// are read from the URL (?from_type=&from_id=&to_type=&to_id=). Parity target:
// legacy `public/js/pages/pathfinder.js`.
const api = usePublicApi()
const filters = useFilterState()

const hasEndpoints = computed(
  () => !!(filters.get('from_id') && filters.get('to_id')),
)

const { data, pending, error } = await useDataRoute<PathResponse | null>(
  'public-pathfinder',
  (f) => {
    if (!f.from_id || !f.to_id) return Promise.resolve(null)
    return api.relationshipPath({ query: f })
  },
)

const nodes = computed<PathNode[]>(() => data.value?.nodes ?? [])
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold">Pathfinder</h1>
    <p class="opacity-70 max-w-2xl text-sm">
      The shortest verified path between two entities. Only confirmed edges are
      followed — a path is a chain of verified relationships, not a measure of
      how strongly two entities are linked.
    </p>

    <StEmptyState
      v-if="!hasEndpoints"
      title="Choose two entities"
      message="Open this view with a start and end entity (?from_id=…&to_id=…) to find a verified path between them."
    />
    <div v-else-if="pending" class="text-sm opacity-60">Searching for a path…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else-if="data">
      <StEmptyState
        v-if="!data.found"
        title="No verified path"
        message="No chain of confirmed edges connects these two entities within the hop limit. That is not proof they are unconnected — only that no verified path was found."
      />
      <UCard v-else>
        <template #header>
          <span class="text-sm font-medium">{{ data.hops }} hop(s)</span>
        </template>
        <ol class="space-y-2">
          <li
            v-for="(n, i) in nodes"
            :key="i"
            class="flex items-center gap-2 text-sm"
          >
            <span class="opacity-40 font-mono">{{ i + 1 }}</span>
            <span class="font-medium">{{ n.node }}</span>
            <span class="opacity-60">({{ n.type }})</span>
          </li>
        </ol>
      </UCard>
    </template>
  </section>
</template>
