import { expect, test } from '@playwright/test'

const session = (messages = []) => ({
  schema_version: 'agent-session-detail-v1', session_id: 'f4-session', status: 'created', current_stage: 'created', version: 1,
  messages, steps: [], brief_summary: null, product_design: null, visual_direction: null, final_result: null,
  revision_count: 0, generation_log_id: null, error: null, created_at: '2026-08-02T09:00:00Z', updated_at: '2026-08-02T09:00:00Z',
})

test('F4 workspace keeps conversation primary and only executes after an explicit confirmation', async ({ page }) => {
  const messages = []
  const calls = { request: 0, approve: 0, execute: 0 }
  const task = { id: 'task-f4', session_id: 'f4-session', title: '陶瓷杯垫', status: 'active', version: 1, origin: 'native', created_at: '2026-08-02T09:00:00Z', updated_at: '2026-08-02T09:00:00Z', is_active: true }
  const artifacts = []
  await page.addInitScript(() => { localStorage.setItem('token', 'f4-test-token'); localStorage.setItem('userInfo', JSON.stringify({ user_id: 'f4-user', username: 'f4-user' })); localStorage.setItem('agent_workspace_session', 'f4-session') })
  await page.route('**/api/**', async (route) => {
    const request = route.request(); const path = new URL(request.url()).pathname
    const json = (data) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
    if (path === '/api/user/profile') return json({ status: 'success', user: { user_id: 'f4-user' } })
    if (path === '/api/v2/agent-design/sessions' && request.method() === 'GET') return json({ status: 'success', data: [{ session_id: 'f4-session', title: '陶瓷杯垫讨论', conversation_status: 'active', status: 'created', updated_at: '2026-08-02T09:00:00Z', has_pending_action: false }] })
    if (path === '/api/v2/agent-design/sessions/f4-session' && request.method() === 'GET') return json({ status: 'success', data: session(messages) })
    if (path === '/api/v2/agent-design/sessions/f4-session/tasks' && request.method() === 'GET') return json({ status: 'success', data: [task] })
    if (path === '/api/v2/agent-design/sessions/f4-session/tasks/task-f4/artifacts') return json({ status: 'success', data: artifacts })
    if (path === '/api/v2/agent-design/sessions/f4-session/tasks/task-f4/actions' && request.method() === 'GET') return json({ status: 'success', data: [] })
    if (path === '/api/v2/agent-design/sessions/f4-session/assistant-turns' && request.method() === 'POST') {
      messages.push({ id: 'f4-user-message', role: 'user', message_type: 'runtime_request', text: request.postDataJSON().content, client_turn_id: request.postDataJSON().client_turn_id, created_at: '2026-08-02T09:01:00Z' })
      messages.push({ id: 'f4-agent-message', role: 'assistant', message_type: 'runtime_result', text: '可以生成一版试稿。', created_at: '2026-08-02T09:01:01Z', structured_output: { message: '可以生成一版试稿。', intent: 'business_action_request', output_origin: 'provider', suggestions: [], artifact_proposal: null, business_action: { action: 'generate_image_from_conversation', reason_summary: '当前对话已形成可确认的试稿方向。' } } })
      return json({ status: 'success', data: { run: { id: 'run-f4', status: 'completed' }, display: {} } })
    }
    if (path.endsWith('/assistant-turns/run-f4/action-proposal')) return json({ status: 'success', data: { source_runtime_run_id: 'run-f4', action_type: 'generate_image_from_conversation', source_proposal_digest: 'a'.repeat(64), display: { source_type: 'conversation_snapshot', confirmed_constraints: ['陶瓷杯垫'], tentative_assumptions: ['青绿色'], presentation_mode: 'single_hero' } } })
    if (path.endsWith('/actions') && request.method() === 'POST') { calls.request += 1; return json({ status: 'success', data: { id: 'action-f4', action_type: 'generate_image_from_conversation', status: 'requested', task_id: 'task-f4', safe_summary: '生成一张试稿' } }) }
    if (path === '/api/v2/agent-design/actions/action-f4/approve') { calls.approve += 1; return json({ status: 'success', data: { id: 'action-f4', status: 'approved' } }) }
    if (path === '/api/v2/agent-design/actions/action-f4/execute') { calls.execute += 1; artifacts.push({ id: 'image-f4', task_id: 'task-f4', artifact_type: 'generated_image', status: 'confirmed', version_number: 1, parent_artifact_id: null, origin: 'native', safe_content: { image_url: 'mock://generated/f4', source_type: 'conversation_snapshot' } }); return json({ status: 'success', data: { action: { id: 'action-f4', status: 'completed' }, created_artifact_ids: ['image-f4'], superseded_artifact_ids: [], task } }) }
    return json({ status: 'success', data: [] })
  })

  await page.goto('/index.html')
  await expect(page.getByRole('button', { name: '协作式设计' })).toHaveClass(/active/)
  await expect(page.locator('.workspace-nav')).toHaveCount(0)
  await expect(page.locator('.agent-workspace')).toBeVisible()
  await expect(page.getByText('把想法说出来')).toBeVisible()
  await page.getByLabel('描述你的文创产品需求').fill('先为陶瓷杯垫出一版试稿')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByText('准备生成试稿').or(page.getByText('生成一张试稿'))).toBeVisible()
  expect(calls.request).toBe(0); expect(calls.approve).toBe(0); expect(calls.execute).toBe(0)
  await page.getByLabel(/我同意使用以上暂定假设/).check()
  await page.getByRole('button', { name: '确认生成' }).click()
  await expect.poll(() => calls.execute).toBe(1)
  await expect(page.getByText('试稿 V1')).toBeVisible()
  await expect(page.getByLabel('描述你的文创产品需求')).toBeEnabled()
})
