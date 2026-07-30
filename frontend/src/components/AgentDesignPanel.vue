<template>
  <section class="agent-panel" aria-labelledby="agent-design-title">
    <header>
      <div class="agent-header-row">
        <div>
          <p class="section-index">{{ historyView ? '协作式设计记录' : '协作式设计' }}</p>
          <h2 id="agent-design-title">{{ historyView ? '协作式设计记录' : 'AI 文创产品设计助手' }}</h2>
          <p>{{ historyView ? '这是一次已完成创作的只读回顾，不会再次调用模型或生成图片。' : '用一句话描述需求，助手会补全产品方案。确认后可修改设计文本最多四次，再形成视觉方向。' }}</p>
        </div>
        <div class="agent-header-actions">
          <button v-if="historyView" type="button" class="secondary-button" @click="returnToHistory">返回全部创作记录</button>
          <button v-else type="button" class="secondary-button" @click="returnToHistory">协作式历史记录</button>
          <button v-if="historyView" type="button" class="primary-button" @click="startNew">开始新的协作设计</button>
        </div>
      </div>
    </header>

    <p v-if="notice" class="agent-notice" role="status">{{ notice }}</p>
    <p v-if="error" class="agent-error" role="alert">{{ error }}</p>
    <div v-if="loading && !session" class="agent-empty">正在读取协作会话。</div>

    <div v-else class="agent-layout">
      <main>
        <template v-if="session">
          <section class="dialogue" aria-label="协作消息">
            <article v-for="messageItem in session.messages" :key="messageItem.id" :class="['bubble', messageItem.role]">
              <strong>{{ messageItem.role === 'user' ? '你' : '设计助手' }}</strong>
              <p>{{ messageItem.text }}</p>
            </article>
            <p v-if="!session.messages.length" class="agent-empty">从一句产品需求开始吧。</p>
          </section>

          <section v-if="session.brief_summary" class="summary-card">
            <h3>我理解的需求</h3>
            <dl>
              <div><dt>文化主题</dt><dd>{{ session.brief_summary.cultural_theme || '—' }}</dd></div>
              <div><dt>产品类型</dt><dd>{{ session.brief_summary.product_type || '—' }}</dd></div>
              <div><dt>使用场景</dt><dd>{{ session.brief_summary.use_case || '—' }}</dd></div>
              <div><dt>风格</dt><dd>{{ session.brief_summary.style || '—' }}</dd></div>
            </dl>
            <p v-if="session.brief_summary.design_constraints?.length">约束：{{ session.brief_summary.design_constraints.join('；') }}</p>
            <p v-if="session.brief_summary.assumptions?.length">主动补充：{{ session.brief_summary.assumptions.join('；') }}</p>
          </section>

          <section v-if="session.product_design" class="summary-card">
            <h3>{{ session.product_design.product_name || '产品设计方案' }}</h3>
            <dl>
              <div v-for="field in designFields" :key="field.key"><dt>{{ field.label }}</dt><dd>{{ session.product_design[field.key] || '—' }}</dd></div>
            </dl>
            <h4>核心卖点</h4>
            <ul><li v-for="point in session.product_design.selling_points" :key="point">{{ point }}</li></ul>
            <p>资料状态：{{ session.product_design.evidence_status || '—' }} · 文本 Skill：{{ session.product_design.selected_text_skill || '—' }}</p>
          </section>

          <section v-if="session.visual_direction" class="summary-card visual-card">
            <h3>视觉方向</h3>
            <p>{{ session.visual_direction.summary || '视觉方向已准备。' }}</p>
            <dl>
              <div v-for="field in visualFields" :key="field.key"><dt>{{ field.label }}</dt><dd>{{ session.visual_direction[field.key] || '—' }}</dd></div>
            </dl>
            <p>避免项：{{ (session.visual_direction.avoid || session.visual_direction.negative_constraints || []).join('；') || '—' }}</p>
            <p>视觉 Skill：{{ session.visual_direction.selected_visual_skill || '默认视觉规则' }}</p>
          </section>

          <section v-if="session.status === 'completed'" class="summary-card final-card">
            <h3>{{ session.final_result?.product_name || session.product_design?.product_name || '最终设计结果' }}</h3>
            <div v-if="session.final_result?.image_url" class="final-image">
              <img :src="session.final_result.image_url" :alt="session.final_result.product_name || '文创产品最终图片'" @error="handleImageError">
            </div>
            <p v-else class="agent-error">结果暂时无法展示；产品设计文本与创作记录仍可查看。</p>
            <dl>
              <div><dt>文化资料状态</dt><dd>{{ session.final_result?.evidence_status || session.product_design?.evidence_status || '—' }}</dd></div>
              <div><dt>文本 Skill</dt><dd>{{ session.final_result?.selected_text_skill || session.product_design?.selected_text_skill || '—' }}</dd></div>
              <div><dt>视觉 Skill</dt><dd>{{ session.final_result?.selected_visual_skill || session.visual_direction?.selected_visual_skill || '—' }}</dd></div>
              <div><dt>生成耗时</dt><dd>{{ session.final_result?.generation_time ?? '—' }} 秒</dd></div>
              <div><dt>记录编号</dt><dd>{{ session.generation_log_id || '—' }}</dd></div>
              <div><dt>创建时间</dt><dd>{{ formatDate(session.created_at) }}</dd></div>
              <div><dt>完成时间</dt><dd>{{ formatDate(session.completed_at || session.updated_at) }}</dd></div>
            </dl>
          </section>

          <section v-if="historyView" class="summary-card history-readonly-card">
            <h3>历史回顾</h3>
            <p>修订次数：{{ session.revision_count }} / 4 · generation_log_id：{{ session.generation_log_id || '—' }}</p>
            <p>创建时间：{{ formatDate(session.created_at) }} · 完成时间：{{ formatDate(session.completed_at || session.updated_at) }}</p>
          </section>
        </template>

        <section v-if="session && !historyView">
          <AgentDecisionCard :status="session.status" :revision-count="session.revision_count" :busy="decisionBusy" @decide="decide" />
        </section>

        <form v-if="inputCopy" class="agent-input" @submit.prevent="send">
          <label for="agent-message">{{ inputCopy.title }}</label>
          <p>{{ inputCopy.description }}</p>
          <textarea id="agent-message" v-model="message" rows="3" :disabled="loading || decisionBusy" :placeholder="inputCopy.placeholder"></textarea>
          <button type="submit" class="secondary-button" :disabled="!message.trim() || loading || decisionBusy">{{ loading ? '正在整理' : inputCopy.button }}</button>
        </form>

        <p v-else-if="session && !historyView && session.status === 'waiting_image_confirmation'" class="agent-notice">第一版暂不支持修改图片或重新生成图片，请确认当前视觉方向。</p>
        <p v-else-if="session && !historyView && session.status === 'generating_image'" class="agent-notice">正在真实生成图片，请不要重复操作。</p>
        <p v-else-if="session && !historyView && session.status === 'failed'" class="agent-error">{{ session.error?.message || '此阶段未能完成，请查看协作过程中的错误信息。' }}</p>

        <section v-if="canStartNew" class="restart-actions" aria-label="开始新的创作">
          <button type="button" class="secondary-button" :disabled="loading || decisionBusy" @click="startNew">开始新的协作设计</button>
        </section>

        <section v-if="session && session.status === 'completed' && !historyView" class="completion-actions" aria-label="完成后的操作">
          <h3>本次协作设计已完成</h3>
          <p>可以保留这份记录，或从一段全新的需求开始下一次创作。</p>
          <div>
            <button type="button" class="primary-button" @click="startNew">开始新的协作设计</button>
          </div>
        </section>
      </main>
      <aside v-if="session"><AgentDialogueTimeline :steps="session.steps" /></aside>
    </div>
  </section>
</template>

<script>
import AgentDialogueTimeline from './AgentDialogueTimeline.vue'
import AgentDecisionCard from './AgentDecisionCard.vue'
import { createSession, getSession, sendMessage, submitDecision } from '../services/agentDialogueApi'

const INITIAL_INPUT = {
  title: '描述你的文创产品需求',
  description: '用一句话描述文化主题、产品类型、使用场景和希望避免的设计方向。',
  placeholder: '例如：以三兔共耳纹样设计一款现代桌面灯，强调环形动态感，避免仿古造型',
  button: '开始设计',
}

export default {
  name: 'AgentDesignPanel',
  components: { AgentDialogueTimeline, AgentDecisionCard },
  emits: ['return-to-history'],
  data: () => ({
    session: null,
    message: '',
    loading: false,
    decisionBusy: false,
    error: '',
    notice: '',
    historyView: false,
    designFields: [
      { key: 'design_concept', label: '设计理念' }, { key: 'cultural_translation', label: '文化转译' },
      { key: 'structure', label: '结构' }, { key: 'materials', label: '材质' },
      { key: 'color_plan', label: '配色' }, { key: 'usage_scene', label: '使用场景' },
    ],
    visualFields: [
      { key: 'product_form', label: '产品形态' }, { key: 'materials', label: '材质' },
      { key: 'color_plan', label: '色彩' }, { key: 'composition', label: '构图' },
      { key: 'scene', label: '场景' }, { key: 'presentation_mode', label: '展示方式' },
    ],
  }),
  computed: {
    canStartNew() {
      return Boolean(this.session) && !this.historyView && !['completed', 'generating_image'].includes(this.session.status)
    },
    inputCopy() {
      if (this.historyView) return null
      const status = this.session?.status || 'created'
      const revisionCount = this.session?.revision_count || 0
      return {
        created: INITIAL_INPUT,
        extracting_brief: { ...INITIAL_INPUT, description: '正在理解你的需求。', placeholder: '请等待需求理解完成' },
        waiting_brief_confirmation: { title: '补充或修改需求理解', description: '可以修改其中一部分，也可以要求 Agent 全部重新理解。', placeholder: '例如：材质改成磨砂金属；或“全部重新理解，改成现代胸针”', button: '发送修改' },
        waiting_text_feedback: { title: '提出设计方案修改意见', description: `已修改 ${revisionCount} 次，还可修改 ${Math.max(0, 4 - revisionCount)} 次。`, placeholder: '例如：名称保留，材质改成磨砂金属，颜色不要大红色', button: '修改方案' },
      }[status] || null
    },
  },
  async mounted() {
    const query = new URLSearchParams(window.location.search)
    const id = query.get('agent_session_id')
    this.historyView = query.get('view') === 'history'
    if (id) await this.restore(id)
  },
  methods: {
    setQuery(id) {
      const url = new URL(window.location.href)
      url.searchParams.set('agent_session_id', id)
      window.history.replaceState({}, '', url)
    },
    clearAgentQuery() {
      const url = new URL(window.location.href)
      url.searchParams.delete('agent_session_id')
      url.searchParams.delete('view')
      window.history.replaceState({}, '', url)
    },
    async create() {
      this.loading = true
      this.error = ''
      try {
        this.session = await createSession()
        this.setQuery(this.session.session_id)
      } catch (error) {
        this.displayError(error)
      } finally {
        this.loading = false
      }
    },
    async restore(id) {
      this.loading = true
      this.error = ''
      try {
        this.session = await getSession(id)
        this.setQuery(id)
      } catch (error) {
        this.displayError(error)
      } finally {
        this.loading = false
      }
    },
    async send() {
      const text = this.message.trim()
      if (!text || this.historyView) return
      if (!this.session) {
        await this.create()
        if (!this.session) return
      }
      this.loading = true
      this.error = ''
      try {
        this.session = await sendMessage(this.session.session_id, text, this.session.status, this.session.version)
        this.message = ''
      } catch (error) {
        this.displayError(error)
      } finally {
        this.loading = false
      }
    },
    async decide(action) {
      if (!this.session || this.historyView || this.decisionBusy) return
      this.decisionBusy = true
      this.error = ''
      this.notice = ''
      try {
        this.session = await submitDecision(this.session.session_id, action, this.session.status, this.session.version)
        if (action === 'confirm_image_generation') this.notice = '视觉方向已确认，正在提交最终图片生成。'
      } catch (error) {
        this.displayError(error)
      } finally {
        this.decisionBusy = false
      }
    },
    startNew() {
      if (this.session && this.session.status !== 'completed' && !this.historyView && !window.confirm('当前方案尚未完成。开始新的协作设计不会删除这份记录，仍要继续吗？')) return false
      this.session = null
      this.message = ''
      this.error = ''
      this.notice = ''
      this.historyView = false
      this.clearAgentQuery()
      return true
    },
    returnToHistory() {
      this.$emit('return-to-history')
    },
    handleImageError(event) {
      event.currentTarget.style.display = 'none'
      this.notice = '图片暂时无法加载；产品设计文本与创作记录仍可查看。'
    },
    formatDate(value) {
      if (!value) return '时间未记录'
      const date = new Date(value)
      return Number.isNaN(date.getTime()) ? '时间格式异常' : date.toLocaleString('zh-CN', { dateStyle: 'medium', timeStyle: 'short' })
    },
    displayError(error) {
      this.error = error?.code === 'AGENT_DTO_INCOMPLETE'
        ? '结果暂时无法展示，请稍后刷新。'
        : error?.response?.status === 409
          ? '当前方案状态已变化，请刷新后继续。'
          : error?.kind === 'network'
            ? '无法连接协作服务，请检查网络。'
            : (error?.message || '协作服务暂时不可用。')
    },
  },
}
</script>

<style scoped>
.agent-panel{margin-top:1.25rem}.agent-panel header{padding-bottom:1rem;border-bottom:1px solid #d4cec2}.agent-header-row{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start}.agent-header-actions{display:flex;flex-wrap:wrap;gap:.6rem;align-items:center;padding-top:.2rem}.agent-panel h2{margin:.2rem 0;color:#245244;font-size:clamp(1.45rem,3vw,2.2rem)}.agent-panel header p{margin:.25rem 0;color:#59655b;line-height:1.65}.agent-layout{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(230px,.75fr);gap:1.25rem;margin-top:1.25rem}.dialogue{display:grid;gap:.7rem}.bubble{padding:.75rem .9rem;border:1px solid #d4cec2;background:#fffdf5}.bubble.user{background:#edf3ed;border-color:#bed0c1}.bubble strong{font-size:.78rem;color:#245244}.bubble p{white-space:pre-wrap;margin:.25rem 0 0;line-height:1.6}.summary-card{margin-top:1rem;border:1px solid #d4cec2;background:#fff;padding:1rem}.summary-card h3,.summary-card h4{margin:0 0 .65rem;color:#245244}.summary-card dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.65rem;margin:0}.summary-card dt{font-size:.76rem;color:#697468}.summary-card dd{margin:.15rem 0 0;line-height:1.5}.summary-card p,.summary-card li{line-height:1.6}.summary-card ul{margin:.25rem 0;padding-left:1.1rem}.agent-input{margin-top:1rem;display:grid;gap:.5rem}.agent-input label{font-weight:600;color:#245244}.agent-input textarea{border:1px solid #aeb8ac;background:#fffdf5;padding:.7rem;font:inherit;resize:vertical}.agent-input button{justify-self:start}.agent-error,.agent-notice,.agent-empty{margin-top:1rem;padding:.75rem 1rem;background:#fff7ee;border-left:3px solid #b74b3c}.agent-notice{background:#f1f6ed;border-color:#245244}.agent-empty{color:#657066;border-color:#9ca69d}.restart-actions{margin-top:1rem}.completion-actions{margin-top:1rem;padding:1rem;border-top:2px solid #17221f;background:#f4f7f0}.completion-actions h3{margin:0;color:#245244}.completion-actions p{margin:.4rem 0 .9rem;line-height:1.6}.completion-actions div{display:flex;flex-wrap:wrap;gap:.75rem;align-items:center}.history-readonly-card{background:#f4f7f0}@media(max-width:760px){.agent-header-row{display:grid}.agent-header-actions{padding-top:0}.agent-layout{grid-template-columns:1fr}.summary-card dl{grid-template-columns:1fr}}
.final-image{margin:.75rem 0;background:#f1f3ee}.final-image img{display:block;width:100%;max-height:480px;object-fit:contain}
</style>
