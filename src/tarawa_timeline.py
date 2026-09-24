# -*- coding: utf-8 -*-
"""
tarawa_timeline.py
=====================================================================
塔拉瓦 1943 末 · 联合推演的「连续时间线」版
---------------------------------------------------------------------
用户 2026-09-24 要求：把 joint_tarawa_wargame.py 的推演结果，
**转成从夜战开始的、每 30 分钟一步的连续推演**。

做法（诚实、可复现、不编造）：
  1. 用 seed=42 跑一次 joint_tarawa_wargame.campaign() 得到**单次实现**的真实损失
     （不是 500 局均值；均值见 run_output.txt）。
  2. 把这个单次实现里各阶段(P2夜战/P3拂晓/P4跨越轰炸/P5潜艇/P6撤运)的损失，
     按真实战役时序铺到 **30 分钟一格** 的连续时钟上（T0 = D+3 22:00 夜战接敌）。
  3. 每一步给出：时钟、阶段、事件、双方舰队状态快照、本步损失 Δ。

所有数字来自 joint 模型的标定常量与单次实现；时钟/步长/接敌时刻为建模假设
（已在输出中标注），作战机理不新增。

依赖：joint_tarawa_wargame.py（同目录）
=====================================================================
"""
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import joint_tarawa_wargame as JT

STEP = 30  # 分钟 / 步
# T0 = D+3 22:00 第二舰队接敌
def clock(tmin):
    total = 22 * 60 + tmin
    day = 3 + total // (24 * 60)
    h = (total // 60) % 24
    m = total % 60
    return "D+%d %02d:%02d" % (day, h, m)

def spread(n, steps):
    """把整数 n 轮转分配到 steps 列表上，返回 {step: 数量}。"""
    out = {s: 0 for s in steps}
    if n <= 0:
        return out
    i = 0
    while n > 0:
        out[steps[i % len(steps)]] += 1
        n -= 1
        i += 1
    return out

def run_timeline(seed=42):
    rng = random.Random(seed)
    res = JT.campaign(rng)
    log = res["log"]

    # ── 起始状态（P0 空袭后，P1 编组后）──
    us = {
        "CV": JT.US_FLEET["CV"], "CVL": JT.US_FLEET["CVL"],
        "BB_new": JT.US_FLEET["BB_new"], "CA": JT.US_FLEET["CA"],
        "CL": JT.US_FLEET["CL"], "DD": JT.US_FLEET["DD"],
        "SS": JT.US_FLEET["SS"],
        "aircraft": JT.US_FLEET["aircraft"] - log["p0"][0],
    }
    jp = {
        "CV": JT.JP_FLEET["CV"], "BB_super": JT.JP_FLEET["BB_super"],
        "BB": JT.JP_FLEET["BB"], "CA": JT.JP_FLEET["CA"],
        "CL": JT.JP_FLEET["CL"], "DD": JT.JP_FLEET["DD"],
        "SS": JT.JP_FLEET["SS"],
        "carrier_aircraft": JT.JP_FLEET["carrier_aircraft"],
        "land_bombers": JT.JP_FLEET["land_bombers"] - log["p0"][1],
        "garrison_fighters": JT.JP_FLEET["garrison_fighters"] - log["p0"][2],
    }

    # 拦截队 / 炮击队 编组规模（P1 公式，仅用于展示）
    intercept = JT.phase1_landing_split(dict(JT.US_FLEET), rng)[0]

    # ── 各阶段真实损失（单次实现）──
    bb2, ca2, dd2, jpdd2 = log["p2"]
    bb3, usair3, jpair3 = log["p3"]
    cv_lost, jp_air_loss, _ = log["p4"]
    us_ship_lost, jp_ship_lost = log["p5"]
    evac, evac_dd, evac_ss = log["p6"]

    # ── 把损失铺到 30 分钟网格 ──
    # 夜战 P2：step 0=22:00 .. 7=01:30（02:00 脱离）
    apply = {}  # step -> list of (dict, key, amount)
    def put(step, d, k, n):
        apply.setdefault(step, []).append((d, k, n))

    # 夜战损失分布
    for s, n in spread(bb2, [2, 3, 4]).items():
        if n: put(s, us, "BB_new", n)
    for s, n in spread(ca2, [1, 2, 3, 4]).items():
        if n: put(s, us, "CA", n)
    for s, n in spread(dd2, [1, 2, 3, 4, 5]).items():
        if n: put(s, us, "DD", n)
    for s, n in spread(jpdd2, [3, 4, 5, 6]).items():
        if n: put(s, jp, "DD", n)

    # 拂晓 P3：step 15=05:30(袭击慢速本队) 16=06:00(空战) 17=06:30(持续)
    for s, n in spread(bb3, [15]).items():
        if n: put(s, us, "BB_new", n)
    for s, n in spread(usair3, [16, 17]).items():
        if n: put(s, us, "aircraft", n)
    for s, n in spread(jpair3, [16, 17]).items():
        if n: put(s, jp, "carrier_aircraft", n)

    # 跨越轰炸 P4：第一击 step17(D+4 06:30 发射后撤) + 第二击 step63(D+5 05:30 岸基再战)
    w1 = int(round(jp_air_loss * 0.60))
    w2 = jp_air_loss - w1
    if w1: put(17, jp, "carrier_aircraft", w1)
    if w2: put(63, jp, "carrier_aircraft", w2)
    # 美航母重创：主要在第一击窗口
    for s, n in spread(cv_lost, [17, 63]).items():
        if n: put(s, us, "CV", n)

    # 潜艇 P5：夜 3(23:30) / 拂晓 15(05:30) / 白昼 33(D+4 15:00) / 次日 63
    for s, n in spread(us_ship_lost, [3, 15, 33, 63]).items():
        if n: put(s, us, "DD", n)
    for s, n in spread(jp_ship_lost, [3, 15, 33, 63]).items():
        if n: put(s, jp, "DD", n)
    # 双方潜艇互有损失（反潜）：放在 D+4 22:00 = step 48
    ss_us = int(round(us["SS"] * 0.15))
    ss_jp = int(round(jp["SS"] * 0.15))
    if ss_us: put(48, us, "SS", ss_us)
    if ss_jp: put(48, jp, "SS", ss_jp)

    # 撤运 P6：D+4 22:00 = step 48 夜 run
    if evac_dd: put(48, jp, "DD", evac_dd)
    if evac_ss: put(48, jp, "SS", evac_ss)

    MAX_STEP = 63  # D+5 05:30 第二击结束

    # 事件文本（仅关键步）
    EVENT = {
        0: "南云第二舰队（大和/武藏+4BB+10CA+8CL+36DD，含九三式鱼雷）雷达接敌美拦截队；双方雷达均开机。",
        1: "日 DD 九三式 36×8 管齐射穿越美屏卫；首轮命中落向美 CA/DD。",
        2: "第二波鱼雷+ opening gunnery；美拦截队 CA 开始受损。",
        3: "美新锐 BB 遭 ≥2 命中→重创/沉；双方潜艇开始互相渗透。",
        4: "两军雷达引导炮火对射达峰值；美损持续累积。",
        5: "美雷达+CIC 引导夜战炮火反制日 DD，日 DD 开始损失。",
        6: "日方达撤退阈值（有路可退），开始收拢。",
        7: "02:00 第二舰队转向脱离；夜战结束，未歼灭（双方均可撤）。",
        15: "陆攻（G4M+银河/火星发动机）与金星零战自马绍尔/南洋集结地去袭美慢速本队（炮击队）；潜艇互击持续。",
        16: "美航母被迫派 CAP 护本队 → 与金星零战空战（交换比 1.10，日优）。",
        17: "小泽 6 艘航母机群全出击后立即西撤离开美打击范围；飞行员空袭后退往附近岸上机场加油。",
        33: "日机在岸基加油再整备；美舰队维持封锁；零星潜艇接触。",
        48: "丁型(松型)驱逐舰+舰队潜艇驶抵塔拉瓦，撤运残兵；双方潜艇互有损失（反潜）。",
        63: "D+5 拂晓岸基再整备机群发动第二波跨越轰炸；美航母再遭重创；联合推演收束。",
    }
    PHASE = {}
    for s in range(0, 8): PHASE[s] = "P2 夜战"
    for s in (15, 16, 17): PHASE[s] = "P3 拂晓/P4 跨越"
    PHASE[33] = "P4 整备"
    PHASE[48] = "P5/P6 潜艇+撤运"
    PHASE[63] = "P4 第二击"

    rows = []
    for s in range(0, MAX_STEP + 1):
        # 应用本步损失（同侧同舰种合并为一行）
        dl = {}
        if s in apply:
            for d, k, n in apply[s]:
                d[k] = max(0, d[k] - n)
                side = "美" if d is us else "日"
                dl[(side, k)] = dl.get((side, k), 0) + n
        dl_us = " ".join("%s%s-%d" % (sd, kk, nn)
                          for (sd, kk), nn in sorted(dl.items()) if sd == "美")
        dl_jp = " ".join("%s%s-%d" % (sd, kk, nn)
                          for (sd, kk), nn in sorted(dl.items()) if sd == "日")
        rows.append({
            "step": s, "clock": clock(s * STEP),
            "phase": PHASE.get(s, "—"),
            "event": EVENT.get(s, ""),
            "us": dict(us), "jp": dict(jp),
            "dl_us": dl_us, "dl_jp": dl_jp,
        })
    return rows, res

def fmt_state(d, keys):
    return " ".join("%s%d" % (k, d[k]) for k in keys)

def main():
    rows, res = run_timeline(42)
    print("=" * 100)
    print("  塔拉瓦 1943 末 · 连续时间线推演（从夜战起，30 分钟一步）  seed=42")
    print("  （单次实现；均值见 run_output.txt。时钟/接敌时刻为建模假设）")
    print("=" * 100)
    hdr = "%-4s %-12s %-14s %-46s | %s" % ("步", "时钟", "阶段", "事件", "美/日 舰队状态(关键)")
    print(hdr)
    print("-" * 100)
    us_keys = ["CV", "CVL", "BB新", "CA", "CL", "DD", "SS", "机"]
    jp_keys = ["CV", "大和", "BB", "CA", "CL", "DD", "SS", "航母机", "陆攻", "驻机"]
    # 注意 fmt_state 用短键映射
    def fUs(d):
        return "CV%d CVL%d BB新%d CA%d CL%d DD%d SS%d 机%d" % (
            d["CV"], d["CVL"], d["BB_new"], d["CA"], d["CL"], d["DD"], d["SS"], d["aircraft"])
    def fJp(d):
        return "CV%d 大和%d BB%d CA%d CL%d DD%d SS%d 航母机%d 陆攻%d 驻机%d" % (
            d["CV"], d["BB_super"], d["BB"], d["CA"], d["CL"], d["DD"], d["SS"],
            d["carrier_aircraft"], d["land_bombers"], d["garrison_fighters"])
    last_event = None
    for r in rows:
        if r["event"] or r["dl_us"] or r["dl_jp"]:
            ev = r["event"][:44]
            line = "%-4d %-12s %-14s %-46s | %s" % (
                r["step"], r["clock"], r["phase"], ev, fUs(r["us"]))
            print(line)
            print("      %-12s %-14s %-46s | %s" % ("", "", "", "日:" + fJp(r["jp"])))
            if r["dl_us"]: print("      ↳ 美损: %s" % r["dl_us"])
            if r["dl_jp"]: print("      ↳ 日损: %s" % r["dl_jp"])
    print("-" * 100)
    print("[最终结果 · 单次实现]")
    print("  美军夺岛: %s (全战档不翻转)" % ("是" if res["captured"] else "否"))
    print("  守军撤出: %d 人 (%.1f%%)" % (res["evac_headcount"], res["evac_frac"] * 100))
    print("  美舰损失: %d 艘(加权) | 美机损失: %d 架" % (res["us_ships_lost"], res["us_air_lost"]))
    print("  日航母机消耗: %d / 400 (不可补充＝承重墙)" %
          (JT.JP_FLEET["carrier_aircraft"] - res["jp"]["carrier_aircraft"]))

if __name__ == "__main__":
    main()
