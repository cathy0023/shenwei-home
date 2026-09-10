"""媒体签名访问：图片公网 URL 的生成与校验（spec 2026-09-10 §3.2）。

- 库里只存相对路径 uploads/{openid}/{name}；签名 URL 仅在出口（下发前端/外发外部）实时拼装；
- 签名 = HMAC(media_sign_key, "{openid}/{name}/{exp}")[:32]，恒时比较；
- 过期与篡改统一 410（不暴露区分度）；缺失文件 404。
"""
import hashlib
import hmac
import re
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from . import config as config_mod

router = APIRouter(tags=["media"])

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")          # openid 段（无点）
_FILE_RE = re.compile(r"^[A-Za-z0-9_-]+\.(jpg|jpeg|png|webp|gif)$")  # 文件名段（含扩展名）
_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _sign(openid: str, name: str, exp: int) -> str:
    key = config_mod.config.media_sign_key
    return hmac.new(
        key.encode(), f"{openid}/{name}/{exp}".encode(), hashlib.sha256
    ).hexdigest()[:32]


def sign_media_url(openid: str, name: str) -> str:
    """生成带签名+过期的公网媒体 URL（出口单点：下发前端 / 外发外部共用）。"""
    exp = int(time.time()) + config_mod.config.media_url_ttl_days * 86400
    base = config_mod.config.public_base_url.rstrip("/")
    return f"{base}/api/media/{openid}/{name}?exp={exp}&sig={_sign(openid, name, exp)}"


def _deny(reason: str, status: int):
    return JSONResponse({"error_code": reason, "message": reason}, status_code=status)


@router.get("/api/media/{openid}/{name}")
async def get_media(openid: str, name: str, exp: str = "", sig: str = ""):
    # 参数形状校验（防穿越 + 防伪造形状）
    if not _NAME_RE.fullmatch(openid) or not _FILE_RE.fullmatch(name):
        return _deny("invalid_path", 400)
    if not exp.isdigit() or not re.fullmatch(r"[0-9a-f]{32}", sig):
        return _deny("bad_signature", 410)
    exp_i = int(exp)
    if exp_i < int(time.time()):
        return _deny("expired", 410)
    if not hmac.compare_digest(sig, _sign(openid, name, exp_i)):
        return _deny("bad_signature", 410)

    path = Path(config_mod.config.uploads_dir) / openid / name
    if not path.is_file():
        return _deny("not_found", 404)
    media_type = _MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(
        path, media_type=media_type, headers={"X-Content-Type-Options": "nosniff"})
