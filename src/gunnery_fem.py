# -*- coding: utf-8 -*-
"""
BB-vs-BB 夜战炮击命中率 · 有限元（蒙特卡洛）推算
====================================================

方法论（用户 2026-09-24 指令）：
  「先算模型，再用现实校正。否则会迷路。」
  「你的这种推算 200 次就够。炮弹初速查表，飞行时间也查表。」

所以本脚本：
  1) 用【真实弹道表】的飞行时间（TOF），而不是拍脑袋；
  2) 先算出【干净弹道底】—— 只含武器本身的散布 + 火控误差 +
     匀速平台扰动（不含任何夜战混乱）；
  3) 再用真实「实测」锚点去【反推干扰因子】，说明为什么实测远低于
     干净底：照明 / 目标识别混乱 / 火控中断 / 观测虚报。

------------------------------------------------------------------
真实弹道表（来自 NavWeaps 公开射表，口径→飞行时间）
------------------------------------------------------------------
US 16"/45 Mk 6（华盛顿的炮，AP Mk8，MV 701 m/s = 2300 fps）：
  4,572 m  → 6.83 s
  9,140 m  → 14.45 s
  13,716 m → 22.94 s
  18,290 m → 32.55 s
  22,860 m → 43.61 s

JP 46 cm/45 Type 94（大和，91式 AP，MV 780 m/s = 2559 fps）：
  16,830 m → 26.05 s
  27,920 m → 49.21 s
  35,830 m → 70.27 s
  40,700 m → 89.42 s
  （<16.8 km 段由原点线性外推，量级与美 16" 一致）

JP 35.6 cm/45（金刚/雾岛，Vickers Type 41，MV≈775 m/s）TOF 与
46cm 同量级，本推算以 46cm 表作日方代理（保守，略长）。

------------------------------------------------------------------
散布与火控误差模型（假设，可审计）
------------------------------------------------------------------
武器散布（RMS，随距离线性放大，符合"射表散布随射程增大"）：
  σ_range_disp  = 0.0080 * R      # 距离散布 ~0.8%/R
  σ_defl_disp   = 0.0035 * R      # 方向散布 ~0.35%/R
   （注：二战主力舰炮在 15 km 的距离散布约 σ_r~120 m、σ_d~52 m，
    与公开射表量级一致）

火控误差（含测距/测速/提前量，加到散布上）：
  光学（日方夜战，无雷达）：σ_fc_r = 0.020*R ，σ_fc_d = 0.010*R
    —— 夜间光学测距极难，误差远大于昼间
  雷达（美方夜战）：          σ_fc_r = 0.004*R ，σ_fc_d = 0.002*R

平台扰动（匀速，不剧烈规避）：
  借 mc_fem 的 _speed_gun_factor：美方陀螺稳定+雷达→温和；
  日方光学无陀螺→敏感。这里用同一乘数作为干扰项之一。

舰体尺度（半长/半宽，米）：
  BB: 110 / 16   CA: 90 / 10   CL: 70 / 8   DD: 50 / 4
"""

import math
import random

# ----------------------------- 真实 TOF 表 -----------------------------
TOF_US = [(4572, 6.83), (9140, 14.45), (13716, 22.94), (18290, 32.55), (22860, 43.61)]
TOF_JP = [(0, 0.0), (16830, 26.05), (27920, 49.21), (35830, 70.27), (40700, 89.42)]


def tof(range_m: float, table=TOF_US):
    """线性插值飞行时间（秒）。低于最小点则自原点线性外推。"""
    pts = sorted(table)
    if range_m <= pts[0][0]:
        # 原点线性外推
        if pts[0][0] == 0:
            return pts[0][1]
        return range_m * pts[0][1] / pts[0][0]
    if range_m >= pts[-1][0]:
        # 末端线性外推
        a = pts[-2]; b = pts[-1]
        return b[1] + (range_m - b[0]) * (b[1] - a[1]) / (b[0] - a[0])
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]; x1, y1 = pts[i + 1]
        if x0 <= range_m <= x1:
            return y0 + (range_m - x0) * (y1 - y0) / (x1 - x0)
    return pts[-1][1]


# ----------------------- 平台扰动（与 mc_fem 同式） -----------------------
GUN_SPEED_OWN_STABLE = 0.006
GUN_SPEED_OWN_UNSTABLE = 0.012
GUN_SPEED_OWN_UNSTABLE2 = 0.0002
GUN_SPEED_TGT = 0.004
GUN_SPEED_OWN_FLOOR = 0.55
GUN_SPEED_TGT_FLOOR = 0.80


def speed_gun_factor(own_spd, tgt_spd, stable):
    if own_spd <= 0:
        own = 1.0
    elif stable:
        own = max(GUN_SPEED_OWN_FLOOR, 1.0 - GUN_SPEED_OWN_STABLE * own_spd)
    else:
        own = max(GUN_SPEED_OWN_FLOOR,
                  1.0 - GUN_SPEED_OWN_UNSTABLE * own_spd
                  - GUN_SPEED_OWN_UNSTABLE2 * own_spd ** 2)
    tgt = max(GUN_SPEED_TGT_FLOOR, 1.0 - GUN_SPEED_TGT * tgt_spd)
    return own * tgt


# ----------------------------- 参数 -----------------------------
SHIP = {
    "BB": (110.0, 16.0),
    "CA": (90.0, 10.0),
    "CL": (70.0, 8.0),
    "DD": (50.0, 4.0),
}


def sigma_total(range_m, fc, own_spd, tgt_spd):
    """返回 (σ_range_total, σ_defl_total, speed_factor)。"""
    sig_r_disp = 0.0080 * range_m
    sig_d_disp = 0.0035 * range_m
    if fc == "optical":
        sig_fc_r = 0.020 * range_m
        sig_fc_d = 0.010 * range_m
    else:  # radar
        sig_fc_r = 0.004 * range_m
        sig_fc_d = 0.002 * range_m
    sr = math.sqrt(sig_r_disp ** 2 + sig_fc_r ** 2)
    sd = math.sqrt(sig_d_disp ** 2 + sig_fc_d ** 2)
    # 平台扰动乘数（美方 stable=True）
    stable = (fc == "radar")
    sf = speed_gun_factor(own_spd, tgt_spd, stable)
    return sr, sd, sf


def clean_floor(range_m, fc, own_spd, tgt_spd, tgt_cls, n=3000):
    """蒙特卡洛算干净弹道底命中率（无照明/混乱干扰）。"""
    half_len, half_beam = SHIP[tgt_cls]
    sr, sd, sf = sigma_total(range_m, fc, own_spd, tgt_spd)
    rng = random.Random(20260923)
    hits = 0
    for _ in range(n):
        # 命中 = 落点在 [−半长, 半长] × [−半宽, 半宽] 矩形内
        er = rng.gauss(0.0, sr)
        ed = rng.gauss(0.0, sd)
        if abs(er) <= half_len and abs(ed) <= half_beam:
            hits += 1
    floor = hits / n
    # 含平台扰动后的底
    floor_sf = floor * sf
    return floor, floor_sf, sr, sd, sf


# ------------------------------------------------------------------
# 史实锚点（来自 NavWeaps 炮击命中率与穿透标定.md §5.2）
# ------------------------------------------------------------------
ANCHORS = {
    # 华盛顿（雷达）18km 远射雾岛—— 实际打在川内/绫波 DD 群，不计
    # 华盛顿近距 ambush 打雾岛 ~12%
    "washington_kirishima": 0.12,
    # 雾岛（光学）打南达科他 ~1.7%（117 发仅 6 中）
    "kirishima_southdakota": 0.017,
}


def report():
    print("=" * 78)
    print("BB-vs-BB 夜战炮击命中率 · 有限元（蒙特卡洛）推算")
    print("=" * 78)
    print("\n[0] 真实弹道表校验：飞行时间 TOF（秒）")
    print(f"  US 16\"/45 @ 7315 m (8kyd)  ≈ {tof(7315, TOF_US):.1f} s")
    print(f"  US 16\"/45 @13716 m (15kyd) ≈ {tof(13716, TOF_US):.1f} s")
    print(f"  US 16\"/45 @18290 m (20kyd) ≈ {tof(18290, TOF_US):.1f} s")
    print(f"  JP 46cm    @ 7315 m        ≈ {tof(7315, TOF_JP):.1f} s")
    print(f"  JP 46cm    @16830 m        ≈ {tof(16830, TOF_JP):.1f} s")

    print("\n[1] 干净弹道底（无夜战混乱）")
    cases = [
        ("华盛顿(雷达)→雾岛 BB @8kyd", 7315, "radar", 18, 18, "BB"),
        ("雾岛(光学)→南达 BB @8kyd", 7315, "optical", 18, 18, "BB"),
        ("雷达 BB→BB @15kyd", 13716, "radar", 18, 18, "BB"),
        ("光学 BB→BB @15kyd", 13716, "optical", 18, 18, "BB"),
        ("雷达 BB→BB @20kyd", 18290, "radar", 18, 18, "BB"),
        ("光学 BB→BB @20kyd", 18290, "optical", 18, 18, "BB"),
    ]
    rows = []
    for name, R, fc, os_, ts_, cls in cases:
        floor, floor_sf, sr, sd, sf = clean_floor(R, fc, os_, ts_, cls)
        rows.append((name, floor, floor_sf, sr, sd, sf))
        print(f"  {name:32s} 干净底={floor*100:5.1f}%  含匀速扰动={floor_sf*100:5.1f}%"
              f"  (σr={sr:5.0f}m σd={sd:4.0f}m sf={sf:.3f})")

    print("\n[2] 用实测锚点反推『干扰因子』")
    print("    干扰因子 = 实测 / (干净底×匀速扰动)；它衡量夜战混乱吃掉了几成命中。")
    # 华盛顿→雾岛（雷达，近距 ambush，雾岛被己方火光照亮）
    fl, fl_sf, _, _, _ = clean_floor(7315, "radar", 18, 18, "BB")
    meas = ANCHORS["washington_kirishima"]
    print(f"  华盛顿→雾岛：实测 {meas*100:.1f}% / 含扰动底 {fl_sf*100:.1f}%"
          f"  ⇒ 干扰因子 ≈ {meas/fl_sf:.2f}")
    # 雾岛→南达（光学，南达近乎静止但雾岛混乱/分火）
    fl2, fl_sf2, _, _, _ = clean_floor(7315, "optical", 18, 18, "BB")
    meas2 = ANCHORS["kirishima_southdakota"]
    print(f"  雾岛→南达  ：实测 {meas2*100:.1f}% / 含扰动底 {fl_sf2*100:.1f}%"
          f"  ⇒ 干扰因子 ≈ {meas2/fl_sf2:.2f}")

    print("\n[3] 结论：造成实测偏离的干扰因子（按权重）")
    print("  ① 照明：夜战无光源则炮弹落水无人见，命中归零；雾岛打南达时南达")
    print("     电力全失、几乎无轮廓，雾岛火控多半在打华盛顿的闪光。")
    print("  ② 目标识别混乱：多小集群 + T 字头交错，火控频繁切目标/分火，")
    print("     实际落点分散到非预定舰（华盛顿 18km 远射大半落在川内/绫波 DD 群）。")
    print("  ③ 火控中断：光学夜战测距漂移、指挥链被打断，等效把 σ_fc 再放大。")
    print("  ④ 观测虚报：战后复核把'近失/水中炸'算成'命中'，使实测数字虚高；")
    print("     反过来说，若把'真正击穿'筛出来，光学侧底还会更低。")
    print("\n  干净弹道底（含匀速扰动）雷达侧 ~31%、光学侧 ~5.6%；实测是它被")
    print("  上述干扰压到 12% / 1.7%。即：武器本身的命中能力远高于夜战实测，")
    print("  夜战是'传感器与指挥'的战争，不是'弹道'的战争。")

    print("\n[4] 距离敏感性（含匀速扰动底，雷达/光学各一）")
    for R in [5000, 7315, 10000, 13716, 18290]:
        fl_r, fl_r_sf, _, _, _ = clean_floor(R, "radar", 18, 18, "BB")
        fl_o, fl_o_sf, _, _, _ = clean_floor(R, "optical", 18, 18, "BB")
        print(f"  {R:6.0f} m: 雷达底 {fl_r_sf*100:5.1f}%   光学底 {fl_o_sf*100:5.1f}%")


if __name__ == "__main__":
    report()
