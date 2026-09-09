# SHM-001 深维之家智能客服小程序 — 实现计划

> RFC: `docs/rfcs/approved/SHM-001-shenwei-home-mini.md`
> 设计稿: `shenwei-home-mini/design/preview.html @2026-09-09 v0.1`
> 协议: `im-channel-integration-protocol.md` v1

## Goal

建成 `shenwei-home-mini`（微信小程序原生）+ `shenwei-home-api`（FastAPI+SQLite/WAL）全链路，通过 HMAC 对接外部智能回复服务，满足 AC1-AC8。

## Architecture

- worktree: `feat/shenwei-home`，target `main`
- 后端: `shenwei-home-api/app/`（main/config/db/auth/channel_client/routers/{messages,callback,suggestions}）
- 前端: `shenwei-home-mini/{app.*, pages/chat/, components/*}`
- 依赖顺序: T1 → T2 → T3a → T3b → T3c → T4 → T5

## Tech Stack

- Backend: Python 3.11+, FastAPI, httpx, Pydantic v2, SQLite(WAL), pytest
- Frontend: 微信小程序原生 WXML/WXSS/JS
- Signing: hmac + hashlib (标准库)

## Tasks

### T1: 后端骨架 + 数据层 + 健康检查

- [ ] 1.1 写测试: `shenwei-home-api/tests/test_health.py` — `GET /health` 返回 200 + `{status: ok}`，DB 未初始化时 503
- [ ] 1.2 跑失败: `pytest shenwei-home-api/tests/test_health.py` 预期 FAIL（无 app）
- [ ] 1.3 实现: `shenwei-home-api/app/main.py` (FastAPI), `app/config.py` (.env 读取+校验), `app/db.py` (WAL + 4 表建表+索引), `requirements.txt`
- [ ] 1.4 跑通过: `pytest shenwei-home-api/tests/test_health.py` PASS + `curl /health` 200
- [ ] 1.5 commit: `feat(api): T1 backend skeleton + WAL db + health`

### T2: 协议客户端 + callback 接收

- [ ] 2.1 写测试: `tests/test_channel_client.py` (签名向量/空body/错误分类) + `tests/test_callback.py` (challenge/nonce/HMAC/去重/未知kind)
- [ ] 2.2 跑失败: pytest 预期 FAIL
- [ ] 2.3 实现: `app/channel_client.py` (sign/forward/retry), `app/routers/callback.py` (POST /api/external/callback), `app/crypto.py` (HMAC helpers)
- [ ] 2.4 跑通过: pytest 全绿 + `scripts/verify_connection.py` 实测 inbox accepted 仍有效
- [ ] 2.5 commit: `feat(api): T2 channel client + callback + HMAC verify`

### T3a: Auth + 鉴权中间件

- [ ] 3a.1 写测试: `tests/test_auth.py` — login 返回 token+openid、Bearer 鉴权、过期、mock 边界
- [ ] 3a.2 跑失败: 预期 FAIL
- [ ] 3a.3 实现: `app/routers/auth.py`, `app/auth.py` (token 32B hex + sessions 7d), `app/deps.py` (verify_token)
- [ ] 3a.4 跑通过: pytest 全绿
- [ ] 3a.5 commit: `feat(api): T3a auth + Bearer middleware`

### T3b: 消息收发 + 历史 + 轮询

- [ ] 3b.1 写测试: `tests/test_messages.py` — send/list/poll/幂等/分页/去重/status 流转
- [ ] 3b.2 跑失败: 预期 FAIL
- [ ] 3b.3 实现: `app/routers/messages.py` (send/list/poll), `app/service.py` (转发+落库逻辑)
- [ ] 3b.4 跑通过: pytest 全绿
- [ ] 3b.5 commit: `feat(api): T3b messages send/list/poll`

### T3c: 图片 + 转人工 + 推荐

- [ ] 3c.1 写测试: `tests/test_media_transfer.py` — image 大小/MIME/防穿越/占位文本、transfer 去重、suggestions
- [ ] 3c.2 跑失败: 预期 FAIL
- [ ] 3c.3 实现: `app/routers/messages.py` 扩展 image/transfer, `app/routers/suggestions.py`, `uploads/` 处理
- [ ] 3c.4 跑通过: pytest 全绿
- [ ] 3c.5 commit: `feat(api): T3c image + transfer + suggestions`

### T4: 小程序前端（WXML/WXSS/JS）

- [ ] 4.1 写测试: `shenwei-home-mini/tests/` 或 `scripts/check_mini.py` — 文件存在性 + 关键选择器/接口调用检查
- [ ] 4.2 跑失败: 预期 FAIL
- [ ] 4.3 实现: `shenwei-home-mini/app.{js,json,wxss}` + `pages/chat/*` + `components/{hero,suggest-card,msg-bubble,input-bar,emoji-panel,image-preview}`
- [ ] 4.4 跑通过: 检查脚本 PASS + `design/preview.html` 视觉对齐
- [ ] 4.5 commit: `feat(mini): T4 chat UI — hero + bubbles + input + emoji + image`

### T5: 联调打通 + E2E 自测

- [ ] 5.1 写 E2E 脚本: `shenwei-home-api/scripts/e2e.py` — login→send→callback模拟→poll→list→image→transfer 全链路
- [ ] 5.2 跑失败(无后端): 预期 FAIL
- [ ] 5.3 实现/联调: 本地模拟 callback 脚本，无公网亦可跑通；`CHANNEL_ENABLED` 开关验证
- [ ] 5.4 跑通过: E2E 全绿 + `verify_connection.py` 真实链路可选
- [ ] 5.5 commit: `test: T5 E2E full chain`

## Self-Review

- [ ] 每项 AC 有对应 Task: AC1→T4, AC2a/b→T3b+T5, AC3→T3c, AC4→T3c, AC5→T3b, AC6→T2, AC7→T1+T2, AC8→T5
- [ ] 无 TBD/TODO 占位符: grep 检查
- [ ] 所有文件路径精确存在或合理新建: `shenwei-home-api/app/*`, `shenwei-home-mini/pages/chat/*`

