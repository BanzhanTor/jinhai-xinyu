# -*- coding: utf-8 -*-
"""WSGI 应用：路由 + 静态文件 + 全部 API。

用标准库 wsgiref 提供，不依赖 Flask。
因为是标准 WSGI 接口，将来换成 gunicorn / uvicorn(ASGI 除外) / waitress 托管无需改代码。
"""
from __future__ import annotations

import json
import mimetypes
import posixpath
import re
import time
import traceback
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, unquote

from . import db, emotion, fallback, knowledge, prompts, safety, scales
from .llm import LLMClient, LLMError

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config.json"

JSON_TYPE = "application/json; charset=utf-8"

# 允许通过网页修改的字段（其余一律不开放）
EDITABLE_FIELDS = {
    "api_key", "base_url", "model", "provider",
    "temperature", "max_tokens", "timeout", "use_api_emotion",
}
LOCAL_ADDRS = {"127.0.0.1", "::1", "localhost"}


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, **extra):
        super().__init__(message)
        self.message = message
        self.status = status
        self.extra = extra


# ================================================================ 辅助
def _json_response(start_response, data, status=200):
    body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    start_response(
        f"{status} {HTTPStatus(status).phrase}",
        [("Content-Type", JSON_TYPE),
         ("Content-Length", str(len(body))),
         ("Cache-Control", "no-store"),
         ("X-Content-Type-Options", "nosniff")],
    )
    return [body]


def _read_json(environ) -> dict:
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    if length <= 0:
        return {}
    if length > 2 * 1024 * 1024:
        raise ApiError("请求体过大", 413)
    raw = environ["wsgi.input"].read(length)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ApiError("请求体不是合法 JSON")
    if not isinstance(data, dict):
        raise ApiError("请求体必须是 JSON 对象")
    return data


def _q(environ, name: str, default: str = "") -> str:
    qs = parse_qs(environ.get("QUERY_STRING", ""))
    return (qs.get(name) or [default])[0]


def _session(payload: dict, environ) -> str:
    sid = (payload.get("session_id") or _q(environ, "session_id") or "").strip()
    if not sid or len(sid) > 64 or not re.fullmatch(r"[A-Za-z0-9_\-]+", sid):
        raise ApiError("session_id 缺失或格式不合法")
    return sid


# ================================================================ 应用
class Application:
    def __init__(self, cfg):
        self.cfg = cfg
        self.llm = LLMClient(cfg)
        self.started_at = time.time()
        db.init(cfg["db_path"])

    # ------------------------------------------------------------ WSGI
    def __call__(self, environ, start_response):
        path = unquote(environ.get("PATH_INFO") or "/")
        method = environ.get("REQUEST_METHOD", "GET").upper()
        try:
            if path.startswith("/api/"):
                return self._api(path, method, environ, start_response)
            return self._static(path, environ, start_response)
        except ApiError as e:
            return _json_response(start_response, {"ok": False, "error": e.message, **e.extra}, e.status)
        except Exception:
            traceback.print_exc()
            return _json_response(
                start_response,
                {"ok": False, "error": "服务器内部错误，请查看控制台日志"},
                500,
            )

    # ------------------------------------------------------------ 静态
    def _static(self, path, environ, start_response):
        if path in ("/", ""):
            path = "/index.html"
        rel = posixpath.normpath(path).lstrip("/")
        if rel.startswith("..") or ":" in rel:
            return _json_response(start_response, {"ok": False, "error": "非法路径"}, 400)

        file = (WEB_ROOT / rel).resolve()
        try:
            file.relative_to(WEB_ROOT.resolve())
        except ValueError:
            return _json_response(start_response, {"ok": False, "error": "非法路径"}, 400)

        if not file.is_file():
            body = "<h1>404</h1><p>页面不存在。回到 <a href='/'>首页</a></p>".encode("utf-8")
            start_response("404 Not Found",
                           [("Content-Type", "text/html; charset=utf-8"),
                            ("Content-Length", str(len(body)))])
            return [body]

        ctype = mimetypes.guess_type(str(file))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        data = file.read_bytes()
        start_response("200 OK", [
            ("Content-Type", ctype),
            ("Content-Length", str(len(data))),
            # 一律不缓存：避免改完前端刷新还是旧文件，排查时非常容易误判
            ("Cache-Control", "no-store, must-revalidate"),
        ])
        return [data]

    # ------------------------------------------------------------ API
    def _api(self, path, method, environ, start_response):
        route = path[len("/api"):].rstrip("/") or "/"

        # ---------- 健康检查 ----------
        if route == "/health" and method == "GET":
            info = self.llm.ping() if self.llm.configured else {
                "ok": False, "error": "未配置 API Key，当前使用离线规则引擎",
                "model": self.llm.model, "base_url": self.llm.base_url,
            }
            return _json_response(start_response, {
                "ok": True,
                "uptime_sec": int(time.time() - self.started_at),
                "api_configured": self.llm.configured,
                "api": info,
                "db": self.cfg["db_path"],
            })

        # ---------- 公开配置 ----------
        if route == "/config" and method == "GET":
            pub = self.cfg.public()
            pub["providers"] = list(_provider_names())
            pub["scales"] = {k: {"name": v["name"], "items": v["items"],
                                 "options": scales.OPTIONS, "max": v["max"]}
                             for k, v in scales.SCALES.items()}
            return _json_response(start_response, {"ok": True, "config": pub})

        if route == "/config" and method == "POST":
            return _json_response(start_response, self._save_config(_read_json(environ), environ))

        # ---------- 连通性测试 ----------
        if route == "/test" and method == "POST":
            body = _read_json(environ)  # 允许带上临时 key 先测再存
            if body.get("api_key") or body.get("base_url") or body.get("model"):
                probe = dict(self.cfg)
                for k in EDITABLE_FIELDS:
                    if body.get(k) is not None and body.get(k) != "":
                        probe[k] = body[k]
                result = LLMClient(probe).ping()
            else:
                result = self.llm.ping()
            return _json_response(start_response, {"ok": True, "result": result})

        # ---------- 对话 ----------
        if route == "/chat" and method == "POST":
            return _json_response(start_response, self._chat(_read_json(environ)))

        if route == "/chat/history" and method == "GET":
            sid = _session({}, environ)
            return _json_response(start_response, {
                "ok": True,
                "messages": db.get_messages(sid),
                "stats": db.session_stats(sid),
            })

        # ---------- 测评 ----------
        if route == "/score" and method == "POST":
            return _json_response(start_response, self._score(_read_json(environ)))

        if route == "/assessments" and method == "GET":
            sid = _session({}, environ)
            return _json_response(start_response, {
                "ok": True,
                "items": db.list_assessments(sid),
                "trend": {
                    "GAD7": db.assessment_trend(sid, "GAD7"),
                    "PHQ9": db.assessment_trend(sid, "PHQ9"),
                },
            })

        # ---------- 小结报告 ----------
        if route == "/report" and method == "GET":
            sid = _session({}, environ)
            return _json_response(start_response, self._report(sid))

        # ---------- 科普 ----------
        if route == "/knowledge" and method == "GET":
            cat = _q(environ, "cat", "全部")
            kw = _q(environ, "q", "")
            return _json_response(start_response, {
                "ok": True,
                "categories": knowledge.CATEGORIES,
                "items": knowledge.list_articles(cat, kw),
            })

        m = re.fullmatch(r"/knowledge/(\d+)", route)
        if m and method == "GET":
            art = knowledge.get_article(int(m.group(1)))
            if not art:
                raise ApiError("文章不存在", 404)
            return _json_response(start_response, {"ok": True, "article": art})

        # ---------- 树洞 ----------
        if route == "/tree" and method == "GET":
            return _json_response(start_response, {
                "ok": True, "items": _public_posts(),
            })

        if route == "/tree" and method == "POST":
            return _json_response(start_response, self._post_tree(_read_json(environ)))

        m = re.fullmatch(r"/tree/(\d+)/like", route)
        if m and method == "POST":
            likes = db.like_post(int(m.group(1)))
            if likes is None:
                raise ApiError("帖子不存在", 404)
            return _json_response(start_response, {"ok": True, "likes": likes})

        # ---------- 汇总统计 ----------
        if route == "/overview" and method == "GET":
            return _json_response(start_response, {"ok": True, "data": db.overview()})

        raise ApiError(f"接口不存在：{path}", 404)

    # ============================================================ 业务
    def _chat(self, payload: dict) -> dict:
        sid = _session(payload, {})
        text = str(payload.get("message") or "").strip()
        if not text:
            raise ApiError("消息不能为空")
        if len(text) > 1000:
            raise ApiError("单条消息请控制在 1000 字以内")

        t0 = time.time()

        # 第一道护栏：输入侧风险识别
        risk = safety.detect_risk(text)

        # 情绪识别（高风险时直接锁定，不调模型）
        emo = emotion.analyze(
            text,
            llm=self.llm,
            use_api=bool(self.cfg.get("use_api_emotion")) and self.llm.configured,
            risk=risk["risk"],
        )

        db.add_message(sid, "user", text, emotion=emo["label"],
                       strategy=emo["strategy"]["name"], risk=risk["risk"])

        used_api = False
        warning = ""
        reply_text = ""

        if risk["risk"]:
            # 危机轮次：不走模型，固定转介话术，绝对可控
            reply_text = safety.CRISIS_REPLY
            strategy = emotion.STRATEGY["高风险"]
        else:
            strategy = emo["strategy"]
            history = db.chat_history_for_llm(sid, limit=8)
            if history and history[-1]["role"] == "user" and history[-1]["content"] == text:
                history = history[:-1]  # 去掉刚插入的本轮，避免重复

            if self.llm.configured:
                try:
                    system = prompts.build_system(emo["label"], emo["scene"], risk["risk"])
                    msgs = prompts.chat_messages(system, history, text)
                    raw = self.llm.chat(msgs, max_tokens=int(self.cfg.get("max_tokens") or 700))
                    filtered = safety.filter_output(raw, risk=False)
                    reply_text = filtered["text"]
                    used_api = True
                    if filtered.get("blocked"):
                        warning = f"模型输出被安全过滤（{filtered['blocked']}），已替换为安全话术"
                except LLMError as e:
                    reply_text = fallback.reply(emo["label"], emo["scene"])
                    warning = f"模型调用失败，已降级为离线回复：{e}"
                    if e.detail:
                        warning += f"（{e.detail[:120]}）"
            else:
                reply_text = fallback.reply(emo["label"], emo["scene"])

        db.add_message(sid, "assistant", reply_text,
                       emotion=emo["label"], strategy=strategy["name"], risk=False)

        return {
            "ok": True,
            "reply": reply_text,
            "emotion": {
                "label": emo["label"],
                "score": emo["score"],
                "scene": emo["scene"],
                "source": emo["source"],
            },
            "strategy": strategy,
            "risk": risk["risk"],
            "matched": risk["matched"],
            "crisis_card": safety.CRISIS_CARD if risk["risk"] else None,
            "used_api": used_api,
            "warning": warning,
            "latency_ms": int((time.time() - t0) * 1000),
        }

    def _score(self, payload: dict) -> dict:
        sid = _session(payload, {})
        scale = str(payload.get("scale") or "").upper()
        answers = payload.get("answers")
        try:
            result = scales.score(scale, answers)
        except ValueError as e:
            raise ApiError(str(e))
        rid = db.add_assessment(sid, result, [int(a) for a in answers])
        return {"ok": True, "id": rid, "result": result}

    def _save_config(self, payload: dict, environ) -> dict:
        """把网页上填的接口配置写回 config.json，并热替换 LLM 客户端。

        只允许本机访问，避免服务暴露到公网时被人改配置。
        """
        remote = environ.get("REMOTE_ADDR") or ""
        if remote not in LOCAL_ADDRS:
            raise ApiError("出于安全考虑，只允许在本机修改接口配置", 403)

        clean = {}
        for k, v in payload.items():
            if k not in EDITABLE_FIELDS:
                continue
            if k in ("temperature", "max_tokens", "timeout"):
                try:
                    v = float(v) if k == "temperature" else int(v)
                except (TypeError, ValueError):
                    raise ApiError(f"{k} 必须是数字")
            if k == "use_api_emotion":
                v = bool(v)
            clean[k] = v.strip() if isinstance(v, str) else v

        if not clean:
            raise ApiError("没有可保存的字段")

        # 以默认值为底 → 叠加现有文件 → 叠加本次修改，保证写出的文件是完整的
        from . import config as config_mod
        merged = dict(config_mod.DEFAULTS)
        if CONFIG_FILE.is_file():
            try:
                onfile = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
                if isinstance(onfile, dict):
                    merged.update(onfile)
            except Exception:
                pass
        merged.pop("_说明", None)
        merged.pop("_备选服务商", None)
        merged.update(clean)
        merged["db_path"] = self.cfg.get("db_path", merged.get("db_path"))

        tmp = CONFIG_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(CONFIG_FILE)

        # 热重载配置与客户端
        self.cfg = config_mod.load()
        self.llm = LLMClient(self.cfg)

        pub = self.cfg.public()
        return {
            "ok": True,
            "message": "配置已保存并生效",
            "config": {k: v for k, v in pub.items() if k != "scales" and k != "providers"},
        }

    def _post_tree(self, payload: dict) -> dict:
        text = str(payload.get("text") or "").strip()
        if not text:
            raise ApiError("内容不能为空")
        if len(text) > 500:
            raise ApiError("最多 500 字")

        risk = safety.detect_risk(text)
        emo = emotion.analyze(text, llm=self.llm,
                              use_api=bool(self.cfg.get("use_api_emotion")) and self.llm.configured,
                              risk=risk["risk"])

        if risk["risk"]:
            ai_reply = ("这条内容已转入人工通道。如果你此刻感到不安全，"
                        "请联系学校心理中心，或拨打 12356 心理援助热线。你不是一个人。")
            hidden = True
        else:
            hidden = False
            ai_reply = ""
            if self.llm.configured:
                try:
                    raw = self.llm.chat(prompts.tree_messages(text, emo["label"]), max_tokens=220)
                    filtered = safety.filter_output(raw, risk=False)
                    ai_reply = filtered["text"]
                except LLMError:
                    ai_reply = fallback.tree_reply(emo["label"])
            else:
                ai_reply = fallback.tree_reply(emo["label"])

        row = db.add_post(text, emo["label"], ai_reply, hidden)
        return {
            "ok": True,
            "hidden": hidden,
            "emotion": emo["label"],
            "post": {
                "id": row["id"],
                "text": "" if hidden else row["text"],
                "ai_reply": row["ai_reply"],
                "likes": row["likes"],
                "hidden": bool(row["hidden"]),
                "created_at": row["created_at"],
            },
            "items": _public_posts(),
        }

    def _report(self, sid: str) -> dict:
        """生成"心理状态小结"。对应报告里的 /report 接口。"""
        stats = db.session_stats(sid)
        msgs = db.get_messages(sid)
        assessments = db.list_assessments(sid, limit=10)

        emo_count: dict[str, int] = {}
        for m in msgs:
            if m["role"] == "user" and m.get("emotion"):
                emo_count[m["emotion"]] = emo_count.get(m["emotion"], 0) + 1

        dominant = max(emo_count, key=emo_count.get) if emo_count else "暂无"

        lines = [
            f"本次会话共记录 {stats['user_turns']} 次倾诉，"
            f"其中被标记为高风险的 {stats['risk_turns']} 次。",
            f"情绪分布以「{dominant}」为主。",
        ]
        if assessments:
            last = assessments[0]
            lines.append(
                f"最近一次测评：{last['scale']} 得分 {last['total']}，"
                f"分级为「{last['level_label']}」。"
            )
        else:
            lines.append("本会话尚未完成量表测评，建议做一次 GAD-7 或 PHQ-9。")

        suggestions = []
        if stats["risk_turns"]:
            suggestions.append("出现过高风险表述，建议尽快联系学校心理中心或拨打 12356。")
        if assessments and assessments[0].get("crisis"):
            suggestions.append("最近一次测评涉及自伤念头，请优先处理这一项。")
        if not suggestions:
            suggestions.append("保持现在的节奏；如果两周内状态没有改善，再回来复测一次。")

        return {
            "ok": True,
            "session_id": sid,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "stats": stats,
            "emotion_distribution": emo_count,
            "assessments": assessments,
            "summary": lines,
            "suggestions": suggestions,
            "text": "\n".join(lines + ["", "建议："] + suggestions),
            "disclaimer": "本小结由系统根据会话记录自动生成，只作参考，不构成医学诊断。",
        }


def _public_posts() -> list[dict]:
    out = []
    for p in db.list_posts():
        hidden = bool(p["hidden"])
        out.append({
            "id": p["id"],
            "text": "" if hidden else p["text"],
            "ai_reply": p["ai_reply"] if not hidden else "",
            "likes": p["likes"],
            "hidden": hidden,
            "emotion": p["emotion"],
            "created_at": p["created_at"],
        })
    return out


def _provider_names():
    from .config import PROVIDERS
    return PROVIDERS.keys()
