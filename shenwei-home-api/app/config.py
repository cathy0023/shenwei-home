"""shenwei-home-api 配置：环境变量集中读取（.env 注入，凭证不入库）。

协议：IM 渠道对接协议 v1（channel_type='external'）。
"""
import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    """零依赖 .env 加载：仅填充 os.environ 中尚不存在的键（真实环境变量优先）。"""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


@dataclass(frozen=True)
class Config:
    """全局配置（一次性读取，进程内不变）。"""

    # --- 外部智能回复服务（IM 渠道对接协议 v1）---
    channel_base_url: str = field(
        default_factory=lambda: os.getenv("CHANNEL_BASE_URL", ""))
    channel_endpoint_prefix: str = field(
        default_factory=lambda: os.getenv("CHANNEL_ENDPOINT_PREFIX", "/api/v1/sop/im/external"))
    channel_app_key: str = field(
        default_factory=lambda: os.getenv("CHANNEL_APP_KEY", ""))
    channel_app_secret: str = field(
        default_factory=lambda: os.getenv("CHANNEL_APP_SECRET", ""))
    channel_enabled: bool = field(
        default_factory=lambda: os.getenv("CHANNEL_ENABLED", "true").lower() != "false")

    # --- 微信小程序 ---
    wx_mini_appid: str = field(default_factory=lambda: os.getenv("WX_MINI_APPID", ""))
    wx_mini_secret: str = field(default_factory=lambda: os.getenv("WX_MINI_SECRET", ""))

    # --- 转人工 event（外部枚举未定，联调可改）---
    transfer_event_type: str = field(
        default_factory=lambda: os.getenv("TRANSFER_EVENT_TYPE", "transfer_to_human"))

    # --- 存储 ---
    sqlite_path: str = field(
        default_factory=lambda: os.getenv("SHM_SQLITE_PATH", "shenwei_home.db"))
    uploads_dir: str = field(
        default_factory=lambda: os.getenv("SHM_UPLOADS_DIR", "uploads"))

    # --- 会话 ---
    session_ttl_days: int = field(
        default_factory=lambda: int(os.getenv("SHM_SESSION_TTL_DAYS", "7")))

    def validate(self) -> list[str]:
        """必需配置检查，返回缺失项列表（缺失不阻塞启动，/health 可见）。"""
        missing: list[str] = []
        if not self.channel_app_key:
            missing.append("CHANNEL_APP_KEY")
        if not self.channel_app_secret:
            missing.append("CHANNEL_APP_SECRET")
        if not self.channel_base_url:
            missing.append("CHANNEL_BASE_URL")
        return missing

    @property
    def wx_mock_mode(self) -> bool:
        """微信凭证为空时走 mock openid（仅开发期）。"""
        return not (self.wx_mini_appid and self.wx_mini_secret)


config = Config()
