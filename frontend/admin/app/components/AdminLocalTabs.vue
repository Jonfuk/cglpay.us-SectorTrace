<script setup lang="ts">
defineProps<{ tabs: { key: string; label: string }[]; current: string }>();
const route = useRoute();
</script>
<template>
  <nav class="admin-tabs" aria-label="Workspace views">
    <NuxtLink
      v-for="tab in tabs"
      :key="tab.key"
      :to="{ path: route.path, query: { ...route.query, view: tab.key } }"
      :aria-current="current === tab.key ? 'page' : undefined"
      >{{ tab.label }}</NuxtLink
    >
  </nav>
</template>
