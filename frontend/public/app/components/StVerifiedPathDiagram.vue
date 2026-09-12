<script setup lang="ts">
import { linkHorizontal } from 'd3-shape'
import { verifiedNode, type VerifiedHop, type VerifiedPathNode } from '~/lib/verified-path'
import { downloadAnnotatedChart } from '~/lib/chart-export'
const props = defineProps<{ hops: VerifiedHop[]; nodes: VerifiedPathNode[]; selected: string; annotation: string }>()
const emit = defineEmits<{ inspect: [index: number, event: Event] }>()
const root = ref<HTMLElement | null>(null)
const svg = ref<SVGSVGElement | null>(null)
const colour = useColorMode()
const palette = ref({ text: '#EFEFEF', panel: '#141414', line: '#9A9A9A', selected: '#34D1BF' })
const status = ref('')
const path = linkHorizontal<{ source: [number, number]; target: [number, number] }, [number, number]>()
const label = (id: string | null | undefined) => verifiedNode(props.nodes, id)?.label ?? id ?? 'Identifier not supplied'
const lines = (text: string) => (text.match(/.{1,29}(?:\s|$)|.{1,29}/g) ?? []).slice(0, 2).map(line => line.trim())
async function updateColours() { await nextTick(); if (!root.value) return; const css = getComputedStyle(root.value); palette.value = { text: css.getPropertyValue('--text-primary').trim(), panel: css.getPropertyValue('--surface-panel').trim(), line: css.getPropertyValue('--text-muted').trim(), selected: css.getPropertyValue('--interactive-secondary').trim() } }
onMounted(updateColours)
watch(() => colour.value, updateColours)
async function download(format: 'svg' | 'png') {
  if (!root.value || !svg.value) return
  try { const clone = svg.value.cloneNode(true) as SVGSVGElement; clone.setAttribute('width', String(svg.value.clientWidth)); clone.setAttribute('height', String(svg.value.clientHeight)); await downloadAnnotatedChart({ root: root.value, svgUrl: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(new XMLSerializer().serializeToString(clone))}`, title: 'Returned verified path', annotation: props.annotation, filename: 'verified-path-diagram', format }); status.value = 'Annotated path downloaded.' }
  catch { status.value = 'The image could not be created. The path reference JSON remains available.' }
}
</script>
<template>
  <section aria-label="Verified path diagram" class="space-y-3"><p class="atlas-footnote">Rows follow the returned hop order. Lines have equal weight and no directional arrows. Long node labels are shown in full in the evidence list.</p><div class="overflow-x-auto" role="region" aria-label="Scrollable path diagram" tabindex="0"><div ref="root" style="min-width: 680px"><svg ref="svg" width="100%" :height="hops.length * 130 + 30" :viewBox="`0 0 680 ${hops.length * 130 + 30}`" role="group" aria-label="Returned hop sequence" font-family="Arial, sans-serif" font-size="14">
    <g v-for="(hop, index) in hops" :key="index" :transform="`translate(0, ${index * 130 + 20})`" role="button" tabindex="0" :aria-label="`Inspect diagram hop ${index + 1}`" :aria-pressed="selected === String(index + 1)" @click="emit('inspect', index, $event)" @keydown.enter="emit('inspect', index, $event)" @keydown.space.prevent="emit('inspect', index, $event)"><text x="20" y="14" :fill="palette.text">Hop {{ index + 1 }}</text><path :d="path({ source: [260, 63], target: [420, 63] }) ?? ''" fill="none" stroke-width="3" :stroke="selected === String(index + 1) ? palette.selected : palette.line" :stroke-dasharray="selected === String(index + 1) ? '8 4' : undefined" /><template v-for="(side, sideIndex) in ['from', 'to'] as const" :key="side"><rect :x="sideIndex ? 420 : 20" y="30" width="240" height="66" rx="4" :fill="palette.panel" :stroke="palette.line" /><text :x="sideIndex ? 432 : 32" y="54" :fill="palette.text"><tspan v-for="(line, lineIndex) in lines(label(hop[side]))" :key="lineIndex" :x="sideIndex ? 432 : 32" :dy="lineIndex ? 20 : 0">{{ line }}</tspan></text></template><title>Hop {{ index + 1 }}. {{ label(hop.from) }} to {{ label(hop.to) }}. Recorded relationship: {{ hop.relationship_label ?? hop.relationship ?? 'Not supplied' }}.</title></g>
  </svg></div></div><div class="flex flex-wrap gap-2"><button type="button" class="atlas-button" @click="download('svg')">Download annotated path SVG</button><button type="button" class="atlas-button" @click="download('png')">Download annotated path PNG</button></div><p role="status">{{ status }}</p></section>
</template>
<style scoped>g[role=button] { cursor: pointer; } g:focus rect { stroke-width: 3; stroke-dasharray: 5 3; }</style>
