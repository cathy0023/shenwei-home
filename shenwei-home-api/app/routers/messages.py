"""消息 API：send / list / poll / image / transfer（image、transfer 由 T3c 填充 image 端点）。"""
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .. import config as config_mod
from ..deps import current_openid
from ..service import (
    LIST_MAX_LIMIT,
    list_messages,
    poll_messages,
    send_user_message,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["messages"])


class SendRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str = Field(min_length=1, max_length=2000)
    msg_type: str = Field(default="text", pattern="^(text)$")


@router.post("/api/messages/send")
async def send(body: SendRequest, openid: str = current_openid):
    try:
        row = await send_user_message(openid=openid, content=body.content)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_content")
    except Exception:
        logger.exception("send 内部异常 openid=%s", openid)
        return JSONResponse({"error_code": "internal", "message": "internal error"},
                            status_code=500)
    return {"id": row["id"], "status": row["status"], "created_at": row["created_at"]}


@router.get("/api/messages/list")
async def list_msg(cursor: str = "", limit: int | None = None,
                   openid: str = current_openid):
    if limit is not None and (limit < 1 or limit > LIST_MAX_LIMIT):
        raise HTTPException(status_code=400, detail="invalid_limit")
    try:
        return list_messages(openid=openid, cursor=cursor or None, limit=limit)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_cursor")


@router.get("/api/messages/poll")
async def poll(since: int | None = None, limit: int | None = None,
               openid: str = current_openid):
    if since is not None and since < 0:
        raise HTTPException(status_code=400, detail="invalid_since")
    if limit is not None and (limit < 1 or limit > LIST_MAX_LIMIT):
        raise HTTPException(status_code=400, detail="invalid_limit")
    try:
        return poll_messages(openid=openid, since=since, limit=limit)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_since")
