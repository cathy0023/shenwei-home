# 部署（demo 级）

## 前置（一次性，只有你能做）

1. **DNS A 记录**：`api.你的域名` → 服务器公网 IP
2. **云安全组放行**：TCP 8443 入方向
3. 服务器能 SSH、有 root、Python ≥3.10

## 服务器上执行

```bash
# 方式 A：服务器上直接拉仓库
git clone <repo> && cd <repo>/shenwei-home-api
sudo DOMAIN=api.你的域名 bash deploy/deploy.sh
# 脚本第 4 步会给你一条 _acme-challenge TXT 记录，去 DNS 控制台加好再回车
# 第 5 步首次会生成 .env 模板并退出 —— 填入真实 app_key/app_secret 后重跑一次
```

## 验证

```bash
curl https://api.你的域名:8443/health
# 期望: {"status":"ok","db":"ok","config_missing":[]}
```

## 给外部服务方

回调地址：`https://api.你的域名:8443/api/external/callback`
（对方在 IM 频道管理页写入该实例的 callback_url，然后触发 challenge——我们端点自动回显，无需人工）

## 证书续期

90 天手动一次：`sudo certbot renew --manual`（同样加 TXT 记录）。demo 够用；
若 DNS 服务商有 API（阿里云/Cloudflare），可换对应 certbot 插件实现全自动，后续再升级。
