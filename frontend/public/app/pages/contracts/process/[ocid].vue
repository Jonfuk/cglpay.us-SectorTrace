<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
type Row = Record<string, any>
interface Stage { stage: string; present: boolean; notices: Row[] }
interface ProcessResponse { ocid: string; buyer?: { name?: string | null; ons_code?: string | null }; stages?: Stage[]; notice_count?: number; date_range?: { earliest?: string | null; latest?: string | null }; caveat?: string | null }
const route = useRoute()
const api = usePublicApi()
const ocid = computed(() => String(route.params.ocid ?? ''))
const { data, pending, error } = await useAsyncData<ProcessResponse | null>(() => `contract-process-${ocid.value}`, () => api.get<ProcessResponse>(`/contracts/process/${encodeURIComponent(ocid.value)}`), { default: () => null, watch: [ocid] })
const labels: Record<string, string> = { planning: 'Planning', tender: 'Tender', award: 'Award', contract: 'Contract', amendment: 'Amendment', termination: 'Termination', implementation: 'Implementation', other: 'Other / untagged' }
const columns: Column<Row>[] = [{ key: 'date_published', label: 'Published', mono: true }, { key: 'title', label: 'Notice' }, { key: 'ocds_tags_text', label: 'OCDS tags' }, { key: 'value_core', label: 'Published value', numeric: true }, { key: 'procedure_type', label: 'Procedure' }, { key: 'notice_web_url', label: 'Notice', link: true }, { key: 'source_url', label: 'Source', link: true }]
function rows(stage: Stage): Row[] { return stage.notices.map((notice, index) => ({ ...notice, ocds_tags_text: Array.isArray(notice.ocds_tags) ? notice.ocds_tags.join(', ') : notice.ocds_tags, row_key: `${stage.stage}-${index}-${notice.notice_id ?? ''}` })) }
useHead(() => ({ title: `SectorTrace — Procurement lifecycle ${ocid.value}` }))
</script>

<template>
  <section class="space-y-8"><NuxtLink to="/contracts" class="text-sm opacity-70 hover:opacity-100">← All contracts</NuxtLink><div class="atlas-hero"><div><p class="atlas-kicker">Procurement lifecycle · one OCID</p><h1>Procurement lifecycle</h1><p class="atlas-lede">{{ data?.notice_count ?? '—' }} notices published under one OCID{{ data?.buyer?.name ? ` by ${data.buyer.name}` : '' }}{{ data?.date_range?.earliest ? ` · ${data.date_range.earliest.slice(0, 10)} to ${data.date_range.latest?.slice(0, 10) ?? '—'}` : '' }}.</p><p class="font-mono text-sm opacity-70">{{ ocid }}</p></div></div><div v-if="pending" class="text-sm opacity-60">Loading procurement lifecycle…</div><StEmptyState v-else-if="error" variant="unavailable" /><template v-else-if="data"><StCaveat :text="data.caveat" /><section v-for="stage in data.stages ?? []" :key="stage.stage" class="atlas-section atlas-panel atlas-panel-body space-y-4"><div class="atlas-section-head"><h2>{{ labels[stage.stage] ?? stage.stage }}</h2><p v-if="!stage.present">No notice was published for this stage — not evidence that the stage did not happen.</p><p v-else>{{ stage.notices.length }} notice{{ stage.notices.length === 1 ? '' : 's' }} in this stage.</p></div><StEvidenceTable v-if="stage.present" :columns="columns" :rows="rows(stage)" row-key="row_key" /></section></template></section>
</template>
