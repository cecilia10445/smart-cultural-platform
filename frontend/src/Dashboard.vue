<template>
  <div class="dashboard-container">
    <!-- 左侧导航面板 -->
    <Sidebar
      :activeChart="activeChart"
      :navItems="navItems"
      :userName="userName"
      :userEmail="userEmail"
      :userInitial="userInitial"
      @switch-chart="switchChart"
      @logout="logout"
    />
    
    <!-- 右侧内容区域 -->
    <div class="main-content">
      <Header
        :chartTitle="chartTitle"
        :dateRange="dateRange"
        :currentDate="currentDate"
        @apply-date-range="applyDateRange"
        @reset-date-range="resetDateRange"
        @select-last-7-days="selectLast7Days"
        @select-last-30-days="selectLast30Days"
      />
      
      <!-- 数据概览卡片 -->
      <StatsCards
        v-if="activeChart === 'overview' && statsLoaded && statsHasData && !statsError"
        :stats="stats"
      />

      <div v-if="activeChart === 'overview' && statsLoading" class="data-state">
        正在加载统计数据...
      </div>
      <div v-else-if="activeChart === 'overview' && statsError" class="data-state error-state">
        <span>{{ statsError }}</span>
        <button @click="loadStatsData">重试统计数据</button>
      </div>
      <div v-else-if="activeChart === 'overview' && statsLoaded && !statsHasData" class="data-state">
        暂无统计数据
      </div>

      <div v-if="profileLoading" class="data-state">正在加载画像数据...</div>
      <div v-else-if="profileError" class="data-state error-state">
        <span>{{ profileError }}</span>
        <button @click="loadDashboardData">重试画像数据</button>
      </div>
      <div v-else-if="profileLoaded && !currentChartHasData" class="data-state">
        {{ currentChartEmptyMessage }}
      </div>
      
      <!-- 图表容器 -->
      <div v-if="profileLoaded && currentChartHasData && !profileError" class="chart-content">
        <!-- 数据概览 -->
        <div id="overview" class="chart-section" v-show="activeChart === 'overview'">
          <div class="chart-row">
            <AgeDistributionChart
              :data="dashboardData.age_distribution"
              ref="ageChartRef"
            />
            <GenderDistributionChart
              :data="dashboardData.gender_distribution"
              ref="genderChartRef"
            />
          </div>
        </div>
        
        <!-- 用户活跃时段 -->
        <div id="active-period" class="chart-section" v-show="activeChart === 'active-period'">
          <ActivePeriodChart
            :data="dashboardData.active_period_distribution"
            ref="activePeriodChartRef"
          />
        </div>
        
        <!-- 用户行为分析 -->
        <div id="user-behavior" class="chart-section" v-show="activeChart === 'user-behavior'">
          <UserBehaviorChart
            :data="dashboardData.user_behavior_7days"
            ref="behaviorDetailChartRef"
          />
        </div>
        
        <!-- 风格热度排行 -->
        <div id="style-popularity" class="chart-section" v-show="activeChart === 'style-popularity'">
          <StylePopularityChart
            :data="dashboardData.style_popularity"
            ref="stylePopularityChartRef"
          />
        </div>
        
        <!-- 风格趋势分析 -->
        <div id="style-trend" class="chart-section" v-show="activeChart === 'style-trend'">
          <StyleTrendChart
            :data="dashboardData.style_trend_30days"
            ref="styleTrendChartRef"
          />
        </div>
        
        <!-- 用户满意度 -->
        <div id="rating-distribution" class="chart-section" v-show="activeChart === 'rating-distribution'">
          <RatingDistributionChart
            :data="dashboardData.rating_distribution"
            ref="ratingChartRef"
          />
        </div>
        
        <!-- 热门关键词 -->
        <div id="hot-keywords" class="chart-section" v-show="activeChart === 'hot-keywords'">
          <div class="chart-row">
            <WordCloud
              :data="dashboardData.hot_keywords"
              ref="wordCloudRef"
            />
          </div>
        </div>
        
        <!-- 生成效率分析 -->
        <div id="generation-efficiency" class="chart-section" v-show="activeChart === 'generation-efficiency'">
          <GenerationEfficiencyChart
            :data="dashboardData.generation_efficiency"
            ref="efficiencyChartRef"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, watch, computed, nextTick } from 'vue'
import Sidebar from '@/components/dashboard/layout/Sidebar.vue'
import Header from '@/components/dashboard/layout/Header.vue'
import StatsCards from '@/components/dashboard/StatsCards.vue'
import AgeDistributionChart from '@/components/dashboard/charts/AgeDistributionChart.vue'
import GenderDistributionChart from '@/components/dashboard/charts/GenderDistributionChart.vue'
import ActivePeriodChart from '@/components/dashboard/charts/ActivePeriodChart.vue'
import UserBehaviorChart from '@/components/dashboard/charts/UserBehaviorChart.vue'
import StylePopularityChart from '@/components/dashboard/charts/StylePopularityChart.vue'
import StyleTrendChart from '@/components/dashboard/charts/StyleTrendChart.vue'
import RatingDistributionChart from '@/components/dashboard/charts/RatingDistributionChart.vue'
import GenerationEfficiencyChart from '@/components/dashboard/charts/GenerationEfficiencyChart.vue'
import WordCloud from '@/components/dashboard/charts/WordCloud.vue'

export default {
  name: 'Dashboard',
  components: {
    Sidebar,
    Header,
    StatsCards,
    AgeDistributionChart,
    GenderDistributionChart,
    ActivePeriodChart,
    UserBehaviorChart,
    StylePopularityChart,
    StyleTrendChart,
    RatingDistributionChart,
    GenerationEfficiencyChart,
    WordCloud
  },
  setup() {
    // 响应式数据
    const activeChart = ref('overview')
    const dateRange = ref({
      startDate: '',
      endDate: ''
    })
    const dashboardData = ref({})
    const userInfo = ref({})
    const statsLoading = ref(false)
    const statsError = ref('')
    const statsLoaded = ref(false)
    const statsHasData = ref(false)
    const profileLoading = ref(false)
    const profileError = ref('')
    const profileLoaded = ref(false)
    
    // 统计数据
    const stats = ref({
      totalUsers: '--',
      totalGenerations: '--',
      activeUsers: '--',
      avgRating: '--'
    })

    // 导航项
    const navItems = [
      { id: 'overview', text: '数据概览', icon: '📈' },
      { id: 'active-period', text: '用户活跃时段', icon: '⏰' },
      { id: 'user-behavior', text: '用户行为分析', icon: '📊' },
      { id: 'style-popularity', text: '风格热度排行', icon: '🔥' },
      { id: 'style-trend', text: '风格趋势分析', icon: '📅' },
      { id: 'rating-distribution', text: '用户满意度', icon: '⭐' },
      { id: 'hot-keywords', text: '热门关键词', icon: '🔍' },
      { id: 'generation-efficiency', text: '生成效率分析', icon: '⚡' }
    ]

    // 计算属性
    const chartTitle = computed(() => {
      const nav = navItems.find(item => item.id === activeChart.value)
      return nav ? nav.text : '数据面板'
    })

    const currentDate = computed(() => {
      return new Date().toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      })
    })

    const currentChartHasData = computed(() => {
      const data = dashboardData.value
      const checks = {
        overview: () => data.age_distribution.length > 0 || data.gender_distribution.length > 0,
        'active-period': () => data.active_period_distribution.length > 0,
        'user-behavior': () => data.user_behavior_7days.labels.length > 0,
        'style-popularity': () => data.style_popularity.length > 0,
        'style-trend': () => data.style_trend_30days.labels.length > 0 && data.style_trend_30days.datasets.length > 0,
        'rating-distribution': () => data.rating_distribution.length > 0,
        'hot-keywords': () => data.hot_keywords.length > 0,
        'generation-efficiency': () => data.generation_efficiency.length > 0
      }
      return profileLoaded.value ? checks[activeChart.value]() : false
    })

    const currentChartEmptyMessage = computed(() => {
      const messages = {
        overview: '暂无年龄或性别分布数据',
        'active-period': '暂无用户活跃时段数据',
        'user-behavior': '暂无用户行为数据',
        'style-popularity': '暂无风格热度数据',
        'style-trend': '暂无风格趋势数据',
        'rating-distribution': '暂无用户满意度数据',
        'hot-keywords': '暂无热门关键词数据',
        'generation-efficiency': '暂无生成效率数据'
      }
      return messages[activeChart.value]
    })

    const userName = computed(() => {
      return userInfo.value?.name || userInfo.value?.username || '未登录用户'
    })

    const userEmail = computed(() => {
      return userInfo.value?.email || ''
    })

    const userInitial = computed(() => {
      return userName.value.charAt(0).toUpperCase()
    })

    // 图表组件引用
    const ageChartRef = ref(null)
    const genderChartRef = ref(null)
    const activePeriodChartRef = ref(null)
    const behaviorDetailChartRef = ref(null)
    const stylePopularityChartRef = ref(null)
    const styleTrendChartRef = ref(null)
    const ratingChartRef = ref(null)
    const efficiencyChartRef = ref(null)
    const wordCloudRef = ref(null)

    // 方法
    const switchChart = (chartId) => {
      activeChart.value = chartId
    }

    const applyDateRange = () => {
      console.log('应用日期范围:', dateRange.value)
      Promise.all([loadStatsData(), loadDashboardData()])
    }

    const resetDateRange = () => {
      const endDate = new Date()
      const startDate = new Date()
      startDate.setDate(startDate.getDate() - 30)
      
      dateRange.value = {
        startDate: startDate.toISOString().split('T')[0],
        endDate: endDate.toISOString().split('T')[0]
      }
      Promise.all([loadStatsData(), loadDashboardData()])
    }

    const selectLast7Days = () => {
      const end = new Date()
      const start = new Date()
      start.setDate(end.getDate() - 7)
      dateRange.value = {
        startDate: start.toISOString().split('T')[0],
        endDate: end.toISOString().split('T')[0]
      }
      Promise.all([loadStatsData(), loadDashboardData()])
    }

    const selectLast30Days = () => {
      const end = new Date()
      const start = new Date()
      start.setDate(end.getDate() - 30)
      dateRange.value = {
        startDate: start.toISOString().split('T')[0],
        endDate: end.toISOString().split('T')[0]
      }
      Promise.all([loadStatsData(), loadDashboardData()])
    }

    // API 调用
    const statusMessage = (status, resourceName) => {
      if (status === 401) return '登录状态已失效，请重新登录'
      if (status === 403) return `当前账户无权查看${resourceName}`
      if (status === 503) return `${resourceName}暂不可用，请稍后重试`
      return `${resourceName}加载失败，请检查网络后重试`
    }

    const loadStatsData = async () => {
      statsLoading.value = true
      statsError.value = ''
      statsLoaded.value = false
      statsHasData.value = false
      stats.value = {
        totalUsers: '--',
        totalGenerations: '--',
        activeUsers: '--',
        avgRating: '--'
      }

      try {
        const token = localStorage.getItem('adminToken') || localStorage.getItem('token')
        if (!token) {
          statsError.value = '登录状态已失效，请重新登录'
          return
        }
        const url = new URL('/api/dashboard/stats', window.location.origin)
        
        if (dateRange.value.startDate && dateRange.value.endDate) {
          url.searchParams.append('start_date', dateRange.value.startDate)
          url.searchParams.append('end_date', dateRange.value.endDate)
        }
        
        const response = await fetch(url, {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        })
        
        if (!response.ok) {
          statsError.value = statusMessage(response.status, '统计数据')
          return
        }

        const contentType = response.headers.get('content-type')
        if (!contentType || !contentType.includes('application/json')) {
          statsError.value = '统计服务返回的数据格式异常，请稍后重试'
          return
        }

        const result = await response.json()
        const statsData = result?.data?.stats
        if (result?.status !== 'success' || !statsData || typeof statsData !== 'object' || Array.isArray(statsData)) {
          statsError.value = '统计服务返回的数据格式异常，请稍后重试'
          return
        }

        const requiredStatsFields = ['totalUsers', 'totalGenerations', 'activeUsers', 'avgRating']
        const statsKeys = Object.keys(statsData)
        if (statsKeys.length === 0) {
          statsLoaded.value = true
          return
        }
        if (!requiredStatsFields.every(field =>
          Object.prototype.hasOwnProperty.call(statsData, field) &&
          typeof statsData[field] === 'number' && Number.isFinite(statsData[field])
        )) {
          statsError.value = '统计服务返回的数据格式异常，请稍后重试'
          return
        }

        stats.value = {
          totalUsers: statsData.totalUsers.toLocaleString(),
          totalGenerations: statsData.totalGenerations.toLocaleString(),
          activeUsers: statsData.activeUsers.toLocaleString(),
          avgRating: statsData.avgRating
        }
        statsHasData.value = true
        statsLoaded.value = true
      } catch {
        statsError.value = '统计数据加载失败，请检查网络后重试'
      } finally {
        statsLoading.value = false
      }
    }

    const loadDashboardData = async () => {
      profileLoading.value = true
      profileError.value = ''
      profileLoaded.value = false
      dashboardData.value = {}

      try {
        const token = localStorage.getItem('adminToken') || localStorage.getItem('token')
        if (!token) {
          profileError.value = '登录状态已失效，请重新登录'
          return
        }
        const url = new URL('/api/dashboard/user-profile', window.location.origin)
        
        if (dateRange.value.startDate && dateRange.value.endDate) {
          url.searchParams.append('start_date', dateRange.value.startDate)
          url.searchParams.append('end_date', dateRange.value.endDate)
        }
        
        const response = await fetch(url, {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        })
        
        if (!response.ok) {
          profileError.value = statusMessage(response.status, '画像数据')
          return
        }

        const contentType = response.headers.get('content-type')
        if (!contentType || !contentType.includes('application/json')) {
          profileError.value = '画像服务返回的数据格式异常，请稍后重试'
          return
        }

        const result = await response.json()
        if (result?.status !== 'success' || !result.data || typeof result.data !== 'object' || Array.isArray(result.data)) {
          profileError.value = '画像服务返回的数据格式异常，请稍后重试'
          return
        }

        const data = result.data
        const arraysValid = [
          'age_distribution',
          'gender_distribution',
          'active_period_distribution',
          'style_popularity',
          'rating_distribution',
          'hot_keywords',
          'generation_efficiency'
        ].every(field => Array.isArray(data[field]))
        const behaviorValid = data.user_behavior_7days &&
          typeof data.user_behavior_7days === 'object' &&
          !Array.isArray(data.user_behavior_7days) &&
          Array.isArray(data.user_behavior_7days.labels)
        const styleTrendValid = data.style_trend_30days &&
          typeof data.style_trend_30days === 'object' &&
          !Array.isArray(data.style_trend_30days) &&
          Array.isArray(data.style_trend_30days.labels) &&
          Array.isArray(data.style_trend_30days.datasets)
        if (!arraysValid || !behaviorValid || !styleTrendValid) {
          profileError.value = '画像服务返回的数据格式异常，请稍后重试'
          return
        }

        dashboardData.value = data
        profileLoaded.value = true
      } catch {
        profileError.value = '画像数据加载失败，请检查网络后重试'
      } finally {
        profileLoading.value = false
      }
    }

    // 图表渲染方法 - 简化版本
    const renderCurrentChart = async () => {
      await nextTick()
      
      setTimeout(() => {
        try {
          // 调用各个图表组件的渲染方法
          const chartRefs = {
            'overview': [ageChartRef, genderChartRef],
            'active-period': [activePeriodChartRef],
            'user-behavior': [behaviorDetailChartRef],
            'style-popularity': [stylePopularityChartRef],
            'style-trend': [styleTrendChartRef],
            'rating-distribution': [ratingChartRef],
            'hot-keywords': [wordCloudRef],
            'generation-efficiency': [efficiencyChartRef]
          }

          const currentRefs = chartRefs[activeChart.value]
          if (currentRefs) {
            currentRefs.forEach(ref => {
              if (ref.value && ref.value.renderChart) {
                ref.value.renderChart()
              }
            })
          }
        } catch (error) {
          console.error(`渲染${activeChart.value}图表失败:`, error)
        }
      }, 100)
    }

    const logout = () => {
      if (confirm('确定要退出登录吗？')) {
        localStorage.removeItem('adminToken')
        localStorage.removeItem('adminUser')
        localStorage.removeItem('token')
        localStorage.removeItem('userInfo')
        window.location.href = '/login.html'
      }
    }

    // 生命周期
    onMounted(() => {
      const storedUser = localStorage.getItem('adminUser') || localStorage.getItem('userInfo')
      const token = localStorage.getItem('adminToken') || localStorage.getItem('token')
      
      if (!storedUser || !token) {
        alert('请先登录运营账户')
        window.location.href = '/login.html'
        return
      }
      
      userInfo.value = JSON.parse(storedUser)
      
      if (userInfo.value.role !== 'admin') {
        alert('无权限访问运营端，请使用运营账户登录')
        window.location.href = '/login.html'
        return
      }

      console.log('用户验证通过:', userInfo.value.username)
      selectLast30Days()
    })

    // 监听器
    watch(activeChart, renderCurrentChart)
    watch(dashboardData, renderCurrentChart, { deep: true })

    return {
      activeChart,
      dateRange,
      dashboardData,
      userInfo,
      stats,
      statsLoading,
      statsError,
      statsLoaded,
      statsHasData,
      profileLoading,
      profileError,
      profileLoaded,
      currentChartHasData,
      currentChartEmptyMessage,
      navItems,
      chartTitle,
      currentDate,
      userName,
      userEmail,
      userInitial,
      ageChartRef,
      genderChartRef,
      activePeriodChartRef,
      behaviorDetailChartRef,
      stylePopularityChartRef,
      styleTrendChartRef,
      ratingChartRef,
      efficiencyChartRef,
      wordCloudRef,
      switchChart,
      applyDateRange,
      resetDateRange,
      selectLast7Days,
      selectLast30Days,
      loadStatsData,
      loadDashboardData,
      logout
    }
  }
}
</script>

<style scoped>
/* 样式保持不变 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
  font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
}

.dashboard-container {
  display: flex;
  min-height: 100vh;
  width: 100%;
  background: #1a1a1a;
  color: #e0e0e0;
}

/* 右侧内容区域 */
.main-content {
  flex: 1;
  padding: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  background: #1a1a1a;
  height: 100vh;
  overflow: hidden;
}

.chart-content {
  flex: 1;
  padding: 20px 30px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.chart-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

/* 数据概览页面布局 */
#overview {
  display: flex;
  flex-direction: column;
  height: 100%;
}

#overview .chart-row {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 0;
  min-height: 0;
}

/* 热门关键词页面布局 */
#hot-keywords .chart-row {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr;
  gap: 20px;
  height: 100%;
  min-height: 0;
}

.data-state {
  margin: 20px 30px 0;
  padding: 18px;
  border: 1px solid #444;
  border-radius: 8px;
  background: #242424;
  color: #ddd;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.data-state.error-state {
  border-color: #8b4545;
  color: #ffb4b4;
}

.data-state button {
  border: 1px solid #777;
  border-radius: 6px;
  padding: 6px 12px;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

/* 响应式调整 */
@media (max-width: 1200px) {
  .chart-row {
    grid-template-columns: 1fr;
  }
}

/* 滚动条样式 */
::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  background: #2d2d2d;
}

::-webkit-scrollbar-thumb {
  background: #555;
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: #777;
}
</style>
