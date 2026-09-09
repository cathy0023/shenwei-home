"""外部 callback 接收：验签（3 头）+ challenge 回显 + delivery 落库去重。

协议 2.2/2.3/5.2：外部推送只带 Timestamp/Nonce/Signature 三头（无 App-Key），
用本端 app_secret 验签；challenge 需 200 原样回显；delivery_id 幂等去重。
"""
import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, Request

from ..config import config
from ..db import execute_write, get_conn, now_ms

logger = logging.getLogger(__name__)
router = APIRouter(tags=["external"])

TIMESTAMP_TOLERANCE_S = 300
NONCE_WINDOW_MS = 5 * 60 * 1000


def _verify(request: Request, body: bytes) -> tuple[bool, str]:
    """验签三步：timestamp 窗口 → nonce 去重 → HMAC 对比。返回 (ok, reason)。"""
    ts = request.headers.get("X-Channel-Timestamp", "")
    nonce = request.headers.get("X-Channel-Nonce", "")
    signature = request.headers.get("X-Channel-Signature", "")
    if not ts or not nonce or not signature:
        return False, "missing_headers"
    if not ts.isdigit() or abs(int(time.time()) - int(ts)) > TIMESTAMP_TOLERANCE_S:
        return False, "timestamp_skew"
    expected = hmac.new(
        config.channel_app_secret.encode(),
        f"{ts}\n{nonce}\n{hashlib.sha256(body).hexdigest()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False, "bad_signature"
    with execute_write() as conn:
        conn.execute("DELETE FROM nonces WHERE expire_at < ?", (now_ms(),))
        try:
            conn.execute(
                "INSERT INTO nonces (nonce, expire_at) VALUES (?, ?)",
                (nonce, now_ms() + NONCE_WINDOW_MS))
        except Exception:
            return False, "nonce_replayed"
    return True, ""


@router.post("/api/external/callback")
async def external_callback(request: Request):
    body = await request.body()
    ok, reason = _verify(request, body)
    if not ok:
        return _error(reason)

    try:
        data = json.loads(body)
    except Exception:
        return _error("invalid_json")

    # challenge：200 原样回显
    if data.get("type") == "im_channel_challenge":
        return {"challenge": data.get("challenge")}

    delivery = _normalize_delivery(data)
    if delivery is None:
        # 未知/不完整载荷：记录但仍 ack（Additive-Only，不中断外部重试风暴）
        logger.warning("callback 未知载荷: keys=%s", sorted(data.keys()))
        return {"ack": True}

    with execute_write() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO deliveries "
            "(delivery_id, kind, conversation_key, external_user_id, msg_type, content, payload, status, created_at, acked_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'acked', ?, ?)",
            (delivery["delivery_id"], delivery["kind"], delivery["conversation_key"],
             delivery["external_user_id"], delivery["msg_type"],
             json.dumps(delivery["content"], ensure_ascii=False),
             json.dumps(data, ensure_ascii=False),
             delivery["created_at"], now_ms()))
    return {"ack": True}


def _normalize_delivery(data: dict) -> dict | None:
    """未知 kind 仍接受（记录 warn 交由调用方）；缺关键字段视为不可投递。"""
    delivery_id = data.get("delivery_id")
    kind = data.get("kind", "")
    if not delivery_id or not kind:
        return None
    if kind not in ("ai_reply", "boss_reply"):
        logger.warning("callback 未知 kind=%s delivery_id=%s（仍 ack）", kind, delivery_id)
    return {
        "delivery_id": delivery_id,
        "kind": kind,
        "conversation_key": data.get("conversation_key", ""),
        "external_user_id": data.get("external_user_id", ""),
        "msg_type": data.get("msg_type", "text"),
        "content": data.get("content", {}),
        "created_at": data.get("created_at", now_ms()),
    }


def _error(reason: str):
    from fastapi.responses import JSONResponse
    status = 401 if reason in ("missing_headers", "timestamp_skew", "bad_signature", "nonce_replayed") else 400
    return JSONResponse({"error_code": reason, "message": reason}, status_code=status)
