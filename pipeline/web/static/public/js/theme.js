/* The `sectorTrace` ECharts theme.
 *
 * Registered once and passed to every echarts.init call, so a chart added
 * later cannot quietly arrive in ECharts' default blue-on-white and break the
 * page it sits in.
 */
'use strict';

export const PALETTE = [
  '#21d4d0', '#fbbf24', '#4ade80', '#fb7185',
  '#a78bfa', '#4f8cff', '#f472b6',
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
  textStyle: { fontFamily: 'Manrope, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif' },
  title: { textStyle: { color: '#f4f8ff' }, subtextStyle: { color: '#b2c0d3' } },
  legend: { textStyle: { color: '#b2c0d3' }, inactiveColor: '#52657d' },
  tooltip: {
    backgroundColor: 'rgba(8, 17, 31, 0.94)',
    borderColor: '#21d4d0',
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
  pie: { itemStyle: { borderColor: '#08111f', borderWidth: 2 } },
  visualMap: { textStyle: { color: '#b2c0d3' } },
  dataZoom: {
    borderColor: '#21262d',
    textStyle: { color: '#8b949e' },
    handleStyle: { color: '#21d4d0' },
  },
};

let registered = false;

export function registerTheme() {
  if (registered || !window.echarts) return;
  window.echarts.registerTheme('sectorTrace', THEME);
  window.echarts.registerTheme('sectorTraceLight', {
    ...THEME,
    title: { textStyle: { color: '#132238' }, subtextStyle: { color: '#455a73' } },
    legend: { textStyle: { color: '#455a73' }, inactiveColor: '#93a3b8' },
    tooltip: { ...THEME.tooltip, backgroundColor: 'rgba(255,255,255,.97)', textStyle: { color: '#132238' } },
    categoryAxis: { ...AXIS, axisLine: { lineStyle: { color: '#c4d0dd' } }, axisTick: { lineStyle: { color: '#c4d0dd' } }, axisLabel: { color: '#455a73' }, splitLine: { lineStyle: { color: '#dce5ef' } } },
    valueAxis: { ...AXIS, axisLine: { lineStyle: { color: '#c4d0dd' } }, axisTick: { lineStyle: { color: '#c4d0dd' } }, axisLabel: { color: '#455a73' }, splitLine: { lineStyle: { color: '#dce5ef' } } },
  });
  registered = true;
}

const THEME_KEY = 'sectortrace-theme';

export function applyPortalTheme(choice = 'system') {
  const theme = ['system', 'light', 'dark'].includes(choice) ? choice : 'system';
  const root = document.documentElement;
  root.dataset.bsTheme = theme === 'system'
    ? (window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark')
    : theme;
  root.dataset.portalTheme = theme;
  const select = document.querySelector('#theme-select');
  if (select) select.value = theme;
  window.dispatchEvent(new CustomEvent('portalthemechange'));
}

export function initPortalTheme() {
  let choice = 'system';
  try { choice = localStorage.getItem(THEME_KEY) || choice; } catch (e) { /* private mode */ }
  applyPortalTheme(choice);
  document.querySelector('#theme-select')?.addEventListener('change', (event) => {
    const next = event.target.value;
    try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* private mode */ }
    applyPortalTheme(next);
  });
  window.matchMedia?.('(prefers-color-scheme: light)').addEventListener('change', () => {
    if (document.documentElement.dataset.portalTheme === 'system') applyPortalTheme('system');
  });
}
