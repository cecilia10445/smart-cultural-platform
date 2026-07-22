import path from 'node:path'

import { expect, test } from '@playwright/test'

const screenshotDirectory = process.env.PLAYWRIGHT_SCREENSHOT_DIR
  || path.resolve(process.cwd(), 'test-results', 'screenshots')

const testUser = {
  user_id: 'playwright-user',
  username: 'playwright-user',
  name: 'Playwright 测试用户',
}

function deferred() {
  let resolve
  const promise = new Promise((resolver) => {
    resolve = resolver
  })
  return { promise, resolve }
}

function generationBody(imageUrl = 'https://test-images.invalid/generated.png') {
  return {
    status: 'success',
    generation_kind: 'cultural_product',
    prompt_template_version: 'cultural-product-v1',
    image_url: imageUrl,
    product_name: '测试数据：青花书签',
    factual_background: { status: 'user_supplied', text: '测试数据：用户确认的事实。', evidence_mode: 'user_supplied_only', citations: [] },
    design_interpretation: '测试数据：用于验证设计解读展示。',
    product_copy: '测试数据：用于验证浏览器中的产品讲解展示，不会写入任何生产数据。',
    generation_time: 1.25,
    log_id: 'test-log-001',
  }
}

async function fillBrief(page, name = '测试数据：青花纹样书签') {
  await page.getByLabel('产品类型').fill('书签')
  await page.getByLabel('文化原型或灵感来源').fill('青花折枝纹')
  await page.getByLabel('造型与材质').fill('长条形纸质书签，带丝带')
  await page.getByLabel('使用场景').fill('博物馆文创商店')
  await page.getByLabel('确认事实（每行一条）').fill(name)
}

async function fulfillJson(route, status, body) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function openWorkspace(page, context, options = {}) {
  const consoleErrors = []
  const pageErrors = []
  const forbiddenRequests = []
  const generateSeen = deferred()
  const releaseGenerate = deferred()
  const generatePayloads = []
  let generateRequests = 0
  const allowedOrigins = new Set([
    process.env.PLAYWRIGHT_BASE_URL || `http://127.0.0.1:${process.env.PLAYWRIGHT_PORT || 3000}`,
    'https://cdn.jsdelivr.net',
    'https://test-images.invalid',
  ])

  page.on('console', (message) => {
    const isExpectedMockHttpError = message.text().includes('the server responded with a status of 401')
      || message.text().includes('the server responded with a status of 503')
    if (message.type() === 'error' && !isExpectedMockHttpError) consoleErrors.push(message.text())
  })
  page.on('pageerror', (error) => pageErrors.push(error.message))
  await context.addInitScript((user) => {
    localStorage.setItem('token', 'playwright-test-token')
    localStorage.setItem('userInfo', JSON.stringify(user))
  }, testUser)

  await page.route('**/*', async (route) => {
    const requestUrl = new URL(route.request().url())
    if (!['http:', 'https:'].includes(requestUrl.protocol)) {
      await route.continue()
      return
    }
    if (allowedOrigins.has(requestUrl.origin)) {
      await route.continue()
      return
    }

    forbiddenRequests.push(requestUrl.href)
    await route.abort('blockedbyclient')
  })
  await page.route('https://cdn.jsdelivr.net/**', (route) => route.fulfill({ status: 200, body: '' }))
  await page.route('https://test-images.invalid/**', async (route) => {
    if (route.request().url().endsWith('/missing.png')) {
      await route.fulfill({ status: 200, contentType: 'image/png', body: 'invalid test image data' })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'image/png',
      body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFgAI/ScL3VQAAAABJRU5ErkJggg==', 'base64'),
    })
  })
  await page.route('**/api/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname

    if (pathname === '/api/user/profile') {
      await fulfillJson(route, 200, { status: 'success', user: testUser })
      return
    }
    if (pathname === '/api/user/history') {
      await fulfillJson(route, 200, { status: 'success', data: [] })
      return
    }
    if (pathname === '/api/recommendations/personalized') {
      await fulfillJson(route, 200, {
        status: 'success',
        data: { style_recommendations: [], hot_keywords: [] },
      })
      return
    }
    if (pathname === '/api/rating') {
      const rating = JSON.parse(route.request().postData() || '{}').rating
      await fulfillJson(route, 200, { status: 'success', rating })
      return
    }
    if (pathname === '/api/download') {
      await fulfillJson(route, 200, { status: 'success' })
      return
    }
    if (pathname === '/api/v2/cultural-products/generate') {
      generateRequests += 1
      generatePayloads.push(JSON.parse(route.request().postData() || '{}'))
      if (options.generateMode === 'hold-success') {
        generateSeen.resolve()
        await releaseGenerate.promise
      }
      if (options.generateMode === 'service-unavailable') {
        await fulfillJson(route, 503, { status: 'error', message: 'test service unavailable' })
        return
      }
      if (options.generateMode === 'unauthorized') {
        await fulfillJson(route, 401, { status: 'error', message: 'test unauthorized' })
        return
      }
      const imageUrl = options.generateMode === 'missing-image'
        ? 'https://test-images.invalid/missing.png'
        : undefined
      await fulfillJson(route, 200, generationBody(imageUrl))
      return
    }

    await fulfillJson(route, 404, { status: 'error', message: 'unhandled Playwright test route' })
  })

  await page.goto('/index.html', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: '把文化意象说清楚' })).toBeVisible()

  return {
    consoleErrors,
    forbiddenRequests,
    generateRequests: () => generateRequests,
    generatePayloads: () => generatePayloads,
    pageErrors,
    releaseGenerate: () => releaseGenerate.resolve(),
    waitForGenerate: () => generateSeen.promise,
  }
}

async function expectLayoutIsUsable(page) {
    await expect(page.getByRole('button', { name: '生成文创产品' })).toBeVisible()
  await expect(page.getByRole('navigation', { name: '用户工作台导航' })).toBeVisible()
  const hasHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
  expect(hasHorizontalOverflow).toBe(false)
}

test.describe('桌面端生成工作台', () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name !== 'desktop', '本组仅在 1440×900 验收')
  })

  test('默认显示策展方案和四个画面维度', async ({ page, context }) => {
    const harness = await openWorkspace(page, context)

    await expect(page.getByRole('button', { name: /宋韵青绿/ })).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByRole('button', { name: /敦煌重彩/ })).toHaveAttribute('aria-pressed', 'false')
    await expect(page.getByLabel('文化语境')).toHaveValue('song')
    await expect(page.getByLabel('表现媒介')).toHaveValue('gongbi')
    await expect(page.getByLabel('色彩倾向')).toHaveValue('qingGreen')
    await expect(page.getByLabel('构图气质')).toHaveValue('openSpace')
    await expectLayoutIsUsable(page)
    await page.screenshot({ path: path.join(screenshotDirectory, 'desktop-default.png'), fullPage: true })

    expect(harness.consoleErrors).toEqual([])
    expect(harness.pageErrors).toEqual([])
    expect(harness.forbiddenRequests).toEqual([])
  })

  test('切换方案、编辑维度和补充要求会更新稳定画面描述', async ({ page, context }) => {
    const harness = await openWorkspace(page, context)

    await page.getByRole('button', { name: /敦煌重彩/ }).click()
    await expect(page.getByRole('button', { name: /敦煌重彩/ })).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByRole('button', { name: /宋韵青绿/ })).toHaveAttribute('aria-pressed', 'false')
    await expect(page.getByLabel('文化语境')).toHaveValue('dunhuang')
    await expect(page.getByLabel('表现媒介')).toHaveValue('mineral')
    await page.getByLabel('构图气质').selectOption('geometry')
    await page.getByLabel('补充画面要求（可选）').fill('纹样边缘清晰，避免人物')
    await page.getByText('查看本次画面描述').click()
    await expect(page.getByText('敦煌壁画；矿物重彩；朱砂石青鎏金；几何秩序；补充：纹样边缘清晰，避免人物')).toBeVisible()
    await expectLayoutIsUsable(page)
    await page.screenshot({ path: path.join(screenshotDirectory, 'desktop-direction-edit.png'), fullPage: true })

    await fillBrief(page)
    await page.getByRole('button', { name: '生成文创产品' }).click()
    await expect(page.getByRole('heading', { name: '测试数据：青花书签' })).toBeVisible()
    expect(harness.generatePayloads()).toEqual([expect.objectContaining({
      brief_version: '1.0',
      brief: expect.objectContaining({
        product_type: '书签',
        cultural_source: expect.objectContaining({ name: '青花折枝纹' }),
        confirmed_facts: ['测试数据：青花纹样书签'],
        visual_direction: expect.objectContaining({
          cultural_context: '敦煌壁画', medium: '矿物重彩', palette: '朱砂石青鎏金',
          composition: '几何秩序', additional_requirements: '纹样边缘清晰，避免人物',
        }),
      }),
    })])

    expect(harness.consoleErrors).toEqual([])
    expect(harness.pageErrors).toEqual([])
    expect(harness.forbiddenRequests).toEqual([])
  })

  test('空主题阻止提交，503 后保留用户输入', async ({ page, context }) => {
    const emptyHarness = await openWorkspace(page, context, { generateMode: 'service-unavailable' })
    await page.getByRole('button', { name: '生成文创产品' }).click()
    await expect(page.getByRole('alert')).toContainText('请填写产品类型')
    expect(emptyHarness.generateRequests()).toBe(0)

    await fillBrief(page, '测试数据：503 后仍应保留')
    await page.getByRole('button', { name: '生成文创产品' }).click()
    await expect(page.getByRole('alert')).toContainText('生成暂时不可用')
    await expect(page.getByLabel('确认事实（每行一条）')).toHaveValue('测试数据：503 后仍应保留')
    await page.screenshot({ path: path.join(screenshotDirectory, 'desktop-503-state.png'), fullPage: true })

    expect(emptyHarness.consoleErrors).toEqual([])
    expect(emptyHarness.pageErrors).toEqual([])
    expect(emptyHarness.forbiddenRequests).toEqual([])
  })

  test('401 显示登录失效并保留用户输入', async ({ page, context }) => {
    const harness = await openWorkspace(page, context, { generateMode: 'unauthorized' })

    await fillBrief(page, '测试数据：401 后仍应保留')
    await page.getByRole('button', { name: '生成文创产品' }).click()
    await expect(page.getByRole('alert').filter({ hasText: '登录状态已失效。' })).toBeVisible()
    await expect(page.getByLabel('确认事实（每行一条）')).toHaveValue('测试数据：401 后仍应保留')

    expect(harness.consoleErrors).toEqual([])
    expect(harness.pageErrors).toEqual([])
    expect(harness.forbiddenRequests).toEqual([])
  })

  test('生成期间阻止重复提交，并展示测试成功结果', async ({ page, context }) => {
    const harness = await openWorkspace(page, context, { generateMode: 'hold-success' })

    await fillBrief(page)
    await page.getByRole('button', { name: '生成文创产品' }).click()
    await harness.waitForGenerate()
    await expect(page.getByRole('heading', { name: '正在处理你的创作请求' })).toBeVisible()
    await expect(page.getByRole('button', { name: '正在生成' })).toBeDisabled()
    await page.getByRole('button', { name: '正在生成' }).click({ force: true })
    expect(harness.generateRequests()).toBe(1)

    harness.releaseGenerate()
    await expect(page.getByRole('heading', { name: '测试数据：青花书签' })).toBeVisible()
    await expect(page.getByText('测试数据：用于验证浏览器中的产品讲解展示，不会写入任何生产数据。')).toBeVisible()
    await expect(page.getByText('1.25 秒')).toBeVisible()
    await expect(page.getByText('test-log-001')).toBeVisible()
    await expect(page.locator('img[alt="测试数据：青花书签"]')).toHaveAttribute('src', 'https://test-images.invalid/generated.png')
    await page.screenshot({ path: path.join(screenshotDirectory, 'desktop-success-result.png'), fullPage: true })

    expect(harness.consoleErrors).toEqual([])
    expect(harness.pageErrors).toEqual([])
    expect(harness.forbiddenRequests).toEqual([])
  })

  test('图片加载失败时显示本地错误状态', async ({ page, context }) => {
    const harness = await openWorkspace(page, context, { generateMode: 'missing-image' })

    await fillBrief(page, '测试数据：图片失败')
    await page.getByRole('button', { name: '生成文创产品' }).click()
    await expect(page.getByText('图片暂时无法加载')).toBeVisible()
    await expect(page.getByText('你仍可以查看本次生成的文字内容。')).toBeVisible()
    await page.screenshot({ path: path.join(screenshotDirectory, 'desktop-image-failure.png'), fullPage: true })

    expect(harness.consoleErrors).toEqual([])
    expect(harness.pageErrors).toEqual([])
    expect(harness.forbiddenRequests).toEqual([])
  })
})

test.describe('移动端生成工作台', () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name !== 'mobile', '本组仅在 390×844 验收')
  })

  test('默认页面可操作且没有页面级横向溢出', async ({ page, context }) => {
    const harness = await openWorkspace(page, context)

    await expect(page.getByRole('button', { name: /宋韵青绿/ })).toBeVisible()
    await expect(page.getByLabel('补充画面要求（可选）')).toBeVisible()
    await expectLayoutIsUsable(page)
    await page.screenshot({ path: path.join(screenshotDirectory, 'mobile-default.png'), fullPage: true })

    expect(harness.consoleErrors).toEqual([])
    expect(harness.pageErrors).toEqual([])
    expect(harness.forbiddenRequests).toEqual([])
  })
})
