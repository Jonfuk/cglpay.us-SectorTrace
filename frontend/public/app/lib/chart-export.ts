// Export annotations belong to the image itself, so a copied chart retains its
// evidence window and caveats. Source strings enter SVG only as text nodes.
export async function downloadAnnotatedChart(options: { svgUrl: string; root: HTMLElement; title: string; annotation: string; filename: string; format: 'svg' | 'png' }) {
  const { root, title, annotation, filename, format } = options
  const source = new DOMParser().parseFromString(decodeURIComponent(options.svgUrl.slice(options.svgUrl.indexOf(',') + 1)), 'image/svg+xml').documentElement
  if (source.localName !== 'svg') throw new Error('Chart SVG unavailable')
  const width = Math.max(640, Math.round(root.clientWidth))
  const chartHeight = Math.round(root.clientHeight)
  const ns = 'http://www.w3.org/2000/svg'
  const output = document.createElementNS(ns, 'svg')
  const lines = (annotation.match(/.{1,95}(?:\s|$)|.{1,95}/g) ?? []).map(line => line.trim())
  const height = chartHeight + 70 + lines.length * 19
  output.setAttribute('width', String(width)); output.setAttribute('height', String(height)); output.setAttribute('viewBox', `0 0 ${width} ${height}`)
  const styles = getComputedStyle(root)
  const background = document.createElementNS(ns, 'rect')
  background.setAttribute('width', '100%'); background.setAttribute('height', '100%'); background.setAttribute('fill', styles.getPropertyValue('--surface-panel').trim() || '#070707'); output.append(background)
  function textLine(value: string, y: number, size: number) {
    const line = document.createElementNS(ns, 'text')
    line.setAttribute('x', '18'); line.setAttribute('y', String(y)); line.setAttribute('font-size', String(size)); line.setAttribute('font-family', 'Arial, sans-serif'); line.setAttribute('fill', styles.getPropertyValue('--text-primary').trim() || '#EFEFEF'); line.textContent = value; output.append(line)
  }
  textLine(title, 26, 18)
  source.setAttribute('y', '40'); source.setAttribute('width', String(width)); output.append(source)
  lines.forEach((line, index) => textLine(line, chartHeight + 60 + index * 19, 12))
  const serialized = new XMLSerializer().serializeToString(output)
  let blob = new Blob([serialized], { type: 'image/svg+xml' })
  if (format === 'png') {
    // The production image policy allows data URLs, but not blob images.
    const picture = new Image()
    picture.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(serialized)}`
    await picture.decode()
    const canvas = document.createElement('canvas')
    canvas.width = width * 2; canvas.height = height * 2
    const context = canvas.getContext('2d')
    if (!context) throw new Error('Canvas unavailable')
    context.drawImage(picture, 0, 0, canvas.width, canvas.height)
    blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('Image unavailable')), 'image/png'))
  }
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url; link.download = `${filename}.${format}`; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
