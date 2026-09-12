<script setup lang="ts">
// Keep this presentational leaf on the stable VDOM runtime until the pinned
// Vue 3.6 RC Vapor interop passes a deployed browser smoke test. The migration
// does not depend on Vapor, so the performance experiment can be re-enabled
// here independently without risking the application root.
defineProps<{
  revision: string | null
  migration: number | null
  lastFetch: string | null
}>()
</script>

<template>
  <dl class="grid grid-cols-3 gap-4 text-sm">
    <div>
      <dt class="opacity-60">Build</dt>
      <dd class="font-mono">{{ revision ? revision.slice(0, 12) : '—' }}</dd>
    </div>
    <div>
      <dt class="opacity-60">Schema</dt>
      <dd class="font-mono">{{ migration ?? '—' }}</dd>
    </div>
    <div>
      <dt class="opacity-60">Last fetch</dt>
      <dd class="font-mono">{{ lastFetch ?? '—' }}</dd>
    </div>
  </dl>
</template>
