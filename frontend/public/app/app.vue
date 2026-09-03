<script setup lang="ts">
// Application root. The public atlas uses no toasts, overlays, tooltips, or
// portals, so it deliberately does NOT mount Nuxt UI's <UApp> host — that host
// pulls Reka UI's overlay/portal machinery into the shared entry chunk, and
// leaving it out keeps the public shared bundle smaller. The admin app, which
// does use toasts, mounts <UApp>. If a future public route needs an overlay,
// reintroduce <UApp> and re-check the shared-JS budget.
</script>

<template>
  <NuxtLayout>
    <NuxtPage />
  </NuxtLayout>
</template>
