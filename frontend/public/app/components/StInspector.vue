<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
defineProps<{ title: string }>()
const emit = defineEmits<{ close: [] }>()
const wide = ref<boolean | null>(null)
const open = ref(true)
const heading = ref<HTMLElement | null>(null)
let media: MediaQueryList | undefined
function update() { wide.value = media?.matches ?? false }
onMounted(() => { media = matchMedia('(min-width: 1200px)'); update(); media.addEventListener('change', update) })
onBeforeUnmount(() => media?.removeEventListener('change', update))
// Wait for the media query before mounting either branch. Briefly mounting
// a mobile focus trap on desktop can restore focus after the heading receives it.
watch(wide, async value => { if (value) { await nextTick(); heading.value?.focus() } }, { flush: 'post' })
</script>
<template>
  <aside v-if="wide" class="st-inspector" :aria-label="title"><header><h2 ref="heading" tabindex="-1" class="st-inspector-heading">{{ title }}</h2><button type="button" class="atlas-button" @click="emit('close')">Close</button></header><slot /></aside>
  <LazyStInspectorSheet v-else-if="wide === false" v-model:open="open" :title="title" @update:open="value => { if (!value) emit('close') }"><slot /></LazyStInspectorSheet>
</template>
