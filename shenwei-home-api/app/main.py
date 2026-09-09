"""shenwei-home-api 入口。

启动: uvicorn app.main:app --host 127.0.0.1 --port 8200 --reload
"""
import logging
from fastapi import FastAPI

from .config import config
from .db import get_conn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app() -> FastAPI:
    app = FastAPI(title="shenwei-home-api", version="0.1.0")

    @app.get("/health")
    def health():
        """深度检查：DB 可连 + 配置完整性（缺失项可见，不阻塞启动）。"""
        body: dict = {"status": "ok", "db": "ok", "config_missing": []}
        try:
            get_conn().execute("SELECT 1").fetchone()
        except Exception as exc:  # pragma: no cover - 防御式
            body["db"] = f"error: {exc}"
            body["status"] = "degraded"
        body["config_missing"] = config.validate()
        return body

    from .routers.callback import router as callback_router
    from .routers.auth import router as auth_router
    from .routers.messages import router as messages_router
    from .routers.suggestions import router as suggestions_router

    app.include_router(callback_router)
    app.include_router(auth_router)
    app.include_router(messages_router)
    app.include_router(suggestions_router)
    return app


app = create_app()
