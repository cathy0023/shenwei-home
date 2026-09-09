#!/usr/bin/env python3
"""连通性验证脚本：按协议 v1 实测外部智能回复服务两条链路。

1. POST /inbox  —— 推一条测试消息（期望逐条 accepted）
2. GET /deliveries —— 拉 AI 回复投递（期望 200 + deliveries/cursor）

签名算法（协议 2.2）：
    签名串    = timestamp + "\\n" + nonce + "\\n" + SHA256_HEX(body)
    signature = HMAC_SHA256(app_secret, 签名串).hex().lower()

用法：python3 scripts/verify_connection.py
"""
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def load_env() -> dict:
    env = {}
    for line in (BASE / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def signed_headers(secret: str, body: bytes) -> dict:
    ts = str(int(time.time()))
    nonce = secrets.token_hex(16)
    signing_string = f"{ts}\n{nonce}\n{hashlib.sha256(body).hexdigest()}"
    sig = hmac.new(secret.encode(), signing_string.encode(), hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Channel-App-Key": os.environ["CHANNEL_APP_KEY"],
        "X-Channel-Timestamp": ts,
        "X-Channel-Nonce": nonce,
        "X-Channel-Signature": sig,
    }


def request(url: str, headers: dict, body: bytes | None, method: str) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode()
            try:
                return resp.status, json.loads(data)
            except json.JSONDecodeError:
                return resp.status, data
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]
    except urllib.error.URLError as e:
        return -1, f"connection error: {e.reason}"


def main() -> int:
    env = load_env()
    os.environ.update(env)
    required = ["CHANNEL_BASE_URL", "CHANNEL_ENDPOINT_PREFIX", "CHANNEL_APP_KEY", "CHANNEL_APP_SECRET"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"FAIL: .env 缺少配置项: {missing}")
        return 1

    base_url = os.environ["CHANNEL_BASE_URL"].rstrip("/")
    prefix = os.environ["CHANNEL_ENDPOINT_PREFIX"]
    secret = os.environ["CHANNEL_APP_SECRET"]

    # --- 1. inbox 入站：推一条 AI 可直答的测试消息 ---
    now_ms = int(time.time() * 1000)
    inbox_body = json.dumps(
        {
            "messages": [
                {
                    "external_msg_id": f"verify_{now_ms}",
                    "conversation_key": "shenwei_verify_conn",
                    "external_user_id": "verify_user",
                    "msg_type": "text",
                    "content": {"content": "你好，这是一条链路验证测试消息"},
                    "occurred_at": now_ms,
                    "raw": {"source": "verify_connection.py"},
                }
            ]
        }
    ).encode()
    status, resp = request(
        f"{base_url}{prefix}/inbox", signed_headers(secret, inbox_body), inbox_body, "POST"
    )
    print(f"[inbox]    POST {base_url}{prefix}/inbox -> HTTP {status}")
    print(f"[inbox]    {json.dumps(resp, ensure_ascii=False)[:400]}")
    inbox_ok = status == 200

    # --- 2. deliveries 拉取：看投递队列形状 ---
    status2, resp2 = request(
        f"{base_url}{prefix}/deliveries?limit=10", signed_headers(secret, b""), None, "GET"
    )
    print(f"[pull]     GET  {base_url}{prefix}/deliveries?limit=10 -> HTTP {status2}")
    if isinstance(resp2, dict):
        n = len(resp2.get("deliveries", []))
        print(f"[pull]     {n} 条待消费投递, cursor={'有' if resp2.get('cursor') else '空'}")
        for d in resp2.get("deliveries", [])[:3]:
            print(
                f"[pull]     - {d.get('delivery_id')} kind={d.get('kind')} "
                f"status={d.get('status')} content={json.dumps(d.get('content'), ensure_ascii=False)[:80]}"
            )
    else:
        print(f"[pull]     {str(resp2)[:300]}")
    pull_ok = status2 == 200

    print()
    if inbox_ok and pull_ok:
        print("PASS: 入站 + 拉取两条链路签名与连通均验证通过，凭证可用")
        return 0
    print(f"FAIL: inbox_ok={inbox_ok} pull_ok={pull_ok}，按上方 HTTP 状态码与错误体排查")
    return 1


if __name__ == "__main__":
    sys.exit(main())
