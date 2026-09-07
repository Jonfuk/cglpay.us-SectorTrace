<script setup lang="ts">
defineProps<{ label: string; kind: string; identifier: string }>()
const emit = defineEmits<{ kind: [value: string]; identifier: [value: string] }>()
</script>
<template>
  <fieldset class="space-y-3"><legend class="font-semibold">{{ label }}</legend>
    <label>Entity type<select :value="kind" @change="emit('kind', ($event.target as HTMLSelectElement).value)"><option v-if="!['provider', 'authority', 'supplier'].includes(kind)" :value="kind">Unsupported type: {{ kind }}</option><option value="provider">Provider</option><option value="authority">Authority</option><option value="supplier">Supplier</option></select></label>
    <StEntityPicker v-if="kind === 'provider' || kind === 'authority'" :kind="kind" :label="`${label} ${kind}`" :model-value="identifier" @update:model-value="emit('identifier', $event)" />
    <label>{{ label }} identifier<input :value="identifier" autocomplete="off" @input="emit('identifier', ($event.target as HTMLInputElement).value)"></label>
    <p class="atlas-footnote">{{ kind === 'supplier' ? 'Enter an exact supplier key from a public evidence record. A supplier directory is not available here.' : 'Choose from the directory or enter an exact public identifier from an evidence record.' }}</p>
  </fieldset>
</template>
<style scoped>label { display: grid; gap: 6px; } input, select { min-height: 44px; width: 100%; padding: 8px; background: var(--surface-panel); color: var(--text-primary); border: 1px solid var(--border-control); border-radius: 4px; }</style>
