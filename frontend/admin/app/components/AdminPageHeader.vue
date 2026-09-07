<script setup lang="ts">
defineProps<{ title: string; description?: string; eyebrow?: string }>();
</script>
<template>
  <header class="admin-pagehead">
    <div>
      <p class="admin-eyebrow">{{ eyebrow || 'SectorTrace Â· Operations' }}</p>
      <h1>{{ title }}</h1>
      <p v-if="description" class="admin-description">{{ description }}</p>
    </div>
    <div class="admin-actions"><slot /></div>
  </header>
</template>
