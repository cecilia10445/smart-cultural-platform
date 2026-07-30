import { expect, test } from '@playwright/test'

const base = (status, extra = {}) => ({ status: 'success', request_id: 'stub-request', data: {
  schema_version: 'agent-session-detail-v1', session_id: 'agent-stub-1', status, current_stage: status, revision_count: 0,
  generation_log_id: null, brief_summary: null, product_design: null, visual_direction: null, final_result: null,
  messages: [], steps: [], error: null, created_at: '2026-07-30T12:00:00', updated_at: '2026-07-30T12:00:00', ...extra,
} })

const completedSession = () => base('completed', {
  session_id: 'agent-completed-1', generation_log_id: 73, revision_count: 1,
  brief_summary: { cultural_theme: '三兔共耳纹样', product_type: '现代桌面灯', use_case: '家居照明', style: '现代简洁', design_constraints: ['避免仿古'], assumptions: ['单品主视图'] },
  product_design: { product_name: '三兔环光桌面灯', design_concept: '以环形动态表达三兔共耳。', cultural_translation: '将循环纹样转为现代灯体结构。', structure: '金属环与半透明灯罩', materials: '磨砂金属、半透明亚克力', color_plan: '暖白、深灰', usage_scene: '现代家居桌面', selling_points: ['环形动态', '柔和照明'], evidence_status: 'grounded', selected_text_skill: 'retail-product-copy' },
  visual_direction: { summary: '现代产品主视图，强调环形结构与柔和灯光。', selected_visual_skill: 'commercial-product-presentation', positive_prompt_summary: '环形灯体', negative_constraints: ['人物', '水印'], presentation_mode: 'single_hero', product_form: '环形结构', materials: '磨砂金属', color_plan: '暖白与深灰', composition: '单品主视图', scene: '现代书桌', avoid: ['人物', '水印'] },
  final_result: { product_name: '三兔环光桌面灯', image_url: '/static/images/agent-stub.png', evidence_status: 'grounded', selected_text_skill: 'retail-product-copy', selected_visual_skill: 'commercial-product-presentation', generation_time: 3.4 },
  messages: [
    { id: 'm1', sequence_no: 1, role: 'user', message_type: 'user_message', text: '以三兔共耳设计现代桌面灯', created_at: '2026-07-30T12:00:00' },
    { id: 'm2', sequence_no: 2, role: 'assistant', message_type: 'brief_summary', text: '我理解你希望设计一款现代桌面照明产品。', created_at: '2026-07-30T12:01:00' },
  ],
  steps: [
    { id: 's1', ordinal: 1, stage: 'extracting_brief', status: 'completed', summary: '需求已整理', tool: 'brief_agent' },
    { id: 's2', ordinal: 2, stage: 'generating_product_text', status: 'completed', summary: '产品设计稿已生成', tool: 'retail-product-copy' },
    { id: 's3', ordinal: 3, stage: 'building_visual_prompt', status: 'completed', summary: '视觉方向已整理', tool: 'commercial-product-presentation' },
  ],
  completed_at: '2026-07-30T12:05:00',
})

async function installApiStub(page) {
  const calls = { creates: 0, messages: 0, decisions: 0, sessionGets: 0 }
  await page.addInitScript(() => {
    Object.defineProperty(globalThis.crypto, 'randomUUID', { value: undefined, configurable: true })
    localStorage.setItem('token', 'agent-stub-token')
    localStorage.setItem('userInfo', JSON.stringify({ user_id: 'u1', username: 'stub' }))
  })
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/user/profile') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'success', user: { user_id: 'u1' } }) })
    if (path === '/api/user/history') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'success', data: [
        { record_type: 'agent_dialogue_generation', log_id: 73, agent_session_id: 'agent-completed-1', product_name: '三兔环光桌面灯', image_url: '/static/images/agent-stub.png', timestamp: '2026-07-30T12:05:00', product_design_summary: '现代环形桌面灯', selected_text_skill: 'retail-product-copy', selected_visual_skill: 'commercial-product-presentation' },
        { log_id: 74, product_name: '普通快速生成产品', image_url: '/static/images/legacy.png', timestamp: '2026-07-30T12:06:00', presentation_mode: 'single_hero', prompt_template_version: 'cultural-product-rag-v2', design_concept: '旧详情仍应打开', cultural_meaning: '旧文化说明', creative_origin: '旧创意来源', selling_points: ['旧卖点'] },
      ], pagination: { total: 2, has_more: false } }) })
    }
    if (path === '/api/v2/agent-design/sessions' && request.method() === 'POST') {
      calls.creates += 1
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(base('created', { session_id: `agent-new-${calls.creates}` })) })
    }
    if (path.startsWith('/api/v2/agent-design/sessions/') && request.method() === 'GET') {
      calls.sessionGets += 1
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(completedSession()) })
    }
    if (path.endsWith('/messages')) {
      calls.messages += 1
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(base('waiting_brief_confirmation', {
        session_id: 'agent-new-1',
        brief_summary: { cultural_theme: '三兔共耳', product_type: '桌面灯', use_case: '桌面照明', style: '现代', design_constraints: ['避免仿古'], assumptions: ['单品主视图'] },
        messages: [{ id: 'm1', sequence_no: 1, role: 'assistant', message_type: 'brief_summary', text: '我理解你的需求。', created_at: '2026-07-30T12:00:00' }],
        steps: [{ id: 's1', ordinal: 1, stage: 'extracting_brief', status: 'completed', summary: '需求已整理', tool: 'brief_agent' }],
      })) })
    }
    if (path.endsWith('/decisions')) {
      calls.decisions += 1
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(base('waiting_image_confirmation')) })
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'success', data: [] }) })
  })
  return calls
}

test('协作式设计从首条消息创建会话，且模式分隔线保留局部间距', async ({ page }) => {
  const calls = await installApiStub(page)
  await page.goto('/index.html')
  await expect(page.getByRole('button', { name: '生成文创产品' })).toBeVisible()
  const fastGap = await page.locator('.creation-form').evaluate((node) => {
    const dividerBottom = document.querySelector('.creation-mode-area').getBoundingClientRect().bottom
    return node.getBoundingClientRect().top - dividerBottom
  })
  expect(fastGap).toBeGreaterThanOrEqual(18)
  expect(fastGap).toBeLessThanOrEqual(24)
  await page.getByRole('button', { name: '协作式设计' }).click()
  await expect(page.getByLabel('描述你的文创产品需求')).toBeVisible()
  expect(calls.creates).toBe(0)
  const spacing = await page.locator('.creation-mode-area').evaluate((node) => ({
    paddingBottom: Number.parseFloat(getComputedStyle(node).paddingBottom),
    borderBottomWidth: Number.parseFloat(getComputedStyle(node).borderBottomWidth),
  }))
  expect(spacing.paddingBottom).toBeGreaterThanOrEqual(12)
  expect(spacing.paddingBottom).toBeLessThanOrEqual(16)
  expect(spacing.borderBottomWidth).toBeGreaterThanOrEqual(1)
  const agentGap = await page.locator('.agent-panel').evaluate((node) => {
    const dividerBottom = document.querySelector('.creation-mode-area').getBoundingClientRect().bottom
    return node.getBoundingClientRect().top - dividerBottom
  })
  expect(agentGap).toBeGreaterThanOrEqual(18)
  expect(agentGap).toBeLessThanOrEqual(24)
  await page.getByLabel('描述你的文创产品需求').fill('以三兔共耳设计现代桌面灯')
  await page.getByRole('button', { name: '开始设计' }).click()
  await expect(page.getByText('我理解的需求')).toBeVisible()
  expect(calls.creates).toBe(1)
  expect(calls.messages).toBe(1)
  expect(page.url()).toContain('agent_session_id=agent-new-1')
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: '开始新的协作设计' }).click()
  await expect(page.getByLabel('描述你的文创产品需求')).toBeVisible()
  expect(page.url()).not.toContain('agent_session_id=')
  expect(calls.creates).toBe(1)
})

test('已完成会话可开始新的协作设计，且不复用旧 session', async ({ page }) => {
  const calls = await installApiStub(page)
  await page.goto('/index.html?agent_session_id=agent-completed-1')
  await expect(page.getByText('本次协作设计已完成')).toBeVisible()
  await page.getByRole('button', { name: '协作式设计' }).click()
  await expect(page.getByLabel('描述你的文创产品需求')).toBeVisible()
  expect(page.url()).not.toContain('agent_session_id=')
  expect(calls.creates).toBe(0)
  await page.getByLabel('描述你的文创产品需求').fill('设计一款现代文化胸针')
  await page.getByRole('button', { name: '开始设计' }).click()
  expect(calls.creates).toBe(1)
  expect(calls.messages).toBe(1)
  expect(page.url()).toContain('agent_session_id=agent-new-1')
})

test('Agent 历史记录进入只读回顾，普通快速生成仍使用旧详情', async ({ page }) => {
  const calls = await installApiStub(page)
  await page.goto('/index.html')
  await page.getByRole('button', { name: '协作式设计' }).click()
  await page.getByRole('button', { name: '协作式历史记录' }).click()
  await expect(page.getByRole('heading', { name: '创作记录' })).toBeVisible()
  const agentCard = page.locator('.history-entry').filter({ hasText: '三兔环光桌面灯' })
  await agentCard.getByRole('button', { name: '查看详情' }).click()
  await expect(page.getByRole('heading', { name: '协作式设计记录' })).toBeVisible()
  expect(page.url()).toContain('agent_session_id=agent-completed-1')
  expect(page.url()).toContain('view=history')
  await expect(page.getByText('我理解你希望设计一款现代桌面照明产品。')).toBeVisible()
  await expect(page.getByText('产品设计稿已生成')).toBeVisible()
  await expect(page.getByRole('heading', { name: '三兔环光桌面灯' }).first()).toBeVisible()
  await expect(page.getByText('generation_log_id：73')).toBeVisible()
  await expect(page.getByLabel('描述你的文创产品需求')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '确认需求方案' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '确认生成图片' })).toHaveCount(0)
  expect(calls.messages).toBe(0)
  expect(calls.decisions).toBe(0)
  await page.getByRole('button', { name: '返回全部创作记录' }).click()
  await expect(page.getByRole('heading', { name: '创作记录' })).toBeVisible()
  const legacyCard = page.locator('.history-entry').filter({ hasText: '普通快速生成产品' })
  await legacyCard.getByRole('button', { name: '查看详情' }).click()
  await expect(page.getByRole('dialog', { name: '普通快速生成产品' })).toBeVisible()
})
