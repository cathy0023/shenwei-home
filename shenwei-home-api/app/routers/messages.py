"""消息收发 API（T3b/T3c 逐步补全；list 先行支撑鉴权链路验证）。"""
from fastapi import APIRouter

from ..deps import current_openid

router = APIRouter(tags=["messages"])


@router.get("/api/messages/list")
async def list_messages(openid: str = current_openid):
    return {"items": [], "next_cursor": "", "has_more": False}
