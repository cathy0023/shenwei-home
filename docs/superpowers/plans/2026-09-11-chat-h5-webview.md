# SHM-002 chat 页 H5 化 — 实现计划

> RFC: `docs/rfcs/approved/SHM-002-chat-h5-webview.md`
> 设计基线: `shenwei-home-mini/design/preview.html`
> 功能基准: `shenwei-home-mini/pages/chat/*`（原生页最终形态）
> 仓库: `github.com/cathy0023/shenwei-home`（worktree `feat/chat-h5-webview`）

## Goal

建成 `shenwei-home-h5`（React 18 + Vite + TS）聊天页 + 小程序壳（mine/webview），同域 `/h5/` 部署，满足 AC1-AC8。

## Architecture

```
小程序 pages/mine（静默登录）→ pages/webview（web-view ?token=）
  → https://xdf.nonoai.com.cn/h5/  (React SPA, base=/h5/)
      → sessionStorage token → fetch /api/* (Bearer)
      → list/poll/send/image/transfer 全量对齐原生页
nginx: root /opt/shenwei-home + /h5/ location（root 写法，无 alias 陷阱）
```

## Tech Stack

- H5: Vite 5 + React 18 + TypeScript + 原生 CSS（无组件库、无 router）
- 测试: Vitest + Testing Library（API 层/工具函数单测）
- 部署: nginx root 写法 + rsync 时间戳目录 + symlink 原子切换

## Tasks

### T0: 建仓

- [ ] 0.1 `shenwei-home-h5/` 目录 + `.gitignore`（dist/node_modules/coverage）
- [ ] 0.2 目录骨架（src/{api,components,pages,utils,styles} + tests + scripts）
- [ ] 0.3 commit: `chore(h5): T0 scaffold directory`

### T1: 脚手架 + API 层

- [ ] 1.1 写测试: `tests/token.test.ts` — query 解析（有/无/非法 token）、sessionStorage 优先级（query 优先→storage 兜底）、replaceState 清除
- [ ] 1.2 写测试: `tests/api.test.ts` — Bearer 注入、401 → 清 storage + 抛 AuthError、send/list/poll/image/transfer 形状
- [ ] 1.3 跑失败（Vitest RED）
- [ ] 1.4 实现: `vite.config.ts`(base=/h5/)、`src/utils/token.ts`、`src/api.ts`、`src/types.ts`
- [ ] 1.5 跑通过 + commit: `feat(h5): T1 scaffold + api layer`

### T2: UI 骨架 + 设计变量 + 键盘/安全区

- [ ] 2.1 写测试: `tests/components.test.tsx` — 消息流渲染（user/assistant/system 三态、金标、图片节点）、输入栏（禁用态）、hero 渲染
- [ ] 2.2 跑失败
- [ ] 2.3 实现: `src/styles/global.css`（preview.html 变量移植: 色板/圆角/渐变/纯 CSS 机器人）、`src/components/{MessageList,MessageItem,InputBar,Hero,EmojiPanel}.tsx`、visualViewport 监听 + scrollIntoView + safe-area、输入框 ≥16px
- [ ] 2.4 跑通过 + `pnpm build`（gzip < 200KB 检查）
- [ ] 2.5 commit: `feat(h5): T2 chat UI skeleton`

### T3: 核心交互

- [ ] 3.1 写测试: `tests/chat-logic.test.ts` — 乐观回显→send 对账（temp 替换）、轮询退避状态机（3s→+1s→10s 封顶）、visibilitychange 暂停/恢复即拉、游标从最新历史初始化防重放
- [ ] 3.2 跑失败
- [ ] 3.3 实现: `src/pages/Chat.tsx`（loadHistory ASC 反转+分页 cursor、sendText 乐观回显、poll 循环、表情盘 32 枚=原生 EMOJIS 数组逐枚相同）、历史分页上滑加载
- [ ] 3.4 跑通过 + commit: `feat(h5): T3 core interactions`

### T4: 图片链路

- [ ] 4.1 写测试: `tests/image.test.ts` — 压缩参数（长边 1600/q0.6）、>10MB 前置拒绝、HEIC 解码失败回退原图、blob URL 展示策略
- [ ] 4.2 跑失败
- [ ] 4.3 实现: `src/utils/image.ts`（createImageBitmap+canvas 压缩）、input file 单选接入、binderror→失败占位卡片（对齐原生）
- [ ] 4.4 跑通过 + commit: `feat(h5): T4 image pipeline`

### T5: 转人工 + 错误态收尾

- [ ] 5.1 写测试: `tests/error-states.test.tsx` — 401 错误态卡片（清 storage+返回引导文案）、空态、transfer 触发 system 提示
- [ ] 5.2 跑失败
- [ ] 5.3 实现: 错误态/空态组件、transfer 接入、人工金标+人形徽章头像终验
- [ ] 5.4 跑通过 + 全量单测绿
- [ ] 5.5 commit: `feat(h5): T5 transfer + error states`

### T6: 小程序壳

- [ ] 6.1 写测试: `shenwei-home-mini/tests/check_mini.py` 扩展 — mine/webview 页面四件套存在、webview 页 onShareAppMessage 禁分享断言、跳转链路（mine→webview token 传递）
- [ ] 6.2 跑失败
- [ ] 6.3 实现: `pages/mine/*`（头像区+菜单列表，联系客服主项）、`pages/webview/*`（onLoad 收 token 拼 src、缺 token toast+返回、**onShareAppMessage 禁用**）、`app.json` 注册、app.js silentLogin 缓存 Promise（mine 页 await 防竞态）
- [ ] 6.4 跑通过（check_mini.py + 后端 pytest 回归）
- [ ] 6.5 commit: `feat(mini): T6 mine page + webview shell`

### T7: 部署 + 验证

- [ ] 7.1 nginx: `/etc/nginx/conf.d/xdf.conf` 追加 `/h5/` location（root /opt/shenwei-home 写法）+ tokenless log_format + gzip；`nginx -t` 后 reload
- [ ] 7.2 构建产物部署: `pnpm build` → rsync dist/ 至 `/opt/shenwei-home/h5.new-<ts>/` → symlink 原子切换 `/opt/shenwei-home/h5`
- [ ] 7.3 API 冒烟: `shenwei-home-h5/scripts/smoke.py`（种子 token 直插 sessions 表→fetch /api/messages/list→断言 200+items 数组）
- [ ] 7.4 AC 核验: AC1 浏览器五项视觉清单 / AC2-AC5 功能 / AC6 curl / AC7 真机双端清单（键盘/安全区/上传/分享无 token）/ AC8 push GitHub
- [ ] 7.5 commit: `chore(h5): T7 deploy configs + smoke` + push

## Self-Review

- [x] AC 覆盖: AC1→T2+T7.4, AC2→T3+T4, AC3→T5, AC3a/3b→T3.1 单测, AC4→T5, AC5→T6+T7.4, AC6→T7.1/7.2, AC7→T7.4, AC8→T0+T7.5
- [x] 无 TBD/TODO 占位符
- [x] 文件路径精确: shenwei-home-h5/{src,tests,scripts} + shenwei-home-mini/pages/{mine,webview}

