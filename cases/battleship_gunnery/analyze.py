# -*- coding: utf-8 -*-
"""
战列舰炮战命中数据分析 —— 检验"头5-10次命中决定战局与被击中战舰命运"假说
使用: 纯标准库 (无需 pandas/matplotlib), 输出 SVG 图表 + 自包含 HTML 报告
"""
import os
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dataset import DATASET

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUT, exist_ok=True)

CLS_ZH = {"BB": "战列舰", "BC": "战列巡洋舰", "AC": "装甲巡洋舰", "DD": "驱逐舰"}
OUTCOME_ZH = {"sunk": "沉没", "crippled": "重创/瘫痪", "survived": "幸存",
              "mission_kill": "任务杀伤", "captured": "被俘"}

# ================= 统计 =================
ships = DATASET
n = len(ships)

# 1) 结局分布
outcome_counter = Counter(s["outcome"] for s in ships)

# 2) 假说检验: 按 decided_by_10 分类
support = [s for s in ships if s["decided_by_10"] is True]
against = [s for s in ships if s["decided_by_10"] is False]
partial = [s for s in ships if s["decided_by_10"] == "partial"]
unknown = [s for s in ships if s["decided_by_10"] is None]

# 3) 决定性命中数统计 —— 只统计"支持+部分支持"记录中 decisive_hits 有值的
#    (这些记录的 decisive_hits 语义 = 真正致命的那几发命中; 反例记录的
#    decisive_hits 是其总命中数的替代, 语义不同, 不混入本统计)
dh = [s for s in ships if s["decided_by_10"] in (True, "partial") and s["decisive_hits"] is not None]
dh_counts = [s["decisive_hits"] for s in dh]
dh_le5 = sum(1 for v in dh_counts if v <= 5)
dh_le10 = sum(1 for v in dh_counts if v <= 10)
dh_le15 = sum(1 for v in dh_counts if v <= 15)

# 4) 反例(在5-10发区间内命中仍未决定命运/需>10发才决定/命中多仍存活)总命中数
against_counts = sorted((s["total_hits"] for s in against if s["total_hits"]), reverse=True)

# 5) 按年代分组的"决定性命中数"分布
eras = defaultdict(list)
for s in dh:
    era = "日俄战争(1904-05)" if s["year"] <= 1905 else ("一战(1914-18)" if s["year"] <= 1918 else "二战(1939-45)")
    eras[era].append(s["decisive_hits"])

# 6) 按舰型统计平均/中位决定性命中数
by_cls = defaultdict(list)
for s in dh:
    by_cls[s["cls"]].append(s["decisive_hits"])

def mean(xs): return sum(xs) / len(xs) if xs else 0
def median(xs):
    if not xs: return 0
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m-1] + s[m]) / 2

# 7) 沉没 vs 幸存: 总命中数对比
sunk_ships = [s for s in ships if s["outcome"] in ("sunk",)]
surv_ships = [s for s in ships if s["outcome"] in ("survived", "captured")]
sunk_totals = [s["total_hits"] for s in sunk_ships if s["total_hits"]]
surv_totals = [s["total_hits"] for s in surv_ships if s["total_hits"]]

stats = {
    "n": n,
    "outcome_counter": dict(outcome_counter),
    "support": len(support), "against": len(against), "partial": len(partial),
    "unknown": len(unknown),
    "support_pct": round(len(support) / n * 100, 1),
    "strict_support_pct": round(len(support) / (len(support) + len(against)) * 100, 1) if (support or against) else 0,
    "support_plus_partial_pct": round((len(support) + len(partial)) / (len(support) + len(against) + len(partial)) * 100, 1) if (support or against or partial) else 0,
    "decisive": {"n": len(dh), "counts": dh_counts,
                 "le5": dh_le5, "le10": dh_le10, "le15": dh_le15,
                 "le5_pct": round(dh_le5 / len(dh) * 100, 1) if dh else 0,
                 "le10_pct": round(dh_le10 / len(dh) * 100, 1) if dh else 0,
                 "mean": round(mean(dh_counts), 1), "median": median(dh_counts),
                 "min": min(dh_counts) if dh_counts else 0, "max": max(dh_counts) if dh_counts else 0},
    "against_counts": against_counts,
    "eras": {k: {"counts": v, "mean": round(mean(v), 1), "median": median(v)} for k, v in eras.items()},
    "by_cls": {k: {"counts": v, "mean": round(mean(v), 1), "median": median(v)} for k, v in by_cls.items()},
    "sunk": {"n": len(sunk_totals), "totals": sorted(sunk_totals),
             "mean": round(mean(sunk_totals), 1) if sunk_totals else 0,
             "median": median(sunk_totals) if sunk_totals else 0},
    "survived": {"n": len(surv_totals), "totals": sorted(surv_totals),
                 "mean": round(mean(surv_totals), 1) if surv_totals else 0,
                 "median": median(surv_totals) if surv_totals else 0},
}

with open(os.path.join(OUT, "stats.json"), "w", encoding="utf-8") as f:
    json.dump(stats, f, ensure_ascii=False, indent=2)

# ================= SVG 图表 =================

def esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def svg_bar_hits_title():
    """图1: 各舰决定性命中数条形图 (只画有 decisive_hits 的)"""
    items = sorted(dh, key=lambda s: s["decisive_hits"], reverse=True)
    H = max(20, len(items) * 34 + 60)
    W = 640
    bar_max = max(dh_counts)
    x0, y0 = 150, 20
    bw = 24
    rows = []
    for i, s in enumerate(items):
        v = s["decisive_hits"]
        y = y0 + i * 34
        wbar = (W - x0 - 60) * v / bar_max
        color = "#c0392b" if v <= 10 else "#8e44ad"
        rows.append(f'<text x="{x0-8}" y="{y+16}" text-anchor="end" font-size="11" fill="#333">{esc(s["ship"][:14])}</text>')
        rows.append(f'<rect x="{x0}" y="{y}" width="{max(wbar,2)}" height="{bw}" fill="{color}" rx="2"/>')
        rows.append(f'<text x="{x0+wbar+6}" y="{y+16}" font-size="11" fill="#333">{v}发</text>')
    return f'''<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI, Microsoft YaHei, sans-serif">
<text x="{x0}" y="12" font-size="13" font-weight="bold" fill="#222">各舰'决定命运所需命中数' (红=≤10发, 紫=>10发)</text>
{''.join(rows)}
</svg>'''

def svg_scatter_total_vs_decisive():
    """图2: 总命中数 vs 决定性命中数 散点"""
    pts = [(s["total_hits"] or 0, s["decisive_hits"] or 0, s) for s in ships
           if s["total_hits"] is not None and s["decisive_hits"] is not None]
    W, H = 640, 380
    mx = max(p[0] for p in pts) if pts else 10
    my = max(p[1] for p in pts) if pts else 10
    x0, y0, xw, yh = 70, 20, W - 90, H - 70
    rows = [f'<text x="{(W)/2}" y="12" text-anchor="middle" font-size="13" font-weight="bold" fill="#222">总命中数 vs 决定命运所需命中数 (红=最终沉没/被俘, 蓝=幸存)</text>']
    # grid
    for gx in range(0, mx + 1, max(1, mx // 8)):
        x = x0 + xw * gx / mx
        rows.append(f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0+yh}" stroke="#e0e0e0" stroke-width="1"/>')
        rows.append(f'<text x="{x}" y="{y0+yh+14}" font-size="10" fill="#888" text-anchor="middle">{gx}</text>')
    for gy in range(0, my + 1, max(1, my // 6)):
        y = y0 + yh - yh * gy / my
        rows.append(f'<line x1="{x0}" y1="{y}" x2="{x0+xw}" y2="{y}" stroke="#e0e0e0" stroke-width="1"/>')
        rows.append(f'<text x="{x0-6}" y="{y+4}" font-size="10" fill="#888" text-anchor="end">{gy}</text>')
    rows.append(f'<text x="{x0-6}" y="{y0+yh+30}" font-size="11" fill="#666" text-anchor="middle">总命中数</text>')
    rows.append(f'<text x="16" y="{y0+yh/2}" font-size="11" fill="#666" text-anchor="middle" transform="rotate(-90 16 {y0+yh/2})">决定性命中数</text>')
    # 10发参考线
    y10 = y0 + yh - yh * 10 / my
    rows.append(f'<line x1="{x0}" y1="{y10}" x2="{x0+xw}" y2="{y10}" stroke="#c0392b" stroke-width="1.5" stroke-dasharray="5,4"/>')
    rows.append(f'<text x="{x0+xw}" y="{y10-4}" font-size="10" fill="#c0392b" text-anchor="end">决定性=10发线</text>')
    for tx, ty, s in pts:
        cx = x0 + xw * tx / mx
        cy = y0 + yh - yh * ty / my
        sunk = s["outcome"] in ("sunk", "captured")
        color = "#c0392b" if sunk else "#2471a3"
        rows.append(f'<circle cx="{cx}" cy="{cy}" r="5" fill="{color}" opacity="0.85"><title>{esc(s["ship"])}: 总{tx}发 / 决定性{ty}发</title></circle>')
    return f'''<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI, Microsoft YaHei, sans-serif">
{''.join(rows)}
</svg>'''

def svg_era_means():
    """图3: 各年代决定性命中数均值(箱线风格: 均值柱+范围线)"""
    era_order = ["日俄战争(1904-05)", "一战(1914-18)", "二战(1939-45)"]
    W, H = 640, 300
    x0, y0, xw, yh = 120, 30, W - 180, H - 80
    mmax = max((max(v["counts"]) for k, v in stats["eras"].items()), default=1)
    rows = [f'<text x="{W/2}" y="16" text-anchor="middle" font-size="13" font-weight="bold" fill="#222">各年代「决定命运所需命中数」范围(竖线)与均值(柱)</text>']
    n_era = len(era_order)
    gap = xw / max(n_era, 1)
    for i, era in enumerate(era_order):
        if era not in stats["eras"]: continue
        v = stats["eras"][era]
        counts = v["counts"]
        cx = x0 + gap * i + gap / 2
        lo, hi = min(counts), max(counts)
        y_hi = y0 + yh - yh * hi / mmax
        y_lo = y0 + yh - yh * lo / mmax
        y_m = y0 + yh - yh * v["mean"] / mmax
        rows.append(f'<line x1="{cx}" y1="{y_hi}" x2="{cx}" y2="{y_lo}" stroke="#7d3c98" stroke-width="2"/>')
        rows.append(f'<rect x="{cx-14}" y="{y_m-6}" width="28" height="12" fill="#c0392b" rx="2"/>')
        rows.append(f'<text x="{cx}" y="{y_hi-6}" font-size="10" fill="#7d3c98" text-anchor="middle">范围{lo}–{hi}</text>')
        rows.append(f'<text x="{cx}" y="{y0+yh+16}" font-size="11" fill="#333" text-anchor="middle">{esc(era)}</text>')
        rows.append(f'<text x="{cx}" y="{y0+yh+32}" font-size="10" fill="#666" text-anchor="middle">均值 {v["mean"]} / 中位 {v["median"]} (n={len(counts)})</text>')
    return f'''<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI, Microsoft YaHei, sans-serif">
{''.join(rows)}
</svg>'''

def svg_outcome_bar():
    """图4: 各结局舰船数量"""
    W, H = 640, 260
    items = list(outcome_counter.items())
    x0, y0, xw, yh = 130, 30, W - 200, H - 80
    mmax = max(outcome_counter.values())
    rows = [f'<text x="{W/2}" y="16" text-anchor="middle" font-size="13" font-weight="bold" fill="#222">各结局舰船数 (n={n})</text>']
    gap = yh / max(len(items), 1)
    colors = ["#c0392b", "#e67e22", "#2471a3", "#7d3c98", "#27ae60"]
    for i, (k, v) in enumerate(items):
        y = y0 + gap * i
        wbar = (xw) * v / mmax
        rows.append(f'<text x="{x0-8}" y="{y+gap/2+4}" text-anchor="end" font-size="11" fill="#333">{OUTCOME_ZH.get(k,k)}</text>')
        rows.append(f'<rect x="{x0}" y="{y+gap/2-8}" width="{max(wbar,2)}" height="16" fill="{colors[i%len(colors)]}" rx="2"/>')
        rows.append(f'<text x="{x0+wbar+6}" y="{y+gap/2+4}" font-size="11" fill="#333">{v}艘</text>')
    return f'''<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI, Microsoft YaHei, sans-serif">
{''.join(rows)}
</svg>'''

def svg_hitrate_compare():
    """图5: 日德兰 vs 二战英军海战 大口径命中率对比 (战术主动性/交战距离维度)"""
    # (标签, 发射数, 命中数, 命中率%, 颜色)
    items = [
        ("日德兰·贝蒂战巡分队(1916)", 1469, 21, 1.43, "#95a5a6"),
        ("日德兰·英舰队总体(1916)", 4534, 123, 2.71, "#5d6d7e"),
        ("日德兰·德公海舰队(1916)", 3597, 122, 3.39, "#5d6d7e"),
        ("北角·约克公爵号(1943)", 446, 30, 6.7, "#c0392b"),
        ("俾斯麦最后一战·罗德尼+KGV(1941)", 719, 55, 7.6, "#c0392b"),
    ]
    W, H = 640, 320
    x0, y0, xw, yh = 150, 30, W - 180, H - 95
    mmax = 10.0
    rows = [f'<text x="{W/2}" y="16" text-anchor="middle" font-size="13" font-weight="bold" fill="#222">大口径命中率对比：日德兰(灰) vs 二战英军主动接战(红)</text>']
    for gx in range(0, 11, 2):
        x = x0 + xw * gx / mmax
        rows.append(f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0+yh}" stroke="#e0e0e0" stroke-width="1"/>')
        rows.append(f'<text x="{x}" y="{y0+yh+14}" font-size="9" fill="#888" text-anchor="middle">{gx}%</text>')
    gap = yh / len(items)
    for i, (label, fired, hit, rate, color) in enumerate(items):
        y = y0 + gap * i + 8
        hbar = gap * 0.62
        wbar = xw * rate / mmax
        rows.append(f'<text x="{x0-8}" y="{y+hbar/2+4}" text-anchor="end" font-size="10.5" fill="#333">{esc(label)}</text>')
        rows.append(f'<rect x="{x0}" y="{y}" width="{max(wbar,2)}" height="{hbar}" fill="{color}" rx="2"/>')
        rows.append(f'<text x="{x0+wbar+6}" y="{y+hbar/2+4}" font-size="10.5" fill="#333">{rate}% ({hit}/{fired}发)</text>')
    return f'''<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI, Microsoft YaHei, sans-serif">
{''.join(rows)}
</svg>'''

def svg_cost_ratio():
    """图6: 第二周期「攻击成本 vs 防御成本」交换比 (对数-对数刻度)"""
    import math
    def usd_label(e):
        m = {3: "$1K", 4: "$10K", 5: "$100K", 6: "$1M", 7: "$10M", 8: "$100M", 9: "$1B", 10: "$10B"}
        return m.get(e, f"$10^{e}")
    pts = [
        ("胡塞自杀无人机 vs SM-2", 2_000, 2_100_000),
        ("沙希德-136 vs SM-6", 20_000, 4_000_000),
        ("海王星 vs 莫斯科号(整舰)", 1_000_000, 2_000_000_000),
        ("反舰导弹 vs 林肯号航母(整舰)", 1_000_000, 13_000_000_000),
    ]
    W, H = 640, 415
    x0, y0, xw, yh = 150, 30, W - 190, H - 115
    lo, hi = 3.0, 10.5
    def X(v): return x0 + xw * (math.log10(v) - lo) / (hi - lo)
    def Y(v): return y0 + yh - yh * (math.log10(v) - lo) / (hi - lo)
    rows = [f'<text x="{W/2}" y="14" text-anchor="middle" font-size="13" font-weight="bold" fill="#222">第二周期「攻击成本 vs 防御成本」交换比（对数刻度；点越在对角线下方，防御越贵、越不可持续）</text>']
    for e in range(int(lo), int(hi) + 1):
        x, y = X(10 ** e), Y(10 ** e)
        rows.append(f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0+yh}" stroke="#e0e0e0" stroke-width="1"/>')
        rows.append(f'<line x1="{x0}" y1="{y}" x2="{x0+xw}" y2="{y}" stroke="#e0e0e0" stroke-width="1"/>')
        rows.append(f'<text x="{x}" y="{y0+yh+14}" font-size="9" fill="#888" text-anchor="middle">{usd_label(e)}</text>')
        rows.append(f'<text x="{x0-6}" y="{y+4}" font-size="9" fill="#888" text-anchor="end">{usd_label(e)}</text>')
    rows.append(f'<line x1="{X(10**lo)}" y1="{Y(10**lo)}" x2="{X(10**hi)}" y2="{Y(10**hi)}" stroke="#7f8c8d" stroke-width="1.5" stroke-dasharray="5,4"/>')
    rows.append(f'<text x="{X(10**8.5)}" y="{Y(10**8.5)-5}" font-size="10" fill="#7f8c8d" text-anchor="middle">1:1 等成本线（线上=对等，线下=防御更贵）</text>')
    colors = ["#c0392b", "#c0392b", "#e67e22", "#e67e22"]
    for (label, ac, dc), color in zip(pts, colors):
        cx, cy = X(ac), Y(dc)
        ac_s = f"${ac/1000:.0f}K" if ac < 1e6 else f"${ac/1e6:.0f}M"
        dc_s = f"${dc/1e6:.0f}M" if dc < 1e9 else f"${dc/1e9:.1f}B"
        rows.append(f'<circle cx="{cx}" cy="{cy}" r="7" fill="{color}" stroke="#fff" stroke-width="1.5"/>')
        rows.append(f'<text x="{cx+10}" y="{cy-6}" font-size="10" font-weight="bold" fill="#333">{ac_s} → {dc_s}</text>')
        rows.append(f'<text x="{cx+10}" y="{cy+7}" font-size="10" fill="#666">{esc(label)}</text>')
    rows.append(f'<text x="{x0}" y="{y0+yh+32}" font-size="10" fill="#555">横轴=攻击方单发成本，纵轴=防御方单次成本：红海常态约 1000:1 倒挂；整舰级对比中海王星/反舰导弹以百万级代价消耗十亿级平台（莫斯科号、林肯号）。</text>')
    return f'''<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI, Microsoft YaHei, sans-serif">
{''.join(rows)}
</svg>'''

def svg_loop_control():
    """图7: 开环预测 vs 在线控制 —— 两个周期破局机制的对照"""
    W, H = 640, 500
    rows = [f'<text x="{W/2}" y="16" text-anchor="middle" font-size="13" font-weight="bold" fill="#222">同一个破解公式：开环预测 vs 在线控制（控制回路的位置，决定命中率与成本）</text>']
    rows.append('<defs><marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="#185FA5"/></marker></defs>')
    lx, ly, lw, lh = 20, 40, 205, 370
    rows.append(f'<rect x="{lx}" y="{ly}" width="{lw}" height="{lh}" rx="8" fill="#fdf3f3" stroke="#c0392b" stroke-width="1.5"/>')
    rows.append(f'<text x="{lx+lw/2}" y="{ly+20}" text-anchor="middle" font-size="12" font-weight="bold" fill="#c0392b">开环预测</text>')
    rows.append(f'<text x="{lx+lw/2}" y="{ly+35}" text-anchor="middle" font-size="9.5" fill="#666">舰炮时代 1906–1980s</text>')
    steps = ["① 测距测向（光学/雷达）", "② 火控解算（匀速直线假设）", "③ 一次性装定射击诸元", "④ 开火", "⑤ 弹道飞行 40–60 秒", "⑥ 目标蛇形机动→解算作废", "⑦ 等落点（校射轮次稀疏）", "⑧ 15km+ 间接瞄准 = 开环"]
    for i, st in enumerate(steps):
        yy = ly + 54 + i * 34
        rows.append(f'<text x="{lx+12}" y="{yy}" font-size="10" fill="#333">{st}</text>')
        if i < len(steps) - 1:
            rows.append(f'<line x1="{lx+lw/2}" y1="{yy+8}" x2="{lx+lw/2}" y2="{yy+26}" stroke="#c0392b" stroke-width="1" opacity="0.45"/>')
    rows.append(f'<text x="{lx+lw/2}" y="{ly+lh-12}" text-anchor="middle" font-size="11" font-weight="bold" fill="#c0392b">命中率 2–3%，80 年未变</text>')
    fx = 242
    rows.append(f'<path d="M {fx} {ly+50} C {fx-16} {ly+50} {fx-16} {ly+lh-40} {fx} {ly+lh-40}" stroke="#185FA5" stroke-width="2.5" fill="none" marker-end="url(#arr)"/>')
    rows.append(f'<text x="{fx}" y="{ly+lh/2+4}" text-anchor="middle" font-size="10" fill="#185FA5" transform="rotate(90 {fx} {ly+lh/2})">反馈回路</text>')
    rx, ry, rw, rh = 268, 40, 352, 172
    rows.append(f'<rect x="{rx}" y="{ry}" width="{rw}" height="{rh}" rx="8" fill="#eafaf1" stroke="#27ae60" stroke-width="1.5"/>')
    rows.append(f'<text x="{rx+14}" y="{ry+22}" font-size="12" font-weight="bold" fill="#1e8449">在线控制 ① 俯冲轰炸「人在回路」（1942 中途岛）</text>')
    lines = [
        "· 飞行员目视目标，持续修正航迹与投弹时机",
        "· 控制回路闭合到末端：投弹瞬间=最后一次修正",
        "· 载体把「射程」变成「飞到目标头顶」",
        "· 人把「落点」变成「实时反馈」，不再赌概率",
    ]
    for i, ln in enumerate(lines):
        rows.append(f'<text x="{rx+14}" y="{ry+46+i*26}" font-size="10.5" fill="#333">{ln}</text>')
    rows.append(f'<text x="{rx+14}" y="{ry+rh-12}" font-size="11" font-weight="bold" fill="#1e8449">命中率 15–33%（39 架 SBD，8 发直接命中）</text>')
    ry2, rh2 = 224, 186
    rows.append(f'<rect x="{rx}" y="{ry2}" width="{rw}" height="{rh2}" rx="8" fill="#eaf2fb" stroke="#2471a3" stroke-width="1.5"/>')
    rows.append(f'<text x="{rx+14}" y="{ry2+22}" font-size="12" font-weight="bold" fill="#1a5276">在线控制 ② 分布式蜂群「人在回路」（2022–26）</text>')
    lines2 = [
        "· TB-2 诱骗防空雷达 → 海王星掠海突防（莫斯科号）",
        "· 无人艇蜂群夜袭塞瓦斯托波尔港",
        "· 2,000 美元无人机 vs 200 万美元 SM-2：饱和攻击数学上拦不住",
        "· 控制回路铺满战场：廉价载体批量携带「末端修正」",
    ]
    for i, ln in enumerate(lines2):
        rows.append(f'<text x="{rx+14}" y="{ry2+46+i*26}" font-size="10.5" fill="#333">{ln}</text>')
    rows.append(f'<text x="{rx+14}" y="{ry2+rh2-12}" font-size="11" font-weight="bold" fill="#1a5276">攻击成本 &lt; 防御成本：拦截方先破产</text>')
    bx, by, bw, bh = 20, 428, 600, 56
    rows.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="8" fill="#1a252f"/>')
    rows.append(f'<text x="{bx+bw/2}" y="{by+24}" text-anchor="middle" font-size="12" font-weight="bold" fill="#fff">两个周期、同一个公式：把控制回路从「中央一次性解算」推到「末端实时修正」</text>')
    rows.append(f'<text x="{bx+bw/2}" y="{by+44}" text-anchor="middle" font-size="10.5" fill="#ddd">贵的开环预测输给便宜的闭环修正——战列舰输给俯冲轰炸机，航母输给蜂群</text>')
    return f'''<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI, Microsoft YaHei, sans-serif">
{''.join(rows)}
</svg>'''

charts = {
    "bar_hits": svg_bar_hits_title(),
    "scatter": svg_scatter_total_vs_decisive(),
    "era": svg_era_means(),
    "outcome": svg_outcome_bar(),
    "hitrate": svg_hitrate_compare(),
    "cost": svg_cost_ratio(),
    "loop": svg_loop_control(),
}

# ================= HTML 报告 =================
d = stats

# ---- 第八章: 第二周期 (2022-2026 证伪) ----
CH8 = f"""
<h2>八、第二周期：冷战后「肥胖化」重演与 2022–2026 的证伪</h2>
<p>第一周期（战列舰）终结时留下的「标准答案」是：航母+导弹取代巨炮。但被继承下来的其实是同一个错误——<b>把问题归咎于「还不够大、不够贵、不够远」，而不是「精度与距离、成本与存在的系统性矛盾」</b>。于是同样的反馈回路换了宿主，再转一圈：</p>
<div class="loop">
<b>① 福克兰(1982)与海湾战争(1991)「证明」了导弹时代航母舰队的价值</b>——谢菲尔德号被 1 枚飞鱼击沉的教训，被翻译成「需要更大更贵更好的盾」，而不是「也许该重新考虑要不要造这么贵的东西」；<br/>
<b>② 冷战后造舰竞赛</b>——尼米兹级（单舰约 45 亿美元）→ 福特级（单舰 130 亿+，超支过半）；提康德罗加级巡洋舰 → 朱姆沃尔特级（单价约 75 亿，造 3 艘即停产）；F-22 → F-35（全生命周期约 1.7 万亿美元，人类史上最贵武器项目）；「巨型导弹」标准-6 单枚 400 万美元，高超音速计划一再延期超支；<br/>
<b>③ 更大更贵 → 数量锐减</b>——美国海军舰艇总数从冷战高峰约 590 艘跌至不足 300 艘，「355 艘舰队」目标始终凑不齐，单舰「不可损失」程度史无前例；<br/>
<b>④ 更损失不起 → 存在性使用</b>——核动力航母从战术武器退化为「不能损失的威慑资产」，部署=展示=熬时间，与提尔皮茨趴在挪威峡湾、大和巡游特鲁克同构；<br/>
<b>⑤ 递归错误重演</b>——第一周期放大「炮与装甲」、忽略「精度∝1/距离」；第二周期放大「平台尺寸/导弹射程/战机单价」，忽略「拦截成本∝攻击成本」与「平台越大、廉价精确弹药越划算」——循环回到①，每转一圈更贵、更少、更不敢用。</div>

<h3>证伪三部曲：黑海(2022) → 红海(2023-24) → 波斯湾(2026)</h3>
<table>
<tr><th>战场/时间</th><th>巨型平台</th><th>廉价攻击手段</th><th>结果</th><th>成本对比</th></tr>
<tr><td>黑海 2022.4.13</td><td>莫斯科号·光荣级巡洋舰（满载 11,674 吨，黑海舰队旗舰；S-300FM「堡垒」64 枚备弹+黄蜂-M 近防）</td><td>TB-2 无人机诱骗雷达 + 电子战干扰 + 2 枚海王星掠海反舰导弹（飞行高度约 3 米，近舰 10-15km 才被发现）</td><td>防空体系被「欺骗-突防」组合击穿，P-1000 弹药库殉爆连锁反应，拖曳中沉没——<b>二战后被反舰导弹击沉的最大吨位军舰</b></td><td>单枚海王星约 100 万美元（媒体称不足整舰造价 0.1%），摧毁的是整支舰队的旗舰</td></tr>
<tr><td>红海 2023.12-2024</td><td>卡尼号/格雷夫利号等阿利·伯克级驱逐舰</td><td>胡塞自杀无人机（约 2,000 美元）、沙希德-136（约 2 万美元）、反舰弹道导弹</td><td>「拦截成功率 100%」但成本倒挂：SM-2 约 210-250 万美元/枚、SM-6 约 400 万+、海麻雀约 100-180 万；卡尼号单日拦截 14 架；最终美军被迫「直击源头」轰炸也门——因为数学上拦不起了</td><td><b>约 1000:1</b>（2000 美元 vs 200 万美元）；「干掉弓箭手总比拦弓箭便宜」</td></tr>
<tr><td>波斯湾 2026.2-8（「史诗怒火」行动）</td><td>林肯号核动力航母；特拉克斯顿/拉斐尔·佩拉尔塔/梅森三艘驱逐舰</td><td>卡德尔-380 反舰导弹（射程约 1000km、强抗干扰）、反舰弹道导弹+无人机+小艇混合饱和</td><td>3 月 1 日 4 枚反舰导弹瞄准林肯号（300km 内）→ 航母紧急掉头撤往印度洋；3 月 4 日卡德尔-380 在约 600km 外命中美军驱逐舰与油轮（「以为安全的安全距离」被证伪）；5 月 7 日三艘驱逐舰穿越霍尔木兹时遭导弹+无人机+小艇围攻；8 月林肯号连续 250 天不靠港、200+ 天连续执勤，舰上食品牙膏短缺、饮用水污染、<b>多名船员精神崩溃、跳海自杀未遂</b>，参议员质询</td><td>数枚百万美元级导弹，迫使 130 亿美元级航母改变部署、消耗 5000 名船员</td></tr>
</table>

<div class="warn"><b>2026 波斯湾的证伪方式值得玩味：巨舰没有被击沉——而是被「消耗」。</b><br/>
① 林肯号不是被导弹摧毁，而是被<b>存在性威胁</b>困住：伊朗用「我能打到你」取代了「我打中了你」——4 枚导弹逼退航母、卡德尔-380 千里外点名，让巨型平台每时每刻都处在「是否值得暴露」的博弈里；<br/>
② 250 天不靠港、船员精神崩溃、物资断供——这是<b>「存在即价值」的代价表</b>：一艘不能靠港的航母，本质上是一座漂浮的、耗尽的军营，与日德兰之后「损失不起所以束之高阁」的战列舰共享同一命运逻辑；<br/>
③ 双方口径自相矛盾（美军中央司令部称「美方资产未遭受任何命中」，伊朗革命卫队称「重大损失、3 舰撤离」）——这正是巨型平台政治的典型特征：<b>在信息战里，巨舰的存在本身成了宣传符号，物理命中与否反而次要</b>；<br/>
④ 霍尔木兹海峡的僵局（伊朗宣称「完全掌控」、美防长宣称「无限期维持」封锁）是日德兰式「点到为止」的现代翻版：双方都输不起，于是都选择「继续存在」而不是「决战」——战列舰时代的循环，在航母身上完整重演了一遍。</div>

<h3>两个周期，同一张底片</h3>
<table>
<tr><th>维度</th><th>第一周期：战列舰(1906-1945)</th><th>第二周期：航母+导弹舰(1980s-2026)</th></tr>
<tr><td>被递归放大的内部指标</td><td>炮的口径、装甲厚度</td><td>平台吨位/造价、导弹射程、战机单价（F-35 全周期 1.7 万亿美元）</td></tr>
<tr><td>被系统性忽略的外部约束</td><td>精度∝1/距离（15km+ 开环间接瞄准，命中率 2-3%）</td><td>拦截成本&gt;攻击成本（200 万 vs 2000 美元）；平台越大、被廉价精确弹药抵消得越快</td></tr>
<tr><td>决定性破局者</td><td>俯冲轰炸机——「人在回路的在线控制」（命中率 15-33%）</td><td>无人机/无人艇/廉价反舰导弹——「分布式在线控制」（TB-2 诱骗+海王星、无人艇蜂群、见证者-136 饱和）</td></tr>
<tr><td>破局者成本</td><td>一架 SBD &lt; 一枚 460mm 炮弹的零头</td><td>一架自杀无人机 2,000 美元 vs 一枚 SM-2 约 200 万美元（1000:1）</td></tr>
<tr><td>巨型平台的最终命运</td><td>束之高阁：威慑资产（提尔皮茨/大和）</td><td>被消耗：250 天不靠港、船员崩溃、弹药与人力双枯竭——「存在即价值、用则不划算」</td></tr>
</table>

<div class="chart">{charts['cost']}</div>
<div class="chart">{charts['loop']}</div>

<div class="warn"><b>最终裁决（第二周期）：</b>第一周期死于「命中率与距离的矛盾」，第二周期死于「成本与存在的矛盾」。两个周期共享同一个根错误：<b>用内部的放大指标（炮/装甲/平台/单价）去回应外部约束（距离/成本/时间），而不是改变约束本身</b>。而破局者永远是同一个公式：<b>把控制回路从中央推到末端——让人或廉价载体「在回路里」实时修正</b>。俯冲轰炸机如此，海王星+TB-2 的组合如此，2,000 美元的无人机让 200 万美元的导弹破产亦如此。战列舰不是被航母淘汰的，是被「开环」淘汰的；航母与导弹舰如今正在被「闭环的廉价蜂群」淘汰——<b>这不是武器竞赛，这是控制回路竞赛</b>。</div>
"""

def rows_html():
    trs = []
    for s in ships:
        db = {True: "支持", False: "反例", "partial": "部分支持", None: "—"}[s["decided_by_10"]]
        db_color = {"支持": "#27ae60", "反例": "#c0392b", "部分支持": "#e67e22", "—": "#999"}[db]
        trs.append(
            f"<tr>"
            f"<td>{esc(s['battle'])}<br/><span style='color:#888;font-size:11px'>{esc(s['year'])}</span></td>"
            f"<td>{esc(s['ship'])}<br/><span style='color:#888;font-size:11px'>{CLS_ZH.get(s['cls'],s['cls'])}</span></td>"
            f"<td>{s['total_hits'] if s['total_hits'] is not None else '—'}</td>"
            f"<td>{s.get('main_hits') if s.get('main_hits') is not None else '—'}</td>"
            f"<td>{s['decisive_hits'] if s['decisive_hits'] is not None else '—'}</td>"
            f"<td style='text-align:left'>{esc(s['critical_loc'])}</td>"
            f"<td>{OUTCOME_ZH.get(s['outcome'], s['outcome'])}</td>"
            f"<td><span style='color:{db_color};font-weight:bold'>{db}</span></td>"
            f"<td style='text-align:left;font-size:11px;color:#555'>{esc(s['note'])}</td>"
            f"</tr>")
    return "".join(trs)

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>战列舰炮战命中数据分析报告 (1904-1945)</title>
<style>
  body {{ font-family: "Segoe UI", "Microsoft YaHei", sans-serif; margin: 0; background: #f5f6fa; color: #2c3e50; }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
  h1 {{ color: #1a252f; border-bottom: 3px solid #c0392b; padding-bottom: 10px; }}
  h2 {{ color: #1a252f; margin-top: 36px; border-left: 4px solid #c0392b; padding-left: 10px; }}
  .cards {{ display: flex; flex-wrap: wrap; gap: 14px; margin: 18px 0; }}
  .card {{ flex: 1; min-width: 160px; background: #fff; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  .card .num {{ font-size: 28px; font-weight: 700; color: #c0392b; }}
  .card .lbl {{ font-size: 12px; color: #7f8c8d; margin-top: 4px; }}
  .verdict {{ background: #fff; border-radius: 8px; padding: 18px 22px; box-shadow: 0 1px 4px rgba(0,0,0,.08); margin: 18px 0; }}
  .verdict h3 {{ margin-top: 0; color: #1a252f; }}
  .ok {{ color: #27ae60; font-weight: 700; }} .bad {{ color: #c0392b; font-weight: 700; }} .mid {{ color: #e67e22; font-weight: 700; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; font-size: 12px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  th, td {{ border: 1px solid #e3e7ee; padding: 6px 8px; text-align: center; }}
  th {{ background: #2c3e50; color: #fff; }}
  tr:nth-child(even) {{ background: #f8f9fb; }}
  .chart {{ background: #fff; border-radius: 8px; padding: 14px; box-shadow: 0 1px 4px rgba(0,0,0,.08); margin: 12px 0; }}
  .chart svg {{ width: 100%; height: auto; }}
  .foot {{ color: #95a5a6; font-size: 12px; margin-top: 30px; border-top: 1px solid #dcdde1; padding-top: 12px; }}
  .warn {{ background: #fef9e7; border-left: 4px solid #f39c12; padding: 10px 14px; border-radius: 4px; margin: 12px 0; font-size: 13px; }}
  .loop {{ background: #fff; border-left: 4px solid #185FA5; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 4px rgba(0,0,0,.08); margin: 14px 0; font-size: 13px; line-height: 2.0; }}
</style>
</head>
<body>
<div class="wrap">
<h1>战列舰炮战命中数据分析：检验「头5-10次命中决定战局」假说</h1>
<p style="color:#555">覆盖范围：日俄战争(1904-05) → 一战 → 二战结束(1945)，共 <b>{d['n']}</b> 条战舰被命中记录（黄海/对马/科罗内尔/福克兰/多格尔沙洲/日德兰/卡拉布里亚/梅尔斯埃尔凯比尔/达喀尔/丹麦海峡/俾斯麦最后一战/卡萨布兰卡/两次瓜岛/北角/苏里高/萨马岛，全部来自清洗后的维基战史语料）。</p>

<h2>一、核心结论</h2>
<div class="verdict">
<h3>假说检验：部分成立 —— 「决定性命中」远少于「总命中数」</h3>
<p>
在 <b>{d['decisive']['n']}</b> 条命运已定且能识别决定性命中的记录中，<span class="ok">有 {d['decisive']['le10']} 条（{d['decisive']['le10_pct']}%）的决定性命中发生在 ≤10 发之内</span>；
其中 ≤5 发的有 {d['decisive']['le5']} 条（{d['decisive']['le5_pct']}%）。<b>决定性命中数的中位数为 {d['decisive']['median']} 发，均值 {d['decisive']['mean']} 发</b>。
</p>
<p>
若把「被击中后是否在10发内命运已定」作为判据：<span class="ok">明确支持 {d['support']} 条</span>、<span class="bad">明确反例 {d['against']} 条</span>、<span class="mid">部分支持 {d['partial']} 条</span>、无法判定 {d['unknown']} 条。
严格支持率（支持/(支持+反例)）= <b>{d['strict_support_pct']}%</b>；若把「部分支持」计入（决定性命中发生早、但总命中大），支持面为 <b>{d['support_plus_partial_pct']}%</b>。
</p>
<div class="warn"><b>口径与补刀辨析（本报告的方法论核心）：</b><br/>
① <b>「全部命中」≠「大口径命中」≠「决定性命中」</b>——决定命运的是大口径穿甲弹/要害命中（司令塔、弹药库、舵机、火控、动力），而非命中总数；<br/>
② <b>补刀效应</b>：被击沉舰的决定性命中几乎都发生在早期（俾斯麦开火15分钟内指挥/火控/前炮塔全灭、比睿2发8in毁舵、雾岛约7分钟内主炮塔+舵全灭、布吕歇尔第一轮13.5in命中即丧失速度），其后数百发命中多为补刀；<br/>
③ <b>幸存反例的机制</b>：命中多仍幸存 = 防御厚度 + 损管 + <b>弹药性质</b> + 命中位置运气。典型如南达科他号（本版已由反例改判支持）：27发中14in仅6发，且雾岛按对岸炮击准备装的是三式烧夷弹（仅1发穿甲弹）、减装药、多弹未爆，前5发14in已摧毁雷达/火控/通信=战术出局；不沉是穿甲弹极少+三式弹无法穿透其装甲的结果，而非"头几次命中无效"；<br/>
④ <b>弹径威力差距（210mm vs 12in+）</b>：好望角挨35发210mm才殉爆、福克兰英战巡挨40发210mm几乎无损，而博罗季诺仅1发12in命中弹药库即全舰殉爆（除1人）、胡德1发38cm殉爆——前无畏舰以副炮对射为主（对马射程4000-6000米，三笠挨30发未掉速、东乡未死），正是大口径的一发定局优势催生了无畏级"全主炮"革命；<br/>
⑤ <b>命中部位决定命运（水线下 vs 水线上）</b>：吕佐夫船头水线下中炮→进水不可控→夜间自沉；塞德利茨24发、德芙林格尔20发均水线上中弹仍幸存——同口径弹，水线下命中几乎必致命；<br/>
⑥ <b>过穿效应（命中数量失效的极端案例）</b>：萨马岛海战大和号约20,300码对误判为巡洋舰的约翰斯顿号（弗莱彻级驱逐舰，舰型高大）整轮齐射，3发460mm穿甲弹+3发155mm共<b>6发全中</b>——但460mm穿甲弹引信按重装甲目标延迟起爆，穿过19mm薄壳舰体过穿未爆，约翰斯顿未立即瘫痪、继续作战数小时（155mm仅撕碎上层建筑）；金刚号当时被雨幕遮蔽未开火（美军最初误记为"金刚14in"）。同一轮齐射命中率100%却近乎无效——<b>命中质量（引信×装甲匹配、过穿与否）决定效果，而非命中数量</b>；<br/>
⑦ <b>战术主动性与交战距离（二战英军）</b>：日德兰英方命中率仅2.71%（贝蒂分队1.43%），二战英军主动拉近距离——北角约克公爵逼近11km开火命中率约6.7%、俾斯麦最后一战罗德尼贴脸2.5-4km命中率约7.6%（罗德尼单舰~10%）——距离是命中率与致命性的放大器，"头5-10发决定论"在英军主动接战战术下被进一步强化（详见"三之三"）；<br/>
⑧ <b>「命中率」不等于「决定命运」</b>：苏里高海峡美军战列舰发射285发炮弹仅2发命中、约4000发巡洋舰炮弹命中不足10发（据日方生还者报告），西弗吉尼亚首轮齐射即命中但山城/扶桑直接死因均为鱼雷——雷达火控只是提升"首轮命中"概率，炮战本身未决定命运；<br/>
⑨ 结论：<b>「头5-10次命中决定战局」成立的前提是命中质量（弹种×部位×口径×穿透），而不是命中数量本身</b>。</div>
</div>

<div class="cards">
  <div class="card"><div class="num">{d['decisive']['median']}</div><div class="lbl">决定性命中数·中位数(发)</div></div>
  <div class="card"><div class="num">{d['decisive']['le10_pct']}%</div><div class="lbl">≤10发内决定命运的比例</div></div>
  <div class="card"><div class="num">{d['strict_support_pct']}%</div><div class="lbl">严格支持率(支持/支持+反例)</div></div>
  <div class="card"><div class="num">{d['support']}</div><div class="lbl">明确支持案例数</div></div>
  <div class="card"><div class="num">{d['against']}</div><div class="lbl">明确反例案例数</div></div>
  <div class="card"><div class="num">{d['decisive']['min']}–{d['decisive']['max']}</div><div class="lbl">决定性命中数范围(发)</div></div>
</div>

<h2>二、数据图表</h2>
<div class="chart">{charts['bar_hits']}</div>
<div class="chart">{charts['scatter']}</div>
<div class="chart">{charts['era']}</div>
<div class="chart">{charts['outcome']}</div>

<h2>三、时代差异</h2>
<table>
<tr><th>时代</th><th>案例数</th><th>决定性命中数范围</th><th>均值</th><th>中位数</th><th>解读</th></tr>
<tr><td>日俄战争(1904-05)</td><td>{len(eras['日俄战争(1904-05)'])}</td><td>{min(eras['日俄战争(1904-05)'])}–{max(eras['日俄战争(1904-05)'])}</td><td>{stats['eras']['日俄战争(1904-05)']['mean']}</td><td>{stats['eras']['日俄战争(1904-05)']['median']}</td><td>副炮对射为主(4000-6000米), 小口径命中多但无效(三笠30发未掉速/东乡未死); 大口径主炮一发定局: 博罗季诺1发12in殉爆、苏沃洛夫司令塔被端指挥崩溃——催生无畏级全主炮革命</td></tr>
<tr><td>一战(1914-18)</td><td>{len(eras['一战(1914-18)'])}</td><td>{min(eras['一战(1914-18)'])}–{max(eras['一战(1914-18)'])}</td><td>{stats['eras']['一战(1914-18)']['mean']}</td><td>{stats['eras']['一战(1914-18)']['median']}</td><td>英国战列巡洋舰5-7发殉爆(薄甲+弹药管理差)，德国舰18-24发仍存(厚甲+损管)</td></tr>
<tr><td>二战(1939-45)</td><td>{len(eras['二战(1939-45)'])}</td><td>{min(eras['二战(1939-45)'])}–{max(eras['二战(1939-45)'])}</td><td>{stats['eras']['二战(1939-45)']['mean']}</td><td>{stats['eras']['二战(1939-45)']['median']}</td><td>雷达火控+大威力弹, 决定性命中往往1-2发(胡德/敦刻尔克/卡拉布里亚); 但苏里高285发战列舰炮弹仅2中(死因为鱼雷)与萨马岛大和6发全中却过穿无效, 证明命中质量仍是决定性变量</td></tr>
</table>

<h2>三之二、口径构成与补刀效应</h2>
<p style="color:#555">下表把「总命中数」拆解为「大口径主炮命中」与「决定性命中」两个层次，展示命中质量如何决定命运。标 * 的一行（好望角）为反例语义：其「决定性命中」=总命中数，意为"挨了这么多发才沉"，归因于对手210mm弹径威力不足。</p>
<table>
<tr><th>舰船</th><th>总命中</th><th>大口径主炮命中</th><th>决定性命中</th><th>说明</th></tr>
<tr><td>南达科他号 (1942)</td><td>27</td><td>6发14in(仅1发AP)</td><td>5</td><td>前5发14in(三式弹+1发AP)摧毁雷达/火控/通信/后炮塔机构→战术出局; 不沉=穿甲弹极少+三式弹不穿甲+命中集中上层建筑</td></tr>
<tr><td>鹰号 (1905)</td><td>74</td><td>5发12in</td><td>—</td><td>主炮命中仅5发, 其余为中小口径; 俄式水密隔舱使其不沉——总命中数在此具误导性</td></tr>
<tr><td>雾岛号 (1942)</td><td>37</td><td>20发16in</td><td>13</td><td>决定性损伤(4主炮塔+舵全灭)在约7分钟内完成, 其后为补刀</td></tr>
<tr><td>俾斯麦号 (1941)</td><td>~400</td><td>—</td><td>10</td><td>决定性=开火15分钟内指挥/火控/前炮塔全灭; 后续约390发+5鱼雷均为补刀</td></tr>
<tr><td>比睿号 (1942)</td><td>85</td><td>—</td><td>2</td><td>决定性=2发8in击中舵机舱, 丧失机动后无法逃脱, 被集火击沉</td></tr>
<tr><td>布吕歇尔号 (1915)</td><td>85</td><td>—</td><td>2</td><td>第一轮13.5in命中后即彻底丧失速度(战术出局), 其后70-100发+鱼雷均为补刀; 已由"85发强反例"改判部分支持</td></tr>
<tr><td>好望角号 (1914)</td><td>35</td><td>—</td><td>35*</td><td>对手沙恩霍斯特级主炮为210mm(威力不足), 35发累积至弹药库命中才殉爆; 弹径不足型反例</td></tr>
<tr><td>约翰斯顿号 (1944)</td><td>6</td><td>3发460mm(大和)</td><td>0</td><td>大和号20,300码整轮齐射6发全中(3发460mm AP+3发155mm), 但460mm穿甲弹过穿未爆、155mm仅伤上层建筑——命中率100%却未决定命运; 决定性的是后续集火(累计20+发)</td></tr>
</table>

<h2>三之三、战术主动性与交战距离：二战英军为何命中率翻倍</h2>
<div class="chart">{charts['hitrate']}</div>
<p style="color:#555"><b>核心观察：</b>皇家海军在二战有把握的战列舰炮战中普遍采取"<b>取得优势后主动压缩距离</b>"战术——北角海战约克公爵在45,500码雷达发现沙恩霍斯特后主动逼近至12,000码才开火；俾斯麦最后一战罗德尼在09:02决定性齐射摧毁其火控后直接贴脸到2,500–4,000米。结果是：命中率从日德兰的 <b>2.71%</b>（贝蒂战巡分队仅1.43%）跃升至 <b>6.7%–7.6%</b>，且决定性命中发生得更早、更密集。</p>
<table>
<tr><th>海战</th><th>英方主力</th><th>发射(大口径)</th><th>命中</th><th>命中率</th><th>开火/决定性距离</th><th>战术机制</th></tr>
<tr><td>日德兰(1916)</td><td>英舰队总体</td><td>4,534</td><td>123</td><td>2.71%</td><td>8–15km(远距对射为主)</td><td>射控原始+编队纪律束缚+能见度差; 贝蒂战巡分队仅1.43%——远距离对射时代</td></tr>
<tr><td>北角(1943)</td><td>约克公爵号</td><td>446</td><td>~30(一说13)</td><td>~6.7%(保守口径~2.9%)</td><td>雷达发现45,500码→主动逼近12,000码(11km)开火</td><td>Type284雷达火控→北极雪暴夜战仍精确测距; 沙恩霍斯特前雷达早毁、光学在雪暴中失效成"半盲"; 首轮齐射即命中瘫痪前炮塔</td></tr>
<tr><td>俾斯麦最后一战(1941)</td><td>罗德尼+KGV</td><td>~719</td><td>~55</td><td>~7.6%(罗德尼~10%/KGV~5%)</td><td>20km开火→罗德尼贴脸2,500–4,000m</td><td>09:02罗德尼16in齐射摧毁舰桥/火控后, 罗德尼逼近至"几乎不可能脱靶"的贴脸距离, 逐发点名; 距离=命中率与穿透力的放大器</td></tr>
</table>
<div class="warn"><b>为什么英军敢拉近距离？</b><br/>
① <b>雷达火控革命</b>：Type 284/274 雷达让英军能在夜间、雪暴、烟雾中精确测距测向；而德军（沙恩霍斯特FuMO、俾斯麦火控）一旦雷达受损或天气恶劣就退回光学时代——"看得见"才敢贴上去，这是与日德兰最本质的差别；<br/>
② <b>"close action"战术文化</b>：自纳尔逊时代"贴近敌人"的传统 + 日德兰后皇家海军炮术改革的直接成果（集中射击指挥仪普及、训练改革）；<br/>
③ <b>距离-命中率物理</b>：弹道散布与射程正相关，距离减半命中概率约×4；近距弹道平直、穿甲弹存速高穿透强——弹药库/水线命中概率与破坏力同步上升；<br/>
④ <b>决定性打击后立即贴脸补刀</b>：俾斯麦09:02火控全灭后罗德尼冲到2.5–4km、北角18:20锅炉舱命中后驱逐舰群抵近2,100–2,800码鱼雷齐射——这正是"头5-10发决定战局"的战术放大：<b>决定性命中一旦出现，主动压缩距离就成为加速处决的工具</b>。</div>
<p style="color:#555"><b>限定与反例：</b>丹麦海峡=英军主动拦截，但德军15km级远射先命中（胡德1发殉爆），说明主动接近亦有风险；卡拉布里亚=厌战号26,000码(23.8km)超远命中纪录，说明远距离并非不能命中、而是效率与破坏力双低；梅尔斯埃尔凯比尔=英军对锚地法舰约14km开火，属"压制射击+近距补枪"混合。整体上，二战英军有把握的炮战，其开火距离与决定性距离均显著小于日德兰——<b>同一支海军，把命中率从约2.7%打到7%上下，靠的不是运气而是主动拉近距离×雷达火控</b>。</p>

<h2>四、支持与部分支持案例（决定性命中发生早）</h2>
<table>
<tr><th>海战</th><th>舰船</th><th>总命中(大口径)</th><th>决定性命中</th><th>要害部位</th><th>结局</th><th>判据</th></tr>
{''.join(f"<tr><td>{esc(s['battle'])} ({s['year']})</td><td>{esc(s['ship'])}</td><td>{s['total_hits'] if s['total_hits'] is not None else '—'}发({s.get('main_hits') if s.get('main_hits') is not None else '—'})</td><td><b>{s['decisive_hits'] if s['decisive_hits'] is not None else '—'}发</b></td><td>{esc(s['critical_loc'])}</td><td>{OUTCOME_ZH.get(s['outcome'],s['outcome'])}</td><td><span style='color:{'#27ae60' if s['decided_by_10'] is True else '#e67e22'};font-weight:bold'>{'支持' if s['decided_by_10'] is True else '部分支持'}</span></td></tr>" for s in support + partial)}
</table>
<p style="color:#555">注：部分支持 = 决定性命中发生早（≤10发），但总命中数大或沉没被推迟（补刀效应），如俾斯麦（决定性在开火15分钟内，总命中~400）、布吕歇尔（第一轮13.5in命中即丧失速度，总命中85）。</p>

<h2>五、反例（5-10发区间内命中仍未决定命运 / 需>10发才决定 / 命中多仍幸存）</h2>
<table>
<tr><th>海战</th><th>舰船</th><th>总命中</th><th>大口径命中</th><th>结局</th><th>反例性质</th></tr>
{''.join(f"<tr><td>{esc(s['battle'])} ({s['year']})</td><td>{esc(s['ship'])}</td><td><b>{s['total_hits'] if s['total_hits'] is not None else '—'}发</b></td><td>{s.get('main_hits') if s.get('main_hits') is not None else '—'}</td><td>{OUTCOME_ZH.get(s['outcome'],s['outcome'])}</td><td style='text-align:left'>{esc(s['note'])}</td></tr>" for s in against)}
</table>

<h2>五之二、无法判定（命中数未达5发检验区间 / 非炮战决定）</h2>
<table>
<tr><th>海战</th><th>舰船</th><th>总命中</th><th>结局</th><th>原因</th></tr>
{''.join(f"<tr><td>{esc(s['battle'])} ({s['year']})</td><td>{esc(s['ship'])}</td><td>{s['total_hits'] if s['total_hits'] is not None else '—'}</td><td>{OUTCOME_ZH.get(s['outcome'],s['outcome'])}</td><td style='text-align:left'>{esc(s['note'])}</td></tr>" for s in unknown)}
</table>

<h2>六、全部样本明细</h2>
<table>
<tr><th>海战</th><th>舰船</th><th>总命中</th><th>大口径命中</th><th>决定性命中</th><th>要害部位</th><th>结局</th><th>判据</th><th>备注</th></tr>
{rows_html()}
</table>

<h2>七、终章：自我实现的预言 —— 战列舰兴衰的反馈回路</h2>
<p>把前面全部命中数据放到系统层面看，战列舰的兴衰完全符合<b>「一次成功经验被递归放大 → 教条化 → 官僚体系自我实现」</b>的正反馈回路：</p>
<div class="loop">
<b>① 对马海战(1905)「证明」了战列舰决胜</b>——但真实胜因是日军炮术训练、俄军指挥崩溃与航速优势，却被简化为「全重炮教条」，成为此后四十年的训练数据；<br/>
<b>② 无畏舰革命+英德军备竞赛(1906-14)</b>——教条驱动的技术升级与数量竞赛，无畏舰成为「国家海权」的度量单位；<br/>
<b>③ 舰队膨胀、单舰造价攀升</b>——沉没一艘战列舰=战略灾难，损失变得不可承受；<br/>
<b>④ 输不起 → 不敢决战</b>——日德兰(1916)双方「点到为止」：舍尔夜间突围、英军放弃追击，谁都怕输掉「一次性国运」；<br/>
<b>⑤ 海军条约(1922-36)锁死数量</b>——华盛顿/伦敦条约冻结战列舰建造，剩余舰被迫更大更贵（纳尔逊级16in），1936年条约失效后更催生俾斯麦、大和级超级战列舰；<br/>
<b>⑥ 更损失不起 → 束之高阁</b>——战列舰从「战术武器」降级为「威慑资产」：提尔皮茨趴在挪威峡湾牵制英国主力，大和当「帝国旅馆」巡游特鲁克；<br/>
<b>⑦ 信仰自我强化</b>——海军官僚、造船工业、条约外交都靠战列舰的「存在正当性」维系，预算与军衔与之绑定，循环回到①，每转一圈舰更大、更贵、更不敢用。<br/>
</div>
<p>这与大模型的三类系统性缺陷同构：</p>
<table>
<tr><th>AI 理论</th><th>战列舰史对应</th></tr>
<tr><td><b>数据递归错误</b><br/><span style="color:#777">用错误/过时数据反复训练，模型自我强化</span></td><td><b>核心机制：只放大「炮」与「装甲」，忽略「精度∝1/距离」的外部物理约束。</b>对马海战证明的是「近距炮术决胜」（4-6km 对射、日军炮术碾压），却被教条化为「全重炮化」——此后每一代新舰（无畏→超无畏→大和）都放大口径与装甲，同时把交战距离推到 15km+，命中率随之从对马级别跌到日德兰的 2.71%。决策模型用旧数据证明新战列舰的合理性，即使射控、装甲、空中力量已彻底改变</td></tr>
<tr><td><b>思维定式主义</b><br/><span style="color:#777">教条不可挑战，路径依赖</span></td><td>马汉海权论+巨舰大炮主义成为公理：1906-1914年，质疑「战列舰=海权」的将领无法晋升；航母早在1917年就有雏形，却被归类为「辅助勤务」直到1941年珍珠港</td></tr>
<tr><td><b>官僚自我实现</b><br/><span style="color:#777">体系为自身存续而行动</span></td><td>预算、军衔、造船工业利益集团让「维持战列舰」成为目的本身；存在即价值（威慑逻辑），效率不是评估指标——大和号就是最贵的官僚纪念碑</td></tr>
</table>
<h3>递归错误的精确机制：距离-精度矛盾被系统性忽略</h3>
<p>「数据递归错误」不是笼统的「用旧数据证明新舰合理」，而是有一个<b>精确的物理内核</b>：造舰竞赛只放大<b>炮的口径</b>与<b>装甲厚度</b>（系统内部可测量的硬指标），却忽略了<b>命中精度随交战距离的劣化</b>这一外部物理约束。每一次「放大」都同时把交战距离推得更远，而距离是精度的死敌——两者构成被忽视的负反馈：</p>
<table>
<tr><th>距离效应</th><th>物理机制</th><th>对马(1905) vs 日德兰(1916)</th></tr>
<tr><td>弹道散布</td><td>散布椭圆随射程近似线性放大，目标「命中窗口」占散布面积的比重随距离平方级下降</td><td>对马 4-6km 近距对射 → 日德兰 8-15km 远距对射，英方命中率仅 2.71%（贝蒂战巡分队 1.43%）</td></tr>
<tr><td>弹道飞行时间</td><td>15km 级弹道飞行 40-60 秒，目标在此窗口内的任何机动都让解算前提失效</td><td>4km 级弹道飞行不足 10 秒，目标几乎无规避余地——近距是「瞄准」，远距是「赌博」</td></tr>
<tr><td>目标机动假设</td><td>模拟火控计算机（rangekeeper）硬性假设目标<b>匀速直线航行</b>，无法解算曲线航迹；蛇形机动=利用弹着观测间隙转向</td><td>日德兰高速机动的战巡分队命中率垫底；稳定航向航速的战列线对射才是「有效率」的射击环境</td></tr>
</table>
<div class="warn"><b>雷达解决不了这个问题——它只解决「观测」，不解决「预测」：</b><br/>
① 火控雷达（Type 284/274、Mark 3/8）带来的是「看得见、测距准、夜战可行」，但弹着点预判仍交给建立在<b>匀速直线假设</b>上的模拟计算机——<b>双方蛇形机动、或射程进入间接瞄准（15km+，跨地平线、依赖侦察机/观瞄机弹着报告）时，依然服从概率原则</b>；<br/>
② 真正的每发闭环修正要到 <b>1980 年代</b>：Iowa 级加装 DR-810 多普勒初速雷达 + MK-160 数字弹道电脑，每次射击实时测炮口初速、自动修正下一发——1987 年试射 31.9km 外 15 发 14 发落入 230m 方形内。注意：提升精度的是<b>反馈闭环</b>，不是数字化本身（美海军战术嵌入式计算机办公室主任 Boslaugh 原话：「纯数字化既不提高可靠性也不提高精度」）；<br/>
③ 这意味着从无畏舰诞生（1906）到 1980s，<b>八十年的舰炮发展里「距离-精度矛盾」从未被武器本身的演进解决</b>——它只被战术（英军主动贴脸）和载体革命（飞机把射程变成接近）绕过了。</div>
<h3>航母如何打破循环：效率高出两个数量级</h3>
<p>二战航母不是「更好的战列舰」，而是<b>另一种武器</b>——它把命中率与平台安全性同时提升了一个数量级，且飞机成本低廉到可以「消耗」：</p>
<table>
<tr><th>指标</th><th>战列舰炮战(1905-45)</th><th>航母俯冲轰炸(中途岛 1942)</th></tr>
<tr><td>对移动目标的命中率</td><td>2-3%（远距对射）~ 6-8%（英军贴脸）</td><td><b>15-33%</b>——39架SBD对3艘机动中的日军航母投弹、8发直接命中（赤城/苍龙组33%、加贺组15%），6分钟内瘫痪3艘主力航母</td></tr>
<tr><td>单次武器的致命效果</td><td>发射1,000发约997发无决定性效果（决定性命中数中位2发）</td><td>1-2发炸弹即毁一艘航母（机库燃油+弹药殉爆），赤城1发即瘫痪、加贺挨4-5发</td></tr>
<tr><td>平台位置与安全性</td><td>必须在敌方主炮射程内对射</td><td>航母编队在目标200-300km外放飞，自身不在敌方火力圈内</td></tr>
<tr><td>成本与可消耗性</td><td>一艘大和(7万吨)≈一支特混编队，损失不起</td><td>一架SBD成本不足一发460mm炮弹的零头；中途岛损失35架SBD击沉4艘主力航母，交换比1:10</td></tr>
<tr><td>精度实现机制（射程-精度矛盾的解法）</td><td><b>开环预测</b>：开火前一次性解算，命中与否交给概率；校射轮次稀疏，雷达与模拟计算机都不改变「匀速直线假设」的本质——射程越远，越接近掷骰子</td><td><b>人在回路的在线控制</b>：飞行员目视俯冲、持续修正投弹瞬间——载体把「射程」变成「飞到目标头顶」，人把「落点」变成「实时反馈修正」——这是二战中唯一真正绕开距离-精度矛盾的武器，也是命中率高出一个数量级的根本原因</td></tr>
</table>
<div class="warn"><b>最终裁决：</b>战列舰不是「最SB的武器」，而是<b>用火力效率兑换威慑存在的豪赌——人类造过的最贵的「表态」</b>。它的悲剧不是它没用，而是在它即将证明自己「还能用」之前，就被效率高出两个数量级的工具（航母+潜艇+航空兵）取代。整份命中数据分析最终指向的结论恰好与历史同步：<b>决定战局的是1-5发「打对了」的炮弹，而不是1,000发打出去的炮弹</b>——这个道理本身就是对战列舰最优雅的告别辞。</div>

{CH8}

<div class="foot">
数据来源：en.wikipedia.org 战史条目（Battle of Tsushima / Yellow Sea / Jutland / Denmark Strait / North Cape / Guadalcanal / Surigao Strait / Calabria / Mers-el-Kébir / Dakar / Casablanca / Dogger Bank / Coronel / Falklands 及各舰专条），经本地模型(local-llm-token-cleaner)清洗压缩后由 Python 统计分析。生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}<br/>
免责声明：历史文献对命中数记载常有出入（如雾岛号20发vs美军估计9发），本报告以维基条目引述数字为准，结论属概率性推断而非定论。第八章节第二周期数据来自公开报道（2022 乌克兰官方/西方情报开源、2023-24 美军中央司令部与英媒《防务新闻》《海军时报》、2026 美伊冲突新华社/澎湃/美军中央司令部/伊朗革命卫队声明），交战双方口径矛盾处均已如实标注，不作单方采信。
</div>
</div>
</body>
</html>
"""

with open(os.path.join(OUT, "report.html"), "w", encoding="utf-8") as f:
    f.write(html)

# ================= 控制台摘要 =================
print("=" * 60)
print(f"样本数: {n}")
print(f"结局分布: {dict(outcome_counter)}")
print(f"假说判据: 支持={len(support)} 反例={len(against)} 部分={len(partial)} 无法判定={len(unknown)}")
print(f"严格支持率: {d['strict_support_pct']}%  (含部分支持: {d['support_plus_partial_pct']}%)")
print(f"决定性命中数: 中位={d['decisive']['median']} 均值={d['decisive']['mean']} 范围={d['decisive']['min']}-{d['decisive']['max']}")
print(f"  ≤5发: {d['decisive']['le5']}条 ({d['decisive']['le5_pct']}%)  ≤10发: {d['decisive']['le10']}条 ({d['decisive']['le10_pct']}%)")
print(f"反例命中数(总): {d['against_counts']}")
print(f"沉没舰总命中均值={d['sunk']['mean']} 中位={d['sunk']['median']} (n={d['sunk']['n']}); 幸存舰总命中均值={d['survived']['mean']} 中位={d['survived']['median']} (n={d['survived']['n']})")
print(f"按时代决定性命中数: " + "; ".join(f"{k}: {v['mean']}" for k, v in stats['eras'].items()))
print(f"英军命中率对比(战术主动性): 日德兰2.71%(贝蒂1.43%) -> 北角约克公爵~6.7% -> 俾斯麦最后一战罗德尼+KGV~7.6%(罗德尼~10%)")
print(f"第二周期(2022-26)证伪链: 莫斯科号(2x海王星~100万美元) -> 红海1000:1成本倒挂(2000美元无人机 vs 200万美元SM-2) -> 林肯号250天不靠港/4枚导弹逼退/卡德尔-380命中驱逐舰")
print(f"按舰型决定性命中数: " + "; ".join(f"{k}({CLS_ZH[k]}): {v['mean']}" for k, v in stats['by_cls'].items()))
print(f"输出: {OUT}/report.html, stats.json")
print("=" * 60)
