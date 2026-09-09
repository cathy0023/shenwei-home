"""FastAPI 依赖：Bearer token → openid；无效一律 401（不区分过期/伪造）。"""
import logging

from fastapi import Depends, HTTPException, Request

from .auth import resolve_openid

logger = logging.getLogger(__name__)


def _extract_bearer(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[len("Bearer "):].strip()
    return ""


def verify_token(request: Request) -> str:
    """所有小程序侧消息 API 共用的鉴权依赖，返回 openid。"""
    token = _extract_bearer(request)
    if not token:
        raise HTTPException(status_code=401, detail="missing_token")
    openid = resolve_openid(token)
    if not openid:
        raise HTTPException(status_code=401, detail="invalid_token")
    return openid


current_openid = Depends(verify_token)
