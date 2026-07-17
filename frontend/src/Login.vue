<template>
  <div class="login-page">
    <!-- 登录容器 -->
    <div class="login-container">
      <div class="logo">
        <h1>🎨 智能文创平台</h1>
        <p>请选择身份登录</p>
      </div>
      
      <!-- 角色选择 -->
      <div class="role-selector">
        <div class="role-option" 
             :class="{ active: loginType === 'user' }"
             @click="loginType = 'user'">
          👤 用户登录
        </div>
        <div class="role-option" 
             :class="{ active: loginType === 'admin' }"
             @click="loginType = 'admin'">
          🛠️ 运营登录
        </div>
      </div>
      
      <!-- 登录表单 -->
      <form @submit.prevent="handleLogin">
        <div class="form-group">
          <label for="username">用户名</label>
          <input type="text" id="username" v-model="username" placeholder="请输入用户名" required>
        </div>
        <div class="form-group">
          <label for="password">密码</label>
          <input type="password" id="password" v-model="password" placeholder="请输入密码" required>
        </div>
        
        <!-- 错误提示 -->
        <div v-if="error" class="error-message">
          ❌ {{ error }}
        </div>
        
        <!-- 登录按钮 -->
        <button type="submit" class="login-btn" :disabled="loading">
          <span v-if="loading">🔄 登录中...</span>
          <span v-else>🚀 立即登录</span>
        </button>
        
        <!-- 注册入口（区分用户和运营） -->
        <div class="register-options">
          <div class="register-type">
            普通用户注册？
            <button type="button" class="register-btn" @click="openRegister('user')">
              点击注册
            </button>
          </div>
          <div class="register-type">
            运营账号注册？
            <button type="button" class="register-btn" @click="openRegister('admin')">
              点击注册（需密钥）
            </button>
          </div>
        </div>
      </form>
    </div>
    
    <!-- 注册弹窗（默认隐藏） -->
    <div v-if="showRegister" class="modal-overlay">
      <div class="modal-container">
        <div class="modal-header">
          <h2>
            <span v-if="registerRole === 'user'">📝 用户注册</span>
            <span v-if="registerRole === 'admin'">🔑 运营注册</span>
          </h2>
          <button class="close-btn" @click="showRegister = false">×</button>
        </div>
        
        <form @submit.prevent="handleRegister">
          <!-- 运营注册需要密钥验证 -->
          <div v-if="registerRole === 'admin'" class="form-group">
            <label for="regKey">运营注册密钥</label>
            <input type="password" id="regKey" v-model="registerForm.key" placeholder="请输入运营密钥" required>
            <p class="key-hint">提示：密钥由系统管理员提供</p>
          </div>
          
          <div class="form-group">
            <label for="regUsername">用户名</label>
            <input type="text" id="regUsername" v-model="registerForm.username" placeholder="3-12位字符" required>
          </div>
          <div class="form-group">
            <label for="regPassword">密码</label>
            <input type="password" id="regPassword" v-model="registerForm.password" placeholder="6-16位字符" required>
          </div>
          <div class="form-group">
            <label for="regName">姓名</label>
            <input type="text" id="regName" v-model="registerForm.name" placeholder="请输入姓名" required>
          </div>
          
          <!-- 注册错误提示 -->
          <div v-if="registerError" class="error-message">
            ❌ {{ registerError }}
          </div>
          
          <!-- 注册按钮 -->
          <button type="submit" class="login-btn" :disabled="registerLoading">
            <span v-if="registerLoading">🔄 注册中...</span>
            <span v-else>
              <span v-if="registerRole === 'user'">✅ 完成注册</span>
              <span v-if="registerRole === 'admin'">✅ 验证并注册</span>
            </span>
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  name: 'LoginPage',
  data() {
    return {
      // 登录相关
      loginType: 'user', // user 或 admin
      username: '',
      password: '',
      loading: false,
      error: '',
      
      // 注册相关
      showRegister: false,       // 控制注册弹窗显示
      registerRole: 'user',      // 记录当前注册角色（user/admin）
      registerForm: {
        username: '',
        password: '',
        name: '',
        key: ''                   // 运营注册密钥
      },
      registerLoading: false,
      registerError: '',
      // 运营注册密钥（与后端脚本保持一致）
      ADMIN_CREATION_KEY: "9876543210"
    }
  },
  methods: {
    // 登录处理
    async handleLogin() {
      if (!this.username.trim() || !this.password.trim()) {
        this.error = '用户名和密码不能为空';
        return;
      }

      this.loading = true;
      this.error = '';
      try {
        const response = await axios.post('/api/login', {
          username: this.username.trim(),
          password: this.password.trim(),
          role: this.loginType
        });

        if (response.data.status === 'success') {
          // 保存用户信息和Token
          localStorage.setItem('userInfo', JSON.stringify(response.data.user));
          localStorage.setItem('token', response.data.token);
          
          // 如果是运营登录，额外保存到admin相关字段
          if (this.loginType === 'admin') {
            localStorage.setItem('adminToken', response.data.token);
            localStorage.setItem('adminUser', JSON.stringify(response.data.user));
          }
          
          // 跳转对应页面
          window.location.href = this.loginType === 'user' ? '/index.html' : '/dashboard.html';
        } else {
          this.error = response.data.message || '登录失败，请重试';
        }
      } catch (error) {
        console.error('登录错误:', error);
        this.error = error.response?.data?.message || '网络异常，请稍后重试';
      } finally {
        this.loading = false;
      }
    },

    // 打开注册弹窗（区分角色）
    openRegister(role) {
      this.registerRole = role;
      this.showRegister = true;
      // 重置表单和错误信息
      this.registerForm = { username: '', password: '', name: '', key: '' };
      this.registerError = '';
    },

    // 注册处理
    async handleRegister() {
      // 表单基础校验
      if (this.registerForm.username.trim().length < 3 || this.registerForm.username.trim().length > 12) {
        this.registerError = '用户名需3-12位字符';
        return;
      }
      if (this.registerForm.password.trim().length < 6 || this.registerForm.password.trim().length > 16) {
        this.registerError = '密码需6-16位字符';
        return;
      }
      if (!this.registerForm.name.trim()) {
        this.registerError = '请输入姓名';
        return;
      }

      // 运营注册额外校验密钥
      if (this.registerRole === 'admin') {
        if (this.registerForm.key !== this.ADMIN_CREATION_KEY) {
          this.registerError = '运营密钥错误，请联系管理员';
          return;
        }
      }

      this.registerLoading = true;
      this.registerError = '';
      try {
        const response = await axios.post('/api/register', {
          username: this.registerForm.username.trim(),
          password: this.registerForm.password.trim(),
          name: this.registerForm.name.trim(),
          role: this.registerRole  // 传递注册角色（user/admin）
        });

        if (response.data.status === 'success') {
          alert(`${this.registerRole === 'user' ? '用户' : '运营'}注册成功！即将跳转到登录页`);
          this.showRegister = false;
          // 自动填充用户名到登录框
          this.username = this.registerForm.username;
          // 切换到对应登录角色
          this.loginType = this.registerRole;
        } else {
          this.registerError = response.data.message || '注册失败，请重试';
        }
      } catch (error) {
        console.error('注册错误:', error);
        this.registerError = error.response?.data?.message || '网络异常，请稍后重试';
      } finally {
        this.registerLoading = false;
      }
    }
  },
  mounted() {
    console.log('登录页面已加载');
  }
}
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

body { 
  font-family: 'Microsoft YaHei', sans-serif; 
  margin: 0;
  padding: 0;
  min-height: 100vh;
}

.login-page {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  /* 使用正确的图片路径 */
  background: 
    linear-gradient(rgba(0, 0, 0, 0.5), rgba(0, 0, 0, 0.5)),
    url('/images/back.png');
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  background-attachment: fixed;
}

/* 登录容器 - 白灰色风格 */
.login-container {
  background: rgba(255, 255, 255, 0.95);
  padding: 45px 40px;
  border-radius: 18px;
  box-shadow: 0 15px 35px rgba(0, 0, 0, 0.3);
  width: 100%;
  max-width: 420px;
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.3);
}

/* Logo区域 */
.logo {
  text-align: center;
  margin-bottom: 35px;
}
.logo h1 {
  font-size: 2.4em;
  color: #2c3e50;
  margin-bottom: 8px;
  letter-spacing: -0.5px;
}
.logo p {
  color: #7f8c8d;
  font-size: 1.05em;
}

/* 角色选择器 */
.role-selector {
  display: flex;
  margin-bottom: 30px;
  border-radius: 10px;
  overflow: hidden;
  border: 2px solid #ecf0f1;
  background: #f8f9fa;
}
.role-option {
  flex: 1;
  padding: 14px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
  background: #f8f9fa;
  font-size: 1em;
  font-weight: 500;
  color: #5a6c7d;
}
.role-option.active {
  background: linear-gradient(135deg, #34495e 0%, #2c3e50 100%);
  color: white;
  border-color: transparent;
}
.role-option:first-child {
  border-right: 1px solid #ecf0f1;
}

/* 表单样式 */
.form-group {
  margin-bottom: 25px;
}
.form-group label {
  display: block;
  margin-bottom: 10px;
  font-weight: 600;
  color: #34495e;
  font-size: 1.05em;
}
.form-group input {
  width: 100%;
  padding: 14px 16px;
  border: 2px solid #e0e6ed;
  border-radius: 10px;
  font-size: 1em;
  transition: all 0.3s ease;
  background: #ffffff;
  color: #2c3e50;
}
.form-group input:focus {
  outline: none;
  border-color: #34495e;
  box-shadow: 0 0 0 3px rgba(52, 73, 94, 0.1);
  background: #ffffff;
}
.form-group input::placeholder {
  color: #a0aec0;
}

/* 按钮样式 */
.login-btn {
  width: 100%;
  padding: 15px;
  background: linear-gradient(135deg, #34495e 0%, #2c3e50 100%);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 1.1em;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 4px 15px rgba(52, 73, 94, 0.2);
}
.login-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(52, 73, 94, 0.3);
}
.login-btn:active {
  transform: translateY(0);
}
.login-btn:disabled {
  background: #bdc3c7;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

/* 错误提示 */
.error-message {
  background: #ffeaea;
  color: #c0392b;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 25px;
  border-left: 4px solid #c0392b;
  font-size: 0.95em;
}

/* 注册入口 */
.register-options {
  text-align: center;
  margin-top: 22px;
  font-size: 0.95em;
  color: #7f8c8d;
}
.register-type {
  margin: 8px 0;
}
.register-btn {
  background: transparent;
  border: none;
  color: #34495e;
  font-weight: 600;
  cursor: pointer;
  padding: 2px 4px;
  transition: all 0.2s ease;
  text-decoration: none;
}
.register-btn:hover {
  color: #2c3e50;
  text-decoration: underline;
}

/* 注册弹窗 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}
.modal-container {
  background: rgba(255, 255, 255, 0.98);
  padding: 40px;
  border-radius: 18px;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(15px);
  border: 1px solid rgba(255, 255, 255, 0.3);
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
}
.modal-header h2 {
  color: #2c3e50;
  font-size: 1.8em;
  font-weight: 600;
}
.close-btn {
  background: transparent;
  border: none;
  font-size: 1.8em;
  cursor: pointer;
  color: #7f8c8d;
  transition: color 0.2s ease;
}
.close-btn:hover {
  color: #c0392b;
}

/* 密钥提示 */
.key-hint {
  font-size: 0.85em;
  color: #7f8c8d;
  margin-top: -15px;
  margin-bottom: 20px;
  font-style: italic;
}

/* 响应式适配 */
@media (max-width: 480px) {
  .login-container, .modal-container {
    padding: 35px 25px;
  }
  .logo h1 {
    font-size: 2em;
  }
  .role-option {
    padding: 12px;
    font-size: 0.95em;
  }
}
</style>