import fs from 'node:fs'
import path from 'node:path'
import { expect, test } from '@playwright/test'
import { assertAllVisibleEditableFieldsFilled, fillOrdinaryUserImageBrief } from './user-image-demo-data.js'
import { payloadSha256 } from './payload-contract.js'

const username = process.env.DEMO_USERNAME
const password = process.env.DEMO_PASSWORD

test('普通用户图片业务预演只捕获正式 payload，不调用模型', async ({ page }, testInfo) => {
  test.skip(!username || !password, '需要 DEMO_USERNAME 和 DEMO_PASSWORD。')
  let captured = null
  let calls = 0
  await page.route('**/api/v2/cultural-products/generate', async (route) => {
    calls += 1
    captured = route.request().postDataJSON()
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      status: 'success', generation_kind: 'cultural_product', prompt_template_version: 'cultural-product-rag-v2',
      product_name: '预演书签', image_url: '/static/images/preflight.png', generation_time: 0, log_id: 0,
      factual_background: { text: '预演仅验证合同。', status: 'grounded', citations: [{ source_id: 'met-65625', title: 'Landscape', source_url: 'https://www.metmuseum.org/art/collection/search/65625' }] },
      evidence_status: 'grounded', used_source_ids: ['met-65625'], creative_origin: '预演', design_concept: '预演', cultural_meaning: '预演', selling_points: ['一', '二', '三'],
    }) })
  })
  await page.goto('/login.html', { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: /普通用户/ }).click()
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码').fill(password)
  await Promise.all([page.waitForURL(/index\.html/), page.getByRole('button', { name: '进入创作工作台' }).click()])
  // Verify the authenticated principal through the real profile API rather
  // than trusting browser storage populated during login.
  const profile = await page.evaluate(async () => {
    const token = localStorage.getItem('token')
    const response = await fetch('/api/user/profile', {
      cache: 'no-store',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!response.ok) throw new Error(`profile request failed: ${response.status}`)
    const body = await response.json()
    return body.user || body.data || body
  })
  expect(profile.username).toBe(username)
  expect(profile.role).toBe('user')
  if (process.env.DEMO_PROFILE_PATH) {
    fs.mkdirSync(path.dirname(process.env.DEMO_PROFILE_PATH), { recursive: true })
    fs.writeFileSync(process.env.DEMO_PROFILE_PATH, `${JSON.stringify({ user_id: profile.user_id, username: profile.username, role: profile.role }, null, 2)}\n`, 'utf8')
  }
  await fillOrdinaryUserImageBrief(page)
  await expect(page.getByLabel('产品展示方式')).toHaveValue('single_hero')
  await assertAllVisibleEditableFieldsFilled(page)
  await page.getByRole('button', { name: '生成文创产品' }).click()
  await expect(page.getByRole('heading', { name: '预演书签' })).toBeVisible()
  expect(calls).toBe(1)
  expect(captured?.brief?.presentation_mode).toBe('single_hero')
  const payloadPath = process.env.DEMO_PREFLIGHT_PAYLOAD_PATH || testInfo.outputPath('ordinary-user-image-payload.json')
  fs.mkdirSync(path.dirname(payloadPath), { recursive: true })
  fs.writeFileSync(payloadPath, `${JSON.stringify(captured, null, 2)}\n`, 'utf8')
  if (process.env.DEMO_PREFLIGHT_MANIFEST_PATH) {
    fs.mkdirSync(path.dirname(process.env.DEMO_PREFLIGHT_MANIFEST_PATH), { recursive: true })
    fs.writeFileSync(process.env.DEMO_PREFLIGHT_MANIFEST_PATH, `${JSON.stringify({ payload_sha256: payloadSha256(captured), endpoint: '/api/v2/cultural-products/generate', model_calls: 0, image_calls: 0, database_writes: 0 }, null, 2)}\n`, 'utf8')
  }
})
