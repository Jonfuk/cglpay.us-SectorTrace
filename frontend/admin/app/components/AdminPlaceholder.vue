<script setup lang="ts">
// An honest placeholder for an operator module whose full port is scheduled for
// a later stage. It states what the module is and that it is not yet ported —
// it never fakes data. The route exists so nav, deep links, and bookmarks
// resolve during the migration.
defineProps<{ title: string; note: string }>()
</script>

<template>
  <section class="space-y-4">
    <h1 class="text-2xl font-semibold">{{ title }}</h1>
    <div class="border border-dashed border-black/15 dark:border-white/15 rounded-lg p-6 space-y-1">
      <p class="text-sm font-medium">Not yet ported</p>
      <p class="text-sm opacity-60 max-w-lg">{{ note }}</p>
    </div>
  </section>
</template>
