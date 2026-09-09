"""小程序登录与鉴权（T3a 实现完整逻辑，T1 先挂空路由保证 import 闭环）。"""
from fastapi import APIRouter

router = APIRouter(tags=["auth"])
