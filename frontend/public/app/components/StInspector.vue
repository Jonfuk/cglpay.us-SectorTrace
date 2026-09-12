<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
defineProps<{ title: string }>()
const emit = defineEmits<{ close: [] }>()
const route = useRoute()
const store = useLocalStore<number>(`st:inspector-width:${route.path}`, 1, () => 360)
const preferred = ref(360)
const available = ref(0)
const desktop = ref(false)
const ready = ref(false)
const wide = computed(() => ready.value ? desktop.value && available.value >= 824 : null)
const maximum = computed(() => Math.max(320, Math.min(560, available.value - 504)))
const width = computed(() => Math.max(320, Math.min(maximum.value, preferred.value)))
const open = ref(true)
const heading = ref<HTMLElement | null>(null)
const anchor = ref<HTMLElement | null>(null)
const status = ref('')
let host: HTMLElement | null = null
let media: MediaQueryList | undefined
let observer: ResizeObserver | undefined
let dragging: { x: number; width: number } | null = null
function update() { desktop.value = media?.matches ?? false }
function persist() { status.value = store.write(preferred.value) ? '' : 'This browser could not save the layout. It remains available until you leave this view.' }
function resize(value: number) { preferred.value = Math.max(320, Math.min(maximum.value, value)) }
function reset() { preferred.value = 360; persist() }
function key(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  resize(event.key === 'Home' ? 320 : event.key === 'End' ? maximum.value : width.value + (event.key === 'ArrowLeft' ? 10 : -10))
  persist()
}
function start(event: PointerEvent) {
  if (event.button !== 0) return
  dragging = { x: event.clientX, width: width.value }
  const target = event.currentTarget as HTMLElement
  target.focus()
  target.setPointerCapture(event.pointerId)
}
function move(event: PointerEvent) { if (dragging) resize(dragging.width + dragging.x - event.clientX) }
function end() { if (dragging) { dragging = null; persist() } }
onMounted(() => {
  const saved = store.read()
  if (typeof saved === 'number' && Number.isFinite(saved)) preferred.value = Math.max(320, Math.min(560, saved))
  // Every inspector is a sibling of its evidence pane. Measure that containing
  // workspace, since viewport width alone cannot account for nested panels.
  host = anchor.value?.parentElement ?? null
  host?.classList.add('st-inspector-host')
  observer = new ResizeObserver(entries => { available.value = entries[0]?.contentRect.width ?? 0; ready.value = true })
  if (host) observer.observe(host)
  media = matchMedia('(min-width: 1200px)')
  update()
  media.addEventListener('change', update)
})
onBeforeUnmount(() => {
  media?.removeEventListener('change', update)
  observer?.disconnect()
  host?.classList.remove('st-inspector-host', 'st-inspector-docked')
  host?.style.removeProperty('--inspector-width')
})
watch([wide, width], () => {
  host?.classList.toggle('st-inspector-docked', wide.value === true)
  host?.style.setProperty('--inspector-width', `${width.value}px`)
}, { flush: 'post' })
// Wait for the containing workspace before mounting either branch. Briefly
// mounting a mobile focus trap on desktop can steal the heading's focus.
watch(wide, async value => { if (value) { await nextTick(); heading.value?.focus() } }, { flush: 'post' })
</script>
<template>
  <span ref="anchor" hidden />
  <aside v-if="wide" class="st-inspector" :aria-label="title">
    <div class="st-inspector-resize" role="separator" tabindex="0" aria-orientation="vertical" :aria-label="`Resize ${title} inspector`" :aria-valuenow="Math.round(width)" aria-valuemin="320" :aria-valuemax="Math.floor(maximum)" :aria-valuetext="`${Math.round(width)} pixels`" @keydown="key" @pointerdown="start" @pointermove="move" @pointerup="end" @lostpointercapture="end" />
    <header><h2 ref="heading" tabindex="-1" class="st-inspector-heading">{{ title }}</h2><button type="button" class="atlas-button" @click="emit('close')">Close</button></header>
    <button type="button" class="atlas-button" @click="reset">Reset inspector width</button><p v-if="status" role="status">{{ status }}</p><slot />
  </aside>
  <LazyStInspectorSheet v-else-if="wide === false" v-model:open="open" :title="title" @update:open="value => { if (!value) emit('close') }"><slot /></LazyStInspectorSheet>
</template>
