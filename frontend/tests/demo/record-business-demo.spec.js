import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { assertAllVisibleEditableFieldsFilled, fillThreeViewBrief } from './business-demo-data.js'
import { payloadSha256 } from './payload-contract.js'

const email = process.env.DEMO_EMAIL
const password = process.env.DEMO_PASSWORD

test('录制真实文本 Skill 业务生成与运营报告回看', async ({ page }, testInfo) => {
  test.skip(!email || !password, '需要通过 DEMO_EMAIL 和 DEMO_PASSWORD 提供运营账户。')
  const pageErrors = []
  page.on('pageerror', error => pageErrors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') pageErrors.push(message.text()) })
  await page.goto('/login.html', { waitUntil: 'networkidle' })
  await expect(page.getByRole('heading', { name: '智能文创平台' })).toBeVisible()
  await page.waitForTimeout(1200)
  await page.getByRole('button', { name: /运营用户/ }).click()
  await page.getByLabel('用户名').fill(email)
  await page.getByLabel('密码').fill(password)
  await page.getByRole('button', { name: '进入运营面板' }).click()
  await page.waitForURL(/dashboard\.html/)
  await page.waitForTimeout(1200)

  await page.getByRole('link', { name: '返回创作页' }).click()
  await page.waitForURL(/index\.html/)
  await expect(page.getByRole('heading', { name: '把文化意象说清楚' })).toBeVisible()
  await page.waitForTimeout(1000)

  await fillThreeViewBrief(page)
  await expect(page.getByLabel('产品展示方式')).toHaveValue('three_view')
  await assertAllVisibleEditableFieldsFilled(page)
  await page.waitForTimeout(8000)
  const submitted = page.waitForRequest((request) => request.method() === 'POST'
    && new URL(request.url()).pathname === '/api/v2/cultural-products/generate-with-text-skill')
  const completed = page.waitForResponse((response) => response.request().method() === 'POST'
    && new URL(response.url()).pathname === '/api/v2/cultural-products/generate-with-text-skill')
  await page.getByRole('button', { name: '生成文创产品' }).click()
  const submittedRequest = await submitted
  const submittedPayload = submittedRequest.postDataJSON()
  const submittedSha = payloadSha256(submittedPayload)
  if (process.env.DEMO_EXPECTED_PAYLOAD_SHA) expect(submittedSha).toBe(process.env.DEMO_EXPECTED_PAYLOAD_SHA)
  if (process.env.DEMO_FORMAL_PAYLOAD_PATH) {
    fs.mkdirSync(path.dirname(process.env.DEMO_FORMAL_PAYLOAD_PATH), { recursive: true })
    fs.writeFileSync(process.env.DEMO_FORMAL_PAYLOAD_PATH, `${JSON.stringify(submittedPayload, null, 2)}\n`, 'utf8')
  }
  const generationResponse = await completed
  expect(generationResponse.status()).toBe(200)
  const generationBody = await generationResponse.json()
  expect(generationBody.experimental_text_skill).toBe(true)
  expect(generationBody.run_id).toMatch(/^round-17c-business-/)
  expect(generationBody.business_record_id).toBeTruthy()
  await expect(page.getByTestId('text-skill-result')).toBeVisible({ timeout: 150_000 })
  await expect(page.getByRole('heading', { name: '真实业务文本结果' })).toBeVisible()
  await page.waitForTimeout(7000)
  const runId = await page.locator('.result-meta').getByText(/round-17c-business-/).textContent()
  expect(runId).toMatch(/^round-17c-business-/)
  const readback = await page.evaluate(async (id) => {
    const token = localStorage.getItem('token')
    const response = await fetch(`/api/v2/cultural-products/text-skill-generations/${encodeURIComponent(id)}`, { headers: { Authorization: `Bearer ${token}` } })
    return { status: response.status, body: await response.json() }
  }, runId)
  expect(readback.status).toBe(200)
  expect(readback.body.data.run_id).toBe(runId)
  expect(readback.body.data.product_copy).toBeTruthy()
  expect(readback.body.data.image_design_spec).toBeTruthy()
  expect(Number(readback.body.data.actual_calls.database_writes)).toBe(1)
  await page.screenshot({ path: testInfo.outputPath('business-result.png'), fullPage: true })

  await page.goto('/dashboard.html', { waitUntil: 'networkidle' })
  await expect(page.getByRole('heading', { name: '把一次真实生成看清楚' })).toBeVisible()
  const history = page.getByLabel('选择历史运行')
  await expect(history).toContainText(runId)
  await history.selectOption(runId)
  await expect(page.getByText('RAG 来源')).toBeVisible()
  await expect(page.getByText('Agent 工具轨迹')).toBeVisible()
  await expect(page.getByText('load_generation_skill')).toBeVisible()
  await expect(page.getByText('Qwen 请求')).toBeVisible()
  await expect(page.getByText('图片调用')).toBeVisible()
  await expect(page.getByText('数据库写入')).toBeVisible()
  await expect(page.locator('.facts').getByText('1', { exact: true })).toBeVisible()
  await expect(page.getByText(/Judge|DeepSeek|评分|赢家|位置偏差/)).toHaveCount(0)
  const pageOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  expect(pageOverflow).toBe(false)
  await page.waitForTimeout(7000)
  await page.screenshot({ path: testInfo.outputPath('business-report.png'), fullPage: true })
  expect(pageErrors).toEqual([])
})
