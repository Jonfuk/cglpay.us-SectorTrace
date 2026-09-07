<script setup lang="ts">
const open = defineModel<boolean>('open', { default: false })
</script>
<template>
  <USlideover v-model:open="open" title="Sections" description="Browse SectorTrace" side="left" :close="false"
    :ui="{ content: 'st-drawer', body: 'p-0', header: 'st-drawer-header' }">
    <template #actions><button type="button" class="atlas-button" @click="open = false">Close</button></template>
    <template #body><StNavigation @navigate="open = false" /></template>
  </USlideover>
</template>
