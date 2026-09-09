# 企微侧边栏话术助手 · 实现全记录与踩坑指南

> 2026-09-03 全链路打通。本文是完整复盘：实现步骤、踩过的每一个坑（现象/根因/解法）、以及**会话存档链路（本次未打通）的预期实现方案**。
>
> 代码位置：后端 `rpa-demo-api`（分支 `feat/wecom-sidebar-assistant`），前端 `rpa-demo-web`（同名分支），生产 `https://wecom.nonoai.com.cn/sidebar.html`（47.89.150.106，systemd 服务 `wecom-sidebar`）。

---

## 一、最终形态（架构总览）

```
企微客户端(客户单聊侧边栏)                FastAPI(rpa-demo-api) @ 47.89.150.106
┌───────────────────────┐              ┌────────────────────────────────────┐
│ sidebar.html (React)  │              │ nginx 443(wecom.nonoai.com.cn)     │
│                       │              │   └─ 反代 127.0.0.1:8000 uvicorn   │
│ 1 OAuth2 跳转拿 code  │─────────────→│ /api/v1/wecom/sidebar/sign  双签名 │
│ 2 wx.config(企业鉴权) │              │        /login  code→userid+cookie  │
│ 3 agentConfig(应用)   │              │        /profile 画像(含缓存)       │
│ 4 getCurExternalContact│             │        /history  历史降级[]        │
│ 5 画像+生成话术        │─────────────│        /generate 话术(MiniMax-M3)  │
│ 6 复制粘贴发客户       │              │                                    │
└───────────────────────┘              │ [未打通] msgaudit 同步任务(开关关)  │
                                       └────────────────────────────────────┘
```

鉴权双轨制（企微的底层设计，理解了它一半的坑都能自解）：

| 轨道 | 鉴权接口 | ticket 端点 | 用途 |
|---|---|---|---|
| 企业身份 | `wx.config` | `/cgi-bin/get_jsapi_ticket` | 基础 JSAPI（分享等） |
| 应用身份 | `wx.agentConfig` | `/cgi-bin/ticket/get?type=agent_config` | 会话属性接口（getCurExternalContact） |
| 员工身份 | OAuth2 网页授权 | `open.weixin.qq.com/connect/oauth2/authorize`（snsapi_base 静默） | code → `/cgi-bin/auth/getuserinfo` 换 userid |

---

## 二、实现步骤（照此可复现）

### 步骤 1：企微管理后台配置（管理员操作，全部前置）

| # | 配置项 | 路径 | 关键点 |
|---|---|---|---|
| 1.1 | 创建自建应用 | 应用管理 → 自建 → 创建 | 记录 CorpID / AgentId / Secret |
| 1.2 | **企业可信IP** | 应用详情 → 开发者接口 → 企业可信IP | 服务器 IP + 开发机出口 IP 都要加；不加报 `60020 not allow to access from your ip` |
| 1.3 | **客户联系 API 授权**（最易漏） | **客户联系 → 底部「可调用接口的应用」→ 添加本应用** | 不加报 `permission denied`（前端）/ `48002 api forbidden`（服务端） |
| 1.4 | 可信域名 | 应用详情 → 网页授权及JS-SDK | 域名须 ICP 备案；下载 `WW_verify_*.txt` 放到站点根（我们放前端 `public/`，构建自动带上）；改完需重启企微客户端 |
| 1.5 | 配置到聊天工具栏 | **客户联系 → 聊天工具栏**（不是「上下游聊天工具栏」） | 页面地址 `https://wecom.nonoai.com.cn/sidebar.html`；上下游是跨企业协作场景，拿不到客户 userid |
| 1.6 | 可见范围 | 应用详情 → 可见范围 | 只勾目标销售部门；成员不在范围内接口也会被拒 |

### 步骤 2：后端（rpa-demo-api，FastAPI）

新增 `app/wecom/` 包：

| 模块 | 职责 |
|---|---|
| `config.py` | `WECOM_*` 环境变量集中读取；`validate_cookie_secret`（corp_id 非空时 cookie_secret 必须 ≥16 位，启动 fail-fast） |
| `token.py` | access_token + 企业/应用双 jsapi_ticket，内存缓存 7200s 提前 300s 刷新 |
| `signature.py` | `sha1(jsapi_ticket=..&noncestr=..&timestamp=..&url=..)`，url 截断 `#` 后内容 |
| `auth.py` | HMAC-SHA256 签名会话 cookie（HttpOnly，2h） |
| `contact.py` | 画像代理 `/cgi-bin/externalcontact/get`（**参数名 `external_userid`**），SQLite 缓存 TTL 10min |
| `msgaudit.py` | 会话存档解密层（RSA-PKCS1v15 + AES-256-CBC 纯函数，可单测）+ C SDK ctypes 封装（当前 Disabled） |
| `sync.py` | 后台同步任务：seq 增量拉取 → 过滤（群聊/非文本/内部会话跳过）→ 幂等落库 → last_seq 断点续拉（当前不启动） |
| `context.py` / `generate.py` | 画像+历史拼 prompt → LLM 生成 1 条话术（exclude 去重） |
| `llm_shared.py` | 从 RPA 的 llm.py 提取的 OpenAI 兼容调用（含思维链响应兼容），原路径零改动 |
| `router.py` / `deps.py` | 5 个端点 + 会话守卫（无 cookie 401 顶层信封） |

5 个端点（信封 `{code:2000, data, message}`）：

```
GET  /api/v1/wecom/sidebar/sign?url=<页面URL>   双签名一次返回
POST /api/v1/wecom/sidebar/login {code}          OAuth code 兑换 userid，Set-Cookie
GET  /api/v1/wecom/sidebar/profile?userid=<ext>  精简画像
GET  /api/v1/wecom/sidebar/history?userid&limit  最近消息（存档未开通返回 []）
POST /api/v1/wecom/sidebar/generate {userid, scenario?, exclude?}
```

新表：`wecom_chat_history`（seq UNIQUE 幂等）、`sync_state`（last_seq）、`wecom_profile_cache`（TTL）。

### 步骤 3：前端（rpa-demo-web，Vite 多页）

- `vite.config.ts`：input 加 `sidebar` 入口；dev proxy `/api → localhost:8000`
- `sidebar.html`：**双 SDK 引入，顺序固定**：
  ```html
  <script src="https://res.wx.qq.com/open/js/jweixin-1.2.0.js"></script>   <!-- 基础: wx.config/ready/error/checkJsApi -->
  <script src="https://res.wx.qq.com/wwopen/js/jwxwork-1.0.0.js"></script> <!-- 企微: agentConfig / wx.qy / wx.invoke -->
  ```
- `src/sidebar/auth.ts` 鉴权链路（顺序敏感）：
  ```
  URL 带 ?code= → 剥离 code(replaceState) → POST /login
  URL 无 code  → 跳 OAuth2(snsapi_base) → 企微 302 回跳带新 code
  → fetchSign → wx.config({beta:true, appId:corp_id, jsApiList 非空})
  → wx.ready → wx.agentConfig({corpid, agentid, jsApiList:['getCurExternalContact']})
  → 等 wx.qy 异步挂载 → wx.invoke('getCurExternalContact') 优先 / wx.qy.* 兜底
  ```
- `Assistant.tsx`：三态 UI（loading/error/ready）；话术卡片 + 复制 + 换一条(exclude) + scenario 输入；4001 自动重登（重跳 OAuth）；15s 前端超时
- `public/WW_verify_*.txt`：企微域名归属验证文件放这里，构建自动带进 dist

### 步骤 4：服务器部署（47.89.150.106，同源形态）

```bash
# 产物：后端代码 + 前端 dist 放同一目录，FastAPI 静态托管(dist 存在才挂载,同源保证 SameSite=Lax cookie 生效)
/opt/wecom-sidebar/
├── app/  requirements.txt  .venv/     # 后端(python3.11 venv——系统 3.6 太老,pydantic2 跑不了)
├── dist/                              # 前端构建产物(sidebar.html + assets + WW_verify)
└── .env                               # WECOM_* + LLM 配置(密钥只在这里)
```

- nginx：`/etc/nginx/conf.d/wecom.conf`，80(acme+301) / 443(ssl + 反代 127.0.0.1:8000，`proxy_buffering off` 保 SSE)；证书 certbot webroot 签发，续期走服务器已有 cron（`certbot renew --post-hook 'nginx -s reload'`）
- systemd：`wecom-sidebar.service`，`EnvironmentFile=/opt/wecom-sidebar/.env`（KEY=VALUE 格式直接兼容），`--workers 2`，enabled 自启
- 更新发布：本地 tar → scp → 服务器解包 → `systemctl restart wecom-sidebar`（前端改动只需换 dist，不用重启）

### 步骤 5：验收链（每步有明确判据）

| # | 验证 | 判据 |
|---|---|---|
| 1 | `curl https://wecom.nonoai.com.cn/healthz` | 200 |
| 2 | `curl .../WW_verify_*.txt` | 200 + 文件内容 |
| 3 | `curl ".../sign?url=..."` | code:2000 + 双签名（此步过=IP 白名单+凭证 OK） |
| 4 | 企微打开侧边栏，地址栏变干净 | OAuth 静默授权 OK（员工身份通） |
| 5 | 企微 debug 模式 alert | `wx.config:ok`（企业鉴权通） |
| 6 | 顶栏出现客户名/标签 | getCurExternalContact OK（客户联系权限+会话属性接口通） |
| 7 | 点生成出话术 | LLM 链路通（全闭环） |

---

## 三、踩坑全记录（8 个坑，按撞上的时间序）

### 坑 1：`wx.config` 参数名 `corpId` ≠ `appId` → 40063

- **现象**：`wx.config:fail some parameters are empty (40063)`
- **根因**：基础 jweixin SDK 的 `wx.config` 参数键是 **`appId`**（值填 corpid）；`corpId`/`agentid` 是 `wx.agentConfig` 的键。传错键 → appId 为空 → 40063
- **解法**：`wx.config({appId: corp_id, ...})`

### 坑 2：`jsApiList` 空数组 → 40063（同一个错误码第二个成因）

- **现象**：改了 appId 仍 40063
- **根因**：`jsApiList` 必须至少声明一个接口，空数组被判为「参数空」
- **解法**：非空列表。经验：开 `debug:true`，企微会 alert 弹出 checkResult，哪个接口注册成功一目了然

### 坑 3：`wx.qy.login` 是小程序专属，H5 根本没有

- **现象**：`undefined is not an object (evaluating 'window.wx.qy.login')`
- **根因**：`wx.qy.login` 仅企微**小程序**可用；H5 拿员工身份的正解是 **OAuth2 网页授权**（snsapi_base 静默，无感授权）。这是 RFC 设计阶段就埋错的假设，mock 测试无法暴露
- **解法**：前端构造 `https://open.weixin.qq.com/connect/oauth2/authorize?appid=CORPID&redirect_uri=...&response_type=code&scope=snsapi_base&state=STATE&agentid=AGENTID#wechat_redirect` 跳转 → 回跳带 `?code=` → 后端 `/cgi-bin/auth/getuserinfo` 兑换 userid → Set-Cookie

### 坑 4：企微专有 SDK 引用 404，`wx.qy` 命名空间不存在

- **现象**：过了 wx.config，`wx.qy.getCurExternalContact` undefined
- **根因**：网传的 `open.work.weixin.qq.com/wwopen/js/jsapi/jweixin-1.1.0.js` **已 404**，第二个 SDK 根本没加载
- **解法**：换 `https://res.wx.qq.com/wwopen/js/jwxwork-1.0.0.js`（200 可用，提供 agentConfig/wx.qy/wx.invoke）。引用前先 `curl -sI` 验 URL 存活

### 坑 5：`wx.qy` 异步挂载时序

- **现象**：SDK 换对了，偶尔仍 undefined
- **根因**：jwxwork 晚于 jweixin 异步挂载；`waitForSdk` 只等 `wx.config` 存在，`wx.qy` 可能还没就绪
- **解法**：单独 `waitForQySdk()` 轮询等 `wx.qy`/`wx.invoke`；调用时 `wx.invoke('getCurExternalContact',...)` 优先、`wx.qy.getCurExternalContact` 兜底

### 坑 6：`getCurExternalContact: permission denied` → 后台没配「客户联系」授权（最大的坑，卡最久）

- **现象**：SDK 链路全通，最后一步 `permission denied`；wx.config 的 checkJsApi 里 `getCurExternalContact:false`
- **根因**：自建应用**默认没有「客户联系」API 家族权限**。需在管理后台 **客户联系 → 底部「可调用接口的应用」→ 添加本应用**。加了之后 checkResult 的 false 与 permission denied 同时消失
- **决定性定位法**（比反复改前端快十倍）：**用同一套凭证在服务端调 `externalcontact/list`，同样报 `48002 api forbidden`** → 双端同根因，实锤是后台配置而非代码
- **教训**：`permission denied` 类错误先用服务端 API 同凭证复现；前端 SDK 报错文案只说明「被拒」，不说「谁拒」

### 坑 7：`externalcontact/get` 参数名是 `external_userid` 不是 `userid` → 40058

- **现象**：`missing field 'external_userid'. invalid Request Parameter`
- **根因**：服务端 API 参数名与直觉不同（`getuserinfo` 用 `code`，`externalcontact/get` 用 `external_userid`）
- **解法**：`params={"access_token":..., "external_userid": userid}`。**注意这是好消息的信号**——能收到 40058 说明权限已生效（否则还是 48002）

### 坑 8：OAuth code 一次性，URL 残留重放 → 40029 invalid code

- **现象**：`POST /login` 间歇性 400，日志呈「两次 400 → 一次 200」抖动
- **根因**：OAuth 回跳后 `?code=xxx` 残留地址栏；企微 WebView 切会话回来页面重载，拿已消费的旧 code 重放。code 5 分钟有效且只能兑换一次
- **解法**：code 消费前立即 `history.replaceState` 剥离；会话过期重登时不再依赖地址栏 code，直接重跳 OAuth 拿新 code

### 环境类坑（快查表）

| 坑 | 信号 | 解法 |
|---|---|---|
| IP 白名单未加 | `60020 not allow to access from your ip` | 后台加出口 IP（服务器+开发机都要）；错误消息里 `from ip:` 直接告诉你该加哪个 |
| 应用 ticket 端点用错 | agentConfig invalid signature | 应用票走 `/cgi-bin/ticket/get?type=agent_config`，企业票走 `/cgi-bin/get_jsapi_ticket`，**两个端点不同** |
| dist 挂载遮蔽 API/healthz | 带前端产物后 healthz 404 | FastAPI `Mount("/")` 按注册顺序匹配，静态挂载必须放在 API 路由与 healthz **之后** |
| 系统 Python 3.6 | pydantic2/fastapi 装不上 | 用 python3.11 建 venv |
| 系统无 rsync | rsync: 未找到命令 | tar + scp 代替 |
| 侧边栏配置不生效 | 改了后台没变化 | **重启企微客户端**（配置和 WebView 都有缓存） |
| 企微 debug 模式 | 看不到 console | 企微内 `Ctrl+Alt+Shift+D` 开调试，页面右键 → 开发者工具 |
| 思维链模型返回空 content | LLM 返回但 content=null | glm 系列把内容放 `reasoning_content`/`thinking_blocks`；llm_shared 已兼容；MiniMax-M3 输出干净 |

---

## 四、会话存档（本次未打通）· 预期实现方案

> **现状**：公司未购买会话存档服务，`WECOM_SID_ENABLED=false`（降级形态）：`/history` 返回空数组，话术仅基于客户画像 + scenario 生成。**功能不残废，但 AI 少了「最近聊了什么」这个最强上下文。**

### 4.1 前提条件（行政先行，技术就绪后接线很快）

1. 企业微信**付费版**，且单独购买「会话存档」服务（按坐席付费）
2. 合规审批通过；需告知员工+客户（外部联系人单聊有「同意存档」提示机制，客户未同意的消息拿不到）
3. 管理后台 → 安全与管理 → 管理工具 → 会话存档 → 开通，配置 **RSA 公钥**

### 4.2 代码现状（已全部预留，开通后只差 3 个配置）

| 组件 | 状态 |
|---|---|
| 解密层 `msgaudit.py` | ✅ 已实现+单测：`decrypt_random_key`（RSA-PKCS1v15 解出 secret_key）+ `decrypt_chat_msg`（AES-256-CBC 解消息体，key=sha256(secret_key)，iv=key[:16]，PKCS7）+ `parse_msg` |
| SDK 封装 | ✅ `CtypesChatArchiveClient`（Init/GetChatData/FreeData/Destroy 官方签名），SDK 路径可配；加载失败自动降级 Disabled 不阻断启动 |
| 同步任务 `sync.py` | ✅ asyncio 后台轮询（默认 5s，批 100）：seq 增量拉取 → 过滤（roomid 非空=群聊跳过、非文本跳过、对端非外部联系人跳过）→ 幂等落库（seq UNIQUE + INSERT OR IGNORE）→ last_seq 断点续拉；解密失败单条跳过+告警，连续失败聚合 |
| 存储表 | ✅ `wecom_chat_history` / `sync_state` 已建 |
| `/history` 端点 | ✅ 开关关时返回 `[]`，开了直接查表返回 |
| C SDK 二进制 | ❌ 需下载 `libWeWorkFinanceSdk_C.so`（Linux）放到服务器 |

### 4.3 开通后的接线步骤（预计半天内完成联调）

```bash
# 1. 生成 RSA 密钥对
openssl genrsa -out msgaudit_private.pem 2048
openssl rsa -in msgaudit_private.pem -pubout -out msgaudit_public.pem
# 公钥内容贴到 管理后台 → 会话存档 → 配置公钥

# 2. 下载官方 C SDK（会话存档开通页提供），上传服务器，例如：
#    /opt/wecom-sidebar/sdk/libWeWorkFinanceSdk_C.so

# 3. 服务器 /opt/wecom-sidebar/.env 追加/修改：
WECOM_SID_ENABLED=true
WECOM_SID_SDK_PATH=/opt/wecom-sidebar/sdk/libWeWorkFinanceSdk_C.so
WECOM_SID_MSGAUDIT_PRIVATE_KEY="<私钥PEM全文,含BEGIN/END行>"

# 4. 重启
systemctl restart wecom-sidebar
# 日志应出现同步任务启动(而非"会话存档同步不启动(降级)")
```

### 4.4 数据流（文字版时序）

```
[启动] lifespan → WECOM_SID_ENABLED=true → 读私钥 → CDLL 加载 SDK → Init(corpid, secret)
[循环] 每 5s: 读 sync_state.last_seq → GetChatData(seq, limit=100)
       → 每条消息: encrypt_random_key --RSA私钥解密--> secret_key
                  encrypt_chat_msg  --AES-256-CBC(secret_key)--> 消息JSON
       → 过滤: roomid 非空(群聊)跳 / msgtype≠text 跳 / 对端非 wo|wm|wp 外部联系人跳
       → INSERT OR IGNORE wecom_chat_history(seq 幂等)
       → UPSERT sync_state.last_seq（断点续拉,重启不丢）
[消费] 侧边栏 /history?userid=外部客户id → 最近 N 条 → 拼 LLM prompt
```

### 4.5 已知限制与风险（写进预期的，不是缺陷）

- **消息留存 5 天**：企微服务端只保留 5 天内的存档数据，同步任务停超过 5 天就有缺口——所以轮询必须常开（systemd Restart=always 已兜住）
- **同意机制**：客户侧未同意存档的单聊消息拿不到（返回里没有）；员工侧需在移动端确认过存档协议
- **媒体消息**：当前只处理文本；图片/文件等跳过（如需要接 media get 接口下载，属后续迭代）
- **内外部判定**：`wo/wm/wp` 前缀启发式 + roomid 判空 + 单对端校验三重判据；若企业自定义了以 wo/wp 开头的内部 userid 会误判（低概率，注释已声明）
- **合规红线**：会话数据仅本地存储用于话术生成上下文，禁止转发/导出/另作他用
- **platform**：SDK 二进制分平台（macOS .dylib / Linux .so），本地跑不了真实 SDK 属预期，单测全部走 mock/自构造密文向量

---

## 五、运维速查

```bash
# 服务状态/日志
ssh -i ~/.ssh/aliyun_openclaw root@47.89.150.106
systemctl status wecom-sidebar
journalctl -u wecom-sidebar -f --no-pager | grep -E "wecom|ERROR"

# 改配置后重启
vi /opt/wecom-sidebar/.env && systemctl restart wecom-sidebar

# 更新后端：本地打包(排除 .venv/.git/.env/db/dist) → scp → 解包 → restart
# 更新前端：pnpm build → tar dist → scp → 解包(无需 restart)

# 降级开关(出问题先关存档链路)
WECOM_SID_ENABLED=false

# LLM 当前配置
# base_url=https://token.mgvai.cn/v1  model=minimax/MiniMax-M3  key=.env 里
```

**待办清理**（链路已稳，下次迭代顺手做）：
- [ ] `auth.ts` 关 `debug:true`（生产不再弹 alert）
- [ ] RFC WECOM-001 补「鉴权实现踩坑记录」（本文档坑 1-8 摘要回填）
- [ ] 企微后台重置 App Secret（聊天中明文出现过），重置后同步改服务器 .env
