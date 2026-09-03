<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { DiscrepancyResponse, DiscrepancyRow } from '~/types/api'

// Discrepancies route. Where sources disagree on an entity's identity-level
// fields. A discrepancy is a difference BETWEEN sources, not an assertion that
// either source is wrong — both observations are shown with their origins.
// Entity read from the URL (?provider_key= or ?ons_code=). Parity target:
// legacy `public/js/pages/discrepancies.js`.
const api = usePublicApi()
const filters = useFilterState()

const hasEntity = computed(
  () => !!(filters.get('provider_key') || filters.get('ons_code')),
)

const { data, pending, error } = await useDataRoute<DiscrepancyResponse | null>(
  'public-discrepancies',
  (f) => {
    if (!f.provider_key && !f.ons_code) return Promise.resolve(null)
    return api.discrepancies({ query: f })
  },
)

const discrepancies = computed<DiscrepancyRow[]>(() => data.value?.discrepancies ?? [])
const agreed = computed<DiscrepancyRow[]>(() => data.value?.agreed ?? [])

const agreedColumns: Column<DiscrepancyRow>[] = [
  { key: 'label', label: 'Field' },
  { key: 'value', label: 'Agreed value' },
]
</script>

<template>
  <section class="space-y-6">
    <div class="space-y-2">
      <h1 class="text-2xl font-semibold">Source discrepancies</h1>
      <p class="opacity-70 max-w-2xl">
        Where sources disagree on an entity's identity fields. A discrepancy is a
        difference between sources, not proof that either is wrong.
      </p>
    </div>

    <StEmptyState
      v-if="!hasEntity"
      title="Choose an entity"
      message="Open this view from a provider or authority to compare what its sources say."
    />
    <div v-else-if="pending" class="text-sm opacity-60">Checking sources…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <UCard>
        <template #header>
          <span class="text-sm font-medium">
            {{ discrepancies.length }} discrepancies
            <span class="opacity-60">· {{ data?.checked ?? 0 }} fields checked</span>
          </span>
        </template>
        <div v-if="discrepancies.length" class="space-y-4">
          <div v-for="d in discrepancies" :key="d.id" class="space-y-2">
            <p class="text-sm font-medium">{{ d.label }}</p>
            <ul class="text-sm space-y-1">
              <li
                v-for="(obs, i) in d.observations ?? []"
                :key="i"
                class="flex gap-3"
              >
                <span class="opacity-60">{{ (obs as Record<string, unknown>).source }}</span>
                <span>{{ (obs as Record<string, unknown>).value ?? '—' }}</span>
              </li>
            </ul>
          </div>
        </div>
        <StEmptyState
          v-else
          title="No discrepancies"
          message="Every source that reports these fields agrees."
        />
        <template v-if="data?.caveat" #footer>
          <StCaveat :text="data.caveat" />
        </template>
      </UCard>

      <UCard v-if="agreed.length">
        <template #header>
          <span class="text-sm font-medium">Agreed fields</span>
        </template>
        <StEvidenceTable :columns="agreedColumns" :rows="agreed" row-key="id" />
      </UCard>
    </template>
  </section>
</template>
