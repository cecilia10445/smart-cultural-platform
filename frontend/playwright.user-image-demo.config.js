import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/demo',
  testMatch: 'record-user-image-demo.spec.js',
  timeout: 600_000,
  expect: { timeout: 600_000 },
  workers: 1,
  retries: 0,
  fullyParallel: false,
  reporter: [['list'], ['html', { outputFolder: 'user-image-demo-report', open: 'never' }]],
  use: {
    baseURL: process.env.DEMO_BASE_URL || 'http://192.168.48.133:3000',
    browserName: 'chromium', headless: true,
    viewport: { width: 2560, height: 1440 },
    deviceScaleFactor: 1, colorScheme: 'light',
    // `video: 'on'` uses Playwright's default 800×450 size. Keep the size
    // with the video option itself so future live recordings remain 1440p.
    video: { mode: 'on', size: { width: 2560, height: 1440 } },
    trace: 'off', screenshot: 'only-on-failure',
    launchOptions: { args: ['--disable-gpu', '--no-proxy-server'], env: { ...process.env, LD_PRELOAD: '' } },
  },
})
