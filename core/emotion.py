# -*- coding: utf-8 -*-
"""情绪识别：规则引擎（永远可用） + 大模型分类（配置了 API 才启用）。

规则引擎不是玩具：它给了系统一个"永远能跑"的底线，
大模型挂掉、没网、没配 key 的时候，平台依然能完成基础的情绪分流。
"""
from __future__ import annotations

import json
import re

from . import prompts

# --------------------------------------------------------------- 词典
NEG_WORDS = [
    "累", "疲惫", "难过", "伤心", "焦虑", "压力", "崩溃", "孤独", "失眠", "睡不着",
    "害怕", "恐惧", "烦", "委屈", "想哭", "没用", "失败", "颓", "压抑", "难受",
    "紧张", "担心", "迷茫", "绝望", "内耗", "摆烂", "无力", "窒息", "emo",
    "讨厌", "烦死", "熬", "扛不住", "撑不住", "空虚", "麻木", "自责", "后悔",
]
POS_WORDS = [
    "开心", "高兴", "不错", "顺利", "期待", "放松", "好起来", "还行", "满意",
    "轻松", "谢谢", "感动", "有希望", "挺好", "踏实", "舒服", "进步", "喜欢",
]

SCENES = {
    "study": ["考试", "期末", "期中", "论文", "作业", "绩点", "挂科", "保研",
              "考研", "学习", "答辩", "复习", "课程", "导师", "文献", "实验"],
    "job": ["简历", "面试", "实习", "offer", "秋招", "春招", "求职", "找工作",
            "就业", "投递", "招聘", "招聘会", "笔试", "实习期", "入职"],
    "people": ["室友", "舍友", "朋友", "同学", "老师", "矛盾", "吵架", "孤立",
               "人际", "班级", "社团", "宿舍", "被排挤", "冷暴力"],
    "love": ["恋爱", "分手", "喜欢", "暗恋", "异地", "失恋", "对象", "男朋友",
             "女朋友", "表白", "前任", "暧昧"],
}

# 情绪 → 回应策略（这就是报告里写的"策略映射"）
STRATEGY = {
    "消极": {"key": "console", "name": "安慰疏导", "desc": "先接住情绪，再谈具体问题"},
    "中性": {"key": "companion", "name": "陪伴支持", "desc": "顺着聊下去，适度给方法"},
    "积极": {"key": "companion", "name": "陪伴支持", "desc": "陪着把好状态延续下去"},
    "高风险": {"key": "transfer", "name": "人工转接", "desc": "停止生成，转介真人"},
}


# --------------------------------------------------------------- 规则引擎
def detect_scene(text: str) -> str:
    t = text or ""
    best, best_hits = "general", 0
    for scene, words in SCENES.items():
        hits = sum(1 for w in words if w in t)
        if hits > best_hits:
            best, best_hits = scene, hits
    return best


def analyze_by_rules(text: str, risk: bool) -> dict:
    t = text or ""
    if risk:
        return {"label": "高风险", "score": 0.95, "scene": detect_scene(t), "source": "rules"}

    neg = sum(1 for w in NEG_WORDS if w in t)
    pos = sum(1 for w in POS_WORDS if w in t)

    if neg == 0 and pos == 0:
        label, score = "中性", 0.55
    elif neg >= pos:
        label = "消极"
        score = min(0.94, 0.56 + neg * 0.07)
    else:
        label = "积极"
        score = min(0.92, 0.58 + pos * 0.08)

    # 否定式正向表达降权：「不难过了」不该判成消极
    if re.search(r"(不|没)(那么)?(难过|焦虑|累|烦)了", t):
        label, score = "积极", max(score, 0.62)

    return {"label": label, "score": round(score, 2), "scene": detect_scene(t), "source": "rules"}


# --------------------------------------------------------------- 大模型分类
def _parse_json_loose(raw: str) -> dict | None:
    """模型有时会包 ```json ``` 或加解释，尽量抠出 JSON。"""
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r"\{.*\}", s, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def analyze_by_llm(text: str, llm) -> dict | None:
    """调模型做分类。失败返回 None，由调用方回落到规则引擎。"""
    if llm is None or not llm.configured:
        return None
    try:
        raw = llm.chat(
            [
                {"role": "system", "content": prompts.EMOTION_SYSTEM},
                {"role": "user", "content": text[:500]},
            ],
            temperature=0,
            max_tokens=80,
            json_mode=True,
        )
    except Exception:
        return None

    data = _parse_json_loose(raw)
    if not isinstance(data, dict):
        return None

    label = str(data.get("label", "")).strip()
    if label not in ("积极", "中性", "消极", "高风险"):
        return None
    try:
        score = float(data.get("score", 0.7))
    except (TypeError, ValueError):
        score = 0.7
    score = max(0.0, min(1.0, score))

    scene = str(data.get("scene", "")).strip()
    if scene not in ("study", "job", "people", "love", "general"):
        scene = detect_scene(text)

    return {"label": label, "score": round(score, 2), "scene": scene, "source": "llm"}


# --------------------------------------------------------------- 统一入口
def analyze(text: str, llm=None, use_api: bool = True, risk: bool = False) -> dict:
    """合并决策：以高风险判定为最高优先级，其余优先用模型，失败回落规则。"""
    rules = analyze_by_rules(text, risk)

    if risk:
        # 危机不需要模型判断，直接锁定
        return _finalize("高风险", 0.95, rules["scene"], "rules")

    result = None
    if use_api:
        result = analyze_by_llm(text, llm)
    if result is None:
        result = rules

    return _finalize(result["label"], result["score"], result["scene"], result["source"])


def _finalize(label: str, score: float, scene: str, source: str) -> dict:
    strategy = STRATEGY.get(label, STRATEGY["中性"])
    return {
        "label": label,
        "score": round(float(score), 2),
        "scene": scene,
        "source": source,
        "strategy": strategy,
    }
