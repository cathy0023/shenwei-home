#!/usr/bin/env python3
"""T5 端到端自测：login → send → callback(本地模拟) → poll → list → image → transfer。

前置：后端已启动（uvicorn app.main:app --port 8200），CHANNEL_ENABLED=false
（不外发，外部回复用本地模拟 callback 注入）。
用法：python3 scripts/e2e.py [base_url]
"""
import hashlib
import hmac
import io
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(f"  {'✅' if cond else '❌'} {msg}")
    if not cond:
        FAILURES.append(msg)


def req(base: str, path: str, *, method: str = "GET", data=None,
        token: str = "", raw: bytes | None = None, headers: dict | None = None):
    url = f"{base}{path}"
    body = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
    r = urllib.request.Request(url, data=body, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def signed(secret: str, body: bytes, nonce: str) -> dict:
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(),
                   f"{ts}\n{nonce}\n{hashlib.sha256(body).hexdigest()}".encode(),
                   hashlib.sha256).hexdigest()
    return {"X-Channel-Timestamp": ts, "X-Channel-Nonce": nonce, "X-Channel-Signature": sig}


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8200"
    secret = os.environ.get("CHANNEL_APP_SECRET", "")
    if not secret:  # 从 .env 读取（与 config.py 同规则）
        for line in (BASE / ".env").read_text().splitlines():
            if line.startswith("CHANNEL_APP_SECRET="):
                secret = line.split("=", 1)[1].strip()

    print("== 1. health ==")
    status, body = req(base, "/health")
    check(status == 200, f"/health 200 (got {status})")

    print("== 2. login ==")
    status, body = req(base, "/api/auth/login", method="POST", data={"code": "e2e-user"})
    check(status == 200, "login 200")
    token = json.loads(body)["token"]

    print("== 3. send text ==")
    status, body = req(base, "/api/messages/send", method="POST",
                       data={"content": "E2E 测试消息"}, token=token)
    check(status == 200, "send 200")
    send_res = json.loads(body)

    print("== 4. simulate callback (ai_reply) ==")
    delivery = {"delivery_id": f"dlv-e2e-{secrets.token_hex(4)}", "kind": "ai_reply",
                "conversation_key": "mock_e2e-user", "external_user_id": "mock_e2e-user",
                "msg_type": "text", "content": {"content": "E2E 回复"},
                "created_at": int(time.time() * 1000)}
    raw = json.dumps(delivery).encode()
    status, body = req(base, "/api/external/callback", method="POST", raw=raw,
                       headers=signed(secret, raw, secrets.token_hex(8)))
    check(status == 200 and json.loads(body) == {"ack": True}, "callback ack")

    print("== 5. poll receives reply ==")
    status, body = req(base, "/api/messages/poll", token=token)
    items = json.loads(body)["items"]
    check(any(i["content"].get("content") == "E2E 回复" for i in items),
          "poll 拉到 ai_reply")

    print("== 6. list pagination ==")
    status, body = req(base, "/api/messages/list?limit=50", token=token)
    listed = json.loads(body)
    check(status == 200 and any(i["role"] == "user" for i in listed["items"]),
          "list 含用户消息")

    print("== 7. image upload ==")
    boundary = f"----e2e{secrets.token_hex(4)}"
    part = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\";"
        f" filename=\"t.png\"\r\nContent-Type: image/png\r\n\r\n").encode() + PNG + f"\r\n--{boundary}--\r\n".encode()
    status, body = req(base, "/api/messages/image", method="POST", raw=part, token=token,
                       headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    check(status == 200, f"image upload 200 (got {status})")
    image_url = json.loads(body).get("image_url", "")
    status, body = req(base, image_url)
    check(status == 200 and body.startswith(b"\x89PNG"), "image 回读 200")

    print("== 8. transfer ==")
    status, body = req(base, "/api/messages/transfer", method="POST", data={}, token=token)
    check(status == 200, "transfer 200")

    print("== 9. callback dedup ==")
    raw2 = json.dumps(delivery).encode()
    status, body = req(base, "/api/external/callback", method="POST", raw=raw2,
                       headers=signed(secret, raw2, secrets.token_hex(8)))
    check(status == 200 and json.loads(body) == {"ack": True}, "重复 delivery 仍 ack")

    print()
    if FAILURES:
        print(f"E2E FAIL: {len(FAILURES)} 项未通过")
        return 1
    print("E2E PASS: 全链路 9 步通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
