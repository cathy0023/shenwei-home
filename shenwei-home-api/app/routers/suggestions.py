"""推荐问题（T3c 实现，T1 先挂空路由保证 import 闭环）。"""
from fastapi import APIRouter

router = APIRouter(tags=["suggestions"])
