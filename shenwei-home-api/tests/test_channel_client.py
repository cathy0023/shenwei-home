"""T2: 协议客户端 — 签名向量 / 空body / 错误分类。"""
import hashlib
import hmac as hmac_mod
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(monkeypatch):
    """用 dataclasses.replace 派生测试凭证的 config 单例（frozen 不可原地改）。"""
    import dataclasses

    from app import config as config_mod

    test_cfg = dataclasses.replace(
        config_mod.config,
        channel_base_url="https://ext.example.com",
        channel_endpoint_prefix="/api/v1/sop/im/external",
        channel_app_key="test_key",
        channel_app_secret="test_secret",
        channel_enabled=True,
    )
    monkeypatch.setattr(config_mod, "config", test_cfg)
    from app.channel_client import ChannelClient

    return ChannelClient()


def test_sign_matches_reference_vector(client):
    """签名串 = ts + \\n + nonce + \\n + SHA256_HEX(body)，HMAC-SHA256 hex 小写。"""
    import time

    body = b'{"a":1}'
    ts = str(int(time.time()))
    nonce = "nonce123"
    expected = hmac_mod.new(
        b"test_secret",
        f"{ts}\n{nonce}\n{hashlib.sha256(body).hexdigest()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    headers = client._sign_headers(body, ts=ts, nonce=nonce)
    assert headers["X-Channel-App-Key"] == "test_key"
    assert headers["X-Channel-Timestamp"] == ts
    assert headers["X-Channel-Nonce"] == nonce
    assert headers["X-Channel-Signature"] == expected
    assert headers["X-Channel-Signature"] == headers["X-Channel-Signature"].lower()


def test_sign_empty_body(client):
    """空 body 按 SHA256("") 计算。"""
    import time

    ts = str(int(time.time()))
    nonce = "n2"
    expected = hmac_mod.new(
        b"test_secret",
        f"{ts}\n{nonce}\n{hashlib.sha256(b'').hexdigest()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    headers = client._sign_headers(b"", ts=ts, nonce=nonce)
    assert headers["X-Channel-Signature"] == expected


@pytest.mark.anyio
async def test_forward_retries_on_5xx(client, monkeypatch):
    """5xx 指数退避重试，复用同一 external_msg_id；4xx 不重试。"""
    calls = []

    async def fake_post(url, *, headers=None, content=None, timeout=None):
        calls.append(headers["X-Channel-Signature"])
        class Resp:
            status_code = 500 if len(calls) < 3 else 200
            def json(self):
                return {"results": [{"external_msg_id": "m1", "result": "accepted"}]}
            def raise_for_status(self):
                if self.status_code >= 500 and len(calls) < 3:
                    raise RuntimeError("500")
        return Resp()

    monkeypatch.setattr(client, "_post", fake_post)
    monkeypatch.setattr("app.channel_client.RETRY_DELAYS", [0, 0, 0])
    result = await client.forward_inbox(
        external_msg_id="m1", conversation_key="c1", external_user_id="u1",
        msg_type="text", content={"content": "hi"})
    assert result == "accepted"
    assert len(calls) == 3  # 两次 500 重试 + 一次成功


@pytest.mark.anyio
async def test_forward_no_retry_on_4xx(client, monkeypatch):
    calls = []

    async def fake_post(url, *, headers=None, content=None, timeout=None):
        calls.append(1)
        class Resp:
            status_code = 401
            def json(self):
                return {"error_code": "bad_signature", "message": "x"}
            def raise_for_status(self):
                pass
        return Resp()

    monkeypatch.setattr(client, "_post", fake_post)
    monkeypatch.setattr("app.channel_client.RETRY_DELAYS", [0, 0, 0])
    with pytest.raises(RuntimeError, match="bad_signature"):
        await client.forward_inbox(
            external_msg_id="m1", conversation_key="c1", external_user_id="u1",
            msg_type="text", content={"content": "hi"})
    assert len(calls) == 1
