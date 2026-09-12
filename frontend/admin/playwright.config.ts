import { existsSync } from 'node:fs'
import { defineConfig, devices } from '@playwright/test'

// The admin smoke gate uses the generated static app and the same dependency-
// free server as the Lighthouse harness. Keeping this config in the admin app
// makes its browser coverage independently runnable and preserves the physical
// public/admin build boundary.
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
    baseURL: 'http://localhost:4174/admin/',
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
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
  webServer: {
    command: 'node ../scripts/serve-static.mjs',
    port: 4174,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
    env: { PORT: '4174' },
  },
})
