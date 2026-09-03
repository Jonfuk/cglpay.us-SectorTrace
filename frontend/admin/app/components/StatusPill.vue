<script setup lang="ts">
import { computed } from 'vue'

// A small operator status badge. Tone is derived from a coarse level so the
// operator scans state at a glance; the exact label is passed through verbatim.
const props = withDefaults(
  defineProps<{
    label: string | number | null | undefined
    level?: 'ok' | 'warn' | 'bad' | 'neutral'
  }>(),
  { level: 'neutral' },
)

const classes = computed(() => {
  switch (props.level) {
    case 'ok':
      return 'bg-green-500/15 text-green-700 dark:text-green-400'
    case 'warn':
      return 'bg-amber-500/15 text-amber-700 dark:text-amber-400'
    case 'bad':
      return 'bg-red-500/15 text-red-700 dark:text-red-400'
    default:
      return 'bg-black/10 dark:bg-white/10 opacity-80'
  }
})
</script>

<template>
  <span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium" :class="classes">
    {{ label ?? '—' }}
  </span>
</template>
