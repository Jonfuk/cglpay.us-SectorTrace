<script setup lang="ts">
import { init, use, type EChartsType } from 'echarts/core'
import { CustomChart, LineChart, type CustomSeriesOption } from 'echarts/charts'
import { AriaComponent, GridComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import { fingertipsSlots, treatmentText } from '~/lib/treatment'
import { downloadAnnotatedChart } from '~/lib/chart-export'
import type { TreatmentObservation } from '~/types/treatment'

use([CustomChart, LineChart, AriaComponent, GridComponent, TooltipComponent, SVGRenderer])
const props = defineProps<{ rows: TreatmentObservation[]; title: string; unit: string; periods?: unknown; horizontal?: boolean; selected: string; annotation: string }>()
const emit = defineEmits<{ inspect: [row: TreatmentObservation, event?: Event] }>()
const plot = computed(() => props.horizontal ? { slots: props.rows.map(observation => ({ label: `${observation.period} · Publication ${treatmentText(observation.row.published_in)}`, observation })), connect: false, scaffold: false } : fingertipsSlots(props.rows, props.periods))
const root = ref<HTMLElement | null>(null)
const ready = ref(false)
const unavailable = ref(false)
const status = ref('')
const colour = useColorMode()
let chart: EChartsType | null = null
let observer: ResizeObserver | null = null
let disposed = false
const tooltip = (item: TreatmentObservation) => [item.label, `Observation period: ${item.period}`, `Publication edition: ${treatmentText(item.row.published_in)}`, `Published value: ${treatmentText(item.row.value_text ?? item.row.value)}`, `Numeric value: ${treatmentText(item.value)}`, `Unit: ${props.unit}`, item.intervalNote, `Source note: ${treatmentText(item.row.value_note)}`, `Source URL: ${treatmentText(item.row.source_url)}`, `Retrieved: ${treatmentText(item.row.retrieved_at)}`, 'Payload hash not supplied by this response.'].join('\n')

function draw() {
  if (!root.value || !chart) return
  const styles = getComputedStyle(root.value)
  const text = styles.getPropertyValue('--text-primary').trim() || '#EFEFEF'
  const border = styles.getPropertyValue('--border-subtle').trim() || '#777'
  const intervals: CustomSeriesOption = { id: 'treatment-uncertainty', type: 'custom', name: 'Published 95% bounds', clip: true,
    data: plot.value.slots.map((slot, index) => slot.observation?.interval && slot.observation.value !== null ? [index, slot.observation.lower, slot.observation.upper] : [index, null, null]), encode: props.horizontal ? { x: [1, 2], y: 0 } : { x: 0, y: [1, 2] },
    renderItem: (params, api) => {
      const item = plot.value.slots[params.dataIndex]?.observation
      if (!item?.interval || item.value === null) return
      const start = api.coord!(props.horizontal ? [item.lower!, params.dataIndex] : [params.dataIndex, item.lower!])
      const end = api.coord!(props.horizontal ? [item.upper!, params.dataIndex] : [params.dataIndex, item.upper!])
      const x1 = start[0]!, y1 = start[1]!, x2 = end[0]!, y2 = end[1]!
      const stroke = item.key === props.selected ? '#D1345B' : text
      return { type: 'group', children: [
        { type: 'line', shape: { x1, y1, x2, y2 }, style: { stroke, lineWidth: 2 } },
        { type: 'line', shape: props.horizontal ? { x1, y1: y1 - 5, x2: x1, y2: y1 + 5 } : { x1: x1 - 5, y1, x2: x1 + 5, y2: y1 }, style: { stroke, lineWidth: 2 } },
        { type: 'line', shape: props.horizontal ? { x1: x2, y1: y2 - 5, x2, y2: y2 + 5 } : { x1: x2 - 5, y1: y2, x2: x2 + 5, y2 }, style: { stroke, lineWidth: 2 } },
      ] }
    },
  }
  const category = { type: 'category', data: plot.value.slots.map(slot => slot.label), axisLabel: { color: text, width: props.horizontal ? 130 : 75, overflow: 'truncate' }, axisLine: { lineStyle: { color: border } } }
  const number = { type: 'value', name: props.unit, nameTextStyle: { color: text }, axisLabel: { color: text }, splitLine: { lineStyle: { color: border } } }
  chart.setOption({ animation: false, aria: { enabled: true, label: { description: `${props.title}. ${props.unit}. Points show published values and capped lines show supplied 95% bounds. Exact observations and source controls follow.` } }, textStyle: { color: text, fontFamily: 'Manrope, sans-serif' },
    grid: { left: props.horizontal ? 155 : 70, right: 30, top: 55, bottom: 55 },
    xAxis: props.horizontal ? number : category, yAxis: props.horizontal ? { ...category, inverse: true } : number,
    tooltip: { trigger: 'item', renderMode: 'richText', formatter: (event: { dataIndex?: number }) => { const slot = plot.value.slots[event.dataIndex ?? -1]; return slot?.observation ? tooltip(slot.observation) : `${slot?.label ?? ''}\nNo observation in this displayed series.` } },
    series: [intervals, { id: 'treatment-observations', type: 'line', name: 'Published value', connectNulls: false, showAllSymbol: true, showSymbol: true, symbol: 'circle', symbolSize: 9, smooth: false, lineStyle: { opacity: plot.value.connect ? 1 : 0, color: text }, data: plot.value.slots.map((slot, index) => ({ value: props.horizontal ? [slot.observation?.value ?? null, index] : [index, slot.observation?.value ?? null], itemStyle: { color: slot.observation?.key === props.selected ? '#D1345B' : '#3454D1' } })) }],
  }, { notMerge: true })
}
onMounted(async () => {
  try {
    await document.fonts.ready
    if (disposed || !root.value) return
    chart = init(root.value, undefined, { renderer: 'svg' })
    chart.on('click', (event: { dataIndex?: number }) => { const item = plot.value.slots[event.dataIndex ?? -1]?.observation; if (item) emit('inspect', item) })
    draw(); ready.value = true
    observer = new ResizeObserver(() => chart?.resize()); observer.observe(root.value)
  } catch { unavailable.value = true }
})
watch(() => [props.rows, props.periods, props.selected, colour.value], async () => { await nextTick(); draw(); chart?.resize() })
onBeforeUnmount(() => { disposed = true; observer?.disconnect(); chart?.dispose(); chart = null })
async function download(format: 'svg' | 'png') {
  if (!root.value || !chart) return
  try {
    const sources = props.rows.map((item, index) => `${index + 1}. ${tooltip(item).replaceAll('\n', ' ')}`).join(' ')
    await downloadAnnotatedChart({ root: root.value, svgUrl: chart.getDataURL({ type: 'svg' }), title: props.title, annotation: `Unit: ${props.unit}. Points: published values. Capped lines: numeric 95% bounds. Missing values are gaps. ${props.annotation} ${sources}`, filename: 'treatment-observations-annotated', format })
    status.value = 'Annotated chart downloaded. Keep the displayed reference manifest with it.'
  } catch { status.value = 'The chart image could not be exported. The data and reference downloads remain available.' }
}
</script>
<template>
  <section class="space-y-3" :aria-label="`${title} chart`"><h3>{{ title }}</h3><p class="atlas-footnote">Unit: {{ unit }}. Points show published values. Capped lines show both supplied numeric 95% bounds. Missing values remain gaps. An interval is not drawn when its bounds are absent or reversed.</p><p v-if="plot.scaffold" class="atlas-footnote">The horizontal axis uses only the selected catalogue’s supplied periods. A gap means there is no numeric observation in this displayed series.</p><p v-else-if="!horizontal && !plot.connect" class="atlas-footnote">These periods cannot define one unambiguous chronological line. Each returned observation is shown separately.</p><p v-if="unavailable" role="status">The chart could not load. The complete displayed observations remain in the data table.</p><p v-else-if="!ready" role="status">Loading the treatment chart.</p><div ref="root" role="img" :aria-label="`${title}. ${unit}. Exact values, bounds and source inspection follow in the table.`" :style="{ height: `${horizontal ? Math.max(300, rows.length * 44 + 110) : 370}px` }" /><div class="flex flex-wrap gap-2"><button type="button" class="atlas-button" :disabled="!ready || unavailable" @click="download('png')">Download annotated chart PNG</button><button type="button" class="atlas-button" :disabled="!ready || unavailable" @click="download('svg')">Download annotated chart SVG</button></div><p role="status">{{ status }}</p></section>
</template>
