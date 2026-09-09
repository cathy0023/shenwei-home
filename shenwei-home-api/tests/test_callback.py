"""T2: callback 接收 — challenge / nonce 防重放 / HMAC 验签 / 去重 / 未知 kind。"""
import hashlib
import hmac as hmac_mod
import json
import os
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
SECRET = "test_secret"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SHM_SQLITE_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("CHANNEL_APP_KEY", "test_key")
    monkeypatch.setenv("CHANNEL_APP_SECRET", SECRET)
    from app.main import create_app

    return TestClient(create_app())


def signed_headers(body: bytes, nonce: str = "n1", ts: str | None = None) -> dict:
    ts = ts or str(int(time.time()))
    sig = hmac_mod.new(
        SECRET.encode(),
        f"{ts}\n{nonce}\n{hashlib.sha256(body).hexdigest()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return {"X-Channel-Timestamp": ts, "X-Channel-Nonce": nonce, "X-Channel-Signature": sig}


def test_challenge_echo(client):
    body = json.dumps({"type": "im_channel_challenge", "challenge": "abc123"}).encode()
    resp = client.post("/api/external/callback", content=body, headers=signed_headers(body))
    assert resp.status_code == 200
    assert resp.json() == {"challenge": "abc123"}


def test_push_delivery_ok_and_dedup(client):
    body = json.dumps({
        "delivery_id": "dlv-1", "kind": "ai_reply", "conversation_key": "c1",
        "external_user_id": "u1", "msg_type": "text",
        "content": {"content": "您好"}, "created_at": int(time.time() * 1000),
    }).encode()
    resp = client.post("/api/external/callback", content=body, headers=signed_headers(body, nonce="a1"))
    assert resp.status_code == 200
    assert resp.json() == {"ack": True}

    # 同 delivery_id 重放 → 仍 ack:true 但不重复落库
    body2 = json.dumps({**json.loads(body), "content": {"content": "改过的"}}).encode()
    resp2 = client.post("/api/external/callback", content=body2, headers=signed_headers(body2, nonce="a2"))
    assert resp2.json() == {"ack": True}

    from app.db import get_conn
    n = get_conn().execute("SELECT COUNT(*) c FROM deliveries WHERE delivery_id='dlv-1'").fetchone()["c"]
    assert n == 1


def test_bad_signature_rejected(client):
    resp = client.post("/api/external/callback", content=b"{}", headers={
        "X-Channel-Timestamp": str(int(time.time())),
        "X-Channel-Nonce": "nx",
        "X-Channel-Signature": "deadbeef",
    })
    assert resp.status_code == 401


def test_stale_timestamp_rejected(client):
    body = b"{}"
    old_ts = str(int(time.time()) - 400)  # 超出 ±300s
    resp = client.post("/api/external/callback", content=body, headers=signed_headers(body, ts=old_ts))
    assert resp.status_code == 401


def test_nonce_replay_rejected(client):
    body = b"{}"
    h = signed_headers(body, nonce="same_nonce")
    r1 = client.post("/api/external/callback", content=body, headers=h)
    assert r1.status_code == 200
    r2 = client.post("/api/external/callback", content=body, headers=h)
    assert r2.status_code == 401


def test_unknown_kind_still_acked(client):
    body = json.dumps({
        "delivery_id": "dlv-x", "kind": "future_kind", "conversation_key": "c1",
        "external_user_id": "u1", "msg_type": "text",
        "content": {"content": "?"}, "created_at": int(time.time() * 1000),
    }).encode()
    resp = client.post("/api/external/callback", content=body, headers=signed_headers(body, nonce="u1"))
    assert resp.status_code == 200
    assert resp.json() == {"ack": True}
