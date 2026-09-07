<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
const props = withDefaults(defineProps<{ storageKey: string; primaryLabel: string; secondaryLabel: string; pane?: string; initial?: number }>(), { pane: 'primary', initial: 38 })
const emit = defineEmits<{ pane: [value: string] }>()
const container = ref<HTMLElement | null>(null)
const preferredPercent = ref(props.initial)
const width = ref(1000)
const store = useLocalStore<number>(`st.split.${props.storageKey}`, 1, () => props.initial)
const minimum = computed(() => Math.min(45, 280 / width.value * 100))
const maximum = computed(() => Math.max(minimum.value, Math.min(65, (width.value - 492) / width.value * 100)))
let observer: ResizeObserver | undefined
let dragging = false
function clamp(value: number) { return Math.max(minimum.value, Math.min(maximum.value, value)) }
const percent = computed(() => clamp(preferredPercent.value))
function persist() { store.write(preferredPercent.value) }
function reset() { preferredPercent.value = clamp(props.initial); persist() }
function point(event: PointerEvent) {
  if (!dragging || !container.value) return
  const box = container.value.getBoundingClientRect()
  preferredPercent.value = clamp((event.clientX - box.left) / box.width * 100)
}
function start(event: PointerEvent) {
  if (event.button !== 0) return
  dragging = true
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  point(event)
}
function end() { if (dragging) { dragging = false; persist() } }
function key(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  preferredPercent.value = clamp(event.key === 'Home' ? minimum.value : event.key === 'End' ? maximum.value : percent.value + (event.key === 'ArrowLeft' ? -2 : 2))
  persist()
}
onMounted(() => {
  const saved = store.read()
  if (typeof saved === 'number' && Number.isFinite(saved)) preferredPercent.value = saved
  observer = new ResizeObserver(entries => { width.value = Math.max(1, entries[0]?.contentRect.width ?? 1000) })
  if (container.value) observer.observe(container.value)
})
onBeforeUnmount(() => observer?.disconnect())
</script>
<template>
  <div><div class="st-pane-controls"><div class="st-mobile-panes" role="group" aria-label="Workspace pane"><button type="button" class="atlas-button" :aria-pressed="pane === 'primary'" @click="emit('pane', 'primary')">{{ primaryLabel }}</button><button type="button" class="atlas-button" :aria-pressed="pane === 'secondary'" @click="emit('pane', 'secondary')">{{ secondaryLabel }}</button></div><button type="button" class="atlas-button st-reset-split" @click="reset">Reset layout</button></div>
    <div ref="container" class="st-split-workspace" :data-pane="pane" :style="{ '--split-percent': `${percent}%` }"><div class="st-split-primary"><slot name="primary" /></div><div class="st-split-separator" role="separator" tabindex="0" aria-orientation="vertical" :aria-label="`Resize ${primaryLabel} and ${secondaryLabel}`" :aria-valuenow="Math.round(percent)" :aria-valuemin="Math.round(minimum)" :aria-valuemax="Math.round(maximum)" @keydown="key" @pointerdown="start" @pointermove="point" @pointerup="end" @lostpointercapture="end" /><div class="st-split-secondary"><slot name="secondary" /></div></div>
  </div>
</template>
