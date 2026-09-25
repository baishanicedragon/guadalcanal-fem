# -*- coding: utf-8 -*-
"""
fem_bridge.py · 交战命中率桥接层
=================================
把 engine 的" shooter × target × weapon × range × 多维不确定性 "
映射到命中率。优先复用 GitHub 仓库的 FEM（gunnery_fem / torpedo_fem /
aerial_torpedo_fem / aircraft_dogfight_fem）；仓库不在时退回内置简化底，
保证框架独立可跑。

所有返回值都是 [0,1] 的干净底命中率；engine 再乘 uncertainty 与火控质量。
"""
import math
import random
from . import model as M


def _simplified_gunnery(range_m: float, caliber_in: float, target_cls: str) -> float:
    """内置简化底（兜底）：随距离下降、随口径上升，量级对齐 gunnery_fem。"""
    hl, hb = M.SHIP_HALF.get(target_cls, (70.0, 8.0))
    area = (2 * hl) * (2 * hb)
    sigma = 0.012 * range_m / max(1.0, caliber_in / 8.0)   # 小口径散布更大
    if sigma <= 0:
        return 0.5
    hit = min(0.95, area / (math.pi * sigma * sigma))
    return max(0.001, hit)


def gunnery_hit_rate(shooter: M.Unit, target: M.Unit, range_m: float,
                     disp_mult: float, rng: random.Random) -> float:
    """舰炮干净底命中率。尝试桥接 gunnery_fem.clean_floor，否则用简化底。"""
    gun = max((w for w in shooter.weapons if w.kind == "gun"),
              key=lambda w: w.caliber, default=None)
    cal = gun.caliber if gun else 8.0
    try:
        from gunnery_fem import clean_floor  # 同仓库时启用
        base, _, _, _, _ = clean_floor(range_m, "radar" if any(
            s.kind == "radar" for s in shooter.sensors) else "optical",
            18.0, 18.0, target.cls, n=400)
    except Exception:
        base = _simplified_gunnery(range_m, cal, target.cls)
    return base / max(1.0, disp_mult)     # 散布批差放大 → 命中率下降


def torpedo_hit_rate(shooter: M.Unit, target: M.Unit, range_m: float,
                      rng: random.Random) -> float:
    """鱼雷干净底命中率（直线雷对匀速编队）。九三式/Mk-15 的可靠性在 engine 层伯努利处理，
    这里只给几何底。贴近鱼叉/历史：九三式"长矛"在夜战近距离（<10km）是决定性威胁，
    命中率随距离快速上升；Mk-15 因 1942 磁引信灾难，即便命中几何底高也多在 engine 层哑火。"""
    torp = next((w for w in shooter.weapons if w.kind == "torpedo"), None)
    if torp is None:
        return 0.0
    # 近距离高威胁：9km 约 18%，3.5km 接近 45%（cap），远距离衰减。
    base = 0.18 * (9000.0 / max(2000.0, range_m))
    return min(0.45, max(0.001, base))


def air_hit_rate(shooter: M.Unit, target: M.Unit, range_m: float,
                 rng: random.Random) -> float:
    """鱼雷机/舰爆干净底（开环几何，900m 投雷 CV≈96%）。"""
    base = 0.96 if range_m < 1500 else max(0.05, 0.96 * (1500.0 / range_m))
    return base


def aerial_torpedo_hit_rate(shooter: M.Unit, target: M.Unit, range_m: float,
                           rng: random.Random) -> float:
    """空射鱼雷干净底（机降直航，比舰射九三式更近更稳）：约 800m 投雷 40%，
    随距离快速衰减（目标机动规避）；>6km 几乎失效。引擎对航空打击固定用 1200m
    等效距离（飞机飞抵目标），故此处命中率约 0.27。"""
    base = 0.40 * (800.0 / max(800.0, range_m))
    return min(0.45, max(0.02, base))
