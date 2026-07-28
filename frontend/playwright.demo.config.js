import { defineConfig } from '@playwright/test'

const baseURL = process.env.DEMO_BASE_URL || 'http://192.168.48.133:3000'

export default defineConfig({
  testDir: './tests/demo',
  timeout: 180_000,
  expect: { timeout: 15_000 },
  workers: 1,
  retries: 0,
  fullyParallel: false,
  reporter: [['list'], ['html', { outputFolder: 'demo-test-report', open: 'never' }]],
  use: {
    baseURL,
    browserName: 'chromium',
    headless: true,
    viewport: { width: 2560, height: 1440 },
    deviceScaleFactor: 1,
    colorScheme: 'light',
    video: 'on',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: { args: ['--disable-gpu'], env: { ...process.env, LD_PRELOAD: '' } },
  },
})
