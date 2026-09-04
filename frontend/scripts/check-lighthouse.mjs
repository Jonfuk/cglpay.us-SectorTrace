// Assert the Phase 6 pinned mobile user-experience thresholds from raw
// Lighthouse reports. Values are milliseconds except CLS, which is unitless.
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(fileURLToPath(new URL('..', import.meta.url)))
const reports = resolve(root, '.lighthouse')
const limits = {
  'largest-contentful-paint': 2500,
  'cumulative-layout-shift': 0.1,
  'total-blocking-time': 200,
}
const names = ['public-overview', 'public-places', 'admin-overview']
const failures = []

for (const name of names) {
  const path = resolve(reports, `${name}.json`)
  if (!existsSync(path)) {
    failures.push(`${name}: report missing`)
    continue
  }
  const report = JSON.parse(readFileSync(path, 'utf8'))
  for (const [audit, limit] of Object.entries(limits)) {
    const value = report.audits?.[audit]?.numericValue
    const unit = audit === 'cumulative-layout-shift' ? '' : ' ms'
    if (!Number.isFinite(value)) {
      failures.push(`${name} ${audit}: numeric value missing`)
      continue
    }
    const result = value <= limit ? 'PASS' : 'FAIL'
    console.log(`${result} ${name} ${audit}: ${value.toFixed(3)} <= ${limit}${unit}`)
    if (value > limit) failures.push(`${name} ${audit}: ${value} > ${limit}`)
  }
}

if (failures.length) {
  console.error('\nLighthouse gate failed:')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}
console.log('Lighthouse gate passed.')
