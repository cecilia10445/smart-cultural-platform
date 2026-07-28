import { expect, test } from '@playwright/test'

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

  await page.getByLabel('产品类型').fill('清代山水画意象折叠阅读灯')
  await page.getByLabel('产品展示方式').selectOption('single_hero')
  await page.getByLabel('文化原型或灵感来源').fill('清代山水画意象')
  await page.getByLabel('已知时代（可选）').fill('清代')
  await page.getByLabel('使用场景').fill('书房与旅行阅读')
  await page.getByLabel('目标受众（可选）').fill('年轻阅读者、博物馆文创消费者')
  await page.getByLabel('造型与材质').fill('竹木灯体、半透明纸质扩散罩；折叠后便于收纳与随身携带。')
  await page.getByLabel('确认事实（每行一条）').fill('竹木灯体\n半透明纸质扩散罩\n可折叠收纳')
  await page.getByRole('button', { name: '生成文创产品' }).click()
  await expect(page.getByTestId('text-skill-result')).toBeVisible({ timeout: 150_000 })
  await expect(page.getByRole('heading', { name: '真实业务文本结果' })).toBeVisible()
  await page.waitForTimeout(3000)
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
  await expect(page.getByText(/Judge|DeepSeek|评分|赢家|位置偏差/)).toHaveCount(0)
  const pageOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  expect(pageOverflow).toBe(false)
  await page.waitForTimeout(3000)
  await page.screenshot({ path: testInfo.outputPath('business-report.png'), fullPage: true })
  expect(pageErrors).toEqual([])
})
