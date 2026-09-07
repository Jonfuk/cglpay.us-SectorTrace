<script setup lang="ts">
import { init, use, type EChartsType } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { AriaComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import type { ComparisonMeasure, ComparisonPoint } from '~/lib/comparison-chart'
import { connectionText } from '~/lib/connections'
import { downloadAnnotatedChart } from '~/lib/chart-export'
use([BarChart, AriaComponent, GridComponent, LegendComponent, TooltipComponent, SVGRenderer])
const props = defineProps<{ points: ComparisonPoint[]; measures: ComparisonMeasure[]; title: string; unit: string; annotation: string; selectedIndex?: number }>()
const emit = defineEmits<{ inspect: [index: number, event?: Event] }>()
const root = ref<HTMLElement | null>(null)
const ready = ref(false)
const failure = ref(false)
const status = ref('')
const colour = useColorMode()
let chart: EChartsType | null = null
let observer: ResizeObserver | undefined
function describe(point: ComparisonPoint) { return `Record ${point.index + 1}. Period ${point.period}. ${props.measures.map((measure, index) => `${measure.label}: ${connectionText(point.values[index])}`).join('. ')}. Source ${connectionText(point.row.source_url)}. Retrieved ${connectionText(point.row.retrieved_at)}. Payload hash ${connectionText(point.row.payload_sha256)}. Allocation status ${connectionText(point.row.allocation_status)}.` }
function draw() {
  if (!root.value || !chart) return
  const css = getComputedStyle(root.value)
  const text = css.getPropertyValue('--text-primary').trim()
  const border = css.getPropertyValue('--border-subtle').trim()
  const colours = [css.getPropertyValue('--interactive-primary').trim(), css.getPropertyValue('--interactive-secondary').trim()]
  chart.setOption({ animation: false, aria: { enabled: true, decal: { show: true }, label: { description: `${props.title}. ${props.unit}. Independent peer scale. Exact values and source inspection are in the record table.` } }, textStyle: { color: text, fontFamily: 'Manrope, sans-serif' },
    grid: { left: 125, right: 25, top: 70, bottom: 45 }, legend: { selectedMode: false, textStyle: { color: text }, top: 5 },
    xAxis: { type: 'value', minInterval: props.unit === 'Published notices' ? 1 : undefined, name: props.unit, nameLocation: 'middle', nameGap: 28, nameTextStyle: { color: text }, axisLabel: { color: text }, splitLine: { lineStyle: { color: border } }, min: Math.min(0, ...props.points.flatMap(point => point.values.filter((value): value is number => value !== null))) },
    yAxis: { type: 'category', inverse: true, data: props.points.map(point => `${point.period}\nRecord ${point.index + 1}`), axisLabel: { color: text, width: 112, overflow: 'truncate' }, axisLine: { lineStyle: { color: border } } },
    tooltip: { renderMode: 'richText', trigger: 'item', formatter: (params: unknown) => { const point = props.points[(params as { dataIndex: number }).dataIndex]; return point ? describe(point) : '' } },
    series: props.measures.map((measure, index) => ({ id: measure.key, name: measure.label, type: 'bar', barMaxWidth: 22, data: props.points.map(point => ({ value: point.values[index], itemStyle: { borderColor: text, borderWidth: point.index === props.selectedIndex ? 3 : 0 } })), itemStyle: { color: colours[index % colours.length], decal: index ? { symbol: 'rect', dashArrayX: [1, 0], dashArrayY: [3, 4], rotation: -Math.PI / 4 } : undefined } })),
  }, { notMerge: true })
}
onMounted(() => { try { if (!root.value) return; chart = init(root.value, undefined, { renderer: 'svg' }); chart.on('click', (event: { dataIndex?: number }) => { const point = props.points[event.dataIndex ?? -1]; if (point) emit('inspect', point.index) }); draw(); ready.value = true; observer = new ResizeObserver(() => chart?.resize()); observer.observe(root.value) } catch { failure.value = true } })
watch(() => [props.points, props.measures, props.selectedIndex, colour.value], async () => { await nextTick(); draw(); chart?.resize() })
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose(); chart = null })
async function download(format: 'svg' | 'png') { if (!chart || !root.value) return; try { await downloadAnnotatedChart({ root: root.value, svgUrl: chart.getDataURL({ type: 'svg' }), title: props.title, annotation: `Unit: ${props.unit}. Each peer has an independent scale including zero. Repeated periods remain separate records. Missing numeric values are not zero. ${props.annotation}\n${props.points.map(describe).join('\n')}`, filename: 'comparison-displayed-peer-chart', format }); status.value = 'Annotated peer chart downloaded.' } catch { status.value = 'The chart image could not be exported. Source-reference downloads remain available.' } }
</script>
<template><section class="space-y-3" :aria-label="`${title} chart`"><h4>{{ title }}</h4><p class="atlas-footnote">{{ unit }}. This peer has an independent scale including zero. Compare exact values, not bar lengths across panels. Each record keeps its own period.</p><p v-if="failure" role="status">The chart could not load. The record table remains available.</p><div ref="root" role="img" :aria-label="`${title}. ${unit}. The record table provides exact values and sources.`" :style="{ height: `${Math.max(260, points.length * measures.length * 30 + 115)}px` }" /><div class="flex flex-wrap gap-2"><button v-for="point in points" :key="point.index" :aria-pressed="point.index === selectedIndex" type="button" class="atlas-button" @click="emit('inspect', point.index, $event)">Inspect plotted record {{ point.index + 1 }}</button></div><div class="flex gap-2"><button type="button" class="atlas-button" :disabled="!ready || failure" @click="download('svg')">Download peer chart SVG</button><button type="button" class="atlas-button" :disabled="!ready || failure" @click="download('png')">Download peer chart PNG</button></div><p role="status">{{ status }}</p></section></template>
