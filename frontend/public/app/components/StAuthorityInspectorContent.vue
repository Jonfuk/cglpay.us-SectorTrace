<script setup lang="ts">
import type { AuthorityResponse } from '~/types/api'
const props = defineProps<{ code: string }>()
const emit = defineEmits<{ identity: [name: string] }>()
const api = usePublicApi()
const saved = useSavedSearches()
const feedback = ref('')
const { data, pending, error, refresh } = useAsyncData(
  () => `authority-inspection-${props.code}`,
  (_app, { signal }) => api.authority(props.code, { signal }) as Promise<AuthorityResponse & { coverage?: { cells?: Record<string, number> } }>,
)
watch(() => data.value?.authority?.name, name => emit('identity', name ?? props.code))
function save() { feedback.value = saved.save(String(data.value?.authority?.name ?? props.code), `#/authorities/${encodeURIComponent(props.code)}`) ? 'Authority reference saved.' : 'Reference kept for this visit. Browser storage is unavailable.' }
</script>
<template><div><p class="atlas-footnote">ONS code {{ code }}</p><StEvidenceState :pending="pending" :error="error" :empty="!data?.authority" empty-title="Authority unavailable" @retry="refresh"><p>{{ data?.authority?.type ?? 'Authority type not supplied' }}<span v-if="data?.authority?.region"> · {{ data.authority.region }}</span></p><h3>Evidence availability</h3><dl class="st-holdings"><template v-for="(count, label) in data?.coverage?.cells ?? {}" :key="label"><dt>{{ label }}</dt><dd>{{ count.toLocaleString('en-GB') }}</dd></template></dl><p v-if="!data?.coverage?.cells">Holdings were not supplied in this response.</p><p class="atlas-footnote">These are separate collections, including candidates where labelled. Counts are not a measure of activity or performance.</p><div class="st-inspector-actions"><NuxtLink :to="{ path: '/coverage', query: { lens: 'history', ons_code: code } }" class="atlas-button">View evidence periods</NuxtLink><NuxtLink :to="`/authorities/${encodeURIComponent(code)}`" class="atlas-button primary">Open profile</NuxtLink><NuxtLink :to="{ path: '/compare', query: { ons_code: code } }" class="atlas-button">Compare</NuxtLink><button type="button" class="atlas-button" @click="save">Save authority</button></div><p role="status">{{ feedback }}</p></StEvidenceState></div></template>
