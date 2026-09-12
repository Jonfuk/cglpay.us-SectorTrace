<script setup lang="ts">
const route = useRoute()
const views = [
  { path: '/coverage', lens: 'guide', label: 'Guide' },
  { path: '/catalogue', label: 'Catalogue' },
  { path: '/coverage', lens: 'history', label: 'History' },
  { path: '/coverage', lens: 'freshness', label: 'Freshness' },
  { path: '/calendar', label: 'Publication calendar' },
  { path: '/changes', label: 'Recorded changes' },
]
function active(view: typeof views[number]) {
  const lens = route.query.lens ?? (route.query.provider_key || route.query.ons_code ? 'history' : 'guide')
  return route.path === view.path && (!view.lens || view.lens === lens)
}
</script>
<template><nav aria-label="Evidence coverage views" class="st-lens-nav"><NuxtLink v-for="view in views" :key="view.label" :to="{ path: view.path, query: view.lens && view.lens !== 'guide' ? { lens: view.lens } : {} }" active-class="" exact-active-class="" :aria-current="active(view) ? 'page' : undefined">{{ view.label }}</NuxtLink></nav></template>
