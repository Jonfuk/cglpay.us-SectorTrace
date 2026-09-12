<script setup lang="ts">
import type { Column } from '~/components/StEvidenceTable.vue'
import type { ContractNotice, ContractsResponse } from '~/types/api'
const props = defineProps<{ providerKey?: string; authorityCode?: string }>()
const api = usePublicApi()
const query = computed(() => ({ provider_key: props.providerKey, buyer_ons_code: props.authorityCode, limit: 50 }))
const { data, pending, error, refresh } = await useAsyncData(
  () => `profile-notices-${props.providerKey ?? ''}-${props.authorityCode ?? ''}`,
  (_app, { signal }) => api.contracts({ query: query.value, signal }) as Promise<ContractsResponse & { total?: number }>,
)
const columns: Column<ContractNotice>[] = [
  { key: 'date_published', label: 'Published', mono: true },
  { key: 'title', label: 'Notice' },
  { key: 'buyer_name', label: 'Buyer', to: row => row.buyer_ons_code ? `/authorities/${encodeURIComponent(String(row.buyer_ons_code))}` : null },
  { key: 'supplier_name_raw', label: 'Supplier as published' },
  { key: 'value_core', label: 'Published value', numeric: true },
  { key: 'currency', label: 'Currency' },
  { key: 'ocid', label: 'Procurement process', to: row => row.ocid ? `/contracts/process/${encodeURIComponent(row.ocid)}` : null },
  { key: 'notice_link', label: 'Notice link', link: true },
  { key: 'notice_link_basis', label: 'Link basis' },
  { key: 'source_url', label: 'Data source', link: true },
]
</script>
<template>
  <section class="atlas-section">
    <h2>Contract notices</h2><p>These are published procurement records. Values may be estimates or ceilings and do not describe payments or provider income.</p>
    <NuxtLink :to="{ path: '/contracts', query: { provider_key: providerKey, buyer_ons_code: authorityCode } }" class="atlas-button">Explore matching notices</NuxtLink>
    <StEvidenceState :pending="pending" :error="error" :empty="!data?.notices?.length" empty-title="No matching notices held" @retry="refresh">
      <p class="atlas-footnote">Showing {{ data?.notices.length }} notices<span v-if="data?.total !== undefined"> of {{ data.total }} matching records</span>. This profile requests at most 50 notices.</p>
      <StEvidenceTable :columns="columns" :rows="data?.notices" row-key="notice_id" />
      <StCaveat v-for="(caveat, name) in data?.caveats ?? {}" :key="name" :text="caveat" />
    </StEvidenceState>
  </section>
</template>
