#!/usr/bin/env bash
# 深维之家后端一键部署（demo 级：单进程 uvicorn + TLS 8443）
# 用法（服务器上执行，需 root）:
#   sudo DOMAIN=api.example.com bash deploy.sh
set -euo pipefail

DOMAIN="${DOMAIN:?用法: DOMAIN=api.example.com bash deploy.sh}"
APP_DIR="/opt/shenwei-home-api"
CERT_DIR="/etc/letsencrypt/live/${DOMAIN}"

echo "==> [1/6] 系统依赖（python3-venv + certbot）"
if command -v apt-get >/dev/null; then
  apt-get update -qq && apt-get install -y -qq python3-venv python3-pip certbot >/dev/null
elif command -v yum >/dev/null; then
  yum install -y python3 certbot >/dev/null
else
  echo "仅支持 apt/yum 系统（demo 范围）"; exit 1
fi

echo "==> [2/6] 同步代码到 ${APP_DIR}"
mkdir -p "${APP_DIR}"
# 假设本脚本位于仓库 shenwei-home-api/deploy/ 内（git clone 后原位执行）
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rsync -a --exclude '.venv' --exclude '__pycache__' --exclude '*.db*' \
      --exclude 'uploads/' --exclude '.env' "${SRC_DIR}/" "${APP_DIR}/"

echo "==> [3/6] Python 虚拟环境 + 依赖"
python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install -q -r "${APP_DIR}/requirements.txt"

echo "==> [4/6] TLS 证书（Let's Encrypt DNS-01，未备案域名可用）"
if [ ! -f "${CERT_DIR}/fullchain.pem" ]; then
  echo "交互式签发：certbot 会给你一条 TXT 记录，去 DNS 控制台添加后回车。"
  certbot certonly --manual --preferred-challenges dns \
    -d "${DOMAIN}" --agree-tos --register-unsafely-without-email --no-eff-email
fi

echo "==> [5/6] .env（如不存在则生成模板，需填真实凭证）"
if [ ! -f "${APP_DIR}/.env" ]; then
  cat > "${APP_DIR}/.env" <<EOF
CHANNEL_BASE_URL=https://demo.sop.mgvai.cn
CHANNEL_ENDPOINT_PREFIX=/api/v1/sop/im/external
CHANNEL_APP_KEY=填你的app_key
CHANNEL_APP_SECRET=填你的app_secret
CHANNEL_CALLBACK_URL=https://${DOMAIN}:8443/api/external/callback
WX_MINI_APPID=
WX_MINI_SECRET=
EOF
  chmod 600 "${APP_DIR}/.env"
  echo "!! 请编辑 ${APP_DIR}/.env 填入真实凭证后重新执行本脚本"
  exit 2
fi

echo "==> [6/6] systemd 启动"
sed "s/{{DOMAIN}}/${DOMAIN}/g" "${APP_DIR}/deploy/shenwei-home.service" > /etc/systemd/system/shenwei-home.service
systemctl daemon-reload
systemctl enable --now shenwei-home
sleep 1
systemctl --no-pager status shenwei-home | head -8

echo
echo "✅ 部署完成。回调地址: https://${DOMAIN}:8443/api/external/callback"
echo "   验证: curl https://${DOMAIN}:8443/health"
echo "   续期: 证书 90 天有效，到期前 sudo certbot renew --manual（同样交互式加 TXT）"
