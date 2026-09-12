<script setup lang="ts">
import type { DocumentSearchHit, DocumentSearchPayload } from '~/types/documents'
defineProps<{ query: string; data?: DocumentSearchPayload | null; pending: boolean; error?: unknown; offset: number; selected?: string }>()
defineEmits<{ retry: []; read: [row: DocumentSearchHit]; page: [offset: number] }>()
</script>
<template>
  <div>
    <p v-if="!query.trim()">Enter a search term to find matching passages.</p>
    <StEvidenceState v-else :pending="pending" :error="error" :empty="!data?.results?.length" @retry="$emit('retry')">
      <StCaveat :text="data?.caveat" />
      <p role="status" class="atlas-footnote">Showing {{ offset + 1 }} to {{ offset + (data?.results.length ?? 0) }} of {{ data?.total }} matching passages.</p>
      <StDocumentResults :rows="data?.results ?? []" :selected="selected" @read="row => $emit('read', row)" />
    </StEvidenceState>
    <div v-if="query.trim() && !pending && !error && (data?.total ?? 0) > 0" class="atlas-actions">
      <button type="button" class="atlas-button" :disabled="offset <= 0" @click="$emit('page', Math.max(0, offset - 50))">Previous results</button>
      <button type="button" class="atlas-button" :disabled="offset + (data?.results.length ?? 0) >= (data?.total ?? 0)" @click="$emit('page', offset + 50)">Next results</button>
    </div>
  </div>
</template>
