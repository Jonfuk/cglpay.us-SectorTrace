<script setup lang="ts">
import { markRaw, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { CqcLocation } from '~/types/api'

const props = defineProps<{ locations: CqcLocation[] }>()
const container = ref<HTMLElement | null>(null)
const status = ref<'loading' | 'ready' | 'error'>('loading')
let map: import('maplibre-gl').Map | null = null
let maplibre: typeof import('maplibre-gl') | null = null

function points() {
  return {
    type: 'FeatureCollection' as const,
    features: props.locations
      .filter((row) => row.latitude != null && row.longitude != null)
      .map((row) => ({
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: [Number(row.longitude), Number(row.latitude)] },
        properties: {
          name: row.location_name || row.provider_name || row.location_id || 'CQC location',
          rating: row.overall_rating || 'Not rated',
        },
      })),
  }
}

async function build() {
  if (!container.value) return
  try {
    maplibre = await import('maplibre-gl')
    await import('maplibre-gl/dist/maplibre-gl.css')
    const instance = markRaw(new maplibre.Map({
      container: container.value,
      style: { version: 8, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#0b1220' } }] },
      center: [-1.5, 52.8], zoom: 5.2, attributionControl: false, dragRotate: false,
    }))
    map = instance
    instance.on('load', () => {
      instance.addSource('locations', { type: 'geojson', data: points() })
      instance.addLayer({ id: 'location-point', type: 'circle', source: 'locations', paint: { 'circle-color': '#4f8cff', 'circle-radius': 6, 'circle-stroke-width': 1.5, 'circle-stroke-color': '#f4f8ff' } })
      instance.on('click', 'location-point', (event) => {
        const properties = event.features?.[0]?.properties || {}
        new maplibre!.Popup().setLngLat(event.lngLat).setText(`${properties.name} — ${properties.rating}`).addTo(instance)
      })
      instance.on('mouseenter', 'location-point', () => { instance.getCanvas().style.cursor = 'pointer' })
      instance.on('mouseleave', 'location-point', () => { instance.getCanvas().style.cursor = '' })
      status.value = 'ready'
    })
    instance.on('error', () => { status.value = 'error' })
  } catch {
    status.value = 'error'
  }
}

watch(() => props.locations, () => {
  const source = map?.getSource('locations') as import('maplibre-gl').GeoJSONSource | undefined
  if (source) source.setData(points())
})

onMounted(build)
onBeforeUnmount(() => { map?.remove(); map = null; maplibre = null })
</script>

<template>
  <div class="relative">
    <div ref="container" class="h-[420px] w-full rounded-lg overflow-hidden bg-black/5 dark:bg-white/5" />
    <div v-if="status !== 'ready'" class="absolute inset-0 flex items-center justify-center text-sm opacity-60 pointer-events-none">
      {{ status === 'error' ? 'Map could not load; use the table below.' : 'Loading map…' }}
    </div>
    <div v-else class="absolute bottom-3 left-3 bg-black/70 rounded px-2 py-1 text-xs">Located CQC registrations</div>
  </div>
</template>
