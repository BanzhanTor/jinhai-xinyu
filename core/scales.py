# -*- coding: utf-8 -*-
"""GAD-7 焦虑量表 / PHQ-9 抑郁量表：计分、分级、建议、危机判定。

量表是公开的标准工具，计分规则按通行标准实现。
注意：本模块只做"参考性分级"，不做医学诊断。
"""
from __future__ import annotations

OPTIONS = ["完全不会", "好几天", "一半以上天数", "几乎每天"]

SCALES = {
    "GAD7": {
        "name": "广泛性焦虑量表 GAD-7",
        "short": "GAD-7",
        "intro": "过去两周，你被以下问题困扰的频率有多高？请按真实感受作答。",
        "items": [
            "感到紧张、焦虑或急切",
            "无法停止或控制担忧",
            "对各种各样的事情担忧过多",
            "很难放松下来",
            "由于不安而无法静坐",
            "变得容易烦恼或急躁",
            "感到似乎将有可怕的事情发生而害怕",
        ],
        "max": 21,
        "levels": [
            {"min": 0, "max": 4, "key": "none", "label": "无明显焦虑",
             "desc": "你的焦虑水平在正常范围内。"},
            {"min": 5, "max": 9, "key": "mild", "label": "轻度焦虑",
             "desc": "有一些焦虑信号，但还没有明显影响日常。"},
            {"min": 10, "max": 14, "key": "moderate", "label": "中度焦虑",
             "desc": "焦虑已经在干扰你的注意力或睡眠，值得认真对待。"},
            {"min": 15, "max": 21, "key": "severe", "label": "重度焦虑",
             "desc": "这个水平通常需要专业支持，建议尽快联系学校心理中心。"},
        ],
    },
    "PHQ9": {
        "name": "患者健康问卷 PHQ-9",
        "short": "PHQ-9",
        "intro": "过去两周，以下情况出现的频率有多高？第 9 题涉及自伤念头，请如实作答。",
        "items": [
            "做事时提不起劲或没有兴趣",
            "感到心情低落、沮丧或绝望",
            "入睡困难、睡不安稳或睡得过多",
            "感觉疲倦或没有活力",
            "食欲不振或吃得太多",
            "觉得自己很糟，或很失败，或让自己/家人失望",
            "对事物专注有困难（看手机、看书时）",
            "动作或说话慢到别人都察觉，或相反：烦躁、坐立不安",
            "有不如死掉、或用某种方式伤害自己的念头",
        ],
        "max": 27,
        "levels": [
            {"min": 0, "max": 4, "key": "none", "label": "无明显抑郁",
             "desc": "你的情绪状态在正常波动范围内。"},
            {"min": 5, "max": 9, "key": "mild", "label": "轻度抑郁",
             "desc": "有一些低落信号，多数人靠自己调节也能缓解。"},
            {"min": 10, "max": 14, "key": "moderate", "label": "中度抑郁",
             "desc": "情绪已经影响到生活节奏，建议寻求支持。"},
            {"min": 15, "max": 19, "key": "severe", "label": "中重度抑郁",
             "desc": "这个水平建议尽快与专业心理咨询师谈一次。"},
            {"min": 20, "max": 27, "key": "severe", "label": "重度抑郁",
             "desc": "请尽快联系学校心理中心或专业医疗机构。"},
        ],
    },
}

# PHQ-9 第 9 题（索引 8）为自伤念头题，>0 即触发危机
_CRISIS_ITEM = {"PHQ9": 8}

ADVICE = {
    ("GAD7", "none"): [
        "当前没有明显信号，保持现在的节奏就好。",
        "一个好习惯：每周固定做一件「只为自己」的事，别让它被日程挤掉。",
        "如果之后情绪持续两周以上低落，再回来测一次。",
    ],
    ("GAD7", "mild"): [
        "轻度阶段最有效的往往不是「治疗」，而是把生活节律拉回来：固定起床时间、每天出门 20 分钟。",
        "焦虑上头时用 4-7-8 呼吸：吸气 4 秒、屏住 7 秒、呼气 8 秒，重复四轮。",
        "试着记录三天的波动点——什么时候最难受、和什么有关。这比笼统地「我不开心」有用得多。",
        "两周后再测一次，看趋势比看单次数值更重要。",
    ],
    ("GAD7", "moderate"): [
        "这个水平建议主动约一次学校心理中心的咨询。不是「严重到要去」，而是「早点去更省力」。",
        "把最消耗你的那一件事写下来，只处理这一件，其余的暂时允许它不完美。",
        "告诉至少一个你信任的人：你最近状态不太好。被知道本身就有缓解作用。",
        "避免用熬夜、酒精、报复性刷手机来调节，这些会让情况更糟。",
    ],
    ("GAD7", "severe"): [
        "请尽快联系学校心理中心，预约一次专业面谈；这个水平不建议独自硬扛。",
        "如果需要医疗评估，可以去正规医院的精神科/心理科门诊，这和你去看内科没有区别。",
        "现在先做一件小事：保证睡眠和三餐。身体状态是情绪的底座。",
        "把 12356 心理援助热线存进手机，难受的时候可以随时打。",
    ],
    ("PHQ9", "none"): [
        "当前没有明显信号。",
        "保持作息和社会连接——这两件事对情绪的防护作用比想象中大。",
        "偶尔低落是正常的，不必因为一次低分焦虑。",
    ],
    ("PHQ9", "mild"): [
        "轻度阶段先从「行为激活」开始：每天安排一件小而确定能完成的事，做完就记下来。",
        "减少反刍：给「想同一件事」设一个 15 分钟的时间盒，时间到就去做别的。",
        "晒太阳、走路、和人说话，这三件小事对情绪的作用有实证支持。",
        "两周后复测，看趋势。",
    ],
    ("PHQ9", "moderate"): [
        "建议主动预约学校心理中心。中度的标志是「已经开始影响生活」，早介入会省很多力。",
        "先守住底线：睡眠、三餐、出门。低落的时候最容易先丢掉的正是这三样。",
        "把「我应该振作」换成「我今天能完成一件小事」，标准降低反而更容易动起来。",
        "如果两周内没有改善，或个人状态继续下滑，请尽快就医评估。",
    ],
    ("PHQ9", "severe"): [
        "请尽快联系学校心理中心，并考虑去正规医院精神科/心理科做一次专业评估。",
        "这个程度不建议独自应对，请让至少一个家人或朋友知道你的状态。",
        "先保证基本生理需求：吃饭、睡觉、喝水。这是底线，不是要求。",
        "把 12356 心理援助热线存进手机，紧急情况请拨打 120。",
    ],
}


def get_scale(key: str) -> dict | None:
    return SCALES.get((key or "").upper())


def score(key: str, answers: list) -> dict:
    """计分 + 分级 + 建议 + 危机判定。

    answers: 与 items 等长的整数列表（0-3）。
    返回结果字典；参数不合法抛 ValueError。
    """
    k = (key or "").upper()
    scale = SCALES.get(k)
    if scale is None:
        raise ValueError(f"未知量表：{key}")

    n = len(scale["items"])
    if not isinstance(answers, list) or len(answers) != n:
        raise ValueError(f"答案数量不对，应为 {n} 题")

    vals = []
    for i, a in enumerate(answers):
        try:
            v = int(a)
        except (TypeError, ValueError):
            raise ValueError(f"第 {i + 1} 题的答案不是整数")
        if v < 0 or v > 3:
            raise ValueError(f"第 {i + 1} 题的取值超出范围（应为 0-3）")
        vals.append(v)

    total = sum(vals)
    level = scale["levels"][-1]
    for lv in scale["levels"]:
        if lv["min"] <= total <= lv["max"]:
            level = lv
            break

    crisis = False
    idx = _CRISIS_ITEM.get(k)
    if idx is not None and vals[idx] > 0:
        crisis = True

    advice = list(ADVICE.get((k, level["key"]), []))
    if crisis:
        advice.insert(0, "你选择了「有不如死掉或伤害自己的念头」。这个回答很重要，请优先处理这一条。")

    return {
        "scale": k,
        "scale_name": scale["name"],
        "total": total,
        "max": scale["max"],
        "percent": round(total / scale["max"] * 100),
        "level_key": "crisis" if crisis else level["key"],
        "level_label": "需立即关注" if crisis else level["label"],
        "description": ("你在自伤念头上给出了肯定回答。这不代表你有问题，"
                        "只代表现在需要有人和你一起面对。")
        if crisis else level["desc"],
        "crisis": crisis,
        "advice": advice,
        "items": [{"q": q, "v": v} for q, v in zip(scale["items"], vals)],
    }
