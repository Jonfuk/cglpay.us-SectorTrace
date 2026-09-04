<script setup lang="ts">
// Saved searches — filtered views the reader chose to keep, each a shareable
// link back to that exact URL (a filtered view is a link). Per-browser only.
const saved = useSavedSearches()
useHead({ title: 'SectorTrace — Saved searches' })
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold">Saved searches</h1>
    <p class="opacity-70 text-sm">
      Views you saved with the ☆ button, kept in this browser. Each is a link
      back to that exact filtered view.
    </p>

    <StEmptyState
      v-if="!saved.searches.value.length"
      title="No saved searches"
      message="Use the ☆ Save button in the header to keep a filtered view here."
    />
    <ul v-else class="divide-y divide-black/5 dark:divide-white/5">
      <li v-for="s in saved.searches.value" :key="s.id" class="py-2 flex items-center gap-4">
        <a :href="s.href" class="flex-1 text-[var(--st-accent)] hover:underline break-words">{{ s.label }}</a>
        <UButton size="xs" color="neutral" variant="ghost" @click="saved.remove(s.id)">Remove</UButton>
      </li>
    </ul>
  </section>
</template>
