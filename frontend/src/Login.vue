<template>
  <main class="login-page">
    <section class="login-intro" aria-labelledby="platform-title">
      <div class="seal-mark" aria-hidden="true"><span></span><span></span><span></span></div>
      <p class="eyebrow">SMART CULTURAL PLATFORM / 01</p>
      <h1 id="platform-title">智能文创平台</h1>
      <p class="intro-copy">以清晰的创作需求，生成可追溯的图文内容。</p>
      <dl class="intro-notes" aria-label="平台工作方式">
        <div><dt>输入</dt><dd>主题与风格</dd></div>
        <div><dt>生成</dt><dd>图文创作请求</dd></div>
        <div><dt>记录</dt><dd>真实结果留存</dd></div>
      </dl>
    </section>

    <section class="login-panel" aria-labelledby="login-title">
      <p class="eyebrow">ACCESS PORTAL</p>
      <h2 id="login-title">进入工作台</h2>
      <p class="panel-copy">请选择与账户匹配的身份后登录。</p>

      <div class="role-selector" role="group" aria-label="登录身份">
        <button
          type="button"
          class="role-option"
          :class="{ active: loginType === 'user' }"
          :aria-pressed="loginType === 'user'"
          @click="selectRole('user')"
        >
          普通用户
          <small>创作工作台</small>
        </button>
        <button
          type="button"
          class="role-option"
          :class="{ active: loginType === 'admin' }"
          :aria-pressed="loginType === 'admin'"
          @click="selectRole('admin')"
        >
          运营用户
          <small>运营面板</small>
        </button>
      </div>

      <form @submit.prevent="handleLogin" novalidate>
        <div class="field-group">
          <label for="username">用户名</label>
          <input
            id="username"
            v-model="username"
            type="text"
            autocomplete="username"
            placeholder="请输入用户名"
            :aria-describedby="error ? 'login-error' : undefined"
            :disabled="loading"
          >
        </div>
        <div class="field-group">
          <label for="password">密码</label>
          <input
            id="password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            :aria-describedby="error ? 'login-error' : undefined"
            :disabled="loading"
          >
        </div>

        <p v-if="error" id="login-error" class="error-message" role="alert">{{ error }}</p>

        <button type="submit" class="submit-button" :disabled="loading">
          <span v-if="loading" class="loading-label"><span class="inline-spinner" aria-hidden="true"></span>正在验证身份</span>
          <span v-else>进入{{ loginType === 'admin' ? '运营面板' : '创作工作台' }}</span>
        </button>
      </form>

      <p class="access-note">账户由平台管理员统一维护。登录信息仅用于本次身份验证。</p>
    </section>
  </main>
</template>

<script>
import axios from 'axios'

export default {
  name: 'LoginPage',
  data() {
    return {
      loginType: 'user',
      username: '',
      password: '',
      loading: false,
      error: ''
    }
  },
  methods: {
    selectRole(role) {
      this.loginType = role
      this.error = ''
    },
    loginErrorMessage(error) {
      const status = error.response?.status
      if (status === 401) return '用户名、密码或所选身份不匹配，请重新确认。'
      if (status === 403) return '当前账户没有访问该入口的权限。'
      if (status === 503) return '认证服务暂时不可用，请稍后重试。'
      if (status) return '登录请求未能完成，请稍后重试。'
      if (error.request) return '无法连接认证服务，请检查网络后重试。'
      return '登录响应格式异常，请稍后重试。'
    },
    async handleLogin() {
      if (this.loading) return
      if (!this.username.trim() || !this.password.trim()) {
        this.error = '请填写用户名和密码后再继续。'
        return
      }

      this.loading = true
      this.error = ''
      try {
        const response = await axios.post('/api/login', {
          username: this.username.trim(),
          password: this.password,
          role: this.loginType
        })
        const body = response.data
        if (body?.status !== 'success' || typeof body.token !== 'string' || !body.token || !body.user || typeof body.user !== 'object') {
          this.error = '登录响应格式异常，请稍后重试。'
          return
        }

        localStorage.setItem('userInfo', JSON.stringify(body.user))
        localStorage.setItem('token', body.token)
        if (this.loginType === 'admin') {
          localStorage.setItem('adminToken', body.token)
          localStorage.setItem('adminUser', JSON.stringify(body.user))
        } else {
          localStorage.removeItem('adminToken')
          localStorage.removeItem('adminUser')
        }
        window.location.href = this.loginType === 'admin' ? '/dashboard.html' : '/index.html'
      } catch (error) {
        this.error = this.loginErrorMessage(error)
      } finally {
        this.loading = false
      }
    }
  }
}
</script>

<style>
:root { color: #17221f; background: #f3f0e8; font-family: "Noto Serif CJK SC", "Songti SC", "STSong", serif; }
* { box-sizing: border-box; }
body { margin: 0; min-width: 320px; background: #f3f0e8; }
button, input { font: inherit; }
.login-page { min-height: 100vh; display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(360px, .9fr); background: #f3f0e8; }
.login-intro { position: relative; overflow: hidden; padding: clamp(3rem, 9vw, 8rem) clamp(2rem, 10vw, 10rem); display: flex; flex-direction: column; justify-content: center; border-right: 1px solid #c9c3b6; background-color: #e9e5d9; background-image: repeating-linear-gradient(90deg, rgba(40, 57, 47, .045) 0, rgba(40, 57, 47, .045) 1px, transparent 1px, transparent 64px); }
.login-intro::after { content: "文创"; position: absolute; right: -1.2rem; bottom: -3rem; color: rgba(36, 82, 68, .09); font-size: clamp(11rem, 25vw, 22rem); line-height: 1; font-weight: 700; pointer-events: none; }
.seal-mark { width: 78px; height: 78px; margin-bottom: 2.5rem; border: 1px solid #245244; border-radius: 50%; display: grid; place-content: center; gap: 5px; transform: rotate(-8deg); }
.seal-mark span { display: block; width: 31px; height: 5px; background: #245244; }
.seal-mark span:nth-child(2) { width: 44px; background: #a44536; }
.seal-mark span:nth-child(3) { width: 22px; margin-left: 11px; }
.eyebrow { margin: 0 0 1rem; color: #5d675e; font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; font-size: .72rem; font-weight: 700; letter-spacing: .16em; }
.login-intro h1, .login-panel h2 { margin: 0; font-weight: 700; letter-spacing: .04em; }
.login-intro h1 { max-width: 7em; font-size: clamp(3rem, 6.2vw, 6.2rem); line-height: 1.12; }
.intro-copy { max-width: 25rem; margin: 1.75rem 0 2.5rem; color: #3f4a43; font-size: 1.1rem; line-height: 1.9; }
.intro-notes { position: relative; z-index: 1; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); max-width: 34rem; margin: 0; border-top: 1px solid #a9afa5; }
.intro-notes div { padding: 1rem .75rem 0 0; }
.intro-notes dt { color: #245244; font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; font-size: .72rem; font-weight: 700; letter-spacing: .12em; }
.intro-notes dd { margin: .45rem 0 0; color: #3d453f; font-size: .9rem; }
.login-panel { align-self: center; width: min(100%, 31rem); margin: 0 auto; padding: clamp(2rem, 6vw, 5rem) clamp(1.5rem, 5vw, 4rem); }
.login-panel h2 { font-size: clamp(2rem, 3.4vw, 3.1rem); line-height: 1.2; }
.panel-copy { margin: .8rem 0 2.25rem; color: #5c655e; line-height: 1.7; }
.role-selector { display: grid; grid-template-columns: 1fr 1fr; gap: .65rem; margin-bottom: 2rem; }
.role-option { min-height: 76px; padding: .9rem; text-align: left; color: #39433c; background: transparent; border: 1px solid #b9b9aa; border-radius: 0; cursor: pointer; transition: border-color .18s ease, background-color .18s ease, color .18s ease; }
.role-option small { display: block; margin-top: .35rem; color: inherit; opacity: .72; font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; font-size: .75rem; }
.role-option:hover, .role-option.active { color: #fffdf5; border-color: #245244; background: #245244; }
.field-group { margin-bottom: 1.2rem; }
.field-group label { display: block; margin-bottom: .55rem; color: #303a33; font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; font-size: .87rem; font-weight: 700; }
.field-group input { width: 100%; min-height: 52px; padding: .75rem .85rem; color: #17221f; background: #fbfaf5; border: 1px solid #aeb1a5; border-radius: 0; outline: none; transition: border-color .18s ease, box-shadow .18s ease; }
.field-group input::placeholder { color: #758076; }
.field-group input:focus-visible, .role-option:focus-visible, .submit-button:focus-visible { outline: 3px solid #a44536; outline-offset: 3px; }
.field-group input:focus { border-color: #245244; box-shadow: inset 0 -2px 0 #245244; }
.error-message { margin: 1rem 0; padding: .8rem .9rem; color: #7d241d; background: #f7e7df; border-left: 4px solid #a44536; font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; font-size: .9rem; line-height: 1.55; }
.submit-button { width: 100%; min-height: 54px; margin-top: .45rem; color: #fffdf5; background: #17221f; border: 1px solid #17221f; border-radius: 0; cursor: pointer; font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; font-weight: 700; transition: background-color .18s ease, transform .18s ease; }
.submit-button:hover:not(:disabled) { background: #245244; }
.submit-button:active:not(:disabled) { transform: translateY(1px); }
.submit-button:disabled { opacity: .68; cursor: wait; }
.loading-label { display: inline-flex; align-items: center; gap: .55rem; }
.inline-spinner { width: 1rem; height: 1rem; border: 2px solid rgba(255,255,255,.4); border-top-color: #fff; border-radius: 50%; animation: spin .8s linear infinite; }
.access-note { margin: 1.35rem 0 0; color: #697169; font-size: .82rem; line-height: 1.65; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 760px) { .login-page { grid-template-columns: 1fr; } .login-intro { min-height: 34vh; padding: 2.25rem 1.5rem 2.5rem; border-right: 0; border-bottom: 1px solid #c9c3b6; } .login-intro::after { font-size: 10rem; bottom: -1.7rem; } .seal-mark { width: 55px; height: 55px; margin-bottom: 1.25rem; } .seal-mark span { width: 22px; height: 4px; } .seal-mark span:nth-child(2) { width: 31px; } .seal-mark span:nth-child(3) { width: 16px; margin-left: 8px; } .login-intro h1 { font-size: clamp(2.45rem, 11vw, 4rem); } .intro-copy { margin: .75rem 0 1.25rem; font-size: 1rem; } .intro-notes { max-width: 29rem; } .intro-notes div { padding-top: .7rem; } .login-panel { padding: 2.5rem 1.5rem 3rem; } }
@media (max-width: 390px) { .role-selector { grid-template-columns: 1fr; } .intro-notes { grid-template-columns: 1fr; gap: .35rem; } .intro-notes div { padding-top: .45rem; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; animation-duration: .01ms !important; animation-iteration-count: 1 !important; } }
</style>
