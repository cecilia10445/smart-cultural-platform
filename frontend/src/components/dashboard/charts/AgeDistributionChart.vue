<template>
  <div class="chart-container half-chart">
    <div class="chart-title">
      <span>👥</span>
      <span>用户年龄分布</span>
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
  name: 'AgeDistributionChart',
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
      if (!chartCanvas.value) return
      
      const ctx = chartCanvas.value.getContext('2d')
      
      // 销毁现有图表
      if (chartInstance.value) {
        chartInstance.value.destroy()
      }
      
      // 如果没有数据，创建一个空的图表
      if (!props.data || props.data.length === 0) {
        chartInstance.value = new Chart(ctx, {
          type: 'bar',
          data: {
            labels: ['暂无数据'],
            datasets: [{
              label: '用户数量',
              data: [0],
              backgroundColor: '#666',
              borderColor: '#888',
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
        return
      }
      
      const ageData = props.data
      const labels = ageData.map(item => {
        const ageMap = {
          '1': '18岁以下', '2': '18-24岁', '3': '25-29岁',
          '4': '30-34岁', '5': '35-39岁', '6': '40-49岁',
          '7': '50岁以上', '0': '未知'
        }
        return ageMap[item.age_range] || item.age_range
      })
      const counts = ageData.map(item => item.count)
      
      chartInstance.value = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [{
            label: '用户数量',
            data: counts,
            backgroundColor: '#ff6b6b',
            borderColor: '#ee5a24',
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

    // 监听数据变化 - 确保数据更新时重新渲染
    watch(() => props.data, (newData, oldData) => {
      console.log('AgeDistributionChart 数据变化:', newData)
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