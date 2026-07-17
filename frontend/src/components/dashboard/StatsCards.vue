<template>
  <div class="stats-cards">
    <div class="stat-card">
      <div class="value">{{ stats.totalUsers }}</div>
      <div class="label">总用户数</div>
    </div>
    <div class="stat-card">
      <div class="value">{{ stats.totalGenerations }}</div>
      <div class="label">总生成次数</div>
    </div>
    <div class="stat-card">
      <div class="value">{{ stats.activeUsers }}</div>
      <div class="label">7日活跃用户</div>
    </div>
    <div class="stat-card">
      <div class="value">{{ stats.avgRating }}</div>
      <div class="label">平均评分</div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'StatsCards',
  props: {
    stats: {
      type: Object,
      default: () => ({})
    }
  }
}
</script>

<style scoped>
.stats-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 25px;
  padding: 25px 30px;
  background: rgba(255, 255, 255, 0.02);
  flex-shrink: 0;
}

.stat-card {
  background: linear-gradient(135deg, #2d2d2d 0%, #1a1a1a 100%);
  border-radius: 16px;
  padding: 30px 25px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3);
  border: 1px solid #333;
  transition: all 0.3s ease;
  min-height: 140px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.stat-card:hover {
  transform: translateY(-8px);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.4);
}

.stat-card .value {
  font-size: 42px;
  font-weight: bold;
  color: #fff;
  margin-bottom: 12px;
  text-align: center;
}

.stat-card .label {
  font-size: 16px;
  color: #aaa;
  text-align: center;
  font-weight: 500;
}

/* 响应式调整 */
@media (max-width: 1200px) {
  .stats-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>