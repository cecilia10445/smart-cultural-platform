<template>
  <div class="header">
    <h1>{{ chartTitle }}</h1>
    <div class="date-selector">
      <span>日期范围：</span>
      <input type="date" v-model="dateRange.startDate">
      <span>至</span>
      <input type="date" v-model="dateRange.endDate">
      <button @click="$emit('apply-date-range')">应用</button>
      <button @click="$emit('reset-date-range')">重置</button>
      <button @click="$emit('select-last-7-days')">近7天</button>
      <button @click="$emit('select-last-30-days')">近30天</button>
      <span>{{ currentDate }}</span>
    </div>
  </div>
</template>

<script>
import { watch } from 'vue'

export default {
  name: 'Header',
  props: {
    chartTitle: String,
    dateRange: Object,
    currentDate: String
  },
  emits: ['apply-date-range', 'reset-date-range', 'select-last-7-days', 'select-last-30-days'],
  setup(props, { emit }) {
    // 监听日期变化，自动应用
    watch(() => props.dateRange, (newVal) => {
      if (newVal.startDate && newVal.endDate) {
        emit('apply-date-range')
      }
    }, { deep: true })

    return {}
  }
}
</script>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 30px;
  background: rgba(255, 255, 255, 0.05);
  border-bottom: 1px solid #333;
}

.header h1 {
  font-size: 24px;
  color: #fff;
  font-weight: 600;
}

.date-selector {
  color: #aaa;
  font-size: 14px;
}

.date-selector input {
  background: #2d2d2d;
  border: 1px solid #444;
  color: #e0e0e0;
  padding: 5px 10px;
  border-radius: 4px;
  margin: 0 5px;
}

.date-selector button {
  background: #667eea;
  border: none;
  color: white;
  padding: 5px 10px;
  border-radius: 4px;
  cursor: pointer;
  margin: 0 2px;
  font-size: 12px;
}

.date-selector button:hover {
  background: #5a6fd8;
}

.date-selector button:active {
  background: #4c5dc1;
}
</style>