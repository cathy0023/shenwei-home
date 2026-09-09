"""T3c: 图片上传 / 转人工 / 推荐问题。"""
import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SHM_SQLITE_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("SHM_UPLOADS_DIR", str(tmp_path / "uploads"))
    import dataclasses

    from app import config as config_mod

    test_cfg = dataclasses.replace(config_mod.config, channel_enabled=False)
    monkeypatch.setattr(config_mod, "config", test_cfg)
    from app.main import create_app

    c = TestClient(create_app())
    login = c.post("/api/auth/login", json={"code": "u1"}).json()
    c.headers.update({"Authorization": f"Bearer {login['token']}"})
    return c


def _png(size: int = 100) -> bytes:
    # 最小 PNG 头（非真图即可过 MIME 校验：按 content-type/扩展名白名单）
    return b"\x89PNG\r\n\x1a\n" + b"0" * size


def test_image_upload_ok(client):
    resp = client.post(
        "/api/messages/image",
        files={"file": ("a.png", io.BytesIO(_png()), "image/png")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["msg_type"] == "image"
    assert body["image_url"].startswith("/uploads/")
    # 落库可见
    items = client.get("/api/messages/list").json()["items"]
    assert any(i["msg_type"] == "image" for i in items)


def test_image_rejects_bad_mime(client):
    resp = client.post(
        "/api/messages/image",
        files={"file": ("a.txt", io.BytesIO(b"hello"), "text/plain")})
    assert resp.status_code == 415


def test_image_rejects_too_large(client, monkeypatch):
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024 + 1)
    resp = client.post(
        "/api/messages/image",
        files={"file": ("big.png", io.BytesIO(big), "image/png")})
    assert resp.status_code in (413, 422)


def test_image_served_back(client):
    up = client.post(
        "/api/messages/image",
        files={"file": ("a.png", io.BytesIO(_png()), "image/png")}).json()
    static = client.get(up["image_url"])
    assert static.status_code == 200
    assert static.content.startswith(b"\x89PNG")


def test_transfer_inserts_system_tip(client):
    resp = client.post("/api/messages/transfer")
    assert resp.status_code == 200
    items = client.get("/api/messages/list").json()["items"]
    roles = [i["role"] for i in items]
    assert "system" in roles
    tips = [i["content"].get("content", "") for i in items if i["role"] == "system"]
    assert any("转接人工" in t for t in tips)


def test_suggestions_endpoint(client, monkeypatch):
    """suggestions 无需鉴权，返回非空列表。"""
    c = TestClient(client.app)
    resp = c.get("/api/suggestions")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["items"], list) and len(body["items"]) >= 3
