<script setup lang="ts">
defineProps<{ term: string }>();
defineEmits<{ navigate: [] }>();
const api = useAdminApi();
const { data } = await useAsyncData(
  'admin-palette-schema',
  () => api.api<{ objects: { name: string }[] }>('/schema'),
  { lazy: true },
);
const { data: facets } = await useAsyncData(
  'admin-palette-facets',
  () => api.api<{ modules?: { module: string }[] }>('/review/facets'),
  { lazy: true },
);
</script>
<template>
  <details class="mt-3">
    <summary class="admin-note">Tables and review worklists</summary>
    <div class="max-h-56 overflow-auto">
      <NuxtLink
        v-for="object in data?.objects?.filter((x) =>
          x.name.toLowerCase().includes(term.toLowerCase()),
        )"
        :key="object.name"
        :to="{ path: '/database', query: { table: object.name } }"
        class="admin-nav-link"
        @click="$emit('navigate')"
        >{{ object.name }}</NuxtLink
      ><NuxtLink
        v-for="module in facets?.modules"
        :key="module.module"
        :to="{ path: '/review', query: { module: module.module } }"
        class="admin-nav-link"
        @click="$emit('navigate')"
        >Review {{ module.module }}</NuxtLink
      >
    </div>
  </details>
</template>
