<template>
  <div class="overview-charts">
    <!-- 原有图表结构和逻辑保持不变 -->
    <div class="chart-grid">
      <div class="chart-item">
        <canvas ref="userGrowthChart"></canvas>
      </div>
      <div class="chart-item">
        <canvas ref="contentGenerationChart"></canvas>
      </div>
      <div class="chart-item">
        <canvas ref="satisfactionChart"></canvas>
      </div>
      <div class="chart-item">
        <canvas ref="styleDistributionChart"></canvas>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, watch } from 'vue'
import Chart from 'chart.js/auto'

export default {
  name: 'OverviewCharts',
  props: {
    data: Object,
    dateRange: Object
  },
  emits: ['chart-rendered', 'chart-error'],
  setup(props, { emit }) {
    const userGrowthChart = ref(null)
    const contentGenerationChart = ref(null)
    const satisfactionChart = ref(null)
    const styleDistributionChart = ref(null)
    
    let charts = {}
    
    // 原有图表初始化逻辑保持不变
    const initCharts = () => {
      try {
        // 用户增长图表
        if (userGrowthChart.value) {
          charts.userGrowth = new Chart(userGrowthChart.value, {
            type: 'line',
            data: {
              labels: ['1月', '2月', '3月', '4月', '5月', '6月'],
              datasets: [{
                label: '新增用户',
                data: [65, 59, 80, 81, 56, 55],
                borderColor: 'rgb(75, 192, 192)',
                tension: 0.1
              }]
            }
          })
        }
        
        // 其他图表初始化...
        
        emit('chart-rendered', 'overview')
      } catch (error) {
        emit('chart-error', 'overview', error)
      }
    }
    
    onMounted(() => {
      initCharts()
    })
    
    watch(() => props.dateRange, () => {
      // 更新图表数据
      updateCharts()
    })
    
    const updateCharts = () => {
      // 原有更新图表数据的逻辑
    }
    
    return {
      userGrowthChart,
      contentGenerationChart,
      satisfactionChart,
      styleDistributionChart
    }
  }
}
</script>

<style scoped>
/* 原有样式保持不变 */
.overview-charts {
  padding: 20px;
}
.chart-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}
.chart-item {
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
</style>