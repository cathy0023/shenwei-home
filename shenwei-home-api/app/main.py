"""shenwei-home-api 入口。

启动: uvicorn app.main:app --host 127.0.0.1 --port 8200 --reload
"""
import logging
from fastapi import FastAPI

from . import config as config_mod
from .db import get_conn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app() -> FastAPI:
    app = FastAPI(title="shenwei-home-api", version="0.1.0")

    @app.get("/health")
    def health():
        """深度检查：DB 可连 + 配置完整性（缺失项可见，不阻塞启动）。

        经 config_mod 间接引用，测试替换 app.config.config 单例即生效。
        """
        body: dict = {"status": "ok", "db": "ok", "config_missing": []}
        try:
            get_conn().execute("SELECT 1").fetchone()
        except Exception as exc:  # pragma: no cover - 防御式
            body["db"] = f"error: {exc}"
            body["status"] = "degraded"
        body["config_missing"] = config_mod.config.validate()
        return body

    from .routers.callback import router as callback_router
    from .routers.auth import router as auth_router
    from .routers.messages import router as messages_router
    from .routers.suggestions import router as suggestions_router

    app.include_router(callback_router)
    app.include_router(auth_router)
    app.include_router(messages_router)
    app.include_router(suggestions_router)

    # uploads 静态托管（图片回显）；目录不存在则跳过（首张上传时自建）
    from pathlib import Path

    from starlette.staticfiles import StaticFiles

    uploads = Path(config_mod.config.uploads_dir)
    if uploads.is_dir():
        app.mount("/uploads", StaticFiles(directory=str(uploads)), name="uploads")
    app.state.mount_uploads = _ensure_uploads_mount  # 延迟挂载钩子（见下）
    return app


def _ensure_uploads_mount(app: FastAPI) -> None:
    """uploads 目录在首图落盘后才存在；路由层上传后调用此钩子补挂载。"""
    from pathlib import Path

    from starlette.staticfiles import StaticFiles

    uploads = Path(config_mod.config.uploads_dir)
    already = any(getattr(r, "path", "") == "/uploads" for r in app.router.routes)
    if uploads.is_dir() and not already:
        app.mount("/uploads", StaticFiles(directory=str(uploads)), name="uploads")


app = create_app()
