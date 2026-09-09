"""T1: /health 健康检查 — DB 可连 + 配置完整性。"""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SHM_SQLITE_PATH", ":memory:")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SHM_SQLITE_PATH", str(tmp_path / "test.db"))
    from app.main import create_app

    app = create_app()
    return TestClient(app)


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"


def test_health_reports_missing_config(client, monkeypatch):
    """渠道凭证缺失时 health 仍 200，但 config 段标记缺失项。

    config 为 import 时冻结的 dataclass 单例（跨测试会残留其他用例写入的
    环境值），frozen 不可原地改；用 dataclasses.replace 派生缺失凭证的新
    实例并临时替换模块引用（不可变更新范式）。
    """
    import dataclasses

    from app import config as config_mod

    missing_cfg = dataclasses.replace(
        config_mod.config, channel_app_key="", channel_app_secret="")
    monkeypatch.setattr(config_mod, "config", missing_cfg)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "CHANNEL_APP_KEY" in body["config_missing"]


def test_db_tables_created(client):
    """4 张表 + WAL 初始化即建好。"""
    from app.db import get_conn

    conn = get_conn()
    names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"sessions", "messages", "deliveries", "nonces"} <= names
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
