"""消息 API：send / list / poll / image / transfer。"""
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .. import config as config_mod
from ..deps import current_openid
from ..service import (
    LIST_MAX_LIMIT,
    list_messages,
    poll_messages,
    send_user_image,
    send_user_message,
    transfer_to_human,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["messages"])

IMAGE_MAX_BYTES = 10 * 1024 * 1024
IMAGE_MIME_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


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


@router.post("/api/messages/image")
async def upload_image(file: UploadFile, request: Request,
                       openid: str = current_openid):
    """图片上传：≤10MB、MIME 白名单、UUID 文件名防穿越；占位文本进 inbox。"""
    ext = IMAGE_MIME_EXT.get(file.content_type or "")
    if ext is None:
        return JSONResponse({"error_code": "media_format_unsupported",
                             "message": "unsupported image format"}, status_code=415)
    data = await file.read()
    if len(data) > IMAGE_MAX_BYTES:
        return JSONResponse({"error_code": "media_too_large",
                             "message": "image exceeds 10MB"}, status_code=413)

    uploads = Path(config_mod.config.uploads_dir) / openid
    try:
        uploads.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}{ext}"
        (uploads / name).write_bytes(data)
    except OSError:
        logger.exception("图片落盘失败 openid=%s", openid)
        return JSONResponse({"error_code": "storage_unavailable",
                             "message": "cannot write upload"}, status_code=507)

    # 目录现已在磁盘上：补挂载静态路由（幂等）
    request.app.state.mount_uploads(request.app)

    image_url = f"/uploads/{openid}/{name}"
    row = await send_user_image(openid=openid, image_url=image_url)
    return {"id": row["id"], "msg_type": "image", "image_url": image_url,
            "status": row["status"], "created_at": row["created_at"]}


@router.post("/api/messages/transfer")
async def transfer(openid: str = current_openid):
    """转人工：event 进外部 inbox（event_type 可配）+ 本地 system 提示。"""
    result = await transfer_to_human(
        openid=openid, event_type=config_mod.config.transfer_event_type)
    return result
