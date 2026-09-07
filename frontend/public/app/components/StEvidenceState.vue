<script setup lang="ts">
defineProps<{ pending?: boolean; error?: unknown; empty?: boolean; emptyTitle?: string; message?: string }>()
defineEmits<{ retry: [] }>()
</script>
<template>
  <section v-if="pending" class="st-evidence-state" aria-busy="true" role="status"><p>Loading evidence…</p><div class="st-skeleton" aria-hidden="true" /></section>
  <section v-else-if="error" class="st-evidence-state" role="status"><h2>Evidence is unavailable</h2><p>This request could not be completed.</p><button type="button" class="atlas-button" @click="$emit('retry')">Retry</button></section>
  <section v-else-if="empty" class="st-evidence-state"><h2>{{ emptyTitle ?? 'No matching evidence found' }}</h2><p>{{ message ?? 'Try another selection or clear the active filters.' }}</p></section>
  <slot v-else />
</template>
