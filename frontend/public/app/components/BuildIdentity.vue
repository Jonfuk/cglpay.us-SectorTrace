<script setup vapor lang="ts">
// A Vapor-mode component (Phase 6: Vapor enabled from the first prototype).
// It is a simple, presentational, performance-insensitive leaf — exactly the
// class the plan nominates for Vapor: no VNodes, no public-instance proxy, no
// Options API, no Nuxt UI control inside it. If the pinned Vue 3.6 RC / Vapor
// combination fails its interop or measured-benefit gate, dropping the `vapor`
// attribute above turns this back into an ordinary VDOM component with no other
// change — the migration does not depend on Vapor.
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
