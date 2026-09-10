"""消息业务逻辑：落库 → 转发外部 inbox → status 流转（pending/accepted/failed）。

全部 async：转发走异步 channel_client；SQLite 写由全局锁串行化。
"""
import asyncio
import json
import logging
import uuid

import httpx

from .channel_client import UpstreamError, channel_client
from . import config as config_mod
from .db import execute_write, get_conn, now_ms

logger = logging.getLogger(__name__)

IMAGE_PLACEHOLDER = "[用户发送了图片]"
MAX_CONTENT_LEN = 2000
LIST_DEFAULT_LIMIT = 20
LIST_MAX_LIMIT = 50
SEND_FORWARD_TIMEOUT_S = 25.0  # 请求路径内联转发的总超时（wx.request 默认 60s 内返回）


def _egress_content(openid: str, content: dict) -> dict:
    """下发出口：库内相对路径 image_url → 签名公网 URL（spec §4 出口单点拼装）。"""
    url = content.get("image_url")
    if url and url.startswith("/uploads/"):
        from .media import sign_media_url

        content = {**content, "image_url": sign_media_url(openid, url.rstrip("/").split("/")[-1])}
    return content


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


async def send_user_image(*, openid: str, name: str, media_url: str) -> dict:
    """图片消息：相对路径落库展示；外部收「兜底文本 + media_url 结构化字段」。

    media_url 为签名公网 URL（spec 2026-09-10 §3.1），外部按协议 4.2 voice
    先例下载（他们不认字段时，文本里的 URL 仍可正则提取——双保险）。
    """
    rel = f"/uploads/{openid}/{name}"
    row = insert_message(
        conversation_key=openid, external_user_id=openid,
        role="user", msg_type="image", content={"image_url": rel})
    status = await _forward(
        external_msg_id=row["external_msg_id"], conversation_key=openid,
        external_user_id=openid, msg_type="text",
        content={"content": f"{IMAGE_PLACEHOLDER} {media_url}",
                 "media_url": media_url})
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
    """转发 inbox；channel 关闭视为 accepted（AC8 降级）；异常转 failed 不抛出。

    请求路径内联转发但设总超时（SEND_FORWARD_TIMEOUT_S），防止外部 5xx
    退避（最长 21min）挂死用户请求；超时按 failed 落库，前端可重试。
    """
    if not config_mod.config.channel_enabled:
        return "accepted"
    try:
        result = await asyncio.wait_for(
            channel_client.forward_inbox(**kwargs), timeout=SEND_FORWARD_TIMEOUT_S)
        return "accepted" if result in ("accepted", "duplicated") else "failed"
    except (UpstreamError, asyncio.TimeoutError, httpx.HTTPError) as exc:
        logger.error("inbox 转发失败 external_msg_id=%s err=%s",
                     kwargs.get("external_msg_id"), exc)
        return "failed"


def list_messages(*, openid: str, cursor: str | None, limit: int | None) -> dict:
    """游标分页（created_at DESC, id DESC）；cursor 为上一页最后 id。

    历史视图 = messages（user/system）∪ deliveries（assistant 回复）按时间
    归并——外部回复只落 deliveries，不合并则刷新后历史里没有 AI 侧内容。
    """
    if limit is None:
        limit = LIST_DEFAULT_LIMIT
    limit = max(1, min(limit, LIST_MAX_LIMIT))
    conn = get_conn()

    msg_cond, msg_params = "", []
    dlv_cond, dlv_params = "", []
    if cursor:
        m = conn.execute(
            "SELECT created_at FROM messages WHERE id = ? AND conversation_key = ?",
            (cursor, openid)).fetchone()
        d = conn.execute(
            "SELECT created_at FROM deliveries WHERE delivery_id = ? AND conversation_key = ?",
            (cursor, openid)).fetchone()
        if m is None and d is None:
            raise ValueError("invalid_cursor")
        if m is not None:
            msg_cond = "AND (created_at < ? OR (created_at = ? AND id < ?))"
            msg_params = [m["created_at"], m["created_at"], cursor]
            dlv_cond, dlv_params = "AND created_at <= ?", [m["created_at"]]
        else:
            msg_cond, msg_params = "AND created_at <= ?", [d["created_at"]]
            dlv_cond = "AND (created_at < ? OR (created_at = ? AND delivery_id < ?))"
            dlv_params = [d["created_at"], d["created_at"], cursor]

    msg_rows = conn.execute(
        f"SELECT id, role, msg_type, content, status, created_at FROM messages "
        f"WHERE conversation_key = ? {msg_cond} "
        f"ORDER BY created_at DESC, id DESC LIMIT ?",
        (openid, *msg_params, limit + 1)).fetchall()
    dlv_rows = conn.execute(
        "SELECT delivery_id AS id, 'assistant' AS role, kind, msg_type, content, '' AS status, created_at "
        f"FROM deliveries WHERE conversation_key = ? {dlv_cond} "
        "ORDER BY created_at DESC, delivery_id DESC LIMIT ?",
        (openid, *dlv_params, limit + 1)).fetchall()

    merged = sorted(
        [_row_to_item(r) for r in msg_rows] + [_delivery_to_item(r) for r in dlv_rows],
        key=lambda i: (i["created_at"], i["id"]),
        reverse=True)
    # 出口转换：相对路径 image_url → 签名公网 URL（spec §4）
    merged = [{**i, "content": _egress_content(openid, i["content"])} if i["msg_type"] == "image" else i
              for i in merged]
    has_more = len(merged) > limit
    page = merged[:limit]
    return {
        "items": page,
        "next_cursor": page[-1]["id"] if page and has_more else "",
        "has_more": has_more,
    }


def _delivery_to_item(r) -> dict:
    return {
        "id": r["id"],
        "role": r["role"],
        "kind": r["kind"],  # ai_reply | boss_reply，前端据此渲染人工/AI 样式
        "msg_type": r["msg_type"],
        "content": json.loads(r["content"]),
        "status": r["status"] or "accepted",
        "created_at": r["created_at"],
    }


def poll_messages(*, openid: str, since: int | None, limit: int | None) -> dict:
    """增量拉新（deliveries + 本地 system 提示，按 created_at ASC）；since 为上次 max(created_at)。

    RFC 5.4 语义：poll 只下发外部投递 + system 提示，不含用户自己的消息
    （用户消息由 send 响应确认，避免前端 temp 气泡与轮询重复）。
    """
    if limit is None:
        limit = LIST_DEFAULT_LIMIT
    limit = max(1, min(limit, LIST_MAX_LIMIT))
    if since is not None and since < 0:
        raise ValueError("invalid_since")

    msg_rows = get_conn().execute(
        "SELECT id, role, msg_type, content, status, created_at FROM messages "
        "WHERE conversation_key = ? AND role = 'system' AND created_at > ? "
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
    # 出口转换：相对路径 image_url → 签名公网 URL（spec §4）
    items = [{**i, "content": _egress_content(openid, i["content"])} if i["msg_type"] == "image" else i
             for i in items]
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
