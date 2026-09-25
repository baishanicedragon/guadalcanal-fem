# -*- coding: utf-8 -*-
"""v0.6 验证脚本：三场景终局状态分布 + 中途岛官僚主义旋钮对比。"""
from sim.engine import Engine
from sim import scenarios as SC


def run_to_end(name, seed=42, max_ticks=400):
    sc = SC.REGISTRY[name]()
    eng = Engine(sc, seed=seed, step_sec=30)
    for _ in range(max_ticks):
        snap = eng.step()
        if snap["over"]:
            break
    return sc, eng, snap


def status_dist(sc):
    out = {}
    for side in sc.sides:
        d = {}
        for u in side.units:
            d[u.status] = d.get(u.status, 0) + 1
        out[side.name] = d
    return out


print("========== 三场景终局状态分布 ==========")
for name in ["瓜岛", "中途岛", "塔拉瓦"]:
    sc, eng, snap = run_to_end(name)
    camp = eng.campaign_result()
    print(f"--- {name}  T+{snap['time_s']}s  tactical={camp['tactical']}  strategic={camp['strategic']}")
    for side, d in status_dist(sc).items():
        print(f"    {side}: {d}")

print()
print("========== 中途岛官僚主义旋钮对比 ==========")
for pen in (0.0, 0.15, 0.25, 0.35):
    sc = SC.REGISTRY["中途岛"]()
    sc.sides[0].c2_penalty = pen     # JP 方
    eng = Engine(sc, seed=42, step_sec=30)
    for _ in range(400):
        snap = eng.step()
        if snap["over"]:
            break
    jp = sum(1 for u in sc.sides[0].units if not u.alive)
    us = sum(1 for u in sc.sides[1].units if not u.alive)
    print(f"JP c2_penalty={pen:.2f}  ->  T+{snap['time_s']}s  日沉{jp}/美沉{us}  "
          f"tactical={snap['outcome']}")
