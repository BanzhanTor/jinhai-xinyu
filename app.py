# -*- coding: utf-8 -*-
"""金海心语 —— 基于 AI 赋能的大学生心理服务互动网站
服务入口。

用法：
    python app.py                # 默认读 config.json，监听 127.0.0.1:8000
    python app.py --port 8080    # 换端口
    python app.py --open         # 启动后自动打开浏览器
    python app.py --reload       # 改代码自动重启（开发用）
"""
from __future__ import annotations

import argparse
import os
import socket
import socketserver
import sys
import threading
import time
import webbrowser
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core import config as config_mod  # noqa: E402
from core.wsgi import Application      # noqa: E402

try:  # Windows 控制台中文不乱码
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BANNER = r"""
   _  _                 _   _               _
  | || |   __ _  _  _  | |_| |_  ___  _ _  (_)_ _  ___  ___
  | __ |  / _` || || | |  _| ' \/ -_)| ' \ | | ' \/ _ \/ _ \
  |_||_|  \__,_| \_, |  \__|_||_\___||_||_||_|_||_\___/\___/
                |__/
  金海心语 · 大学生心理服务互动平台   后端 v1.0
"""


class ThreadingWSGIServer(socketserver.ThreadingMixIn, WSGIServer):
    daemon_threads = True
    allow_reuse_address = True


def _make_handler(log_quiet: bool):
    class Handler(WSGIRequestHandler):
        def log_message(self, fmt, *args):
            if log_quiet:
                return
            # 只打 API 请求，静态资源不刷屏
            msg = fmt % args
            if "/api/" in msg:
                sys.stdout.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

    return Handler


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def _pick_port(host: str, want: int) -> int:
    if _port_free(host, want):
        return want
    for p in range(want + 1, want + 20):
        if _port_free(host, p):
            print(f"[warn] 端口 {want} 被占用，改用 {p}")
            return p
    raise SystemExit(f"端口 {want}-{want + 19} 都被占用，请用 --port 指定其他端口")


def main() -> None:
    ap = argparse.ArgumentParser(description="金海心语后端服务")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    ap.add_argument("--reload", action="store_true", help="修改代码后自动重启（开发用）")
    ap.add_argument("--quiet", action="store_true", help="不打印请求日志")
    args = ap.parse_args()

    if args.reload:
        return _run_reloader()

    cfg = config_mod.load()
    host = args.host or cfg.get("host") or "127.0.0.1"
    want_port = args.port or int(cfg.get("port") or 8000)
    port = _pick_port(host, want_port)

    app = Application(cfg)

    print(BANNER)
    llm = app.llm
    if llm.configured:
        print(f"  大模型   : 已配置  {llm.model}  @ {llm.base_url}")
        if llm.api_key:
            print(f"  API Key  : ****{llm.api_key[-4:]}")
    else:
        print("  大模型   : 未配置 —— 当前使用【离线规则引擎】作答")
        print("             填入 config.json 的 api_key 即可启用真实大模型")
    print(f"  数据库   : {cfg['db_path']}")
    print(f"  本地地址 : http://{host}:{port}")
    print("  停止服务 : Ctrl + C\n")

    if args.open:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://{host}:{port}")).start()

    handler = _make_handler(args.quiet)
    httpd = make_server(host, port, app,
                        server_class=ThreadingWSGIServer,
                        handler_class=handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[stop] 服务已停止")
        httpd.server_close()


def _run_reloader() -> None:
    """极简热重载：按文件修改时间轮询。"""
    import subprocess

    watched = {p: p.stat().st_mtime for p in ROOT.rglob("*.py")}
    cmd = [sys.executable, str(ROOT / "app.py")] + [
        a for a in sys.argv[1:] if a != "--reload"]
    print("[reload] 监听 .py 文件变化，Ctrl+C 退出")
    proc = subprocess.Popen(cmd)
    try:
        while True:
            time.sleep(1.0)
            changed = False
            for p in ROOT.rglob("*.py"):
                m = p.stat().st_mtime
                if watched.get(p) != m:
                    watched[p] = m
                    changed = True
            if changed:
                print("\n[reload] 检测到修改，重启…")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
                proc = subprocess.Popen(cmd)
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


if __name__ == "__main__":
    main()
