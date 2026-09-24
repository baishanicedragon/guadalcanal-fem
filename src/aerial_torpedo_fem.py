# -*- coding: utf-8 -*-
"""
飞机投雷 · 有限元（蒙特卡洛）推算   (aerial_torpedo_fem)
=============================================================

用户 2026-09-24 指令：
  「没有游戏模型，你就自己如刚才那个建模下，毕竟日本鱼雷机速度，
    投弹距离和反击被击中都是可算模型」

方法论（与 gunnery_fem / torpedo_fem 完全一致）：
  先算【干净几何底】（仅投弹方位散布 + 目标匀速机动 + 鱼雷直航），
  再用【实测锚点】反推干扰因子
    —— CAP 拦截 / 高炮命中（"反击被击中"）/ 鱼雷可靠性 / 投弹距离误差。

------------------------------------------------------------------
真实参数（查表 / 可算）
------------------------------------------------------------------
投雷机速度与投弹距离：
  九七式艦攻 B5N2（Kate）：极速 ~235 kt、投弹速度 ~110 kt、可挂 1×九一式
  一式陸攻 G4M1（Betty）：极速 ~270 kt、投弹速度 ~150 kt、可挂 1×九一式
  TBF Avenger            ：极速 ~270 kt、投弹速度 ~120 kt、可挂 1×Mk13
航空鱼雷：
  九一式航空魚雷（Type 91）：航速 ~40 kt（20.6 m/s）、装药 ~240 kg 九四式；
    触发/定深可靠、浅定深木鳍版适配瓜岛浅水 → 可靠性因子 ≈ 0.80
  Mk 13（1942 美）：早期定深/引信问题严重 → 可靠性因子 ≈ 0.30-0.50
目标机动航速：BB 18-27 kt、CA 33 kt、CV 30+ kt、CL 30 kt、DD 35 kt
舰体半长：BB 110 m / CV 130 m / CA 90 m / CL 70 m / DD 50 m
投弹距离（飞机→目标水平距离＝鱼雷运行距离）：典型 800-1000 m
投弹方位误差（1σ）：含瞄准 + 投弹姿态 + 提前量误差，取 2.5°
投弹距离误差（1σ）：±120 m（投近/投远，跑出射程即失的）
九一式最大运行距离：取 2000 m（超出即鱼雷跑不到目标）

------------------------------------------------------------------
几何（飞机在高空/低空水平投雷，鱼雷入水直航）
------------------------------------------------------------------
投弹瞬间：飞机在 O(0,0)，目标在 (D,0)，目标以 Vt 沿 +y 匀速漂移。
完美提前量：鱼雷瞄向 (D, Vt·T)，T = D / v_torp，发射角 θ0 = atan2(Vt·T, D)。
带散布 ε~N(0,σ_bear) 与距离误差 δ~N(0,σ_dist)（实际 D'=D+δ）：
  鱼雷抵 x=D' 平面时 y_imp = D'·tan(θ0+ε)；
  命中 = |y_imp − Vt·T'| ≤ Lh（T'=D'/v_torp）。
若 D' > MAX_RUN ⇒ 鱼雷跑不到 ⇒ 失的。
"""

import math
import random

KT = 0.5144
TORP_SPEED = 40.0 * KT            # 20.56 m/s （九一式航空鱼雷）
DROP_DIST = 900.0                 # m，典型投弹距离
SIGMA_BEAR = math.radians(2.5)    # 投弹方位误差 (1σ)
SIGMA_DIST = 120.0                # m，投弹距离误差 (1σ)
MAX_RUN = 2000.0                  # m，九一式最大运行距离
SHIP_HL = {"BB": 110.0, "CV": 130.0, "CA": 90.0, "CL": 70.0, "DD": 50.0}

# 鱼雷可靠性因子（实测锚点反推）
REL = {"Type91": 0.80, "Mk13_1942": 0.40, "none": 1.0}


def drop_hit_rate(D, Vt_kt, cls="BB",
                  sigma_bear=SIGMA_BEAR, sigma_dist=SIGMA_DIST,
                  n=8000, seed=20260924):
    """干净几何底：单条飞机投雷的命中概率（仅几何＋目标匀速）。"""
    Vt = Vt_kt * KT
    rng = random.Random(seed)
    Lh = SHIP_HL[cls]
    hit = 0
    for _ in range(n):
        eps = rng.gauss(0.0, sigma_bear)
        derr = rng.gauss(0.0, sigma_dist)
        Dp = D + derr
        if Dp <= 0 or Dp > MAX_RUN:
            continue                    # 投太近/太远：失的
        Tp = Dp / TORP_SPEED
        lead = Vt * Tp
        theta0 = math.atan2(lead, Dp)
        y_imp = Dp * math.tan(theta0 + eps)
        if abs(y_imp - lead) <= Lh:
            hit += 1
    return hit / n


def attacker_loss_rate(cap_coverage, aaa_intensity, ammo, attacker_speed_kt):
    """『反击被击中』可算模型（线性，输入皆物理量）：
      cap_coverage  : 目标上空 CAP 密度 0-1（0=无战斗机掩护）
      aaa_intensity : 目标高炮火力密度 0-1
      ammo          : 高炮弹药的"有/无" 0-1（夜战耗尽则≈0）
      attacker_speed: 投雷机投弹速度 kt（越慢越易被截/被高炮锁）
    返回：投雷机战损率（0-0.95）。"""
    cap_k = cap_coverage * 0.40 * (120.0 / max(80.0, attacker_speed_kt))
    aaa_k = aaa_intensity * ammo * 0.25
    return min(0.95, 0.03 + cap_k + aaa_k)   # 0.03 = 残存/航程损耗基底


def raid_expected_hits(n_bombers, D, Vt_kt, cls,
                       rel=REL["Type91"],
                       cap_coverage=0.0, aaa_intensity=0.0, ammo=0.0,
                       attacker_speed_kt=110.0,
                       combat_drop=1.0, hits_to_cripple=3, hits_to_sink=4,
                       n=8000, seed=20260924):
    """一次鱼雷机突袭的期望值：
      n_bombers          : 出击投雷机数
      combat_drop        : 战斗投弹成功率（在火力下成功投出合格雷的比例，
                            由锚点反推；无拦截≈0.85，圣克鲁斯≈0.2-0.25，
                            中途岛 TBD 无掩护≈0.05）
      → 返回：期望命中数、期望战损数、命中后目标状态概率（完好/重创/沉没）"""
    clean = drop_hit_rate(D, Vt_kt, cls, n=n, seed=seed)
    loss = attacker_loss_rate(cap_coverage, aaa_intensity, ammo, attacker_speed_kt)
    survive = 1.0 - loss
    # 成功投出合格雷的机数
    effective = n_bombers * survive * combat_drop
    p_hit_drop = clean * rel
    exp_hits = effective * p_hit_drop

    # 目标状态：用泊松近似命中数→状态分布（命中≥重创阈值→重创，≥沉没阈值→沉没）
    import math as _m
    lam = exp_hits
    p_crip = 0.0
    p_sink = 0.0
    for k in range(hits_to_cripple):
        p_crip += _m.exp(-lam) * lam**k / _m.factorial(k)
    for k in range(hits_to_sink):
        p_sink += _m.exp(-lam) * lam**k / _m.factorial(k)
    p_crip = 1.0 - p_crip          # ≥重创阈值
    p_sink = 1.0 - p_sink          # ≥沉没阈值
    return {
        "clean_floor": clean,
        "loss_rate": loss,
        "survive_rate": survive,
        "effective_bombers": effective,
        "p_hit_per_drop": p_hit_drop,
        "exp_hits": exp_hits,
        "p_cripple": p_crip,
        "p_sink": p_sink,
    }


def report():
    print("=" * 78)
    print("飞机投雷 · 有限元（蒙特卡洛）推算  (aerial_torpedo_fem)")
    print("=" * 78)

    print("\n[0] 干净几何底：单条投雷命中概率（仅几何+目标匀速，未乘可靠性）")
    print(f"    投弹距离 D=900m，方位误差 2.5°(1σ)，距离误差 120m，九一式 40kt")
    print(f"    {'目标':>4} {'Vt(kt)':>7} {'干净命中':>8} {'运行时间':>8}")
    for cls, vt in [("BB", 8), ("BB", 18), ("CV", 30), ("CA", 33), ("DD", 35)]:
        c = drop_hit_rate(DROP_DIST, vt, cls)
        T = DROP_DIST / TORP_SPEED
        print(f"    {cls:>4} {vt:7d} {c*100:7.1f}% {T:7.1f}s")

    print("\n[1] 投弹距离敏感性（CV 30kt，干净命中%）")
    for D in [700, 900, 1100, 1300, 1500]:
        c = drop_hit_rate(D, 30, "CV")
        note = "  (跑出射程↑)" if D > 1500 else ""
        print(f"    D={D:4d}m → {c*100:5.1f}%{note}")

    print("\n[2] 『反击被击中』可算模型：投雷机战损率 vs 防御态势")
    print(f"    {'场景':<22}{'CAP':>5}{'高炮':>6}{'弹药':>6}{'速度':>6}{'战损':>7}")
    scen = [
        ("无掩护(残队)", 0.0, 0.05, 0.0, 150),
        ("史实企业号(圣克鲁斯)", 0.9, 0.8, 1.0, 110),
        ("fork企业号(减CAP)", 0.5, 0.7, 1.0, 110),
    ]
    for name, cap, aaa, am, sp in scen:
        lr = attacker_loss_rate(cap, aaa, am, sp)
        print(f"    {name:<22}{cap:5.1f}{aaa:6.1f}{am:6.1f}{sp:6d}{lr*100:6.1f}%")

    print("\n[3] 锚点反推『战斗投弹成功率 combat_drop』")
    print("    干净底(CV30kt,900m)≈ %.0f%% × 可靠性0.8 ≈ %.0f%%/drop"
          % (drop_hit_rate(900, 30, "CV")*100,
             drop_hit_rate(900, 30, "CV")*100*0.8))
    print("    史实圣克鲁斯：~40 架 Kate 出击，企业+大黄蜂共中 ~6-8 雷")
    print("      → 期望命中 7 / (40×0.8×clean) 反推 combat_drop ≈ 0.20-0.25")
    print("    中途岛 TBD：41 架出击、35 架被击落、0 命中 → combat_drop≈0.05（无掩护+机劣）")

    print("\n[4] 场景 A · 拂晓一式陆攻(G4M)突袭撤走的美残队")
    print("    目标：夜战重创 BB/CA，Vt≈8kt，无 CAP(企业号 150nm+)，无高炮弹药")
    rA = raid_expected_hits(
        n_bombers=18, D=900, Vt_kt=8, cls="BB",
        rel=REL["Type91"], cap_coverage=0.0, aaa_intensity=0.05, ammo=0.0,
        attacker_speed_kt=150, combat_drop=0.85, hits_to_cripple=2, hits_to_sink=3)
    _print_raid("A 拂晓G4M突袭残队", rA)

    print("\n[5] 场景 B · 南云 Kate 突击 fork 企业号（减CAP）")
    print("    目标：CV 30kt 机动，fork 下 CAP 减半、高炮齐全")
    rB = raid_expected_hits(
        n_bombers=40, D=900, Vt_kt=30, cls="CV",
        rel=REL["Type91"], cap_coverage=0.5, aaa_intensity=0.7, ammo=1.0,
        attacker_speed_kt=110, combat_drop=0.45, hits_to_cripple=2, hits_to_sink=3)
    _print_raid("B 南云Kate突击企业号", rB)

    print("\n[6] 场景 B' · 对照：史实企业号（满CAP）下同样 40 架 Kate")
    rB2 = raid_expected_hits(
        n_bombers=40, D=900, Vt_kt=30, cls="CV",
        rel=REL["Type91"], cap_coverage=0.9, aaa_intensity=0.8, ammo=1.0,
        attacker_speed_kt=110, combat_drop=0.22, hits_to_cripple=2, hits_to_sink=3)
    _print_raid("B' 史实企业号(满CAP)", rB2)

    print("\n[7] 结论（结构）")
    print("    · 干净几何底证明：匀速/低速大舰是鱼雷机的『好靶子』，")
    print("      投弹距离 900m 时干净命中 CV≈%.0f%%、残队BB≈%.0f%%"
          % (drop_hit_rate(900, 30, 'CV')*100, drop_hit_rate(900, 8, 'BB')*100))
    print("    · 『打不中』主要来自战斗投弹成功率(combat_drop)与可靠性，")
    print("      而非几何——无掩护残队 combat_drop≈0.85 → 突袭高效；")
    print("      fork 企业号因水面清零→CAP减半→combat_drop 0.45 > 史实 0.22，")
    print("      故南云反杀的『牌』在 fork 下显著多于史实。")
    print("    · 三段链合理性：A 高效(残队无弹无CAP) → 金凯德被迫以航母填补")
    print("      防空真空追日战列舰 → 南云以保全之机动部队反杀企业号，自洽。")


def _print_raid(name, r):
    print(f"    [{name}]")
    print(f"      干净命中/雷 = {r['clean_floor']*100:5.1f}%  | 战损率 = {r['loss_rate']*100:4.1f}%")
    print(f"      有效投雷机 = {r['effective_bombers']:5.1f}  | 单雷命中期望 = {r['p_hit_per_drop']*100:4.1f}%")
    print(f"      期望命中数 = {r['exp_hits']:5.2f}  | 重创概率 = {r['p_cripple']*100:5.1f}%  | 沉没概率 = {r['p_sink']*100:5.1f}%")


if __name__ == "__main__":
    report()
