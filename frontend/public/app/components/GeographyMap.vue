<script setup lang="ts">
import { computed, markRaw, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import type { ExpressionSpecification, GeoJSONSource, Map as MlMap } from 'maplibre-gl'
import type { FeatureCollection, Point } from 'geojson'
import type { GeographyFeature } from '~/types/api'
import { createPmtilesProtocol, type BoundaryManifest } from '~/lib/pmtiles'
import { mapScale } from '~/lib/map-scale'
import { authorityObservations, type MapLocation } from '~/lib/places'
const props = defineProps<{ features: GeographyFeature[]; metricLabel?: string; locator?: boolean; selected?: string; focusSelected?: boolean; pointLayer?: boolean; locations?: MapLocation[]; selectedLocation?: string; excludedCodes?: string[] }>()
const emit = defineEmits<{ select: [code: string]; selectLocation: [id: string] }>()
const container = ref<HTMLElement | null>(null)
const map = shallowRef<MlMap | null>(null)
const status = ref<'loading' | 'ready' | 'error'>('loading')
const selectedBoundaryFound = ref<boolean | null>(null)
const numericValues = computed(() => [...valueByCode().values()])
const scale = computed(() => mapScale(numericValues.value))
let resizeObserver: ResizeObserver | null = null
let fetchController: AbortController | null = null
let disposed = false
let appliedCodes = new Set<string>()
let module: typeof import('maplibre-gl') | null = null
let protocolRegistered = false
let focusedCode: string | undefined
function focusBoundary(instance: MlMap) {
  if (!props.focusSelected || !props.selected || focusedCode === props.selected || !instance.isSourceLoaded('authorities')) return
  const features = instance.querySourceFeatures('authorities', { sourceLayer: 'authorities', filter: ['==', ['get', 'ons_code'], props.selected] })
  selectedBoundaryFound.value = features.length > 0
  if (!features.length) return
  const positions: number[][] = []
  function collect(value: unknown) {
    if (!Array.isArray(value)) return
    if (value.length >= 2 && typeof value[0] === 'number' && typeof value[1] === 'number' && Number.isFinite(value[0]) && Number.isFinite(value[1])) positions.push([value[0], value[1]])
    else value.forEach(collect)
  }
  for (const feature of features) if ('coordinates' in feature.geometry) collect(feature.geometry.coordinates)
  if (!positions.length) return
  focusedCode = props.selected
  instance.fitBounds([[Math.min(...positions.map(p => p[0]!)), Math.min(...positions.map(p => p[1]!))], [Math.max(...positions.map(p => p[0]!)), Math.max(...positions.map(p => p[1]!))]], { padding: 36, maxZoom: 10, duration: 0 })
}
function valueByCode() {
  const values = new Map<string, number>()
  for (const f of authorityObservations(props.features).mapped) {
    if (f.ons_code && typeof f.value === 'number' && Number.isFinite(f.value)) values.set(f.ons_code, f.value)
  }
  return values
}
function colours(): ExpressionSpecification | string {
  if (props.locator) return '#607080'
  const { breaks, colours } = scale.value
  const steps = breaks.flatMap((value, index) => [value, colours[index + 1]!])
  const numeric = breaks.length ? ['step', ['feature-state', 'value'], colours[0], ...steps] : colours[0]
  return ['case', ['==', ['feature-state', 'recordState'], 'ambiguous'], '#986D2D', ['==', ['feature-state', 'recordState'], null], '#323232', ['==', ['feature-state', 'value'], null], '#656565', ['==', ['feature-state', 'value'], 0], '#FFFFFF', numeric] as ExpressionSpecification
}
function syncState(instance: MlMap) {
  const values = valueByCode()
  const groups = authorityObservations(props.features)
  const codes = new Set([...groups.grouped.keys(), ...(props.excludedCodes ?? [])])
  // Feature IDs are scoped to the vector source layer. Clear obsolete values
  // before a new period paints, so missing evidence cannot inherit old colour.
  for (const code of appliedCodes) {
    if (!codes.has(code)) instance.removeFeatureState({ source: 'authorities', sourceLayer: 'authorities', id: code })
  }
  for (const code of codes) instance.setFeatureState({ source: 'authorities', sourceLayer: 'authorities', id: code }, { value: values.get(code) ?? null, recordState: groups.ambiguous.includes(code) || props.excludedCodes?.includes(code) ? 'ambiguous' : 'single' })
  appliedCodes = codes
}
function pointData(): FeatureCollection<Point> {
  return { type: 'FeatureCollection', features: (props.locations ?? []).map(row => ({ type: 'Feature', properties: { location_id: row.location_id, name: row.location_name }, geometry: { type: 'Point', coordinates: [row.longitude, row.latitude] } })) }
}
function update() {
  const instance = map.value
  if (!instance?.getLayer('authorities-fill')) return
  instance.setPaintProperty('authorities-fill', 'fill-color', colours())
  instance.setFilter('authority-selection', ['==', ['get', 'ons_code'], props.selected ?? ''])
  syncState(instance)
  const points = instance.getSource('locations') as GeoJSONSource | undefined
  points?.setData(pointData())
  for (const id of ['locations-cluster', 'locations-point', 'location-selection']) if (instance.getLayer(id)) instance.setLayoutProperty(id, 'visibility', props.pointLayer ? 'visible' : 'none')
  if (instance.getLayer('location-selection')) instance.setFilter('location-selection', ['==', ['get', 'location_id'], props.selectedLocation ?? ''])
  if (props.focusSelected) focusBoundary(instance)
}
onMounted(async () => {
  fetchController = new AbortController()
  try {
    // Heavy runtime and styles remain outside the shell and directory chunks.
    const ml = await import('maplibre-gl')
    module = ml
    await import('maplibre-gl/dist/maplibre-gl.css')
    if (disposed || !container.value) return
    const response = await fetch('/map/boundaries.json', { signal: fetchController.signal, headers: { Accept: 'application/json' } })
    if (!response.ok) throw new Error('Boundary manifest unavailable')
    const manifest: BoundaryManifest = await response.json()
    if (disposed) return
    ml.addProtocol('pmtiles', createPmtilesProtocol(manifest.archive))
    protocolRegistered = true
    const instance = markRaw(new ml.Map({ container: container.value, style: { version: 8, sources: {}, layers: [] }, center: [-1.5, 52.8], zoom: 5.2, attributionControl: false, dragRotate: false }))
    map.value = instance
    // Start with the manifest extent so a selected northern or coastal area is
    // loaded before fitting its actual returned geometry. Never guess a centre.
    instance.fitBounds(manifest.bounds, { padding: 16, duration: 0 })
    instance.addControl(new ml.NavigationControl({ showCompass: false }), 'top-right')
    instance.on('load', () => {
      if (disposed) return
      instance.addSource('authorities', { type: 'vector', tiles: ['pmtiles://boundaries/{z}/{x}/{y}.pbf'], minzoom: manifest.min_zoom, maxzoom: manifest.max_zoom, promoteId: 'ons_code' })
      instance.addLayer({ id: 'authorities-fill', type: 'fill', source: 'authorities', 'source-layer': 'authorities', paint: { 'fill-color': colours(), 'fill-outline-color': '#141414', 'fill-opacity': .9 } })
      instance.addLayer({ id: 'authority-selection', type: 'line', source: 'authorities', 'source-layer': 'authorities', filter: ['==', ['get', 'ons_code'], props.selected ?? ''], paint: { 'line-color': '#34D1BF', 'line-width': 3 } })
      instance.addSource('locations', { type: 'geojson', data: pointData(), cluster: true, clusterRadius: 40, clusterMaxZoom: 12 })
      instance.addLayer({ id: 'locations-cluster', type: 'circle', source: 'locations', filter: ['has', 'point_count'], paint: { 'circle-radius': 14, 'circle-color': '#3454D1', 'circle-stroke-color': '#DDE3FA', 'circle-stroke-width': 2 } })
      instance.addLayer({ id: 'locations-point', type: 'circle', source: 'locations', filter: ['!', ['has', 'point_count']], paint: { 'circle-radius': 6, 'circle-color': '#3454D1', 'circle-stroke-color': '#DDE3FA', 'circle-stroke-width': 2 } })
      instance.addLayer({ id: 'location-selection', type: 'circle', source: 'locations', filter: ['==', ['get', 'location_id'], props.selectedLocation ?? ''], paint: { 'circle-radius': 10, 'circle-color': 'transparent', 'circle-stroke-color': '#34D1BF', 'circle-stroke-width': 3 } })
      instance.on('click', 'locations-point', event => {
        const id = event.features?.[0]?.properties?.location_id
        if (typeof id === 'string') emit('selectLocation', id)
      })
      instance.on('click', 'locations-cluster', async event => {
        const cluster = event.features?.[0]
        if (!cluster || cluster.geometry.type !== 'Point') return
        try {
          const zoom = await (instance.getSource('locations') as GeoJSONSource).getClusterExpansionZoom(Number(cluster.properties.cluster_id))
          if (!disposed) instance.easeTo({ center: cluster.geometry.coordinates as [number, number], zoom, duration: 0 })
        } catch { /* A disappearing cluster can follow a changed layer. */ }
      })
      instance.on('sourcedata', event => { if (event.isSourceLoaded && event.sourceId === 'authorities') syncState(instance) })
      instance.on('idle', () => focusBoundary(instance))
      instance.on('click', 'authorities-fill', event => {
        if (props.pointLayer) return
        const code = event.features?.[0]?.properties?.ons_code
        if (typeof code === 'string') emit('select', code)
      })
      status.value = 'ready'
      update()
    })
    instance.on('error', () => { status.value = 'error' })
    resizeObserver = new ResizeObserver(() => instance.resize())
    resizeObserver.observe(container.value)
  } catch { if (!disposed) status.value = 'error' }
})
watch(() => [props.features, props.locator, props.selected, props.locations, props.pointLayer, props.selectedLocation, props.excludedCodes], update)
onBeforeUnmount(() => {
  disposed = true
  fetchController?.abort()
  resizeObserver?.disconnect()
  map.value?.remove()
  if (protocolRegistered) module?.removeProtocol('pmtiles')
})
</script>
<template>
  <div class="st-geography-map">
    <div class="relative"><div ref="container" class="st-map-canvas" role="region" :aria-label="pointLayer ? 'Loaded CQC registration locations' : locator ? 'Authority boundary map' : (metricLabel ?? 'Authority evidence map')" />
      <p v-if="status !== 'ready'" class="st-map-status" role="status">{{ status === 'error' ? (pointLayer ? 'Map could not load. Use the registration list to continue.' : 'Map could not load. Use the authority list to continue.') : 'Loading map…' }}</p>
    </div>
    <p v-if="focusSelected && selectedBoundaryFound === false && status === 'ready'" class="atlas-footnote" role="status">The selected boundary is not present in the loaded map. The authority identity and evidence remain available below.</p>
    <p v-if="focusSelected && selectedBoundaryFound === true && status === 'ready'" class="atlas-footnote" role="status">The selected authority boundary is outlined.</p>
    <div v-if="!locator" class="st-map-legend"><strong>{{ metricLabel ?? 'Value' }}</strong><template v-if="numericValues.length"><span v-for="(colour, index) in scale.colours" :key="colour"><i :style="{ background: colour }" aria-hidden="true" />{{ index === 0 ? (scale.breaks.length ? `Below ${scale.breaks[0]?.toLocaleString('en-GB')}` : `Constant value ${numericValues[0]?.toLocaleString('en-GB')}`) : `From ${scale.breaks[index - 1]?.toLocaleString('en-GB')}` }}</span></template><span v-else>No numeric observations to classify</span><span>Grey: missing value</span><span>White: zero</span><span>Dark: no observation returned</span><span>Amber: multiple observations</span><p>Display classification uses up to five quantile bands over the unambiguous numeric observations. Repeated breakpoints are combined.</p></div>
    <p v-if="pointLayer" class="atlas-footnote">Small blue circles are returned registration locations. Larger circles group nearby returned locations. Select a group to zoom in.</p>
    <p class="atlas-footnote">Authority boundaries: Office for National Statistics.</p>
  </div>
</template>
