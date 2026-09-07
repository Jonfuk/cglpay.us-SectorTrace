// Quantiles classify the display, not evidence. Duplicate breakpoints would
// make a MapLibre step expression invalid, including constant distributions.
export const mapRamp = ['#DDE3FA', '#B4C1EF', '#8A9FE5', '#607DDB', '#3454D1'] as const
export function mapScale(values: number[]) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b)
  if (!sorted.length) return { breaks: [] as number[], colours: [mapRamp[0]] as readonly string[] }
  const breaks = [...new Set([.2, .4, .6, .8].map(p => sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))]!))].filter(value => value > sorted[0]!)
  return { breaks, colours: mapRamp.slice(0, breaks.length + 1) as readonly string[] }
}
