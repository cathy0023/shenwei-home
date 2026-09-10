---
title: SSE 实时推送设计（替换前端轮询）
date: 2026-09-10
status: draft
source: brainstorm
decisions:
  transport: SSE（wx.request enableChunked，复用 quiz 项目 SessionStream 模式）
  notify: callback 落库 asyncio 事件通知 + 服务端 2s 兜底扫描
  fallback: 前端轮询保留为降级路径
---

# SSE 实时推送设计（替换前端轮询）

## 1. 背景与目标

现状：小程序以 3-10s 短轮询（`GET /api/messages/poll`）拉取外部服务推送回来的 AI/人工回复。痛点：回复延迟最高 10s；空闲期持续发起请求（耗电耗流量）。

目标：
- G1: 新回复亚秒级到达小程序（外部 callback 落库 → 前端渲染 < 1s）；
- G2: 空闲期无客户端请求（连接保持、服务端按需推）；
- G3: 断线/失败平滑降级回现有轮询，不丢消息（poll 语义不变）。

**可行性依据**：`/Users/chenyan/Documents/cy-test/wx-mp-plugin-sdk-open-api-quiz` 项目已在微信小程序生产验证 SSE——`wx.request` + `enableChunked: true` + `arraybuffer` + 自研 SSE 解析器，含 iOS 真机验证记录。本次直接移植该模式。

## 2. 架构

```
外部服务 --callback--> [FastAPI] --落库 deliveries + asyncio 事件通知--> [SSE 端点]
                                                                            |
微信小程序 <--SSE 长连接（event: message 通知帧）----------------------------/
     |
     收到通知帧 → 调用现有 GET /api/messages/poll?since= 拉数据（不双写真相）
     SSE 失败/断连 5 次 → 自动回退现有轮询（3-10s）
```

**核心原则**：SSE 只做「有新消息」的通知信令，载荷仍由 poll 下发——单一数据出口，SSE 断连期间消息不丢（重连后 poll 补拉）。

## 3. 后端设计

### 3.1 新端点 `GET /api/messages/stream`

- 鉴权：`token` query 参数（SSE 场景 EventSource 无法带 header；wx.request 可带 header，但统一 query 简化）；无效 401 后直接关流；
- 响应：`StreamingResponse(media_type="text/event-stream")`，头 `Cache-Control: no-cache`、`X-Accel-Buffering: no`（防 nginx 缓冲）；
- 事件帧：
  - `event: message\ndata: {"since": <当前max>}\n\n` —— 有新消息通知；
  - `: ping\n\n` 注释行心跳，每 15s 一次（保活 + 探测半开连接）；
  - `event: close\ndata: {}\n\n` —— 服务端优雅关流（如重启前）；
- 连接生命周期：单连接上限 30 分钟（防僵死），到期发 close 由客户端重连。

### 3.2 新消息检测（单进程单 worker，同进程通知）

```python
# app/events.py（新）
_subscribers: dict[str, set[asyncio.Queue]] = {}  # openid -> queues

def notify_new_message(openid: str):        # callback 落库后调用
    for q in _subscribers.get(openid, ()): 
        q.put_nowait("new")

def subscribe(openid) -> Queue / unsubscribe(openid, q)
```

- `routers/callback.py`：delivery `INSERT OR IGNORE` 后若确实新落库（rowcount>0）→ `notify_new_message(conversation_key)`；
- SSE 端点：`asyncio.wait_for(queue.get(), timeout=2.0)` 循环——2s 超时则做一次兜底 DB 扫描（`SELECT max(created_at) FROM deliveries/messages WHERE conversation_key=?`），有新增也发通知帧（防事件丢失/多进程部署遗漏）；
- 心跳：独立 15s 定时，与通知循环合并为 `asyncio.wait` 多源等待。

### 3.3 nginx 配置

`xdf.conf` 的 `/api/` location 已有 `proxy_buffering off` + `proxy_read_timeout 300s`——SSE 直接可用，**零配置改动**；仅确认 `proxy_http_version 1.1` 已有（有）。

## 4. 前端设计

### 4.1 移植（quiz 项目 → 本项目）

| 源文件 | 处置 |
|---|---|
| `utils/sse-parser.js` | **原样复制**（通用 SSE 帧解析，零业务耦合） |
| `utils/session-stream.js` | 裁剪移植：去掉 turn 去重/phase/ielts 等业务事件，保留 connect/代际守卫/指数退避(5次)/网络监听重连/心跳超时判死；URL 换 `/api/messages/stream?token=`；handler 收敛为 `onNotify`（触发 pollOnce）与 `onDown`（切轮询） |

### 4.2 chat.js 集成

- onLoad：登录后启动 SSE（保持现有 `loadHistory`）；
- `onNotify` → 立即 `pollOnce()`（现有函数原样复用）并重置轮询退避；
- `onDown`（SSE 5 次重连耗尽）→ `startPolling()` 现有轮询路径，toast 提示「实时通道不可用，已切换轮询」；
- onHide → 销毁 SSE；onShow → 重建 SSE + 立即 pollOnce（现有语义不变）；
- 现有轮询代码**保留不删**，仅在 SSE 未建立/降级时运行。

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| SSE 连接失败/5 次重连耗尽 | 降级轮询（现状路径），用户无感 |
| 网络切换（WiFi↔蜂窝） | `wx.onNetworkStatusChange` 重建连接（quiz 模式） |
| 切后台 | 系统挂起连接；onShow 重建 + 立即 pollOnce 补拉 |
| 服务端重启 | close 帧 → 客户端立即重连（指数退避） |
| 通知帧丢失 | 服务端 2s 兜底扫描 + 客户端心跳超时（45s 无任何帧判死重连）双保险 |
| token 过期 | 端点 401 关流 → 客户端 relogin → 重建 SSE |

## 6. 测试计划

- 单测：notify/subscribe 注册与清理；SSE 端点 401；事件帧格式（`event:`/`data:`/心跳注释行）；callback 落库触发 notify（mock queue 断言 put_nowait 调用）；
- E2E（扩展 e2e.py）：建立 SSE 连接（httpx stream）→ 模拟 callback 推投递 → 断言 <1s 收到 message 帧 → poll 拉到数据；心跳 15s 出现；token 无效 401；
- 前端：check_mini 增加 sse-parser.js / session-stream.js 存在性 + chat.js 集成点断言；
- 真机验证清单：iOS/Android 真机收通知延迟、切后台恢复、断网重连、降级路径。

## 7. 改动面

| 模块 | 改动 |
|---|---|
| 后端新增 | `app/events.py`（订阅注册表）、`GET /api/messages/stream`（约 80 行） |
| 后端修改 | `callback.py` 落库后 notify（1 行） |
| 前端新增 | `utils/sse-parser.js`（复制）、`utils/session-stream.js`（裁剪移植约 150 行） |
| 前端修改 | `chat.js` 集成（启动/降级/生命周期，约 30 行） |
| nginx | 零改动（已具备） |
| 数据库 | 零迁移 |

## 8. 非目标

- WebSocket（SSE 已满足单向通知需求，且客户端代码已有验证资产）；
- SSE 携带消息载荷（坚持「通知 + poll 拉取」，避免双写真相）；
- 多 worker/多进程部署的跨进程通知（demo 单 worker；届时换 Redis pub/sub，接口已隔离在 events.py）；
- 图片链路（独立 spec，见 2026-09-10-image-pipeline-design.md）。
