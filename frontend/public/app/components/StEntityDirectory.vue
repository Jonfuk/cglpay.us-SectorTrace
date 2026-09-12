<script setup lang="ts">
import { computed, nextTick } from 'vue'
import type { ProviderRow } from '~/types/api'
interface Authority { ons_code: string; name: string; type?: string | null; region?: string | null }
interface Entry { id: string; name: string; description: string; provider?: ProviderRow }
const props = defineProps<{ kind: 'providers' | 'authorities' }>()
const api = usePublicApi()
const filters = useFilterState()
const { data, pending, error, refresh } = await useAsyncData(`public-directory-${props.kind}`, async () => {
  if (props.kind === 'providers') {
    const response = await api.providers()
    return response.providers.map(row => ({ id: row.provider_key, name: row.canonical_name, description: typeof row.status === 'string' ? row.status : 'Tracked identity', provider: row })) as Entry[]
  }
  const response = await api.get<{ authorities: Authority[] }>('/authorities')
  return response.authorities.map(row => ({ id: row.ons_code, name: row.name, description: [row.type, row.region].filter(Boolean).join(' · ') })) as Entry[]
})
const search = computed({ get: () => String(filters.get('q') ?? ''), set: value => { void filters.set('q', value || undefined) } })
const rows = computed(() => {
  const q = search.value.trim().toLocaleLowerCase('en-GB')
  return (data.value ?? []).filter(row => [row.id, row.name].some(value => value?.toLocaleLowerCase('en-GB').includes(q)))
    .sort((a, b) => a.name.localeCompare(b.name, 'en-GB'))
})
const inspectId = computed(() => String(filters.get('inspect') ?? ''))
const selected = computed(() => data.value?.find(row => row.id === inspectId.value))
let trigger: HTMLElement | null = null
async function inspect(id: string, event: Event) {
  trigger = event.currentTarget as HTMLElement
  await filters.set('inspect', id)
  await nextTick()
  document.querySelector<HTMLElement>('.st-inspector-heading')?.focus()
}
async function close() { await filters.set('inspect', undefined); await nextTick(); trigger?.focus() }
const holdingFields = [['contract_count', 'Procurement notices'], ['cqc_locations', 'CQC registrations'], ['tribunal_count', 'Tribunal cases'], ['nhs_job_advert_count', 'NHS Jobs adverts']] as const
function count(row: ProviderRow | undefined, key: string) { const value = row?.[key]; return typeof value === 'number' ? value.toLocaleString('en-GB') : 'Not supplied' }
</script>
<template>
  <section>
    <header class="st-page-header"><p class="atlas-eyebrow">Explore</p><h1>{{ kind === 'providers' ? 'Providers' : 'Authorities' }}</h1><p>{{ kind === 'providers' ? 'Find a tracked organisation and inspect the evidence held for its identity.' : 'Find a local authority by name or ONS code. Historical identities remain separate.' }}</p></header>
    <label class="st-directory-search">Search by name or identifier<input v-model="search" type="search" placeholder="Enter a name or identifier"></label>
    <StEvidenceState :pending="pending" :error="error" :empty="!rows.length" @retry="refresh">
      <p class="atlas-footnote" role="status">{{ rows.length.toLocaleString('en-GB') }} matching {{ kind }} of {{ data?.length.toLocaleString('en-GB') }} held in the directory</p>
      <div class="st-directory-workspace" :class="{ 'has-inspector': inspectId }">
        <ul class="st-directory-list"><li v-for="row in rows" :key="row.id" :class="{ selected: row.id === inspectId }"><div><NuxtLink :to="`/${kind}/${encodeURIComponent(row.id)}`">{{ row.name }}</NuxtLink><p>{{ row.description }}<span v-if="row.description"> · </span>{{ row.id }}</p></div><button type="button" class="atlas-button" :aria-label="`Inspect ${row.name}`" @click="inspect(row.id, $event)">Inspect</button></li></ul>
        <StInspector v-if="inspectId" :title="selected?.name ?? 'Entity unavailable'" @close="close">
          <template v-if="selected"><p class="atlas-footnote">{{ selected.description }} · {{ selected.id }}</p><dl v-if="selected.provider" class="st-holdings"><template v-for="[key, label] in holdingFields" :key="key"><dt>{{ label }}</dt><dd>{{ count(selected.provider, key) }}</dd></template></dl><p class="atlas-footnote">Holdings describe records in this directory. They do not measure organisation size or performance.</p><div class="st-inspector-actions"><NuxtLink :to="`/${kind}/${encodeURIComponent(selected.id)}`" class="atlas-button primary">Open profile</NuxtLink><NuxtLink :to="{ path: '/compare', query: { [kind === 'providers' ? 'provider_key' : 'ons_code']: selected.id } }" class="atlas-button">Compare</NuxtLink><NuxtLink :to="{ path: '/documents', query: { q: selected.name } }" class="atlas-button">Search documents for this name</NuxtLink></div><p class="atlas-footnote">A document name search does not establish a relationship to this entity.</p></template>
          <p v-else>The selected identifier is not in the current directory response.</p>
        </StInspector>
      </div>
    </StEvidenceState>
  </section>
</template>
