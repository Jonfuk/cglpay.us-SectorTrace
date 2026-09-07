<script setup lang="ts">
defineProps<{ title: string }>()
const open = defineModel<boolean>('open', { default: true })
</script>
<template>
  <USlideover v-model:open="open" :title="title" description="Selected evidence" :close="false" :ui="{ content: 'st-inspector-sheet', body: 'st-inspector-body' }">
    <template #actions><button type="button" class="atlas-button" @click="open = false">Close</button></template>
    <template #body><slot /></template>
  </USlideover>
</template>
