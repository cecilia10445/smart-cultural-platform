import { expect, test } from '@playwright/test'

const detail = (id, messages = []) => ({
  schema_version: 'agent-session-detail-v1', session_id: id, status: 'created', current_stage: 'created', revision_count: 0,
  generation_log_id: null, brief_summary: null, product_design: null, visual_direction: null, final_result: null,
  messages, steps: [], error: null, created_at: '2026-08-01T09:00:00', updated_at: '2026-08-01T09:00:00',
})

test('multi-session workspace keeps drafts, messages and structured turns isolated', async ({ page }) => {
  const sessions = { A: detail('A'), B: detail('B') }
  let creativeContinuationPersisted = false
  let assistantTurnCalls = 0
  let createCalls = 0
  let releaseFirstTurn
  const firstTurnGate = new Promise((resolve) => { releaseFirstTurn = resolve })
  await page.addInitScript(() => { localStorage.setItem('token', 'offline-test-token'); localStorage.setItem('userInfo', JSON.stringify({ user_id: 'offline-user', username: 'offline-user' })); localStorage.removeItem('agent_workspace_session') })
  await page.route('**/api/**', async (route) => {
    const request = route.request(); const path = new URL(request.url()).pathname
    const json = (data) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
    if (path === '/api/user/profile') return json({ status: 'success', user: { user_id: 'offline-user', username: 'offline-user' } })
    if (path === '/api/v2/agent-design/sessions' && request.method() === 'GET') return json({ status: 'success', data: ['A', 'B'].map((id) => ({ session_id: id, title: id === 'A' ? '敦煌书签' : '苗绣帆布包', status: 'created', updated_at: sessions[id].updated_at, has_pending_action: false })) })
    if (path === '/api/v2/agent-design/sessions' && request.method() === 'POST') { createCalls += 1; return json({ status: 'success', data: detail('C') }) }
    if (path === '/api/v2/agent-design/sessions/A' && request.method() === 'GET') return json({ status: 'success', data: sessions.A })
    if (path === '/api/v2/agent-design/sessions/B' && request.method() === 'GET') return json({ status: 'success', data: sessions.B })
    if (path.endsWith('/assistant-turns') && request.method() === 'POST') {
      const id = path.split('/')[5]; const payload = request.postDataJSON()
      assistantTurnCalls += 1
      if (payload.content.includes('按纯创意方向继续讨论')) creativeContinuationPersisted = true
      if (assistantTurnCalls === 1) await firstTurnGate
      sessions[id].messages.push({ id: `${id}-u-${assistantTurnCalls}`, sequence_no: assistantTurnCalls * 2 - 1, role: 'user', message_type: 'runtime_request', text: payload.content, client_turn_id: payload.client_turn_id, created_at: '2026-08-01T09:01:00' })
      sessions[id].messages.push({ id: `${id}-a-${assistantTurnCalls}`, sequence_no: assistantTurnCalls * 2, role: 'assistant', message_type: 'runtime_result', text: `${id} 的补充问题`, created_at: '2026-08-01T09:01:01', structured_output: { message: `${id} 的补充问题`, intent: 'clarification', suggestions: id === 'A' ? [{ label: '继续按纯创意方向讨论', draft_text: '请按纯创意方向继续讨论，避免编造文化资料或出处。' }] : [], artifact_proposal: null, business_action: null, output_origin: 'provider' } })
      return json({ status: 'success', data: { run: { id: `run-${id}`, status: 'completed' }, replayed: false, display: { id: `run-${id}`, status: 'completed', safe_tool_events: ['inspect_design_state'], context_metadata: { compression_triggered: id === 'A', summary_version: id === 'A' ? 1 : null } } } })
    }
    return json({ status: 'success', data: [] })
  })
  await page.goto('/index.html')
  await page.getByRole('button', { name: '协作式设计' }).click()
  await expect(page.getByRole('heading', { name: '文创 Agent 工作区' })).toBeVisible()
  await page.locator('.new-session').click()
  await expect(page.getByRole('heading', { name: '新对话' })).toBeVisible()
  await expect(page.locator('.session-item').filter({ hasText: '新建对话' })).toBeVisible()
  expect(createCalls).toBe(0)
  await page.getByRole('button', { name: /敦煌书签/ }).click()
  await expect(page.getByRole('heading', { name: '敦煌书签' })).toBeVisible()
  const composer = page.locator('.agent-composer textarea')
  await composer.fill('A 的独立草稿')
  await page.getByRole('button', { name: /苗绣帆布包/ }).click()
  await expect(page.getByRole('heading', { name: '苗绣帆布包' })).toBeVisible()
  await composer.fill('B 的独立草稿')
  await page.getByRole('button', { name: /敦煌书签/ }).click()
  await expect(page.getByRole('heading', { name: '敦煌书签' })).toBeVisible()
  await expect(composer).toHaveValue('A 的独立草稿')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByText('A 的独立草稿')).toBeVisible()
  await expect(page.getByText('正在发送并等待设计助手回应…')).toBeVisible()
  releaseFirstTurn()
  await expect(page.getByText('A 的补充问题')).toBeVisible()
  await page.getByRole('button', { name: '继续按纯创意方向讨论' }).click()
  await expect(composer).toHaveValue('请按纯创意方向继续讨论，避免编造文化资料或出处。')
  expect(assistantTurnCalls).toBe(1)
  expect(creativeContinuationPersisted).toBe(false)
  await page.getByRole('button', { name: '发送' }).click()
  await expect.poll(() => creativeContinuationPersisted).toBe(true)
  await expect(page.getByText('已整理较早的对话历史，关键目标和约束仍被保留')).toBeVisible()
  await page.getByRole('button', { name: /苗绣帆布包/ }).click()
  await expect(page.getByText('A 的补充问题')).toHaveCount(0)
  await expect(composer).toHaveValue('B 的独立草稿')
  await page.reload()
  await expect(page.getByRole('button', { name: /苗绣帆布包/ })).toHaveClass(/active/)
  await expect(page.getByText('图片将在方案确认后开放', { exact: true })).toBeVisible()
})

test('workspace suppresses protocol output and only renders a V2-valid Brief attachment', async ({ page }) => {
  const unsafe = 'The previous output was invalid. Here is the corrected compact JSON envelope.'
  const sessions = {
    V2: detail('V2', [
      { id: 'u-1', sequence_no: 1, role: 'user', message_type: 'runtime_request', text: '先出一版', created_at: '2026-08-01T10:00:00' },
      { id: 'a-unsafe', sequence_no: 2, role: 'assistant', message_type: 'runtime_result', text: unsafe, created_at: '2026-08-01T10:00:01', structured_output: {
        message: unsafe, intent: 'general_answer', output_origin: 'provider_repair', suggestions: [], business_action: null,
        artifact_proposal: { kind: 'brief', valid: true, summary: unsafe, content: {} },
      } },
      { id: 'a-brief', sequence_no: 3, role: 'assistant', message_type: 'runtime_result', text: '我已整理成一版正式 Brief，仍未保存。', created_at: '2026-08-01T10:00:02', structured_output: {
        message: '我已整理成一版正式 Brief，仍未保存。', intent: 'brief_proposal', output_origin: 'provider', suggestions: [], business_action: null,
        artifact_proposal: { kind: 'brief', valid: true, summary: '现代陶杯垫的设计方向与使用边界。', content: { product_type: '陶杯垫', design_goal: '适合日常书桌使用' } },
      } },
    ]),
  }
  await page.addInitScript(() => { localStorage.setItem('token', 'offline-test-token'); localStorage.setItem('userInfo', JSON.stringify({ user_id: 'offline-user', username: 'offline-user' })); localStorage.setItem('agent_workspace_session', 'V2') })
  await page.route('**/api/**', async (route) => {
    const request = route.request(); const path = new URL(request.url()).pathname
    const json = (data) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
    if (path === '/api/user/profile') return json({ status: 'success', user: { user_id: 'offline-user', username: 'offline-user' } })
    if (path === '/api/v2/agent-design/sessions' && request.method() === 'GET') return json({ status: 'success', data: [{ session_id: 'V2', title: '陶杯垫讨论', status: 'created', updated_at: sessions.V2.updated_at, has_pending_action: false }] })
    if (path === '/api/v2/agent-design/sessions/V2' && request.method() === 'GET') return json({ status: 'success', data: sessions.V2 })
    return json({ status: 'success', data: [] })
  })
  await page.goto('/index.html')
  await page.getByRole('button', { name: '协作式设计' }).click()
  await expect(page.getByText(unsafe)).toHaveCount(0)
  await expect(page.getByText('本轮智能协作未能生成有效回复，请重新尝试。')).toBeVisible()
  await expect(page.getByText('我已整理成一版正式 Brief，仍未保存。')).toBeVisible()
  await expect(page.getByText('设计 Brief（尚未保存）')).toBeVisible()
  await expect(page.getByText('尚未保存为正式设计稿。')).toBeVisible()
  await expect(page.getByText('初步设计方案')).toHaveCount(0)
})
