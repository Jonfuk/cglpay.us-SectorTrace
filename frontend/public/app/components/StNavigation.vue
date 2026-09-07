<script setup lang="ts">
import { navigationGroups, navigationSectionPath } from '~/lib/navigation'
const route = useRoute()
defineProps<{ compact?: boolean }>()
defineEmits<{ navigate: [] }>()
</script>
<template>
  <nav aria-label="Main sections" class="st-navigation" :class="{ 'is-compact': compact }">
    <details v-for="group in navigationGroups" :key="group.label" open class="st-nav-group">
      <summary :title="group.label" :aria-label="group.label"><span>{{ group.label }}</span></summary>
      <NuxtLink v-for="[to, label, symbol] in group.items" :key="to" :to="to"
        :class="{ 'router-link-active': navigationSectionPath(route.path) === to }"
        :title="label" :aria-label="label" @click="$emit('navigate')">
        <span class="st-nav-symbol" aria-hidden="true">{{ symbol }}</span><span class="st-nav-label">{{ label }}</span>
      </NuxtLink>
    </details>
  </nav>
</template>
