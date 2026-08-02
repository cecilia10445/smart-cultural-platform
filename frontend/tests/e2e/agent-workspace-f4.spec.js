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
      messages.push({ id: 'f4-agent-message', runtime_run_id: 'run-f4', role: 'assistant', message_type: 'runtime_result', text: '可以生成一版试稿。', created_at: '2026-08-02T09:01:01Z', structured_output: { message: '可以生成一版试稿。', intent: 'business_action_request', output_origin: 'provider', suggestions: [], artifact_proposal: null, business_action: { action: 'generate_image_from_conversation', reason_summary: '当前对话已形成可确认的试稿方向。' } } })
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

test('Conversation-scoped image action does not create a design task', async ({ page }) => {
  const messages = []
  const calls = { createTask: 0, request: 0, approve: 0, execute: 0 }
  await page.addInitScript(() => { localStorage.setItem('token', 'f4-test-token'); localStorage.setItem('userInfo', JSON.stringify({ user_id: 'f4-user', username: 'f4-user' })); localStorage.setItem('agent_workspace_session', 'f4-session') })
  await page.route('**/api/**', async (route) => {
    const request = route.request(); const path = new URL(request.url()).pathname
    const json = (data) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
    if (path === '/api/user/profile') return json({ status: 'success', user: { user_id: 'f4-user' } })
    if (path === '/api/v2/agent-design/sessions' && request.method() === 'GET') return json({ status: 'success', data: [{ session_id: 'f4-session', title: '自由讨论', conversation_status: 'active', status: 'created', updated_at: '2026-08-02T09:00:00Z' }] })
    if (path === '/api/v2/agent-design/sessions/f4-session' && request.method() === 'GET') return json({ status: 'success', data: session(messages) })
    if (path === '/api/v2/agent-design/sessions/f4-session/tasks') { if (request.method() === 'POST') calls.createTask += 1; return json({ status: 'success', data: [] }) }
    if (path === '/api/v2/agent-design/sessions/f4-session/artifacts') return json({ status: 'success', data: [] })
    if (path === '/api/v2/agent-design/sessions/f4-session/actions' && request.method() === 'GET') return json({ status: 'success', data: [] })
    if (path === '/api/v2/agent-design/sessions/f4-session/assistant-turns' && request.method() === 'POST') {
      messages.push({ id: 'free-user', role: 'user', message_type: 'runtime_request', text: request.postDataJSON().content, client_turn_id: request.postDataJSON().client_turn_id, created_at: '2026-08-02T09:01:00Z' })
      messages.push({ id: 'free-agent', runtime_run_id: 'run-free', role: 'assistant', message_type: 'runtime_result', text: '我可以根据当前对话生成一版试稿。', created_at: '2026-08-02T09:01:01Z', structured_output: { message: '我可以根据当前对话生成一版试稿。', intent: 'business_action_request', output_origin: 'provider', suggestions: [], artifact_proposal: null, business_action: { action: 'generate_image_from_conversation', reason_summary: '当前对话已形成可确认的试稿方向。' } } })
      return json({ status: 'success', data: { run: { id: 'run-free', status: 'completed' }, display: {} } })
    }
    if (path.endsWith('/assistant-turns/run-free/action-proposal')) return json({ status: 'success', data: { source_runtime_run_id: 'run-free', action_type: 'generate_image_from_conversation', source_proposal_digest: 'b'.repeat(64), display: { source_type: 'conversation_snapshot', confirmed_constraints: ['竹编收纳筐'], tentative_assumptions: ['试稿'], presentation_mode: 'three_view' } } })
    if (path === '/api/v2/agent-design/sessions/f4-session/actions' && request.method() === 'POST') { calls.request += 1; return json({ status: 'success', data: { id: 'free-action', action_type: 'generate_image_from_conversation', status: 'requested', task_id: null, safe_summary: '生成一张试稿' } }) }
    if (path === '/api/v2/agent-design/actions/free-action/approve') { calls.approve += 1; return json({ status: 'success', data: { id: 'free-action', status: 'approved' } }) }
    if (path === '/api/v2/agent-design/actions/free-action/execute') { calls.execute += 1; return json({ status: 'success', data: { action: { id: 'free-action', status: 'completed' }, created_artifact_ids: ['free-image'] } }) }
    return json({ status: 'success', data: [] })
  })
  await page.goto('/index.html')
  await page.getByLabel('描述你的文创产品需求').fill('请先为竹编收纳筐出一版三视图')
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByText('生成一张试稿')).toBeVisible()
  await page.getByLabel(/我同意使用以上暂定假设/).check()
  await page.getByRole('button', { name: '确认生成' }).click()
  await expect.poll(() => calls.execute).toBe(1)
  expect(calls.request).toBe(1); expect(calls.approve).toBe(1); expect(calls.createTask).toBe(0)
})

test('Task API unavailability is distinct from an empty design project and keeps chat available', async ({ page }) => {
  let taskCalls = 0
  await page.addInitScript(() => { localStorage.setItem('token', 'f4-test-token'); localStorage.setItem('userInfo', JSON.stringify({ user_id: 'f4-user', username: 'f4-user' })); localStorage.setItem('agent_workspace_session', 'f4-session') })
  await page.route('**/api/**', async (route) => {
    const request = route.request(); const path = new URL(request.url()).pathname
    const json = (data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })
    if (path === '/api/user/profile') return json({ status: 'success', user: { user_id: 'f4-user' } })
    if (path === '/api/v2/agent-design/sessions' && request.method() === 'GET') return json({ status: 'success', data: [{ session_id: 'f4-session', title: '陶瓷杯垫讨论', conversation_status: 'active', status: 'created', updated_at: '2026-08-02T09:00:00Z' }] })
    if (path === '/api/v2/agent-design/sessions/f4-session' && request.method() === 'GET') return json({ status: 'success', data: session() })
    if (path === '/api/v2/agent-design/sessions/f4-session/tasks' && request.method() === 'GET') { taskCalls += 1; return json({ status: 'unavailable', code: 'AGENT_PERSISTENCE_UNAVAILABLE', message: 'Agent session data service is temporarily unavailable.' }, 503) }
    return json({ status: 'success', data: [] })
  })

  await page.goto('/index.html')
  await expect(page.getByText('设计档案暂时无法加载')).toBeVisible()
  await expect(page.getByText('普通对话仍可继续。请稍后重试读取设计项目与版本记录。')).toBeVisible()
  await expect(page.getByLabel('描述你的文创产品需求')).toBeEnabled()
  await expect(page.getByText('未建立设计项目')).toHaveCount(0)
  await page.getByRole('button', { name: '重试读取' }).click()
  await expect.poll(() => taskCalls).toBe(2)
})

test('Agent generation history opens a read-only projection and continues with its task only on demand', async ({ page }) => {
  const calls = { detail: 0, select: 0 }
  const task = { id: 'task-history', session_id: 'history-session', title: '景德镇杯垫', status: 'active', version: 1, origin: 'native', created_at: '2026-08-02T09:00:00Z', updated_at: '2026-08-02T09:00:00Z', is_active: false }
  await page.addInitScript(() => { localStorage.setItem('token', 'f4-test-token'); localStorage.setItem('userInfo', JSON.stringify({ user_id: 'f4-user', username: 'f4-user' })) })
  await page.route('**/api/**', async (route) => {
    const request = route.request(); const path = new URL(request.url()).pathname
    const json = (data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })
    if (path === '/api/user/profile') return json({ status: 'success', user: { user_id: 'f4-user' } })
    if (path === '/api/user/history') return json({ status: 'success', data: [
      { record_type: 'agent_artifact_image', log_id: 81, product_name: '景德镇杯垫试稿', image_url: 'mock://generated/history-v2', timestamp: '2026-08-02T10:00:00Z', generation_kind: 'agent_action_image' },
      { record_type: 'fast_generation', log_id: 82, product_name: '普通快速生成', image_url: '/static/fast.png', prompt_template_version: 'cultural-product-rag-v2', timestamp: '2026-08-02T10:01:00Z' },
      { record_type: 'unknown_generation', log_id: 83, title: '未知记录', generation_kind: 'provider_future_kind', timestamp: '2026-08-02T10:02:00Z' },
    ], pagination: { total: 3, has_more: false } })
    if (path === '/api/v2/agent-design/history/generation-logs/81') {
      calls.detail += 1
      return json({ status: 'success', data: {
        kind: 'agent_artifact_image', read_only: true,
        generation_log: { id: 81, title: '景德镇杯垫试稿', image_url: 'mock://generated/history-v2', created_at: '2026-08-02T10:00:00Z', generation_kind: 'agent_action_image' },
        image_artifact: { id: 'image-v2', artifact_type: 'generated_image', status: 'confirmed', version_number: 2, parent_artifact_id: 'image-v1' },
        source_action: { id: 'action-v2', action_type: 'regenerate_image', status: 'completed', safe_summary: '基于上一版调整釉色' },
        source_task: { id: 'task-history', title: '景德镇杯垫', status: 'active', origin: 'native', version: 1 },
        related_artifacts: [{ id: 'brief-v1', artifact_type: 'brief', status: 'confirmed', version_number: 1, summary: '陶瓷杯垫方向', origin: 'native' }],
        generation_snapshot: { source_type: 'regeneration_snapshot', confirmed_constraints: ['陶瓷杯垫'], tentative_assumptions: ['青绿色'], presentation_mode: 'single_hero' },
        version_lineage: { version_number: 2, parent_artifact_id: 'image-v1', parent_version_number: 1 },
        continue_design: { session_id: 'history-session', task_id: 'task-history', available: true },
      } })
    }
    if (path === '/api/v2/agent-design/sessions' && request.method() === 'GET') return json({ status: 'success', data: [{ session_id: 'history-session', title: '景德镇杯垫讨论', conversation_status: 'active', status: 'created', updated_at: '2026-08-02T10:00:00Z' }] })
    if (path === '/api/v2/agent-design/sessions/history-session' && request.method() === 'GET') return json({ status: 'success', data: { ...session(), session_id: 'history-session' } })
    if (path === '/api/v2/agent-design/sessions/history-session/tasks' && request.method() === 'GET') return json({ status: 'success', data: [task] })
    if (path === '/api/v2/agent-design/sessions/history-session/tasks/task-history/select') { calls.select += 1; return json({ status: 'success', data: task }) }
    if (path.includes('/tasks/task-history/artifacts') || path.includes('/tasks/task-history/actions')) return json({ status: 'success', data: [] })
    return json({ status: 'success', data: [] })
  })

  await page.goto('/index.html')
  await page.getByRole('button', { name: '记录' }).click()
  const agentCard = page.locator('.history-entry').filter({ hasText: '景德镇杯垫试稿' })
  await agentCard.getByRole('button', { name: '查看详情' }).click()
  await expect(page.getByRole('heading', { name: '景德镇杯垫试稿' })).toBeVisible()
  await expect(page.getByText('基于上一版调整釉色')).toBeVisible()
  await expect(page.getByText('V2')).toBeVisible()
  expect(calls.detail).toBe(1)
  await page.getByRole('button', { name: '继续设计' }).click()
  await expect(page.getByLabel('描述你的文创产品需求')).toBeVisible()
  expect(page.url()).toContain('agent_session_id=history-session')
  expect(page.url()).toContain('agent_task_id=task-history')
  await expect.poll(() => calls.select).toBe(1)
  const unknownCard = page.locator('.history-entry').filter({ hasText: '未知记录' })
  await page.getByRole('button', { name: '记录' }).click()
  await unknownCard.getByRole('button', { name: '查看详情' }).click()
  await expect(page.getByText('未识别的生成类型')).toBeVisible()
  expect(calls.detail).toBe(1)
})
