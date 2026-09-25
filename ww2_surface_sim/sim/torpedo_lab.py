# -*- coding: utf-8 -*-
"""
torpedo_lab.py · 鱼雷对决实验室（可独立加载子模块）
====================================================
学习目标：鱼雷型号差距（93式 vs Mk15 引信灾难/修复）、距离、齐射规模、
目标航速/队形/能见度 对命中与击沉的影响。

校准锚点（《瓜岛推演稿-不疯的山本》）：
  · 93 式近距完全奇袭（萨沃岛口径）：12-15%
  · 93 式 15-18km 远距发射：2.5-3.5%
  · Mk15（1942 磁引信灾难）reliability 0.07；1943+ mod3 修复 0.45
  · 每命中沉没率：DD 一雷即沉；CL/CA 约三雷沉（瓜岛稿收敛口径）；
    BB 有 TDS，瓜岛稿实测 7.8%
公式（主代理定死）：
  p = 0.13 * (4000/range_m)^0.9 * (rel/0.80) * (40/target_kt)
      * formation * vis，clamp [0.002, 0.15]
"""
import random

TYPES = {
    "93式酸素鱼雷(日)":            {"rel": 0.80, "spd": 50, "rng": 20000},
    "Mk15 mod0(美,1942 磁引信灾难)": {"rel": 0.07, "spd": 45, "rng": 13700},
    "Mk15 mod3(美,1943+ 引信修复)":  {"rel": 0.45, "spd": 45, "rng": 13700},
}
FORMATION = {"单纵·横越(打侧面)": 1.0, "单列·迎头(打正面)": 0.45}
VIS = {"晴(昼)": 1.0, "薄雾(昼)": 0.8, "夜": 1.0, "夜雨": 0.7}
SINK = {"DD": 1.0, "CL": 0.33, "CA": 0.33, "BB": 0.078}
SIZES = ["DD", "CL", "CA", "BB"]

PARAMS = [
    {"key": "type", "label": "鱼雷型号", "kind": "option", "values": list(TYPES)},
    {"key": "range_km", "label": "发射距离(km)", "kind": "spin", "from": 2, "to": 20, "init": 8},
    {"key": "torps", "label": "齐射管数", "kind": "spin", "from": 1, "to": 40, "init": 16},
    {"key": "target_kt", "label": "目标航速(节)", "kind": "spin", "from": 10, "to": 40, "init": 30},
    {"key": "formation", "label": "目标队形", "kind": "option", "values": list(FORMATION)},
    {"key": "vis", "label": "能见度", "kind": "option", "values": list(VIS)},
    {"key": "target", "label": "目标舰种", "kind": "option", "values": SIZES},
    {"key": "n_targets", "label": "目标数量", "kind": "spin", "from": 1, "to": 12, "init": 6},
]


def single_torp_p(ttype, range_km, target_kt, formation, vis):
    t = TYPES[ttype]
    p = 0.13 * (4000.0 / (range_km * 1000.0)) ** 0.9
    p *= (t["rel"] / 0.80) * (40.0 / max(10, target_kt))
    p *= FORMATION[formation] * VIS[vis]
    return max(0.002, min(0.15, p))


def run(params) -> str:
    rng = random.Random(42)
    ttype = params["type"]
    range_km = float(params["range_km"])
    torps = int(params["torps"])
    target_kt = int(params["target_kt"])
    formation, vis = params["formation"], params["vis"]
    target, n_targets = params["target"], int(params["n_targets"])

    p = single_torp_p(ttype, range_km, target_kt, formation, vis)
    sink_p = SINK[target]

    trials = 1000
    hit_hist, sink_hist = [], []
    for _ in range(trials):
        hits = sum(1 for _ in range(torps) if rng.random() < p)
        sunk = 0
        for _ in range(hits):
            if sunk < n_targets and rng.random() < sink_p:
                sunk += 1
        hit_hist.append(hits)
        sink_hist.append(sunk)
    hit_hist.sort()
    sink_hist.sort()
    trials_f = float(trials)
    mean_hits = sum(hit_hist) / trials_f
    mean_sunk = sum(sink_hist) / trials_f
    at_least_one = sum(1 for s in sink_hist if s >= 1) / trials_f

    lines = [
        "【鱼雷对决】%s ×%d @%.0fkm → %s×%d(%d节,%s,%s)"
        % (ttype, torps, range_km, target, n_targets, target_kt, formation, vis),
        "  单雷命中率 p = %.2f%%   齐射期望命中 %.2f 条" % (p * 100, p * torps),
        "  1000 次试验：均值命中 %.2f 条 | 中位 %d | 最大 %d"
        % (mean_hits, hit_hist[trials // 2], hit_hist[-1]),
        "  击沉：期望 %.2f 艘 | 至少一沉概率 %.1f%% | 最多一次击沉 %d 艘"
        % (mean_sunk, at_least_one * 100, sink_hist[-1]),
        "  锚点：93式近距奇袭 12-15% / 远距 2.5-3.5%；Mk15(1942) 引信灾难 rel=0.07；"
        "DD 一雷沉 / BB TDS 7.8%。",
    ]
    return "\n".join(lines)


def interactive():
    print("=== 鱼雷对决实验室（q 退出） ===")
    print("鱼雷型号:", "; ".join(TYPES))
    while True:
        try:
            s = input("参数(型号序号,km,管数,目标节,队形序号,能见度序号,舰种,目标数) "
                      "例: 0,8,16,30,0,2,CL,6 > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if s.lower() in ("q", "quit", "exit"):
            break
        try:
            parts = [x.strip() for x in s.split(",")] if s else []
            tnames = list(TYPES)
            fnames = list(FORMATION)
            vnames = list(VIS)
            params = {"type": tnames[int(parts[0])] if parts and parts[0] else tnames[0],
                      "range_km": float(parts[1]) if len(parts) > 1 and parts[1] else 8.0,
                      "torps": int(parts[2]) if len(parts) > 2 and parts[2] else 16,
                      "target_kt": int(parts[3]) if len(parts) > 3 and parts[3] else 30,
                      "formation": fnames[int(parts[4])] if len(parts) > 4 and parts[4] else fnames[0],
                      "vis": vnames[int(parts[5])] if len(parts) > 5 and parts[5] else vnames[2],
                      "target": parts[6] if len(parts) > 6 and parts[6] in SIZES else "CL",
                      "n_targets": int(parts[7]) if len(parts) > 7 and parts[7] else 6}
            print(run(params))
        except Exception as e:
            print("输入无效:", e)


if __name__ == "__main__":
    interactive()
