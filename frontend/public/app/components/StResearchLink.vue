<script setup lang="ts">
import { computed } from 'vue'
import { researchHref } from '~/lib/route-compatibility'
const props = defineProps<{ href: string | null | undefined }>()
const internal = computed(() => researchHref(props.href))
</script>
<template><NuxtLink v-if="internal" :to="internal.slice(1)"><slot>{{ href }}</slot></NuxtLink><StLink v-else :href="href"><slot>{{ href ?? 'Not supplied' }}</slot></StLink></template>
