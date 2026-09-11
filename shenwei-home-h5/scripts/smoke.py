#!/usr/bin/env python3
"""H5 部署冒烟：种子 token 直插 sessions 表 → 验证 H5 页面 + 同域 API。

用法（服务器上）：python3 scripts/smoke.py
前提：后端运行中；脚本以服务器本地 SQLite 直插方式获取 token（wx.login code 微信外不可得）。
"""
import json
import secrets
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://xdf.nonoai.com.cn"
API_DIR = Path(__file__).resolve().parent.parent.parent / "shenwei-home-api"
FAILURES = []


def check(cond, msg):
    print(f"  {'✅' if cond else '❌'} {msg}")
    if not cond:
        FAILURES.append(msg)


def main():
    sys.path.insert(0, str(API_DIR))
    import os
    os.environ.setdefault("SHM_SQLITE_PATH", str(API_DIR / "shenwei_home.db"))
    from app import db as db_mod

    db_mod.reset_for_tests()
    token = secrets.token_hex(32)
    with db_mod.execute_write() as conn:
        conn.execute(
            "INSERT INTO sessions (token, openid, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, "h5_smoke_test", db_mod.now_ms(), db_mod.now_ms() + 86400000))

    print("== 1. H5 页面 ==")
    with urllib.request.urlopen(f"{BASE}/h5/", timeout=10) as r:
        body = r.read().decode()
        check(r.status == 200 and "assets" in body, "H5 index 200 且引用构建资源")

    print("== 2. 同域 API（Bearer = 种子 token）==")
    req = urllib.request.Request(
        f"{BASE}/api/messages/list?limit=5",
        headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
        check(r.status == 200 and "items" in data, "list 200 + items 数组")

    print("== 3. 发消息 + 轮询 ==")
    req = urllib.request.Request(
        f"{BASE}/api/messages/send",
        data=json.dumps({"content": "H5 冒烟测试"}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        check(r.status == 200, "send 200")

    print()
    if FAILURES:
        print(f"SMOKE FAIL: {len(FAILURES)}")
        return 1
    print("SMOKE PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
