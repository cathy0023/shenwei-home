"""推荐问题：首期硬编码 + 内存缓存（内容来源待产品提供，见 RFC Open Questions）。"""
from fastapi import APIRouter

router = APIRouter(tags=["suggestions"])

_SUGGESTIONS = [
    "会员积分充错账户了怎么办？",
    "怎么创建家庭组？",
    "积分兑换的优惠券在哪里查看？",
]


@router.get("/api/suggestions")
async def suggestions():
    return {"items": list(_SUGGESTIONS)}
