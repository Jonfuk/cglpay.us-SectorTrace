<script setup lang="ts">
import { markRaw, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
// Type-only imports are erased at build time, so they do NOT pull MapLibre into
// this chunk — the runtime import stays dynamic below.
import type { ExpressionSpecification, Map as MlMap } from 'maplibre-gl'
import type { GeographyFeature } from '~/types/api'

// A lifecycle-safe MapLibre choropleth, confined to the Places route.
//
// MapLibre and its CSS are DYNAMICALLY imported here, so they land in this
// component's own async chunk and never touch the shared bundle — no non-map
// route pays for the map (Phase 6 route boundary). The map instance is markRaw
// (Vue must not proxy an imperative WebGL object), and everything it creates —
// the map, the ResizeObserver, the outstanding fetch — is disposed before
// unmount so ten navigations leave no detached canvas, observer, or in-flight
// request behind.
//
// There is NO base map: only the authority polygons on a blank ground, coloured
// by value. That keeps the map origin-only and working with the network cable
// unplugged — the boundary geometry is the same-origin `/api/v1/boundaries`
// FeatureCollection, joined by ons_code to the values this component is given.
// (The ~14 MB full-resolution GeoJSON is the current API; serving pre-tiled
// PMTiles is the tracked optimisation, and this component's source is the seam
// where that swap lands.)
const props = defineProps<{
  /** Authority values to colour by, keyed by ons_code via `ons_code`/`value`. */
  features: GeographyFeature[]
  /** Label for the legend. */
  metricLabel?: string
}>()

const container = ref<HTMLElement | null>(null)
const map = shallowRef<MlMap | null>(null)
const status = ref<'loading' | 'ready' | 'error'>('loading')
let resizeObserver: ResizeObserver | null = null
let fetchController: AbortController | null = null
let disposed = false

// A five-step single-hue sequential ramp (light → dark blue). Sequential data,
// single hue: darker = larger. Deliberately not a rainbow.
const RAMP = ['#e8eef9', '#b9ccec', '#7fa6db', '#3f74c0', '#1d4ed8'] as const

function valueByCode(): Map<string, number> {
  const m = new Map<string, number>()
  for (const f of props.features) {
    if (f.ons_code && typeof f.value === 'number') m.set(f.ons_code, f.value)
  }
  return m
}

/** Build a MapLibre step expression from the value distribution. */
function colorExpression(values: number[]): ExpressionSpecification | string {
  if (!values.length) return RAMP[0]
  const sorted = [...values].sort((a, b) => a - b)
  const q = (p: number) => sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))]
  const breaks = [q(0.2), q(0.4), q(0.6), q(0.8)]
  return [
    'step',
    ['coalesce', ['feature-state', 'value'], -Infinity],
    RAMP[0],
    breaks[0], RAMP[1],
    breaks[1], RAMP[2],
    breaks[2], RAMP[3],
    breaks[3], RAMP[4],
  ] as ExpressionSpecification
}

async function build() {
  if (!container.value) return
  fetchController = new AbortController()
  try {
    // Dynamic import → separate chunk. CSS injected the same way.
    const maplibre = await import('maplibre-gl')
    await import('maplibre-gl/dist/maplibre-gl.css')
    if (disposed) return

    const boundaries = await fetch('/api/v1/boundaries', {
      headers: { Accept: 'application/json' },
      signal: fetchController.signal,
    }).then((r) => r.json())
    if (disposed) return

    const instance = markRaw(
      new maplibre.Map({
        container: container.value,
        // A blank style — no external tiles, no CDN. Just our own polygons.
        style: { version: 8, sources: {}, layers: [] },
        center: [-1.5, 52.8],
        zoom: 5.2,
        attributionControl: false,
        // The boundary geometry is not interactive-tile-backed; keep it simple.
        dragRotate: false,
      }),
    )
    map.value = instance

    instance.on('load', () => {
      if (disposed) return
      instance.addSource('authorities', { type: 'geojson', data: boundaries, promoteId: 'ons_code' })
      const values = valueByCode()
      instance.addLayer({
        id: 'authorities-fill',
        type: 'fill',
        source: 'authorities',
        paint: {
          'fill-color': colorExpression([...values.values()]),
          'fill-outline-color': '#ffffff',
          'fill-opacity': 0.9,
        },
      })
      // Feature-state carries the value so the paint expression can read it.
      for (const feature of boundaries.features ?? []) {
        const code = feature.properties?.ons_code
        if (code && values.has(code)) {
          instance.setFeatureState({ source: 'authorities', id: code }, { value: values.get(code) })
        }
      }
      status.value = 'ready'
    })
    instance.on('error', () => { status.value = 'error' })

    resizeObserver = new ResizeObserver(() => instance.resize())
    resizeObserver.observe(container.value)
  } catch {
    if (!disposed) status.value = 'error'
  }
}

// Recolour in place when the values change (metric switch) without rebuilding.
watch(
  () => props.features,
  () => {
    const instance = map.value
    if (!instance || status.value !== 'ready') return
    const values = valueByCode()
    if (instance.getLayer('authorities-fill')) {
      instance.setPaintProperty('authorities-fill', 'fill-color', colorExpression([...values.values()]))
    }
    for (const [code, value] of values) {
      instance.setFeatureState({ source: 'authorities', id: code }, { value })
    }
  },
)

onMounted(build)

onBeforeUnmount(() => {
  disposed = true
  fetchController?.abort()
  fetchController = null
  resizeObserver?.disconnect()
  resizeObserver = null
  map.value?.remove()
  map.value = null
})
</script>

<template>
  <div class="relative">
    <div ref="container" class="h-[520px] w-full rounded-lg overflow-hidden bg-black/5 dark:bg-white/5" />
    <div
      v-if="status !== 'ready'"
      class="absolute inset-0 flex items-center justify-center text-sm opacity-60 pointer-events-none"
    >
      {{ status === 'error' ? 'Map could not load.' : 'Loading map…' }}
    </div>
    <div
      v-if="status === 'ready'"
      class="absolute bottom-3 left-3 bg-white/85 dark:bg-black/70 rounded px-2 py-1 text-xs"
    >
      <span class="opacity-70">{{ metricLabel ?? 'Value' }}:</span>
      <span class="inline-flex items-center gap-0.5 ml-1 align-middle">
        <span class="opacity-60">low</span>
        <span
          v-for="c in ['#e8eef9', '#b9ccec', '#7fa6db', '#3f74c0', '#1d4ed8']"
          :key="c"
          class="inline-block w-3 h-3 rounded-sm"
          :style="{ backgroundColor: c }"
        />
        <span class="opacity-60">high</span>
      </span>
    </div>
  </div>
</template>
