<template>
  <main class="quality-page">
    <header class="quality-header">
      <a class="brand" href="/index.html" aria-label="智能文创平台，返回创作页">
        <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>
        <span>智能文创平台</span>
      </a>
      <div class="header-title">
        <span>运营空间</span>
        <strong>AI 质量评测</strong>
      </div>
      <div class="account-area">
        <span>{{ userName }}</span>
        <button type="button" class="quiet-button" @click="logout">退出登录</button>
      </div>
    </header>

    <div class="quality-main">
      <section class="intro-row" aria-labelledby="quality-title">
        <div>
          <p class="eyebrow">OFFLINE SECURITY &amp; ROBUSTNESS REGRESSION</p>
          <h1 id="quality-title">把评测结果看清楚</h1>
          <p class="intro-copy">只展示脱敏后的 Promptfoo 回归结果，帮助运营团队快速识别结构、引用、事实和泄漏风险。</p>
        </div>
        <div class="intro-actions">
          <button type="button" class="secondary-button" :disabled="loading" @click="loadReport">{{ loading ? '正在刷新' : '刷新评测' }}</button>
          <button type="button" class="primary-button" :disabled="!report || downloading" @click="downloadReport">{{ downloading ? '正在准备报告' : '下载完整 Promptfoo 报告' }}</button>
        </div>
      </section>

      <div v-if="qualityError" class="state-card unavailable" role="alert">
        <span class="state-symbol" aria-hidden="true">!</span>
        <div><strong>{{ qualityError }}</strong><p>请检查最近一次离线评测产物后再刷新。</p></div>
        <a class="text-link" href="/login.html">返回登录</a>
      </div>
      <div v-else-if="loading" class="state-card loading-state" aria-live="polite">正在读取最近一次离线评测。</div>

      <template v-else-if="report">
        <section class="run-summary" aria-labelledby="run-title">
          <div class="section-label"><span class="status-dot" :data-status="report.run_status"></span><span>最近一次评测</span></div>
          <div class="run-summary-main">
            <div><h2 id="run-title">{{ statusLabel(report.run_status) }}</h2><p>{{ formatDate(report.generated_at) }} · {{ report.run_id }}</p></div>
            <div class="trust-note"><strong>离线安全与鲁棒性回归</strong><span>executor_type=stub · measurement_scope=harness_self_test</span></div>
          </div>
        </section>

        <section aria-labelledby="metrics-title">
          <div class="section-heading"><p class="eyebrow">MEASUREMENT</p><h2 id="metrics-title">核心指标</h2></div>
          <div class="metric-grid">
            <article v-for="metric in metrics" :key="metric.key" class="metric-card"><span>{{ metric.label }}</span><strong>{{ displayMetric(metric.key) }}</strong><small>{{ metric.note }}</small></article>
          </div>
        </section>

        <section class="risk-section" aria-labelledby="risk-title">
          <div class="section-heading"><p class="eyebrow">RISK REGISTER</p><h2 id="risk-title">风险类别</h2></div>
          <div class="risk-grid">
            <article v-for="risk in riskMetrics" :key="risk.key" class="risk-card"><div><span>{{ risk.label }}</span><small>{{ risk.note }}</small></div><strong :data-alert="report[risk.key] > 0">{{ report[risk.key] }}</strong></article>
          </div>
          <dl class="category-list"><div v-for="(counts, category) in report.security_categories" :key="category"><dt>{{ categoryLabel(category) }}</dt><dd><span>{{ counts.passed }} 通过</span><span>{{ counts.failed }} 失败</span><span>{{ counts.error }} 错误</span></dd></div></dl>
        </section>

        <section class="cases-section" aria-labelledby="cases-title">
          <div class="section-heading cases-heading"><div><p class="eyebrow">REDACTED CASE REGISTER</p><h2 id="cases-title">逐用例脱敏明细</h2></div><button type="button" class="secondary-button" @click="showCases = !showCases">{{ showCases ? '收起用例' : `查看全部 ${report.cases.length} 项` }}</button></div>
          <div v-if="showCases" class="cases-panel">
            <div class="filter-row" role="group" aria-label="按评测结果筛选"><button v-for="filter in filters" :key="filter.id" type="button" class="filter-button" :class="{ active: activeFilter === filter.id }" :aria-pressed="activeFilter === filter.id" @click="activeFilter = filter.id">{{ filter.label }}<span>{{ filterCount(filter.id) }}</span></button></div>
            <div class="case-list"><article v-for="caseItem in filteredCases" :key="caseItem.case_id" class="case-row"><div class="case-name"><span class="outcome-mark" :data-outcome="caseItem.outcome"></span><strong>{{ categoryLabel(caseItem.category) }}</strong><small>{{ caseItem.case_id }}</small></div><dl><div><dt>结果</dt><dd>{{ outcomeLabel(caseItem.outcome) }}</dd></div><div><dt>稳定码</dt><dd>{{ caseItem.stable_code }}</dd></div><div><dt>断言</dt><dd>{{ assertionLabel(caseItem.assertion_name) }}</dd></div></dl></article></div>
          </div>
        </section>

        <p class="disclaimer">本页是离线安全与鲁棒性回归的脱敏汇总；23/23 通过只代表当前 Stub 测试契约通过，不代表真实模型绝对安全。</p>
      </template>
    </div>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

const report = ref(null)
const loading = ref(true)
const downloading = ref(false)
const qualityError = ref('')
const userName = ref('运营管理员')
const showCases = ref(false)
const activeFilter = ref('all')

const metrics = [
  { key: 'total', label: '总用例', note: '当前回归范围' },
  { key: 'passed', label: '通过', note: '边界保持有效' },
  { key: 'failed', label: '失败', note: '需要复核' },
  { key: 'error', label: '错误', note: '执行异常' },
  { key: 'attack_success_rate', label: '攻击成功率', note: '失败 / 总用例' },
]
const riskMetrics = [
  { key: 'leakage_count', label: 'Prompt / 凭据泄漏', note: 'Prompt、凭据、Authorization' },
  { key: 'invalid_citation_count', label: '非法引用', note: '来源与证据边界' },
  { key: 'factual_overreach_count', label: '事实越界', note: '时代、作者、机构与馆藏' },
  { key: 'invalid_structure_count', label: '结构错误', note: '输入与响应契约' },
]
const filters = [
  { id: 'all', label: '全部' },
  { id: 'passed', label: '通过' },
  { id: 'failed', label: '失败' },
  { id: 'error', label: '错误' },
]
const categoryNames = {
  'unknown-field': '未知字段', 'invalid-json': '非法 JSON', 'field-type': '类型错误',
  'long-input': '超长输入', 'long-facts': '超长事实数组', 'malicious-url': '恶意 URL',
  xss: 'HTML / XSS', unicode: 'Unicode 绕过', 'fake-origin': '伪造数据来源',
  'fake-source': '伪造来源引用', 'malformed-evidence': '损坏证据', 'out-of-bounds-source': '越界引用',
  'grounded-empty-citation': 'grounded 引用冲突', 'insufficient-with-citation': '资料不足引用冲突',
  'prompt-leak': 'Prompt 泄漏', 'credential-leak': '凭据泄漏', 'authorization-leak': 'Authorization 泄漏',
  'fake-era': '伪造年代', 'fake-author': '伪造作者', 'fake-endorsement': '伪造机构背书',
  'fake-collection': '伪造官方馆藏', 'fake-history': '伪造历史事实', 'web-as-museum': '网页冒充馆藏',
}
const token = () => localStorage.getItem('adminToken') || localStorage.getItem('token')

const normalizedReport = (value) => {
  const data = value?.data
  if (value?.status !== 'success' || !data || !Array.isArray(data.cases) || data.cases.some((item) => {
    return !item || typeof item.case_id !== 'string' || !categoryNames[item.category] || !['passed', 'failed', 'error'].includes(item.outcome) || typeof item.stable_code !== 'string' || typeof item.assertion_name !== 'string'
  })) return null
  return data
}

const loadReport = async () => {
  loading.value = true
  qualityError.value = ''
  try {
    if (!token()) { qualityError.value = '登录状态已失效，请重新登录。'; return }
    const response = await fetch('/api/dashboard/quality-report', { headers: { Authorization: `Bearer ${token()}` } })
    const body = await response.json().catch(() => ({}))
    if (response.status === 401 || body.code === 'AUTH_REQUIRED') { qualityError.value = '登录状态已失效，请重新登录。'; return }
    if (response.status === 503 || body.code === 'QUALITY_REPORT_UNAVAILABLE') { qualityError.value = '最近评测报告暂不可用。'; return }
    if (!response.ok) { qualityError.value = '质量评测加载失败，请稍后重试。'; return }
    const safeReport = normalizedReport(body)
    if (!safeReport) { qualityError.value = '最近评测报告暂不可用。'; return }
    report.value = safeReport
  } catch { qualityError.value = '质量评测加载失败，请检查网络后重试。' }
  finally { loading.value = false }
}

const downloadReport = async () => {
  if (!token() || downloading.value) return
  downloading.value = true
  qualityError.value = ''
  try {
    const response = await fetch('/api/dashboard/quality-report/html', { headers: { Authorization: `Bearer ${token()}` } })
    if (response.status === 401) { qualityError.value = '登录状态已失效，请重新登录。'; return }
    if (response.status === 503) { qualityError.value = '完整评测报告暂不可用。'; return }
    if (!response.ok) { qualityError.value = '完整评测报告下载失败，请稍后重试。'; return }
    const url = URL.createObjectURL(await response.blob())
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'promptfoo-security-report.html'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  } catch { qualityError.value = '完整评测报告下载失败，请检查网络后重试。' }
  finally { downloading.value = false }
}

const filteredCases = computed(() => !report.value ? [] : report.value.cases.filter((item) => activeFilter.value === 'all' || item.outcome === activeFilter.value))
const filterCount = (filter) => filter === 'all' ? report.value.cases.length : report.value.cases.filter((item) => item.outcome === filter).length
const categoryLabel = (category) => categoryNames[category] || '其他安全边界'
const outcomeLabel = (outcome) => ({ passed: '通过', failed: '失败', error: '错误' }[outcome] || '未知')
const assertionLabel = (name) => ({ security_boundary: '安全边界断言', json_shape: 'JSON 结构断言', provider_error: 'Provider 错误' }[name] || '固定断言')
const statusLabel = (status) => ({ passed: '评测通过', failed: '存在失败用例', error: '评测执行异常' }[status] || '状态未知')
const displayMetric = (key) => key === 'attack_success_rate' ? `${Math.round(Number(report.value[key] || 0) * 100)}%` : report.value[key]
const formatDate = (value) => { const date = new Date(value); return Number.isNaN(date.getTime()) ? '时间不可用' : date.toLocaleString('zh-CN') }
const logout = () => { localStorage.removeItem('adminToken'); localStorage.removeItem('adminUser'); localStorage.removeItem('token'); localStorage.removeItem('userInfo'); window.location.href = '/login.html' }

onMounted(() => {
  const storedUser = localStorage.getItem('adminUser') || localStorage.getItem('userInfo')
  if (storedUser) {
    try { const parsed = JSON.parse(storedUser); if (parsed.role === 'admin') userName.value = parsed.name || parsed.username || userName.value } catch { /* ignore malformed local identity */ }
  }
  loadReport()
})
</script>

<style>
:root { color: #17221f; background: #f3f0e8; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; min-width: 320px; background: #f3f0e8; }
button { font: inherit; }
button:focus-visible, a:focus-visible { outline: 3px solid #a44536; outline-offset: 3px; }
.quality-page { min-height: 100vh; overflow-x: hidden; background: #f3f0e8; }
.quality-header { min-height: 74px; padding: 0 clamp(1rem, 5vw, 5rem); display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 1.5rem; border-bottom: 1px solid #c9c3b6; background: #fbfaf5; }
.brand { display: inline-flex; align-items: center; gap: .65rem; width: fit-content; color: #17221f; text-decoration: none; font-weight: 750; letter-spacing: .04em; }
.brand-mark { width: 28px; height: 28px; display: grid; place-content: center; gap: 3px; border: 1px solid #245244; border-radius: 50%; transform: rotate(-8deg); }
.brand-mark i { display: block; width: 12px; height: 2px; background: #245244; }.brand-mark i:nth-child(2) { width: 16px; background: #a44536; }.brand-mark i:nth-child(3) { width: 8px; margin-left: 4px; }
.header-title { display: flex; align-items: baseline; gap: .7rem; color: #5c655e; font-size: .77rem; letter-spacing: .08em; }.header-title strong { color: #17221f; font-size: 1rem; }
.account-area { display: flex; justify-content: flex-end; align-items: center; gap: 1rem; color: #4f5a51; font-size: .88rem; }.quiet-button, .text-link { color: #245244; background: transparent; border: 0; cursor: pointer; text-decoration: underline; text-underline-offset: .25rem; }
.quality-main { width: min(1180px, calc(100% - 2rem)); margin: 0 auto; padding: clamp(2rem, 5vw, 4.5rem) 0 4rem; }
.intro-row { display: flex; justify-content: space-between; align-items: end; gap: 2rem; padding-bottom: 2.25rem; border-bottom: 2px solid #17221f; }.eyebrow { margin: 0 0 .7rem; color: #245244; font-size: .7rem; font-weight: 750; letter-spacing: .15em; }.intro-row h1 { max-width: 18ch; margin: 0; font-size: clamp(2.3rem, 5vw, 5rem); line-height: 1.06; letter-spacing: -.045em; }.intro-copy { max-width: 42rem; margin: 1rem 0 0; color: #5b655d; line-height: 1.7; }.intro-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .7rem; }
.primary-button, .secondary-button { min-height: 44px; padding: .7rem 1rem; border: 1px solid #17221f; cursor: pointer; font-weight: 700; }.primary-button { color: #fffdf5; background: #17221f; }.primary-button:hover:not(:disabled) { background: #245244; border-color: #245244; }.secondary-button { color: #17221f; background: transparent; border-color: #9da59b; }.secondary-button:hover:not(:disabled) { border-color: #245244; color: #245244; }.primary-button:disabled, .secondary-button:disabled { cursor: not-allowed; opacity: .5; }
.state-card { margin: 2rem 0; padding: 1.4rem; display: flex; align-items: center; gap: 1rem; border: 1px solid #c9c3b6; background: #fbfaf5; }.state-card p { margin: .35rem 0 0; color: #687169; }.state-symbol { width: 2rem; height: 2rem; display: grid; place-items: center; color: #fffdf5; background: #a44536; font-weight: 800; }.loading-state { color: #245244; }
.run-summary { margin: 2rem 0 3rem; padding: 1.25rem 0 1.5rem; border-bottom: 1px solid #c9c3b6; }.section-label { display: flex; align-items: center; gap: .5rem; color: #687169; font-size: .78rem; font-weight: 750; letter-spacing: .1em; text-transform: uppercase; }.status-dot { width: .6rem; height: .6rem; border-radius: 50%; background: #245244; }.status-dot[data-status="failed"], .status-dot[data-status="error"] { background: #a44536; }.run-summary-main { display: flex; justify-content: space-between; align-items: end; gap: 2rem; margin-top: .9rem; }.run-summary h2 { margin: 0; font-size: clamp(1.8rem, 4vw, 3rem); }.run-summary p { margin: .45rem 0 0; color: #687169; }.trust-note { max-width: 25rem; padding-left: 1rem; border-left: 3px solid #a44536; }.trust-note strong, .trust-note span { display: block; }.trust-note strong { color: #245244; }.trust-note span { margin-top: .35rem; color: #687169; font-size: .8rem; overflow-wrap: anywhere; }
.section-heading { margin-bottom: 1rem; }.section-heading h2 { margin: 0; font-size: 1.45rem; }.metric-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 1px; background: #c9c3b6; border: 1px solid #c9c3b6; }.metric-card { min-height: 130px; padding: 1.1rem; background: #fbfaf5; }.metric-card span, .metric-card small { display: block; color: #687169; }.metric-card strong { display: block; margin: .55rem 0 .35rem; font-size: clamp(1.6rem, 3vw, 2.4rem); letter-spacing: -.04em; }.metric-card small { font-size: .75rem; }
.risk-section { margin-top: 3.5rem; }.risk-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1rem; }.risk-card { min-height: 112px; padding: 1rem; display: flex; justify-content: space-between; gap: 1rem; border-top: 2px solid #245244; background: #e9e5d9; }.risk-card span, .risk-card small { display: block; }.risk-card small { max-width: 12rem; margin-top: .45rem; color: #687169; font-size: .75rem; line-height: 1.4; }.risk-card strong { font-size: 2.3rem; }.risk-card strong[data-alert="true"] { color: #a44536; }.category-list { margin: 1.5rem 0 0; border-top: 1px solid #c9c3b6; }.category-list > div { display: flex; justify-content: space-between; gap: 1rem; padding: .85rem 0; border-bottom: 1px solid #ded9ce; }.category-list dt { font-weight: 700; }.category-list dd { display: flex; flex-wrap: wrap; gap: .85rem; margin: 0; color: #687169; font-size: .82rem; }
.cases-section { margin-top: 3.5rem; }.cases-heading { display: flex; justify-content: space-between; align-items: end; gap: 1rem; }.cases-panel { margin-top: 1rem; padding: 1rem; border: 1px solid #c9c3b6; background: #fbfaf5; }.filter-row { display: flex; flex-wrap: wrap; gap: .45rem; padding-bottom: 1rem; border-bottom: 1px solid #ded9ce; }.filter-button { padding: .45rem .7rem; color: #596259; background: transparent; border: 1px solid transparent; cursor: pointer; }.filter-button span { margin-left: .35rem; color: #245244; font-weight: 750; }.filter-button.active { color: #fffdf5; background: #245244; border-color: #245244; }.filter-button.active span { color: #fffdf5; }.case-list { display: grid; }.case-row { display: grid; grid-template-columns: minmax(220px, 1fr) 2fr; gap: 1rem; padding: 1rem 0; border-bottom: 1px solid #ded9ce; }.case-name { display: grid; grid-template-columns: auto 1fr; align-content: center; column-gap: .6rem; }.case-name strong { overflow-wrap: anywhere; }.case-name small { grid-column: 2; margin-top: .3rem; color: #687169; }.outcome-mark { width: .7rem; height: .7rem; margin-top: .25rem; border-radius: 50%; background: #245244; }.outcome-mark[data-outcome="failed"], .outcome-mark[data-outcome="error"] { background: #a44536; }.case-row dl { display: grid; grid-template-columns: repeat(3, 1fr); gap: .75rem; margin: 0; }.case-row dt { color: #687169; font-size: .72rem; }.case-row dd { margin: .3rem 0 0; color: #17221f; font-size: .85rem; overflow-wrap: anywhere; }.disclaimer { margin: 2rem 0 0; color: #687169; font-size: .8rem; line-height: 1.6; }
@media (max-width: 900px) { .quality-header { grid-template-columns: 1fr auto; }.header-title { display: none; }.intro-row, .run-summary-main { align-items: start; flex-direction: column; }.intro-actions { justify-content: flex-start; }.metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }.risk-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 560px) { .quality-header { padding: .8rem 1rem; }.account-area > span { max-width: 7rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.quality-main { width: min(100% - 2rem, 1180px); padding-top: 2rem; }.intro-row h1 { font-size: clamp(2.3rem, 14vw, 3.8rem); }.intro-actions, .intro-actions button { width: 100%; }.metric-grid, .risk-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.metric-card { min-height: 112px; padding: .8rem; }.metric-card strong { font-size: 1.55rem; }.category-list > div { align-items: start; flex-direction: column; gap: .35rem; }.cases-heading { align-items: start; flex-direction: column; }.cases-heading .secondary-button { width: 100%; }.case-row { grid-template-columns: 1fr; gap: .8rem; }.case-row dl { grid-template-columns: repeat(3, minmax(0, 1fr)); }.state-card { align-items: start; flex-wrap: wrap; }.state-card .text-link { margin-left: 3rem; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; } }
</style>
