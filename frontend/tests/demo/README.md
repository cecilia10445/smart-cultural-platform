# Ubuntu 真实业务录像

录像通过当前网页的实验性文本 Skill 入口发出一次真实业务请求；运行前必须启动 Flask 和 Vite，并以环境变量提供一个运营账户：

```bash
DEMO_EMAIL='运营账户名' DEMO_PASSWORD='账户密码' \
  npx playwright test -c playwright.demo.config.js
```

录制只生成一条文本业务记录。视频、截图、trace 和 HTML 报告位于 Playwright 的 `test-results/` 与 `demo-test-report/`；密码不会写入源码、报告或录像。
