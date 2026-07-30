import { expect, test } from '@playwright/test'

const base = (status, extra = {}) => ({ status: 'success', request_id: 'stub-request', data: {
  schema_version: 'agent-session-detail-v1', session_id: 'agent-stub-1', status, current_stage: status, revision_count: 0,
  generation_log_id: null, brief_summary: null, product_design: null, visual_direction: null, final_result: null,
  messages: [], steps: [], error: null, created_at: '2026-07-30T12:00:00', updated_at: '2026-07-30T12:00:00', ...extra,
} })

test('协作式设计使用后端会话 fixture，且不影响快速生成入口', async ({ page }) => {
  await page.addInitScript(() => { Object.defineProperty(globalThis.crypto, 'randomUUID', { value: undefined, configurable: true }); localStorage.setItem('token', 'agent-stub-token'); localStorage.setItem('userInfo', JSON.stringify({ user_id: 'u1', username: 'stub' })) })
  let decisions = 0
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/user/profile') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'success', user: { user_id: 'u1' } }) })
    if (path === '/api/v2/agent-design/sessions') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(base('created')) })
    if (path.endsWith('/messages')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(base('waiting_brief_confirmation', { brief_summary: { cultural_theme: '三兔共耳', product_type: '桌面灯', use_case: '桌面照明', style: '现代', design_constraints: ['避免仿古'], assumptions: ['单品主视图'] }, messages: [{ id: 'm1', sequence_no: 1, role: 'assistant', message_type: 'brief_summary', text: '我理解你的需求。', created_at: '2026-07-30T12:00:00' }], steps: [{ id: 's1', ordinal: 1, stage: 'extracting_brief', status: 'completed', summary: '需求已整理', tool: 'brief_agent' }] })) })
    if (path.endsWith('/decisions')) { decisions += 1; return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(base('waiting_image_confirmation', { visual_direction: { summary: '现代产品主视图', selected_visual_skill: 'commercial-product-presentation', positive_prompt_summary: '环形灯体', negative_constraints: ['人物'], presentation_mode: 'single_hero', product_form: '环形结构', materials: '磨砂金属', color_plan: '暖白', composition: '主视图', scene: '桌面', avoid: ['人物'] } })) }) }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'success', data: [] }) })
  })
  await page.goto('/index.html')
  await expect(page.getByRole('button', { name: '生成文创产品' })).toBeVisible()
  await page.getByRole('button', { name: '协作式设计' }).click()
  await expect(page.getByRole('heading', { name: 'AI 文创产品设计助手' })).toBeVisible()
  await page.getByLabel('描述你的文创产品需求').fill('以三兔共耳设计现代桌面灯')
  await page.getByRole('button', { name: '开始设计' }).click()
  await expect(page.getByText('我理解的需求')).toBeVisible()
  await page.getByRole('button', { name: '确认需求方案' }).click()
  await expect(page.getByRole('heading', { name: '视觉方向', exact: true })).toBeVisible()
  expect(decisions).toBe(1)
})
