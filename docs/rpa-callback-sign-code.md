# RPA 回调接口入参 → 验签代码(给服务商)

**日期**: 2026-08-28
**用途**: 服务商要求查看回调接口 `https://mgdev.nonoai.com.cn/api/v1/rpa/callback/1` 从入参到验签的完整代码

---

## 1. 回调接口入参(FastAPI 路由)

```python
# app/routers/callback.py

@router.post("/callback/{team_id}")
async def rpa_callback(
    team_id: str,                          # URL 路径参数, 例: "1"
    request: Request,                      # HTTP 请求(含密文 body)
    x_sign: str = Header("", alias="X-Sign"),        # 签名, Base64(HmacSHA256)
    x_nonce: str = Header("", alias="X-Nonce"),      # 随机数
    x_timestamp: str = Header("", alias="X-Timestamp"),  # 时间戳(毫秒)
):
    # 1. 校验 team_id
    if not _validate_team_id(team_id):
        return Response(status_code=400, content="invalid team_id")

    # 2. 校验三个 header 必须存在
    if not (x_sign and x_nonce and x_timestamp):
        return Response(status_code=401, content="missing headers")

    # 3. 时间窗校验(±5 分钟,兼容毫秒)
    if not _in_window(x_timestamp):
        return Response(status_code=401, content="timestamp out of window")

    # 4. 读取原始密文 body(字节)
    body = await request.body()
    if not body or len(body) > MAX_BODY_BYTES:
        return Response(status_code=400, content="invalid body")

    # 5. 验签 + 解密(见第 2、3 节)
    return await handle_encrypted(
        team_id, body, x_timestamp, x_nonce, x_sign,
        config.callback_aes_key,     # aesKey: 18a5604a-...
        config.callback_app_secret,  # appSecret: 7f08ca05-...
    )
```

---

## 2. 验签代码(核心)

```python
# app/crypto.py

def create_sign(app_secret: str, body: bytes, timestamp: str, nonce: str) -> str:
    """生成签名(与官方文档一致)"""
    str_to_sign = (
        timestamp.encode("utf-8")      # timestamp + "\n"
        + b"\n"
        + nonce.encode("utf-8")        # nonce + "\n"
        + b"\n"
        + java_utf8_replace(body)      # new String(body, UTF-8) 的复刻
    )
    mac = hmac.new(app_secret.encode("utf-8"), str_to_sign, hashlib.sha256)
    return base64.b64encode(mac.digest()).decode("utf-8")


def verify_sign(app_secret: str, body: bytes, timestamp: str, nonce: str, sign: str) -> bool:
    """验签:重算签名并常量时间比对"""
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

**签名串完全一致**: `timestamp + "\n" + nonce + "\n" + body`

---

## 3. java_utf8_replace 说明(关键差异点)

官方 Java 入参是 `@RequestBody byte[] body`,然后 `new String(body)`(Java 默认 UTF-8 解码)。

```java
String bodyStr = new String(body);   // 字节 → String(非法 UTF-8 序列替换为 U+FFFD)
```

我们的 `java_utf8_replace` **精确复刻**了这个行为:

```python
def java_utf8_replace(body: bytes) -> bytes:
    """复刻 Java CharsetDecoder(UTF-8, REPLACE) 的 new String(byte[]) 语义:
    - overlong / 超范围 / 非法 leading: 每字节替换 1 个 U+FFFD
    - surrogate: 整个序列替换 1 个 U+FFFD
    - 不完整序列: 合并替换 1 个
    - 孤立 continuation: 逐个替换
    """
    out = bytearray()
    replacement = b"\xef\xbf\xbd"  # U+FFFD
    b = body
    n = len(b)
    i = 0
    while i < n:
        c = b[i]
        if c < 0x80:
            out.append(c); i += 1
        elif c in (0xC0, 0xC1):
            out += replacement; i += 1
        elif 0xC2 <= c <= 0xDF:
            if i + 1 < n and 0x80 <= b[i+1] <= 0xBF:
                out += b[i:i+2]; i += 2
            else:
                out += replacement; i += 1
        elif 0xE0 <= c <= 0xEF:
            # 3 字节序列处理(含 overlong / surrogate 检查)
            ...
        elif 0xF0 <= c <= 0xF4:
            # 4 字节序列处理(含 overlong / 超范围检查)
            ...
        else:
            out += replacement; i += 1
    return bytes(out)
```

---

## 4. 验证调用链

```
入参(X-Timestamp, X-Nonce, X-Sign, body密文)
  ↓
handle_encrypted(team_id, body, x_timestamp, x_nonce, x_sign, aes_key, app_secret)
  ↓
if not verify_sign(app_secret, body, timestamp, nonce, sign):   # ← 这里验签
    # 验签失败 → 401
    _save_body_for_analysis(timestamp, nonce, body)  # 保存密文供分析
    return Response(status_code=401, content="verify failed")
  ↓
# 验签通过 → AES-CTR 解密 → zstd 解压 → 解析
```

---

## 5. 当前问题:验签失败但 AES 解密成功

- ✅ AES 解密成功(aesKey `18a5604a-...` 正确)
- ❌ X-Sign 验签失败(appSecret `7f08ca05-...` 对不上)

**结论**: 签名用的 appSecret 与我们配置的不一致。已提供完整回调参数(见 `rpa-callback-params-to-provider.md`),请服务商核对实际签名的 appSecret。
