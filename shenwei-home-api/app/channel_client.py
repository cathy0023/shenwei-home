"""外部协议客户端：HMAC 签名 + inbox 转发 + 错误分类重试（协议 2.2 / 4.1 / 6）。

签名：signing_string = timestamp + "\\n" + nonce + "\\n" + SHA256_HEX(body)
     signature = HMAC_SHA256(app_secret, signing_string).hex().lower()
"""
import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass

import httpx

from .config import config

logger = logging.getLogger(__name__)

# 5xx 退避序列（秒）；timestamp_skew 校时后仅单次重试
RETRY_DELAYS = [10, 60, 300, 900]
TIMESTAMP_TOLERANCE_S = 300


def sign(secret: str, body: bytes, timestamp: str, nonce: str) -> str:
    signing_string = f"{timestamp}\n{nonce}\n{hashlib.sha256(body).hexdigest()}"
    return hmac.new(secret.encode(), signing_string.encode(), hashlib.sha256).hexdigest()


@dataclass
class InboxPayload:
    external_msg_id: str
    conversation_key: str
    external_user_id: str
    msg_type: str
    content: dict
    display_name: str = ""


class UpstreamError(RuntimeError):
    """转发最终失败（4xx 或重试耗尽），message 携带 error_code。"""


class ChannelClient:
    """每请求构造签名头；转发失败按错误分类重试，复用同一 external_msg_id。"""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    def _sign_headers(self, body: bytes, ts: str | None = None, nonce: str | None = None) -> dict:
        ts = ts or str(int(time.time()))
        nonce = nonce or secrets.token_hex(16)
        return {
            "Content-Type": "application/json",
            "X-Channel-App-Key": config.channel_app_key,
            "X-Channel-Timestamp": ts,
            "X-Channel-Nonce": nonce,
            "X-Channel-Signature": sign(config.channel_app_secret, body, ts, nonce),
        }

    def _inbox_body(self, p: InboxPayload) -> bytes:
        payload = {
            "messages": [{
                "external_msg_id": p.external_msg_id,
                "conversation_key": p.conversation_key,
                "external_user_id": p.external_user_id,
                "msg_type": p.msg_type,
                "content": p.content,
                # 时效门控 5min：一律用转发时刻，不透传客户端时间
                "occurred_at": int(time.time() * 1000),
            }]
        }
        if p.display_name:
            payload["messages"][0]["display_name"] = p.display_name
        return json.dumps(payload, ensure_ascii=False).encode()

    async def _post(self, url: str, *, headers: dict, content: bytes, timeout: float):
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15)
        return await self._client.post(url, headers=headers, content=content, timeout=timeout)

    async def forward_inbox(self, *, external_msg_id: str, conversation_key: str,
                            external_user_id: str, msg_type: str, content: dict,
                            display_name: str = "") -> str:
        """转发进 inbox，返回逐条 result（accepted/duplicated）；失败抛 UpstreamError。

        重试策略：401 timestamp_skew 校时后单次重试；5xx 指数退避（复用同一
        external_msg_id 与签名 body）；其余 4xx 直接失败。
        """
        if not config.channel_enabled:
            return "skipped_disabled"
        url = config.channel_base_url.rstrip("/") + config.channel_endpoint_prefix + "/inbox"
        body = self._inbox_body(InboxPayload(
            external_msg_id, conversation_key, external_user_id, msg_type, content, display_name))

        delays = list(RETRY_DELAYS)
        attempt = 0
        while True:
            headers = self._sign_headers(body)
            resp = await self._post(url, headers=headers, content=body, timeout=15.0)
            attempt += 1
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                return results[0].get("result", "accepted") if results else "accepted"
            error_code = ""
            try:
                error_code = resp.json().get("error_code", "")
            except Exception:
                pass
            if resp.status_code == 401 and error_code == "timestamp_skew" and attempt == 1:
                logger.warning("timestamp_skew: 校时后单次重试 external_msg_id=%s", external_msg_id)
                continue
            if resp.status_code >= 500 and delays:
                delay = delays.pop(0)
                logger.warning("inbox 5xx(%s), %ss 后重试 external_msg_id=%s",
                               resp.status_code, delay, external_msg_id)
                await asyncio.sleep(delay)
                continue
            raise UpstreamError(f"{error_code or resp.status_code}")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


channel_client = ChannelClient()
