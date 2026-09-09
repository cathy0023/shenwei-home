# RPA 回调签名长度为 44 字符 — 证据(给服务商)

**日期**: 2026-08-28
**结论**: 企销宝实际发送的 `X-Sign` 是 **44 字符**(HMAC-SHA256 完整 32 字节),不是 40 字符。

---

## 证据 1: 服务端日志直接记录 sign 长度

服务端已加日志记录 `incoming_sign_len`,企销宝真实回调全部显示 **44**:

```
verify ok team=1 ts=1787913405939 nonce=837ff769... incoming_sign_len=44 body_len=325
verify ok team=1 ts=1787913408925 nonce=159163e0... incoming_sign_len=44 body_len=338
verify ok team=1 ts=1787913412611 nonce=ea070af4... incoming_sign_len=44 body_len=404
verify ok team=1 ts=1787913416442 nonce=a95a9afa... incoming_sign_len=44 body_len=445
verify ok team=1 ts=1787913423627 nonce=6ab17226... incoming_sign_len=44 body_len=337
verify ok team=1 ts=1787913425186 nonce=761900eb... incoming_sign_len=44 body_len=329
verify ok team=1 ts=1787913430614 nonce=326b1b20... incoming_sign_len=44 body_len=660
verify ok team=1 ts=1787913436626 nonce=06f73dc7... incoming_sign_len=44 body_len=146
```

**所有真实回调的 X-Sign 都是 44 字符。**

---

## 证据 2: base64 解码验证字节数

取一条真实回调的 X-Sign(完整 44 字符),base64 解码:

```
X-Sign = bvNgnsHYzQyXahh1iy/3ochgBwaBk0JduhQe4JypAA...
(完整 44 字符)
```

base64 解码后 = **32 字节**(标准 HMAC-SHA256 输出)。

- 44 字符 base64 = 32 字节(完整 HMAC-SHA256)
- 40 字符 base64 = 30 字节(截断)

---

## 证据 3: 我方重算签名对比

我方用相同参数(ts/nonce/body)重算:

| 项 | 值 |
|---|---|
| 企销宝发送的 X-Sign(44字符) | `bvNgnsHYzQyXahh1iy/3ochgBwaBk0JduhQe4JypAA...` |
| 我方完整 HMAC-SHA256(44字符) | 完全一致 |
| 我方截断前30字节(40字符) | 与企销宝发的**前40字符**一致(但缺末尾4字符) |

**说明**: 企销宝发的 44 字符 = 我方完整 32 字节 HMAC-SHA256。我方只需比较前 40 字符即可兼容,但企销宝确实发送完整 44 字符。

---

## 结论

1. **企销宝回调 X-Sign 是完整 44 字符**(HMAC-SHA256 32 字节),非 40 字符。
2. 服务商侧校验「40 能过」是他们的兼容逻辑,但**实际发送是 44**。
3. 我方 `verify_sign` 已兼容两种长度(比较前 40 字符),因此全部通过。
