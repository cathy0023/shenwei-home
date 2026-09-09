"""T3a: 登录 + Bearer 鉴权 — token 签发 / 过期 / mock 边界 / 未授权拒绝。"""
import os
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SHM_SQLITE_PATH", str(tmp_path / "t.db"))
    monkeypatch.delenv("WX_MINI_APPID", raising=False)
    monkeypatch.delenv("WX_MINI_SECRET", raising=False)
    from app.main import create_app

    return TestClient(create_app())


def _fresh_app(tmp_path, monkeypatch):
    monkeypatch.setenv("SHM_SQLITE_PATH", str(tmp_path / "t2.db"))
    from app.main import create_app

    return TestClient(create_app())


def test_login_mock_mode_returns_token(client):
    """WX_MINI_* 为空 → mock openid（mock_<code>），签发 token。"""
    resp = client.post("/api/auth/login", json={"code": "abc123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["openid"] == "mock_abc123"
    assert len(body["token"]) >= 32


def test_login_rejects_empty_code(client):
    resp = client.post("/api/auth/login", json={"code": ""})
    assert resp.status_code == 422


def test_bearer_required(client):
    resp = client.get("/api/messages/list")
    assert resp.status_code == 401
    resp2 = client.get("/api/messages/list", headers={"Authorization": "Bearer wrong"})
    assert resp2.status_code == 401


def test_bearer_accepts_valid_token(client):
    login = client.post("/api/auth/login", json={"code": "u1"}).json()
    resp = client.get(
        "/api/messages/list", headers={"Authorization": f"Bearer {login['token']}"})
    assert resp.status_code == 200


def test_expired_token_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("SHM_SQLITE_PATH", str(tmp_path / "t3.db"))
    import dataclasses

    from app import config as config_mod

    zero_ttl = dataclasses.replace(config_mod.config, session_ttl_days=0)  # 立即过期
    monkeypatch.setattr(config_mod, "config", zero_ttl)
    from app.main import create_app

    c = TestClient(create_app())
    login = c.post("/api/auth/login", json={"code": "u9"}).json()
    # TTL=0 天 → expires_at == created_at，resolve 时已过
    resp = c.get("/api/messages/list", headers={"Authorization": f"Bearer {login['token']}"})
    assert resp.status_code == 401
