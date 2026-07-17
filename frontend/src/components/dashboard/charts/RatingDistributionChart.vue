<template>
  <div class="chart-container full-chart">
    <div class="chart-title">
      <span>⭐</span>
      <span>用户满意度评分分布</span>
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
  name: 'RatingDistributionChart',
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
      
      const ratingData = props.data
      const labels = ratingData.map(item => item.rating + '分')
      const counts = ratingData.map(item => item.count)
      
      chartInstance.value = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [{
            label: '评分数量',
            data: counts,
            backgroundColor: '#fbc531',
            borderColor: '#e1b12c',
            borderWidth: 1
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: false
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
  console.log('RatingDistributionChart 数据变化:', newData)
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

.full-chart {
  width: 100%;
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