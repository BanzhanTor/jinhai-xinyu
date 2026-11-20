# -*- coding: utf-8 -*-
"""环境自检：不用起服务，先把该查的都查一遍。

用法：python check_env.py
"""
from __future__ import annotations

import json
import platform
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OK, WARN, BAD = "[OK]  ", "[WARN]", "[FAIL]"
issues: list[str] = []


def line(tag, text):
    print(f"  {tag} {text}")


def main() -> int:
    print("=" * 62)
    print(" 金海心语 · 环境自检")
    print("=" * 62)

    # ---------- 1 Python ----------
    print("\n[1] Python 运行环境")
    v = sys.version_info
    line(OK if v >= (3, 9) else BAD, f"Python {platform.python_version()}  ({platform.machine()})")
    if v < (3, 9):
        issues.append("Python 版本过低，请安装 3.9 及以上")

    missing = []
    for m in ("wsgiref", "sqlite3", "urllib.request", "json", "ssl"):
        try:
            __import__(m)
        except Exception:
            missing.append(m)
    line(OK if not missing else BAD,
         "标准库齐全" if not missing else f"缺少模块：{', '.join(missing)}")
    if missing:
        issues.append("标准库不完整，建议重装 Python")

    # ---------- 2 文件 ----------
    print("\n[2] 项目文件")
    need = ["app.py", "core/wsgi.py", "core/llm.py", "core/safety.py",
            "web/index.html", "web/assets/app.js", "web/assets/style.css"]
    for rel in need:
        p = ROOT / rel
        line(OK if p.is_file() else BAD, rel)
        if not p.is_file():
            issues.append(f"缺少文件：{rel}")

    cfg_file = ROOT / "config.json"
    if cfg_file.is_file():
        line(OK, "config.json 存在")
    else:
        ex = ROOT / "config.example.json"
        line(WARN, "config.json 不存在" + ("（可以从 config.example.json 复制）" if ex.is_file() else ""))
        issues.append("没有 config.json，将使用默认配置（离线模式）")

    # ---------- 3 配置 ----------
    print("\n[3] 接口配置")
    try:
        from core import config as config_mod
        from core.llm import LLMClient
        cfg = config_mod.load()
        llm = LLMClient(cfg)
        line(OK, f"base_url : {llm.base_url or '(空)'}")
        line(OK, f"model    : {llm.model}")
        if llm.api_key:
            line(OK, f"api_key  : 已填写 (****{llm.api_key[-4:]})")
        elif any(h in llm.base_url for h in ("127.0.0.1", "localhost")):
            line(OK, "api_key  : 本地模型，无需填写")
        else:
            line(WARN, "api_key  : 未填写 —— 系统将以【离线规则引擎】运行")
            issues.append("未配置 API Key，对话将走离线规则引擎（功能可用，但不是真模型）")
    except Exception as e:
        line(BAD, f"读取配置失败：{e}")
        issues.append(f"配置读取异常：{e}")
        llm = None

    # ---------- 4 数据库 ----------
    print("\n[4] 数据存储")
    try:
        from core import db
        db.init(cfg["db_path"])
        line(OK, f"SQLite 可用：{cfg['db_path']}")
        line(OK, f"当前数据：{json.dumps(db.overview(), ensure_ascii=False)}")
    except Exception as e:
        line(BAD, f"数据库初始化失败：{e}")
        issues.append(f"SQLite 异常：{e}")

    # ---------- 5 端口 ----------
    print("\n[5] 端口占用")
    host, port = cfg.get("host", "127.0.0.1"), int(cfg.get("port", 8000))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        busy = s.connect_ex((host, port)) == 0
    if busy:
        line(WARN, f"{host}:{port} 已被占用（如果服务已在运行，这是正常的）")
    else:
        line(OK, f"{host}:{port} 可用")

    # ---------- 6 外网 ----------
    print("\n[6] 大模型接口连通性")
    if llm and not llm.configured:
        line(WARN, "跳过（没有 key）")
    elif llm:
        try:
            from urllib.parse import urlparse
            u = urlparse(llm.base_url)
            host = u.hostname
            port2 = u.port or (443 if u.scheme == "https" else 80)
            with socket.create_connection((host, port2), timeout=6):
                line(OK, f"能连到 {host}:{port2}")
        except Exception as e:
            line(BAD, f"连不上 {llm.base_url}：{e}")
            issues.append("连不上模型服务商，检查网络 / 代理 / 校园网限制")

    # ---------- 汇总 ----------
    print("\n" + "=" * 62)
    if not issues:
        print(" 结论：一切正常，直接运行  python app.py --open")
    else:
        print(f" 结论：发现 {len(issues)} 个待处理项")
        for i, s in enumerate(issues, 1):
            print(f"   {i}. {s}")
        print("\n 提示：运行  python test_api.py  可以单独测试大模型接口")
    print("=" * 62)
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
