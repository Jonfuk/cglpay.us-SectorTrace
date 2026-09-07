<script setup lang="ts">
import type { ProcessPayload } from '~/types/contracts'
import { researchHref } from '~/lib/route-compatibility'
const route = useRoute()
const api = usePublicApi()
const filters = useFilterState()
const ocid = computed(() => String(route.params.ocid ?? ''))
const id = computed(() => String(filters.get('notice_id') ?? ''))
const timeline = computed(() => filters.get('view') === 'timeline')
const back = computed(() => researchHref(filters.get('from')))
const { data, pending, error, refresh } = await useAsyncData(() => `contract-process-${ocid.value}`, (_app, { signal }) => api.get<ProcessPayload>(`/contracts/process/${encodeURIComponent(ocid.value)}`, { signal }))
const labels: Record<string, string> = { planning: 'Planning', tender: 'Tender', award: 'Award', contract: 'Contract', amendment: 'Amendment', termination: 'Termination', implementation: 'Implementation', other: 'Other or untagged' }
const rows = computed(() => (data.value?.stages ?? []).flatMap(stage => stage.notices.map(row => ({ ...row, stage: stage.stage }))))
const dated = computed(() => rows.value.filter(row => row.date_published && Number.isFinite(Date.parse(row.date_published))).sort((a, b) => Date.parse(a.date_published!) - Date.parse(b.date_published!)))
const undated = computed(() => rows.value.filter(row => !row.date_published || !Number.isFinite(Date.parse(row.date_published))))
const selected = computed(() => rows.value.find(row => row.notice_id === id.value))
let trigger: HTMLElement | null = null
async function inspect(noticeId: string, event: Event) { trigger = event.currentTarget as HTMLElement; await filters.set('notice_id', noticeId); await nextTick(); document.querySelector<HTMLElement>('.st-inspector-heading')?.focus() }
async function close() { await filters.set('notice_id', undefined); await nextTick(); if (trigger?.isConnected) trigger.focus() }
useHead(() => ({ title: `Procurement process ${ocid.value} · SectorTrace` }))
</script>
<template>
  <section class="space-y-6"><StResearchLink v-if="back" :href="back" class="atlas-button">Return to source view</StResearchLink><NuxtLink v-else to="/contracts" class="atlas-button">All procurement notices</NuxtLink><header class="st-page-header"><p class="atlas-eyebrow">Procurement process</p><h1>Procurement lifecycle</h1><p class="font-mono break-all">{{ ocid }}</p><p>Read the stages named by published notices. A sequence of notices can include updates, cancellations and amendments to the same procurement.</p></header>
    <StEvidenceState :pending="pending" :error="error" @retry="refresh"><template v-if="data"><p class="atlas-footnote">Distinct notice identifiers: {{ data.notice_count ?? 'Not supplied' }}. Publication range: {{ data.date_range?.earliest ?? 'Not supplied' }} to {{ data.date_range?.latest ?? 'Not supplied' }}.</p><p v-if="data.buyer?.name">Buyer named in the first returned notice: <NuxtLink v-if="data.buyer.ons_code" :to="`/authorities/${encodeURIComponent(data.buyer.ons_code)}`">{{ data.buyer.name }}</NuxtLink><span v-else>{{ data.buyer.name }}</span></p><StCaveat :text="data.caveat" /><div class="flex flex-wrap gap-2" role="group" aria-label="Process view"><button type="button" class="atlas-button" :aria-pressed="!timeline" @click="filters.set('view', 'stages')">Stages</button><button v-if="dated.length" type="button" class="atlas-button" :aria-pressed="timeline" @click="filters.set('view', 'timeline')">Publication timeline</button><NuxtLink :to="{ path: '/diary', query: { ocid } }" class="atlas-button">Procurement dates</NuxtLink><NuxtLink :to="{ path: '/revisions', query: { kind: 'ocds', ocid } }" class="atlas-button">Process revisions</NuxtLink></div>
      <div class="st-directory-workspace" :class="{ 'has-inspector': id }"><div class="space-y-5 min-w-0"><template v-if="!timeline"><section v-for="stage in data.stages ?? []" :key="stage.stage" class="atlas-panel atlas-panel-body space-y-3"><h2>{{ labels[stage.stage] ?? stage.stage }}</h2><p v-if="!stage.notices.length">No notice is held for this stage. This does not establish whether the stage took place.</p><ul class="st-process-notices"><li v-for="row in stage.notices" :key="row.notice_id ?? ''"><h3>{{ row.title ?? 'Title not supplied' }}</h3><p>{{ row.date_published ?? 'Publication date not supplied' }} · {{ row.notice_type_raw ?? 'Notice type not supplied' }}</p><p>Published core value: {{ row.value_core ?? 'Not supplied' }} {{ row.currency ?? '(currency not supplied)' }}</p><button v-if="row.notice_id" class="atlas-button" type="button" :aria-label="`Inspect notice ${row.notice_id}`" @click="inspect(row.notice_id, $event)">Inspect notice</button></li></ul></section></template>
        <template v-else><p class="atlas-footnote">Ordered by publication date, with each source-defined stage retained. Undated records follow separately.</p><p v-if="!dated.length">No usable publication dates were returned.</p><ol class="st-process-timeline"><li v-for="row in dated" :key="row.notice_id ?? ''"><time>{{ row.date_published }}</time><p>{{ labels[row.stage] ?? row.stage }} · {{ row.notice_type_raw ?? 'Notice type not supplied' }}</p><h3>{{ row.title ?? 'Title not supplied' }}</h3><button v-if="row.notice_id" class="atlas-button" type="button" :aria-label="`Inspect notice ${row.notice_id}`" @click="inspect(row.notice_id, $event)">Inspect notice</button></li></ol><section v-if="undated.length"><h2>No usable publication date</h2><ul class="st-process-notices"><li v-for="row in undated" :key="row.notice_id ?? ''"><h3>{{ row.title ?? 'Title not supplied' }}</h3><p>{{ labels[row.stage] ?? row.stage }} · {{ row.date_published ?? 'Date not supplied' }}</p><button v-if="row.notice_id" class="atlas-button" type="button" :aria-label="`Inspect notice ${row.notice_id}`" @click="inspect(row.notice_id, $event)">Inspect notice</button></li></ul></section></template>
      </div><StInspector v-if="id" :title="selected?.title ?? 'Notice unavailable in this process'" @close="close"><StNoticeRecord v-if="selected" :row="selected" :process-id="ocid" process-response /><p v-else>Notice {{ id }} is not in this returned process. No substitute notice has been selected.</p></StInspector></div>
    </template></StEvidenceState>
  </section>
</template>
<style scoped>
.st-process-notices li { padding: 12px 0; border-bottom: 1px solid var(--border-subtle); }
.st-process-notices p, .st-process-timeline p, time { color: var(--text-muted); font-size: 13px; margin: 6px 0; }
.st-process-timeline { border-left: 2px solid var(--interactive-secondary); padding-left: 20px; }
.st-process-timeline li { margin-bottom: 28px; }
h3 { font-size: 15px; overflow-wrap: anywhere; }
</style>
