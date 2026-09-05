<script setup lang="ts">
import { adminGroups } from '~/lib/navigation';
defineProps<{ collapsed?: boolean }>();
const route = useRoute();
const { prefs, save } = useAdminPreferences();
function groupToggle(label: string, event: Event) {
  prefs.value.groups[label] = (event.target as HTMLDetailsElement).open;
  save();
}
</script>
<template>
  <nav aria-label="Operator navigation">
    <template v-for="group in adminGroups" :key="group.label">
      <div v-if="collapsed" class="px-1 py-1">
        <template v-for="item in group.items" :key="item.to"
          ><NuxtLink
            :to="item.to"
            :aria-label="item.label"
            :title="item.label"
            :aria-current="route.path === item.to ? 'page' : undefined"
            class="admin-nav-link"
            ><AdminIcon class="admin-nav-icon" :name="item.to" /></NuxtLink
        ></template>
      </div>
      <details
        v-else
        class="admin-nav-group"
        :open="prefs.groups[group.label] !== false"
        @toggle="groupToggle(group.label, $event)"
      >
        <summary>{{ group.label }}</summary>
        <NuxtLink
          v-for="item in group.items"
          :key="item.to"
          :to="item.to"
          class="admin-nav-link"
          :aria-current="route.path === item.to ? 'page' : undefined"
          ><AdminIcon class="admin-nav-icon" :name="item.to" />{{
            item.label
          }}</NuxtLink
        >
      </details>
    </template>
  </nav>
</template>
