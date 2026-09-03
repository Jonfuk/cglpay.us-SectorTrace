<script setup lang="ts">
import type { Provenance } from '~/types/api'

// Provenance-or-NULL is the project's core rule: every figure carries its
// source URL, fetch time, and the SHA-256 of the exact bytes. This component
// renders that trio compactly. A missing field shows an em dash — it is never
// filled with a guess, and its absence never implies the figure is unsourced
// by choice.
const props = defineProps<{ provenance: Provenance | null | undefined }>()

function shortHash(h: string | null | undefined): string {
  return h ? `${h.slice(0, 12)}…` : '—'
}
</script>

<template>
  <dl v-if="provenance" class="text-xs grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
    <dt class="opacity-60">Source</dt>
    <dd class="min-w-0">
      <StLink :href="provenance.source_url">{{ provenance.source_url ?? '—' }}</StLink>
    </dd>
    <dt class="opacity-60">Retrieved</dt>
    <dd class="font-mono">{{ provenance.retrieved_at ?? '—' }}</dd>
    <dt class="opacity-60">Hash</dt>
    <dd class="font-mono">{{ shortHash(provenance.content_sha256) }}</dd>
  </dl>
</template>
