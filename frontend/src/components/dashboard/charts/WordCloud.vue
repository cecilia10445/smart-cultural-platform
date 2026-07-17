<template>
  <div class="chart-container half-chart">
    <div class="chart-title">
      <span>🔍</span>
      <span>热门关键词词云</span>
    </div>
    <div class="chart-wrapper">
      <div class="word-cloud">
        <div class="loading" v-if="!data || data.length === 0">加载中...</div>
        <div v-else v-for="keyword in data" 
             :key="keyword.keyword"
             class="word-item"
             :style="{ fontSize: calculateFontSize(keyword.frequency) + 'px' }">
          {{ keyword.keyword }}
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, watch } from 'vue'

export default {
  name: 'WordCloud',
  props: {
    data: {
      type: Array,
      default: () => []
    }
  },
  setup(props) {
    const calculateFontSize = (frequency) => {
      // 添加更严格的空值检查
      if (!props.data || !Array.isArray(props.data) || props.data.length === 0) {
        return 16
      }
      
      try {
        const frequencies = props.data.map(k => k.frequency).filter(f => typeof f === 'number')
        if (frequencies.length === 0) return 16
        
        const maxFreq = Math.max(...frequencies)
        const minFreq = Math.min(...frequencies)
        
        if (maxFreq === minFreq) return 20
        return 14 + (frequency - minFreq) / (maxFreq - minFreq) * 20
      } catch (error) {
        console.error('计算字体大小失败:', error)
        return 16
      }
    }

    const renderChart = () => {
      console.log('WordCloud 渲染，数据:', props.data)
      // 词云组件不需要额外的渲染逻辑，数据变化会自动更新
    }

    watch(() => props.data, (newData, oldData) => {
      console.log('WordCloud 数据变化:', newData)
      renderChart()
    }, { deep: true })

    return {
      calculateFontSize,
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

.loading {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  font-size: 16px;
  color: #aaa;
}

.word-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: center;
  align-items: center;
  height: 100%;
  padding: 20px;
}

.word-item {
  padding: 10px 18px;
  border-radius: 25px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-weight: bold;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
  transition: all 0.3s ease;
}

.word-item:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5);
}
</style>