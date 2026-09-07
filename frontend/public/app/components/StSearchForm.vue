<script setup lang="ts">
import { ref, watch } from 'vue'
const route = useRoute()
const router = useRouter()
const kinds = ['providers', 'authorities', 'documents'] as const
const kind = ref<string>(kinds.includes(route.query.type as typeof kinds[number]) ? String(route.query.type) : 'providers')
const query = ref(String(route.query.q ?? ''))
watch(() => route.query, () => { query.value = String(route.query.q ?? '') })
function submit() { return router.push({ path: `/${kind.value}`, query: query.value.trim() ? { q: query.value.trim() } : {} }) }
</script>
<template>
  <form class="st-search-form" role="search" aria-label="Find evidence" @submit.prevent="submit">
    <label>Search for<select v-model="kind"><option value="providers">Providers</option><option value="authorities">Authorities</option><option value="documents">Documents</option></select></label>
    <label class="st-query">{{ kind === 'documents' ? 'Words in committee or CDP documents' : 'Name or identifier' }}<input v-model="query" type="search" :placeholder="kind === 'documents' ? 'Enter search words' : 'Enter a name or identifier'"></label>
    <button type="submit" class="atlas-button primary">Search</button>
  </form>
</template>
