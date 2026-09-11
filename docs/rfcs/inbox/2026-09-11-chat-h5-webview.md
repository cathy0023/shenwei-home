---
title: chat 页 H5 化（React + web-view 嵌入）
created: 2026-09-11
source: brainstorm
status: inbox
---

# chat 页 H5 化（React + web-view 嵌入）

## 背景

- **来源**：用户 2026-09-11 提出。客户侧小程序的客服页面形态是 **webview 套 H5**；为对齐该架构，将现有小程序原生 chat 页能力用 React 在 H5 项目中重新实现，H5 部署到与后端相同的域名（`xdf.nonoai.com.cn`），小程序原生 chat 页改为 web-view 壳指向该页面。
- **现状**：
  - 小程序原生 chat 页能力齐全（生产验证）：文字/表情/图片发送（压缩+签名 URL）、历史拉取（游标分页）、轮询收 AI/人工回复、转人工、人工/AI 角标区分、图片失败占位；
  - 后端 FastAPI 部署于 `https://xdf.nonoai.com.cn`（nginx → uvicorn:8200），API 前缀 `/api/*`；
  - 鉴权链路：小程序 `wx.login` → code → 后端 `jscode2session` 换 openid → Bearer token（7 天）；
  - 仓库：`github.com/cathy0023/shenwei-home`（shenwei-home-api + shenwei-home-mini 同仓）；
  - 设计基线：`shenwei-home-mini/design/preview.html`（青色系视觉 + 纯 CSS 机器人吉祥物）。
- **痛点**：客户侧客服形态为 webview+H5；原生页与客户架构不一致，未来能力迭代需要双端维护。

## 目标（用户视角）

- 让用户在小程序内通过 web-view 打开 H5 聊天页，获得与原生页完全对齐的客服体验；
- 让「我的」个人页（对齐客户侧个人中心形态）承载登录态，点「联系客服」进入客服 H5；
- 让 H5 与后端同域部署（`/h5/` 子路径），无 CORS、无新域名成本；
- 让前后端 + H5 三者同仓管理、同流程推送 GitHub。

## 范围

### 在范围内（In Scope）

**1. React H5 项目（`shenwei-home-h5/`，新目录同仓）**
- Vite + React + TypeScript 脚手架（工程范式参考 `rpa-demo-web-wecom-sidebar`）；
- 聊天页完整对齐原生页能力：文字/表情盘/图片（压缩+预览+失败占位）、历史分页拉取、轮询收回复、转人工（chip + 提示）、人工/AI 区分（右上角「人工」金标 + 人形头像徽章）、图片签名 URL 展示（本会话 tmp / 历史 URL 策略同原生页最终方案）；
- 视觉：移植 `design/preview.html` CSS 设计变量（青色系/圆角/渐变/纯 CSS 机器人 hero），不引 UI 组件库；
- 身份：从 URL query 读 token（`/h5/?token=xxx`），无 token 时显示错误态提示；
- API 基址：同域相对路径 `/api/*`（无 CORS）。

**2. 小程序壳改造（`shenwei-home-mini/`）**
- 新增「我的」个人页（pages/mine）：对齐客户侧个人中心形态（头像区 + 菜单列表），静默登录持 token；菜单含「联系客服」入口；
- chat 原生页改造：跳转 `web-view` 页面，src = `https://xdf.nonoai.com.cn/h5/?token=<token>`；
- 原生 chat 页保留（不删），作为 web-view 不可用时的回退与开发参照。

**3. 部署（`xdf.nonoai.com.cn/h5/`）**
- nginx 新增 location：`/h5/` → H5 构建产物静态目录；
- Vite `base: '/h5/'`；构建产物 rsync 至服务器（复用现有部署脚本模式）。

### 不在范围内（Non-Goals）

- SSE 实时推送（spec 已备，H5 首版沿用轮询，后续独立迭代）；
- 语音消息、客服坐席工作台、管理后台；
- 正式发布所需的业务域名配置/备案（开发/测试阶段不阻塞；发布前需：企业主体业务域名配置 + 校验文件部署 + ICP 备案确认）；
- H5 独立 SEO/分享能力（web-view 内无意义）。

## 约束

- **web-view 硬约束**：小程序为企业/组织主体（已确认 ✓）；开发/测试阶段无需业务域名配置（真机开发版有「继续访问」豁免）；正式发布前必须完成业务域名 + 备案；
- **身份桥接**：H5 无法调用 `wx.login`，token 由小程序壳经 web-view src query 传入（7 天有效期，HTTPS 传输；泄露面可控）；token 失效时 H5 显示「请从小程序重新进入」错误态（H5 无法自行续期）；
- **同域部署**：H5 与 API 同域，nginx 同一 server 块；`/h5/` 与 `/api/*` 路径互斥不冲突；
- React H5 的 API 契约与原生页完全一致（后端零改动）；
- 项目位置：仓库根 `shenwei-home-h5/`，与 api/mini 平级，同仓推送 GitHub。

## 已讨论的方案

### 方案 A：React + Vite + 原生 CSS 移植设计变量（已选 ✓，并采纳 C 的工程范式）

- **核心思路**：Vite+React+TS 脚手架（工程配置参考 rpa-demo-web-wecom-sidebar 同形态项目），视觉层移植 `design/preview.html` 的 CSS 设计变量与纯 CSS 机器人，不引 UI 组件库。
- **优点**：与原生页视觉 1:1（同一套 CSS 变量）；零组件库依赖包小（web-view 首屏敏感）；preview.html 样式可大量复用。
- **缺点**：复杂交互组件需手写（聊天页场景少）。
- **工作量**：中（约 2-3 天含部署联调）。

### 方案 B：React + Ant Design Mobile / TDesign 组件库

- **优点**：输入栏/弹层组件现成规范。
- **缺点**：主题定制成本高（视觉难对齐现有设计）；包体积 +200KB 拖慢 web-view 首屏。
- **驳回理由**：视觉对齐成本反超自写，包体积劣化首屏。

### 方案 C：仅参考 rpa-demo-web-wecom-sidebar 工程范式（并入 A）

- **优点**：Vite 配置/部署脚本有已验证范式。
- **缺点**：业务代码无复用价值（企微侧边栏 ≠ 聊天页）。
- **处置**：不作为独立方案，其工程范式并入方案 A 执行。

### 身份桥接子方案（已选 ✓）

- 小程序壳「我的」页静默登录持 token → 点「联系客服」→ web-view src 带 `?token=`；H5 读 query 用 token 调 API。后端零改动。
- 驳回备选：postMessage 传递（仅特定时机投递，不可靠）；H5 独立身份（跨端会话割裂，不符客服场景）。

### 部署子方案（已选 ✓）

- 同域子路径 `/h5/`：nginx location + Vite `base:'/h5/'`；同域无 CORS、零新域名成本。
- 驳回备选：FastAPI StaticFiles 托管（发版耦合）；独立子域（新域名+证书+业务域名多配一条）。

## 成功标准

- [ ] H5 聊天页在浏览器直接打开（带 token）可完整聊天：发文字/表情/图片、收 AI 回复、转人工、人工金标、历史分页、图片显示与失败占位；
- [ ] 小程序「我的」页 →「联系客服」→ web-view 打开 H5，身份直通（能看到自己的历史会话）；
- [ ] H5 视觉与 design/preview.html 设计基线一致（青色系/机器人/气泡样式）；
- [ ] `https://xdf.nonoai.com.cn/h5/` 生产可访问，同域调 `/api/*` 无 CORS 报错；
- [ ] 三端（api/mini/h5）同仓推送 GitHub，H5 有独立构建脚本与部署文档；
- [ ] 真机（开发版）web-view 内聊天全链路可用。

## 待解决问题

- web-view 真机首次打开未配置业务域名时的「继续访问」豁免入口在 iOS/Android 微信版本间的表现差异（真机联调确认）；
- token 失效窗口内的 H5 体验（是否给「返回小程序重进」引导按钮——`wx.miniProgram.navigateBack` 可用性确认）；
- H5 在 web-view 内的 viewport/安全区适配（iOS 底部 home indicator）细节；
- 「我的」个人页的信息架构裁剪（客户侧有积分/订单等，本期仅头像+联系客服+设置占位？需产品确认最小形态）；
- 发布前清单（业务域名配置/校验文件/备案）归档为发布阶段任务，开发期不阻塞。

