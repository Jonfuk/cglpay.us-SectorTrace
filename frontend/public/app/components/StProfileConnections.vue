<script setup lang="ts">
import type { RelationshipsResponse, Provenance } from '~/types/api'
const props = defineProps<{ providerKey?: string; authorityCode?: string }>()
const api = usePublicApi()
const { data, pending, error, refresh } = await useAsyncData(
  () => `profile-connections-${props.providerKey ?? ''}-${props.authorityCode ?? ''}`,
  (_app, { signal }) => api.relationships({ query: { provider_key: props.providerKey, ons_code: props.authorityCode }, signal }) as Promise<RelationshipsResponse & { caveat?: string }>,
)
const names = computed(() => new Map([data.value?.center, ...(data.value?.neighbours ?? [])].filter(Boolean).map(node => [String(node?.entity_id), String(node?.canonical_name ?? node?.entity_id)])))
</script>
<template>
  <section class="atlas-section">
    <h2>Commissioning connections</h2><p>Each record describes an awarded-to relationship supported by procurement evidence. Its validity dates do not establish current service delivery.</p>
    <NuxtLink :to="{ path: '/relationships', query: { provider_key: providerKey, ons_code: authorityCode } }" class="atlas-button">Explore commissioning connections</NuxtLink>
    <StEvidenceState :pending="pending" :error="error" :empty="!data?.edges.length" empty-title="No commissioning connections held" message="No relationship records were returned for this entity. This does not establish an absence of commissioning activity." @retry="refresh">
      <StCaveat :text="data?.caveat" />
      <details v-for="(edge, index) in data?.edges ?? []" :key="edge.relationship_id ?? index" class="st-connection-record">
        <summary>{{ names.get(String(edge.subject_entity_id)) ?? edge.subject_entity_id ?? 'Subject unavailable' }} awarded to {{ names.get(String(edge.object_entity_id)) ?? edge.object_entity_id ?? 'Object unavailable' }}</summary>
        <dl><dt>Relationship</dt><dd>AWARDED_TO</dd><dt>Valid from</dt><dd>{{ edge.valid_from ?? 'Not supplied' }}</dd><dt>Valid to</dt><dd>{{ edge.valid_to ?? 'Not supplied' }}</dd><dt>Recorded confidence</dt><dd>{{ edge.confidence ?? 'Not supplied' }}</dd><dt>Relationship identifier</dt><dd>{{ edge.relationship_id ?? 'Not supplied' }}</dd></dl>
        <StProvenance :provenance="edge as Provenance" />
      </details>
    </StEvidenceState>
  </section>
</template>
