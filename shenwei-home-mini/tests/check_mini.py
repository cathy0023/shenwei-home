#!/usr/bin/env python3
"""T4 结构检查：小程序文件完整性 + 关键能力（页面/组件/API 调用）静态校验。

微信开发者工具不可脚本化的部分（真机预览、视觉比对）由人工按 AC1 验收；
本脚本覆盖可自动化的存在性与一致性检查。
"""
import json
import re
import sys
from pathlib import Path

MINI = Path(__file__).resolve().parent.parent  # shenwei-home-mini/

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append(msg)


def main() -> int:
    # 1. app 三件套 + 页面四件套 + 配置
    for f in ("app.js", "app.json", "app.wxss", "sitemap.json", "project.config.json"):
        check((MINI / f).is_file(), f"缺少 {f}")
    for f in ("chat.js", "chat.wxml", "chat.wxss", "chat.json"):
        check((MINI / "pages/chat" / f).is_file(), f"缺少 pages/chat/{f}")

    # 2. app.json 注册页面与磁盘一致
    app_json = json.loads((MINI / "app.json").read_text())
    for page in app_json["pages"]:
        check((MINI / f"{page}.wxml").is_file(), f"app.json 页面 {page} 缺 wxml")

    # 3. WXML 引用的静态资源存在
    wxml = (MINI / "pages/chat/chat.wxml").read_text()
    for src in set(re.findall(r'src="(/images/[^"]+)"', wxml)):
        check((MINI / src.lstrip("/")).is_file(), f"WXML 引用资源缺失 {src}")

    # 4. JS ↔ WXML 事件绑定一致性
    js = (MINI / "pages/chat/chat.js").read_text()
    for handler in set(re.findall(r'bind(?:tap|input|confirm|refresherrefresh)="(\w+)"', wxml)):
        check(re.search(rf"\b{handler}\s*\(", js) is not None,
              f"WXML 绑定的事件处理函数 {handler} 未在 chat.js 定义")

    # 5. 关键能力点（RFC G1-G3）
    for token, desc in [
        ("wx.login", "静默登录"),          # 在 app.js
        ("api.send", "发消息"),
        ("api.uploadImage", "图片上传"),
        ("api.transfer", "转人工"),
        ("api.poll", "轮询收回复"),
        ("api.list", "历史加载"),
        ("POLL_SLOW_MS", "轮询退避"),
    ]:
        check(token in js or token in (MINI / "app.js").read_text(),
              f"缺少能力点 {desc}（{token}）")

    # 6. 范围裁剪：不做服务评价/购物车/工单
    for banned in ("服务评价", "购物车", "工单", "切换学员"):
        check(banned not in wxml, f"WXML 出现裁剪项 {banned}")

    if FAILURES:
        print("FAIL:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"PASS: mini program structure OK ({MINI})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
