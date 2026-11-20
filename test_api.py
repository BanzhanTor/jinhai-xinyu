# -*- coding: utf-8 -*-
"""大模型接口连通性测试。

用法：
    python test_api.py                  # 读 config.json
    python test_api.py --key sk-xxxx    # 临时指定 key
    python test_api.py --key sk-xxx --base-url https://api.deepseek.com/v1 --model deepseek-chat
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core import config as config_mod  # noqa: E402
from core.llm import LLMClient, LLMError  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key")
    ap.add_argument("--base-url")
    ap.add_argument("--model")
    args = ap.parse_args()

    cfg = config_mod.load()
    if args.key:
        cfg["api_key"] = args.key
    if args.base_url:
        cfg["base_url"] = args.base_url
    if args.model:
        cfg["model"] = args.model

    llm = LLMClient(cfg)

    print("=" * 58)
    print(" 金海心语 · 大模型接口自检")
    print("=" * 58)
    print(f"  base_url : {llm.base_url or '(空)'}")
    print(f"  model    : {llm.model}")
    print(f"  api_key  : {'已填写 (****' + llm.api_key[-4:] + ')' if llm.api_key else '(空)'}")
    print(f"  超时     : {llm.timeout}s")

    if not llm.configured:
        print("\n[✗] 没有可用的 key，也没有检测到本地模型地址。")
        print("    请把 key 填进 config.json 的 \"api_key\"，或运行：")
        print("    python test_api.py --key sk-你的key")
        return 2

    print("\n正在发送测试请求……")
    r = llm.ping()
    if r.get("ok"):
        print(f"\n[✓] 连接成功，耗时 {r['ms']} ms")
        print(f"    模型回声：{r['reply']}")
        print("\n现在可以启动服务了：python app.py")
        return 0

    print(f"\n[✗] 连接失败：{r.get('error')}")
    detail = (r.get("detail") or "").strip()
    if detail:
        print(f"    服务端原始返回：{detail[:400]}")

    err = (r.get("error") or "")
    print("\n排查建议：")
    if "401" in err or "Key" in err or "key" in err:
        print("  · key 是不是复制少了几位？前后有没有空格？")
        print("  · 这个服务商的 key 需要先在控制台创建")
    elif "404" in err:
        print("  · base_url 是否缺失或多余的路径？DeepSeek 要写到 https://api.deepseek.com/v1")
    elif "402" in err or "余额" in err:
        print("  · 账户余额不足，去控制台充值")
    elif "网络" in err or "超时" in err or "解析" in err or "TLS" in err:
        print("  · 先确认这台机器能上网（浏览器打开 deepseek.com 试试）")
        print("  · 校园网/公司网可能拦截了外网 HTTPS，试试手机热点")
        print("  · 如果学校要求代理，需要在系统里配好代理")
    else:
        print("  · 用 --base-url 和 --model 显式指定再试一次")
    return 1


if __name__ == "__main__":
    sys.exit(main())
