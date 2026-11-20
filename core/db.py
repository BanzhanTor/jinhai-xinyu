# -*- coding: utf-8 -*-
"""SQLite 数据层：三张核心表（对话、测评、树洞）。

设计原则（写在结题报告里的"数据最小化"）：
- 只存必要字段，不收集姓名、学号、IP；
- 会话用随机 session_id 标识，不建用户画像；
- 所有时间戳只到秒，不记录精确行为轨迹。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

_lock = threading.Lock()
_db_path: str = ""


SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT    NOT NULL,
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    emotion    TEXT,
    strategy   TEXT,
    risk       INTEGER DEFAULT 0,
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS assessments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT    NOT NULL,
    scale      TEXT    NOT NULL,
    total      INTEGER NOT NULL,
    level_key  TEXT    NOT NULL,
    level_label TEXT   NOT NULL,
    crisis     INTEGER DEFAULT 0,
    answers    TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assess_session ON assessments(session_id, id);

CREATE TABLE IF NOT EXISTS tree_posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT    NOT NULL,
    emotion    TEXT,
    ai_reply   TEXT,
    likes      INTEGER DEFAULT 0,
    hidden     INTEGER DEFAULT 0,
    created_at TEXT    NOT NULL
);
"""


def init(db_path: str) -> None:
    global _db_path
    _db_path = db_path
    with _conn() as c:
        c.executescript(SCHEMA)
    _seed_tree()


@contextmanager
def _conn():
    conn = sqlite3.connect(_db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with _lock:
            yield conn
            conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------- 对话
def add_message(session_id: str, role: str, content: str, *,
                emotion: str = "", strategy: str = "", risk: bool = False) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO messages(session_id, role, content, emotion, strategy, risk, created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (session_id, role, content, emotion, strategy, 1 if risk else 0, _now()),
        )


def get_messages(session_id: str, limit: int = 200) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT role, content, emotion, strategy, risk, created_at FROM messages"
            " WHERE session_id=? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def chat_history_for_llm(session_id: str, limit: int = 8) -> list[dict]:
    """取最近若干条轮次，喂给模型做上下文。"""
    with _conn() as c:
        rows = c.execute(
            "SELECT role, content FROM messages WHERE session_id=?"
            " ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def session_stats(session_id: str) -> dict:
    with _conn() as c:
        total = c.execute(
            "SELECT COUNT(*) n FROM messages WHERE session_id=? AND role='user'",
            (session_id,),
        ).fetchone()["n"]
        risks = c.execute(
            "SELECT COUNT(*) n FROM messages WHERE session_id=? AND risk=1",
            (session_id,),
        ).fetchone()["n"]
    return {"user_turns": total, "risk_turns": risks}


# --------------------------------------------------------------- 测评
def add_assessment(session_id: str, result: dict, answers: list) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO assessments(session_id, scale, total, level_key, level_label,"
            " crisis, answers, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (session_id, result["scale"], result["total"], result["level_key"],
             result["level_label"], 1 if result["crisis"] else 0,
             json.dumps(answers), _now()),
        )
        return int(cur.lastrowid)


def list_assessments(session_id: str, limit: int = 30) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, scale, total, level_key, level_label, crisis, created_at"
            " FROM assessments WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def assessment_trend(session_id: str, scale: str) -> list[dict]:
    """前测—后测对比用：按时间正序取同一量表的全部记录。"""
    with _conn() as c:
        rows = c.execute(
            "SELECT total, created_at FROM assessments"
            " WHERE session_id=? AND scale=? ORDER BY id ASC",
            (session_id, scale),
        ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------- 树洞
def _seed_tree() -> None:
    with _conn() as c:
        n = c.execute("SELECT COUNT(*) n FROM tree_posts").fetchone()["n"]
        if n:
            return
        seeds = [
            ("大三了还是不知道自己想干什么。室友都有明确目标了，每天听他们聊实习聊考研，"
             "我就只能假装在忙。有时候觉得自己特别没用。",
             "消极",
             "「假装在忙」这四个字挺让人心疼的。大三这个节点，很多人都在假装清楚，只是没人先说出来。"
             "你不是没用，只是还没找到那个能让你投入的具体问题。"),
            ("期末周连续熬了四天，今天早上起来突然就哭了一场，也不知道为什么。擦干眼泪还是去上了课。",
             "消极",
             "身体比我们诚实。连续四天熬夜之后，哭一场其实是它在替你说话。"
             "你擦干眼泪去上课的样子很了不起，但也很累，今晚能不能只做一件事：早点躺下。"),
        ]
        for text, emo, reply in seeds:
            c.execute(
                "INSERT INTO tree_posts(text, emotion, ai_reply, likes, hidden, created_at)"
                " VALUES(?,?,?,?,0,?)",
                (text, emo, reply, 0, _now()),
            )


def add_post(text: str, emotion: str, ai_reply: str, hidden: bool) -> dict:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO tree_posts(text, emotion, ai_reply, likes, hidden, created_at)"
            " VALUES(?,?,?,0,?,?)",
            (text, emotion, ai_reply, 1 if hidden else 0, _now()),
        )
        pid = int(cur.lastrowid)
        row = c.execute("SELECT * FROM tree_posts WHERE id=?", (pid,)).fetchone()
    return dict(row)


def list_posts(limit: int = 50) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, text, emotion, ai_reply, likes, hidden, created_at"
            " FROM tree_posts ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def like_post(pid: int) -> int | None:
    with _conn() as c:
        c.execute("UPDATE tree_posts SET likes = likes + 1 WHERE id=?", (pid,))
        row = c.execute("SELECT likes FROM tree_posts WHERE id=?", (pid,)).fetchone()
    return int(row["likes"]) if row else None


# --------------------------------------------------------------- 统计
def overview() -> dict:
    """首页/后台用的汇总数字，对应结题报告里的"运行数据"。"""
    with _conn() as c:
        sessions = c.execute("SELECT COUNT(DISTINCT session_id) n FROM messages").fetchone()["n"]
        msgs = c.execute("SELECT COUNT(*) n FROM messages WHERE role='user'").fetchone()["n"]
        risks = c.execute("SELECT COUNT(*) n FROM messages WHERE risk=1").fetchone()["n"]
        assess = c.execute("SELECT COUNT(*) n FROM assessments").fetchone()["n"]
        posts = c.execute("SELECT COUNT(*) n FROM tree_posts WHERE hidden=0").fetchone()["n"]
        avg = c.execute("SELECT AVG(likes) v FROM tree_posts").fetchone()["v"]
    return {
        "sessions": sessions,
        "user_messages": msgs,
        "risk_messages": risks,
        "assessments": assess,
        "posts": posts,
        "avg_likes": round(avg or 0, 1),
    }
