"""SQLite 落库：sessions/messages/deliveries/nonces，WAL + 线程锁串行写。"""
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from . import config as config_mod

_mutex = threading.Lock()
_conn: sqlite3.Connection | None = None
_conn_key: str | None = None  # 当前连接对应的 sqlite_path（测试替换单例后自动重建）


def write_lock() -> threading.Lock:
    """进程级全局写锁：所有写操作共用，避免同一连接并发写。"""
    return _mutex


@contextmanager
def execute_write():
    """写操作上下文：统一持全局写锁，退出自动提交；异常自动回滚。"""
    with _mutex:
        conn = get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def reset_for_tests() -> None:
    """测试专用：关闭并丢弃缓存连接，使新 sqlite_path 生效（隔离各用例 DB）。"""
    global _conn, _conn_key
    with _mutex:
        if _conn is not None:
            _conn.close()
        _conn = None
        _conn_key = None


def get_conn() -> sqlite3.Connection:
    global _conn, _conn_key
    path = config_mod.config.sqlite_path
    if _conn is not None and _conn_key != path:
        # 配置被测试替换（dataclasses.replace）→ 旧连接作废
        _conn.close()
        _conn = None
    if _conn is None:
        _conn_key = path
        p = Path(path)
        if str(p) != ":memory:":
            p.parent.mkdir(parents=True, exist_ok=True)
        # FastAPI/Starlette 跨线程访问（TestClient 亦然），并发写由全局 _mutex 串行化
        _conn = sqlite3.connect(str(p), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.execute("PRAGMA busy_timeout=5000")
        _init_schema(_conn)
    return _conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token       TEXT PRIMARY KEY,
            openid      TEXT NOT NULL,
            created_at  INTEGER NOT NULL,
            expires_at  INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_openid ON sessions(openid);

        CREATE TABLE IF NOT EXISTS messages (
            id               TEXT PRIMARY KEY,
            conversation_key TEXT NOT NULL,
            external_user_id TEXT NOT NULL,
            external_msg_id  TEXT NOT NULL UNIQUE,
            role             TEXT NOT NULL,
            msg_type         TEXT NOT NULL,
            content          TEXT NOT NULL,
            status           TEXT NOT NULL DEFAULT 'pending',
            occurred_at      INTEGER NOT NULL,
            created_at       INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_conv_created
            ON messages(conversation_key, created_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_messages_external_user
            ON messages(external_user_id, occurred_at DESC);

        CREATE TABLE IF NOT EXISTS deliveries (
            delivery_id      TEXT PRIMARY KEY,
            kind             TEXT NOT NULL,
            conversation_key TEXT NOT NULL,
            external_user_id TEXT NOT NULL,
            msg_type         TEXT NOT NULL,
            content          TEXT NOT NULL,
            payload          TEXT,
            status           TEXT NOT NULL DEFAULT 'acked',
            created_at       INTEGER NOT NULL,
            acked_at         INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_deliveries_conv_created
            ON deliveries(conversation_key, created_at ASC);

        CREATE TABLE IF NOT EXISTS nonces (
            nonce     TEXT PRIMARY KEY,
            expire_at INTEGER NOT NULL
        );
        """
    )
    conn.commit()


def now_ms() -> int:
    return int(time.time() * 1000)


def cleanup_expired_nonces() -> None:
    """清理过窗 nonce（每次 callback 鉴权顺带修剪）。"""
    with execute_write() as conn:
        conn.execute("DELETE FROM nonces WHERE expire_at < ?", (now_ms(),))
