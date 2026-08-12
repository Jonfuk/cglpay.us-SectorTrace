/* The `sectorTrace` ECharts theme.
 *
 * Registered once and passed to every echarts.init call, so a chart added
 * later cannot quietly arrive in ECharts' default blue-on-white and break the
 * page it sits in.
 */
'use strict';

export const PALETTE = [
  '#38bdf8', '#f59e0b', '#34d399', '#f87171',
  '#a78bfa', '#fb923c', '#e879f9',
];

// Paired with the palette by index. Colour is never the only difference
// between two series: a reader who cannot separate the teal line from the
// green one can still separate a circle from a triangle.
export const SYMBOLS = [
  'circle', 'triangle', 'rect', 'diamond', 'roundRect', 'pin', 'arrow',
];

const AXIS = {
  axisLine: { lineStyle: { color: '#1e293b' } },
  axisTick: { lineStyle: { color: '#1e293b' } },
  axisLabel: { color: '#64748b' },
  splitLine: { lineStyle: { color: '#1e293b' } },
};

export const THEME = {
  color: PALETTE,
  backgroundColor: 'transparent',
  textStyle: { fontFamily: 'Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif' },
  title: { textStyle: { color: '#e6edf3' }, subtextStyle: { color: '#8b949e' } },
  legend: { textStyle: { color: '#94a3b8' }, inactiveColor: '#484f58' },
  tooltip: {
    backgroundColor: 'rgba(13, 17, 23, 0.92)',
    borderColor: '#38bdf8',
    borderWidth: 1,
    textStyle: { color: '#e6edf3' },
    extraCssText: 'backdrop-filter: blur(6px); box-shadow: 0 8px 28px rgba(0,0,0,0.6);',
  },
  grid: { borderColor: '#1e293b', containLabel: true, left: 12, right: 20, top: 40, bottom: 12 },
  categoryAxis: AXIS,
  valueAxis: AXIS,
  timeAxis: AXIS,
  logAxis: AXIS,
  line: { symbolSize: 7, lineStyle: { width: 2 } },
  bar: { itemStyle: { borderRadius: [3, 3, 0, 0] } },
  pie: { itemStyle: { borderColor: '#0d1117', borderWidth: 2 } },
  visualMap: { textStyle: { color: '#8b949e' } },
  dataZoom: {
    borderColor: '#21262d',
    textStyle: { color: '#8b949e' },
    handleStyle: { color: '#38bdf8' },
  },
};

let registered = false;

export function registerTheme() {
  if (registered || !window.echarts) return;
  window.echarts.registerTheme('sectorTrace', THEME);
  registered = true;
}
