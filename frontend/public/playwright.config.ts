import { existsSync } from 'node:fs'
import { defineConfig, devices } from '@playwright/test'

// Playwright smoke gate for the built public app. It serves the generated
// `dist/` (no API) and drives it in a real Chromium to prove the shell boots
// with no console errors or hydration/interop warnings — the check that
// catches a broken Vapor/VDOM interop or a bad build that typecheck and unit
// tests miss.
//
// Prefer a Chromium pre-installed in the image (dev/CI images that bundle one),
// pointing at its binary explicitly so the exact @playwright/test version does
// not need a matching managed download. When that binary is absent (e.g. a
// stock GitHub runner where CI runs `playwright install chromium`), fall back to
// Playwright's managed browser by leaving executablePath unset.
const PINNED = process.env.PLAYWRIGHT_CHROMIUM_PATH
  || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const CHROME = existsSync(PINNED) ? PINNED : undefined

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  reporter: 'line',
  use: {
    baseURL: 'http://localhost:4173',
    trace: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        ...(CHROME ? { launchOptions: { executablePath: CHROME } } : {}),
      },
    },
  ],
  webServer: {
    command: 'node scripts/serve-dist.mjs',
    port: 4173,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
})
