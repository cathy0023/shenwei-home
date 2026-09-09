---
id: SHM-001
title: 深维之家智能客服小程序（前后端新建）
status: Approved
created: 2026-09-09
author: shenwei
approved: 2026-09-09
inbox: docs/rfcs/inbox/2026-09-09-shenwei-home-mini.md
---

# SHM-001 深维之家智能客服小程序（前后端新建）

## 1. Summary

新建"深维之家"微信小程序原生前端（`shenwei-home-mini`）+ FastAPI 后端（`shenwei-home-api`），通过 IM 渠道对接协议 v1 将用户消息转发至外部智能回复服务，并接收 callback 推送的 AI 回复回流至小程序。界面对齐已确认的设计稿 `shenwei-home-mini/design/preview.html @2026-09-09 v0.1`（深青渐变 hero + 机器人吉祥物 + 推荐问题卡片 + 转人工 chip + 表情/图片输入）。

## 2. Goals

- G1: 用户在微信小程序内完成文字/表情/图片咨询，并收到外部服务生成的 `ai_reply` / `boss_reply` 回复。
- G2: 快捷操作仅保留"转人工"：点击后后端发 `event` 通知外部 + 小程序内插入转接提示。
- G3: 聊天历史持久化（后端落库），支持下拉分页加载，重进小程序不丢失。
- G4: 外部协议严格按 IM 渠道对接协议 v1 实现（HMAC 签名、幂等、Additive-Only 容错）。
- G5: 界面观感对齐已确认设计稿，WXML/WXSS 原生实现。

## 3. Non-Goals

- 服务评价、切换学员、购物车、工单等快捷入口。
- 图片内容进入 AI（本期仅本地展示 + 占位文本 `[用户发送了图片]`，待外部约定再升级）。
- 语音消息（协议支持 voice，但本期 UI 不做语音输入）。
- 人工坐席工作台 / 会话接管。
- 出站 pull 消费（实例已配 callback_url，统一只走 push）。
- 多租户、OAuth、限流、管理后台。

## 4. Background

- **来源**：用户 2026-09-09 提出，界面仿新东方客服咨询 H5 截图。
- **先例**：workspace 内 `rpa-demo-api-wecom-sidebar`（FastAPI+SQLite）与 `rpa-demo-web-wecom-sidebar`（React+Vite）可作工程范式参考，但前端平台不同不复用代码。
- **外部能力**：IM 渠道对接协议 v1（`POST /external/inbox` 批量入站、`callback` 出站推送、HMAC-SHA256 签名、幂等键、门控 5min 时效等）。凭证已验证（`CHANNEL_APP_KEY/SECRET` 经 `shenwei-home-api/.env` 注入，`scripts/verify_connection.py` 实测 inbox `accepted` / deliveries `200` 通，凭证不在文档明文）。
- **设计稿**：`shenwei-home-mini/design/preview.html @2026-09-09 v0.1` 已在浏览器交互验证（推荐问题/表情/图片/转人工全流程），已确认不做二次视觉评审。

## 5. Design

### 5.1 Architecture

```
[微信小程序 WXML/WXSS/JS]  <--HTTPS-->  [shenwei-home-api FastAPI]
        |                                      |
        |-- wx.login code换openid              |-- HMAC签名前置 inbox 转发 --> [外部 demo.sop.mgvai.cn]
        |-- 发消息/图片/转人工/拉历史            |-- callback 接收 ai_reply/boss_reply (验签+ack)
        |-- 轮询拉新回复 (3s/退避)              |-- 消息落库 SQLite(WAL) + 下发状态
```

- 小程序不直连外部服务，`app_secret` 仅后端持有（`.env` 注入，响应体与日志脱敏）。
- 出站只走 callback push（pull 已裁剪）；保留 `ENABLE_PULL_FALLBACK=false` feature-flag 桩位，开发期可用本地模拟 callback 脚本解耦公网依赖。
- 后端同时服务小程序 API 与外部 callback，两类鉴权隔离：小程序侧 `Bearer token`，外部侧 HMAC。

### 5.2 Tech Stack

| 层 | 选型 | 理由 |
|---|---|---|
| 小程序前端 | 微信小程序原生 WXML/WXSS/JS | 用户已确认，不用 Taro/uni-app |
| 后端 | FastAPI + SQLite(WAL) + httpx + Pydantic | 与 `rpa-demo-api-wecom-sidebar` 同栈，异步友好 |
| 签名 | `hmac` + `hashlib.sha256` 标准库 | 协议 2.2 定死的算法，不引入额外依赖 |
| 存储 | SQLite（`messages` + `deliveries` + `nonces` + `sessions`） | demo 体量，零运维 |

### 5.3 Data Model

```sql
-- SQLite 初始化: PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000;

-- sessions: 小程序会话
sessions(
  token TEXT PK,              -- 32B 随机 hex
  openid TEXT NOT NULL,
  created_at INTEGER,
  expires_at INTEGER          -- +7d
);
CREATE INDEX idx_sessions_openid ON sessions(openid);

-- messages: 小程序侧消息 + 外部 inbox 转发记录
messages(
  id TEXT PK,                 -- UUIDv4 string
  conversation_key TEXT NOT NULL,  -- = openid，本期单用户单会话
  external_user_id TEXT NOT NULL,  -- = openid
  external_msg_id TEXT NOT NULL,   -- 后端生成 UUIDv4，重试复用已落库值
  role TEXT NOT NULL,         -- user | assistant | system
  msg_type TEXT NOT NULL,     -- text | image | event (未知类型记录后跳过不报错)
  content JSON NOT NULL,      -- {content: "..."} 或 {image_url: "..."}
  status TEXT NOT NULL DEFAULT 'pending', -- pending | accepted | failed
  occurred_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  UNIQUE(external_msg_id)     -- 单租户 demo 简化；多租户时扩展为 (tenant_id, channel_type, account_id, external_msg_id)
);
CREATE INDEX idx_messages_conv_created ON messages(conversation_key, created_at DESC, id DESC);
CREATE INDEX idx_messages_external_user ON messages(external_user_id, occurred_at DESC);

-- deliveries: 外部 callback 投递，去重按 delivery_id
deliveries(
  delivery_id TEXT PK,        -- 外部生成
  kind TEXT NOT NULL,         -- ai_reply | boss_reply (未知 kind 记录 warn 仍回 ack:true)
  conversation_key TEXT NOT NULL,
  external_user_id TEXT NOT NULL,
  msg_type TEXT NOT NULL,
  content JSON NOT NULL,
  payload JSON,               -- 原文存档，Additive-Only 容错
  status TEXT NOT NULL DEFAULT 'acked', -- acked
  created_at INTEGER NOT NULL,
  acked_at INTEGER
);
CREATE INDEX idx_deliveries_conv_created ON deliveries(conversation_key, created_at ASC);

-- nonces: callback 重放防护，5min 窗口
nonces(
  nonce TEXT PK,
  expire_at INTEGER NOT NULL
);
-- 定时清理: DELETE FROM nonces WHERE expire_at < now
```

**关键语义**：
- `external_msg_id` 首次落库生成，重试复用 DB 已有值（幂等）。
- `delivery_id` 去重用 `INSERT OR IGNORE`，重复直接回 `{"ack": true}`。
- `messages.status`: `send` 同步落库 `pending` → 后台转发 inbox → 成功置 `accepted`，失败置 `failed`（前端可重试，不丢消息）。
- 未知 `msg_type/kind/status` 记录 warn 日志 + 计数器，仍回 ack，不中断批量。

### 5.4 Backend API

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| POST | `/api/auth/login` | 无 | body `{code}` → `wx.jscode2session` 换 openid（`WX_MINI_*` 为空时 `mock_<code>` 仅开发期）；签发 `token` (32B hex) 存 `sessions` 表 7d；返回 `{token, openid}` |
| POST | `/api/messages/send` | Bearer | body `{content: string(≤2000), msg_type?: text}`；落库 pending → 转发 inbox（`occurred_at=now_ms` 防 5min 门控）→ 置 accepted/failed；`content` 校验长度 |
| POST | `/api/messages/image` | Bearer | multipart `file` (≤10MB, MIME 白名单 `image/jpeg|png|webp|gif`)；文件名 `UUID+ext` 防穿越，存 `uploads/{openid}/{uuid}.ext`；落库 `msg_type=image`；占位文本 `[用户发送了图片]` 进 inbox；磁盘满 507 |
| GET | `/api/messages/list?cursor=&limit=` | Bearer | 游标分页：`cursor` 为上一页最后 `id`，空/非法 400；`limit` 默认 20 上限 50；按 `created_at DESC, id DESC`；`cursor=""` 表示无下一页前端保留旧游标 |
| GET | `/api/messages/poll?since=&limit=` | Bearer | 增量拉新：`since` 为上次 `max(created_at)` 时间戳；查 `deliveries` + `messages` 中 `system` 提示；按 `created_at ASC` 返回 `{items, next_since, has_more}`；空轮询快速返回；前端 3s 轮询（有新消息保持，无消息退避至 10s，切后台暂停 onShow 立即拉） |
| POST | `/api/messages/transfer` | Bearer | 转人工：发 `msg_type=event, event_type=TRANSFER_EVENT_TYPE(默认 transfer_to_human, 环境变量可配)` 进 inbox + 插 `role=system` 提示；前端 5s 防抖 + 后端 `external_msg_id` 去重 |
| GET | `/api/suggestions` | 无 | 推荐问题列表（首期硬编码 + 内存缓存 5min） |
| POST | `/api/external/callback` | HMAC | 外部推送接收：验 timestamp(±300s) → 查 nonce 去重(5min 窗口) → 验 HMAC(3 头 + 本端 secret) → challenge 回显 `{"challenge": 同值}` → 落 deliveries `INSERT OR IGNORE` → 回 `{"ack": true}`；未知 kind 仍 ack |
| GET | `/health` | 无 | 深度检查：DB 可连 + 配置完整性 |

**通用约束**：所有 Pydantic 模型 `model_config = ConfigDict(extra="ignore")` 以满足 Additive-Only；日志与响应体脱敏 `app_secret`。

### 5.5 Protocol Client

- **签名**（协议 2.2）：`signing_string = timestamp + "\n" + nonce + "\n" + SHA256_HEX(body)`，`signature = HMAC_SHA256(app_secret, signing_string).hex().lower()`。
  - 头：`X-Channel-App-Key` / `X-Channel-Timestamp` / `X-Channel-Nonce` / `X-Channel-Signature`（大小写固定）；空 body 按 `""` 计算 SHA256；JSON 规范化 `json.dumps(sort_keys=True, separators=(",",":"))` 后再 SHA256。
  - callback 验签：仅校验 3 头（Timestamp/Nonce/Signature），用本端 `app_secret` 计算对比；`X-App-Key` 缺失为正常（对称设计）。
- **错误分类与重试**：

  | HTTP | error_code | 重试 |
  |---|---|---|
  | 400 | `invalid_field` / `batch_too_large` | 否 |
  | 401 | `bad_signature` / `nonce_replayed` | 否（换 nonce 重签除外） |
  | 401 | `timestamp_skew` | 是（校时后单次重试） |
  | 403 | `instance_disabled` | 否 |
  | 429 | `rate_limited` | 是（按 Retry-After） |
  | 5xx | `internal` / `media_storage_unavailable` | 是（指数退避 10s→60s→300s→900s） |
  | 422/500 | 全局异常 `{code: 4022/5000}` | 按 HTTP 状态码分类 |

  - 伪代码：`external_msg_id` 首次落库生成 → 构造 inbox body → 签名 → POST → 4xx 直接置 failed / 5xx 退避重试(复用同一 external_msg_id) / timestamp_skew 校时重试 1 次。
- **幂等与去重**：`external_msg_id` 重试复用；`delivery_id` `INSERT OR IGNORE`；重复 ack 幂等。
- **时效**：`occurred_at` 用转发时刻 `now_ms`，不透传客户端时间；失败返回 `upstream_rejected` 前端 toast 可重试。

### 5.6 Frontend Pages

单页聊天：`pages/chat/` 承载全部（对齐参考设计无需多页）。
组件拆分：`components/hero`（欢迎区）、`components/suggest-card`、`components/msg-bubble`、`components/input-bar` + `components/emoji-panel`、`components/image-preview`。
状态：`app.js` 存 `token/openid` 于 `wx.storage`，`chat.js` 管理消息列表 + 轮询定时器（3s/退避，切后台暂停）。
输入校验：`content ≤2000`，分页 `limit` 默认 20 上限 50，转人工前端防抖，emoji 正常编码。

### 5.7 Alternatives Considered

| 维度 | 选项 A (已选) | 选项 B | 选项 C | 决策理由 |
|---|---|---|---|---|
| 接入方式 | 后端全代理 + push 主路径 | 前端直连外部 | 极简 MVP(不做转人工/boss_reply) | B 泄漏 `app_secret` 安全硬伤；C 功能不完整(转人工为本期必做) |
| 出站消费 | push only (+ pull feature-flag 桩位) | push + pull 双活 | 仅 pull 轮询 | 实例已配 callback_url 实测 pull 常年为空，单 push 最简状态机；桩位保留降级 |
| 前端轮询 | 3s 短轮询 + 退避 | SSE/WebSocket | 长轮询 | 小程序对 SSE/WS 支持弱，短轮询 MVP 最稳，后续可演进 |
| 存储 | SQLite(WAL) | Postgres | - | demo 体量零运维；WAL + busy_timeout 解决并发锁 |
| 小程序框架 | 原生 WXML/WXSS/JS | Taro | uni-app | 用户已确认原生；Taro 多一层编译，uni-app Vue 栈不一致 |

图片与转人工子方案见 inbox：图片占位 `[用户发送了图片]` 待外部约定升级；转人工 `event_type` 环境变量 `TRANSFER_EVENT_TYPE` 默认 `transfer_to_human`，联调确认。

## 6. Implementation

| Task | 标题 | 产出 | 依赖 |
|---|---|---|---|
| T1 | 后端骨架 + 数据层 + 健康检查 | FastAPI app、config(.env 校验)、db 初始化(WAL/建表/索引)、`GET /health`、sessions 表 | - |
| T2 | 协议客户端 + callback 接收 | `channel_client.py`（签名/转发/错误分类/重试）、`POST /api/external/callback`（timestamp/nonce/HMAC/challenge/delivery 落库）、`scripts/verify_connection.py` 复用验证 | T1 |
| T3a | 小程序侧 Auth + 鉴权中间件 | `POST /api/auth/login`、sessions 7d、Bearer 中间件 `Depends(verify_token)`、mock openid 边界 | T1 |
| T3b | 消息收发 + 历史 + 轮询 | `POST /send`(pending→accepted/failed)、`GET /list`(游标分页)、`GET /poll`(since 增量+退避语义) | T2, T3a |
| T3c | 图片 + 转人工 + 推荐 | `POST /image`(≤10MB/白名单/防穿越)、`POST /transfer`(event 去重)、`GET /suggestions` | T3b |
| T4 | 小程序前端（WXML/WXSS/JS） | `app.*` + `pages/chat/*` + components，对齐 `design/preview.html @v0.1` 视觉 | T3a |
| T5 | 联调打通 + E2E 自测 | 端到端脚本：login→send→callback 模拟→poll→list→image→transfer；本地模拟 callback 脚本(无公网亦可跑通) | T3c, T4 |

> 工时：T1-T2 约 0.5d/个，T3a-T3c 约 0.5-1d/个，T4 约 1d，T5 约 0.5d。每个 Task 遵循 5 步（写测试→跑失败→实现→跑通过→commit）。

## 7. Acceptance Criteria

- [ ] AC1: `shenwei-home-mini` 在微信开发者工具可预览：hero 渐变(深青→亮青)、吉祥物、推荐卡片、气泡流、转人工 chip、输入栏（文字/表情/图片）与 `design/preview.html @v0.1` 像素级一致（提供三态截图：空态/单轮/多轮）。
- [ ] AC2a(Mock): `POST /api/messages/send` 返回 200 且 DB 落库 `status=accepted`（`CHANNEL_ENABLED=false` 时不外发）。
- [ ] AC2b(真实联调): 非 mock 时真实转发外部 inbox 得逐条 `accepted`，`GET /api/messages/poll` 能拉到 callback 落库的 `ai_reply`；CI 仅跑 Mock，真实链路为 `scripts/verify_connection.py` 手动门禁。
- [ ] AC3: `POST /api/messages/image` (≤10MB, 白名单) → 聊天流显示图片，外部收到的是占位文本 `[用户发送了图片]`；未知 `msg_type` 仅 warn 不报错。
- [ ] AC4: `POST /api/messages/transfer` → 会话插入 system 提示，外部 inbox 收到一条 `msg_type=event, event_type=transfer_to_human`（`TRANSFER_EVENT_TYPE` 可配）；重复点击去重。
- [ ] AC5: `GET /api/messages/list` 游标分页有效（`limit` 默认 20 上限 50，空串不覆盖游标），`poll` 增量有效；杀进程重进后历史不丢；`external_msg_id` / `delivery_id` 重放去重；重启容器后 `list` 仍可查（持久卷或 demo 期可接受丢失需文档说明）。
- [ ] AC6: `POST /api/external/callback` challenge 回显 `{"challenge": 同值}` + 推送验签(timestamp/nonce/HMAC) + `{"ack": true}` 确认；未知 `kind` 记录 warn 仍回 ack；nonce 重放 5min 窗口去重。
- [ ] AC7: 无硬编码 `app_secret`（`grep -r app_secret` 仅命中 config 读取），`.env` 注入；响应体与日志不含凭证（`verify_connection.py` 零依赖指代该脚本自身不依赖 httpx，与后端选型 httpx 不矛盾）。
- [ ] AC8(降级): `CHANNEL_ENABLED=false` 时 send 仅本地落库，前端轮询与历史不受影响。

## 8. Risks & Mitigations

| 风险 | 缓解 |
|---|---|
| callback 需公网 HTTPS 才能被外部推到 | 开发期可用内网穿透；保留 `ENABLE_PULL_FALLBACK` 桩位；T5 本地模拟 callback 脚本无公网亦可跑通 |
| 外部 event_type 未约定 | `TRANSFER_EVENT_TYPE` 环境变量可配，默认 `transfer_to_human`；外部忽略则降级为 text 占位 + system 提示 |
| 微信 AppID 未注册 | `WX_MINI_*` 为空走 `mock_<code>` 仅开发期，不阻塞 |
| SQLite 并发锁 (`database is locked`) | `WAL + synchronous=NORMAL + busy_timeout=5000ms`；demo 期单 worker，必要时文件锁队列 |
| `uploads/` 被部署清理 | 路径 `uploads/{openid}/{uuid}.ext` 持久卷挂载或文档声明 demo 期可接受丢失；大小 ≤10MB、MIME 白名单、定期清理 |
| 服务器时钟漂移 → `timestamp_skew` | 收 `timestamp_skew` 后校时单次重试；部署 NTP 同步 |
| 5min 时效门控丢消息 | 转发 `occurred_at=now_ms`；失败前端 toast 可重试 |
| 轮询风暴（并发用户高频 poll） | 有新消息 3s / 无消息退避至 10s；切后台暂停；空轮询快速返回；`deliveries` 索引保障 |
| 外部服务不可用/超时 | 前端降级提示 + 重试；`messages.status=failed` 可查询 |
| 小程序 request 合法域名未配 | 微信后台 `request合法域名` 配置 `https://<后端域名>`；未配时开发工具勾选不校验 |
| 日志/响应体泄露凭证 | 结构化日志脱敏 `app_secret`；AC7 自动化扫描 |

## 9. Observability & Rollout

- **日志**：结构化 JSON（字段 `external_msg_id/delivery_id/latency/kind`），`app_secret` 脱敏；未知 kind/msg_type 记 warn + 计数器。
- **指标**：callback 验签失败率、inbox 转发成功率、poll 延迟 P95。
- **健康检查**：`GET /health` 深度检查 DB 可连 + 配置完整性。
- **发布**：小程序 灰度（开发者工具→体验版→正式版）；后端保留上一版镜像可回滚；`CHANNEL_ENABLED` 一键降级 Mock。

## 10. Open Questions

| 问题 | Owner | 状态 |
|---|---|---|
| `event_type=transfer_to_human` 是否被外部识别处理 | 后端联调确认 | 待联调 |
| 外部是否计划支持 `image` msg_type，何时约定 | 外部产品 | 待确认 |
| callback_url 公网部署形态（直接暴露 vs 内网穿透） | 运维 | 开发期穿透，生产直连 |
| 微信小程序 AppID 是否已注册认证 | 产品 | 待确认 |
| 推荐问题清单内容来源 | 产品 | 首期硬编码，配置化后续 |
| `conversation_key` 粒度（单用户单会话 vs 多会话） | 产品 | 本期单会话(`=openid`) |
| 图片存储（本地盘 vs 对象存储） | 运维 | demo 本地盘 + 持久卷，生产对象存储 |

## 11. Rollback Plan

- **DB**：建表 `IF NOT EXISTS` + 版本化迁移；失败空库重建不阻塞启动。
- **外部对接**：HMAC/转发失败本地仍落库，前端可展示；`CHANNEL_ENABLED=false` 降级 Mock。
- **部署**：保留上一版镜像可 `docker rollback`；小程序体验版可回退。

## 12. Notes

- 凭证仅 `shenwei-home-api/.env`，两级 `.gitignore` 已排除，不在文档与 git 历史明文。
- 图片 protocol gap 已在 inbox 记录，待外部约定 `image` 再升级多模态链路。
- 工时为估算，非"分钟级"承诺；每个 Task 5 步 TDD。

