<script setup lang="ts">
import { computed } from 'vue'
const route = useRoute()
const filters = useFilterState()
const id = computed(() => String(route.params.id ?? ''))
const element = computed(() => typeof filters.get('element_id') === 'string' ? String(filters.get('element_id')) : undefined)
const returnQuery = computed(() => Object.fromEntries(['q', 'source_system', 'document_type', 'year_from', 'year_to', 'since_retrieved_at', 'offset'].map(key => [key, filters.get(key)]).filter(([, value]) => value != null)))
useHead(() => ({ title: `Document ${id.value} · SectorTrace` }))
</script>
<template><section class="space-y-6"><NuxtLink :to="{ path: '/documents', query: returnQuery }">Back to document search</NuxtLink><StPassageReader :document-id="id" :element-id="element" @select="value => filters.set('element_id', value)" /></section></template>
