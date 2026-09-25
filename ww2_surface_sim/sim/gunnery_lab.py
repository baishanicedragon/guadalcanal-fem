# -*- coding: utf-8 -*-
"""
gunnery_lab.py · 炮战实验室（可独立加载子模块）
================================================
学习目标：命中率如何随 距离/能见度/雷达/奇袭窗口/目标舰种 变化。

校准锚点（《瓜岛推演稿-不疯的山本》，用户口径）：
  · 泗水海战 1942-02-27：8in 1,619 发 → 5 命中 = 0.31% @15-18km（持续炮战口径）
  · 华盛顿伏击雾岛 1942-11-14：7,000m 奇袭窗口 20-27%（唯一例外，
    属 9 管齐射口径 + 奇袭倍率；本模型 ×2.0 折算后量级吻合）
公式（主代理定死）：p = c * (16000/range_m)^1.8 * vis * size，clamp [0.0002, 0.30]。
"""
import random

GUNS = {
    "JP 46cm(大和级)":   {"c": 0.0042, "guns": 9},
    "JP 35.6cm(金刚级)": {"c": 0.0031, "guns": 8},
    "JP 20.3cm":         {"c": 0.0031, "guns": 10},
    "JP 12.7cm":         {"c": 0.0022, "guns": 5},
    "US 16in":           {"c": 0.0033, "guns": 9},
    "US 8in":            {"c": 0.0031, "guns": 10},
    "US 6in":            {"c": 0.0028, "guns": 15},
    "US 5in":            {"c": 0.0022, "guns": 5},
}
VIS = {"晴(昼)": 1.0, "薄雾(昼)": 0.7, "夜·无雷达": 0.35, "夜·有雷达": 0.75, "夜雨": 0.5}
SIZE = {"DD": 0.75, "CL": 0.95, "CA": 1.10, "BB": 1.35}

PARAMS = [
    {"key": "gun", "label": "火炮", "kind": "option", "values": list(GUNS)},
    {"key": "range_km", "label": "距离(km)", "kind": "spin", "from": 5, "to": 30, "init": 16},
    {"key": "vis", "label": "能见度", "kind": "option", "values": list(VIS)},
    {"key": "surprise", "label": "奇袭窗口(前2分钟)", "kind": "option", "values": ["否", "是"]},
    {"key": "target", "label": "目标舰种", "kind": "option", "values": list(SIZE)},
    {"key": "shells", "label": "发射弹数", "kind": "spin", "from": 20, "to": 1000, "init": 200},
]


def single_hit_p(gun, range_km, vis, surprise, target):
    g = GUNS[gun]
    p = g["c"] * (16000.0 / (range_km * 1000.0)) ** 1.8
    p *= VIS[vis] * SIZE[target]
    if surprise == "是":
        p *= 2.0
    return max(0.0002, min(0.30, p))


def run(params) -> str:
    rng = random.Random(42)
    gun = params["gun"]
    range_km = float(params["range_km"])
    vis, surprise, target = params["vis"], params["surprise"], params["target"]
    shells = int(params["shells"])
    p = single_hit_p(gun, range_km, vis, surprise, target)
    per_salvo = 1.0 - (1.0 - p) ** GUNS[gun]["guns"]

    trials = 1000
    totals = []
    for _ in range(trials):
        hits = sum(1 for _ in range(shells) if rng.random() < p)
        totals.append(hits)
    totals.sort()
    mean = sum(totals) / trials
    med = totals[trials // 2]
    lines = [
        "【炮战实验室】%s → %s @%.0fkm  %s%s" % (gun, target, range_km, vis,
                                                 " +奇袭窗口" if surprise == "是" else ""),
        "  单发命中率 p = %.3f%%   每轮齐射(%d管)命中率 = %.1f%%"
        % (p * 100, GUNS[gun]["guns"], per_salvo * 100),
        "  %d 发 × 1000 次试验：均值命中 %.1f 发 | 中位 %d | 最大 %d"
        % (shells, mean, med, totals[-1]),
        "  锚点：泗水海战 0.31%@15-18km（持续炮战）；华盛顿-雾岛 7km 奇袭 20-27%"
        "（齐射口径）。",
    ]
    return "\n".join(lines)


def interactive():
    print("=== 炮战实验室（q 退出，直接回车用默认值） ===")
    while True:
        try:
            s = input("参数(炮,km,能见度,奇袭,目标,弹数) 例: US 16in,16,夜·有雷达,是,BB,200 > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if s.lower() in ("q", "quit", "exit"):
            break
        try:
            parts = [x.strip() for x in s.split(",")] if s else []
            params = {"gun": GUNS and (parts[0] if parts and parts[0] in GUNS else "US 16in"),
                      "range_km": float(parts[1]) if len(parts) > 1 else 16.0,
                      "vis": parts[2] if len(parts) > 2 and parts[2] in VIS else "晴(昼)",
                      "surprise": parts[3] if len(parts) > 3 and parts[3] in ("是", "否") else "否",
                      "target": parts[4] if len(parts) > 4 and parts[4] in SIZE else "CA",
                      "shells": int(parts[5]) if len(parts) > 5 else 200}
            print(run(params))
        except Exception as e:
            print("输入无效:", e)


if __name__ == "__main__":
    interactive()
