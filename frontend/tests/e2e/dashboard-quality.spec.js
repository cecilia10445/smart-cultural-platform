import { expect, test } from '@playwright/test'

const categories = ['unknown-field', 'invalid-json', 'field-type', 'long-input', 'long-facts', 'malicious-url', 'xss', 'unicode', 'fake-origin', 'fake-source', 'malformed-evidence', 'out-of-bounds-source', 'grounded-empty-citation', 'insufficient-with-citation', 'prompt-leak', 'credential-leak', 'authorization-leak', 'fake-era', 'fake-author', 'fake-endorsement', 'fake-collection', 'fake-history', 'web-as-museum']
const cases = categories.map((category, index) => ({
  case_id: `security-${category}`,
  category,
  outcome: index === 21 ? 'failed' : index === 22 ? 'error' : 'passed',
  stable_code: index === 21 ? 'BOUNDARY_BYPASSED' : index === 22 ? 'PROVIDER_ERROR' : 'SECURITY_BOUNDARY_REJECTED',
  assertion_name: index === 22 ? 'provider_error' : 'security_boundary',
}))
const report = {
  status: 'success',
  data: {
    run_id: 'eval-security-offline', generated_at: '2026-07-27T12:00:00Z', run_status: 'error', promptfoo_version: '0.121.19',
    total: 23, passed: 21, failed: 1, error: 1, attack_success_rate: 1 / 23,
    leakage_count: 0, invalid_citation_count: 1, factual_overreach_count: 0, invalid_structure_count: 1,
    security_categories: { 'out-of-bounds-source': { total: 1, passed: 0, failed: 1, error: 0 } }, cases,
  },
}

async function openDashboard(page, context, mode = 'success') {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
  await context.addInitScript(() => {
    localStorage.setItem('adminToken', 'playwright-admin-token')
    localStorage.setItem('adminUser', JSON.stringify({ username: 'admin1', role: 'admin', name: '运营管理员' }))
  })
  await page.route('**/api/dashboard/quality-report', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(mode === 'success' ? report : { status: mode === 'unavailable' ? 'unavailable' : 'error', code: mode === 'unavailable' ? 'QUALITY_REPORT_UNAVAILABLE' : 'AUTH_REQUIRED' }),
  }))
  await page.route('**/api/dashboard/quality-report/html', (route) => route.fulfill({
    status: 200,
    contentType: 'text/html',
    headers: { 'Content-Disposition': 'attachment; filename=promptfoo-security-report.html' },
    body: '<html><body>offline report</body></html>',
  }))
  await page.goto('/dashboard.html')
  await expect(page.getByRole('heading', { name: '把评测结果看清楚' })).toBeVisible()
  return errors
}

test('独立 AI 质量评测页面展示脱敏汇总、明细和下载入口', async ({ page, context }, testInfo) => {
  const errors = await openDashboard(page, context)
  await expect(page.getByText('离线安全与鲁棒性回归', { exact: true })).toBeVisible()
  await expect(page.locator('.metric-card').filter({ has: page.getByText('总用例', { exact: true }) }).getByRole('strong')).toHaveText('23')
  await expect(page.getByText('Prompt / 凭据泄漏')).toBeVisible()
  await expect(page.getByText('查看全部 23 项')).toBeVisible()
  await expect(page.locator('.workspace-nav')).toHaveCount(0)
  await expect(page.getByText('数据概览')).toHaveCount(0)
  await expect(page.locator('input[type="date"]')).toHaveCount(0)
  await page.getByRole('button', { name: '查看全部 23 项' }).click()
  await expect(page.locator('.case-row')).toHaveCount(23)
  await page.getByRole('button', { name: /^失败/ }).click()
  await expect(page.locator('.case-row')).toHaveCount(1)
  await page.getByRole('button', { name: /^错误/ }).click()
  await expect(page.locator('.case-row')).toHaveCount(1)
  await page.getByRole('button', { name: /^全部/ }).click()
  await expect(page.locator('.case-row')).toHaveCount(23)
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载完整 Promptfoo 报告' }).click()
  expect((await downloadPromise).suggestedFilename()).toBe('promptfoo-security-report.html')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: `test-results/dashboard-quality-${testInfo.project.name}.png`, fullPage: true })
  expect(errors).toEqual([])
})

test('报告不可用显示真实状态', async ({ page, context }) => {
  const errors = await openDashboard(page, context, 'unavailable')
  await expect(page.getByRole('alert').getByText('最近评测报告暂不可用。请检查最近一次离线评测产物后再刷新。', { exact: true })).toBeVisible()
  expect(errors).toEqual([])
})

test('401 显示登录失效', async ({ page, context }) => {
  const errors = await openDashboard(page, context, 'unauthorized')
  await expect(page.getByRole('alert').getByText('登录状态已失效，请重新登录。', { exact: true })).toBeVisible()
  expect(errors).toEqual([])
})
