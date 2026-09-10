"""图片链路（我们侧）：签名媒体端点 + 外发载荷 media_url + 接收 image 透传。"""
import hashlib
import hmac as hmac_mod
import io
import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SECRET = "media_test_secret"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import dataclasses

    from app import config as config_mod
    from app import db as db_mod

    test_cfg = dataclasses.replace(
        config_mod.config,
        channel_enabled=False,
        sqlite_path=str(tmp_path / "t.db"),
        uploads_dir=str(tmp_path / "uploads"),
        media_sign_key=SECRET,
        public_base_url="http://testserver",
    )
    monkeypatch.setattr(config_mod, "config", test_cfg)
    db_mod.reset_for_tests()
    from app.main import create_app

    c = TestClient(create_app())
    login = c.post("/api/auth/login", json={"code": "u1"}).json()
    c.headers.update({"Authorization": f"Bearer {login['token']}"})
    return c


def _png(size: int = 64) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"0" * size


def _expected_sig(openid: str, name: str, exp: int) -> str:
    return hmac_mod.new(
        SECRET.encode(), f"{openid}/{name}/{exp}".encode(), hashlib.sha256
    ).hexdigest()[:32]


def test_media_endpoint_valid_signature(client):
    """上传后签名 URL 可访问，字节一致。"""
    r = client.post(
        "/api/messages/image",
        files={"file": ("a.png", io.BytesIO(_png()), "image/png")})
    assert r.status_code == 200, r.text
    up = r.json()
    assert up["image_url"].startswith("http://testserver/api/media/")

    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(up["image_url"])
    resp = client.get(f"{parsed.path}?{parsed.query}")
    assert resp.status_code == 200
    assert resp.content == _png()
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_media_endpoint_tampered_signature_410(client):
    up = client.post(
        "/api/messages/image",
        files={"file": ("a.png", io.BytesIO(_png()), "image/png")}).json()
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(up["image_url"])
    qs = parse_qs(parsed.query)
    bad = f"exp={qs['exp'][0]}&sig={'0' * 32}"
    resp = client.get(f"{parsed.path}?{bad}")
    assert resp.status_code == 410


def test_media_endpoint_expired_410(client):
    up = client.post(
        "/api/messages/image",
        files={"file": ("a.png", io.BytesIO(_png()), "image/png")}).json()
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(up["image_url"])
    qs = parse_qs(parsed.query)
    openid, name = parsed.path.split("/")[-2:]
    exp_past = int(time.time()) - 10
    sig = _expected_sig(openid, name, exp_past)
    resp = client.get(f"{parsed.path}?exp={exp_past}&sig={sig}")
    assert resp.status_code == 410


def test_media_endpoint_missing_file_404(client):
    openid, name = "mock_u1", "f" * 32 + ".png"
    exp = int(time.time()) + 3600
    sig = _expected_sig(openid, name, exp)
    resp = client.get(f"/api/media/{openid}/{name}?exp={exp}&sig={sig}")
    assert resp.status_code == 404


def test_media_endpoint_path_traversal_rejected(client):
    exp = int(time.time()) + 3600
    sig = _expected_sig("../evil", "x.png", exp)
    resp = client.get(f"/api/media/..%2Fevil/x.png?exp={exp}&sig={sig}")
    assert resp.status_code in (400, 404, 410)


def test_outbound_payload_carries_media_url(client, monkeypatch):
    """外发 inbox 载荷应含 media_url 结构化字段 + 兜底文本（channel mock 断言）。"""
    import dataclasses

    from app import config as config_mod

    # 打开 channel（fixture 默认关闭会短路转发），捕获转发参数
    enabled_cfg = dataclasses.replace(config_mod.config, channel_enabled=True)
    monkeypatch.setattr(config_mod, "config", enabled_cfg)

    from unittest.mock import patch

    from app import channel_client as cc

    captured = {}

    async def fake_forward(**kwargs):
        captured.update(kwargs)
        return "accepted"

    with patch.object(cc.channel_client, "forward_inbox", side_effect=fake_forward):
        client.post(
            "/api/messages/image",
            files={"file": ("b.png", io.BytesIO(_png()), "image/png")}).json()
    assert captured.get("msg_type") == "text"
    content = captured.get("content", {})
    assert "media_url" in content and content["media_url"].startswith("http")
    assert "[用户发送了图片]" in content.get("content", "")


def test_inbound_image_delivery_passthrough(client):
    """外部推 msg_type=image 投递 → poll/list 均透传 content（含 media_url）。"""
    from app.db import execute_write, now_ms

    raw = {
        "delivery_id": "dlv-img-1", "kind": "ai_reply", "conversation_key": "mock_u1",
        "external_user_id": "mock_u1", "msg_type": "image",
        "content": {"content": "看这张图", "media_url": "https://ext.example.com/pic.png"},
        "created_at": now_ms(),
    }
    with execute_write() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO deliveries (delivery_id, kind, conversation_key, external_user_id,"
            " msg_type, content, payload, status, created_at, acked_at)"
            " VALUES (?, ?, ?, ?, ?, ?, '{}', 'acked', ?, ?)",
            (raw["delivery_id"], raw["kind"], raw["conversation_key"], raw["external_user_id"],
             raw["msg_type"], json.dumps(raw["content"]), raw["created_at"], now_ms()))

    poll_items = client.get("/api/messages/poll").json()["items"]
    hit = [i for i in poll_items if i["id"] == "dlv-img-1"]
    assert hit and hit[0]["msg_type"] == "image"
    assert hit[0]["content"]["media_url"] == "https://ext.example.com/pic.png"

    list_items = client.get("/api/messages/list").json()["items"]
    hit2 = [i for i in list_items if i["id"] == "dlv-img-1"]
    assert hit2 and hit2[0]["content"]["media_url"] == "https://ext.example.com/pic.png"


def test_uploads_static_route_removed(client):
    """公开 /uploads 挂载已移除：裸访问应 404（而非直接读文件）。"""
    resp = client.get("/uploads/mock_u1/whatever.png")
    assert resp.status_code == 404


def test_list_poll_rewrite_image_url_to_signed(client):
    """下发出口（list/poll）必须把库内相对路径重写为签名公网 URL。"""
    client.post(
        "/api/messages/image",
        files={"file": ("a.png", io.BytesIO(_png()), "image/png")}).json()

    list_items = client.get("/api/messages/list").json()["items"]
    imgs = [i for i in list_items if i["msg_type"] == "image"]
    assert imgs, "list 应含图片消息"
    url = imgs[0]["content"]["image_url"]
    assert url.startswith("http://testserver/api/media/"), url
    assert "/uploads/" not in url  # 相对路径绝不能裸下发

    poll_items = client.get("/api/messages/poll").json()["items"]
    imgs_p = [i for i in poll_items if i["msg_type"] == "image"]
    # poll 只下发 system 提示 + 投递；用户图片消息经 list 下发，若出现在 poll 亦应重写
    for i in imgs_p:
        assert i["content"]["image_url"].startswith("http://testserver/api/media/")
