# -*- coding: utf-8 -*-
"""配置加载：config.json + 环境变量覆盖。"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config.json"

DEFAULTS = {
    # ---- 大模型接口（OpenAI 兼容格式）----
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "",
    "temperature": 0.75,
    "max_tokens": 700,
    "timeout": 60,
    "use_api_emotion": True,

    # ---- 服务 ----
    "host": "127.0.0.1",
    "port": 8000,
    "db_path": "data/jhxy.db",
    "debug": False,
}

# 常见服务商的预设，改 provider 就能切
PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "help": "https://platform.deepseek.com/api_keys",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "help": "https://platform.openai.com/api-keys",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "help": "https://bailian.console.aliyun.com/",
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "help": "https://platform.moonshot.cn/console/api-keys",
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        "help": "https://open.bigmodel.cn/usercenter/apikeys",
    },
    "ollama": {
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "qwen2.5:7b",
        "help": "本地部署，无需 key",
    },
}


class Config(dict):
    """字典形式的配置，带一点便捷方法。"""

    def __init__(self, data: dict):
        super().__init__(data)

    # ---------- 只读视图，给前端用（绝不泄露 key）----------
    def public(self) -> dict:
        p = dict(self)
        p.pop("api_key", None)
        p["has_api_key"] = bool(self.get("api_key"))
        p["key_tail"] = _tail(self.get("api_key", ""))
        p["api_ready"] = bool(self.get("api_key")) or _is_local(self.get("base_url", ""))
        return p


def _tail(key: str) -> str:
    """只露出 key 的后四位，方便用户确认填对了哪一把。"""
    key = (key or "").strip()
    return f"****{key[-4:]}" if len(key) >= 8 else ""


def _is_local(base_url: str) -> bool:
    return any(h in (base_url or "") for h in ("127.0.0.1", "localhost", "0.0.0.0"))


def load() -> Config:
    data = dict(DEFAULTS)

    if CONFIG_FILE.is_file():
        try:
            # utf-8-sig：兼容记事本另存时带 BOM 的情况，否则 json.loads 会直接失败
            user = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
            if isinstance(user, dict):
                data.update({k: v for k, v in user.items() if v is not None})
        except Exception as e:  # 配置写坏了也不要让服务起不来
            print(f"[config] 读取 config.json 失败，使用默认值：{e}")

    # 环境变量优先级最高（适合部署时不落盘明文）
    env_map = {
        "JHXY_API_KEY": "api_key",
        "JHXY_BASE_URL": "base_url",
        "JHXY_MODEL": "model",
        "JHXY_PROVIDER": "provider",
        "JHXY_PORT": "port",
        "JHXY_HOST": "host",
    }
    for env, field in env_map.items():
        val = os.environ.get(env)
        if not val:
            continue
        if field == "port":
            try:
                val = int(val)
            except ValueError:
                continue
        data[field] = val

    # 选了预设服务商但没手改 base_url/model，就用预设
    prov = data.get("provider") or "deepseek"
    if prov in PROVIDERS and prov != "custom":
        preset = PROVIDERS[prov]
        if not data.get("_custom_base_url") and (
            data["base_url"] == DEFAULTS["base_url"] or not data["base_url"]
        ):
            data["base_url"] = preset["base_url"]
        if data["model"] in (DEFAULTS["model"], "", None):
            data["model"] = preset["model"]

    Path(data["db_path"]).parent.mkdir(parents=True, exist_ok=True) if not Path(
        data["db_path"]).parent.is_absolute() else None

    dbp = Path(data["db_path"])
    if not dbp.is_absolute():
        dbp = ROOT / dbp
    dbp.parent.mkdir(parents=True, exist_ok=True)
    data["db_path"] = str(dbp)

    return Config(data)
