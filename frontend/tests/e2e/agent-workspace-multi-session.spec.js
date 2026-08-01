import { expect, test } from '@playwright/test'

const detail = (id, messages = []) => ({
  schema_version: 'agent-session-detail-v1', session_id: id, status: 'created', current_stage: 'created', revision_count: 0,
  generation_log_id: null, brief_summary: null, product_design: null, visual_direction: null, final_result: null,
  messages, steps: [], error: null, created_at: '2026-08-01T09:00:00', updated_at: '2026-08-01T09:00:00',
})

test('multi-session workspace keeps drafts, messages and structured turns isolated', async ({ page }) => {
  const sessions = { A: detail('A'), B: detail('B') }
  await page.addInitScript(() => { localStorage.setItem('token', 'offline-test-token'); localStorage.removeItem('agent_workspace_session') })
  await page.route('**/api/**', async (route) => {
    const request = route.request(); const path = new URL(request.url()).pathname
    const json = (data) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
    if (path === '/api/user/profile') return json({ status: 'success', user: { user_id: 'offline-user', username: 'offline-user' } })
    if (path === '/api/v2/agent-design/sessions' && request.method() === 'GET') return json({ status: 'success', data: ['A', 'B'].map((id) => ({ session_id: id, title: id === 'A' ? '敦煌书签' : '苗绣帆布包', status: 'created', updated_at: sessions[id].updated_at, has_pending_action: false })) })
    if (path === '/api/v2/agent-design/sessions' && request.method() === 'POST') return json({ status: 'success', data: detail('C') })
    if (path === '/api/v2/agent-design/sessions/A' && request.method() === 'GET') return json({ status: 'success', data: sessions.A })
    if (path === '/api/v2/agent-design/sessions/B' && request.method() === 'GET') return json({ status: 'success', data: sessions.B })
    if (path.endsWith('/assistant-turns') && request.method() === 'POST') {
      const id = path.split('/')[5]; const payload = request.postDataJSON()
      sessions[id].messages.push({ id: `${id}-u`, sequence_no: 1, role: 'user', message_type: 'runtime_request', text: payload.content, created_at: '2026-08-01T09:01:00' })
      sessions[id].messages.push({ id: `${id}-a`, sequence_no: 2, role: 'assistant', message_type: 'runtime_result', text: '需要补充', created_at: '2026-08-01T09:01:01', structured_output: { result: { kind: 'ask_user', question: `${id} 的补充问题`, missing_fields: ['材质'], reason_summary: '当前资料不足，需要你补充后继续。' } } })
      return json({ status: 'success', data: { run: { id: `run-${id}`, status: 'completed' }, replayed: false, display: { id: `run-${id}`, status: 'completed', safe_tool_events: ['inspect_design_state'], context_metadata: { compression_triggered: id === 'A', summary_version: id === 'A' ? 1 : null } } } })
    }
    return json({ status: 'success', data: [] })
  })
  await page.goto('/index.html')
  await page.getByRole('button', { name: '协作式设计' }).click()
  await expect(page.getByRole('heading', { name: '文创 Agent 工作区' })).toBeVisible()
  await page.getByRole('button', { name: /敦煌书签/ }).click()
  const composer = page.locator('.agent-composer textarea')
  await composer.fill('A 的独立草稿')
  await page.getByRole('button', { name: /苗绣帆布包/ }).click()
  await composer.fill('B 的独立草稿')
  await page.getByRole('button', { name: /敦煌书签/ }).click()
  await expect(composer).toHaveValue('A 的独立草稿')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByText('A 的补充问题')).toBeVisible()
  await expect(page.getByText('已整理较早的对话历史，关键目标和约束仍被保留')).toBeVisible()
  await page.getByRole('button', { name: /苗绣帆布包/ }).click()
  await expect(page.getByText('A 的补充问题')).toHaveCount(0)
  await expect(composer).toHaveValue('B 的独立草稿')
  await page.reload()
  await expect(page.getByRole('button', { name: /苗绣帆布包/ })).toHaveClass(/active/)
  await expect(page.getByText('图片将在方案确认后开放')).toBeVisible()
})
