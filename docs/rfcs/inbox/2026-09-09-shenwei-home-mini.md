---
title: 深维之家智能客服小程序（前后端新建）
created: 2026-09-09
source: brainstorm
status: inbox
---

# 深维之家智能客服小程序（前后端新建）

## 背景

- **来源**：用户 2026-09-09 提出，要做"深维之家"客服咨询小程序，界面仿照参考截图（新东方客服咨询 H5：顶部欢迎区 + 推荐问题卡片 + 聊天气泡 + 快捷操作条 + 输入框 + 底部功能面板）。
- **现状**：
  - workspace 内已有同形态先例：`rpa-demo-api-wecom-sidebar`（FastAPI + SQLite 后端）、`rpa-demo-web-wecom-sidebar`（React + Vite 前端），可作为工程范式参考，但本次不复用其代码（前端平台不同）。
  - 智能回复能力来自外部服务，对接协议为 `/Users/chenyan/Downloads/im-channel-integration-protocol.md`（IM 渠道对接协议 v1，`channel_type='external'`）：入站 `POST /api/v1/sop/im/external/inbox`（批量、HMAC 签名、幂等键 `(tenant_id, channel_type, account_id, external_msg_id)`），出站支持 callback 推送（`{"ack": true}` 确认）与 pull（`GET /deliveries` + `POST /deliveries/ack`）两种消费方式，共用同一状态机；`kind` 分 `ai_reply` / `boss_reply`。
  - 外部服务凭证（app_key / app_secret / endpoint）已拿到，可直接真实联调。
- **痛点**：目前没有面向终端 C 端用户的客服入口；需要一个微信小程序承载用户咨询，后端负责协议对接。

## 目标（用户视角）

- 让用户在微信小程序内发起咨询，获得外部服务生成的智能自动回复（含 AI 直答与 boss_reply）。
- 让用户能发送文字、表情、图片三类消息，图片在对话中正常展示。
- 让用户能一键"转人工"，得到明确的转接提示。
- 让用户重进小程序/下拉时能看到历史对话（后端落库，分页拉取）。
- 界面观感对齐参考设计：白 + 浅灰 + 青色渐变的现代移动 UI，欢迎区 + 推荐问题卡片 + 气泡流。

## 范围

### 在范围内（In Scope）

**前端（微信小程序原生 WXML/WXSS/JS，项目名 `shenwei-home-mini`）**
- 聊天主界面，仿参考设计：
  - 顶部导航（标题"深维之家"，可自定义）；
  - 欢迎区（问候语 + 引导文案，青色渐变背景；吉祥物可后置）；
  - 推荐问题卡片（"你可以这样问我"，点击即发送；问题清单由后端配置接口下发）；
  - 消息气泡流（用户右侧、客服/AI 左侧带头像；图片消息显示图片；支持下拉加载历史）；
  - 快捷操作条：**仅保留"转人工"**（参考图中的服务评价、切换学员不做）；
  - 输入框：文字输入 + **表情面板** + **图片选择**（`wx.chooseMedia`，从相册/相机）；底部扩展面板仅保留图片入口（购物车、工单不做）；
- `wx.login` 静默登录，code 换 openid；
- 发消息 → 轮询/长连接收 AI 回复（前端到我们后端，不直连外部服务）；
- 历史消息分页拉取（下拉加载更早消息）。

**后端（FastAPI + SQLite，项目名 `shenwei-home-api`）**
- 小程序侧 API：
  - 登录：code → openid（微信 `jscode2session`），签发会话凭证；openid 映射稳定的 `external_user_id` 与 `conversation_key`；
  - 发送消息接口（文字/表情/图片），生成 `external_msg_id`、落库、HMAC 签名后转发外部 `POST /external/inbox`；
  - 图片上传接口（先存本地/对象存储，对话可回显；发给外部 AI 的内容为文本占位"[用户发送了图片]"，等外部约定图片能力后再对接真实图片语义）；
  - 历史消息分页接口；
  - 收件接口：小程序轮询获取新回复（后端把已确认送达的出站投递下发）；
  - 转人工接口：往外部 inbox 发 `msg_type='event'`（`event_type=transfer_to_human`，具体 event_type 值联调时与外部确认）+ 本地会话插一条提示语；
  - 推荐问题配置接口（首期可硬编码/配置文件）。
- 外部协议对接：
  - 协议客户端：HMAC-SHA256 签名（`timestamp + "\n" + nonce + "\n" + SHA256_HEX(body)`，四头携带）、nonce 管理、错误码分类重试（4xx 不重试、5xx 指数退避、`timestamp_skew` 校时重试）；
  - callback 接收端点（公网 HTTPS）：验签（只带 Timestamp/Nonce/Signature 三头）、challenge 回显、处理 `ai_reply` / `boss_reply`、回 `{"ack": true}`；
  - 投递落库与小程序下发状态管理。
  - ~~pull 兜底~~ 已裁剪（2026-09-09 更新）：实例已配 callback_url，实测 pull 常年为空，出站统一走 push 消费。
- 演示/联调配置：endpoint、app_key、app_secret 走环境变量/配置文件，不硬编码。

### 不在范围内（Non-Goals）

- 服务评价、切换学员、购物车、工单等快捷入口（参考图中出现但本期不做）；
- 图片内容进 AI（等外部服务约定图片协议后再做；本期仅本地展示 + 占位文本）；
- 语音消息（协议支持 voice，但本期 UI 不做语音输入）；
- 人工坐席工作台 / 会话接管（协议明确不提供，升级是外部系统内部环节）；
- 出站 pull 消费方式（`GET /deliveries` + ack）：实例已配 callback_url，统一走 push；
- 多租户、OAuth、限流（协议 v1 亦未启用限流）；
- 管理后台。

## 约束

- 前端必须是**微信小程序原生**开发（用户已确认），不用 Taro/uni-app；
- 后端与外部服务的一切往来必须符合协议 v1：Additive-Only、未知字段忽略、未知 `msg_type`/`kind`/`status` 记录并跳过不报错；
- `app_secret` 永不上行，仅参与签名计算，只能存后端配置；响应体不得回显；
- 幂等：`external_msg_id` 全局唯一（我们后端生成，如 UUID）；出站按 `delivery_id` 去重（at-least-once 语义）；
- 时效门控：`occurred_at` 距今超 5 分钟外部不触发回复 → 我们转发必须用当前时间，不能透传客户端时间；
- pull 时 `cursor` 空串表示无下一页，保留上一页游标不覆盖；
- 微信小程序合规：request/uploadFile 合法域名需备案配置；图片 ≤ 微信选择限制，后端建议 ≤10MB 对齐协议媒体约束；
- 项目位置：`/Users/chenyan/Documents/sop-mini/shenwei-home-mini`（小程序）+ `/Users/chenyan/Documents/sop-mini/shenwei-home-api`（后端），与现有 rpa-demo-* 平级。

## 已讨论的方案

### 方案 A：后端全协议对接，推送为主 + pull 兜底（已选 ✓）

- **核心思路**：我们后端作为协议"对接方"完整实现入站（inbox 签名转发）与出站消费（callback 推送接收为主、pull 轮询兜底），小程序只与我们后端通信。
- **优点**：
  - 符合协议 server-to-server 设计，`app_secret` 不出后端；
  - push 直推延迟低；实例已配 callback_url（2026-09-09 实测 pull 常年为空），单 push 路径即可覆盖；
  - 支持 `ai_reply` 与 `boss_reply` 全类型。
- **缺点**：
  - callback 需要公网 HTTPS 可达（部署要求）；
  - 后端需实现完整状态机，工作量中等。

### 方案 B：前端直连外部服务

- **核心思路**：小程序直接签名调外部 inbox/deliveries。
- **优点**：少一层后端。
- **缺点**：
  - `app_secret` 暴露在前端包内，安全硬伤；
  - 小程序要求 HTTPS 合法域名，外部服务域名未必可配；
  - 违背协议 server-to-server 定位。
- **驳回理由**：安全性不可接受，直接排除。

### 方案 C：仅转发 MVP（不做 boss_reply / 转人工）

- **核心思路**：一期只把消息转发进协议、收到什么推什么。
- **优点**：最快跑通。
- **缺点**：转人工是本期明确要的功能，boss_reply 是协议核心产出之一，砍掉不完整。
- **驳回理由**：与用户明确要的"转人工"冲突；后端全对接成本可控，无必要先做残缺版。

### 图片处理子方案（已选 ✓）

- 图片本地选择、本地展示；发外部 AI 时用占位文本"[用户发送了图片]"（或类似），等外部约定图片协议后再对接真实语义。协议 `msg_type` 枚举 Additive-Only 但当前无 `image`，不臆造字段。

### 转人工子方案（已选 ✓）

- 点击后：后端发 `msg_type='event'`、`event_type=transfer_to_human` 进外部 inbox（具体枚举值联调时与外部确认），同时小程序会话内插提示语"已为您转接人工，请稍候"。

### 用户身份子方案（已选 ✓）

- `wx.login` 静默登录 → code 换 openid → openid 映射稳定 `external_user_id` / `conversation_key`，无需用户授权弹窗。

## 成功标准

- [ ] 小程序在开发者工具/真机预览可运行：欢迎区、推荐问题卡片、气泡流、快捷操作条（仅转人工）、输入框（文字/表情/图片）按参考设计呈现；
- [ ] 发送一条文字消息 → 后端签名转发 inbox 得到逐条 `accepted` → 用户在小程序内收到 `ai_reply` 回复（push 或 pull 任一路径，端到端 < 外部服务回复时长 + 3s）；
- [ ] 同一消息重发网络重试不产生重复回复（幂等键生效）；
- [ ] 发送图片：气泡内正常显示图片，外部收到的是占位文本；
- [ ] 点"转人工"：会话出现提示语，外部 inbox 收到一条 event；
- [ ] 下拉可加载历史消息，杀进程重进后会话记录不丢；
- [ ] callback 端点通过外部 challenge 校验，推送 → 验签 → ack → 下发小程序全链路通；
- [ ] 代码内无硬编码 `app_secret`（配置注入），响应体不含凭证。

## 待解决问题

- 外部服务 `event_type=transfer_to_human` 是否被识别处理？event 枚举值需联调确认（协议 4.1 event 仅示例 `enter_session`）；
- 外部服务是否计划支持图片 `msg_type`？何时约定？（决定图片占位方案何时升级）
- callback_url 公网部署形态：直接暴露还是走内网穿透联调（开发期建议 ngrok/frp 类方案）；
- 微信小程序 AppID 是否已注册认证（影响 openid 登录与真机预览）；
- 推荐问题清单的内容来源（产品提供文案，首期配置文件承载）；
- `conversation_key` 粒度：单用户单会话（客服咨询场景默认）还是支持多会话，需产品确认；
- 图片存储：本地盘 vs 对象存储，视部署环境定（demo 期本地盘可接受，需注意部署清理问题——协议文档明确提过本地目录会被部署流程清掉的教训）。
