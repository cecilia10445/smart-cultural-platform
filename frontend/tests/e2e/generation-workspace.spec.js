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

function generationBody(imageUrl = 'https://test-images.invalid/generated.png', evidenceMode = 'grounded') {
  const grounded = evidenceMode === 'grounded'
  const citations = grounded ? [{
    source_id: 'met-39666',
    title: 'Jar with dragon',
    source_url: 'https://www.metmuseum.org/art/collection/search/39666',
    license: 'CC0-1.0',
  }] : []
  return {
    status: 'success',
    generation_kind: 'cultural_product',
    prompt_template_version: 'cultural-product-rag-v1',
    image_url: imageUrl,
    product_name: '测试数据：青花书签',
    evidence_status: grounded ? 'grounded' : 'insufficient_evidence',
    used_source_ids: grounded ? ['met-39666'] : [],
    factual_background: {
      status: grounded ? 'grounded' : 'insufficient_evidence',
      text: grounded ? '测试数据：馆藏器物为釉下钴蓝彩绘瓷器。' : '测试数据：用户确认的事实。',
      evidence_mode: grounded ? 'frozen_official_sources' : 'user_supplied_only',
      citations,
    },
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
      await fulfillJson(route, 200, { status: 'success', data: options.historyData || [] })
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
      const evidenceMode = options.generateMode === 'insufficient-evidence' ? 'insufficient' : 'grounded'
      await fulfillJson(route, 200, generationBody(imageUrl, evidenceMode))
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

  test('历史 v2 详情使用结构化字段并支持图片预览', async ({ page, context }) => {
    const historyData = [{
      log_id: 2,
      prompt_template_version: 'cultural-product-rag-v2',
      product_name: '青花杯垫',
      presentation_mode: 'flat_front_back',
      creative_origin: '源自青花瓷纹样',
      design_concept: '将纹样转为杯垫边缘环形装饰',
      cultural_meaning: '表达雅正生活',
      selling_points: ['正反面一致展示', '粗陶材质耐用', '边缘纹样清晰'],
      factual_background: { text: '馆藏事实脱敏文本', status: 'grounded', citations: [{ source_id: 'met-39666', title: '青花器物', source_url: 'https://www.metmuseum.org/art/collection/search/39666', license: 'CC0' }] },
      evidence_status: 'grounded',
      citations: [{ source_id: 'met-39666', title: '青花器物', source_url: 'https://www.metmuseum.org/art/collection/search/39666', license: 'CC0' }],
      image_url: 'https://test-images.invalid/generated.png',
      generation_time: '2026-01-01T10:00:00Z',
      timestamp: '2026-01-01T10:00:00Z',
    }]
    const harness = await openWorkspace(page, context, { historyData })
    await page.getByRole('button', { name: /记录/ }).click()
    await expect(page.getByRole('heading', { name: '青花杯垫' })).toBeVisible()
    await expect(page.getByText('正反面产品展示')).toBeVisible()
    await expect(page.getByText('正反面一致展示')).toBeVisible()
    await page.getByRole('button', { name: '查看详情' }).click()
    await expect(page.getByRole('dialog', { name: '青花杯垫' })).toBeVisible()
    await expect(page.getByText('馆藏事实脱敏文本')).toBeVisible()
    await expect(page.getByRole('link', { name: '青花器物' })).toHaveAttribute('href', /metmuseum/)
    await expect(page.getByText('[object Object]')).toHaveCount(0)
    await page.getByRole('button', { name: '放大产品图片' }).click()
    await expect(page.getByRole('dialog', { name: '产品图片预览' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog', { name: '产品图片预览' })).toBeHidden()
    await page.getByRole('button', { name: '关闭产品详情' }).click()
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
    const sourceLink = page.getByRole('link', { name: /Jar with dragon/ })
    await expect(sourceLink).toHaveAttribute('href', 'https://www.metmuseum.org/art/collection/search/39666')
    await expect(sourceLink).toHaveAttribute('target', '_blank')
    await expect(sourceLink).toHaveAttribute('rel', 'noopener noreferrer')
    await expect(page.getByText('met-39666')).toBeVisible()
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

  test('无可靠命中时明确显示资料不足且不伪造来源', async ({ page, context }) => {
    const harness = await openWorkspace(page, context, { generateMode: 'insufficient-evidence' })

    await fillBrief(page, '测试数据：无馆藏命中')
    await page.getByRole('button', { name: '生成文创产品' }).click()
    await expect(page.getByRole('heading', { name: '当前资料不足' })).toBeVisible()
    await expect(page.getByText('未找到足够可靠的本地馆藏证据')).toBeVisible()
    await expect(page.getByText('Metropolitan Museum of Art')).toHaveCount(0)
    await expectLayoutIsUsable(page)

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

  test('引用结果在窄屏可读且没有页面级横向溢出', async ({ page, context }) => {
    const harness = await openWorkspace(page, context)

    await fillBrief(page)
    await page.getByRole('button', { name: '生成文创产品' }).click()
    await expect(page.getByRole('heading', { name: '本次实际使用的来源' })).toBeVisible()
    await expect(page.getByRole('link', { name: /Jar with dragon/ })).toBeVisible()
    await expectLayoutIsUsable(page)

    expect(harness.consoleErrors).toEqual([])
    expect(harness.pageErrors).toEqual([])
    expect(harness.forbiddenRequests).toEqual([])
  })

  test('窄屏历史详情上下排列且图片预览可用', async ({ page, context }) => {
    const harness = await openWorkspace(page, context, { historyData: [{
      log_id: 2, prompt_template_version: 'cultural-product-rag-v2', product_name: '移动端杯垫', presentation_mode: 'flat_front_back',
      creative_origin: '青花纹样', design_concept: '环形边缘', cultural_meaning: '雅正生活', selling_points: ['卖点一', '卖点二'],
      factual_background: '归一化资料文本', evidence_status: 'insufficient_evidence', citations: [], image_url: 'https://test-images.invalid/generated.png', timestamp: '2026-01-01T10:00:00Z', generation_time: '2026-01-01T10:00:00Z',
    }] })
    await page.getByRole('button', { name: /记录/ }).click()
    await page.getByRole('button', { name: '查看详情' }).click()
    await expect(page.getByText('归一化资料文本')).toBeVisible()
    await expect(page.getByText('当前资料不足')).toBeVisible()
    await page.getByRole('button', { name: '放大产品图片' }).click()
    await expect(page.getByRole('dialog', { name: '产品图片预览' })).toBeVisible()
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '关闭产品详情' }).click()
    await expect(page.locator('body')).toHaveJSProperty('scrollWidth', 390)
    expect(harness.consoleErrors).toEqual([])
    expect(harness.pageErrors).toEqual([])
  })
})

test.describe('登录页响应式标题', () => {
  test('390px 宽度下平台标题保持单行且不溢出', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'mobile', '本组仅在 390×844 验收')
    await page.goto('/login.html')
    const title = page.getByRole('heading', { name: '智能文创平台' })
    await expect(title).toBeVisible()
    await expect(title).toHaveCSS('white-space', 'nowrap')
    const box = await title.boundingBox()
    expect(box).not.toBeNull()
    expect(box.x + box.width).toBeLessThanOrEqual(390)
    await expect(page.locator('body')).toHaveJSProperty('scrollWidth', 390)
  })
})
