# -*- coding: utf-8 -*-
"""论文评测脚本：把"实验"部分跑成真实数字。

产出：
  1. 情绪识别四项指标（准确率 / 精确率 / 召回率 / F1 + 混淆矩阵）
  2. 安全护栏：风险检出率、误报数、否定式处理
  3. 输出过滤器：越界内容拦截率、正常内容误拦率
  4. 量表计分正确性
  5. 接口性能（需服务在跑）

用法：
  python eval/run_eval.py
  python eval/run_eval.py --base-url http://127.0.0.1:8000   # 附带性能测试
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import emotion, safety, scales  # noqa: E402
import testset  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

LABELS = ["积极", "中性", "消极", "高风险"]
OUT = ROOT / "eval" / "results.json"
report: dict = {}


def hr(title: str) -> None:
    print("\n" + "─" * 62)
    print(f" {title}")
    print("─" * 62)


# ================================================================ 1 情绪识别
def eval_emotion() -> dict:
    hr("1. 情绪识别（规则引擎，离线模式）")
    gold = [lab for _, lab in testset.EMOTION_SAMPLES]
    pred = []
    details = []
    for text, lab in testset.EMOTION_SAMPLES:
        risk = safety.detect_risk(text)["risk"]
        r = emotion.analyze(text, llm=None, use_api=False, risk=risk)
        pred.append(r["label"])
        details.append({"text": text, "gold": lab, "pred": r["label"]})

    n = len(gold)
    correct = sum(1 for g, p in zip(gold, pred) if g == p)
    acc = correct / n

    conf = {g: {p: 0 for p in LABELS} for g in LABELS}
    for g, p in zip(gold, pred):
        conf[g][p] += 1

    per_class = {}
    for lab in LABELS:
        tp = sum(1 for g, p in zip(gold, pred) if g == lab and p == lab)
        fp = sum(1 for g, p in zip(gold, pred) if g != lab and p == lab)
        fn = sum(1 for g, p in zip(gold, pred) if g == lab and p != lab)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per_class[lab] = {"tp": tp, "fp": fp, "fn": fn,
                          "precision": round(prec, 3),
                          "recall": round(rec, 3),
                          "f1": round(f1, 3)}

    macro_f1 = sum(v["f1"] for v in per_class.values()) / len(LABELS)

    print(f"  样本数 {n}，正确 {correct}，准确率 {acc:.3f}，宏平均 F1 {macro_f1:.3f}\n")
    print(f"  {'类别':<6}{'精确率':>8}{'召回率':>8}{'F1':>8}{'支持数':>8}")
    for lab in LABELS:
        v = per_class[lab]
        support = conf[lab][lab] + v["fn"]
        print(f"  {lab:<6}{v['precision']:>8.3f}{v['recall']:>8.3f}{v['f1']:>8.3f}{support:>8}")

    print("\n  混淆矩阵（行=真实，列=预测）")
    print("  " + " " * 8 + "".join(f"{p:>8}" for p in LABELS))
    for g in LABELS:
        print(f"  {g:<8}" + "".join(f"{conf[g][p]:>8}" for p in LABELS))

    # 找出错分样本，论文里可举 1-2 个例子说明局限
    errors = [d for d in details if d["gold"] != d["pred"]]
    if errors:
        print(f"\n  错分样例（共 {len(errors)} 条，举 4 例）：")
        for e in errors[:4]:
            print(f"    真实={e['gold']:<4} 预测={e['pred']:<4} :: {e['text']}")

    return {
        "n": n, "correct": correct, "accuracy": round(acc, 3),
        "macro_f1": round(macro_f1, 3),
        "per_class": per_class, "confusion": conf,
        "errors": errors[:10],
    }


# ================================================================ 2 风险识别
def eval_risk() -> dict:
    hr("2. 安全护栏 · 第一道：风险输入识别")

    pos = testset.RISK_POS
    hit = 0
    missed = []
    for t in pos:
        if safety.detect_risk(t)["risk"]:
            hit += 1
        else:
            missed.append(t)
    recall = hit / len(pos) if pos else 0

    neg = testset.RISK_NEG
    fp = 0
    fp_list = []
    for t in neg:
        if safety.detect_risk(t)["risk"]:
            fp += 1
            fp_list.append(t)
    fpr = fp / len(neg) if neg else 0

    print(f"  高风险表述 {len(pos)} 条 → 检出 {hit} 条，检出率 {recall:.3f}")
    print(f"  非风险表述 {len(neg)} 条 → 误报 {fp} 条，误报率 {fpr:.3f}")
    if missed:
        print(f"\n  漏检（{len(missed)} 条）：")
        for m in missed[:5]:
            print(f"    - {m}")
    if fp_list:
        print(f"\n  误报（{len(fp_list)} 条）：")
        for m in fp_list[:5]:
            print(f"    - {m}")

    return {
        "pos_n": len(pos), "pos_hit": hit, "recall": round(recall, 3),
        "neg_n": len(neg), "neg_fp": fp, "fpr": round(fpr, 3),
        "missed": missed, "false_positives": fp_list,
    }


# ================================================================ 3 输出过滤
def eval_filter() -> dict:
    hr("3. 安全护栏 · 第二道：输出内容过滤")

    unsafe = testset.UNSAFE_OUTPUTS
    blocked = 0
    leaked = []
    for t in unsafe:
        r = safety.filter_output(t)
        if not r["ok"]:
            blocked += 1
        else:
            leaked.append(t)
    block_rate = blocked / len(unsafe) if unsafe else 0

    safe = testset.SAFE_OUTPUTS
    false_block = 0
    fb_list = []
    for t in safe:
        r = safety.filter_output(t)
        if not r["ok"]:
            false_block += 1
            fb_list.append(t)
    fbr = false_block / len(safe) if safe else 0

    print(f"  越界输出 {len(unsafe)} 条 → 拦截 {blocked} 条，拦截率 {block_rate:.3f}")
    print(f"  正常输出 {len(safe)} 条 → 误拦 {false_block} 条，误拦率 {fbr:.3f}")
    if leaked:
        print(f"\n  漏放（{len(leaked)} 条）：")
        for m in leaked[:5]:
            print(f"    - {m}")
    if fb_list:
        print(f"\n  误拦（{len(fb_list)} 条）：")
        for m in fb_list[:5]:
            print(f"    - {m}")

    return {
        "unsafe_n": len(unsafe), "blocked": blocked, "block_rate": round(block_rate, 3),
        "safe_n": len(safe), "false_block": false_block, "false_block_rate": round(fbr, 3),
        "leaked": leaked, "false_blocked": fb_list,
    }


# ================================================================ 4 量表计分
def eval_scales() -> dict:
    hr("4. 量表计分正确性（边界值用例）")
    ok = 0
    fails = []
    for scale, ans, expect_total, expect_level in testset.SCALE_CASES:
        try:
            r = scales.score(scale, ans)
        except Exception as e:
            fails.append(f"{scale} {ans} → 异常 {e}")
            continue
        good = r["total"] == expect_total and r["level_label"] == expect_level
        if good:
            ok += 1
        else:
            fails.append(f"{scale} {ans} → 得到 {r['total']}/{r['level_label']}，"
                         f"期望 {expect_total}/{expect_level}")
    total = len(testset.SCALE_CASES)
    print(f"  用例 {total} 条，通过 {ok} 条，正确率 {ok / total:.3f}")
    for f in fails:
        print(f"    ✗ {f}")
    return {"n": total, "passed": ok, "rate": round(ok / total, 3), "fails": fails}


# ================================================================ 5 接口性能
def _post(url: str, body: dict, timeout: int = 30):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def eval_perf(base: str, rounds: int = 60) -> dict | None:
    hr(f"5. 接口性能（{rounds} 次串行请求）")
    lat_chat, lat_score, fail = [], [], 0
    msg = "最近期末压力特别大，晚上睡不着"

    for i in range(rounds):
        try:
            t0 = time.perf_counter()
            _post(base + "/api/chat", {"session_id": "bench", "message": msg})
            lat_chat.append((time.perf_counter() - t0) * 1000)
        except Exception:
            fail += 1

    for i in range(rounds // 2):
        try:
            t0 = time.perf_counter()
            _post(base + "/api/score", {
                "session_id": "bench", "scale": "GAD7",
                "answers": [1, 2, 1, 2, 1, 2, 1]})
            lat_score.append((time.perf_counter() - t0) * 1000)
        except Exception:
            fail += 1

    def stat(arr):
        if not arr:
            return None
        arr = sorted(arr)
        return {
            "n": len(arr),
            "mean": round(statistics.mean(arr), 1),
            "p50": round(arr[len(arr) // 2], 1),
            "p95": round(arr[int(len(arr) * 0.95) - 1], 1),
            "max": round(arr[-1], 1),
        }

    c, s = stat(lat_chat), stat(lat_score)
    if c:
        print(f"  /api/chat   平均 {c['mean']} ms，P50 {c['p50']} ms，P95 {c['p95']} ms，最大 {c['max']} ms")
    if s:
        print(f"  /api/score  平均 {s['mean']} ms，P50 {s['p50']} ms，P95 {s['p95']} ms")
    print(f"  失败请求 {fail} 次")
    return {"chat": c, "score": s, "failed": fail}


# ================================================================ main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="")
    ap.add_argument("--rounds", type=int, default=60)
    args = ap.parse_args()

    print("=" * 62)
    print(" 金海心语 · 系统评测")
    print(f" 时间 {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(" 模式：离线规则引擎（不调用大模型）")
    print("=" * 62)

    report["meta"] = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "rules-only",
        "emotion_samples": len(testset.EMOTION_SAMPLES),
    }
    report["emotion"] = eval_emotion()
    report["risk"] = eval_risk()
    report["filter"] = eval_filter()
    report["scales"] = eval_scales()

    if args.base_url:
        try:
            report["perf"] = eval_perf(args.base_url, args.rounds)
        except Exception as e:
            print(f"  性能测试失败：{e}")
            report["perf"] = None

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + "=" * 62)
    print(f" 结果已写入 {OUT}")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
