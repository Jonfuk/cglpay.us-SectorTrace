<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string | number | null | undefined;
    level?: 'ok' | 'warn' | 'bad' | 'neutral';
  }>(),
  { level: 'neutral' },
);
</script>
<template>
  <span class="admin-status" :class="`admin-status-${level}`"
    ><span v-if="level === 'ok'" aria-hidden="true">✓</span
    ><span v-if="level === 'bad'" aria-hidden="true">!</span
    >{{ label ?? 'Unavailable' }}</span
  >
</template>
