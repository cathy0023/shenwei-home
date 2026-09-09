# RPA 回调验签失败 - 回调参数

**日期**: 2026-08-28
**用途**: 回调验签持续失败,提供原始回调参数供企销宝开发排查

---

## 背景

- 接入方回调地址: `https://mgv.nonoai.com.cn/api/v1/rpa/callback/1`
- 我们配置的 appSecret: `7f08ca05-edc6-41a1-8d1d-c7569b5535fe`
- 我们配置的 aesKey: `18a5604a-1bc2-45ed-bddd-aad89d5bf062`
- 签名实现与官方文档一致:
  ```
  str = timestamp + "\n" + nonce + "\n" + new String(body, UTF-8)
  X-Sign = Base64(HmacSHA256(appSecret, str))
  ```
- **现象**: AES 解密成功(aesKey 正确),但 `X-Sign` 验签失败

---

## 回调参数 1: 客户消息「我想买课」

```
URL:      POST /api/v1/rpa/callback/1
X-Timestamp: 1787903137094
X-Nonce:     a6a9d00b39c44c48b1885a45a8dc2c13
X-Sign:      maPl0i53U2aDqpU/xVvHXAWAKovX3lvPipkAoZXQ
body_len:    341
```

**body 原始密文 (hex)**:
```
176fdcd4e3921b92694295ec4c12ec6f54ceff4e06560b8a25d15a7cd135d31631fc970bf6e12eb33d185b0baf5f36caec57ae467ca9bb8024e9f4f542231700b88bf29ee0f1702c1b2b7ac6d236bd5b6034b83c80da4d34e1e67bd8025433aa7e4c4241c3b7d3cf4f0a87a8d26d98bb2a7bd0e4a4471a4a7cdfa159cb4d02a3ad919fd19a7d55783f2e9e6864a6bb2274c984ff01ac49797e0cfc04e4f709f631e52222b1eef432db9cd0505de6fe66c2bd96a508ade41f6586eb25dc736e2091af8717c50e3eb3253845081fa7fe1f6d4a7c5d110ceff794d4e6152973b7f9835c744b2f9849fc7d0224499e840493790c6ae7341000de623d8b2bffb58e5898cee08e4df9c48ad570cb3a6273ee8256956844a70a9534dbbb847fe2184235cd5bbce1f3d5b3a4765e089310959bb12b5234d3c5ab5f4b40722330350f5fe6fd8f01d55ed98bfcbe17e79814295b7ab8ec06b6d4
```

**body 原始密文 (base64)**:
```
F2/c1OOSG5JpQpXsTBLsb1TO/04GVguKJdFafNE10xYx/JcL9uEusz0YWwuvXzbK7FeuRnypu4Ak6fT1QiMXALiL8p7g8XAsGyt6xtI2vVtgNLg8gNpNNOHme9gCVDOqfkxCQcO3089PCoeo0m2Yuyp70OSkRxpKfN+hWctNAqOtkZ/Rmn1VeD8unmhkprsidMmE/wGsSXl+DPwE5PcJ9jHlIiKx7vQy25zQUF3m/mbCvZalCK3kH2WG6yXcc24gka+HF8UOPrMlOEUIH6f+H21KfF0RDO/3lNTmFSlzt/mDXHRLL5hJ/H0CJEmehASTeQxq5zQQAN5iPYsr/7WOWJjO4I5N+cSK1XDLOmJz7oJWlWhEpwqVNNu7hH/iGEI1zVu84fPVs6R2XgiTEJWbsStSNNPFq19LQHIjMDUPX+b9jwHVXtmL/L4X55gUKVt6uOwGttQ=
```

**解密后明文**:
```json
[{
  "json": "{\"app_info\":\"4029174459738375188\",\"as_id\":0,\"content\":\"我想买课\",\"custom_service\":\"\",\"devinfo\":0,\"flag\":16777216,\"innerkf_vid\":0,\"is_room\":0,\"is_room_notice\":0,\"msg_id\":2118691,\"msgtype\":2,\"readuinscount\":0,\"receiver\":1688850037545792,\"referid\":0,\"send_time\":1787903135,\"sender\":7881300986104141,\"sender_name\":\"\",\"server_id\":9012618,\"vid\":1688850037545792}",
  "tenantId": "327",
  "type": 102000,
  "uuid": "b46b17a4ba3b48c7a82cb761e7a4cff0"
}]
```

---

## 回调参数 2: AI 回复回声

```
URL:      POST /api/v1/rpa/callback/1
X-Timestamp: 1787903141129
X-Nonce:     6f7b1feac67943b38860d04984b00d37
X-Sign:      OsXV8PWm3qnraBexMHNdI+lSvK9BBsivQj2MqDwH
body_len:    446
```

**body 原始密文 (hex)**:
```
176fdcd4e3511a6a6e42b56628042c31e2cb46e9c059b68b0312113ea44bc984045555c206165c8a6854dcba04e8beffbab0d13257d8afb01ddd6385b975532d0e605fe08866eadac96615e74547dcbbac25dbf6b13c6911de717a4e87c601b7864674a3894ce9363d73e7c26447dee237305e56b3156f6f9ad875b899ce0f7c5680d58aedb5291e927a12a6af66665dc6513710e5a89a62ba2cad233a1297f3e85f2e7c114e40c21730c557214141a4f44a086f21ae9894edabdf019fb06006c52367ed1446841f2f16d441d5afecad84bb1288316fddb8ca3d07a85e13c8b56ee8b4c898bccfe99af545b7faffa8ff0714852fe237a1dda1874d5a283747172d1ce0047c41b21a6e234c7c37d19a89c34ffcda402a88f2fa6823a8b5504437f807cdb95cc69a85d04293d00ccb8a80d78ce4b4fc0de1501dafec1be9aa0b0f26815925405246fb70032084a10c8ee18d79b652a0cde8b80e0b974750b0c363a859cabd1d9d076f5214ecf93bf9731ad9b85de2a8c85f3705fc2570e20383e4dc5b35f0b6f3f2fd8889cc65a0107d6d5269938b4f1cdda983e010f61b5df7ae4ea19433f442262f885b2a5a83ef0134b67cd62af210ee9e821cfadc4836
```

**body 原始密文 (base64)**:
```
F2/c1ONRGmpuQrVmKAQsMeLLRunAWbaLAxIRPqRLyYQEVVXCBhZcimhU3LoE6L7/urDRMlfYr7Ad3WOFuXVTLQ5gX+CIZurayWYV50VH3LusJdv2sTxpEd5xek6HxgG3hkZ0o4lM6TY9c+fCZEfe4jcwXlazFW9vmth1uJnOD3xWgNWK7bUpHpJ6EqavZmZdxlE3EOWommK6LK0jOhKX8+hfLnwRTkDCFzDFVyFBQaT0SghvIa6YlO2r3wGfsGAGxSNn7RRGhB8vFtRB1a/srYS7Eogxb924yj0HqF4TyLVu6LTImLzP6Zr1Rbf6/6j/BxSFL+I3od2hh01aKDdHFy0c4AR8QbIabiNMfDfRmonDT/zaQCqI8vpoI6i1UEQ3+AfNuVzGmoXQQpPQDMuKgNeM5LT8DeFQHa/sG+mqCw8mgVklQFJG+3ADIIShDI7hjXm2UqDN6LgOC5dHULDDY6hZyr0dnQdvUhTs+Tv5cxrZuF3iqMhfNwX8JXDiA4Pk3Fs18Lbz8v2IicxloBB9bVJpk4tPHN2pg+AQ9htd965OoZQz9EImL4hbKlqD7wE0tnzWKvIQ7p6CHPrcSDY=
```

**解密后明文**:
```json
[{
  "corpAppid": "ww36bedca8f623868b",
  "json": "{\"receiver\":7881300986104141,\"sender\":1688850037545792,\"sender_name\":\"\",\"is_room\":0,\"sendtime\":1787903137,\"msg_id\":2118694,\"server_id\":9012619,\"msgtype\":2,\"content\":\"您好！很高兴为您服务，请问有什么可以帮到您的吗？\",\"app_info\":\"CAEQofnE1AYYwLbE1ICAgAMg5+0S\",\"online\":1,\"isApi\":1,\"is_friend\":0,\"add_card_time\":0}",
  "msgFlag": 0,
  "sessionid": "7881300986104141",
  "tenantId": "327",
  "type": 102000,
  "userid": "1688850037545792",
  "uuid": "b46b17a4ba3b48c7a82cb761e7a4cff0"
}]
```

---

## 请企销宝确认

1. 这两条回调的 `X-Sign` 是用哪个 `appSecret` 生成的?我们配置的是 `7f08ca05-edc6-41a1-8d1d-c7569b5535fe`,验签不通过。
2. 是否存在**多种 appSecret**(不同 corpAppid / 不同消息类型用不同密钥)?
3. `new String(body)` 的编码假设:我们按 UTF-8 处理(非法序列替换 U+FFFD),请确认服务端实际行为。
