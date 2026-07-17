<template>
  <div class="chart-container half-chart">
    <div class="chart-title">
      <span>📈</span>
      <span>关键词趋势分析</span>
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
  name: 'KeywordTrendChart',
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
      
      const keywordData = props.data
      const ctx = chartCanvas.value.getContext('2d')
      
      if (chartInstance.value) {
        chartInstance.value.destroy()
      }
      
      // 取前3个关键词展示趋势
      const topKeywords = keywordData.slice(0, 3)
      const colors = ['#ff6b6b', '#4ecdc4', '#45aaf2']
      
      const datasets = topKeywords.map((keyword, index) => {
        // 模拟趋势数据
        const baseValue = keyword.frequency / 10
        const trendData = Array(7).fill(0).map((_, i) => 
          Math.round(baseValue * (0.8 + Math.random() * 0.4))
        )
        
        return {
          label: keyword.keyword,
          data: trendData,
          borderColor: colors[index % colors.length],
          backgroundColor: 'transparent',
          tension: 0.3
        }
      })
      
      const labels = Array(7).fill(0).map((_, i) => {
        const date = new Date()
        date.setDate(date.getDate() - (6 - i))
        return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
      })
      
      chartInstance.value = new Chart(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: datasets
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: 'top',
              labels: {
                color: '#aaa'
              }
            }
          },
          scales: {
            y: {
              beginAtZero: true,
              grid: {
                color: 'rgba(255, 255, 255, 0.1)'
              },
              ticks: {
                color: '#aaa'
              }
            },
            x: {
              grid: {
                color: 'rgba(255, 255, 255, 0.1)'
              },
              ticks: {
                color: '#aaa'
              }
            }
          }
        }
      })
    }

    watch(() => props.data, (newData, oldData) => {
      console.log('KeywordTrendChart 数据变化:', newData)
      nextTick(() => {
        renderChart()
      })
    }, { deep: true })

    onMounted(() => {
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