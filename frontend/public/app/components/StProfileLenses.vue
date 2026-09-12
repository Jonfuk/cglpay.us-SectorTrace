<script setup lang="ts">
defineProps<{ items: Array<{ key: string; label: string }>; selected: string; label: string }>()
const route = useRoute()
</script>
<template><nav :aria-label="label" class="st-lens-nav"><NuxtLink v-for="item in items" :key="item.key" :to="{ path: route.path, query: { ...route.query, lens: item.key } }" active-class="" exact-active-class="" :aria-current="selected === item.key ? 'page' : undefined">{{ item.label }}</NuxtLink></nav></template>
