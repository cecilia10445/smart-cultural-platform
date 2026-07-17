<template>
  <div class="chart-container half-chart">
    <div class="chart-title">
      <span>🚻</span>
      <span>用户性别比例</span>
    </div>
    <div class="chart-wrapper">
      <canvas ref="chartCanvas"></canvas>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, watch, nextTick } from 'vue'
import Chart from 'chart.js/auto'

export default {
  name: 'GenderDistributionChart',
  props: {
    data: {
      type: Array,
      default: () => []
    }
  },
  setup(props) {
    const chartCanvas = ref(null)
    const chartInstance = ref(null)

    const renderChart = () => {
      if (!chartCanvas.value ) return
      
      const ctx = chartCanvas.value.getContext('2d')
      
      if (chartInstance.value) {
        chartInstance.value.destroy()
      }
      
      const genderData = props.data
      const labels = genderData.map(item => {
        const genderMap = { 'female': '女性', 'male': '男性', 'unknown': '未知' }
        return genderMap[item.gender] || item.gender
      })
      const counts = genderData.map(item => item.count)
      
      chartInstance.value = new Chart(ctx, {
        type: 'doughnut',
        data: {
          labels: labels,
          datasets: [{
            data: counts,
            backgroundColor: ['#ff6b6b', '#4ecdc4', '#45aaf2'],
            borderWidth: 1
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: 'bottom',
              labels: {
                color: '#aaa'
              }
            }
          }
        }
      })
    }

    watch(() => props.data, (newData, oldData) => {
    console.log('GenderDistributionChart 数据变化:', newData)
      nextTick(() => {
        renderChart()
      })
    }, { deep: true })

    onMounted(() => {
      // 组件挂载后立即渲染图表
      nextTick(() => {
        renderChart()
      })
    })

    return {
      chartCanvas,
      renderChart
    }
  }
}
</script>

<style scoped>
.chart-container {
  background: linear-gradient(135deg, #2d2d2d 0%, #1a1a1a 100%);
  border-radius: 12px;
  padding: 25px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
  border: 1px solid #333;
  margin-bottom: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  flex: 1;
}

.half-chart {
  height: 100%;
}

.chart-title {
  font-size: 18px;
  margin-bottom: 20px;
  color: #fff;
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  flex-shrink: 0;
}

.chart-wrapper {
  flex: 1;
  position: relative;
  min-height: 0;
}
</style>