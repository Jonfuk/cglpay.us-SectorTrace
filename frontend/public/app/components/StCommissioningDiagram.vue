<script setup lang="ts">
import { linkHorizontal } from 'd3-shape'
import type { ConnectionEdge, ConnectionNode } from '~/types/connections'
import { connectionName, drawableConnections } from '~/lib/connections'
import { downloadAnnotatedChart } from '~/lib/chart-export'
const props = defineProps<{ edges: ConnectionEdge[]; nodes: ConnectionNode[]; selected: string; annotation: string }>()
const emit = defineEmits<{ inspect: [id: string, event: Event]; node: [id: string, event: Event] }>()
const root = ref<HTMLElement | null>(null)
const svg = ref<SVGSVGElement | null>(null)
const colour = useColorMode()
const palette = ref({ text: '#EFEFEF', panel: '#141414', line: '#9A9A9A', selected: '#34D1BF', border: '#7C7C7C' })
const status = ref('')
const plotted = computed(() => drawableConnections(props.edges, props.nodes))
const label = (id: string) => connectionName(props.nodes, id)
const sides = computed(() => {
  const place = (key: 'subject_entity_id' | 'object_entity_id', x: number) => {
    const ids = [...new Set(plotted.value.map(edge => edge[key]!))].sort((a, b) => label(a).localeCompare(label(b), 'en-GB') || a.localeCompare(b))
    let y = 60
    return ids.map(id => { const count = plotted.value.filter(edge => edge[key] === id).length; const height = Math.max(72, count * 18 + 34); const node = { id, x, y, height }; y += height + 22; return node })
  }
  return { authorities: place('subject_entity_id', 20), providers: place('object_entity_id', 570) }
})
const height = computed(() => Math.max(230, ...[...sides.value.authorities, ...sides.value.providers].map(node => node.y + node.height + 25)))
const path = linkHorizontal<{ source: [number, number]; target: [number, number] }, [number, number]>()
const links = computed(() => plotted.value.map((edge, index) => {
  const position = (key: 'subject_entity_id' | 'object_entity_id', column: typeof sides.value.authorities, x: number): [number, number] => {
    const node = column.find(node => node.id === edge[key])!
    const preceding = plotted.value.slice(0, index).filter(row => row[key] === edge[key]).length
    const count = plotted.value.filter(row => row[key] === edge[key]).length
    return [x, node.y + 22 + (node.height - 36) * (preceding + 1) / (count + 1)]
  }
  const source = position('subject_entity_id', sides.value.authorities, 280)
  const target = position('object_entity_id', sides.value.providers, 570)
  return { edge, y: (source[1] + target[1]) / 2, d: path({ source, target }) ?? '' }
}))
async function updateColours() { await nextTick(); if (!root.value) return; const css = getComputedStyle(root.value); palette.value = { text: css.getPropertyValue('--text-primary').trim(), panel: css.getPropertyValue('--surface-panel').trim(), line: css.getPropertyValue('--text-muted').trim(), selected: css.getPropertyValue('--interactive-secondary').trim(), border: css.getPropertyValue('--border-control').trim() } }
onMounted(updateColours)
watch(() => colour.value, updateColours)
async function download(format: 'svg' | 'png') {
  if (!root.value || !svg.value) return
  try { const clone = svg.value.cloneNode(true) as SVGSVGElement; clone.setAttribute('width', String(svg.value.clientWidth)); clone.setAttribute('height', String(svg.value.clientHeight)); await downloadAnnotatedChart({ root: root.value, svgUrl: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(new XMLSerializer().serializeToString(clone))}`, title: 'Commissioning relationships', annotation: props.annotation, filename: 'commissioning-displayed-diagram', format }); status.value = 'Annotated diagram downloaded. Keep the reference manifest with this image.' }
  catch { status.value = 'The diagram export could not be created. Data and reference exports remain available.' }
}
</script>
<template>
  <section class="space-y-3" aria-label="Commissioning relationship diagram"><p class="atlas-footnote">{{ plotted.length }} of {{ edges.length }} edges in this diagram group can be placed using unambiguous authority and provider records. Other edges remain in the data view. Line width and position do not represent spending, importance or strength.</p><div class="overflow-x-auto" tabindex="0" role="region" aria-label="Scrollable commissioning diagram"><div ref="root" style="min-width: 850px"><svg ref="svg" :viewBox="`0 0 850 ${height}`" width="100%" :height="height" role="group" aria-label="Authorities awarded to providers" font-family="Arial, sans-serif" font-size="14"><text x="20" y="28" :fill="palette.text">Authorities</text><text x="570" y="28" :fill="palette.text">Providers</text>
    <path v-for="(link, index) in links" :key="`${link.edge.relationship_id}:${index}`" :d="link.d" fill="none" :stroke="selected === link.edge.relationship_id ? palette.selected : palette.line" :stroke-dasharray="selected === link.edge.relationship_id ? '8 4' : undefined" stroke-width="3" role="button" tabindex="0" :aria-pressed="selected === link.edge.relationship_id" :aria-label="`Inspect relationship ${link.edge.relationship_id}: ${label(link.edge.subject_entity_id!)} awarded to ${label(link.edge.object_entity_id!)}`" @click="emit('inspect', link.edge.relationship_id!, $event)" @keydown.enter="emit('inspect', link.edge.relationship_id!, $event)" @keydown.space.prevent="emit('inspect', link.edge.relationship_id!, $event)"><title>{{ link.edge.relationship_id }} · {{ link.edge.valid_from ?? 'Start date not supplied' }} · {{ link.edge.valid_to ?? 'End date not supplied' }}</title></path>
    <g v-for="(link, index) in links" :key="`label:${index}`" aria-hidden="true" pointer-events="none"><rect x="413" :y="link.y - 8" width="24" height="16" rx="3" :fill="palette.panel" /><text x="425" :y="link.y + 4" text-anchor="middle" font-size="11" :fill="palette.text">{{ index + 1 }}</text></g>
    <g v-for="node in [...sides.authorities, ...sides.providers]" :key="node.id" role="button" tabindex="0" :aria-label="`Inspect graph entity ${label(node.id)}`" @click="emit('node', node.id, $event)" @keydown.enter="emit('node', node.id, $event)" @keydown.space.prevent="emit('node', node.id, $event)"><rect :x="node.x" :y="node.y" width="260" :height="node.height" rx="4" :fill="palette.panel" :stroke="palette.border" /><text :x="node.x + 12" :y="node.y + 23" :fill="palette.text"><tspan v-for="(line, index) in (label(node.id).match(/.{1,30}(?:\s|$)|.{1,30}/g) ?? []).slice(0, 2)" :key="index" :x="node.x + 12" :dy="index ? 19 : 0">{{ line.trim() }}</tspan></text><title>{{ label(node.id) }} · {{ node.id }}</title></g>
  </svg></div></div><div class="flex flex-wrap gap-2"><button type="button" class="atlas-button" @click="download('svg')">Download annotated diagram SVG</button><button type="button" class="atlas-button" @click="download('png')">Download annotated diagram PNG</button></div><p role="status">{{ status }}</p></section>
</template>
<style scoped>path[role=button], g[role=button] { cursor: pointer; } path:focus { stroke-dasharray: 5 3; outline: none; } g:focus rect { stroke-width: 3; stroke-dasharray: 5 3; } </style>
