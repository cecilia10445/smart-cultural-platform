<template>
  <main class="report-page">
    <header><a href="/index.html" aria-label="返回创作页">智能文创平台</a><span>运营空间 · 业务生成报告</span><button type="button" @click="logout">退出登录</button></header>
    <section class="hero"><p>EXPERIMENTAL TEXT SKILL WORKFLOW</p><h1>把一次真实生成看清楚</h1><p>展示已经完整性校验的真实业务生成轨迹、文化证据与文本 Skill 调用记录。</p></section>
    <section class="selector" aria-labelledby="history-title">
      <div><p>HISTORY</p><h2 id="history-title">业务生成记录</h2></div>
      <label>选择历史运行<select v-model="selectedRunId" :disabled="loading || !runs.length" @change="loadRun"><option value="">暂无已封存记录</option><option v-for="run in runs" :key="run.run_id" :value="run.run_id">{{ formatDate(run.started_at) }} · {{ run.run_id }}</option></select></label>
    </section>
    <section v-if="error" class="state error" role="alert">{{ error }}</section>
    <section v-else-if="loading" class="state">正在读取业务生成报告…</section>
    <section v-else-if="report" class="report" aria-labelledby="report-title">
      <div class="status"><span>技术状态：{{ report.technical_status }}</span><span>完整性：{{ report.integrity_status }}</span></div>
      <div v-if="!report.report || report.integrity_status !== 'verified'" class="state error">此运行未通过完整性校验或未完成；已拒绝展示业务输出。</div>
      <template v-else>
        <div class="run-title"><div><p>SEALED BUSINESS ARTIFACT</p><h2 id="report-title">{{ report.run_id }}</h2></div><button type="button" @click="loadRuns">刷新</button></div>
        <dl class="facts"><div><dt>RAG</dt><dd>{{ report.report.rag_status }}</dd></div><div><dt>Text Skill</dt><dd>{{ report.report.selected_skill_id }} · {{ report.report.skill_version }}</dd></div><div><dt>Qwen 请求</dt><dd>{{ report.report.actual_calls?.qwen ?? '未记录' }}</dd></div><div><dt>图片调用</dt><dd>{{ report.report.actual_calls?.image ?? 0 }}</dd></div><div><dt>数据库写入</dt><dd>{{ report.report.actual_calls?.database_writes ?? 0 }}</dd></div></dl>
        <div class="columns"><article><p>PRODUCT COPY</p><h3>产品文案</h3><p>{{ report.output.product_copy }}</p></article><article><p>DESIGN SPEC</p><h3>文字版设计说明</h3><p>{{ report.output.image_design_spec }}</p></article></div>
        <div class="details"><article><h3>RAG 来源</h3><p>{{ report.report.source_ids.join(' · ') }}</p></article><article><h3>Agent 工具轨迹</h3><ul><li v-for="(step, index) in report.report.tool_trajectory" :key="index">{{ step.tool }} <small>{{ step.skill_id || '' }}</small></li></ul></article><article><h3>运行数据</h3><p>规划 {{ formatLatency(report.report.planner_latency_ms) }} · 最终生成 {{ formatLatency(report.report.final_latency_ms) }}</p><p>业务记录 ID：{{ report.report.business_record_id ?? '未记录' }}</p><p>Skill 正文 SHA-256：{{ report.report.skill_body_sha256 }}</p></article></div>
      </template>
    </section>
    <section v-else class="state">尚无已封存的业务生成报告。</section>
  </main>
</template>

<script setup>
import { onMounted, ref } from 'vue'
const runs = ref([]), selectedRunId = ref(''), report = ref(null), loading = ref(false), error = ref('')
const token = () => localStorage.getItem('adminToken') || localStorage.getItem('token') || ''
const formatDate = (value) => { const d = new Date(value); return Number.isNaN(d.getTime()) ? '时间未记录' : d.toLocaleString('zh-CN') }
const formatLatency = (value) => typeof value === 'number' ? `${value.toFixed(0)} ms` : '未记录'
const loadRun = async () => {
  if (!selectedRunId.value) { report.value = null; return }
  loading.value = true; error.value = ''
  try {
    const r = await fetch(`/api/dashboard/business-generation-reports/${encodeURIComponent(selectedRunId.value)}`, { headers: { Authorization: `Bearer ${token()}` } })
    const body = await r.json().catch(() => ({}))
    if (!r.ok || body.status !== 'success') throw new Error('业务生成报告暂不可用。')
    report.value = body.data
  } catch (e) { report.value = null; error.value = e.message || '业务生成报告加载失败。' } finally { loading.value = false }
}
const loadRuns = async () => {
  loading.value = true; error.value = ''
  try {
    const r = await fetch('/api/dashboard/business-generation-reports', { headers: { Authorization: `Bearer ${token()}` } }); const body = await r.json().catch(() => ({}))
    if (!r.ok || body.status !== 'success') throw new Error('业务生成报告历史暂不可用。')
    runs.value = Array.isArray(body.data?.runs) ? body.data.runs : []; selectedRunId.value = body.data?.latest_run_id || ''; await loadRun()
  } catch (e) { error.value = e.message || '业务生成报告历史加载失败。' } finally { loading.value = false }
}
const logout = () => { for (const key of ['adminToken','adminUser','token','userInfo']) localStorage.removeItem(key); window.location.href = '/login.html' }
onMounted(loadRuns)
</script>

<style>
:root{font-family:"Noto Serif CJK SC","Songti SC",serif;color:#182720;background:#f3eee1}*{box-sizing:border-box}body{margin:0}.report-page{min-height:100vh;padding-bottom:5rem;background:radial-gradient(circle at 85% 0,#dbe4d2 0,transparent 27rem),#f3eee1}header{height:70px;border-bottom:1px solid #a9aa93;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;padding:0 6vw;font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif;font-size:.85rem;letter-spacing:.06em}header a{color:#182720;font-weight:800;text-decoration:none}header button{justify-self:end;border:0;border-bottom:1px solid #274c3b;padding:.25rem 0;background:transparent;color:#274c3b;cursor:pointer}.hero,.selector,.report,.state{width:min(1120px,calc(100% - 2rem));margin:auto}.hero{padding:5.5rem 0 3rem;border-bottom:2px solid #182720}.hero p,.selector>div>p,.run-title p,.columns article>p{margin:0;color:#365f4a;font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif;font-size:.74rem;font-weight:800;letter-spacing:.16em}.hero h1{margin:.65rem 0 1rem;font-size:clamp(3rem,5.3vw,6.5rem);line-height:.95;letter-spacing:-.07em;white-space:nowrap}.hero>p:last-child{max-width:42rem;color:#526357;line-height:1.8;letter-spacing:0;font-size:1rem;font-weight:400}.selector{display:flex;justify-content:space-between;gap:2rem;padding:2rem 0;border-bottom:1px solid #c5c2aa}.selector h2{margin:.45rem 0 0}.selector label{min-width:20rem;font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif;font-size:.8rem;color:#526357}.selector select{width:100%;margin-top:.4rem;padding:.7rem;background:#fffdf6;border:1px solid #989b85}.state{margin-top:2rem;padding:1.1rem 1.3rem;border-left:4px solid #365f4a;background:#fffdf6}.state.error{border-color:#a53a2b;color:#76291f}.report{padding-top:2rem}.status{display:flex;gap:.5rem;flex-wrap:wrap}.status span{padding:.35rem .6rem;border:1px solid #a9aa93;background:#fffdf6;font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif;font-size:.78rem}.run-title{display:flex;justify-content:space-between;gap:1rem;align-items:end;margin:2rem 0 1rem}.run-title h2{margin:.5rem 0 0;font-size:clamp(1.5rem,3vw,2.5rem);overflow-wrap:anywhere}.run-title button{padding:.6rem 1rem;border:1px solid #182720;background:#182720;color:#fffdf6;cursor:pointer}.facts,.columns,.details{display:grid;gap:1px;background:#a9aa93;border:1px solid #a9aa93}.facts{grid-template-columns:repeat(5,1fr)}.facts div,.columns article,.details article{padding:1.1rem;background:#fffdf6}.facts dt{font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif;color:#526357;font-size:.75rem}.facts dd{margin:.4rem 0 0;font-size:1rem;overflow-wrap:anywhere}.columns{grid-template-columns:1fr 1fr;margin-top:2rem}.columns h3,.details h3{margin:.45rem 0 .65rem;font-size:1.25rem}.columns p:not(:first-child),.details p,.details li{margin:0;color:#3f5044;line-height:1.8;white-space:pre-wrap}.details{grid-template-columns:repeat(3,1fr);margin-top:1px}.details ul{padding-left:1.2rem;margin:.3rem 0}.details small{color:#6b796d}@media(max-width:760px){header{grid-template-columns:1fr auto}header span{display:none}.selector,.run-title{align-items:start;flex-direction:column}.selector label{min-width:0;width:100%}.facts,.columns,.details{grid-template-columns:1fr}.hero{padding-top:3.5rem}.hero h1{white-space:normal;font-size:clamp(2.6rem,14vw,4rem)}}
</style>
