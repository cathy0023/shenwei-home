"""会话 token：32B 随机 hex，存 sessions 表，TTL 默认 7 天。"""
import secrets
import sqlite3

from . import config as config_mod
from .db import execute_write, get_conn, now_ms

_TOKEN_BYTES = 32


def create_session(openid: str) -> str:
    """签发新 token 并落库（不删除旧 token：多设备并存）。"""
    token = secrets.token_hex(_TOKEN_BYTES)
    ttl_ms = config_mod.config.session_ttl_days * 24 * 3600 * 1000
    with execute_write() as conn:
        conn.execute(
            "INSERT INTO sessions (token, openid, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, openid, now_ms(), now_ms() + ttl_ms))
    return token


def resolve_openid(token: str) -> str | None:
    """按 token 查有效会话；过期视为无效。"""
    row: sqlite3.Row | None = get_conn().execute(
        "SELECT openid FROM sessions WHERE token = ? AND expires_at > ?",
        (token, now_ms())).fetchone()
    return row["openid"] if row else None


def mock_openid(code: str) -> str:
    """开发期 mock 身份（WX_MINI_* 为空时）；格式固定 mock_<code>。"""
    return f"mock_{code}"
