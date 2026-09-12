<script setup lang="ts">
const api = useAdminApi();
const { data, error, refresh } = await useAsyncData(
  'admin-shell-jobs',
  () => api.jobs(),
  { default: () => null, lazy: true },
);
useAdminPolling(refresh, 15000);
</script>
<template>
  <NuxtLink to="/pipeline" class="flex items-center gap-2"
    ><span
      class="inline-block w-1.5 h-1.5 rounded-full"
      :style="{
        background: data?.running ? 'var(--st-positive)' : 'var(--st-muted)',
      }"
      aria-hidden="true"
    /><span>{{
      error
        ? 'Run status unavailable'
        : data?.running
          ? `Run #${data.running} active`
          : data
            ? 'No active collection run'
            : 'Checking run status…'
    }}</span></NuxtLink
  >
</template>
