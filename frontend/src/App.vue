<template>
  <main class="workspace-shell">
    <header class="workspace-header">
      <a class="brand" href="/index.html" aria-label="智能文创平台，返回创作页">
        <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>
        <span>智能文创平台</span>
      </a>
      <div class="account-summary">
        <span class="account-name">{{ userInfo?.name || userInfo?.username || '已登录用户' }}</span>
        <button type="button" class="text-button" @click="logout">退出登录</button>
      </div>
    </header>

    <div class="workspace-layout">
      <nav class="workspace-nav" aria-label="用户工作台导航">
        <button type="button" :class="{ active: activeTab === 'generate' }" :aria-current="activeTab === 'generate' ? 'page' : undefined" @click="switchTab('generate')"><span>01</span>创作</button>
        <button type="button" :class="{ active: activeTab === 'history' }" :aria-current="activeTab === 'history' ? 'page' : undefined" @click="switchTab('history')"><span>02</span>记录</button>
        <button type="button" :class="{ active: activeTab === 'recommendations' }" :aria-current="activeTab === 'recommendations' ? 'page' : undefined" @click="switchTab('recommendations')"><span>03</span>灵感</button>
        <button type="button" :class="{ active: activeTab === 'profile' }" :aria-current="activeTab === 'profile' ? 'page' : undefined" @click="switchTab('profile')"><span>04</span>账户</button>
      </nav>

      <section class="workspace-content">
        <section v-if="activeTab === 'generate'" aria-labelledby="generate-title">
          <div class="section-heading">
            <p class="section-index">创作</p>
            <h1 id="generate-title">把文化意象说清楚</h1>
            <p>写下主题和用途，再选择画面方向，让创作从一个清晰的想法开始。</p>
          </div>

          <form class="creation-form" @submit.prevent="generateContent" novalidate>
            <div class="brief-grid">
              <label class="field-block"><span>产品类型</span><input v-model="brief.product_type" :disabled="loading" placeholder="例如：书签" required></label>
              <label class="field-block"><span>来源类型</span><select v-model="brief.cultural_source.source_type" :disabled="loading"><option value="artifact">器物或纹样</option><option value="heritage">非遗技艺</option><option value="literature">文学意象</option></select></label>
              <label class="field-block"><span>文化原型或灵感来源</span><input v-model="brief.cultural_source.name" :disabled="loading" placeholder="例如：青花折枝纹" required></label>
              <label class="field-block"><span>已知时代（可选）</span><input v-model="brief.cultural_source.era" :disabled="loading" placeholder="例如：明代"></label>
              <label class="field-block"><span>已知作者或机构（可选）</span><input v-model="brief.cultural_source.creator" :disabled="loading"></label>
              <label class="field-block"><span>使用场景</span><input v-model="brief.use_case" :disabled="loading" placeholder="例如：博物馆文创商店" required></label>
              <label class="field-block"><span>目标受众（可选）</span><input v-model="brief.target_audience" :disabled="loading" placeholder="例如：年轻游客和阅读爱好者"></label>
            </div>
            <div class="field-block">
              <label for="facts">确认事实（每行一条）</label>
              <textarea id="facts" v-model="confirmedFactsText" rows="3" :disabled="loading" placeholder="只填写你已确认的信息；未提供资料时，系统不会把具体历史信息标记为已确认。"></textarea>
              <p class="field-help">文化背景只依据这些事实整理；设计解读和产品讲解属于创意内容。</p>
            </div>
            <div class="field-block">
              <label for="form-material">造型与材质</label>
              <textarea id="form-material" v-model="brief.form_and_material" rows="3" :disabled="loading" placeholder="例如：长条形纸质书签，带丝带" required></textarea>
            </div>

            <fieldset class="field-block direction-fieldset" :disabled="loading">
              <legend>画面方向</legend>
              <p class="field-help">先选一组策展方案，也可以继续调整下面的画面维度。</p>
              <div class="direction-grid" role="radiogroup" aria-label="画面方向策展方案">
                <button v-for="direction in visualDirections" :key="direction.id" type="button" class="direction-card" :class="{ active: selectedDirectionId === direction.id }" :aria-pressed="selectedDirectionId === direction.id ? 'true' : 'false'" @click="selectDirection(direction)">
                  <span>{{ direction.name }}</span>
                  <small>{{ direction.summary }}</small>
                </button>
              </div>

              <div class="dimension-grid">
                <label v-for="dimension in dimensionFields" :key="dimension.key" class="dimension-control">
                  <span>{{ dimension.label }}</span>
                  <select v-model="dimensions[dimension.key]" :aria-label="dimension.label" @change="handleDimensionChange">
                    <option v-for="option in dimensionOptions[dimension.key]" :key="option.id" :value="option.id">{{ option.name }}</option>
                  </select>
                </label>
              </div>
            </fieldset>

            <div class="field-block">
              <label for="supplement">补充画面要求（可选）</label>
              <input id="supplement" v-model="supplement" type="text" :maxlength="supplementMaxLength" :disabled="loading" placeholder="可补充材质、光线、镜头或不希望出现的元素" aria-describedby="supplement-help">
              <p id="supplement-help" class="field-help">这项不会改写上面的主题内容。</p>
            </div>

            <details class="style-preview">
              <summary>查看本次画面描述</summary>
              <p>{{ currentStyle }}</p>
            </details>

            <p v-if="error" class="state-message error-state" role="alert">{{ error }}</p>
            <p v-if="sessionExpired" class="state-message error-state" role="alert">登录状态已失效。<a href="/login.html">重新登录</a>后可继续提交当前内容。</p>

            <div class="form-actions">
              <button type="submit" class="primary-button" :disabled="loading">
                <span v-if="loading" class="button-loading"><span class="inline-spinner" aria-hidden="true"></span>正在生成</span>
                <span v-else>生成文创产品</span>
              </button>
              <button type="button" class="secondary-button" :disabled="loading" @click="clearAll">清空本页内容</button>
            </div>
          </form>

          <section v-if="loading" class="generation-state" aria-live="polite">
            <span class="large-spinner" aria-hidden="true"></span>
            <div>
              <h2>正在处理你的创作请求</h2>
              <p>请保持页面开启，完成后会在这里显示结果。</p>
            </div>
          </section>

          <section v-if="result && !loading" class="result-section" aria-labelledby="result-title">
            <div class="result-header">
              <p class="section-index">本次创作</p>
              <h2 id="result-title">生成结果</h2>
            </div>
            <div class="result-grid">
              <div class="image-stage">
                <img v-if="!imageFailed" :src="result.image_url" :alt="result.product_name" @error="imageFailed = true">
                <div v-else class="image-unavailable" role="status">
                  <span aria-hidden="true"></span>
                  <p>图片暂时无法加载</p>
                  <small>你仍可以查看本次生成的文字内容。</small>
                </div>
                <div class="image-actions">
                  <button type="button" class="secondary-button" :disabled="isDownloading" @click="downloadImage">{{ isDownloading ? '正在准备下载' : '下载图片' }}</button>
                  <p v-if="downloadError" class="inline-error" role="alert">{{ downloadError }}</p>
                </div>
              </div>
              <article class="generated-copy">
                <h3>{{ result.product_name }}</h3>
                <section class="content-copy"><h4>文化背景</h4><p>{{ result.factual_background.text }}</p><small>证据状态：{{ result.factual_background.status === 'user_supplied' ? '用户提供的事实' : '证据不足' }}</small></section>
                <section class="content-copy"><h4>设计解读</h4><p>{{ result.design_interpretation }}</p></section>
                <section class="content-copy"><h4>产品讲解</h4><p>{{ result.product_copy }}</p></section>
                <dl class="result-meta">
                  <div><dt>生成耗时</dt><dd>{{ result.generation_time }} 秒</dd></div>
                  <div><dt>记录编号</dt><dd>{{ result.log_id }}</dd></div>
                  <div><dt>画面描述</dt><dd>{{ resultStyle }}</dd></div>
                </dl>
                <div class="rating-panel">
                  <p class="feedback-title">这次结果是否符合你的想法？</p>
                  <div class="rating-buttons" aria-label="为本次生成评分">
                    <button v-for="n in 5" :key="n" type="button" :class="{ selected: userRating === n }" :disabled="ratingSaving" :aria-pressed="userRating === n" @click="rateImage(n)">{{ n }} 分</button>
                  </div>
                  <p v-if="ratingSaving" class="status-copy" aria-live="polite">正在提交反馈。</p>
                  <p v-else-if="ratingError" class="inline-error" role="alert">{{ ratingError }}</p>
                  <p v-else-if="userRating" class="status-copy" aria-live="polite">已收到 {{ userRating }} 分反馈。</p>
                </div>
              </article>
            </div>
          </section>
        </section>

        <section v-else-if="activeTab === 'history'" aria-labelledby="history-title">
          <div class="section-heading section-heading-row">
            <div>
              <p class="section-index">记录</p>
              <h1 id="history-title">创作记录</h1>
              <p>查看当前账户已经保存的创作结果。</p>
            </div>
            <button type="button" class="secondary-button" :disabled="loadingHistory" @click="loadHistory">{{ loadingHistory ? '正在刷新' : '刷新记录' }}</button>
          </div>
          <div v-if="loadingHistory" class="empty-state" aria-live="polite">正在读取创作记录。</div>
          <div v-else-if="historyError" class="state-message error-state" role="alert">{{ historyError }}</div>
          <div v-else-if="historyLoaded && history.length === 0" class="empty-state">
            <h2>还没有创作记录</h2>
            <p>从“创作”页写下一个主题，完成后结果会出现在这里。</p>
            <button type="button" class="primary-button" @click="switchTab('generate')">去创作</button>
          </div>
          <div v-else-if="history.length" class="history-grid">
            <article v-for="record in history" :key="record.log_id || `${record.timestamp}-${record.prompt}`" class="history-entry">
              <div class="history-visual">
                <img v-if="record.image_url && !historyImageErrors[record.image_url]" :src="getImageUrl(record.image_url)" :alt="record.title || record.prompt" @error="markHistoryImageFailed(record.image_url)">
                <div v-else class="history-image-fallback">图片无法加载</div>
              </div>
              <div>
                <p class="record-style">{{ record.style || '未记录画面描述' }}</p>
                <h2>{{ record.title || record.prompt }}</h2>
                <p>{{ previewText(record.content || record.prompt, 110) }}</p>
                <time>{{ formatDate(record.timestamp) }}</time>
              </div>
            </article>
          </div>
        </section>

        <section v-else-if="activeTab === 'recommendations'" aria-labelledby="recommendations-title">
          <div class="section-heading section-heading-row">
            <div>
              <p class="section-index">灵感</p>
              <h1 id="recommendations-title">创作参考</h1>
              <p>这里会显示与你的记录相关的参考内容。</p>
            </div>
            <button type="button" class="secondary-button" :disabled="recommendationLoading" @click="loadRecommendations">{{ recommendationLoading ? '正在刷新' : '刷新参考' }}</button>
          </div>
          <div v-if="recommendationLoading" class="empty-state" aria-live="polite">正在读取参考内容。</div>
          <div v-else-if="recommendationError" class="state-message error-state" role="alert">{{ recommendationError }}</div>
          <div v-else-if="recommendationsLoaded && !trendingStyles.length && !trendingKeywords.length" class="empty-state">
            <h2>暂时没有参考内容</h2>
            <p>完成一些创作后，再回来看看新的参考。</p>
          </div>
          <div v-else-if="recommendationsLoaded" class="reference-grid">
            <section v-if="trendingStyles.length" class="reference-list">
              <h2>画面参考</h2>
              <article v-for="item in trendingStyles" :key="item.style">
                <h3>{{ item.style }}</h3>
                <p v-if="item.reason">{{ item.reason }}</p>
              </article>
            </section>
            <section v-if="trendingKeywords.length" class="reference-list">
              <h2>主题关键词</h2>
              <article v-for="item in trendingKeywords" :key="item.keyword">
                <h3>{{ item.keyword }}</h3>
                <p>在已有创作中出现 {{ item.frequency }} 次。</p>
              </article>
            </section>
          </div>
        </section>

        <section v-else aria-labelledby="profile-title">
          <div class="section-heading">
            <p class="section-index">账户</p>
            <h1 id="profile-title">账户资料</h1>
            <p>以下信息来自当前登录账户。</p>
          </div>
          <dl class="profile-list">
            <div><dt>用户名</dt><dd>{{ userInfo?.username || '—' }}</dd></div>
            <div><dt>姓名</dt><dd>{{ userInfo?.name || '—' }}</dd></div>
            <div><dt>用户编号</dt><dd>{{ userInfo?.user_id || '—' }}</dd></div>
          </dl>
        </section>
      </section>
    </div>
  </main>
</template>

<script>
import axios from 'axios'
import {
  buildStylePrompt,
  DEFAULT_DIRECTION_ID,
  DIMENSION_OPTIONS,
  SUPPLEMENT_MAX_LENGTH,
  VISUAL_DIRECTIONS,
} from './content/visualDirections'

const DEFAULT_DIRECTION = VISUAL_DIRECTIONS.find((direction) => direction.id === DEFAULT_DIRECTION_ID)

export default {
  name: 'App',
  data() {
    return {
      activeTab: 'generate',
      prompt: '',
      confirmedFactsText: '',
      brief: {
        product_type: '',
        cultural_source: { source_type: 'artifact', name: '', era: '', creator: '' },
        form_and_material: '',
        use_case: '',
        target_audience: '',
      },
      dimensions: { ...DEFAULT_DIRECTION.dimensions },
      selectedDirectionId: DEFAULT_DIRECTION_ID,
      supplement: '',
      loading: false,
      error: '',
      sessionExpired: false,
      result: null,
      resultStyle: '',
      userInfo: null,
      imageFailed: false,
      isDownloading: false,
      downloadError: '',
      userRating: 0,
      ratingSaving: false,
      ratingError: '',
      history: [],
      loadingHistory: false,
      historyError: '',
      historyLoaded: false,
      historyImageErrors: {},
      trendingStyles: [],
      trendingKeywords: [],
      recommendationLoading: false,
      recommendationError: '',
      recommendationsLoaded: false,
      visualDirections: VISUAL_DIRECTIONS,
      dimensionOptions: DIMENSION_OPTIONS,
      supplementMaxLength: SUPPLEMENT_MAX_LENGTH,
      dimensionFields: [
        { key: 'culturalContext', label: '文化语境' },
        { key: 'medium', label: '表现媒介' },
        { key: 'palette', label: '色彩倾向' },
        { key: 'composition', label: '构图气质' },
      ],
    }
  },
  computed: {
    currentStyle() {
      return buildStylePrompt(this.dimensions, this.supplement)
    },
    visualDirection() {
      const findText = (key) => this.dimensionOptions[key].find((item) => item.id === this.dimensions[key])?.promptText || ''
      return {
        preset_id: this.selectedDirectionId || 'custom',
        cultural_context: findText('culturalContext'), medium: findText('medium'),
        palette: findText('palette'), composition: findText('composition'),
        additional_requirements: this.supplement.trim(),
      }
    },
    culturalBrief() {
      return {
        brief_version: '1.0',
        brief: {
          ...this.brief,
          cultural_source: { ...this.brief.cultural_source },
          confirmed_facts: this.confirmedFactsText.split('\n').map((value) => value.trim()).filter(Boolean),
          visual_direction: this.visualDirection,
        },
      }
    },
  },
  methods: {
    switchTab(tab) {
      this.activeTab = tab
      if (tab === 'history') this.loadHistory()
      if (tab === 'recommendations') this.loadRecommendations()
    },
    authHeaders() {
      const token = localStorage.getItem('token')
      return token ? { Authorization: `Bearer ${token}` } : null
    },
    requestError(error, subject) {
      const status = error.response?.status
      if (status === 401) {
        this.sessionExpired = true
        return '登录状态已失效。'
      }
      if (status === 403) return `当前账户无权${subject}。`
      if (status === 503) return `${subject}暂时不可用，请稍后重试。`
      if (status === 502) return `${subject}服务暂时不可用，请稍后重试。`
      if (status) return `${subject}未能完成，请稍后重试。`
      if (error.request) return `无法连接${subject}，请检查网络后重试。`
      return `${subject}返回异常，请稍后重试。`
    },
    selectDirection(direction) {
      this.selectedDirectionId = direction.id
      this.dimensions = { ...direction.dimensions }
    },
    handleDimensionChange() {
      this.selectedDirectionId = null
    },
    clearAll() {
      this.prompt = ''
      this.confirmedFactsText = ''
      this.brief = { product_type: '', cultural_source: { source_type: 'artifact', name: '', era: '', creator: '' }, form_and_material: '', use_case: '', target_audience: '' }
      this.dimensions = { ...DEFAULT_DIRECTION.dimensions }
      this.selectedDirectionId = DEFAULT_DIRECTION_ID
      this.supplement = ''
      this.error = ''
      this.sessionExpired = false
      this.result = null
      this.resultStyle = ''
      this.imageFailed = false
      this.downloadError = ''
      this.userRating = 0
      this.ratingError = ''
    },
    validGeneration(body) {
      return body?.status === 'success'
        && typeof body.image_url === 'string'
        && body.image_url
        && body.generation_kind === 'cultural_product'
        && typeof body.product_name === 'string' && body.product_name
        && typeof body.design_interpretation === 'string' && body.design_interpretation
        && typeof body.product_copy === 'string' && body.product_copy
        && body.factual_background && typeof body.factual_background.text === 'string'
        && Number.isFinite(Number(body.generation_time))
        && body.log_id !== undefined
        && body.log_id !== null
    },
    async generateContent() {
      if (this.loading) return
      if (!this.brief.product_type.trim() || !this.brief.cultural_source.name.trim() || !this.brief.form_and_material.trim() || !this.brief.use_case.trim()) {
        this.error = '请填写产品类型、文化来源、造型与材质和使用场景。'
        return
      }
      const headers = this.authHeaders()
      if (!headers) {
        window.location.href = '/login.html'
        return
      }

      const style = this.currentStyle
      this.loading = true
      this.error = ''
      this.sessionExpired = false
      this.result = null
      this.resultStyle = ''
      this.imageFailed = false
      this.downloadError = ''
      this.userRating = 0
      this.ratingError = ''

      try {
        const response = await axios.post('/api/v2/cultural-products/generate', this.culturalBrief, { headers })
        if (!this.validGeneration(response.data)) {
          this.error = '生成结果不完整，请稍后重试。'
          return
        }
        this.result = response.data
        this.resultStyle = style
        this.loadHistory()
      } catch (error) {
        const message = this.requestError(error, '生成')
        this.error = this.sessionExpired ? '' : message
      } finally {
        this.loading = false
      }
    },
    async rateImage(rating) {
      if (!this.result || this.ratingSaving) return
      const headers = this.authHeaders()
      if (!headers) {
        this.sessionExpired = true
        return
      }
      this.ratingSaving = true
      this.ratingError = ''
      try {
        const response = await axios.post('/api/rating', {
          image_url: this.result.image_url,
          prompt: this.brief.cultural_source.name,
          style: this.resultStyle,
          rating,
          log_id: this.result.log_id,
        }, { headers })
        if (response.data?.status !== 'success' || Number(response.data.rating) !== rating) {
          this.ratingError = '反馈暂未保存，请稍后重试。'
          return
        }
        this.userRating = rating
      } catch (error) {
        this.ratingError = this.requestError(error, '反馈')
      } finally {
        this.ratingSaving = false
      }
    },
    async downloadImage() {
      if (!this.result || this.isDownloading) return
      const headers = this.authHeaders()
      if (!headers) {
        this.sessionExpired = true
        return
      }
      this.isDownloading = true
      this.downloadError = ''
      try {
        const response = await axios.post('/api/download', {
          image_url: this.result.image_url,
          prompt: this.brief.cultural_source.name,
          style: this.resultStyle,
        }, { headers })
        if (response.data?.status !== 'success') {
          this.downloadError = '暂时无法下载，请稍后重试。'
          return
        }
        const link = document.createElement('a')
        link.href = this.result.image_url
        link.download = `cultural-generation-${this.result.log_id}`
        link.rel = 'noopener'
        link.click()
      } catch (error) {
        this.downloadError = this.requestError(error, '下载')
      } finally {
        this.isDownloading = false
      }
    },
    async loadHistory() {
      if (this.loadingHistory) return
      const headers = this.authHeaders()
      if (!headers) {
        this.sessionExpired = true
        return
      }
      this.loadingHistory = true
      this.historyError = ''
      try {
        const response = await axios.get('/api/user/history', { headers })
        if (response.data?.status !== 'success' || !Array.isArray(response.data.data)) {
          this.historyError = '创作记录暂时无法读取，请稍后重试。'
          return
        }
        this.history = response.data.data
        this.historyLoaded = true
      } catch (error) {
        this.historyError = this.requestError(error, '创作记录')
      } finally {
        this.loadingHistory = false
      }
    },
    async loadRecommendations() {
      if (this.recommendationLoading) return
      const headers = this.authHeaders()
      if (!headers) {
        this.sessionExpired = true
        return
      }
      this.recommendationLoading = true
      this.recommendationError = ''
      this.recommendationsLoaded = false
      this.trendingStyles = []
      this.trendingKeywords = []
      try {
        const response = await axios.get('/api/recommendations/personalized', { headers })
        const data = response.data?.data
        const validStyles = Array.isArray(data?.style_recommendations)
          && data.style_recommendations.every((item) => item && typeof item.style === 'string')
        const validKeywords = Array.isArray(data?.hot_keywords)
          && data.hot_keywords.every((item) => item && typeof item.keyword === 'string' && Number.isFinite(Number(item.frequency)))
        if (response.data?.status !== 'success' || !validStyles || !validKeywords) {
          this.recommendationError = '参考内容暂时无法读取，请稍后重试。'
          return
        }
        this.trendingStyles = data.style_recommendations
        this.trendingKeywords = data.hot_keywords
        this.recommendationsLoaded = true
      } catch (error) {
        this.recommendationError = this.requestError(error, '参考内容')
      } finally {
        this.recommendationLoading = false
      }
    },
    loadUserProfile() {
      const headers = this.authHeaders()
      if (!headers) return
      axios.get('/api/user/profile', { headers }).then((response) => {
        if (response.data?.status === 'success' && response.data.user && typeof response.data.user === 'object') {
          this.userInfo = response.data.user
          localStorage.setItem('userInfo', JSON.stringify(this.userInfo))
        }
      }).catch(() => {})
    },
    getImageUrl(imageUrl) {
      return imageUrl || ''
    },
    markHistoryImageFailed(imageUrl) {
      this.historyImageErrors = { ...this.historyImageErrors, [imageUrl]: true }
    },
    previewText(value, limit) {
      const text = String(value || '')
      return text.length > limit ? `${text.slice(0, limit)}…` : text
    },
    formatDate(timestamp) {
      if (!timestamp) return '时间未记录'
      const date = new Date(timestamp)
      return Number.isNaN(date.getTime()) ? '时间格式异常' : date.toLocaleString('zh-CN', { dateStyle: 'medium', timeStyle: 'short' })
    },
    logout() {
      localStorage.removeItem('token')
      localStorage.removeItem('userInfo')
      localStorage.removeItem('adminToken')
      localStorage.removeItem('adminUser')
      window.location.href = '/login.html'
    },
  },
  mounted() {
    const token = localStorage.getItem('token')
    const userInfo = localStorage.getItem('userInfo')
    if (!token || !userInfo) {
      window.location.href = '/login.html'
      return
    }
    try {
      this.userInfo = JSON.parse(userInfo)
    } catch {
      window.location.href = '/login.html'
      return
    }
    this.loadUserProfile()
    this.loadHistory()
  },
}
</script>

<style>
:root {
  color: #17221f;
  background: #f5f2ea;
  font-family: "Noto Serif CJK SC", "Songti SC", "STSong", serif;
}
* {
  box-sizing: border-box;
}
body {
  margin: 0;
  min-width: 320px;
  background: #f5f2ea;
}
button, input, select, textarea {
  font: inherit;
}
.workspace-shell {
  min-height: 100vh;
  background: #f5f2ea;
}
.workspace-header {
  min-height: 76px;
  padding: 0 clamp(1rem, 4vw, 4rem);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  border-bottom: 1px solid #c9c3b6;
  background: #f9f7f0;
}
.brand {
  display: inline-flex;
  align-items: center;
  gap: .8rem;
  color: #17221f;
  text-decoration: none;
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: .04em;
}
.brand-mark {
  width: 34px;
  height: 34px;
  display: grid;
  place-content: center;
  gap: 3px;
  border: 1px solid #245244;
}
.brand-mark i {
  display: block;
  width: 15px;
  height: 3px;
  background: #245244;
}
.brand-mark i:nth-child(2) {
  width: 22px;
  background: #a44536;
}
.brand-mark i:nth-child(3) {
  width: 10px;
  margin-left: 5px;
}
.account-summary {
  display: flex;
  align-items: center;
  gap: .85rem;
  color: #4f5a52;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
  font-size: .86rem;
}
.account-name {
  max-width: 14rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.text-button, .workspace-nav button, .direction-card, .primary-button, .secondary-button, .rating-buttons button {
  border-radius: 0;
  cursor: pointer;
}
.text-button {
  padding: .45rem 0;
  color: #245244;
  background: transparent;
  border: 0;
  border-bottom: 1px solid currentColor;
}
.workspace-layout {
  width: min(100%, 1440px);
  min-height: calc(100vh - 76px);
  margin: 0 auto;
  display: grid;
  grid-template-columns: 190px minmax(0, 1fr);
}
.workspace-nav {
  padding: 2rem 1.1rem;
  border-right: 1px solid #d4cec2;
  background: #ece8dd;
}
.workspace-nav button {
  width: 100%;
  display: flex;
  align-items: baseline;
  gap: .6rem;
  padding: .85rem .7rem;
  color: #465046;
  background: transparent;
  border: 0;
  border-bottom: 1px solid #d1ccbf;
  text-align: left;
  font-size: 1rem;
  transition: color .18s ease, background-color .18s ease;
}
.workspace-nav button span {
  color: #8a9389;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
  font-size: .68rem;
  letter-spacing: .08em;
}
.workspace-nav button:hover, .workspace-nav button.active {
  color: #fffdf5;
  background: #245244;
}
.workspace-nav button:hover span, .workspace-nav button.active span {
  color: #d8ebe2;
}
.workspace-content {
  min-width: 0;
  padding: clamp(1.5rem, 4vw, 4.5rem);
}
.section-heading {
  max-width: 50rem;
  margin-bottom: 2.25rem;
}
.section-heading-row {
  max-width: none;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
}
.section-index, .record-style {
  margin: 0 0 .75rem;
  color: #245244;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
  font-size: .68rem;
  font-weight: 700;
  letter-spacing: .15em;
}
.section-heading h1, .result-header h2 {
  margin: 0;
  color: #17221f;
  font-size: clamp(2.15rem, 4vw, 4.2rem);
  line-height: 1.15;
  letter-spacing: .03em;
}
.section-heading > p:last-child {
  margin: 1rem 0 0;
  color: #566057;
  line-height: 1.8;
}
.creation-form {
  max-width: 62rem;
  padding-top: 2rem;
  border-top: 2px solid #17221f;
}
.field-block {
  margin: 0 0 1.7rem;
  padding: 0;
  border: 0;
}
.field-block > label, .field-block legend {
  display: block;
  margin-bottom: .65rem;
  color: #27332c;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
  font-size: .95rem;
  font-weight: 700;
}
textarea, input, select {
  width: 100%;
  padding: .9rem 1rem;
  color: #17221f;
  background: #fbfaf5;
  border: 1px solid #aeb1a5;
  border-radius: 0;
  outline: none;
  line-height: 1.65;
  transition: border-color .18s ease, box-shadow .18s ease;
}
textarea {
  min-height: 168px;
  resize: vertical;
}
textarea::placeholder, input::placeholder {
  color: #778076;
}
textarea:focus, input:focus, select:focus {
  border-color: #245244;
  box-shadow: inset 0 -2px 0 #245244;
}
.field-help {
  margin: .5rem 0 0;
  color: #687169;
  font-size: .86rem;
  line-height: 1.6;
}
.direction-fieldset {
  padding: 1.3rem;
  border: 1px solid #c9c3b6;
  background: #f9f7f0;
}
.direction-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: .7rem;
  margin: 1rem 0 1.35rem;
}
.direction-card {
  min-height: 116px;
  padding: .9rem;
  color: #344039;
  background: #f6f3eb;
  border: 1px solid #bfc0b4;
  text-align: left;
  transition: color .18s ease, border-color .18s ease, background-color .18s ease;
}
.direction-card span {
  display: block;
  margin-bottom: .45rem;
  font-weight: 700;
}
.direction-card small {
  display: block;
  color: inherit;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
  font-size: .76rem;
  line-height: 1.55;
}
.direction-card:hover, .direction-card.active {
  color: #fffdf5;
  border-color: #245244;
  background: #245244;
}
.dimension-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}
.dimension-control {
  display: grid;
  gap: .5rem;
  color: #27332c;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
  font-size: .86rem;
  font-weight: 700;
}
.dimension-control select {
  min-height: 46px;
  padding-right: 2rem;
  font-weight: 400;
}
.style-preview {
  margin: -.2rem 0 1.5rem;
  padding: .8rem 1rem;
  color: #4e5951;
  border-left: 3px solid #245244;
  background: #ece8dd;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
  font-size: .86rem;
  line-height: 1.65;
}
.style-preview summary {
  cursor: pointer;
  color: #245244;
  font-weight: 700;
}
.style-preview p {
  margin: .65rem 0 0;
  overflow-wrap: anywhere;
}
.form-actions {
  display: flex;
  flex-wrap: wrap;
  gap: .75rem;
  margin-top: 1.5rem;
}
.primary-button, .secondary-button {
  min-height: 48px;
  padding: .75rem 1.1rem;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
  font-weight: 700;
  transition: background-color .18s ease, color .18s ease, border-color .18s ease;
}
.primary-button {
  color: #fffdf5;
  background: #17221f;
  border: 1px solid #17221f;
}
.primary-button:hover:not(:disabled) {
  background: #245244;
  border-color: #245244;
}
.secondary-button {
  color: #245244;
  background: transparent;
  border: 1px solid #245244;
}
.secondary-button:hover:not(:disabled) {
  color: #fffdf5;
  background: #245244;
}
.primary-button:disabled, .secondary-button:disabled {
  opacity: .62;
  cursor: wait;
}
.button-loading {
  display: inline-flex;
  align-items: center;
  gap: .55rem;
}
.inline-spinner, .large-spinner {
  display: inline-block;
  border: 2px solid rgba(255, 255, 255, .45);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin .8s linear infinite;
}
.inline-spinner {
  width: 1rem;
  height: 1rem;
  color: #fff;
}
.state-message {
  max-width: 48rem;
  margin: 1rem 0;
  padding: .9rem 1rem;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
  line-height: 1.65;
}
.error-state {
  color: #7d241d;
  background: #f6e6df;
  border-left: 4px solid #a44536;
}
.error-state a {
  color: inherit;
  font-weight: 700;
}
.generation-state {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  max-width: 62rem;
  margin-top: 2.5rem;
  padding: 2rem 0;
  border-top: 1px solid #c9c3b6;
  border-bottom: 1px solid #c9c3b6;
}
.generation-state h2 {
  margin: 0;
  font-size: 1.5rem;
}
.generation-state p {
  margin: .5rem 0 0;
  color: #5a645c;
  line-height: 1.6;
}
.large-spinner {
  flex: 0 0 auto;
  width: 44px;
  height: 44px;
  color: #245244;
  border-color: #b4c3ba;
  border-top-color: #245244;
}
.result-section {
  max-width: 70rem;
  margin-top: 3rem;
  padding-top: 2.2rem;
  border-top: 2px solid #17221f;
}
.result-header {
  margin-bottom: 1.5rem;
}
.result-header h2 {
  font-size: clamp(1.8rem, 3vw, 2.8rem);
}
.result-grid {
  display: grid;
  grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr);
  border: 1px solid #c9c3b6;
  background: #fbfaf5;
}
.image-stage {
  min-width: 0;
  padding: 1rem;
  border-right: 1px solid #c9c3b6;
  background: #e9e5d9;
}
.image-stage > img {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  background: #d9d7cc;
}
.image-unavailable {
  display: grid;
  place-content: center;
  min-height: 320px;
  padding: 2rem;
  color: #465046;
  text-align: center;
  border: 1px dashed #7c877c;
  background: repeating-linear-gradient(45deg, transparent, transparent 12px, rgba(36, 82, 68, .04) 12px, rgba(36, 82, 68, .04) 24px);
}
.image-unavailable span {
  width: 64px;
  height: 64px;
  margin: 0 auto 1rem;
  border: 1px solid #a44536;
  position: relative;
}
.image-unavailable span::after {
  content: "";
  position: absolute;
  top: 30px;
  left: -7px;
  width: 76px;
  height: 1px;
  background: #a44536;
  transform: rotate(-45deg);
}
.image-unavailable p {
  margin: 0;
  font-weight: 700;
}
.image-unavailable small {
  margin-top: .5rem;
  color: #687169;
}
.image-actions {
  margin-top: .85rem;
}
.inline-error {
  margin: .65rem 0 0;
  color: #8a2d23;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
  font-size: .86rem;
  line-height: 1.5;
}
.generated-copy {
  min-width: 0;
  padding: clamp(1.35rem, 3vw, 3rem);
}
.generated-copy h3 {
  margin: 0 0 1.6rem;
  overflow-wrap: anywhere;
  font-size: clamp(1.6rem, 2.7vw, 2.5rem);
  line-height: 1.35;
}
.content-copy {
  color: #354038;
  line-height: 1.9;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.result-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
  margin: 2rem 0;
  padding: 1rem 0;
  border-top: 1px solid #d4cec2;
  border-bottom: 1px solid #d4cec2;
}
.result-meta dt, .profile-list dt {
  color: #687169;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
  font-size: .76rem;
}
.result-meta dd {
  margin: .35rem 0 0;
  overflow-wrap: anywhere;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
  font-weight: 700;
}
.rating-panel {
  padding-top: .25rem;
}
.feedback-title {
  margin: 0 0 .75rem;
  color: #27332c;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
  font-weight: 700;
}
.rating-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: .45rem;
}
.rating-buttons button {
  min-width: 52px;
  min-height: 42px;
  color: #245244;
  background: transparent;
  border: 1px solid #245244;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
}
.rating-buttons button:hover:not(:disabled), .rating-buttons button.selected {
  color: #fffdf5;
  background: #245244;
}
.status-copy {
  margin: .7rem 0 0;
  color: #4a5b50;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
  font-size: .86rem;
}
.empty-state {
  margin-top: 1.5rem;
  padding: 3rem 1.5rem;
  color: #566057;
  border-top: 2px solid #17221f;
  border-bottom: 1px solid #c9c3b6;
  text-align: center;
  line-height: 1.7;
}
.empty-state h2 {
  margin: 0;
  color: #17221f;
  font-size: 1.6rem;
}
.empty-state p {
  margin: .7rem auto 1.25rem;
  max-width: 30rem;
}
.history-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  border-top: 2px solid #17221f;
  background: #c9c3b6;
}
.history-entry {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 1rem;
  min-width: 0;
  padding: 1rem;
  background: #fbfaf5;
}
.history-visual {
  min-width: 0;
  aspect-ratio: 1;
  background: #e9e5d9;
}
.history-visual img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.history-image-fallback {
  display: grid;
  place-content: center;
  height: 100%;
  color: #687169;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
  font-size: .75rem;
  text-align: center;
}
.history-entry h2 {
  margin: 0 0 .55rem;
  overflow-wrap: anywhere;
  font-size: 1.15rem;
  line-height: 1.4;
}
.history-entry p:not(.record-style) {
  margin: 0;
  color: #596259;
  font-size: .9rem;
  line-height: 1.65;
  overflow-wrap: anywhere;
}
.history-entry time {
  display: block;
  margin-top: .7rem;
  color: #788178;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
  font-size: .75rem;
}
.reference-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  border-top: 2px solid #17221f;
  background: #c9c3b6;
}
.reference-list, .profile-list {
  min-width: 0;
  margin: 0;
  padding: 1.5rem;
  background: #fbfaf5;
}
.reference-list h2 {
  margin: 0 0 1.2rem;
  font-size: 1.4rem;
}
.reference-list article {
  padding: 1rem 0;
  border-top: 1px solid #d4cec2;
}
.reference-list h3 {
  margin: 0;
  overflow-wrap: anywhere;
  font-size: 1.1rem;
}
.reference-list p {
  margin: .5rem 0 0;
  color: #596259;
  line-height: 1.55;
}
.profile-list {
  display: grid;
  gap: 1rem;
  max-width: 38rem;
  border-top: 2px solid #17221f;
}
.profile-list div {
  padding-bottom: 1rem;
  border-bottom: 1px solid #d4cec2;
}
.profile-list div:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}
.profile-list dd {
  margin: .4rem 0 0;
  overflow-wrap: anywhere;
  font-size: 1.15rem;
}
.workspace-nav button:focus-visible, .text-button:focus-visible, .direction-card:focus-visible, .primary-button:focus-visible, .secondary-button:focus-visible, .rating-buttons button:focus-visible, textarea:focus-visible, input:focus-visible, select:focus-visible, summary:focus-visible {
  outline: 3px solid #a44536;
  outline-offset: 3px;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@media (max-width: 900px) {
  .workspace-layout {
    grid-template-columns: 1fr;
  }
  .workspace-nav {
    display: flex;
    overflow-x: auto;
    padding: 0;
    border-right: 0;
    border-bottom: 1px solid #d4cec2;
  }
  .workspace-nav button {
    flex: 1 0 132px;
    justify-content: center;
    padding: .95rem .75rem;
    border-bottom: 0;
    border-right: 1px solid #d4cec2;
    text-align: center;
  }
  .workspace-content {
    padding: clamp(1.3rem, 4vw, 3rem);
  }
  .direction-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 680px) {
  .workspace-header {
    min-height: 70px;
    padding: .75rem 1rem;
  }
  .brand {
    font-size: .95rem;
  }
  .account-name {
    display: none;
  }
  .workspace-nav button {
    flex-basis: 105px;
    font-size: .9rem;
  }
  .section-heading-row {
    align-items: flex-start;
    flex-direction: column;
  }
  .section-heading h1 {
    font-size: clamp(2rem, 10vw, 3.1rem);
  }
  .direction-grid, .dimension-grid, .result-grid, .reference-grid {
    grid-template-columns: 1fr;
  }
  .direction-card {
    min-height: 0;
  }
  .image-stage {
    border-right: 0;
    border-bottom: 1px solid #c9c3b6;
  }
  .history-grid {
    grid-template-columns: 1fr;
  }
  .history-entry {
    grid-template-columns: 92px minmax(0, 1fr);
  }
  .result-meta {
    grid-template-columns: 1fr;
    gap: .7rem;
  }
}
@media (max-width: 390px) {
  .workspace-nav button {
    flex-basis: 88px;
    font-size: .82rem;
  }
  .workspace-nav button span {
    display: none;
  }
  .form-actions {
    flex-direction: column;
  }
  .primary-button, .secondary-button {
    width: 100%;
  }
  .history-entry {
    grid-template-columns: 1fr;
  }
  .history-visual {
    aspect-ratio: 16 / 9;
  }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    scroll-behavior: auto !important;
    transition-duration: .01ms !important;
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
  }
}
</style>
