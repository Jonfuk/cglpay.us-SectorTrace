<script setup lang="ts">
// Notebook — evidence the reader pinned while researching, with an optional
// note. Per-browser only; nothing is sent anywhere. Entries are added from
// evidence pages via the ✎ action and managed here.
const notebook = useNotebook()
useHead({ title: 'SectorTrace — Notebook' })
</script>

<template>
  <section class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-semibold">Notebook</h1>
      <UButton
        v-if="notebook.entries.value.length"
        size="xs"
        color="neutral"
        variant="ghost"
        @click="notebook.clear()"
      >Clear all</UButton>
    </div>
    <p class="opacity-70 text-sm">Evidence you pinned while researching, kept in this browser.</p>

    <StEmptyState
      v-if="!notebook.entries.value.length"
      title="Your notebook is empty"
      message="Pin an evidence page with the ✎ Note button in the header to keep it here."
    />
    <ul v-else class="space-y-3">
      <li
        v-for="e in notebook.entries.value"
        :key="e.id"
        class="border border-black/10 dark:border-white/10 rounded-lg p-3 space-y-1"
      >
        <div class="flex items-start gap-4">
          <a :href="e.href" class="flex-1 font-medium text-[var(--st-accent)] hover:underline">{{ e.title }}</a>
          <UButton size="xs" color="neutral" variant="ghost" @click="notebook.remove(e.id)">Remove</UButton>
        </div>
        <p v-if="e.note" class="text-sm opacity-70">{{ e.note }}</p>
      </li>
    </ul>
  </section>
</template>
