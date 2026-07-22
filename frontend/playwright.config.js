import { defineConfig, devices } from '@playwright/test'

const port = Number(process.env.PLAYWRIGHT_PORT || 3000)
const baseURL = `http://127.0.0.1:${port}`

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 8_000 },
  reporter: [['list']],
  use: {
    baseURL,
    browserName: 'chromium',
    launchOptions: {
      args: ['--disable-gpu'],
      env: {
        ...process.env,
        LD_PRELOAD: '',
      },
    },
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { ...devices['iPhone 13'], viewport: { width: 390, height: 844 } } },
  ],
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${port} --strictPort`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
  },
})
