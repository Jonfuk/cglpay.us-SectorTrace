<script setup lang="ts">
// No-data and unavailable states. These are distinct and must read distinctly:
//
//   * `unavailable` — the query failed or the source could not be reached right
//     now. Try again; this says nothing about the evidence.
//   * empty (default) — the query succeeded and returned nothing for these
//     filters. This is "no matching evidence returned", NOT "this does not
//     exist". Absence is never rendered as a claim of non-existence.
withDefaults(
  defineProps<{
    variant?: 'empty' | 'unavailable'
    title?: string
    message?: string
  }>(),
  { variant: 'empty' },
)
</script>

<template>
  <div class="border border-dashed border-black/15 dark:border-white/15 rounded-lg p-6 text-center space-y-1">
    <p class="text-sm font-medium">
      {{ title ?? (variant === 'unavailable' ? 'Currently unavailable' : 'No matching evidence') }}
    </p>
    <p class="text-xs opacity-60 max-w-sm mx-auto">
      {{
        message ??
        (variant === 'unavailable'
          ? 'This view could not load right now. It does not mean the evidence is missing.'
          : 'No evidence matched these filters. That is not a claim that none exists — try widening the filters.')
      }}
    </p>
  </div>
</template>
