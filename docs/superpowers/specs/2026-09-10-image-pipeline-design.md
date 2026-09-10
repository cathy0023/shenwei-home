---
title: 图片全链路能力设计（发送/OCR/接收）
date: 2026-09-10
status: draft
source: brainstorm
decisions:
  ocr_owner: 外部服务
  protocol_assumption: 假设可扩展，边做边联调
  transport: media_url 引用（方案 A）
  scope: 双向（发出向图 + 接收外部图片回复）
---

# 图片全链路能力设计（发送/OCR/接收）

## 1. 背景与目标

当前图片链路是半成品：用户在小程序发图 → 存后端 `uploads/`（仅小程序回显）→ 转发给外部 AI 的只是占位文本「[用户发送了图片]」——**AI 看不到图，无法 OCR/理解**。接收方向（外部/人工发图给用户）完全未做。

本设计补齐全链路，达成：

- G1: 用户发的图片能被外部服务下载并 OCR/理解，回复内容针对图片内容；
- G2: 外部（人工坐席）能向用户发图，小程序内正常展示；
- G3: 图片访问安全可控（不公开可枚举、有时效、防篡改）；
- G4: 协议合规——不破坏 IM 渠道对接协议 v1 既有约定，Additive-Only 演进。

**关键决策（brainstorm 确认）**：OCR 由外部服务做；假设外部可扩展支持图片、边做边联调；传输用 `media_url` 引用（复用协议 4.2 voice 先例）；双向同时实现。

## 2. 协议依据与约束

| 约束点 | 协议依据 | 本设计对策 |
|---|---|---|
| `msg_type` 枚举仅 text/voice/event，无 image | 协议 4.1 | 出站发图用 `msg_type=text` 载荷携带（文本兜底 + `media_url` 结构化字段）；入站收图按 Additive-Only 容错（未知 msg_type 记录不报错） |
| `media_url` 是既有字段（voice 用），外部有现成下载器 + SSRF 防护（follow_redirects、公网校验、每跳复校、10MB 上限） | 协议 4.2 | 图片 URL 直接复用该字段，外部下载路径理论上零开发 |
| 媒体端点 `/external/media` 格式白名单仅音频 | 协议 4.2 | 不走 media 上传路线（选型结论：方案 A），避免依赖对方改白名单 |
| voice 媒体生命周期 7 天 | 协议 4.2 | 图片签名 URL 有效期对齐 7 天 |
| Additive-Only：未知字段忽略 | 协议 1.3 | 我们在 text content 里加 `media_url` 字段属于 Additive；外部若不支持，文本兜底仍可用 |

## 3. 架构与数据流

### 3.1 出站（用户发图 → 外部 OCR 理解）

```
小程序 wx.chooseMedia
  → POST /api/messages/image            （现状保留：≤10MB、MIME 白名单、UUID 文件名）
  → 存 uploads/{openid}/{uuid}.ext       （磁盘布局不变）
  → 落库 messages.content = {"image_url": "/uploads/{openid}/{name}"}   （相对路径，与现状一致）
  → 转发 inbox（改造点 ★）：
      msg_type: "text"
      content: {
        "content":  "[用户发送了图片] <签名URL>",   ← 文本兜底：外部正则可提取
        "media_url": "<签名URL>"                    ← 结构化字段：复用 voice 先例
      }
外部 → 按 URL 下载图片 → OCR/多模态理解 → ai_reply / boss_reply 文字回流
      （现有 callback → poll 链路零改动）
```

**签名 URL 生成规则**（后端单点函数 `sign_media_url(openid, name)`）：

```
exp = now + 7天
sig = HMAC_SHA256(MEDIA_SIGN_KEY, f"{openid}/{name}/{exp}").hex()[:32]
URL = https://<部署域名>/api/media/{openid}/{name}?exp={exp}&sig={sig}
```

- `MEDIA_SIGN_KEY`：独立环境变量（不复用 `CHANNEL_APP_SECRET`，职责隔离），`.env` 注入；
- 域名取自部署配置（生产 `https://xdf.nonoai.com.cn`），本地开发用 `http://127.0.0.1:8200`。

### 3.2 媒体访问端点（新增 `GET /api/media/{openid}/{name}`）

替代现有公开静态挂载（`/uploads` StaticFiles 移除，访问面收紧）：

1. 校验 `exp`：过期 → `410 Gone`（区别于 404，前端可区分「过期」与「不存在」）；
2. 校验 `sig`：`hmac.compare_digest`，不符 → `410`（与过期同码，不暴露区分度）；
3. `openid`/`name` 白名单校验（`[A-Za-z0-9_-]`，防路径穿越）；
4. 命中：`FileResponse` + `Content-Type` 按扩展名映射 + `X-Content-Type-Options: nosniff`；
5. 未命中文件：`404`。

### 3.3 入站（外部/人工发图 → 用户）

```
callback 收到投递（建议向外部提议的形状，联调确认项）：
  { "kind": "ai_reply"|"boss_reply", "msg_type": "image",
    "content": {"content": "配文(可空)", "media_url": "https://外部地址/图"} }

后端（基本零改动）：
  → deliveries 落库（现状已支持，未知 msg_type 容错记录）
  → poll/list 下发时把 content 透传（含 media_url）

前端（小改）：
  → toViewModel：assistant 气泡也识别 image_url/media_url 渲染 <image>
  → 加载失败/无 URL：显示「[图片]」占位块，配文照常显示
```

## 4. 数据模型变更

**零迁移**。`messages.content` / `deliveries.content` 均为 JSON 列，新增键（`media_url`）自然兼容；签名 URL 一律在出口（下发前端 / 外发外部）由后端实时拼装，库里只存相对路径——未来换签名算法/域名/有效期不影响存量数据。

## 5. 安全设计

| 面向 | 措施 |
|---|---|
| 不可枚举 | 文件名 uuid4 hex（现状保留） |
| 防篡改/防遍历 | HMAC 签名覆盖 `openid/name/exp`；compare_digest 恒时比较 |
| 时效 | 7 天有效期，过期 410；外部异步下载窗口 + 用户翻历史窗口均可覆盖 |
| 访问面收敛 | 移除公开 `/uploads` 静态挂载，唯一入口是签名端点（对比现状的净改进：现在任何人不带凭证都能读 `/uploads/*`） |
| 路径穿越 | openid/name 正则白名单（复用 P0 修复的字符集约束） |
| 内容类型 | 响应带 `nosniff`；上传侧 MIME 白名单 + 10MB 上限维持现状 |
| 密钥 | `MEDIA_SIGN_KEY` 独立 env，不入库不回显；与协议 HMAC 密钥职责隔离（外发签名/验签体系不受影响） |

## 6. 错误处理与降级

| 故障场景 | 行为 |
|---|---|
| 外部不认 `media_url` 字段 | 文本兜底：`[用户发送了图片] <URL>`，外部正则提取 URL 仍可下载；最差降级为现状（占位文本），链路不阻塞 |
| 外部下载失败（网络/过期/格式不识别） | 外部侧静默降级（协议 4.2 外部行为，我们不可感知）→ 列入联调验证清单 |
| 用户翻旧历史，图片已过期 | 前端 `<image>` binderror → 渲染「图片已过期」占位块（灰底图标 + 文案），配文不受影响 |
| 外部 image 投递缺 `media_url` | 前端只显示 content 配文 + 「[图片]」占位；不报错（Additive-Only） |
| 签名密钥轮换 | 旧 URL 立即失效（410），用户重新进入会话时新 URL 由后端重签——存量聊天中的旧图变过期占位，可接受 |

## 7. 测试计划

**单元测试**（pytest，覆盖 media 签名模块）：
- 签名生成确定性（同输入同输出）、有效期计算正确；
- 端点：有效签名 200、过期 410、篡改 sig 410、伪造路径字符 400/410、文件不存在 404、nosniff 头存在；
- inbox 外发载荷：text content 含兜底文本 + media_url 字段齐备；
- list/poll 下发 assistant image 投递时 content 透传完整。

**E2E**（扩展 `scripts/e2e.py`）：
1. 上传图片 → 从响应解析签名 URL → 公网 GET 200 且字节一致；
2. 篡改 sig → 410；
3. 过期（mock 时间）→ 410；
4. 模拟外部推 `msg_type=image` 投递（HMAC 签名）→ poll 拉到且 content 带配文+media_url；
5. 回归：文本消息、占位文本降级路径不受影响。

**联调确认清单（给外部服务方，本设计的产出物）**：
1. 你们下载器是否接受图片后缀/Content-Type（当前白名单疑似仅音频）？
2. OCR/多模态接入点：下载后走什么管线，text content 里的 URL 正则提取是否需要？
3. 你们回图（boss 在飞书发图）的投递形状确认：`msg_type=image` + `content.media_url` 是否成立？
4. `media_url` 字段是否纳入协议文档 v1.x（Additive-Only 演进）？

## 8. 改动面汇总

| 模块 | 改动 |
|---|---|
| 后端新增 | `app/media.py`（签名生成/校验 + `GET /api/media/{openid}/{name}` 端点） |
| 后端修改 | `service.py` 外发载荷（占位文本 → 兜底文本+media_url）；`main.py` 移除 `/uploads` 静态挂载；config 增加 `MEDIA_SIGN_KEY`/`PUBLIC_BASE_URL` |
| 前端小改 | `toViewModel` assistant 分支识别 image；过期/缺 URL 占位块 |
| 数据库 | 零迁移 |
| 部署 | `.env` 增两配置项；nginx 已有 `/uploads` location 可删（走 `/api/media`） |

## 9. 非目标（本期不做）

- 图片压缩/缩略图（原图直出，10MB 上限兜底）；
- 对象存储迁移（本地盘 + 持久卷维持 demo 决策）；
- 语音消息链路；
- 外部 `media_id` 上传路线（方案 B，联调被拒时再评估）；
- 图片过期前的主动刷新机制（重新进会话即重签）。
