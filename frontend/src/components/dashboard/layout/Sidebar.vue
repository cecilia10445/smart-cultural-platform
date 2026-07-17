<template>
  <div class="sidebar">
    <div class="logo-area">
      <div class="logo">
        <span>📊</span>
        <span>运营数据面板</span>
      </div>
    </div>
    
    <div class="nav-items">
      <div v-for="nav in navItems" 
           :key="nav.id"
           class="nav-item" 
           :class="{ active: activeChart === nav.id }"
           @click="$emit('switch-chart', nav.id)">
        <span>{{ nav.icon }}</span>
        <span>{{ nav.text }}</span>
      </div>
    </div>
    
    <div class="user-area">
      <div class="user-info">
        <div class="user-avatar">{{ userInitial }}</div>
        <div class="user-details">
          <h4>{{ userName }}</h4>
          <p>{{ userEmail }}</p>
        </div>
      </div>
      <button class="logout-btn" @click="$emit('logout')">
        <span>🚪</span>
        <span>退出登录</span>
      </button>
    </div>
  </div>
</template>

<script>
export default {
  name: 'Sidebar',
  props: {
    activeChart: String,
    navItems: Array,
    userName: String,
    userEmail: String,
    userInitial: String
  },
  emits: ['switch-chart', 'logout']
}
</script>

<style scoped>
.sidebar {
  width: 280px;
  background: linear-gradient(180deg, #2d2d2d 0%, #1a1a1a 100%);
  color: #e0e0e0;
  display: flex;
  flex-direction: column;
  box-shadow: 2px 0 10px rgba(0, 0, 0, 0.3);
  z-index: 100;
  border-right: 1px solid #333;
}

.logo-area {
  padding: 25px 20px;
  text-align: center;
  border-bottom: 1px solid #333;
  background: rgba(255, 255, 255, 0.05);
}

.logo {
  font-size: 20px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #fff;
}

.nav-items {
  flex: 1;
  padding: 20px 0;
  overflow-y: auto;
}

.nav-item {
  padding: 16px 20px;
  margin: 4px 15px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid transparent;
}

.nav-item:hover {
  background-color: rgba(255, 255, 255, 0.1);
  border-color: #444;
}

.nav-item.active {
  background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
  box-shadow: 0 4px 12px rgba(255, 107, 107, 0.3);
  border-color: #ff6b6b;
}

.user-area {
  padding: 20px;
  border-top: 1px solid #333;
  background: rgba(255, 255, 255, 0.05);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 15px;
}

.user-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 16px;
  color: white;
}

.user-details h4 {
  font-size: 14px;
  margin-bottom: 4px;
  color: #fff;
}

.user-details p {
  font-size: 12px;
  color: #aaa;
}

.logout-btn {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid #444;
  color: #e0e0e0;
  padding: 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
}

.logout-btn:hover {
  background: rgba(255, 255, 255, 0.2);
  border-color: #666;
}
</style>