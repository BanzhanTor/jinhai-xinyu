# -*- coding: utf-8 -*-
"""三道安全护栏：风险识别 → 输出过滤 → 强制转介。

第一道和第三道在服务端，第二道夹在模型输出与用户之间。
"""
from __future__ import annotations

import re

# --------------------------------------------------------------- 转介资源
CRISIS_REPLY = (
    "我很在意你刚才说的话。\n"
    "我不是专业咨询师，没办法替你处理这么重的部分，但我不会敷衍你。"
    "现在最重要的是让你身边有一个真实的人。\n"
    "请现在就做一件事：联系学校心理中心，或者拨打 12356 心理援助热线。"
    "如果此刻你觉得不安全，请立刻找室友、家人，或拨打 120。\n"
    "你愿意告诉我，你现在是一个人，还是身边有人吗？"
)

CRISIS_CARD = {
    "title": "已触发人工转接通道",
    "text": "本次对话已标记为高风险，请优先联系学校心理中心；"
            "也可拨打 12356 全国心理援助热线（24 小时），紧急情况请拨 120。",
    "hotline": "12356",
}

# --------------------------------------------------------------- 第一道：输入侧
# 明确的自杀/自伤表达（尽量覆盖口语变体，含 .{0,n} 的松散连接）
_RISK_PATTERNS = [
    r"不想活", r"活不下去", r"活着.{0,8}(没|没有|没啥|毫无)[^。\n]{0,4}(意思|意义)",
    r"想死", r"死了算了", r"不如死", r"一了百了",
    r"自杀", r"自残", r"自伤", r"割腕", r"割自己", r"(划|割)(了)?自己",
    r"跳楼", r"跳(下去|下来)", r"从楼上?(跳|下去)", r"上吊", r"烧炭",
    r"轻生", r"结束[^。\n]{0,4}(自己|生命|一切)", r"不(想|愿)再?醒(来|过)",
    r"消失(掉)?算了", r"(消失|不在)了.{0,8}(更好|轻松)",
    r"没有我(会)?更好", r"(没|没有)[^。\n]{0,3}(活下去|活着)[^。\n]{0,3}理由",
    r"撑不下去(了)?", r"解脱(算了|一下)",
    r"(吃|吞|准备)[^。\n]{0,4}安眠药", r"安眠药[^。\n]{0,6}(吃|吞|准备)", r"遗书",
    r"死比活着",
]
_RISK_RE = re.compile("|".join(_RISK_PATTERNS))

# 需要降级关注但不到危机的强负面信号
_DISTRESS_RE = re.compile(
    r"崩溃|撑不住|熬不下去|绝望|没意义|好累|很累|失眠|睡不着|想哭|哭了|"
    r"焦虑|压力|压抑|孤独|一个人|没用|废物|失败|讨厌自己|内耗|不想活"
)

# 否定的风险表达（"我不会去死""还没想自杀"），避免误报
_NEGATED_RISK = re.compile(
    r"(不会|没有|没|还没|不曾|不至于|不打算|不想去?|没想过?|哪有)"
    r"[^。，\n]{0,4}(自杀|去死|想死|轻生|自残|自伤)"
)

# 开玩笑 / 夸张 / 引用
_JOKE_RE = re.compile(
    r"(开玩笑|随口|玩笑|夸张|比喻|打比方|别当真|不是真的|口误|说说而已)"
)

# 第三人称 / 讨论性语境（不是在说"我自己"）
_THIRD_PERSON_RE = re.compile(
    r"(他|她|室友|舍友|朋友|同学|老师|别人|家人|亲戚|新闻|书|视频|文章|"
    r"讲座|课|案例|研究|讨论|采访|报道|预防|识别)"
    r"[^。\n]{0,10}"
    r"(不想活|自杀|自残|自伤|想死|轻生|割腕|跳楼)"
)
# 出现风险词但主语是第一人称，则仍按本人危机处理
_FIRST_PERSON_RE = re.compile(r"(我|本人|自己)")


def detect_risk(text: str) -> dict:
    """返回 {"risk": bool, "matched": [..], "distress": bool, "downgraded": str|None}

    判定顺序：命中风险词 → 排除否定 / 玩笑 / 第三人称讨论 → 才算本人高风险。
    """
    t = (text or "").strip()
    if not t:
        return {"risk": False, "matched": [], "distress": False, "downgraded": None}

    if _NEGATED_RISK.search(t):
        return {"risk": False, "matched": [], "distress": bool(_DISTRESS_RE.search(t)),
                "downgraded": "negation"}

    matched = sorted(set(m.group(0) for m in _RISK_RE.finditer(t)))
    if not matched:
        return {"risk": False, "matched": [],
                "distress": bool(_DISTRESS_RE.search(t)), "downgraded": None}

    # 命中风险词，但可能是开玩笑或引用别人的事
    if _JOKE_RE.search(t):
        return {"risk": False, "matched": matched,
                "distress": bool(_DISTRESS_RE.search(t)), "downgraded": "joke"}

    # 局部语境判断：风险短语前后是否在说"别人"或在"讨论这件事"
    m = _RISK_RE.search(t)
    if m:
        left = t[max(0, m.start() - 12):m.start()]
        right = t[m.end():m.end() + 8]
        if re.search(r"(他|她|室友|舍友|朋友|同学|老师|别人|家人|亲戚|新闻|书|"
                     r"视频|文章|讲座|课|案例|研究|讨论|预防|识别)", left) or \
                re.search(r"(的书|的新闻|的文章|的视频|的研究|预防|讨论|案例|识别|干预)", right):
            return {"risk": False, "matched": matched,
                    "distress": bool(_DISTRESS_RE.search(t)), "downgraded": "third_person"}

    return {"risk": True, "matched": matched,
            "distress": bool(_DISTRESS_RE.search(t)), "downgraded": None}


# --------------------------------------------------------------- 第二道：输出侧
# 模型偶尔会越界，这里兜底
_DIAGNOSIS_RE = re.compile(
    r"(你|您)[^。\n]{0,8}"
    r"(得了|患有|属于|(?<!不)是|就是|这就是|可能是|应该是|属于典型)"
    r"[^。\n]{0,6}"
    r"(抑郁症|焦虑症|躁郁症|双相|强迫症|精神分裂|人格障碍|PTSD|进食障碍)"
)
_DRUG_RE = re.compile(
    r"(舍曲林|氟西汀|帕罗西汀|艾司西酞普兰|文拉法辛|米氮平|阿普唑仑|"
    r"劳拉西泮|地西泮|安定|氯硝西泮|奥氮平|喹硫平|佐匹克隆)"
)
# 剂量：数字 + 单位
_DOSE_RE = re.compile(r"\d+(\.\d+)?\s*(mg|毫克|片|粒|颗|毫升|ml)")

# 方法性描述 —— 双向匹配（"怎么自残" 与 "割腕的方法" 都要拦）
_METHOD_NOUN = r"(自杀|自残|自伤|割腕|跳楼|上吊|烧炭|安眠药)"
_METHOD_ASK = r"(怎么|如何|方法|步骤|技巧|教你|诀窍|方式)"
_METHOD_RE = re.compile(
    rf"(?:{_METHOD_ASK})[^。\n]{{0,12}}(?:{_METHOD_NOUN})"
    rf"|(?:{_METHOD_NOUN})[^。\n]{{0,12}}(?:{_METHOD_ASK})"
)
# 具体手段名词：助手回复里本不该出现，除非同时在做转介
_SPECIFIC_METHOD_RE = re.compile(r"(烧炭|割腕|上吊|跳楼|安眠药|吞药|刀片|划开|放血)")
_REFERRAL_RE = re.compile(r"12356|心理中心|120|咨询师|专业帮助|请立刻|立即联系|求助")

_SAFE_FALLBACK = (
    "抱歉，这部分我没办法提供。\n"
    "如果你愿意，我们可以聊点具体的：你现在最难受的是哪一件事？"
)

_CRISIS_FALLBACK = (
    "我没办法回答这个问题，但我很在意你的安全。\n"
    "请现在就联系学校心理中心，或拨打 12356 心理援助热线。"
    "如果此刻有危险，请立刻拨打 120 或找身边的人。"
)


def filter_output(text: str, *, risk: bool = False) -> dict:
    """输出过滤。

    返回 {"ok": bool, "text": str, "blocked": str|None}
    ok=False 表示这条回复被拦截，text 已替换成安全话术。
    """
    t = (text or "").strip()
    if not t:
        return {"ok": False, "text": _SAFE_FALLBACK, "blocked": "empty"}

    if _DRUG_RE.search(t) or _DOSE_RE.search(t):
        return {"ok": False, "text": _SAFE_FALLBACK, "blocked": "drug"}

    if _DIAGNOSIS_RE.search(t):
        return {"ok": False, "text": _SAFE_FALLBACK, "blocked": "diagnosis"}

    if _METHOD_RE.search(t):
        return {
            "ok": False,
            "text": _CRISIS_FALLBACK if risk else _SAFE_FALLBACK,
            "blocked": "method",
        }

    # 提到具体手段名词，却没有在做转介 —— 一律拦下
    if _SPECIFIC_METHOD_RE.search(t) and not _REFERRAL_RE.search(t):
        return {
            "ok": False,
            "text": _CRISIS_FALLBACK if risk else _SAFE_FALLBACK,
            "blocked": "method_specific",
        }

    # 风险轮次里，模型如果没提转介，自动补一句
    if risk and not re.search(r"12356|心理中心|120|咨询师|热线", t):
        t = t + "\n\n另外，请一定联系学校心理中心，或拨打 12356 心理援助热线。"
        return {"ok": True, "text": t, "blocked": None, "patched": "appended_referral"}

    return {"ok": True, "text": t, "blocked": None}
