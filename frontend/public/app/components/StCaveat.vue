<script setup lang="ts">
// A caveat note. The API attaches caveats to figures that must not be
// over-read (e.g. contract values that must not be summed). Rendering the
// caveat beside the figure is not decoration — it is the difference between a
// defensible figure and a misleading one, so it is a first-class UI state.
defineProps<{ text: string | null | undefined }>()
</script>

<template>
  <p v-if="text" class="text-xs opacity-70 flex gap-1.5 items-start">
    <span aria-hidden="true">⚠</span>
    <span>{{ text }}</span>
  </p>
</template>
