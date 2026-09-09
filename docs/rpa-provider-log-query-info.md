# 给 RPA 服务商 - 查日志所需信息(2026-08-31)

## 一、接入方回调地址

```
https://mgv.nonoai.com.cn/api/v1/rpa/callback/1
```

请按此回调地址在我方服务端日志查询相关推送记录。

---

## 二、服务端日志查询命令

日志系统是 systemd-journal,可用 journalctl 查询:

```bash
# 查询指定时间段的所有回调
journalctl -u rpa --since "2026-08-31 10:00" --until "2026-08-31 11:00"

# 只看验签失败
journalctl -u rpa --since "2026-08-31 10:00" --until "2026-08-31 11:00" | grep "verify failed"

# 只看验签成功
journalctl -u rpa --since "2026-08-31 10:00" --until "2026-08-31 11:00" | grep "verify ok"
```

---

## 三、关键事件时间戳(对应用户报告的 3 条消息)

用户 8/31 10:06 左右发了 3 条消息,但只有第 1 条有 AI 回复,后 2 条 401 验签失败:

| 顺序 | 内容 | ts(ms) | msg_id | 结果 |
|---|---|---|---|---|
| 第一条 | 现在可以问了吗 | `1788141973912` | 1001196 | ✅ 成功 |
| 第二条 | 你好啊 | `1788141991442` | 1001197 | ❌ 401 |
| 第三条 | 我想买课 | `1788141997629` | 1001200 | ❌ 401 |

---

## 四、服务端接收到的完整 401 失败日志

### 第 2 条「你好啊」失败日志

```
8月 31 10:06:31 iZ0xi3lactq0biydjb1ykmZ uvicorn[1573762]: WARNING app.routers.callback verify failed team=1 
  ts=1788141991442 
  nonce=faef579228254505a4d22cb55be065a9 
  incoming_sign_len=44 
  incoming_sign=dEbpdfZbT7eF4NffYDGwcuCdXLE6wznlO3nzPKmr 
  ours=QqbzN63nBuApmYDsEqbOimcG9A4av7F0OhFnzrh5 
  body_len=334 (saved body for analysis)
```

### 第 3 条「我想买课」失败日志

```
8月 31 10:06:37 iZ0xi3lactq0biydjb1ykmZ uvicorn[1573762]: WARNING app.routers.callback verify failed team=1 
  ts=1788141997629 
  nonce=e93cbb169475427bac1a6b8e37188055 
  incoming_sign_len=44 
  incoming_sign=vd0sZebA6XdgivlTX3zcOJUwZuJo5Vrqb0T6jzaB 
  ours=kGRWA2v0h85kYU8fW/09PCbRFQJrW//At1U3cCkJ 
  body_len=335 (saved body for analysis)
```

`incoming_sign`(企销宝发的) 与 `ours`(我方重算) 前 40 字符完全不同 → **签名用的 appSecret 不一致**。

---

## 五、验签失败的密文 body 保存路径

```
/tmp/rpa_bodies/body_1788141991442_faef5792.bin  (334B,「你好啊」)
/tmp/rpa_bodies/body_1788141997629_e93cbb16.bin  (335B,「我想买课」)
```

服务端已 AES 解密+base64 decode 出明文(供参考):

- 「你好啊」明文片段: `receiver=1688857238835968`(新企微号陈燕)
- 「我想买课」明文片段: `receiver=1688857238835968`(新企微号陈燕)

两条失败消息都用了**新企微号 1688857238835968**(陈燕)。

---

## 六、服务端密钥配置(供对照)

服务端 systemd 环境变量:

```
RPA_DEMO_MODE                       = real
RPA_PLATFORM_BASE_URL               = https://quote.youruitech.com
RPA_PLATFORM_APP_KEY                = YR200411511030005
RPA_PLATFORM_APP_SECRET             = 7f08ca05-...(脱敏,服务端配置值)
RPA_PLATFORM_CALLBACK_SECRET        = 7f08ca05-...(脱敏,服务端配置值)
RPA_PLATFORM_CALLBACK_AESKEY        = 18a5604a-...(脱敏,服务端配置值)
```

---

## 七、请服务商确认

1. **新企微号 `1688857238835968`(陈燕)的回调签名 appSecret 是什么?**
   - 是否与原企微号 `1688850037545792` 用同一个 appSecret?
2. 上述 3 条消息,**贵方推送时使用了哪个 appSecret?**
3. 为什么第一条验签通过、第二三条失败? 是否企销宝侧在过渡期使用了不同密钥?

---

## 八、服务端进程信息

```
PID:      1573762
启动时间:  2026-08-28 17:04
运行时长:  2天+
命令:     uvicorn app.main:app --host 127.0.0.1 --port 8100
```