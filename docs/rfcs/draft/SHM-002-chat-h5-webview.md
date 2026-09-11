---
id: SHM-002
title: chat 页 H5 化（React + web-view 嵌入）
status: Draft
created: 2026-09-11
author: shenwei
inbox: docs/rfcs/inbox/2026-09-11-chat-h5-webview.md
---

# SHM-002 chat 页 H5 化（React + web-view 嵌入）

## 1. Goals

- G1: 用户在小程序「我的」页点「联系客服」，经 web-view 打开 React H5 聊天页，获得与原生页完全对齐的客服体验（文字/表情/图片/历史/转人工/人工金标）。
- G2: H5 与后端同域部署（`https://xdf.nonoai.com.cn/h5/`），同域调 `/api/*` 零 CORS。
- G3: 身份直通：小程序壳静默登录持 token，web-view src 传 token，H5 免登录直接看到自己的会话。
- G4: 三端（api/mini/h5）同仓（github.com/cathy0023/shenwei-home）、同流程管理。
- G5: H5 视觉与 `shenwei-home-mini/design/preview.html` 设计基线一致。

## 2. Background

- 客户侧小程序客服页面形态为 webview 套 H5；我方当前为原生 chat 页（SHM-001 交付，生产验证），架构不一致导致双端迭代成本。
- 现有资产：FastAPI 后端（`/api/*`，签名媒体 URL、图片压缩上传、轮询收 AI/人工回复）；原生 chat 页全套交互逻辑可作为 H5 实现的功能基准；preview.html 设计基线。
- 环境：开发/测试阶段不受业务域名/备案约束（企业主体已确认，web-view 开发链路可用）；发布前需完成业务域名配置+校验文件+ICP 确认（归档为发布阶段清单）。
- 行业实践调研结论（2026-09）：身份传递业界首选「一次性 ticket 换 token」；本期内联 token 为其简化形态（方案 B），发布前可平滑升级；web-view 内 H5 关键坑位（键盘 viewport、单文件上传、nginx alias 陷阱、text-size-adjust）已在设计中针对性处理。

## 3. Design

### 3.1 总体架构

```
微信小程序
├── pages/mine（我的，新增）      ── 静默登录持 token
│     └── 「联系客服」菜单项
└── pages/webview（新增，web-view 壳）
      └── src = https://xdf.nonoai.com.cn/h5/?token=<token>
                    │
 nginx(443) ────────┴──────────────────────────
 ├── /h5/  → 静态目录（React H5 构建产物）
 └── /api/ → uvicorn 8200（现有后端，零改动）

H5 (React 18 + Vite + TS)
├── 读 URL token → 存 sessionStorage → history.replaceState 清除 query
├── 同域 /api/* 直调（复用原生页全部 API 契约）
└── 轮询收回复（3s/退避至 10s，对齐原生页策略）
```

### 3.2 H5 技术栈与工程

| 项 | 选型 | 理由 |
|---|---|---|
| 构建 | Vite 5 + React 18 + TypeScript | 团队既有栈；`base:'/h5/'` 子路径 |
| 路由 | 单页单视图，无 router 依赖 | 只有一个聊天视图 |
| 样式 | 原生 CSS（设计变量移植 preview.html） | 与原生页视觉 1:1；零组件库减小首屏 |
| 状态 | React hooks 局部状态 | 单视图无全局状态需求 |
| HTTP | fetch + Bearer header | 同域无 CORS |

### 3.3 身份桥接（本期：内联 token；升级路径：ticket 换 token）

- 小程序「我的」页 onLoad 静默登录（复用现有 app.js silentLogin 链路）→ token 存 globalData；
- 点「联系客服」→ `pages/webview/webview?token=<token>` → web-view src=`https://xdf.nonoai.com.cn/h5/?token=`；
- H5 首帧：解析 query token → 存 sessionStorage → `history.replaceState` 清除 URL 中的 token → 所有 API 带 Bearer；
- token 失效（401）：H5 显示错误态卡片「登录已过期，请返回小程序重新进入」+ 返回按钮（`wx.miniProgram.navigateBack`，JSSDK 可用时）；
- 发布前升级：后端签发 60s 一次性 ticket 代替长期 token 上 URL（Additive：新增 `/api/auth/exchange` 端点，H5 改首帧换 token）。

### 3.4 H5 聊天页功能规格（对齐原生页最终形态）

| 能力 | 实现要点 |
|---|---|
| 消息流 | list 倒序反转 ASC 展示；`kind=boss_reply` 右上角「人工」金标 + 琥珀人形徽章头像（CSS mask SVG）；图片消息裸气泡无边框 |
| 发文字 | 乐观回显 temp 气泡 → send API → 状态同步；≤2000 字 |
| 发图片 | `<input type="file" accept="image/*">`（**单文件**，Android multiple 有兼容坑）→ canvas 压缩（quality 0.6，长边 1600px）→ FormData 上传 → 本地 blob URL 展示（会话内），历史从签名 URL 加载；失败占位卡片 |
| 收回复 | 轮询 poll?since= 游标，3s 起、空闲退避 10s；visibilitychange 暂停/恢复 |
| 转人工 | chip → transfer API → system 提示渲染 |
| 表情 | 常用 emoji 盘（对齐原生页 32 枚） |
| 键盘 | `visualViewport` 监听 + 消息列表 scrollIntoView；输入框字号 ≥16px 防 iOS 缩放 |
| viewport | `viewport-fit=cover` + `env(safe-area-inset-bottom)`；`-webkit-text-size-adjust:100%` |

### 3.5 小程序壳

- `pages/mine/`（新增）：头像区（微信头像昵称占位）+ 菜单列表（联系客服为主项，设置等占位禁用态）——对齐客户侧个人中心的信息架构裁剪版；
- `pages/webview/`（新增）：全屏 web-view 组件，onLoad 接 token 拼 src；token 缺失时 toast + 返回；
- `app.json` pages 注册 + tabBar 不引入（保持单入口直达）；
- 原生 chat 页保留不删（web-view 异常时回退入口 + 开发参照）。

### 3.6 nginx（`/etc/nginx/conf.d/xdf.conf` 追加）

```nginx
location /h5/ {
    alias /opt/shenwei-home-h5/;
    try_files $uri $uri/ /h5/index.html;   # SPA fallback 用完整子路径（alias 陷阱）
}
# 静态资源 hash 长缓存由文件名保证；index.html 不缓存
location = /h5/index.html { add_header Cache-Control "no-cache"; }
```

### 3.7 Alternatives Considered

| 维度 | 已选 | 备选 | 驳回理由 |
|---|---|---|---|
| UI 组件库 | 原生 CSS 移植 | Ant Design Mobile/TDesign | 主题定制成本>自写；包体积+200KB 拖慢 web-view 首屏 |
| 身份传递 | URL 内联 token | ticket 换 token / cookie / postMessage | ticket 为发布前升级项（后端加端点即可）；cookie 在 web-view 割裂不可靠；postMessage 仅特定时机投递 |
| 部署 | nginx 子路径 /h5/ | FastAPI StaticFiles / 独立子域 | StaticFiles 前后端发版耦合；子域需新证书+业务域名多配一条 |
| 图片选择 | H5 input file 单文件 | JSSDK wx.chooseImage | JSSDK 需后端签名 wx.config 且仅限图片；input file 基本可用 |

## 4. Implementation

| Task | 标题 | 产出 | 依赖 |
|---|---|---|---|
| T1 | H5 脚手架 + API 层 | `shenwei-home-h5/`（Vite+React+TS，base=/h5/）、`src/api.ts`（token 注入/401 错误态）、token query 解析工具 | - |
| T2 | 聊天页 UI 骨架 + 设计变量 | 全局样式（preview.html 变量移植）、消息流组件（气泡/头像/金标）、输入栏组件、hero 区 | T1 |
| T3 | 核心交互 | 发文字（乐观回显）、历史分页、轮询收回复（退避+visibilitychange）、表情盘 | T2 |
| T4 | 图片链路 | input file 单选+canvas 压缩+上传、blob/签名 URL 展示策略、失败占位 | T3 |
| T5 | 转人工 + 人工金标 + 收尾 | transfer、kind 区分渲染、错误态/空态、visualViewport 键盘适配、safe-area | T4 |
| T6 | 小程序壳 | pages/mine（我的）、pages/webview、app.json 注册、跳转链路 | T1（并行） |
| T7 | 部署 + E2E | nginx /h5/ location、构建产物部署脚本、浏览器 E2E 冒烟（登录→聊天→图片→转人工）、真机 web-view 验证 | T5, T6 |

> 工时：T1-T5 各约 0.5d，T6 0.5d，T7 0.5d。H5 侧用 Vitest + Testing Library 对 API 层/工具函数做单测；组件交互以浏览器 E2E 冒烟为主。

## 5. Acceptance Criteria

- [ ] AC1: 浏览器打开 `https://xdf.nonoai.com.cn/h5/?token=<有效token>`：历史消息（含图片、人工金标）完整展示，视觉对齐设计基线。
- [ ] AC2: H5 内发文字 → 收到 AI 回复（轮询路径）；发图片（自动压缩）→ 聊天内即时显示，历史重进后仍显示（签名 URL）。
- [ ] AC3: 转人工 → system 提示出现；boss_reply 回流 → 气泡带「人工」金标 + 人形徽章头像。
- [ ] AC4: token 缺失/失效 → H5 错误态卡片，不白屏不报未处理异常。
- [ ] AC5: 小程序「我的」页 →「联系客服」→ web-view 打开 H5，身份直通可见自己的会话；原生 chat 页保留可回退。
- [ ] AC6: `xdf.nonoai.com.cn/h5/` 生产可访问，同域调 API 无 CORS；刷新 `/h5/` 下任意路径 SPA fallback 正常。
- [ ] AC7: iOS/Android 真机（开发版）各过一遍核心链路：键盘弹收后消息列表可见、底部安全区无遮挡、图片选择上传成功。
- [ ] AC8: 仓库推送 GitHub，`shenwei-home-h5` 含 README（本地开发/构建/部署说明）。

## 6. Risks & Mitigations

| 风险 | 缓解 |
|---|---|
| token 上 URL 的泄露面（日志/分享/截屏） | 本期：7 天有效期+HTTPS+replaceState 清除；发布前升级 ticket 换 token（后端加端点，H5 改首帧） |
| web-view 未配业务域名时真机弹「继续访问」 | 开发/体验版有豁免入口；发布清单收口 |
| iOS 键盘不改 viewport、收起不回弹 | visualViewport 监听 + scrollIntoView + 输入框 ≥16px |
| Android input file multiple 无回调 | 单文件模式；逐张上传 |
| nginx alias + try_files 拼接错误 | fallback 写完整 /h5/index.html；AC6 显式验证 |
| 图片压缩在 H5 canvas 的内存峰值（大图） | 压缩前先按长边 1600px 缩放；超 10MB 前置拒绝 |
| JSSDK 不可用导致 navigateBack 失效 | 错误态提供文案引导（手动返回），不强依赖 JSSDK |

## 7. Notes

- 后端 API 本期零改动（身份为既有 token 体系）；ticket 升级为发布前可选增强。
- 原生 chat 页保留：web-view 故障回退 + 双端对照基准。
- 发布阶段清单（非本期）：业务域名配置 + 校验文件上服务器根 + ICP 备案确认 + ticket 换 token 升级。
- E2E 冒烟脚本入 `shenwei-home-h5/scripts/`（fetch 驱动，无浏览器依赖），真机人工验收按 AC7 清单执行。

