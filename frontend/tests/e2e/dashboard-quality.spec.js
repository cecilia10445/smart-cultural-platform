import { expect, test } from '@playwright/test'

const runs = [
  { run_id: 'round-17c-business-20260728T010102Z-27e36a2', started_at: '2026-07-28T01:01:02Z', technical_status: 'completed', integrity_status: 'verified' },
  { run_id: 'round-17c-business-20260728T010101Z-27e36a2', started_at: '2026-07-28T01:01:01Z', technical_status: 'failed', integrity_status: 'verified' },
  { run_id: 'round-17c-business-20260728T010100Z-27e36a2', started_at: '2026-07-28T01:01:00Z', technical_status: 'completed', integrity_status: 'failed' },
]
const output = { product_copy: '清韵折叠阅读灯以竹木和半透明纸罩带来稳定柔和的阅读光线，适合书房和旅行阅读。', image_design_spec: '展开状态突出竹木纹理、透光纸罩与清晰可辨的折叠收纳结构。', used_source_ids: ['met-65625'] }
const completed = { status: 'success', data: { ...runs[0], report: { rag_status: 'grounded', source_ids: ['met-65625'], selected_skill_id: 'retail-product-copy', skill_version: '1.0.0', skill_body_sha256: 'a'.repeat(64), tool_trajectory: [{ tool: 'load_generation_skill', skill_id: 'retail-product-copy' }], planner_latency_ms: 100, final_latency_ms: 200, actual_calls: { qwen: 2, deepseek: 0, image: 0, database_writes: 0 } }, output } }

async function open(page, context) {
  const errors = []; page.on('pageerror', e => errors.push(e.message)); page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
  await context.addInitScript(() => { localStorage.setItem('adminToken', 'fixture'); localStorage.setItem('adminUser', JSON.stringify({ role: 'admin' })) })
  await page.route(/\/api\/dashboard\/business-generation-reports$/, route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'success', data: { runs, latest_run_id: runs[0].run_id } }) }))
  await page.route(/\/api\/dashboard\/business-generation-reports\/[^/]+$/, route => {
    const url = route.request().url(); const selected = runs.find(item => url.endsWith(item.run_id)) || runs[0]
    const data = selected.integrity_status === 'failed' ? { ...selected, report: null } : selected.technical_status === 'failed' ? { ...selected, report: null } : completed.data
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'success', data }) })
  })
  await page.goto('/dashboard.html'); await expect(page.getByRole('heading', { name: '把一次真实生成看清楚' })).toBeVisible(); return errors
}

test('运营页只展示业务生成、文本与轨迹', async ({ page, context }) => {
  const errors = await open(page, context)
  await expect(page.getByText('产品文案')).toBeVisible(); await expect(page.getByText('文字版设计说明')).toBeVisible()
  await expect(page.getByText('retail-product-copy · 1.0.0', { exact: true })).toBeVisible(); await expect(page.getByText(/load_generation_skill retail-product-copy/)).toBeVisible()
  await expect(page.getByText(/质量 Judge 暂未启用/)).toBeVisible(); await expect(page.getByText(/赢家|位置偏差|A\/B 交付/)).toHaveCount(0)
  expect(errors).toEqual([])
})

test('历史运行可切换且失败不显示输出', async ({ page, context }) => {
  const errors = await open(page, context); const select = page.getByLabel('选择历史运行')
  await select.selectOption(runs[1].run_id); await expect(page.getByText(/未通过完整性校验或未完成/)).toBeVisible()
  await select.selectOption(runs[0].run_id); await expect(page.getByText(output.product_copy)).toBeVisible(); expect(errors).toEqual([])
})

test('完整性失败时 fail closed', async ({ page, context }) => {
  const errors = await open(page, context); await page.getByLabel('选择历史运行').selectOption(runs[2].run_id)
  await expect(page.getByText(/已拒绝展示业务输出/)).toBeVisible(); await expect(page.getByText(output.product_copy)).toHaveCount(0); expect(errors).toEqual([])
})

test('调用数保持文本业务边界', async ({ page, context }) => {
  const errors = await open(page, context); await expect(page.locator('.facts').getByText('2', { exact: true })).toBeVisible(); await expect(page.getByText('0 / 0 / 0', { exact: true })).toBeVisible(); expect(errors).toEqual([])
})
