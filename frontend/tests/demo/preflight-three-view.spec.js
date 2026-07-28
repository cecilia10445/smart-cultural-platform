import fs from 'node:fs'
import path from 'node:path'

import { expect, test } from '@playwright/test'
import { assertAllVisibleEditableFieldsFilled, fillThreeViewBrief } from './business-demo-data.js'

const testUser = { user_id: 'preflight-user', username: 'preflight-user', name: '预演用户' }

test('三视图浏览器预演只捕获合法 payload，不发起生成请求', async ({ page, context }, testInfo) => {
  let captured = null
  let generationRequests = 0
  await context.addInitScript((user) => {
    localStorage.setItem('token', 'preflight-token')
    localStorage.setItem('userInfo', JSON.stringify(user))
  }, testUser)
  await page.route('**/api/user/profile', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'success', user: testUser }) }))
  await page.route('**/api/user/history', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'success', data: [] }) }))
  await page.route('**/api/v2/cultural-products/generate-with-text-skill', async route => {
    generationRequests += 1
    captured = route.request().postDataJSON()
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      status: 'success', experimental_text_skill: true, run_id: 'preflight-only', generation_time: 0,
      product_copy: '预演文案', image_design_spec: '预演说明', sources: [{ source_id: 'met-65625', title: 'Landscape', source_url: 'https://www.metmuseum.org/art/collection/search/65625' }], selected_skill_id: 'preflight-only',
    }) })
  })
  await page.goto('/index.html', { waitUntil: 'networkidle' })
  await expect(page.getByRole('heading', { name: '把文化意象说清楚' })).toBeVisible()
  await fillThreeViewBrief(page)
  await expect(page.getByLabel('产品展示方式')).toHaveValue('three_view')
  await assertAllVisibleEditableFieldsFilled(page)
  await page.getByRole('button', { name: '生成文创产品' }).click()
  await expect(page.getByTestId('text-skill-result')).toBeVisible()
  expect(generationRequests).toBe(1)
  expect(captured?.brief?.presentation_mode).toBe('three_view')
  expect(new Set([captured.brief.front_design_requirements, captured.brief.back_design_requirements, captured.brief.side_design_requirements]).size).toBe(3)
  const destination = process.env.DEMO_PREFLIGHT_PAYLOAD_PATH || testInfo.outputPath('three-view-payload.json')
  fs.mkdirSync(path.dirname(destination), { recursive: true })
  fs.writeFileSync(destination, `${JSON.stringify(captured, null, 2)}\n`, 'utf8')
})
