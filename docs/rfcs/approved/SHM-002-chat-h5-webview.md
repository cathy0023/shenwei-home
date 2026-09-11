---
id: SHM-002
title: chat 页 H5 化（React + web-view 嵌入）
status: Approved
created: 2026-09-11
approved: 2026-09-11
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
- H5 首帧：读 URL query 的 token（优先）→ 无存则回读 sessionStorage（刷新/内存重载恢复）→ 存 sessionStorage → `history.replaceState` 清除 URL 中的 token → 所有 API 带 Bearer；
- token 失效（401）：先清 sessionStorage，H5 显示错误态卡片「登录已过期，请返回小程序重新进入」+ 返回按钮（`wx.miniProgram.navigateBack`，JSSDK 可用时）；
- 发布前升级：后端签发 60s 一次性 ticket 代替长期 token 上 URL（Additive：新增 `/api/auth/exchange` 端点，H5 改首帧换 token）。

### 3.4 H5 聊天页功能规格（对齐原生页最终形态）

| 能力 | 实现要点 |
|---|---|
| 消息流 | list 倒序反转 ASC 展示；`kind=boss_reply` 右上角「人工」金标 + 琥珀人形徽章头像（CSS mask SVG）；图片消息裸气泡无边框 |
| 发文字 | 乐观回显 temp 气泡 → send API → 状态同步；≤2000 字 |
| 发图片 | `<input type="file" accept="image/*">`（**单文件**，Android multiple 有兼容坑）→ canvas 压缩（quality 0.6，长边 1600px）→ FormData 上传 → 本地 blob URL 展示（会话内），历史从签名 URL 加载；失败占位卡片 |
| 历史分页 | 上滑加载更早：游标 list 接口（cursor=首条 id），加载态提示，游标从最新历史项初始化防重放 |
| 收回复 | 轮询 poll?since= 游标，3s 起、空闲退避 10s；visibilitychange 暂停/恢复（恢复时立即拉一次） |
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
# 目录布局：/opt/shenwei-home/h5/（root 指向上级，URI 前缀自然命中，无 alias 拼接陷阱）
location /h5/ {
    root /opt/shenwei-home;
    try_files $uri $uri/ /h5/index.html;   # 单视图无路由：fallback 仅为 /h5/ 本身重载兜底
}
# index.html 不缓存（gzip 静态资源开启；add_header 继承规则：本 location 不继承 server 级头，如未来加安全头需 include 统一）
location = /h5/index.html { root /opt/shenwei-home; add_header Cache-Control "no-cache"; }
# token 脱敏：access log 写入前剔除 token= 参数（方案锁定——nginx log_format 变体）
log_format tokenless '$remote_addr [$time_local] "$request_method $uri" '
                  '$status $body_bytes_sent '
                  '"$http_referer" "$http_user_agent"';   # 自定义 format 不含 $args
access_log /var/log/nginx/xdf.access.log tokenless if=$log_tokenless;   # 仅 /h5/ 路径走该 format
```

## 3.6b Non-Goals

- SSE 实时推送（spec 已备：`docs/superpowers/specs/2026-09-10-sse-push-design.md`，独立迭代）；
- 语音消息、客服坐席工作台、管理后台；
- 正式发布所需的业务域名配置/校验文件/ICP 备案（发布阶段清单，不阻塞开发）；
- H5 独立 SEO/分享能力（web-view 内无意义）；
- 后端 API 改动（本期零改动）；
- ticket 换 token 升级（发布前增强项，本期用内联 token）。

### 3.7 Alternatives Considered

| 维度 | 已选 | 备选 | 驳回理由 |
|---|---|---|---|
| UI 组件库 | 原生 CSS 移植 | Ant Design Mobile/TDesign | 主题定制成本>自写；包体积+200KB 拖慢 web-view 首屏 |
| 身份传递 | URL 内联 token | ticket 换 token / cookie / postMessage | ticket 为发布前升级项（后端加端点即可）；cookie 在 web-view 割裂不可靠；postMessage 仅特定时机投递 |
| 部署 | nginx 子路径 /h5/ | FastAPI StaticFiles / 独立子域 | StaticFiles 前后端发版耦合；子域需新证书+业务域名多配一条 |
| 图片选择 | H5 input file 单文件 | JSSDK wx.chooseImage | JSSDK 需后端签名 wx.config 且仅限图片；input file 基本可用 |
| 客户端架构 | web-view+H5 | Taro/uni-app 跨端编译 | 交付物需独立 H5 嵌客户 webview；存量原生页重写+框架锁定成本高 |
| 客户端架构 | web-view+H5 | 维持原生不做 H5 | 不满足「对齐客户侧 webview+H5 交付形态」的业务驱动 |

## 4. Implementation

| Task | 标题 | 产出 | 依赖 |
|---|---|---|---|
| T0 | 建仓 | `shenwei-home-h5/` 目录入现有仓（含 .gitignore 排除 dist/node_modules），首次推送 GitHub | - |
| T1 | H5 脚手架 + API 层 | `shenwei-home-h5/`（Vite+React+TS，base=/h5/）、`src/api.ts`（token 注入/401 错误态）、token query 解析工具 | - |
| T2 | 聊天页 UI 骨架 + 设计变量 + 键盘/安全区 | 全局样式（preview.html 变量移植）、消息流组件（气泡/头像/金标）、输入栏组件（fixed 布局定型时即做 visualViewport 键盘适配 + safe-area，不后置）、hero 区 | T1 |
| T3 | 核心交互 | 发文字（乐观回显）、历史分页、轮询收回复（退避+visibilitychange）、表情盘 | T2 |
| T4 | 图片链路 | input file 单选+canvas 压缩+上传、blob/签名 URL 展示策略、失败占位 | T3 |
| T5 | 转人工 + 错误态/空态收尾 | transfer、错误态卡片（401 清 sessionStorage + 返回引导）、空态 | T4 |
| T6 | 小程序壳 | pages/mine（我的）、pages/webview、app.json 注册、跳转链路 | T1（并行） |
| T7 | 部署 + 验证 | nginx /h5/ location（root 上级目录写法）、access log token 脱敏、构建产物部署（rsync 时间戳目录+symlink 原子切换）、API 冒烟脚本（以传入 token 为前提，登录步骤改为种子 token 直插 sessions 表——wx.login code 在微信外不可得）、真机 web-view 验证 | T5, T6 |

> 工时：T1-T5 各约 0.5d，T6 0.5d，T7 0.5d。H5 侧用 Vitest + Testing Library 对 API 层/工具函数做单测；组件交互以浏览器 E2E 冒烟为主。

## 5. Acceptance Criteria

- [ ] AC1: 浏览器打开 `https://xdf.nonoai.com.cn/h5/?token=<有效token>`：历史消息（含图片、人工金标）完整展示；视觉对照 preview.html 五项清单（hero 渐变+机器人/气泡圆角配色/人工金标+头像徽章/输入栏布局/表情盘网格）逐项一致。
- [ ] AC2: H5 内发文字 → 收到 AI 回复（轮询路径）；发图片（自动压缩）→ 聊天内即时显示，历史重进后仍显示（签名 URL）。
- [ ] AC3: 转人工 → system 提示出现；boss_reply 回流 → 气泡带「人工」金标 + 人形徽章头像。
- [ ] AC3a: 表情盘 32 枚 emoji 与 `shenwei-home-mini/pages/chat/chat.js` EMOJIS 数组**逐枚字符相等**（单测断言）；弹出位置/grid 与原生页一致。
- [ ] AC3b: 历史分页上滑加载更早——`GET /api/messages/list?cursor=<首条id>&limit=20` 单次返回 ≤20 条，加载态文案「正在加载…」可见，单测断言 cursor 推进与消息按 created_at ASC 归并正确（对齐 `tests/test_list_history_merge.py` 已覆盖的后端契约）。
- [ ] AC4: token 缺失/失效 → H5 错误态卡片，不白屏不报未处理异常。
- [ ] AC5: 小程序「我的」页 →「联系客服」→ web-view 打开 H5，身份直通可见自己的会话；原生 chat 页保留可回退。
- [ ] AC6: 服务器侧 `xdf.nonoai.com.cn/h5/` 可访问（curl 200 + HTML 含构建资源引用），同域调 API 无 CORS；直接访问 `/h5/` 重载正常（单视图无路由，无任意深链概念）。
- [ ] AC7: iOS/Android 真机（开发版）各过一遍核心链路：键盘弹收后消息列表可见、底部安全区无遮挡、图片选择上传成功、web-view 页分享菜单无 token 泄露（onShareAppMessage 已禁用/剥离）。
- [ ] AC8: 仓库推送 GitHub（T0 建仓动作：shenwei-home-h5/ 加入现有仓并推送），`shenwei-home-h5` 含 README（本地开发/构建/部署说明）；H5 构建产物 gzip 体积 < 200KB。

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
| web-view 页被转发，分享卡片携带含 token 的 src | pages/webview 的 onShareAppMessage 返回空/禁用分享；T6 实现 |
| iOS input file 产出 HEIC、canvas 解码失败 | 解码失败回退原图上传；后端 415 时显示失败占位（与原生页「失败退回原图」行为对齐） |
| Android 微信 X5 file chooser 偶发不弹 | 真机验收清单单列；JSSDK chooseImage 为备选路径 |
| nginx access log 记录含 token 的 query | /h5/ 请求的日志做 token 脱敏（map $arg_token）；T7 实现 |

## 7. Notes

- 后端 API 本期零改动（身份为既有 token 体系）；ticket 升级为发布前可选增强。
- 原生 chat 页保留：web-view 故障回退 + 双端对照基准。
- 发布阶段清单（非本期）：业务域名配置 + 校验文件上服务器根 + ICP 备案确认 + ticket 换 token 升级。
- E2E 冒烟脚本入 `shenwei-home-h5/scripts/`（fetch 驱动，无浏览器依赖），真机人工验收按 AC7 清单执行。

