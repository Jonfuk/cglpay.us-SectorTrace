<script setup lang="ts">
useHead({ title: 'Verification tools · SectorTrace' })
const tools = [
  ['/discrepancies', 'Compare source observations', 'Inspect differing observations without choosing a winner automatically.'],
  ['/revisions', 'Inspect revisions', 'Read changes between exact procurement or document versions.'],
  ['/doctables', 'Read extracted tables', 'Inspect cells with their document context and extraction status.'],
  ['/links', 'Check a source reference', 'Read the recorded link and archive status for an exact source URL.'],
  ['/diary', 'Procurement dates', 'Follow published dates for notices and procurement processes.'],
] as const
</script>
<template><section><header class="st-page-header"><p class="atlas-eyebrow">Research</p><h1>Verification tools</h1><p>Check an observation, its source or its recorded history.</p></header><div class="st-tool-list"><NuxtLink v-for="[to, title, description] in tools" :key="to" :to="to" class="atlas-explore-card"><strong>{{ title }}</strong><span>{{ description }}</span></NuxtLink></div></section></template>
