<script setup lang="ts">
import { computed } from 'vue'
import type { Column } from '~/components/StEvidenceTable.vue'
import type { PfdReport, PfdResponse } from '~/types/api'

interface CountRow { year?: number; library_year?: number; reports?: number; documents?: number; with_concerns?: number; with_text?: number; coroner_area?: string; sab_name?: string; term: string; occurrences: number | string; [key: string]: unknown }
interface SarReport { document_url: string | null; document_ext: string | null; library_year: number | null; sab_name: string | null; has_body_text: number; source_url: string | null; retrieved_at: string | null; [key: string]: unknown }
interface PfdFullResponse extends PfdResponse {
  totals: { reports: number; with_concerns: number; stubs: number }
  by_year: CountRow[]
  by_coroner_area: CountRow[]
  concern_terms: CountRow[]
  mentions: { sent_to_providers: number; naming_providers: number; recipient_organisations: number }
  recent: PfdReport[]
  caveats: Record<string, string | null>
  sar: { totals: { documents: number; with_text: number; with_board_name: number }; by_year: CountRow[]; by_board: CountRow[]; concern_terms: CountRow[]; mentions: { naming_providers: number }; recent: SarReport[]; caveats: Record<string, string | null> }
}
interface SafetyEvent { date: string | null; source: string; relationship: string; entity_name: string | null; title: string | null; result: string | null; source_url: string | null; [key: string]: unknown }
interface SafetyLegal { events: SafetyEvent[]; counts: { by_source: Record<string, number>; by_relationship: Record<string, number> }; sources: string[]; labels: Record<string, string>; caveats: Record<string, string>; note: string; truncated: boolean }
interface SafetyResponse { notices: Array<Record<string, unknown>>; total: number; caveat: string | null }
interface PfdWorkspace { pfd: PfdFullResponse; safetyLegal: SafetyLegal; safety: SafetyResponse }

const api = usePublicApi()
const filters = useFilterState()
const source = computed(() => String(filters.get('source') || ''))
const relationship = computed(() => String(filters.get('relationship') || ''))
const sourceLabels: Record<string, string> = { pfd: 'Coroners’ reports', sar: 'Safeguarding reviews', hse: 'HSE notices', tribunal: 'Tribunal cases', cqc: 'CQC inspections' }
const relationshipLabels: Record<string, string> = { addressed_to: 'Addressed to', named_in: 'Named in', matched_to: 'Matched to', regulated_by: 'Regulated by' }

const { data, pending, error } = await useDataRoute<PfdWorkspace>('public-pfd-workspace', (f) => Promise.all([
  api.get<PfdFullResponse>('/pfd'),
  api.get<SafetyLegal>('/safety_legal', { query: { source: f.source, relationship: f.relationship } }),
  api.get<SafetyResponse>('/safety'),
]).then(([pfd, safetyLegal, safety]) => ({ pfd, safetyLegal, safety })))

const pfd = computed(() => data.value?.pfd)
const chronology = computed(() => data.value?.safetyLegal.events ?? [])
const safetyCounts = computed(() => data.value?.safetyLegal.counts)
const recent = computed(() => pfd.value?.recent ?? [])
const sarRecent = computed(() => pfd.value?.sar.recent ?? [])
const pfdColumns: Column<PfdReport>[] = [
  { key: 'report_ref', label: 'Reference', mono: true }, { key: 'report_date', label: 'Date', mono: true },
  { key: 'coroner_area', label: 'Coroner area' }, { key: 'categories', label: 'Categories' },
  { key: 'has_concerns', label: 'Concerns' }, { key: 'report_url', label: 'Report', link: true },
]
const chronologyColumns: Column<SafetyEvent>[] = [
  { key: 'date', label: 'Date', mono: true }, { key: 'source', label: 'Source' }, { key: 'relationship', label: 'Relationship' },
  { key: 'entity_name', label: 'Organisation' }, { key: 'title', label: 'Record' }, { key: 'result', label: 'Published result' }, { key: 'source_url', label: 'Source', link: true },
]
const sarColumns: Column<SarReport>[] = [
  { key: 'library_year', label: 'Library year', numeric: true }, { key: 'sab_name', label: 'Board' },
  { key: 'has_body_text', label: 'Text extracted' }, { key: 'document_url', label: 'Review', link: true },
]
const hseColumns: Column<Record<string, unknown>>[] = [
  { key: 'provider_name', label: 'Provider' }, { key: 'notice_type', label: 'Type' }, { key: 'issue_date', label: 'Issued', mono: true },
  { key: 'result', label: 'Result' }, { key: 'legislation', label: 'Legislation' }, { key: 'notice_number', label: 'Number', mono: true },
]

function setSafetyFilter(key: string, value: string): void { void filters.set(key, value || undefined) }
function sourceCount(key: string): number { return safetyCounts.value?.by_source[key] ?? 0 }
function relationshipCount(key: string): number { return safetyCounts.value?.by_relationship[key] ?? 0 }
function countValue(row: CountRow): string { return String(row.reports ?? row.documents ?? row.occurrences ?? 0) }
function sortDesc(rows: CountRow[], key: 'reports' | 'documents' | 'occurrences'): CountRow[] { return [...rows].sort((a, b) => Number(b[key] ?? 0) - Number(a[key] ?? 0)).slice(0, 20) }

useHead({ title: 'SectorTrace — Safety & legal evidence' })
</script>

<template>
  <section class="space-y-8">
    <div class="atlas-hero">
      <div>
        <p class="atlas-kicker">Safety · legal evidence</p>
        <h1>Safety &amp; legal evidence</h1>
        <p class="atlas-lede">{{ pfd?.totals.reports.toLocaleString('en-GB') ?? '—' }} reports from coroners and {{ pfd?.sar.totals.documents.toLocaleString('en-GB') ?? '—' }} Safeguarding Adult Reviews. Each is the author’s own words about how harm could have been avoided — read the document, not just the numbers here.</p>
        <div class="atlas-actions"><a class="atlas-button primary" href="#safety-chronology">Explore the chronology</a><a class="atlas-button" href="#coroners-reports">Read the reports</a></div>
      </div>
      <div class="atlas-hero-aside"><div class="atlas-region"><strong>{{ pfd?.totals.with_concerns.toLocaleString('en-GB') ?? '—' }}</strong><span>coroner reports carrying matters of concern</span></div><div class="atlas-region"><strong>{{ pfd?.totals.stubs.toLocaleString('en-GB') ?? '—' }}</strong><span>metadata stubs; not evidence of no concern</span></div></div>
    </div>

    <details class="atlas-read-first" open><summary>Read reports responsibly</summary><p>A provider mention is not a finding of fault, causation, prevalence, or responsibility. “Sent to” and “named in” are different facts.</p><p>Some publications are metadata stubs, so an absent concern is a source limitation rather than evidence of absence.</p><p>Safeguarding Adult Reviews are a separate evidence stream and are never combined with coroners’ reports.</p></details>

    <div v-if="pending" class="text-sm opacity-60">Loading safety and legal evidence…</div>
    <StEmptyState v-else-if="error" variant="unavailable" />
    <template v-else>
      <section id="safety-chronology" class="atlas-section">
        <div class="atlas-section-head"><h2>Safety &amp; legal chronology</h2><p>Distinct evidence streams on one timeline. Counts remain separated by source and relationship and are never added together.</p></div>
        <div class="atlas-panel atlas-panel-body space-y-4">
          <p class="text-sm opacity-70">{{ data?.safetyLegal.note }}</p>
          <div><p class="text-sm font-semibold mb-2">Filter by source</p><div class="flex flex-wrap gap-2"><button class="atlas-button" :class="!source ? 'primary' : ''" type="button" @click="setSafetyFilter('source', '')">All sources · {{ Object.values(safetyCounts?.by_source ?? {}).reduce((a, b) => a + b, 0) }}</button><button v-for="key in data?.safetyLegal.sources ?? []" :key="key" class="atlas-button" :class="source === key ? 'primary' : ''" type="button" @click="setSafetyFilter('source', key)">{{ sourceLabels[key] ?? key }} · {{ sourceCount(key) }}</button></div></div>
          <div><p class="text-sm font-semibold mb-2">Filter by relationship</p><div class="flex flex-wrap gap-2"><button class="atlas-button" :class="!relationship ? 'primary' : ''" type="button" @click="setSafetyFilter('relationship', '')">Any relationship · {{ Object.values(safetyCounts?.by_relationship ?? {}).reduce((a, b) => a + b, 0) }}</button><button v-for="(label, key) in relationshipLabels" :key="key" class="atlas-button" :class="relationship === key ? 'primary' : ''" type="button" @click="setSafetyFilter('relationship', key)">{{ label }} · {{ relationshipCount(key) }}</button></div></div>
          <StEvidenceTable v-if="chronology.length" :columns="chronologyColumns" :rows="chronology" row-key="source_url" />
          <StEmptyState v-else />
          <StCaveat v-for="(text, key) in data?.safetyLegal.caveats ?? {}" :key="key" :text="text" />
        </div>
      </section>

      <section id="coroners-reports" class="atlas-section">
        <div class="atlas-section-head"><h2>Coroners’ reports in detail</h2><p>{{ pfd?.totals.with_concerns.toLocaleString('en-GB') }} of {{ pfd?.totals.reports.toLocaleString('en-GB') }} carry matters of concern in the published data. The {{ pfd?.totals.stubs.toLocaleString('en-GB') }} remaining rows are metadata stubs.</p></div>
        <div class="atlas-panel atlas-panel-body space-y-5">
          <div class="atlas-grid"><div class="atlas-stat"><div class="atlas-stat-value">{{ pfd?.totals.reports.toLocaleString('en-GB') }}</div><div class="atlas-stat-label">Reports</div></div><div class="atlas-stat"><div class="atlas-stat-value">{{ pfd?.mentions.sent_to_providers }}</div><div class="atlas-stat-label">Sent to tracked providers</div></div><div class="atlas-stat"><div class="atlas-stat-value">{{ pfd?.mentions.naming_providers }}</div><div class="atlas-stat-label">Naming tracked providers</div></div><div class="atlas-stat"><div class="atlas-stat-value">{{ pfd?.mentions.recipient_organisations.toLocaleString('en-GB') }}</div><div class="atlas-stat-label">Recipient organisations</div></div></div>
          <StCaveat v-if="pfd?.caveats.mentions" :text="pfd.caveats.mentions" />
          <h3>Latest reports</h3><StEvidenceTable :columns="pfdColumns" :rows="recent" row-key="report_ref" />
          <h3>Reports by year</h3><StEvidenceTable :columns="[{ key: 'year', label: 'Year', numeric: true }, { key: 'reports', label: 'Reports', numeric: true }, { key: 'with_concerns', label: 'With concerns', numeric: true }]" :rows="pfd?.by_year ?? []" row-key="year" />
          <h3>Leading coroner areas</h3><StEvidenceTable :columns="[{ key: 'coroner_area', label: 'Coroner area' }, { key: 'reports', label: 'Reports', numeric: true }]" :rows="sortDesc(pfd?.by_coroner_area ?? [], 'reports')" row-key="coroner_area" />
          <h3>Concern themes</h3><p class="text-sm opacity-70">A term means the word appears in published concerns. It is a finding aid, not a characterisation of what any report found.</p><StEvidenceTable :columns="[{ key: 'term', label: 'Term' }, { key: 'occurrences', label: 'Occurrences', numeric: true }]" :rows="pfd?.concern_terms ?? []" row-key="term" />
        </div>
      </section>

      <section class="atlas-section"><div class="atlas-section-head"><h2>Safeguarding Adult Reviews</h2><p>A separate evidence stream from the National SAR Library. Coverage is whatever boards submitted, and the library year is not a publication date.</p></div><div class="atlas-panel atlas-panel-body space-y-5"><div class="atlas-grid"><div class="atlas-stat"><div class="atlas-stat-value">{{ pfd?.sar.totals.documents.toLocaleString('en-GB') }}</div><div class="atlas-stat-label">Reviews</div></div><div class="atlas-stat"><div class="atlas-stat-value">{{ pfd?.sar.totals.with_text.toLocaleString('en-GB') }}</div><div class="atlas-stat-label">With extracted text</div></div><div class="atlas-stat"><div class="atlas-stat-value">{{ pfd?.sar.totals.with_board_name.toLocaleString('en-GB') }}</div><div class="atlas-stat-label">With board named</div></div><div class="atlas-stat"><div class="atlas-stat-value">{{ pfd?.sar.mentions.naming_providers }}</div><div class="atlas-stat-label">Naming tracked providers</div></div></div><StCaveat v-if="pfd?.sar.caveats.scope" :text="pfd.sar.caveats.scope" /><h3>Latest reviews</h3><StEvidenceTable :columns="sarColumns" :rows="sarRecent" row-key="document_url" /><h3>Reviews by library year</h3><StEvidenceTable :columns="[{ key: 'library_year', label: 'Library year', numeric: true }, { key: 'documents', label: 'Reviews', numeric: true }, { key: 'with_text', label: 'With text', numeric: true }]" :rows="pfd?.sar.by_year ?? []" row-key="library_year" /><h3>Boards represented</h3><StEvidenceTable :columns="[{ key: 'sab_name', label: 'Board' }, { key: 'documents', label: 'Reviews', numeric: true }]" :rows="sortDesc(pfd?.sar.by_board ?? [], 'documents')" row-key="sab_name" /><StCaveat v-if="pfd?.sar.caveats.mentions" :text="pfd.sar.caveats.mentions" /></div></section>

      <section class="atlas-section"><div class="atlas-section-head"><h2>HSE enforcement notices</h2><p>A third, separate evidence stream: notices served by HSE on an organisation whose name exactly matches a tracked provider.</p></div><div class="atlas-panel atlas-panel-body space-y-4"><p class="text-3xl font-semibold">{{ data?.safety.total.toLocaleString('en-GB') }}</p><StEvidenceTable v-if="data?.safety.notices.length" :columns="hseColumns" :rows="data.safety.notices" /> <StEmptyState v-else /></div></section>
    </template>
  </section>
</template>
