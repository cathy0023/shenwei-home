"""消息业务逻辑：落库 → 转发外部 inbox → status 流转（pending/accepted/failed）。

全部 async：转发走异步 channel_client；SQLite 写由全局锁串行化。
"""
import asyncio
import json
import logging
import uuid

from .channel_client import UpstreamError, channel_client
from . import config as config_mod
from .db import execute_write, get_conn, now_ms

logger = logging.getLogger(__name__)

IMAGE_PLACEHOLDER = "[用户发送了图片]"
MAX_CONTENT_LEN = 2000
LIST_DEFAULT_LIMIT = 20
LIST_MAX_LIMIT = 50


def insert_message(*, conversation_key: str, external_user_id: str, role: str,
                   msg_type: str, content: dict, status: str = "pending",
                   external_msg_id: str | None = None) -> dict:
    """落库一条消息（external_msg_id 首次生成，重试复用）。"""
    mid = str(uuid.uuid4())
    emid = external_msg_id or str(uuid.uuid4())
    ts = now_ms()
    with execute_write() as conn:
        conn.execute(
            "INSERT INTO messages (id, conversation_key, external_user_id, external_msg_id,"
            " role, msg_type, content, status, occurred_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mid, conversation_key, external_user_id, emid, role, msg_type,
             json.dumps(content, ensure_ascii=False), status, ts, ts))
    return {"id": mid, "external_msg_id": emid, "created_at": ts}


def update_message_status(external_msg_id: str, status: str) -> None:
    with execute_write() as conn:
        conn.execute(
            "UPDATE messages SET status = ? WHERE external_msg_id = ?",
            (status, external_msg_id))


async def send_user_message(*, openid: str, content: str) -> dict:
    """文字消息：落库 pending → 转发 → accepted/failed（channel 关闭仅落库）。"""
    if not content or len(content) > MAX_CONTENT_LEN:
        raise ValueError("invalid_content")
    row = insert_message(
        conversation_key=openid, external_user_id=openid,
        role="user", msg_type="text", content={"content": content})
    status = await _forward(
        external_msg_id=row["external_msg_id"], conversation_key=openid,
        external_user_id=openid, msg_type="text", content={"content": content})
    update_message_status(row["external_msg_id"], status)
    row["status"] = status
    return row


async def send_user_image(*, openid: str, image_url: str) -> dict:
    """图片消息：图片 URL 落库展示；外部只收占位文本。"""
    row = insert_message(
        conversation_key=openid, external_user_id=openid,
        role="user", msg_type="image", content={"image_url": image_url})
    status = await _forward(
        external_msg_id=row["external_msg_id"], conversation_key=openid,
        external_user_id=openid, msg_type="text",
        content={"content": IMAGE_PLACEHOLDER})
    update_message_status(row["external_msg_id"], status)
    row["status"] = status
    return row


async def transfer_to_human(*, openid: str, event_type: str) -> dict:
    """转人工：event 进外部 inbox + 本地 system 提示。"""
    row = insert_message(
        conversation_key=openid, external_user_id=openid,
        role="user", msg_type="event",
        content={"event_type": event_type})
    status = await _forward(
        external_msg_id=row["external_msg_id"], conversation_key=openid,
        external_user_id=openid, msg_type="event",
        content={"event_type": event_type})
    update_message_status(row["external_msg_id"], status)
    tip = insert_message(
        conversation_key=openid, external_user_id=openid,
        role="system", msg_type="event",
        content={"content": "已为您转接人工客服，请稍候…"}, status="accepted")
    return {"status": status, "tip_id": tip["id"]}


async def _forward(**kwargs) -> str:
    """转发 inbox；channel 关闭视为 accepted（AC8 降级）；异常转 failed 不抛出。"""
    if not config_mod.config.channel_enabled:
        return "accepted"
    try:
        result = await channel_client.forward_inbox(**kwargs)
        return "accepted" if result in ("accepted", "duplicated") else "failed"
    except (UpstreamError, asyncio.TimeoutError) as exc:
        logger.error("inbox 转发失败 external_msg_id=%s err=%s",
                     kwargs.get("external_msg_id"), exc)
        return "failed"


def list_messages(*, openid: str, cursor: str | None, limit: int | None) -> dict:
    """游标分页（created_at DESC, id DESC）；cursor 为上一页最后 id。"""
    if limit is None:
        limit = LIST_DEFAULT_LIMIT
    limit = max(1, min(limit, LIST_MAX_LIMIT))
    params: list = [openid]
    where = "conversation_key = ?"
    if cursor:
        row = get_conn().execute(
            "SELECT created_at FROM messages WHERE id = ? AND conversation_key = ?",
            (cursor, openid)).fetchone()
        if row is None:
            raise ValueError("invalid_cursor")
        where += " AND (created_at < ? OR (created_at = ? AND id < ?))"
        params += [row["created_at"], row["created_at"], cursor]
    rows = get_conn().execute(
        f"SELECT id, role, msg_type, content, status, created_at FROM messages "
        f"WHERE {where} ORDER BY created_at DESC, id DESC LIMIT ?",
        (*params, limit + 1)).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [_row_to_item(r) for r in rows]
    return {
        "items": items,
        "next_cursor": rows[-1]["id"] if rows and has_more else "",
        "has_more": has_more,
    }


def poll_messages(*, openid: str, since: int | None, limit: int | None) -> dict:
    """增量拉新（messages + deliveries 按 created_at ASC）；since 为上次 max(created_at)。"""
    if limit is None:
        limit = LIST_DEFAULT_LIMIT
    limit = max(1, min(limit, LIST_MAX_LIMIT))
    if since is not None and since < 0:
        raise ValueError("invalid_since")

    msg_rows = get_conn().execute(
        "SELECT id, role, msg_type, content, status, created_at FROM messages "
        "WHERE conversation_key = ? AND created_at > ? "
        "ORDER BY created_at ASC, id ASC LIMIT ?",
        (openid, since or 0, limit)).fetchall()
    dlv_rows = get_conn().execute(
        "SELECT delivery_id, kind, msg_type, content, created_at FROM deliveries "
        "WHERE conversation_key = ? AND created_at > ? "
        "ORDER BY created_at ASC LIMIT ?",
        (openid, since or 0, limit)).fetchall()

    items = [_row_to_item(r) for r in msg_rows]
    for r in dlv_rows:
        items.append({
            "id": r["delivery_id"],
            "role": "assistant",
            "kind": r["kind"],
            "msg_type": r["msg_type"],
            "content": json.loads(r["content"]),
            "created_at": r["created_at"],
        })
    items.sort(key=lambda i: i["created_at"])
    items = items[:limit]
    max_ts = max((i["created_at"] for i in items), default=since or 0)
    return {"items": items, "next_since": max_ts, "has_more": len(items) == limit}


def _row_to_item(r) -> dict:
    return {
        "id": r["id"],
        "role": r["role"],
        "msg_type": r["msg_type"],
        "content": json.loads(r["content"]),
        "status": r["status"],
        "created_at": r["created_at"],
    }
