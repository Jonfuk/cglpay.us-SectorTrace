<script setup lang="ts">
// Journey — the pages this reader has recently visited, most recent first.
// Purely a per-browser convenience; nothing is sent anywhere.
const journey = useJourney()
useHead({ title: 'SectorTrace — Your journey' })
</script>

<template>
  <section class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-semibold">Your journey</h1>
      <UButton
        v-if="journey.visits.value.length"
        size="xs"
        color="neutral"
        variant="ghost"
        @click="journey.clear()"
      >Clear</UButton>
    </div>
    <p class="opacity-70 text-sm">Recently visited pages, kept only in this browser.</p>

    <StEmptyState
      v-if="!journey.visits.value.length"
      title="No pages yet"
      message="Pages you visit appear here so you can retrace your steps."
    />
    <ul v-else class="divide-y divide-black/5 dark:divide-white/5">
      <li v-for="v in journey.visits.value" :key="v.href" class="py-2">
        <a :href="v.href" class="text-[var(--st-accent)] hover:underline">{{ v.label }}</a>
      </li>
    </ul>
  </section>
</template>
