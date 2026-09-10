"""list 历史合并 deliveries：刷新后 AI 回复可见 + 分页跨两表一致。"""
import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import dataclasses

    from app import config as config_mod
    from app import db as db_mod

    # 替换 config 单例（含 sqlite_path）并重置 DB 连接，保证用例级隔离
    test_cfg = dataclasses.replace(
        config_mod.config,
        channel_enabled=False,
        sqlite_path=str(tmp_path / "t.db"))
    monkeypatch.setattr(config_mod, "config", test_cfg)
    db_mod.reset_for_tests()
    from app.main import create_app

    c = TestClient(create_app())
    login = c.post("/api/auth/login", json={"code": "u1"}).json()
    c.headers.update({"Authorization": f"Bearer {login['token']}"})
    return c


def _push_reply(conn, delivery_id, text, ts):
    conn.execute(
        "INSERT INTO deliveries (delivery_id, kind, conversation_key, external_user_id,"
        " msg_type, content, payload, status, created_at, acked_at)"
        " VALUES (?, 'ai_reply', 'mock_u1', 'mock_u1', 'text', ?, '{}', 'acked', ?, ?)",
        (delivery_id, json.dumps({"content": text}), ts, ts))


def test_history_contains_ai_replies(client):
    """刷新场景：user 消息与 AI 回复按时间交错完整返回。"""
    from app.db import execute_write, get_conn, now_ms

    client.post("/api/messages/send", json={"content": "q1"})
    client.post("/api/messages/send", json={"content": "q2"})
    q2_ts = get_conn().execute(
        "SELECT created_at FROM messages WHERE content LIKE '%q2%'").fetchone()["created_at"]
    # 回复时间戳取 q2 落库之后（真实时序：回复总在消息后）
    with execute_write() as conn:
        _push_reply(conn, "dlv-r1", "回复1", q2_ts + 500)
        _push_reply(conn, "dlv-r2", "回复2", q2_ts + 1000)

    items = client.get("/api/messages/list").json()["items"]
    # list 返回 DESC（最新在前）；时间序 = q1, q2, 回复1, 回复2
    texts = [i["content"].get("content") for i in items]
    roles = [i["role"] for i in items]
    assert texts == ["回复2", "回复1", "q2", "q1"]
    assert roles == ["assistant", "assistant", "user", "user"]


def test_history_pagination_across_tables(client):
    """分页游标在 deliveries 上也能锚定，两表联合分页不重不漏。"""
    from app.db import execute_write, get_conn, now_ms

    client.post("/api/messages/send", json={"content": "q1"})
    client.post("/api/messages/send", json={"content": "q2"})
    q2_ts = get_conn().execute(
        "SELECT created_at FROM messages WHERE content LIKE '%q2%'").fetchone()["created_at"]
    with execute_write() as conn:
        _push_reply(conn, "dlv-a", "回复A", q2_ts + 1000)
        _push_reply(conn, "dlv-b", "回复B", q2_ts + 2000)
        _push_reply(conn, "dlv-c", "回复C", q2_ts + 3000)

    page1 = client.get("/api/messages/list?limit=2").json()
    # 时间序: q1, q2, 回复A, 回复B, 回复C → DESC 前2 = 回复C, 回复B
    texts1 = [i["content"]["content"] for i in page1["items"]]
    assert texts1 == ["回复C", "回复B"]
    assert page1["has_more"] is True

    page2 = client.get(
        f"/api/messages/list?limit=2&cursor={page1['next_cursor']}").json()
    texts2 = [i["content"]["content"] for i in page2["items"]]
    assert texts2 == ["回复A", "q2"]
    assert not ({i["id"] for i in page1["items"]} & {i["id"] for i in page2["items"]})

    page3 = client.get(
        f"/api/messages/list?limit=2&cursor={page2['next_cursor']}").json()
    assert [i["content"]["content"] for i in page3["items"]] == ["q1"]
    assert page3["has_more"] is False
