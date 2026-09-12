<script setup lang="ts">
import { init, use, type EChartsType } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { AriaComponent, BrushComponent, GridComponent, TooltipComponent, ToolboxComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import type { CountObservation } from '~/lib/notice-counts'
import { selectedYears } from '~/lib/notice-counts'
use([AriaComponent, BarChart, GridComponent, TooltipComponent, BrushComponent, ToolboxComponent, SVGRenderer])
const props = defineProps<{ rows: CountObservation[]; title: string; horizontal?: boolean; yearBrush?: boolean; selected?: string; annotation: string }>()
const emit = defineEmits<{ select: [key: string]; years: [from: string, to: string] }>()
const root = ref<HTMLElement | null>(null)
const unavailable = ref(false)
const exportStatus = ref('')
const colour = useColorMode()
let chart: EChartsType | null = null
let observer: ResizeObserver | null = null
let disposed = false
function draw() {
  if (!chart || !root.value) return
  const styles = getComputedStyle(root.value)
  const text = styles.getPropertyValue('--text-primary').trim() || '#EFEFEF'
  const border = styles.getPropertyValue('--border-subtle').trim() || '#777'
  const category = { type: 'category' as const, data: props.rows.map(row => row.label), axisLabel: { color: text, width: props.horizontal ? 150 : 65, overflow: 'truncate' as const }, axisLine: { lineStyle: { color: border } } }
  const amount = { type: 'value' as const, min: 0, minInterval: 1, name: 'Notices', axisLabel: { color: text }, nameTextStyle: { color: text }, splitLine: { lineStyle: { color: border } } }
  chart.setOption({ aria: { enabled: true, label: { description: `${props.title}. Published notice counts. Exact values and inspection controls follow in the table.` } }, animation: false, textStyle: { fontFamily: 'Manrope, sans-serif', color: text }, grid: { left: props.horizontal ? 175 : 60, right: 30, top: props.yearBrush ? 62 : 40, bottom: 48 }, tooltip: { trigger: 'item', renderMode: 'richText', formatter: (item: { dataIndex?: number }) => { const row = props.rows[item.dataIndex ?? -1]; return row ? `${row.label}\n${row.value ?? 'Not supplied'} notices` : '' } }, xAxis: props.horizontal ? amount : category, yAxis: props.horizontal ? { ...category, inverse: true } : amount, toolbox: props.yearBrush ? { feature: { brush: { type: ['lineX', 'clear'], title: { lineX: 'Select publication years', clear: 'Clear year selection' } } } } : undefined, brush: props.yearBrush ? { xAxisIndex: 0, brushMode: 'single', throttleType: 'debounce', throttleDelay: 300 } : undefined, series: [{ id: 'notice-counts', type: 'bar', name: 'Published notices', barMaxWidth: 36, data: props.rows.map(row => ({ value: row.value, itemStyle: { color: row.key === props.selected ? '#34D1BF' : '#3454D1' } })) }] }, { notMerge: true })
}
onMounted(async () => {
  try {
    await document.fonts.ready
    if (disposed || !root.value) return
    chart = init(root.value, undefined, { renderer: 'svg' })
    chart.on('click', (event: { dataIndex?: number }) => { const row = props.rows[event.dataIndex ?? -1]; if (row) emit('select', row.key) })
    chart.on('brushselected', (raw: unknown) => {
      const event = raw as { batch?: Array<{ selected?: Array<{ dataIndex?: number[] }> }> }
      if (!props.yearBrush) return
      const range = selectedYears(props.rows, event.batch?.[0]?.selected?.[0]?.dataIndex ?? [])
      if (range) emit('years', range[0], range[1])
    })
    draw()
    observer = new ResizeObserver(() => chart?.resize())
    observer.observe(root.value)
  } catch { unavailable.value = true }
})
watch(() => [props.rows, props.horizontal, props.selected, props.yearBrush, colour.value], async () => { await nextTick(); draw(); chart?.resize() })
onBeforeUnmount(() => { disposed = true; observer?.disconnect(); chart?.dispose(); chart = null })
function selectYears() { chart?.dispatchAction({ type: 'takeGlobalCursor', key: 'brush', brushOption: { brushType: 'lineX', brushMode: 'single' } }) }
// The downloaded SVG includes the displayed filter/scope annotation. The chart
// library owns the drawing, and source text is added only through text nodes.
async function download(format: 'svg' | 'png') {
  if (!chart || !root.value) return
  const raw = chart.getDataURL({ type: 'svg' })
  const source = new DOMParser().parseFromString(decodeURIComponent(raw.slice(raw.indexOf(',') + 1)), 'image/svg+xml').documentElement
  const width = Math.max(640, Math.round(root.value.clientWidth))
  const chartHeight = Math.round(root.value.clientHeight)
  const ns = 'http://www.w3.org/2000/svg'
  const output = document.createElementNS(ns, 'svg')
  const lines = (props.annotation.match(/.{1,95}(?:\s|$)|.{1,95}/g) ?? []).map(line => line.trim())
  output.setAttribute('width', String(width)); output.setAttribute('height', String(chartHeight + 70 + lines.length * 19)); output.setAttribute('viewBox', `0 0 ${width} ${chartHeight + 70 + lines.length * 19}`)
  const bg = document.createElementNS(ns, 'rect'); bg.setAttribute('width', '100%'); bg.setAttribute('height', '100%'); bg.setAttribute('fill', getComputedStyle(root.value).getPropertyValue('--surface-panel').trim() || '#070707'); output.append(bg)
  function textLine(text: string, y: number, size: number) { const line = document.createElementNS(ns, 'text'); line.setAttribute('x', '18'); line.setAttribute('y', String(y)); line.setAttribute('font-size', String(size)); line.setAttribute('font-family', 'Arial, sans-serif'); line.setAttribute('fill', getComputedStyle(root.value!).getPropertyValue('--text-primary').trim() || '#EFEFEF'); line.textContent = text; output.append(line) }
  textLine(props.title, 26, 18)
  source.setAttribute('y', '40'); source.setAttribute('width', String(width)); output.append(source)
  lines.forEach((line, index) => textLine(line, chartHeight + 60 + index * 19, 12))
  const serialized = new XMLSerializer().serializeToString(output)
  const svgBlob = new Blob([serialized], { type: 'image/svg+xml' })
  let downloadBlob = svgBlob
  if (format === 'png') {
    // Production permits data images but not blob images. Keep rasterisation
    // inside that policy instead of requiring a server-header change.
    const sourceUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(serialized)}`
    try {
      const picture = new Image()
      picture.src = sourceUrl
      await picture.decode()
      const canvas = document.createElement('canvas')
      canvas.width = width * 2; canvas.height = (chartHeight + 70 + lines.length * 19) * 2
      const context = canvas.getContext('2d')
      if (!context) throw new Error('Canvas unavailable')
      context.drawImage(picture, 0, 0, canvas.width, canvas.height)
      downloadBlob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Image unavailable')), 'image/png'))
    } catch { exportStatus.value = 'PNG export could not be created. The SVG and aggregate JSON remain available.'; return }
  }
  const url = URL.createObjectURL(downloadBlob)
  const link = document.createElement('a'); link.href = url; link.download = `notice-counts-annotated.${format}`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  exportStatus.value = 'Annotated chart downloaded. The aggregate JSON includes the source limitations and filter scope.'
}
</script>
<template>
  <div><p v-if="unavailable" role="status">The chart could not load. All returned categories remain in the data table.</p><button v-if="yearBrush" class="atlas-button" type="button" @click="selectYears">Select year range on chart</button><div ref="root" role="img" :aria-label="`${title}. Published notice counts. Exact values and inspection controls follow in the table.`" :style="{ height: `${horizontal ? Math.max(320, rows.length * 38 + 90) : 360}px` }" /><div class="flex flex-wrap gap-2"><button class="atlas-button" type="button" :disabled="unavailable" @click="download('png')">Download annotated chart PNG</button><button class="atlas-button" type="button" :disabled="unavailable" @click="download('svg')">Download annotated chart SVG</button></div><p role="status">{{ exportStatus }}</p><p v-if="yearBrush" class="atlas-footnote">The chart’s year-selection tool applies publication year bounds. The publication year fields above provide the same action by keyboard.</p></div>
</template>
