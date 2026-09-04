<script setup lang="ts">
import { computed, ref } from 'vue'

interface LinkOverview { states: string[]; by_state: Record<string, number>; note: string | null }
interface LinkArchive { held?: boolean; bytes?: number; verified?: boolean | null; sha256?: string | null; note?: string }
interface LinkDetail { url: string; state: string; state_label: string; last_checked: string | null; last_http_status: number | null; observed_in: string | null; archive?: LinkArchive; note: string | null; caveat: string | null }
const api = usePublicApi()
const filters = useFilterState()
const url = computed(() => String(filters.get('url') ?? ''))
const draft = ref(url.value)
const { data: overview } = await useAsyncData<LinkOverview | null>('public-source-link-overview', () => api.get<LinkOverview>('/source_link'), { default: () => null })
const { data, pending, error } = await useAsyncData<LinkDetail | null>(() => `public-source-link-${url.value}`, () => url.value ? api.get<LinkDetail>('/source_link', { query: { url: url.value } }) : Promise.resolve(null), { default: () => null, watch: [url] })
function check(): void { void filters.set('url', draft.value.trim() || undefined) }
function clear(): void { draft.value = ''; void filters.set('url', undefined) }
function label(state: string): string { return state.replaceAll('_', ' ') }
useHead({ title: 'SectorTrace — Source-link resilience' })
</script>

<template>
  <section class="space-y-8">
    <div class="atlas-hero"><div><p class="atlas-kicker">Source-link resilience · collection-time metadata</p><h1>Source-link resilience</h1><p class="atlas-lede">See whether a cited source was reachable at the last collection and whether a checksum-verified archive copy is held. This page makes no live request.</p></div><div class="atlas-hero-aside"><div class="atlas-region"><strong>{{ overview ? Object.values(overview.by_state).reduce((a, b) => a + b, 0).toLocaleString('en-GB') : '—' }}</strong><span>cited rows checked</span></div></div></div>
    <section class="atlas-section atlas-panel atlas-panel-body space-y-4"><div class="atlas-section-head"><h2>Check a cited URL</h2><p>The URL is a shareable query. Results describe the last recorded fetch, not the current publisher page.</p></div><form class="flex flex-wrap gap-2" @submit.prevent="check"><input v-model="draft" type="url" class="min-w-0 flex-1 rounded border px-3 py-2" placeholder="https://…" aria-label="Source URL"><button class="atlas-button primary" type="submit">Check URL</button><button v-if="url" class="atlas-button" type="button" @click="clear">Clear</button></form></section>
    <div v-if="pending" class="text-sm opacity-60">Loading recorded link state…</div><StEmptyState v-else-if="error" variant="unavailable" />
    <section v-else-if="data" class="atlas-section atlas-panel atlas-panel-body space-y-4"><div class="atlas-section-head"><h2>This URL</h2><p><StLink :href="data.url" /></p></div><div class="atlas-grid atlas-grid-4"><div class="atlas-stat"><strong>{{ label(data.state) }}</strong><span>{{ data.state_label }}</span></div><div class="atlas-stat"><strong>{{ data.last_http_status ?? '—' }}</strong><span>last HTTP status</span></div><div class="atlas-stat"><strong>{{ data.last_checked ?? '—' }}</strong><span>last checked</span></div><div class="atlas-stat"><strong>{{ data.archive?.held ? 'Held' : 'Not held' }}</strong><span>archive copy</span></div></div><p v-if="data.observed_in" class="text-sm opacity-70">Observed in {{ data.observed_in }}.</p><p v-if="data.archive?.held" class="text-sm">Archive: {{ data.archive.bytes?.toLocaleString('en-GB') ?? '—' }} bytes · {{ data.archive.verified === true ? 'checksum verified' : data.archive.verified === false ? 'checksum mismatch' : 'not re-hashed on request' }}<span v-if="data.archive.sha256" class="font-mono"> · {{ data.archive.sha256.slice(0, 16) }}…</span></p><p v-else class="text-sm opacity-70">{{ data.archive?.note ?? 'No archive copy is held for this URL.' }}</p><StCaveat :text="data.caveat ?? data.note" /></section>
    <section v-if="overview" class="atlas-section atlas-panel atlas-panel-body space-y-4"><div class="atlas-section-head"><h2>Across the warehouse</h2><p>{{ overview.note }}</p></div><div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><div v-for="state in overview.states" :key="state" class="atlas-stat"><strong>{{ overview.by_state[state] ?? 0 }}</strong><span>{{ label(state) }}</span></div></div></section>
  </section>
</template>
