# -*- coding: utf-8 -*-
"""大模型客户端：OpenAI 兼容协议，只用标准库 urllib。

支持 DeepSeek / OpenAI / 通义千问 / Kimi / 智谱 / 本地 Ollama、
以及任何兼容 /chat/completions 的服务。换服务商只改 config.json。
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Iterable


class LLMError(RuntimeError):
    """大模型调用失败。message 直接给用户看，所以要写人话。"""

    def __init__(self, message: str, *, status: int | None = None, detail: str = ""):
        super().__init__(message)
        self.status = status
        self.detail = detail


class LLMClient:
    def __init__(self, cfg):
        self.base_url = (cfg.get("base_url") or "").rstrip("/")
        self.api_key = (cfg.get("api_key") or "").strip()
        self.model = cfg.get("model") or "deepseek-chat"
        self.timeout = int(cfg.get("timeout") or 60)
        self.temperature = float(cfg.get("temperature") or 0.75)
        self.max_tokens = int(cfg.get("max_tokens") or 700)

    # ------------------------------------------------------------ 可用性
    @property
    def configured(self) -> bool:
        """本地模型（ollama 之类）不需要 key。"""
        if not self.base_url:
            return False
        if self.api_key:
            return True
        return any(h in self.base_url for h in ("127.0.0.1", "localhost", "0.0.0.0"))

    # ------------------------------------------------------------ 主接口
    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        if not self.configured:
            raise LLMError("尚未配置 API Key")

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        body = self._post("/chat/completions", payload)
        try:
            msg = body["choices"][0]["message"]
            content = msg.get("content") or ""
            if not content and msg.get("reasoning_content"):
                content = msg["reasoning_content"]
            if not content.strip():
                raise LLMError("模型返回了空内容", detail=json.dumps(body, ensure_ascii=False)[:400])
            return content.strip()
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError("模型返回格式异常", detail=json.dumps(body, ensure_ascii=False)[:400]) from e

    def ping(self) -> dict:
        """连通性自检：发一句最短的话，返回耗时与模型回声。"""
        import time

        t0 = time.time()
        try:
            txt = self.chat(
                [{"role": "user", "content": "回复两个字：在线"}],
                temperature=0,
                max_tokens=16,
            )
            return {
                "ok": True,
                "ms": int((time.time() - t0) * 1000),
                "reply": txt[:60],
                "model": self.model,
                "base_url": self.base_url,
            }
        except LLMError as e:
            return {
                "ok": False,
                "error": str(e),
                "detail": e.detail,
                "model": self.model,
                "base_url": self.base_url,
            }

    # ------------------------------------------------------------ HTTP
    def _post(self, path: str, payload: dict) -> dict:
        url = self.base_url + path
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": "JinHaiXinYu/1.0 (+python-stdlib)",
        }
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace") if e.fp else ""
            raise LLMError(_http_hint(e.code, raw), status=e.code, detail=raw[:500]) from e
        except urllib.error.URLError as e:
            target = (e.reason if hasattr(e, "reason") else e)
            raise LLMError(_net_hint(str(target))) from e
        except (socket.timeout, TimeoutError) as e:
            raise LLMError(f"请求超时（{self.timeout}s），模型可能太慢或网络不稳") from e
        except Exception as e:
            raise LLMError(f"请求失败：{type(e).__name__}: {e}") from e

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise LLMError("接口返回的不是 JSON，检查 base_url 是否写错", detail=raw[:400]) from e


def _http_hint(code: int, raw: str) -> str:
    hint = {
        400: "请求参数有误（多半是 model 名字不对）",
        401: "API Key 无效或已过期（401）",
        402: "账户余额不足（402）",
        403: "没有该模型的访问权限（403）",
        404: "接口地址不对（404），检查 base_url 是否需要带 /v1",
        422: "参数格式错误（422）",
        429: "请求太频繁或额度用完（429），稍后再试",
        500: "服务端内部错误（500）",
        502: "网关错误（502）",
        503: "服务暂时不可用（503）",
    }.get(code, f"接口返回 HTTP {code}")
    # 尽量把服务商的错误信息带出来，方便排查
    snippet = ""
    try:
        j = json.loads(raw)
        snippet = (j.get("error") or {}).get("message") or j.get("message") or ""
    except Exception:
        snippet = raw[:160]
    return f"{hint}" + (f"：{snippet}" if snippet else "")


def _net_hint(msg: str) -> str:
    m = msg.lower()
    if "name or service not known" in m or "getaddrinfo" in m or "11001" in m:
        return "域名解析失败：本机可能无法访问外网，或 base_url 写错了"
    if "certificate" in m or "ssl" in m:
        return "TLS 握手失败：网络被拦截，或系统时间不对，或需要代理"
    if "refused" in m or "10061" in m:
        return "连接被拒绝：服务没启动，或端口不对（本地模型请确认已启动）"
    if "timed out" in m:
        return "连接超时：网络不通或需要代理"
    return f"网络错误：{msg}"


def messages_with_system(system: str, turns: Iterable[dict]) -> list[dict]:
    msgs = [{"role": "system", "content": system}]
    msgs.extend(turns)
    return msgs
