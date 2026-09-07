<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Provenance } from '~/types/api'
const props = defineProps<{ provenance: Provenance | null | undefined; scope?: 'row' | 'returned-series' | 'result-window' }>()
const copied = ref('')
const hash = computed(() => props.provenance?.payload_sha256 ?? props.provenance?.content_sha256)
const unavailable = 'Not supplied in this response'
const scopeLabel = computed(() => ({ row: 'This observation', 'returned-series': 'Returned series', 'result-window': 'Returned result window' })[props.scope ?? 'row'])
async function copyReference() {
  const p = props.provenance
  const lines = [scopeLabel.value, p?.source_url, p?.published_at ? `Published: ${p.published_at}` : null, p?.retrieved_at ? `Retrieved: ${p.retrieved_at}` : null, hash.value ? `SHA-256: ${hash.value}` : null].filter(Boolean)
  try { await navigator.clipboard.writeText(lines.join('\n')); copied.value = 'Reference copied.' }
  catch { copied.value = 'Copy is unavailable. Select the reference text below.' }
}
</script>
<template>
  <details class="st-provenance"><summary>Source details</summary><p class="atlas-footnote">{{ scopeLabel }}</p>
    <dl><dt>Source</dt><dd><StLink v-if="provenance?.source_url" :href="provenance.source_url">{{ provenance.source_url }}</StLink><span v-else>{{ unavailable }}</span></dd>
      <dt>Retrieved</dt><dd>{{ provenance?.retrieved_at ?? unavailable }}</dd>
      <dt>Published</dt><dd>{{ provenance?.published_at ?? unavailable }}</dd>
      <dt>SHA-256</dt><dd class="font-mono">{{ hash ?? unavailable }}</dd>
    </dl><button type="button" class="atlas-button" @click="copyReference">Copy reference</button><p role="status">{{ copied }}</p>
  </details>
</template>
