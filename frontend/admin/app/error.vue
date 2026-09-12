<script setup lang="ts">
import type { NuxtError } from '#app'

// A dynamic route that does not resolve in the client SPA lands here. It is not
// evidence of absence — the app simply has no page for the fragment. Offer a
// route home rather than implying the data does not exist.
defineProps<{ error: NuxtError }>()

function goHome() {
  clearError({ redirect: '/' })
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center p-8">
    <div class="max-w-md text-center space-y-4">
      <p class="text-sm uppercase tracking-wide text-[var(--st-accent)]">
        SectorTrace
      </p>
      <h1 class="text-2xl font-semibold">
        {{ error?.statusCode === 404 ? 'Page not found' : 'Something went wrong' }}
      </h1>
      <p class="text-sm opacity-70">
        This address has no page. It does not mean the underlying evidence is
        missing.
      </p>
      <UButton color="primary" @click="goHome">
        Back to mission control
      </UButton>
    </div>
  </div>
</template>
