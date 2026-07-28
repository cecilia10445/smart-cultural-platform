import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { expect, test } from '@playwright/test'
import { assertAllVisibleEditableFieldsFilled, fillOrdinaryUserImageBrief } from './user-image-demo-data.js'
import { payloadSha256 } from './payload-contract.js'

const username = process.env.DEMO_USERNAME
const password = process.env.DEMO_PASSWORD

test('连续录制普通用户真实图片业务生成', async ({ page }, testInfo) => {
  test.skip(!username || !password, '需要 DEMO_USERNAME 和 DEMO_PASSWORD。')
  const pageErrors = []
  page.on('pageerror', error => pageErrors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') pageErrors.push(message.text()) })
  await page.goto('/login.html', { waitUntil: 'networkidle' })
  await expect(page.getByRole('heading', { name: '智能文创平台' })).toBeVisible()
  await page.getByRole('button', { name: /普通用户/ }).click()
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码').fill(password)
  await expect(page.getByLabel('密码')).toHaveAttribute('type', 'password')
  await Promise.all([page.waitForURL(/index\.html/), page.getByRole('button', { name: '进入创作工作台' }).click()])
  await expect(page.getByRole('navigation', { name: '用户工作台导航' })).toBeVisible()
  await expect(page.getByText('运营管理员')).toHaveCount(0)
  // This is an authenticated, real API read.  Do not treat localStorage as
  // proof of identity in a live-demo contract.
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
  await fillOrdinaryUserImageBrief(page)
  await expect(page.getByLabel('产品展示方式')).toHaveValue('single_hero')
  await assertAllVisibleEditableFieldsFilled(page)
  await page.waitForTimeout(1300)
  const submitted = page.waitForRequest(request => request.method() === 'POST' && new URL(request.url()).pathname === '/api/v2/cultural-products/generate')
  const completed = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v2/cultural-products/generate', { timeout: 600_000 })
  await page.getByRole('button', { name: '生成文创产品' }).click()
  const request = await submitted
  const payload = request.postDataJSON()
  const payloadHash = payloadSha256(payload)
  if (process.env.DEMO_EXPECTED_PAYLOAD_SHA) expect(payloadHash).toBe(process.env.DEMO_EXPECTED_PAYLOAD_SHA)
  if (process.env.DEMO_FORMAL_PAYLOAD_PATH) {
    fs.mkdirSync(path.dirname(process.env.DEMO_FORMAL_PAYLOAD_PATH), { recursive: true })
    fs.writeFileSync(process.env.DEMO_FORMAL_PAYLOAD_PATH, `${JSON.stringify(payload, null, 2)}\n`, 'utf8')
  }
  const response = await completed
  expect(response.status()).toBe(200)
  const body = await response.json()
  expect(body.generation_kind).toBe('cultural_product')
  expect(body.log_id).toBeTruthy()
  expect(body.image_url).toMatch(/^\/static\/images\/image_[a-f0-9]{16}_[a-f0-9]{8}\.(png|jpg|webp)$/)
  expect(body.image_url).not.toContain('preflight')
  await expect(page.getByRole('heading', { name: body.product_name })).toBeVisible({ timeout: 600_000 })
  const image = page.locator('.image-stage img')
  await expect(image).toBeVisible()
  const imageInfo = await image.evaluate(async (node) => {
    const response = await fetch(node.src, { cache: 'no-store' })
    return { naturalWidth: node.naturalWidth, naturalHeight: node.naturalHeight, status: response.status, contentType: response.headers.get('content-type') }
  })
  expect(imageInfo.naturalWidth).toBeGreaterThan(0)
  expect(imageInfo.naturalHeight).toBeGreaterThan(0)
  expect(imageInfo.status).toBe(200)
  expect(imageInfo.contentType).toMatch(/^image\/(png|jpeg|webp)/)
  await page.screenshot({ path: testInfo.outputPath('ordinary-user-image-result.png'), fullPage: true })
  await page.getByRole('button', { name: /记录/ }).click()
  await page.getByRole('button', { name: '刷新记录' }).click()
  await expect(page.getByRole('heading', { name: body.product_name })).toBeVisible()
  await page.getByRole('button', { name: '查看详情' }).first().click()
  await expect(page.getByRole('dialog', { name: body.product_name })).toBeVisible()
  await expect(page.getByRole('button', { name: '放大产品图片' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('ordinary-user-image-history.png'), fullPage: true })
  await page.reload({ waitUntil: 'networkidle' })
  await page.getByRole('button', { name: /记录/ }).click()
  await expect(page.getByRole('heading', { name: body.product_name })).toBeVisible()
  const imageBytes = await page.evaluate(async (url) => Array.from(new Uint8Array(await (await fetch(url, { cache: 'no-store' })).arrayBuffer())), body.image_url)
  const record = { user_id: profile.user_id, username: profile.username, role: profile.role, log_id: body.log_id, image_url: body.image_url, product_name: body.product_name, payload_sha256: payloadHash, image_sha256: crypto.createHash('sha256').update(Buffer.from(imageBytes)).digest('hex'), image_width: imageInfo.naturalWidth, image_height: imageInfo.naturalHeight }
  if (process.env.DEMO_RESULT_PATH) {
    fs.mkdirSync(path.dirname(process.env.DEMO_RESULT_PATH), { recursive: true })
    fs.writeFileSync(process.env.DEMO_RESULT_PATH, `${JSON.stringify(record, null, 2)}\n`, 'utf8')
  }
  expect(pageErrors).toEqual([])
})
