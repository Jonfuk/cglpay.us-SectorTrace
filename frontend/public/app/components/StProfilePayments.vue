<script setup lang="ts">
import type { Column } from '~/components/StEvidenceTable.vue'
type Row = Record<string, unknown>
interface Payments { payments?: Row[]; files?: Row[]; total?: number; caveats?: Record<string, string | null> }
const props = defineProps<{ authorityCode?: string; providerKey?: string }>()
const api = usePublicApi()
const { data, pending, error, refresh } = await useAsyncData(
  () => `profile-payments-${props.authorityCode ?? ''}-${props.providerKey ?? ''}`,
  (_app, { signal }) => api.get<Payments>('/council_spend', { query: { authority_ons_code: props.authorityCode, provider_key: props.providerKey, limit: 100 }, signal }),
)
const columns: Column<Row>[] = [
  { key: 'period', label: 'Source period' }, { key: 'payee', label: 'Payee' },
  { key: 'amount_text', label: 'Published amount' }, { key: 'description', label: 'Description' },
  { key: 'canonical_name', label: 'Matched provider' }, { key: 'source_url', label: 'Source', link: true },
]
const fileColumns: Column<Row>[] = [
  { key: 'file_format', label: 'Format' }, { key: 'parse_status', label: 'Parse status' },
  { key: 'row_count', label: 'Rows', numeric: true }, { key: 'source_url', label: 'Source', link: true },
]
</script>
<template>
  <section class="atlas-section"><h2>Published council payments</h2><p>These are payment lines from published transparency files. They are separate from grants, budgets and procurement notice values. No date filter is applied.</p>
    <StEvidenceState :pending="pending" :error="error" @retry="refresh">
      <p class="atlas-footnote">{{ data?.payments?.length ?? 'Not supplied' }} payment lines returned<span v-if="data?.total !== undefined"> of {{ data.total }} matching records</span>. This view requests at most 100 lines.</p>
      <StEvidenceTable :columns="columns" :rows="data?.payments" caption="Published payment lines" source-details />
      <p v-if="!data?.payments?.length">No payment lines were returned. Check the file statuses below for collection or parsing gaps.</p>
      <StEvidenceTable :columns="fileColumns" :rows="data?.files" caption="Transparency files returned for this selection" source-details />
      <StCaveat v-for="(text, key) in data?.caveats ?? {}" :key="key" :text="text" />
    </StEvidenceState>
  </section>
</template>
