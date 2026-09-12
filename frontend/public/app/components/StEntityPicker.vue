<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ kind: 'provider' | 'authority'; modelValue?: string; label?: string; emptyLabel?: string }>()
const emit = defineEmits<{ 'update:modelValue': [id: string] }>()
const api = usePublicApi()
const { data, pending, error, refresh } = useAsyncData(() => `entity-picker-${props.kind}`, async () => {
  if (props.kind === 'provider') return (await api.providers()).providers.flatMap(row => row.provider_key && row.canonical_name ? [{ id: row.provider_key, name: row.canonical_name }] : [])
  const response = await api.get<{ authorities: Array<{ ons_code: string; name: string }> }>('/authorities')
  return response.authorities.map(row => ({ id: row.ons_code, name: row.name }))
})
const unknown = computed(() => props.modelValue && data.value && !data.value.some(row => row.id === props.modelValue))
</script>
<template><div class="st-entity-picker"><label>{{ label ?? (kind === 'provider' ? 'Provider' : 'Authority') }}<select :value="modelValue ?? ''" :disabled="pending" @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)"><option value="">{{ pending ? 'Loading directory…' : emptyLabel ?? 'Choose an entity' }}</option><option v-if="unknown" :value="modelValue">Unavailable identifier: {{ modelValue }}</option><option v-for="row in data ?? []" :key="row.id" :value="row.id">{{ row.name }} ({{ row.id }})</option></select></label><p v-if="error" role="status">Directory unavailable. <button type="button" class="atlas-button" @click="refresh()">Retry</button></p></div></template>
