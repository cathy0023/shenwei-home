# RPA 回调接口: 入参 → 验签完整代码(单文件,给服务商)

**接口**: `POST https://mgdev.nonoai.com.cn/api/v1/rpa/callback/1`

下面是这个接口从「接收入参」到「验签」的**完整代码**。原代码分散在 3 个文件(`app/routers/callback.py` / `app/crypto.py` / `app/config.py`),此处整合为单个文件方便查看。

---

## 1. 接口入参(FastAPI 路由)

```python
# 原文件: app/routers/callback.py

@router.post("/callback/{team_id}")
async def rpa_callback(
    team_id: str,                               # URL 路径参数, 例: "1"
    request: Request,                           # 请求对象(密文 body)
    x_sign: str = Header("", alias="X-Sign"),   # 签名: Base64(HmacSHA256)
    x_nonce: str = Header("", alias="X-Nonce"), # 随机数
    x_timestamp: str = Header("", alias="X-Timestamp"),  # 时间戳(毫秒)
):
    # 1. 校验 team_id(白名单)
    if not _validate_team_id(team_id):
        return Response(status_code=400, content="invalid team_id")

    # 2. 三个 header 必须存在
    if not (x_sign and x_nonce and x_timestamp):
        return Response(status_code=401, content="missing headers")

    # 3. 时间窗校验(±5 分钟,兼容毫秒)
    if not _in_window(x_timestamp):
        return Response(status_code=401, content="timestamp out of window")

    # 4. 读取原始密文 body(字节,不转字符串)
    body = await request.body()
    if not body or len(body) > MAX_BODY_BYTES:
        return Response(status_code=400, content="invalid body")

    # 5. 验签 + 解密
    return await handle_encrypted(
        team_id, body, x_timestamp, x_nonce, x_sign,
        config.callback_aes_key,      # aesKey
        config.callback_app_secret,   # appSecret
    )
```

---

## 2. 验签 + 解密处理

```python
# 原文件: app/routers/callback.py

async def handle_encrypted(team_id, body, timestamp, nonce, sign, aes_key, app_secret):
    """完整回调处理: 验签 → AES-CTR 解密 → zstd 解压 → 解析"""
    # === 第一步: 验签 ===
    if not verify_sign(app_secret, body, timestamp, nonce, sign):
        # 验签失败 → 401,并保存密文供分析
        ours = create_sign(app_secret, body, timestamp, nonce)
        _save_body_for_analysis(timestamp, nonce, body)
        return Response(status_code=401, content="verify failed")

    # === 第二步: AES-CTR 解密 ===
    compressed = _aes_ctr_transform(body, aes_key)

    # === 第三步: zstd 解压 ===
    plain = _zstd_decompress(compressed)

    # === 第四步: 解析 JSON ===
    req = RpaCallbackRequest.model_validate_json(plain)
    ...
```

---

## 3. 签名生成 + 验签(核心)

```python
# 原文件: app/crypto.py

import hashlib
import hmac
import base64


def create_sign(app_secret: str, body: bytes, timestamp: str, nonce: str) -> str:
    """生成签名 — 与请求头 sign 字段匹配"""
    str_to_sign = (
        timestamp.encode("utf-8")   # timestamp
        + b"\n"                     # + "\n"
        + nonce.encode("utf-8")     # + nonce
        + b"\n"                     # + "\n"
        + java_utf8_replace(body)   # + body(见第 4 节)
    )
    mac = hmac.new(app_secret.encode("utf-8"), str_to_sign, hashlib.sha256)
    return base64.b64encode(mac.digest()).decode("utf-8")


def verify_sign(app_secret: str, body: bytes, timestamp: str, nonce: str, sign: str) -> bool:
    """验签: 用 appSecret 重算签名,与传入的 sign 常量时间比对"""
    expected = create_sign(app_secret, body, timestamp, nonce)
    return hmac.compare_digest(expected.encode("utf-8"), sign.encode("utf-8"))
```

### 等价于官方 Java 代码

```java
// 官方文档
public static String createSign(String appSecret, String body,
                                long timestamp, String nonce) {
    String str = timestamp + "\n" + nonce + "\n" + body;
    Mac mac = Mac.getInstance("HmacSHA256");
    SecretKeySpec secretKey = new SecretKeySpec(
        appSecret.getBytes(StandardCharsets.UTF_8), "HmacSHA256");
    mac.init(secretKey);
    byte[] bytes = mac.doFinal(str.getBytes(StandardCharsets.UTF_8));
    return Base64.getEncoder().encodeToString(bytes);
}
```

**签名串与官方完全一致**: `timestamp + "\n" + nonce + "\n" + body`

---

## 4. java_utf8_replace(关键: 复刻 Java `new String(body)`)

官方 Java 入参是 `@RequestBody byte[] body`, 然后 `String bodyStr = new String(body)`。
Java 的 `new String(byte[])` 用 UTF-8 解码, **非法 UTF-8 序列会替换为 U+FFFD(�)**。

我们的 `java_utf8_replace` 精确复刻这个语义:

```python
# 原文件: app/crypto.py

def java_utf8_replace(body: bytes) -> bytes:
    """复刻 Java CharsetDecoder(UTF-8, REPLACE) 的 new String(byte[]) 语义,
    再按 UTF-8 编码回字节(等价 Java str.getBytes(UTF_8))。

    Java 对 malformed 序列的替换规则:
      - overlong(C0/C1、E0 80-9F、F0 80-8F)/超范围(F4 90-BF)/非法 leading(F5-FF):
        逐个字节替换(每字节 1 个 U+FFFD)
      - surrogate(ED A0-BF): 整个序列替换 1 个 U+FFFD
      - 不完整序列(leading + 部分 continuation 后缺): 合并替换 1 个(消费已有前缀)
      - leading + 非 continuation: 替换 leading 1 个,后续字节重新扫描
      - 孤立 continuation(0x80-0xBF): 逐个替换
    """
    out = bytearray()
    replacement = b"\xef\xbf\xbd"  # U+FFFD
    b = body
    n = len(b)
    i = 0

    def is_cont(x):
        return 0x80 <= x <= 0xBF

    while i < n:
        c = b[i]
        if c < 0x80:
            out.append(c); i += 1
        elif c in (0xC0, 0xC1):
            out += replacement; i += 1
        elif 0xC2 <= c <= 0xDF:
            if i + 1 < n and is_cont(b[i + 1]):
                out += b[i:i + 2]; i += 2
            else:
                out += replacement; i += 1
        elif 0xE0 <= c <= 0xEF:
            if i + 2 < n and is_cont(b[i + 1]) and is_cont(b[i + 2]):
                if (c == 0xE0 and b[i + 1] < 0xA0) or (c == 0xED and b[i + 1] > 0x9F):
                    out += replacement * (3 if c == 0xE0 else 1)
                    i += 3
                else:
                    out += b[i:i + 3]; i += 3
            elif i + 1 < n and is_cont(b[i + 1]):
                out += replacement; i += 2
            else:
                out += replacement; i += 1
        elif 0xF0 <= c <= 0xF4:
            if i + 3 < n and is_cont(b[i + 1]) and is_cont(b[i + 2]) and is_cont(b[i + 3]):
                if (c == 0xF0 and b[i + 1] < 0x90) or (c == 0xF4 and b[i + 1] > 0x8F):
                    out += replacement * 4; i += 4
                else:
                    out += b[i:i + 4]; i += 4
            elif i + 2 < n and is_cont(b[i + 1]) and is_cont(b[i + 2]):
                out += replacement; i += 3
            elif i + 1 < n and is_cont(b[i + 1]):
                out += replacement; i += 2
            else:
                out += replacement; i += 1
        else:
            out += replacement; i += 1
    return bytes(out)
```

---

## 5. 配置(appSecret / aesKey 来源)

```python
# 原文件: app/config.py (环境变量读取, 不硬编码)

callback_app_secret = os.getenv("RPA_PLATFORM_CALLBACK_SECRET")  # 当前值: 7f08ca05-...
callback_aes_key     = os.getenv("RPA_PLATFORM_CALLBACK_AESKEY")  # 当前值: 18a5604a-...
```

---

## 6. 当前问题定位

| 步骤 | 结果 | 说明 |
|---|---|---|
| 验签 | ❌ 失败 | appSecret `7f08ca05-...` 重算签名 ≠ X-Sign |
| AES-CTR 解密 | ✅ 成功 | aesKey `18a5604a-...` 正确 |
| zstd 解压 | ✅ 成功 | 明文正常解析 |

**结论**: 签名用 appSecret 与我们配置不一致。完整回调参数见另一份文档(`rpa-callback-params-to-provider.md`)。
