"""小程序登录：code → openid（jscode2session / mock），签发 Bearer token。"""
import logging

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..auth import create_session, mock_openid
from .. import config as config_mod

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")  # 协议 Additive-Only 同款宽容

    code: str = Field(min_length=1, max_length=256)


@router.post("/api/auth/login")
async def login(body: LoginRequest):
    openid = await _code_to_openid(body.code)
    token = create_session(openid)
    return {"token": token, "openid": openid}


async def _code_to_openid(code: str) -> str:
    """微信凭证为空 → mock 模式（仅开发期）；否则走 jscode2session。"""
    if config_mod.config.wx_mock_mode:
        return mock_openid(code)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.weixin.qq.com/sns/jscode2session",
                params={
                    "appid": config_mod.config.wx_mini_appid,
                    "secret": config_mod.config.wx_mini_secret,
                    "js_code": code,
                    "grant_type": "authorization_code",
                })
        data = resp.json()
    except Exception:
        logger.exception("jscode2session 请求失败")
        raise HTTPException(status_code=502, detail="wx_upstream_error")
    if "openid" not in data:
        # errcode/errmsg 见微信文档；统一 401 不暴露细节
        logger.warning("jscode2session 失败: errcode=%s", data.get("errcode"))
        raise HTTPException(status_code=401, detail="wx_code_invalid")
    return data["openid"]
