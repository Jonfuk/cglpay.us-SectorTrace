<script setup lang="ts">
import { ConfigProvider } from 'reka-ui';
const toast = useToast();
// The fixed operator shell does not use programmatic overlays or tooltips.
// Mount the Nuxt toaster only when there is feedback; its focus/swipe machinery
// should not compete with the initial evidence workspace for download budget.
</script>

<template>
  <ConfigProvider :use-id="useId" locale="en-GB">
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
    <LazyUToaster v-if="toast.toasts.value.length" />
  </ConfigProvider>
</template>
