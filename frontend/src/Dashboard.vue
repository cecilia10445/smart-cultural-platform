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
        v-if="activeChart === 'overview'"
        :stats="stats"
      />
      
      <!-- 图表容器 -->
      <div class="chart-content">
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
            <KeywordTrendChart
              :data="dashboardData.hot_keywords"
              ref="keywordTrendChartRef"
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
import KeywordTrendChart from '@/components/dashboard/charts/KeywordTrendChart.vue'
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
    KeywordTrendChart,
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

    const userName = computed(() => {
      return userInfo.value?.name || userInfo.value?.username || '运营管理员'
    })

    const userEmail = computed(() => {
      return userInfo.value?.username ? `${userInfo.value.username}@aigc-platform.com` : 'admin@aigc-platform.com'
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
    const keywordTrendChartRef = ref(null)
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
    const loadStatsData = async () => {
      try {
        const token = localStorage.getItem('adminToken') || localStorage.getItem('token')
        const url = new URL('/api/dashboard/stats', window.location.origin)
        
        if (dateRange.value.startDate && dateRange.value.endDate) {
          url.searchParams.append('start_date', dateRange.value.startDate)
          url.searchParams.append('end_date', dateRange.value.endDate)
        }
        
        console.log('加载统计数据，URL:', url.toString())
        
        const response = await fetch(url, {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        })
        
        console.log('响应状态:', response.status, response.statusText)
        
        if (!response.ok) {
          const errorText = await response.text()
          console.error('HTTP错误响应:', errorText)
          throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`)
        }

        // 检查响应内容类型
        const contentType = response.headers.get('content-type')
        if (!contentType || !contentType.includes('application/json')) {
          const text = await response.text()
          console.error('非JSON响应:', text.substring(0, 200))
          throw new Error('服务器返回了非JSON响应')
        }

        const result = await response.json()
        console.log('统计数据响应:', result)
        
        if (result.status === 'success') {
          const statsData = result.data.stats
          stats.value.totalUsers = statsData.totalUsers?.toLocaleString() || '0'
          stats.value.totalGenerations = statsData.totalGenerations?.toLocaleString() || '0'
          stats.value.activeUsers = statsData.activeUsers?.toLocaleString() || '0'
          stats.value.avgRating = statsData.avgRating || '0.0'
          console.log('统计数据更新完成:', stats.value)
        }
      } catch (error) {
        console.error('加载统计数据失败:', error)
        // 设置模拟数据用于测试
        stats.value = {
          totalUsers: '1,234',
          totalGenerations: '5,678',
          activeUsers: '890',
          avgRating: '4.5'
        }
      }
    }

    const loadDashboardData = async () => {
      try {
        const token = localStorage.getItem('adminToken') || localStorage.getItem('token')
        const url = new URL('/api/dashboard/user-profile', window.location.origin)
        
        if (dateRange.value.startDate && dateRange.value.endDate) {
          url.searchParams.append('start_date', dateRange.value.startDate)
          url.searchParams.append('end_date', dateRange.value.endDate)
        }
        
        console.log('加载图表数据，URL:', url.toString())
        
        const response = await fetch(url, {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        })
        
        console.log('响应状态:', response.status, response.statusText)
        
        if (!response.ok) {
          const errorText = await response.text()
          console.error('HTTP错误响应:', errorText)
          throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`)
        }

        // 检查响应内容类型
        const contentType = response.headers.get('content-type')
        if (!contentType || !contentType.includes('application/json')) {
          const text = await response.text()
          console.error('非JSON响应:', text.substring(0, 200))
          throw new Error('服务器返回了非JSON响应')
        }

        const result = await response.json()
        console.log('图表数据响应:', result)
        
        if (result.status === 'success') {
          dashboardData.value = result.data
          console.log('图表数据更新完成')
        }
      } catch (error) {
        console.error('加载图表数据失败:', error)
        // 设置模拟数据用于测试
        dashboardData.value = getMockData()
      }
    }

    // 模拟数据函数（如果后端API不可用）
    const getMockData = () => {
      return {
        age_distribution: [
          { age_range: '1', count: 120 },
          { age_range: '2', count: 180 },
          { age_range: '3', count: 90 },
          { age_range: '4', count: 40 },
          { age_range: '5', count: 20 }
        ],
        gender_distribution: [
          { gender: 'female', count: 200 },
          { gender: 'male', count: 250 }
        ],
        active_period_distribution: [
          { period: '00:00-06:00', count: 50 },
          { period: '06:00-12:00', count: 120 },
          { period: '12:00-18:00', count: 180 },
          { period: '18:00-24:00', count: 100 }
        ],
        user_behavior_7days: {
          labels: ['10-13', '10-14', '10-15', '10-16', '10-17', '10-18', '10-19'],
          generation_data: [120, 150, 180, 200, 170, 190, 210],
          download_data: [80, 100, 120, 150, 130, 140, 160]
        },
        style_popularity: [
          { style: '现代简约', usage_count: 450 },
          { style: '复古风格', usage_count: 380 },
          { style: '自然风光', usage_count: 320 },
          { style: '抽象艺术', usage_count: 280 },
          { style: '城市建筑', usage_count: 250 }
        ],
        style_trend_30days: {
          labels: ['09-20', '09-25', '09-30', '10-05', '10-10', '10-15', '10-19'],
          datasets: [
            { label: '现代简约', data: [120, 130, 140, 150, 160, 170, 180] },
            { label: '复古风格', data: [100, 110, 120, 130, 140, 150, 160] },
            { label: '自然风光', data: [80, 90, 100, 110, 120, 130, 140] }
          ]
        },
        rating_distribution: [
          { rating: 1, count: 10 },
          { rating: 2, count: 25 },
          { rating: 3, count: 80 },
          { rating: 4, count: 200 },
          { rating: 5, count: 500 }
        ],
        hot_keywords: [
          { keyword: '风景', frequency: 150 },
          { keyword: '人物', frequency: 120 },
          { keyword: '建筑', frequency: 100 },
          { keyword: '动物', frequency: 80 },
          { keyword: '植物', frequency: 70 },
          { keyword: '天空', frequency: 60 },
          { keyword: '海洋', frequency: 50 }
        ],
        generation_efficiency: [
          { time_range: '<1秒', count: 300 },
          { time_range: '1-3秒', count: 450 },
          { time_range: '3-5秒', count: 200 },
          { time_range: '5-10秒', count: 80 },
          { time_range: '>10秒', count: 20 }
        ]
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
            'hot-keywords': [keywordTrendChartRef, wordCloudRef],
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
      keywordTrendChartRef,
      efficiencyChartRef,
      wordCloudRef,
      switchChart,
      applyDateRange,
      resetDateRange,
      selectLast7Days,
      selectLast30Days,
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
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  height: 100%;
  min-height: 0;
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