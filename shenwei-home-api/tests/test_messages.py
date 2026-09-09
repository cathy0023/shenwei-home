"""T3b: 消息 send/list/poll — 幂等 / 分页 / status 流转 / 增量。"""
import json
import os
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SQLITE = sys.modules.get("sqlite3")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SHM_SQLITE_PATH", str(tmp_path / "t.db"))
    import dataclasses

    from app import config as config_mod

    # 渠道关闭：单测不外发；转发逻辑由 test_channel_client 覆盖
    test_cfg = dataclasses.replace(config_mod.config, channel_enabled=False)
    monkeypatch.setattr(config_mod, "config", test_cfg)
    from app.main import create_app

    c = TestClient(create_app())
    login = c.post("/api/auth/login", json={"code": "u1"}).json()
    c.headers.update({"Authorization": f"Bearer {login['token']}"})
    return c


def test_send_text_persists_accepted(client):
    resp = client.post("/api/messages/send", json={"content": "你好"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "accepted"  # channel disabled -> skipped_disabled 视为 accepted
    items = client.get("/api/messages/list").json()["items"]
    assert any(i["content"].get("content") == "你好" and i["role"] == "user" for i in items)


def test_send_validates_content(client):
    assert client.post("/api/messages/send", json={"content": ""}).status_code == 422
    assert client.post("/api/messages/send", json={"content": "x" * 2001}).status_code == 422


def test_list_pagination_cursor(client):
    for i in range(5):
        client.post("/api/messages/send", json={"content": f"m{i}"})
    page1 = client.get("/api/messages/list?limit=2").json()
    assert len(page1["items"]) == 2
    assert page1["has_more"] is True
    assert page1["next_cursor"]
    page2 = client.get(f"/api/messages/list?limit=2&cursor={page1['next_cursor']}").json()
    assert len(page2["items"]) == 2
    ids1 = {i["id"] for i in page1["items"]}
    ids2 = {i["id"] for i in page2["items"]}
    assert not (ids1 & ids2)  # 无重复


def test_list_invalid_cursor_400(client):
    resp = client.get("/api/messages/list?cursor=not-a-uuid")
    assert resp.status_code == 400


def test_poll_incremental(client):
    """callback 落库的 delivery 能被 poll 拉到，且 since 增量不重复。"""
    client.post("/api/messages/send", json={"content": "q1"})
    # 模拟外部推送两条回复
    from app.db import execute_write, now_ms

    with execute_write() as conn:
        for n in ("r1", "r2"):
            conn.execute(
                "INSERT INTO deliveries (delivery_id, kind, conversation_key, external_user_id,"
                " msg_type, content, payload, status, created_at, acked_at)"
                " VALUES (?, 'ai_reply', 'mock_u1', 'mock_u1', 'text', ?, '{}', 'acked', ?, ?)",
                (f"dlv-{n}", json.dumps({"content": f"回复{n}"}), now_ms(), now_ms()))

    p1 = client.get("/api/messages/poll").json()
    texts = [i["content"].get("content") for i in p1["items"]]
    assert "回复r1" in texts and "回复r2" in texts
    assert p1["next_since"]

    p2 = client.get(f"/api/messages/poll?since={p1['next_since']}").json()
    texts2 = [i["content"].get("content") for i in p2["items"]]
    assert "回复r1" not in texts2 and "回复r2" not in texts2


def test_poll_rejects_non_number_since(client):
    # FastAPI 类型层把非整数 since 拦为 422（框架标准语义）
    resp = client.get("/api/messages/poll?since=abc")
    assert resp.status_code == 422
