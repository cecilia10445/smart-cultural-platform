<template>
  <div class="app-container">
    <!-- 左侧边栏 -->
    <div class="sidebar">
      <div class="logo">
        <div class="logo-icon">🎨</div>
        <h2>智能文创平台</h2>
      </div>
      
      <div class="nav-item" :class="{ active: activeTab === 'generate' }" @click="switchTab('generate')">
        <div class="nav-icon">🚀</div>
        <span class="nav-text">开启对话</span>
      </div>
      
      <div class="nav-item" :class="{ active: activeTab === 'recommendations' }" @click="switchTab('recommendations')">
        <div class="nav-icon">🔥</div>
        <span class="nav-text">热门推荐</span>
      </div>
      
      <div class="nav-item" :class="{ active: activeTab === 'history' }" @click="switchTab('history')">
        <div class="nav-icon">📜</div>
        <span class="nav-text">历史记录</span>
      </div>
      
      <div class="nav-item" :class="{ active: activeTab === 'profile' }" @click="switchTab('profile')">
        <div class="nav-icon">👤</div>
        <span class="nav-text">用户信息</span>
      </div>
      
      <div class="nav-item" :class="{ active: activeTab === 'password' }" @click="switchTab('password')">
        <div class="nav-icon">🔒</div>
        <span class="nav-text">密码修改</span>
      </div>
      
      <div class="user-info">
        <div class="user-avatar">
          {{ getUserInitial() }}
        </div>
        <div class="user-name">{{ userInfo?.name || userInfo?.username }}</div>
        <div class="user-type">{{ getUserTypeText(userInfo?.user_type) }}</div>
        <button class="btn btn-outline-secondary btn-sm mt-3" @click="logout">
          🚪 退出登录
        </button>
      </div>
    </div>
    
    <!-- 右侧内容区 -->
    <div class="main-content">
      <div class="content-header" v-if="activeTab === 'generate'">
        <h3>🚀 智能内容生成</h3>
        <p class="mb-0">输入您的创意想法，AI将为您生成图文内容</p>
      </div>
      
      <div class="content-header" v-else-if="activeTab === 'recommendations'">
        <h3>🔥 热门推荐</h3>
        <p class="mb-0">发现平台最受欢迎的风格和关键词</p>
      </div>
      
      <div class="content-header" v-else-if="activeTab === 'history'">
        <h3>📜 历史记录</h3>
        <p class="mb-0">查看您的创作历史和成果</p>
      </div>
      
      <div class="content-header" v-else-if="activeTab === 'profile'">
        <h3>👤 用户信息</h3>
        <p class="mb-0">管理您的个人资料和设置</p>
      </div>
      
      <div class="content-header" v-else-if="activeTab === 'password'">
        <h3>🔒 密码修改</h3>
        <p class="mb-0">更新您的账户密码</p>
      </div>
      
      <div class="content-body">
        <!-- 内容生成 -->
        <div v-if="activeTab === 'generate'">
          <div class="row">
            <div class="col-md-8">
              <div class="input-group">
                <label for="prompt">✨ 主题描述：</label>
                <textarea id="prompt" v-model="prompt" 
                          placeholder="详细描述您想要生成的内容，例如：夏日黄昏的海边，金色的阳光洒在波光粼粼的海面上..." 
                          rows="4"></textarea>
              </div>

              <div class="input-group">
                <label for="style">🎭 选择风格：</label>
                <div class="style-section">
                  <!-- 左侧：预设风格 -->
                  <div class="style-presets">
                    <div class="style-grid">
                      <div v-for="styleOption in styleOptions" 
                           :key="styleOption"
                           class="style-option"
                           :class="{ active: style === styleOption }"
                           @click="selectStyle(styleOption)">
                        {{ styleOption }}
                      </div>
                    </div>
                  </div>
                  
                  <!-- 右侧：自定义风格 -->
                  <div class="custom-style-side">
                    <label>🎨 自定义风格：</label>
                    <div class="custom-style-input">
                      <input type="text" v-model="customStyle" 
                             placeholder="输入任何您想要的风格描述..." 
                             @input="useCustomStyle">
                    </div>
                  </div>
                </div>
              </div>

              <div class="d-flex gap-2 mb-3">
                <button class="btn btn-primary" @click="generateContent" :disabled="loading">
                  <span v-if="loading">
                    <span class="spinner-border spinner-border-sm me-2"></span>
                    生成中...
                  </span>
                  <span v-else>🚀 开始生成</span>
                </button>

                <button class="btn btn-outline-secondary" @click="clearAll" :disabled="loading">
                  🗑️ 清空
                </button>
              </div>

              <div v-if="error" class="error">
                ❌ {{ error }}
              </div>
            </div>
            
            <div class="col-md-4">
              <div class="card">
                <div class="card-body">
                  <h5 class="card-title">💡 使用提示</h5>
                  <ul class="list-unstyled mt-3">
                    <li class="mb-2">✅ 描述越详细，生成效果越好</li>
                    <li class="mb-2">✅ 可以指定艺术风格或氛围</li>
                    <li class="mb-2">✅ 支持中英文混合描述</li>
                    <li class="mb-2">✅ 生成时间约10-30秒</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>

          <!-- 生成结果 -->
          <div v-if="result && !loading" class="result mt-4">
            <div class="image-container">
              <h4>🖼️ 生成图片</h4>
              <img :src="result.image_url" :alt="prompt" @error="handleImageError" class="mt-3">
              
              <!-- 图片操作区域 -->
              <div class="image-actions mt-3">
                <div class="rating-section mb-3">
                  <label class="rating-label">💖 给这张图片评分：</label>
                  <div class="star-rating">
                    <span v-for="n in 5" 
                          :key="n"
                          class="star"
                          :class="{ active: userRating >= n }"
                          @click="rateImage(n)">
                      ⭐
                    </span>
                  </div>
                  <small class="text-muted ms-2">{{ userRating }}/5分</small>
                </div>
                
                <button class="btn btn-primary w-100" @click="downloadImage">
                  📥 下载图片
                </button>
              </div>
            </div>
            
            <div class="content-container">
              <h4>📝 生成内容</h4>
              <div class="content-box title-box mt-3">
                <strong>标题：</strong>{{ result.title }}
              </div>
              <div class="content-box">
                <strong>正文：</strong><br>
                {{ result.content }}
              </div>
              <div class="mt-3">
                <small class="text-muted">⏱️ 生成时间: {{ result.generation_time }}秒</small>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 热门推荐 -->
        <div v-if="activeTab === 'recommendations'">
          <div v-if="recommendationLoading" class="loading">
            <div class="loading-spinner"></div>
            <p class="mt-3">正在加载推荐数据...</p>
          </div>

          <div v-else-if="recommendationError" class="error">
            <p>❌ {{ recommendationError }}</p>
            <button class="btn btn-outline-primary btn-sm" @click="loadRecommendations">
              重新加载
            </button>
          </div>

          <div v-else-if="recommendationsLoaded && trendingStyles.length === 0 && trendingKeywords.length === 0" class="empty-history">
            <div class="icon">📭</div>
            <h5 class="mb-3">暂无推荐数据</h5>
            <button class="btn btn-outline-primary btn-sm" @click="loadRecommendations">
              重新加载
            </button>
          </div>

          <template v-else-if="recommendationsLoaded">
          <div class="row mb-4" v-if="trendingStyles.length > 0">
            <div class="col-12">
              <h4>🎨 热门风格推荐</h4>
              <div class="recommendation-grid">
                <div class="recommendation-card" v-for="style in trendingStyles" :key="style.style">
                  <div class="recommendation-icon">🎭</div>
                  <div class="recommendation-title">{{ style.style }}</div>
                  <div class="hot-score">推荐评分: {{ style.score }}</div>
                  <div v-if="style.reason" class="recommendation-desc">{{ style.reason }}</div>
                </div>
              </div>
            </div>
          </div>
          
          <div class="row" v-if="trendingKeywords.length > 0">
            <div class="col-12">
              <h4>🔥 热门关键词</h4>
              <div class="recommendation-grid">
                <div class="recommendation-card" v-for="keyword in trendingKeywords" :key="keyword.keyword">
                  <div class="recommendation-icon">🔑</div>
                  <div class="recommendation-title">{{ keyword.keyword }}</div>
                  <div class="recommendation-desc">出现频次: {{ keyword.frequency }}</div>
                  <div class="hot-score">热度: {{ keyword.hot_score }}</div>
                </div>
              </div>
            </div>
          </div>
          </template>
        </div>
        
        <!-- 历史记录 -->
        <div v-if="activeTab === 'history'">
          <div class="d-flex justify-content-between align-items-center mb-4">
            <h4>您的创作历史</h4>
            <button class="btn btn-outline-secondary btn-sm" @click="loadHistory" :disabled="loadingHistory">
              <span v-if="loadingHistory">
                <span class="spinner-border spinner-border-sm me-1"></span>
                加载中
              </span>
              <span v-else>🔄 刷新</span>
            </button>
          </div>

          <!-- 修复：使用正确的属性名 historyLoading -> loadingHistory -->
          <div v-if="loadingHistory" class="loading">
            <div class="loading-spinner"></div>
            <p class="mt-3">正在加载历史记录...</p>
          </div>

          <div v-if="historyError" class="error">
            ❌ {{ historyError }}
          </div>

          <!-- 历史记录网格 -->
          <div v-if="history.length > 0" class="history-grid">
            <div v-for="(record, index) in history" :key="index" class="history-card">
              <div class="history-image">
                <img :src="getImageUrl(record.image_url)" :alt="record.prompt" 
                     @error="handleHistoryImageError"
                     @click="previewImage(record)">
              </div>
              <div class="history-content">
                <h5>{{ record.title || record.prompt.substring(0, 40) + (record.prompt.length > 40 ? '...' : '') }}</h5>
                <p class="history-prompt">
                  {{ (record.content || record.prompt).substring(0, 80) }}{{ (record.content || record.prompt).length > 80 ? '...' : '' }}
                </p>
                <div class="history-meta">
                  <span class="history-style">{{ record.style || '通用' }}</span>
                  <span class="history-time">{{ formatDate(record.timestamp) }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 空状态 -->
          <div v-else-if="historyLoaded && history.length === 0" class="empty-history">
            <div class="icon">📝</div>
            <h5 class="mb-3">暂无生成记录</h5>
            <p class="text-muted mb-4">
              开始您的第一次创作，生成精彩内容吧！
            </p>
            <button class="btn btn-primary" @click="switchTab('generate')">
              🎨 开始创作
            </button>
          </div>
        </div>
        
        <!-- 用户信息 -->
        <div v-if="activeTab === 'profile'">
          <div class="row">
            <div class="col-md-6">
              <div class="card">
                <div class="card-body">
                  <h5 class="card-title">👤 个人信息</h5>
                  <div class="mt-4">
                    <div class="mb-3">
                      <label class="form-label">用户名</label>
                      <input type="text" class="form-control" :value="userInfo?.username" readonly>
                    </div>
                    <div class="mb-3">
                      <label class="form-label">姓名</label>
                      <input type="text" class="form-control" :value="userInfo?.name" readonly>
                    </div>
                    <div class="mb-3">
                      <label class="form-label">用户ID</label>
                      <input type="text" class="form-control" :value="userInfo?.user_id" readonly>
                    </div>
                    <div class="mb-3">
                      <label class="form-label">用户类型</label>
                      <input type="text" class="form-control" :value="getUserTypeText(userInfo?.user_type)" readonly>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div class="col-md-6">
              <div class="card">
                <div class="card-body">
                  <h5 class="card-title">📊 创作统计</h5>
                  <div class="mt-4 text-center">
                    <div class="display-4 text-dark mb-2">{{ history.length }}</div>
                    <p class="text-muted">总创作次数</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 密码修改 -->
        <div v-if="activeTab === 'password'">
          <div class="row justify-content-center">
            <div class="col-md-6">
              <div class="card">
                <div class="card-body">
                  <h5 class="card-title">🔒 修改密码</h5>
                  <div class="mt-4">
                    <div class="mb-3">
                      <label class="form-label">当前密码</label>
                      <input type="password" class="form-control" v-model="currentPassword">
                    </div>
                    <div class="mb-3">
                      <label class="form-label">新密码</label>
                      <input type="password" class="form-control" v-model="newPassword">
                    </div>
                    <div class="mb-3">
                      <label class="form-label">确认新密码</label>
                      <input type="password" class="form-control" v-model="confirmPassword">
                    </div>
                    <button class="btn btn-primary w-100" @click="changePassword">
                      🔄 更新密码
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  name: 'App',
  data() {
    return {
      activeTab: 'generate',
      prompt: '',
      style: '',
      customStyle: '',
      loading: false,
      error: '',
      result: null,
      userInfo: null,
      isGenerating: false,
      isDownloading: false,

      // 新增数据
      styleOptions: [
        "写实风格", "电影感", "鲜明色彩", "艺术感", 
        "自然风格", "赛博朋克", "极简主义", "戏剧化",
        "专业摄影", "水彩画风", "奇幻风格", "复古风"
      ],
      userRating: 0,
      
      // 历史记录相关 - 修复：使用正确的属性名
      history: [],
      loadingHistory: false,  // 修复：原来是 historyLoading
      historyError: '',
      historyLoaded: false,
      
      // 推荐相关
      trendingStyles: [],
      trendingKeywords: [],
      recommendationLoading: false,
      recommendationError: '',
      recommendationsLoaded: false,
      
      // 密码修改
      currentPassword: '',
      newPassword: '',
      confirmPassword: ''
    }
  },
  methods: {
    switchTab(tab) {
      this.activeTab = tab;
      if (tab === 'history') {
        this.loadHistory();
      } else if (tab === 'recommendations') {
        this.loadRecommendations();
      }
    },
    
    async generateContent() {                   
      if (this.isGenerating) return;

      if (!this.prompt.trim()) {
        this.error = '请输入主题描述';
        return;
      }

      this.isGenerating = true;
      this.loading = true;
      this.error = '';
      this.result = null;
      this.userRating = 0; // 重置评分

      const token = localStorage.getItem('token');
      if (!token) {
        this.error = '请先登录';
        this.loading = false;
        this.isGenerating = false;
        return;
      }

      try {
        const response = await axios.post('/api/generate', {
          prompt: this.prompt,
          style: this.style || '通用'
        }, {
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          }
        });

        if (response.data.status === 'success') {
          this.result = response.data;
          // 生成成功后自动刷新历史记录
          setTimeout(() => {
            this.loadHistory();
          }, 1000);
        } else {
          this.error = '生成失败：' + (response.data.message || '未知错误');
        }
      } catch (error) {
        console.error('API调用错误:', error);
        this.error = '请求失败：' + (error.response?.data?.message || error.message);
      } finally {
        this.loading = false;
        this.isGenerating = false;
      }
    },
    
    // 新增方法
    selectStyle(style) {
      this.style = style;
      this.customStyle = ''; // 清空自定义输入
    },
    
    useCustomStyle() {
      if (this.customStyle.trim()) {
        this.style = this.customStyle;
      }
    },
    
    rateImage(rating) {
      this.userRating = rating;
      // 可以在这里添加API调用保存评分
      this.saveRating(rating);
    },
    
    async saveRating(rating) {
      try {
        const token = localStorage.getItem('token');
        await axios.post('/api/rating', {
          image_url: this.result.image_url,
          prompt: this.prompt,
          style: this.style,
          rating: rating,
          log_id: this.result.log_id
        }, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });
        console.log('评分保存成功');
      } catch (error) {
        console.error('保存评分失败:', error);
      }
    },
    
    async downloadImage() {
      if (this.isDownloading) return;
      this.isDownloading = true;

      try {
        const token = localStorage.getItem('token');
        await axios.post('/api/download', {
          image_url: this.result.image_url,
          prompt: this.prompt,
          style: this.style
        }, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });
        
        // 创建下载链接
        const link = document.createElement('a');
        link.href = this.result.image_url;
        link.download = `ai-generated-${Date.now()}.jpg`;
        link.click();
        
        console.log('下载记录成功');
      } catch (error) {
        console.error('下载失败:', error);
        alert('下载失败，请重试');
      } finally {
        this.isDownloading = false;
      }
    },
    
    async loadHistory() {
      this.loadingHistory = true;
      this.historyError = '';
      
      const token = localStorage.getItem('token');
      if (!token) {
        this.historyError = '请先登录';
        this.loadingHistory = false;
        return;
      }

      try {
        const response = await axios.get('/api/user/history', {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });

        if (response.data.status === 'success') {
          this.history = response.data.data;
          this.historyLoaded = true;
        } else {
          this.historyError = '加载历史记录失败：' + (response.data.message || '未知错误');
        }
      } catch (error) {
        console.error('加载历史记录错误:', error);
        this.historyError = '请求失败：' + (error.response?.data?.message || error.message);
      } finally {
        this.loadingHistory = false;
      }
    },
    
    async loadRecommendations() {
      if (this.recommendationLoading) return;
      this.recommendationLoading = true;
      this.recommendationError = '';
      this.recommendationsLoaded = false;
      this.trendingStyles = [];
      this.trendingKeywords = [];

      try {
        const token = localStorage.getItem('token');
        if (!token) {
          this.recommendationError = '登录状态已失效，请重新登录';
          return;
        }

        const response = await axios.get('/api/recommendations/personalized', {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });
        
        const data = response.data?.data;
        if (response.data?.status !== 'success' || !data ||
            !Array.isArray(data.style_recommendations) || !Array.isArray(data.hot_keywords)) {
          this.recommendationError = '推荐服务返回的数据格式异常，请稍后重试';
          return;
        }

        const stylesValid = data.style_recommendations.every(style =>
          style &&
          typeof style.style === 'string' && style.style.trim().length > 0 &&
          typeof style.score === 'number' && Number.isFinite(style.score) &&
          (style.reason == null || typeof style.reason === 'string')
        );
        const keywordsValid = data.hot_keywords.every(keyword =>
          keyword &&
          typeof keyword.keyword === 'string' && keyword.keyword.trim().length > 0 &&
          typeof keyword.frequency === 'number' && Number.isFinite(keyword.frequency) &&
          typeof keyword.hot_score === 'number' && Number.isFinite(keyword.hot_score)
        );
        if (!stylesValid || !keywordsValid) {
          this.recommendationError = '推荐服务返回的数据格式异常，请稍后重试';
          return;
        }

        this.trendingStyles = data.style_recommendations;
        this.trendingKeywords = data.hot_keywords;
        this.recommendationsLoaded = true;
      } catch (error) {
        const status = error.response?.status;
        if (status === 401) {
          this.recommendationError = '登录状态已失效，请重新登录';
        } else if (status === 403) {
          this.recommendationError = '当前账户无权查看推荐数据';
        } else if (status === 503) {
          this.recommendationError = '推荐服务暂不可用，请稍后重试';
        } else {
          this.recommendationError = '推荐数据加载失败，请检查网络后重试';
        }
      } finally {
        this.recommendationLoading = false;
      }
    },

    // 修改 getImageUrl 方法
getImageUrl(imageUrl) {
  if (!imageUrl) {
    return '/images/default-image.png'; // 使用本地默认图片
  }
  
  console.log('原始图片路径:', imageUrl);
  
  // 情况1：处理数据库中的绝对路径
  if (imageUrl.startsWith('/home/mywork/smart-cultural-platform/static/')) {
    // 转换为相对路径，让Vite代理处理
    const relativePath = imageUrl.replace('/home/mywork/smart-cultural-platform', '');
    return relativePath; // 直接返回相对路径
  }
  
  // 情况2：处理相对路径（让Vite代理转发）
  if (imageUrl.startsWith('/static/') || imageUrl.startsWith('/images/')) {
    return imageUrl; // 直接返回，Vite会代理到localhost:5000
  }
  
  // 情况3：如果已经是完整URL，直接返回
  if (imageUrl.startsWith('http')) {
    return imageUrl;
  }
  
  // 情况4：处理其他相对路径
  if (imageUrl.startsWith('./') || !imageUrl.startsWith('/')) {
    return '/static/images/' + imageUrl;
  }
  
  // 默认情况：使用本地默认图片
  return '/images/default-image.png';
},
                
    async changePassword() {
      // 密码修改逻辑
      alert('密码修改功能待实现');
    },
    
    clearAll() {
      this.prompt = '';
      this.style = '';
      this.customStyle = '';
      this.result = null;
      this.error = '';
      this.userRating = 0;
    },
    
    handleImageError(event) {
      event.target.src = 'https://via.placeholder.com/512x512/333333/white?text=图片加载失败';
    },
    
    handleHistoryImageError(event) {
      const img = event.target;
      console.log('图片加载失败，使用默认图片');
      img.src = 'https://via.placeholder.com/350x200/333333/white?text=图片加载失败';
    },
    
    previewImage(record) {
      window.open(this.getImageUrl(record.image_url), '_blank');
    },
    
    formatDate(timestamp) {
      if (!timestamp) return '未知时间';
      const date = new Date(timestamp);
      const now = new Date();
      const diffMs = now - date;
      const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
      
      if (diffDays === 0) {
        return '今天 ' + date.toLocaleTimeString('zh-CN', {hour: '2-digit', minute:'2-digit'});
      } else if (diffDays === 1) {
        return '昨天 ' + date.toLocaleTimeString('zh-CN', {hour: '2-digit', minute:'2-digit'});
      } else if (diffDays < 7) {
        return `${diffDays}天前`;
      } else {
        return date.toLocaleDateString('zh-CN');
      }
    },
    
    getUserTypeText(userType) {
      const typeMap = {
        'real_user': '真实用户',
        'simulation_user': '模拟用户', 
        'new_user': '新用户'
      };
      return typeMap[userType] || userType;
    },
    
    getUserInitial() {
      if (!this.userInfo?.name) return 'U';
      return this.userInfo.name.charAt(0).toUpperCase();
    },
    
    logout() {
      localStorage.removeItem('token');
      localStorage.removeItem('userInfo');
      window.location.href = '/login.html';
    },
    
    loadUserProfile() {
      const token = localStorage.getItem('token');
      if (!token) return;
      
      axios.get('/api/user/profile', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
      .then(response => {
        if (response.data.status === 'success') {
          this.userInfo = response.data.user;
          localStorage.setItem('userInfo', JSON.stringify(this.userInfo));
        }
      })
      .catch(error => {
        console.error('加载用户信息失败:', error);
      });
    }
  },
  
  mounted() {
    // 检查登录状态
    const userInfo = localStorage.getItem('userInfo');
    const token = localStorage.getItem('token');
    
    if (!userInfo || !token) {
      alert('请先登录');
      window.location.href = '/login.html';
      return;
    }
    
    // 解析用户信息
    this.userInfo = JSON.parse(userInfo);
    console.log('当前用户:', this.userInfo);
    
    // 加载用户完整信息
    this.loadUserProfile();
    
    // 加载初始数据（不会自动生成图片）
    this.loadHistory();
    this.loadRecommendations();
    
    console.log('智能文创平台用户端加载完成');
  }
}
</script>

<style>
/* 原有的所有CSS样式完全保持不变 */
* { margin: 0; padding: 0; box-sizing: border-box; }
body { 
  font-family: 'Microsoft YaHei', sans-serif; 
  background: #f5f5f5;
  min-height: 100vh;
  overflow-x: hidden;
}

.app-container {
  display: flex;
  min-height: 100vh;
}

/* 左侧边栏 */
.sidebar {
  width: 280px;
  background: #ffffff;
  box-shadow: 2px 0 10px rgba(0,0,0,0.05);
  padding: 20px;
  display: flex;
  flex-direction: column;
}

.logo {
  text-align: center;
  padding: 20px 0;
  margin-bottom: 30px;
  border-bottom: 1px solid #e0e0e0;
}

.logo h2 {
  color: #333333;
  font-weight: bold;
  margin: 0;
}

.logo-icon {
  font-size: 2em;
  margin-bottom: 10px;
}

.nav-item {
  background: #f8f8f8;
  border-radius: 8px;
  padding: 15px 20px;
  margin-bottom: 15px;
  border: 1px solid #e0e0e0;
  transition: all 0.3s ease;
  cursor: pointer;
}

.nav-item:hover {
  background: #e8e8e8;
}

.nav-item.active {
  background: #333333;
  color: white;
}

.nav-icon {
  font-size: 1.3em;
  margin-right: 10px;
}

.nav-text {
  font-weight: 600;
  font-size: 1.1em;
}

.user-info {
  margin-top: auto;
  background: #f8f8f8;
  border-radius: 8px;
  padding: 15px;
  text-align: center;
  border: 1px solid #e0e0e0;
}

.user-avatar {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: #333333;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5em;
  margin: 0 auto 10px;
}

.user-name {
  font-weight: bold;
  color: #333333;
  margin-bottom: 5px;
}

.user-type {
  background: #555555;
  color: white;
  padding: 2px 10px;
  border-radius: 15px;
  font-size: 0.8em;
  display: inline-block;
}

/* 右侧内容区 */
.main-content {
  flex: 1;
  background: #ffffff;
  margin: 20px;
  border-radius: 12px;
  box-shadow: 0 5px 15px rgba(0,0,0,0.05);
  overflow: hidden;
}

.content-header {
  background: #333333;
  color: white;
  padding: 25px 30px;
}

.content-body {
  padding: 30px;
  min-height: 500px;
}

/* 内容生成样式 */
.input-group { 
  margin-bottom: 25px; 
}

label { 
  display: block; 
  margin-bottom: 8px; 
  font-weight: bold; 
  color: #333333; 
  font-size: 1.1em; 
}

input, select, textarea { 
  width: 100%; 
  padding: 12px; 
  margin-bottom: 15px; 
  border: 1px solid #d0d0d0; 
  border-radius: 6px; 
  font-size: 16px; 
  transition: border-color 0.3s; 
  background: #f8f8f8;
}

input:focus, select:focus, textarea:focus { 
  outline: none; 
  border-color: #666666; 
  background: #ffffff;
}

.btn-primary {
  padding: 12px 30px;
  background: #333333;
  border: none;
  border-radius: 6px;
  font-weight: bold;
  transition: all 0.2s;
}

.btn-primary:hover {
  background: #444444;
}

.btn-outline-secondary {
  padding: 12px 25px;
  border: 1px solid #666666;
  color: #666666;
  background: transparent;
  border-radius: 6px;
  font-weight: bold;
}

.result { 
  display: flex; 
  gap: 30px; 
  margin-top: 40px; 
  animation: fadeIn 0.5s ease-in; 
}

.image-container, .content-container { 
  flex: 1; 
}

.image-container img { 
  width: 100%; 
  max-width: 512px; 
  border-radius: 6px; 
  box-shadow: 0 3px 10px rgba(0,0,0,0.1); 
}

.content-box { 
  background: #f8f8f8; 
  padding: 20px; 
  margin-bottom: 15px; 
  border-radius: 6px; 
  border-left: 3px solid #666666; 
}

.title-box { 
  background: #e8e8e8; 
  border-left-color: #333333; 
  font-size: 1.2em; 
  font-weight: bold; 
}

.loading { 
  text-align: center; 
  padding: 40px; 
}

.loading-spinner { 
  border: 4px solid #e0e0e0; 
  border-top: 4px solid #333333; 
  border-radius: 50%; 
  width: 40px; 
  height: 40px; 
  animation: spin 1s linear infinite; 
  margin: 0 auto 20px; 
}

.error { 
  background: #f8f8f8; 
  color: #c62828; 
  padding: 15px; 
  border-radius: 6px; 
  margin-top: 15px; 
  border-left: 3px solid #c62828; 
}

/* 风格选择网格 */
.style-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-top: 10px;
}

.style-option {
  background: #f8f8f8;
  border: 1px solid #d0d0d0;
  border-radius: 6px;
  padding: 12px 8px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
  font-size: 0.9em;
  font-weight: 500;
}

.style-option:hover {
  background: #e8e8e8;
}

.style-option.active {
  background: #333333;
  color: white;
  border-color: #333333;
}

/* 自定义风格输入框 */
.style-section {
  display: flex;
  gap: 30px;
  align-items: flex-start;
}

.style-presets {
  flex: 1;
}

.custom-style-side {
  flex: 1;
  margin-top: 0;
}

.custom-style-side .custom-style-input {
  margin-top: 10px;
}

/* 评分样式 */
.rating-section {
  text-align: center;
}

.rating-label {
  display: block;
  margin-bottom: 8px;
  font-weight: bold;
  color: #333333;
}

.star-rating {
  display: inline-flex;
  gap: 5px;
}

.star {
  font-size: 1.5em;
  cursor: pointer;
  transition: all 0.2s ease;
  opacity: 0.6;
}

.star:hover {
  transform: scale(1.2);
  opacity: 1;
}

.star.active {
  opacity: 1;
  color: #333333;
  transform: scale(1.1);
}

/* 图片操作区域 */
.image-actions {
  border-top: 1px solid #e0e0e0;
  padding-top: 15px;
}

/* 历史记录样式 */
.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 25px;
  margin-top: 20px;
}

.history-card {
  background: #ffffff;
  border-radius: 8px;
  box-shadow: 0 3px 10px rgba(0,0,0,0.05);
  overflow: hidden;
  transition: all 0.3s ease;
  border: 1px solid #e8e8e8;
}

.history-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 5px 15px rgba(0,0,0,0.1);
}

.history-image {
  height: 200px;
  overflow: hidden;
}

.history-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s ease;
}

.history-card:hover .history-image img {
  transform: scale(1.05);
}

.history-content {
  padding: 20px;
}

.history-content h5 {
  color: #333333;
  margin-bottom: 10px;
  font-weight: 600;
  line-height: 1.4;
}

.history-prompt {
  color: #666666;
  font-size: 0.9em;
  margin-bottom: 8px;
  line-height: 1.4;
}

.history-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid #e8e8e8;
}

.history-style {
  background: #333333;
  color: white;
  padding: 4px 12px;
  border-radius: 15px;
  font-size: 0.8em;
  font-weight: 500;
}

.history-time {
  color: #888888;
  font-size: 0.8em;
}

.empty-history {
  text-align: center;
  padding: 60px 20px;
  color: #666666;
}

.empty-history .icon {
  font-size: 4em;
  margin-bottom: 20px;
  opacity: 0.5;
}

/* 推荐样式 */
.recommendation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 20px;
  margin-top: 20px;
}

.recommendation-card {
  background: #ffffff;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 3px 10px rgba(0,0,0,0.05);
  text-align: center;
  transition: all 0.3s ease;
  border: 1px solid #e8e8e8;
}

.recommendation-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 5px 15px rgba(0,0,0,0.1);
}

.recommendation-icon {
  font-size: 2em;
  margin-bottom: 10px;
  color: #333333;
}

.recommendation-title {
  font-weight: bold;
  color: #333333;
  margin-bottom: 8px;
}

.recommendation-desc {
  color: #666666;
  font-size: 0.9em;
  line-height: 1.4;
}

.hot-score {
  background: #555555;
  color: white;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 0.8em;
  margin-top: 8px;
  display: inline-block;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
