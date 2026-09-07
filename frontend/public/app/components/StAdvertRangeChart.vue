<script setup lang="ts">
import { init, use, type EChartsType } from 'echarts/core'
import { CustomChart, type CustomSeriesOption } from 'echarts/charts'
import { AriaComponent, GridComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import { advertRanges, drawableAdvert } from '~/lib/advert-ranges'
import { downloadAnnotatedChart } from '~/lib/chart-export'
import { payRecordKey, type PayLens, type PayRow } from '~/lib/pay-lenses'

use([CustomChart, AriaComponent, GridComponent, TooltipComponent, SVGRenderer])
const props = defineProps<{ rows: PayRow[]; lens: PayLens; selected: string; annotation: string }>()
const emit = defineEmits<{ inspect: [row: PayRow, event?: Event] }>()
const ranges = computed(() => advertRanges(props.rows))
const plotted = computed(() => ranges.value.filter(drawableAdvert))
const root = ref<HTMLElement | null>(null)
const unavailable = ref(false)
const ready = ref(false)
const exportStatus = ref('')
const colour = useColorMode()
const title = 'What annual pay range does each advert state?'
const label = (row: PayRow) => String(row.job_title ?? 'Advert title not supplied')
let chart: EChartsType | null = null
let observer: ResizeObserver | null = null
let disposed = false

function draw() {
  if (!chart || !root.value) return
  const styles = getComputedStyle(root.value)
  const text = styles.getPropertyValue('--text-primary').trim() || '#EFEFEF'
  const border = styles.getPropertyValue('--border-subtle').trim() || '#777'
  const surface = styles.getPropertyValue('--surface-panel').trim() || '#070707'
  const series: CustomSeriesOption = {
    id: 'annual-advert-ranges', type: 'custom', name: 'Annual advertised bounds', clip: true,
    // A one-bound record repeats its drawing coordinate only. Its missing source
    // bound remains null in the adapter, data table, tooltip and exports.
    data: plotted.value.map(item => [item.lower ?? item.upper!, item.upper ?? item.lower!, item.index]),
    encode: { x: [0, 1], y: 2 },
    renderItem: (params, api) => {
      const item = plotted.value[params.dataIndex]
      if (!item) return
      const left = api.coord!([api.value(0), api.value(2)])
      const right = api.coord!([api.value(1), api.value(2)])
      const x = left[0]!, y = left[1]!, end = right[0]!
      const selected = payRecordKey(props.lens, item.row) === props.selected
      const stroke = selected ? '#D1345B' : text
      if (item.state === 'single') return { type: 'circle', shape: { cx: x, cy: y, r: selected ? 7 : 5 }, style: { fill: stroke } }
      if (item.state === 'lower-only' || item.state === 'upper-only') return { type: 'polygon', shape: { points: [[x, y - 7], [x + 7, y], [x, y + 7], [x - 7, y]] }, style: { stroke, fill: surface, lineWidth: selected ? 3 : 2 } }
      return { type: 'group', children: [
        { type: 'line', shape: { x1: x, y1: y, x2: end, y2: y }, style: { stroke, lineWidth: selected ? 4 : 2 } },
        { type: 'line', shape: { x1: x, y1: y - 6, x2: x, y2: y + 6 }, style: { stroke, lineWidth: 2 } },
        { type: 'line', shape: { x1: end, y1: y - 6, x2: end, y2: y + 6 }, style: { stroke, lineWidth: 2 } },
      ] }
    },
  }
  chart.setOption({ animation: false, aria: { enabled: true, label: { description: `${title} Annual amounts in pounds as parsed from the adverts. Every displayed advert, including undrawn observations, has a labelled inspection control below.` } }, textStyle: { fontFamily: 'Manrope, sans-serif', color: text },
    grid: { left: root.value.clientWidth < 600 ? 45 : 180, right: 32, top: 48, bottom: 55 },
    xAxis: { type: 'value', name: 'Published annual amount (£)', nameLocation: 'middle', nameGap: 32, nameTextStyle: { color: text }, axisLabel: { color: text }, splitLine: { lineStyle: { color: border } } },
    yAxis: { type: 'category', inverse: true, data: ranges.value.map(item => `${item.index + 1}. ${label(item.row)}`), axisLabel: { color: text, width: root.value.clientWidth < 600 ? 24 : 155, overflow: 'truncate' }, axisLine: { lineStyle: { color: border } }, axisTick: { show: false } },
    tooltip: { trigger: 'item', renderMode: 'richText', formatter: (event: { dataIndex?: number }) => {
      const item = plotted.value[event.dataIndex ?? -1]
      if (!item) return ''
      return [label(item.row), `Provider: ${item.row.canonical_name ?? 'not supplied'}`, `Job reference: ${item.row.job_reference ?? 'not supplied'}`, `Published salary: ${item.row.salary_raw ?? 'not supplied'}`, `Source period: ${item.row.salary_period ?? 'not supplied'}`, `Posted: ${item.row.posted_date ?? 'not supplied'}`, item.explanation, `Source: ${item.row.source_url ?? 'not supplied'}`, `Retrieved: ${item.row.retrieved_at ?? 'not supplied'}`, 'Payload hash not supplied by this response.'].join('\n')
    } }, series: [series],
  }, { notMerge: true })
}
onMounted(async () => {
  try {
    await document.fonts.ready
    if (disposed || !root.value) return
    chart = init(root.value, undefined, { renderer: 'svg' })
    chart.on('click', (event: { dataIndex?: number }) => { const item = plotted.value[event.dataIndex ?? -1]; if (item) emit('inspect', item.row) })
    draw()
    ready.value = true
    observer = new ResizeObserver(() => { chart?.resize(); draw() })
    observer.observe(root.value)
  } catch { unavailable.value = true }
})
watch(() => [props.rows, props.selected, colour.value], async () => { await nextTick(); draw(); chart?.resize() })
onBeforeUnmount(() => { disposed = true; observer?.disconnect(); chart?.dispose(); chart = null })
async function download(format: 'svg' | 'png') {
  if (!chart || !root.value) return
  try {
    const records = ranges.value.map(item => `${item.index + 1}. ${label(item.row)}. Job reference ${item.row.job_reference ?? 'not supplied'}. Published salary: ${item.row.salary_raw ?? 'not supplied'}. Period ${item.row.salary_period ?? 'not supplied'}. Posted ${item.row.posted_date ?? 'date not supplied'}. ${item.explanation} Source: ${item.row.source_url ?? 'not supplied'}. Retrieved ${item.row.retrieved_at ?? 'date not supplied'}.`).join(' ')
    await downloadAnnotatedChart({ svgUrl: chart.getDataURL({ type: 'svg' }), root: root.value, title, annotation: `Annual source amounts in pounds. Line: two bounds. Dot: equal bounds. Open diamond: one supplied bound. Unplotted rows remain listed. ${props.annotation} ${records}`, filename: 'annual-advert-ranges-annotated', format })
    exportStatus.value = 'Annotated chart downloaded. Use the displayed rows JSON for the full source records.'
  } catch { exportStatus.value = 'The chart image could not be exported. The displayed rows JSON remains available.' }
}
</script>
<template>
  <section class="space-y-3" aria-label="Annual advertised pay chart">
    <h3>{{ title }}</h3>
    <p class="atlas-footnote">Only adverts with an explicit annual period are plotted. Amounts are in pounds, as recorded by the salary parser. A line joins two published bounds, a filled dot shows equal bounds and an open diamond marks one supplied bound. Missing and reversed bounds are explained below.</p>
    <p v-if="unavailable" role="status">The chart could not load. The advert descriptions and full data table remain available.</p>
    <p v-else-if="!ready" role="status">Loading the annual advert chart.</p>
    <p v-if="!plotted.length" role="status">No displayed advert has annual bounds that can be plotted.</p>
    <div ref="root" role="img" :aria-label="`${title} ${plotted.length} of ${rows.length} displayed adverts have drawable annual amounts. Exact amounts and source inspection follow.`" :style="{ height: `${Math.max(280, rows.length * 42 + 105)}px` }" />
    <div class="flex flex-wrap gap-2"><button type="button" class="atlas-button" :disabled="!ready || unavailable" @click="download('png')">Download annotated chart PNG</button><button type="button" class="atlas-button" :disabled="!ready || unavailable" @click="download('svg')">Download annotated chart SVG</button></div><p role="status">{{ exportStatus }}</p>
    <ol class="st-advert-descriptions" aria-label="Displayed advert ranges"><li v-for="item in ranges" :key="item.index"><button type="button" class="atlas-button" :aria-pressed="payRecordKey(lens, item.row) === selected" @click="emit('inspect', item.row, $event)">{{ item.index + 1 }}. {{ label(item.row) }}</button><p>{{ item.row.canonical_name ?? 'Provider not supplied' }} · {{ item.row.job_reference ?? 'Job reference not supplied' }} · Posted {{ item.row.posted_date ?? 'date not supplied' }}</p><p>{{ item.row.salary_raw ?? 'Published salary text not supplied' }}</p><p>{{ item.explanation }}</p></li></ol>
  </section>
</template>
<style scoped>
.st-advert-descriptions { display: grid; gap: 12px; }
.st-advert-descriptions li { padding: 12px 0; border-bottom: 1px solid var(--border-subtle); overflow-wrap: anywhere; }
.st-advert-descriptions p { font-size: 13px; margin-top: 6px; }
</style>
