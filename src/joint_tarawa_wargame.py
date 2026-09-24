# -*- coding: utf-8 -*-
"""
joint_tarawa_wargame.py
=====================================================================
塔拉瓦 1943 末 · 联合推演（基于本仓库 FEM 系统）
---------------------------------------------------------------------
承接：
  · 瓜岛推演稿-长期影响 (fork：日本赢瓜岛、拿到"完整 1943")
  · 瓜岛推演稿-塔拉瓦1943末·fork推演 (三因子：驻扎战斗机+南云第二舰队+小泽航母)
  · src/mc_fem.py          (夜战水面, 标定校准)
  · src/torpedo_fem.py     (DD/潜艇直航雷 几何底)
  · src/aerial_torpedo_fem.py (飞机投雷几何 + 反击被击中战损)
  · src/aircraft_dogfight_fem.py (能量/回转机动 dogfight 交换比)

用户 2026-09-24 给定的战役序列（"这是一场大战"）：
  [P0] 美军抵达，开始空袭塔拉瓦；日本以【金星零战】护航【陆攻】反击。
  [P1] 四天后美军主队上岛；近海战舰分【拦截队】(挡日本救援) 与【炮击队】(轰岛)。
  [P2] 日本模仿 1942-10-25：夜间由【第二舰队】(因美投新锐战列舰，加强大和、武藏)
        在【南云】指挥下先行夜战。
  [P3] 次日拂晓，从其他地域集结的【陆攻】(含因产能改善+换装【火星发动机】的【银河】)
        与【金星零战】前往袭击美【慢速战列舰为主之本队】，并引诱美航母空战。
  [P4] 【小泽】集中航空兵，发动【跨越轰炸】：航母起飞后立即后撤离开美打击范围，
        飞行员空袭后退往附近岸上机场，加油后次日再战。
  [P5] 双方潜艇互相前进，互试图进攻对方舰队。
  [P6] 日本以【丁型(松型)驱逐舰 + 舰队潜艇】撤运塔拉瓦残兵。
       日本此战方针＝杀伤美军舰机 + 撤出守军，**不夺回塔拉瓦**。

方法论（与本仓库同源）：先算干净底 → 叠标定干扰因子 → 蒙特卡洛累计舰队状态。
=====================================================================
"""
import math
import random
import sys
import os

# 同目录导入子模型
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import torpedo_fem as TF
import aerial_torpedo_fem as ATF
import aircraft_dogfight_fem as ADF

RNG = random.Random(42)

# ────────────────────────────────────────────────────────────────────────────
# 0. 兵力结构（fork 1943-11 基线，单位＝艘/架；均按《长期影响》fork 口径）
# ────────────────────────────────────────────────────────────────────────────
# 美军（fork：1942 多沉航母+队长种子减少 ⇒ 可用联队 ×0.8，aircraft_dogfight QUANTITY）
US_FLEET = {
    "CV": 4, "CVL": 4, "BB_new": 5, "CA": 9, "CL": 8, "DD": 28, "SS": 12,
    "aircraft": 560,            # TF50 可部署机数（OTL ~700 × 0.8）
}
# 日军（fork：油旁训练+产能无忧+金星零战交付 ⇒ 可部署航空队 ×1.3）
JP_FLEET = {
    "CV": 6,                       # 第三舰队(小泽)：翔鹤/瑞鹤/瑞凤/隼鹰/飞鹰/龙凤
    "BB_super": 2,                 # 大和、武藏（第二舰队核心）
    "BB": 4,                       # 金刚级等
    "CA": 10, "CL": 8, "DD": 36, "SS": 18,
    "land_bombers": 120,           # 陆攻(G4M 及 银河) 可出击数（含南洋/马绍尔集结）
    "garrison_fighters": 45,       # 塔拉瓦驻扎战斗机(金星零战) 小战队
    "carrier_aircraft": 400,       # 小泽航母群机数（金星零战为主）
}

# ────────────────────────────────────────────────────────────────────────────
# 1. 标定常量（来自子模型 run 输出，2026-09-24 版；铁律 #16：引用须带版）
# ────────────────────────────────────────────────────────────────────────────
# 空战交换比（日/美）：fork 金星零战 vs US_fork(F6F) 单场 1.10 / 战役 1.78
EXCH_DOGFIGHT = 1.10
# 鱼雷空袭：满 CAP 入侵舰队 combat_drop≈0.22（打不沉核心，仅重创）
CD_FULLCAP = 0.22
CD_LIGHTCAP = 0.55      # 美航母被引开、慢速本队 CAP 稀薄
# DD 直航雷（torpedo_fem）：18km/20kt/N=9 编队，per-any≈0.44，Type93 可靠 0.80
TORP_CLEAN_ANY, TORP_CLEAN_TGT, _ = TF.torp_hit_rate(18000, 20, 9, "BB")
TORP_REL_JP = 0.80      # 九三式
TORP_REL_US = 0.07      # Mk-15(1942)
# 30.25% 美损是 10-25 fork 夜战胜负的标定锚；此处日本攻、量级同族
# 用户 2026-09-24 补充：①双方都有路可退(可撤退) ②双方雷达都用上
#   ⇒ 日雷达使夜战命中更准(美损略升)，但互有雷达探测+可撤退 ⇒ 不歼灭、分沉没/撤退
NIGHT_US_LOSS_BB = 0.34  # 美拦截队夜战损失基准（含日雷达修正）
NIGHT_JP_LOSS_DD = 0.15  # 日 DD 夜战损失（美雷达+CIC；日也探测到故不盲打）
# 撤退机制：败方在达到阈值损伤后脱离接触 ⇒ 损失分「沉没」与「撤退(幸存但退场)」
RETREAT_MAX_FRAC = 0.45  # 单阶段单方可损失(沉+撤)上限（有路可退）
RETREAT_SUNK_FRAC = 0.50 # 损失中"真正沉没"占比（其余为撤退幸存）

# 塔拉瓦守备（fork：含驻扎战斗机训练的地面部队；残兵待撤出）
GARRISON_TOTAL = 4800
JP_EVAC_DD = 18        # 投入撤运的【丁型(松型)驱逐舰】数（JP_DD 子集，专司撤运）
JP_EVAC_SS = 12        # 投入撤运的舰队潜艇数（伊号大型潜艇，可载兵）
DD_TROOPS = 250        # 每艘丁型驱逐舰可撤运战斗员人数（史实松型撤运任务量级）
SS_TROOPS = 110        # 每艘大型舰队潜艇可撤运战斗员人数（伊号潜艇运兵量级）
# ⇒ 单航次理论撤运上限 = 18*250 + 12*110 = 4,500+；需多航次，受美海空封锁强度制约

def _retreat_split(count, loss_frac, rng):
    """对 count 艘舰施加 loss_frac 损失，按 RETREAT 拆成 (沉没, 撤退)。
    败方在达到阈值损伤后脱离接触 ⇒ 损失封顶且分沉/撤。"""
    loss_frac = min(RETREAT_MAX_FRAC, max(0.0, loss_frac))
    total = int(round(count * loss_frac))
    sunk = int(round(total * RETREAT_SUNK_FRAC))
    wd = total - sunk
    return sunk, wd

# ────────────────────────────────────────────────────────────────────────────
# 2. 各阶段解算函数
# ────────────────────────────────────────────────────────────────────────────
def _apply_loss(fleet, key, frac, rng, jitter=0.25):
    """对 fleet[key] 施加 frac 损失（带抖动），返回损失数。"""
    base = fleet[key]
    f = max(0.0, min(1.0, frac + rng.gauss(0, frac * jitter)))
    lost = int(round(base * f))
    fleet[key] = max(0, base - lost)
    return lost

def phase0_air_campaign(us, jp, rng):
    """P0：美军空袭塔拉瓦 + 金星零战护航陆攻反击。
    返回 (us_aircraft_lost, jp_land_bombers_lost, jp_garrison_fighter_lost)。"""
    # (a) 美军舰载机空袭塔拉瓦守军：遭驻扎金星零战拦截 → 空战交换比 EXCH_DOGFIGHT
    #     美军出击强度 vs 守军小战队，美军损失按交换比折算
    us_strike_sorties = us["aircraft"] * 0.25
    jp_def_lost = jp["garrison_fighters"] * rng.uniform(0.10, 0.20)  # 起飞拦截被耗
    # 美军损失 = 守军击杀 × 交换比的倒数（美/日 = 1/1.10）
    us_lost = jp_def_lost * (1.0 / EXCH_DOGFIGHT) * rng.uniform(0.8, 1.2)
    us["aircraft"] = max(0, us["aircraft"] - int(round(us_lost)))
    jp["garrison_fighters"] = max(0, jp["garrison_fighters"] - int(round(jp_def_lost)))

    # (b) 金星零战护航 G4M 反击美航母舰队（满 CAP）：鱼雷/水平轰炸
    r = ATF.raid_expected_hits(
        n_bombers=int(jp["land_bombers"] * 0.30), D=900, Vt_kt=30, cls="CV",
        rel=ATF.REL["Type91"], cap_coverage=0.9, aaa_intensity=0.8, ammo=1.0,
        attacker_speed_kt=150, combat_drop=CD_FULLCAP,
        hits_to_cripple=2, hits_to_sink=3)
    jp_bomber_loss = int(round(r["loss_rate"] * jp["land_bombers"] * 0.30))
    jp["land_bombers"] = max(0, jp["land_bombers"] - jp_bomber_loss)
    # 美航母重创（满 CAP 下仅重创，不沉核心）
    cv_crip = r["p_cripple"]
    if rng.random() < cv_crip * 0.5:   # 约半数重创概率实际落到 1 艘
        us["CV"] = max(0, us["CV"] - 1)
    return int(round(us_lost)), jp_bomber_loss, int(round(jp_def_lost))

def phase1_landing_split(us, rng):
    """P1：D+4 登陆；近海分拦截队/炮击队。
    返回 (intercept, bombard) 两个子结构（复制计数）。"""
    intercept = {
        "BB_new": max(1, int(us["BB_new"] * 0.4)),
        "CA": max(2, int(us["CA"] * 0.5)),
        "CL": max(2, int(us["CL"] * 0.5)),
        "DD": max(6, int(us["DD"] * 0.5)),
    }
    bombard = {
        "BB_new": us["BB_new"] - intercept["BB_new"],   # 慢速本队（炮击队）
        "CA": us["CA"] - intercept["CA"],
        "CL": us["CL"] - intercept["CL"],
        "DD": us["DD"] - intercept["DD"],
    }
    return intercept, bombard

def phase2_night_surface(jp, us, intercept, rng):
    """P2：南云第二舰队(大和/武藏)夜间水面战 vs 美拦截队。
    用 torpedo_fem 几何底 + 10-25 fork 夜战胜负标定。"""
    # 日 DD 九三式齐射（打断美战列线）：per-any 0.44 × 可靠 0.80 × 穿幕 0.75
    tubes = 36 * 8 * 0.75                     # 36 DD × 8 管 × 穿幕率
    exp_hits = tubes * TORP_CLEAN_ANY * TORP_REL_JP
    # 命中摊到拦截队各舰；每舰 ≥2 命中→重创、≥4→沉
    ships = (intercept["BB_new"] + intercept["CA"] + intercept["CL"]
             + intercept["DD"])
    per_ship = exp_hits / max(1, ships)
    bb_lost = 0
    for _ in range(intercept["BB_new"]):
        if per_ship >= 2 and rng.random() < min(1.0, per_ship / 4):
            bb_lost += 1
    ca_lost = int(round(intercept["CA"] * NIGHT_US_LOSS_BB * 0.6))
    dd_lost = int(round(intercept["DD"] * NIGHT_US_LOSS_BB * 0.5))
    # 日方损失：美雷达夜战炮火主要打日 DD
    jp_dd_lost = int(round(jp["DD"] * NIGHT_JP_LOSS_DD))
    intercept["BB_new"] = max(0, intercept["BB_new"] - bb_lost)
    intercept["CA"] = max(0, intercept["CA"] - ca_lost)
    intercept["DD"] = max(0, intercept["DD"] - dd_lost)
    jp["DD"] = max(0, jp["DD"] - jp_dd_lost)
    return bb_lost, ca_lost, dd_lost, jp_dd_lost

def phase3_dawn_strike(jp, us, intercept, bombard, rng):
    """P3：拂晓陆攻(含银河/火星) + 金星零战 袭美慢速本队(炮击队)，诱美航母空战。"""
    # (a) 陆攻袭慢速本队：CAP 稀薄(美航母被引到空战) ⇒ combat_drop 升
    r = ATF.raid_expected_hits(
        n_bombers=int(jp["land_bombers"] * 0.7), D=900, Vt_kt=12, cls="BB",
        rel=ATF.REL["Type91"], cap_coverage=CD_LIGHTCAP, aaa_intensity=0.6,
        ammo=1.0, attacker_speed_kt=150, combat_drop=CD_LIGHTCAP,
        hits_to_cripple=2, hits_to_sink=3)
    bb_lost = 0
    if rng.random() < r["p_sink"]:
        bb_lost = max(1, int(round(bombard["BB_new"] * 0.4)))
    bombard["BB_new"] = max(0, bombard["BB_new"] - bb_lost)

    # (b) 金星零战 vs 美 CAP（诱空战）：用 dogfight 交换比
    #     日出时美航母需派 CAP 护本队，与日机空战
    exp_us_lost = us["aircraft"] * 0.10 * (1.0 / EXCH_DOGFIGHT)  # 美/日=1/1.10
    exp_jp_lost = exp_us_lost * EXCH_DOGFIGHT
    us_air = int(round(exp_us_lost))
    jp_air = int(round(min(exp_jp_lost, jp["carrier_aircraft"] * 0.10)))
    us["aircraft"] = max(0, us["aircraft"] - us_air)
    jp["carrier_aircraft"] = max(0, jp["carrier_aircraft"] - jp_air)
    return bb_lost, us_air, jp_air

def phase4_cross_over(jp, us, rng):
    """P4：小泽跨越轰炸——航母发射后撤、飞行员退岸加油再战。
    特征：日航母存活率高(后撤)，但飞行员/机数双耗；美航母被钉在支援位。"""
    # 第一击：航母机群全出击
    s1 = jp["carrier_aircraft"] * 0.6
    # 第二击(次日)：跨越轰炸带来的额外波次（岸基加油再战）
    s2 = jp["carrier_aircraft"] * 0.45 * 0.9     # 岸基再整备折损
    total_sortie = s1 + s2
    # 命中效率：满 CAP 入侵舰队(美主力仍在) → combat_drop 0.22
    # 但跨越轰炸使日机"打了就跑"，自身损失低
    jp_loss_rate = 0.10                            # 远低于正面 0.4+
    # 美航母损失：按交换比 EXCH_DOGFIGHT（日优），且美航母暴露
    us_cv_crip = total_sortie / max(1, us["aircraft"]) * EXCH_DOGFIGHT * 0.05
    cv_lost = 0
    if rng.random() < min(0.6, us_cv_crip):
        cv_lost = 1
        if rng.random() < 0.4:
            cv_lost = 2
    us["CV"] = max(0, us["CV"] - cv_lost)
    jp_air_loss = int(round(total_sortie * jp_loss_rate))
    jp["carrier_aircraft"] = max(0, jp["carrier_aircraft"] - jp_air_loss)
    # 日航母因后撤，几乎无损失
    jp_cv_lost = 0
    return cv_lost, jp_air_loss, jp_cv_lost

def phase5_submarines(jp, us, rng):
    """P5：双方潜艇互攻。I 艇(日) vs 美舰队；美潜艇 vs 日舰队。
    潜艇鱼雷(九五式/Mark14) 特性：隐蔽突袭 → combat 高，但航速低、再装填慢。"""
    # 日 I 艇袭美（美已分散，且部分被夜战/空袭削弱）
    i_sorties = jp["SS"] * rng.uniform(0.4, 0.7)
    # 美反潜/警戒强(CIC) ⇒ 日艇命中率低
    jp_sub_hit = i_sorties * 0.04 * TORP_REL_JP
    us_ship_lost = int(round(jp_sub_hit))
    us["DD"] = max(0, us["DD"] - us_ship_lost)
    # 美潜艇袭日（日舰队集中且燃油无忧但警戒一般）
    us_sub_sorties = us["SS"] * rng.uniform(0.4, 0.7)
    us_sub_hit = us_sub_sorties * 0.06 * TORP_REL_US / 0.07  # 用 Mk-14 较可靠假定
    jp_ship_lost = int(round(us_sub_hit))
    jp["DD"] = max(0, jp["DD"] - jp_ship_lost)
    # 双方潜艇互有损失（被反潜）
    jp["SS"] = max(0, jp["SS"] - int(round(jp["SS"] * 0.15)))
    us["SS"] = max(0, us["SS"] - int(round(us["SS"] * 0.15)))
    return us_ship_lost, jp_ship_lost

def phase6_evacuate(jp, us, rng):
    """P6：日本以【丁型(松型)驱逐舰 + 舰队潜艇】撤运塔拉瓦残兵。
    日本此战方针＝杀伤美军舰机 + 撤出守军，不夺回塔拉瓦。
    撤运成功率受美海空封锁强度制约（美拦截队/炮击队仍在场）。"""
    lift_per_sortie = JP_EVAC_DD * DD_TROOPS + JP_EVAC_SS * SS_TROOPS  # 4,500+ 人/航次
    # 美封锁强度：拦截队/炮击队残存越多 + 美航母仍在场 ⇒ 封锁越硬 ⇒ 撤运率越低
    us_pressure = (us["CV"] + us["CVL"]) * 0.10 + (us["BB_new"] + us["CA"]) * 0.05
    evac_rate = max(0.15, min(0.65, 0.55 - us_pressure * 0.02 + rng.gauss(0, 0.08)))
    evac_rate = max(0.10, min(0.70, evac_rate))
    # 受 lift 上限（多航次但封锁下实战仅 1–2 航次可得）：
    evac_headcount = int(min(GARRISON_TOTAL * evac_rate, lift_per_sortie * 1.8))
    # 撤运船队自身损失（被美海空拦截）
    evac_dd_lost = int(round(JP_EVAC_DD * (0.10 + 0.10 * (1 - evac_rate))))
    evac_ss_lost = int(round(JP_EVAC_SS * (0.08 + 0.08 * (1 - evac_rate))))
    jp["DD"] = max(0, jp["DD"] - evac_dd_lost)
    jp["SS"] = max(0, jp["SS"] - evac_ss_lost)
    return evac_headcount, evac_dd_lost, evac_ss_lost

# ────────────────────────────────────────────────────────────────────────────
# 3. 单次战役推演
# ────────────────────────────────────────────────────────────────────────────
def campaign(rng):
    us = dict(US_FLEET)
    jp = dict(JP_FLEET)
    log = {}
    log["p0"] = phase0_air_campaign(us, jp, rng)
    intercept, bombard = phase1_landing_split(us, rng)
    log["p2"] = phase2_night_surface(jp, us, intercept, rng)
    bb2, ca2, dd2, jpdd2 = log["p2"]
    # 回写：P2 损失发生在拦截队(us 的子集)上，须扣减主舰队
    us["BB_new"] = max(0, us["BB_new"] - bb2)
    us["CA"]     = max(0, us["CA"] - ca2)
    us["DD"]     = max(0, us["DD"] - dd2)

    log["p3"] = phase3_dawn_strike(jp, us, intercept, bombard, rng)
    bb3, usair3, jpair3 = log["p3"]
    us["BB_new"] = max(0, us["BB_new"] - bb3)   # 拂晓突击落在炮击队(慢速本队)
    # us["aircraft"] 已在 P3 内扣减

    log["p4"] = phase4_cross_over(jp, us, rng)
    log["p5"] = phase5_submarines(jp, us, rng)
    evac_headcount, evac_dd_lost, evac_ss_lost = phase6_evacuate(jp, us, rng)
    log["p6"] = (evac_headcount, evac_dd_lost, evac_ss_lost)

    # 夺岛判定（全战档，铁律 #17）：美军仍可投兵（35,000 vs 5,000 守军），
    # 即便登陆更血腥，结构性事实不翻转 → 夺岛恒为真（除非美舰队被全歼到无法支援）
    us_fleet_alive = us["CV"] + us["CVL"] + us["BB_new"] + us["CA"]
    captured = us_fleet_alive >= 6   # 仍有足够兵力维持封锁/支援

    # 日本此战方针＝杀伤美军舰机 + 撤出守军（不夺回塔拉瓦）
    # 杀伤计分：美损失舰(加权) + 美损失机
    us_ships_lost = ((US_FLEET["CV"] - us["CV"]) + (US_FLEET["CVL"] - us["CVL"])
                     + (US_FLEET["BB_new"] - us["BB_new"]) + (US_FLEET["CA"] - us["CA"])
                     + (US_FLEET["CL"] - us["CL"]) + (US_FLEET["DD"] - us["DD"]))
    us_air_lost = US_FLEET["aircraft"] - us["aircraft"]
    jp_attrition_score = us_ships_lost * 1.0 + us_air_lost / 100.0
    evac_frac = evac_headcount / GARRISON_TOTAL
    return {
        "us": us, "jp": jp, "intercept_loss": intercept,
        "bombard_loss": bombard, "captured": captured,
        "evac_headcount": evac_headcount, "evac_frac": evac_frac,
        "us_ships_lost": us_ships_lost, "us_air_lost": us_air_lost,
        "jp_attrition_score": jp_attrition_score, "log": log,
    }

# ────────────────────────────────────────────────────────────────────────────
# 4. 蒙特卡洛聚合
# ────────────────────────────────────────────────────────────────────────────
def run(n=500, seed=42):
    rng = random.Random(seed)
    results = [campaign(rng) for _ in range(n)]
    # 聚合
    def agg(key_path, meth=min):
        vals = []
        for r in results:
            o = r
            for k in key_path:
                o = o[k]
            vals.append(o)
        return sum(vals) / len(vals)
    us_keys = ["CV", "CVL", "BB_new", "CA", "CL", "DD", "SS", "aircraft"]
    jp_keys = ["CV", "BB_super", "BB", "CA", "CL", "DD", "SS",
               "land_bombers", "garrison_fighters", "carrier_aircraft"]
    print("=" * 82)
    print("  塔拉瓦 1943 末 · 联合推演（基于 FEM 系统）  n=%d  seed=%d" % (n, seed))
    print("=" * 82)
    print("\n[初始兵力]")
    print("  美: CV%d CVL%d BB新%d CA%d CL%d DD%d SS%d 机%d"
          % (US_FLEET["CV"], US_FLEET["CVL"], US_FLEET["BB_new"],
              US_FLEET["CA"], US_FLEET["CL"], US_FLEET["DD"],
              US_FLEET["SS"], US_FLEET["aircraft"]))
    print("  日: CV%d 大和/武藏%d BB%d CA%d CL%d DD%d SS%d 陆攻%d 驻扎机%d 航母机%d"
          % (JP_FLEET["CV"], JP_FLEET["BB_super"], JP_FLEET["BB"],
              JP_FLEET["CA"], JP_FLEET["CL"], JP_FLEET["DD"], JP_FLEET["SS"],
              JP_FLEET["land_bombers"], JP_FLEET["garrison_fighters"],
              JP_FLEET["carrier_aircraft"]))

    print("\n[均值剩余兵力]")
    print("  %-8s %8s %8s %8s" % ("类别", "初始", "美剩余", "日剩余"))
    for k in us_keys:
        init = US_FLEET[k]
        mean = agg(["us", k])
        print("  美 %-5s %8d %8.1f" % (k, init, mean))
    for k in jp_keys:
        init = JP_FLEET[k]
        mean = agg(["jp", k])
        print("  日 %-14s %8d %8.1f" % (k, init, mean))

    print("\n[夺岛结果]  (全战档，铁律 #17：结构性事实不翻转)")
    cap = sum(1 for r in results if r["captured"]) / n
    print("  美军夺岛概率 = %.1f%%  (日方方针＝不夺回，只杀伤+撤运)" % (cap * 100))

    print("\n[日本此战目标：杀伤美军 + 撤出守军]")
    evac_mean = sum(r["evac_headcount"] for r in results) / n
    evac_frac_mean = sum(r["evac_frac"] for r in results) / n
    us_ships_mean = sum(r["us_ships_lost"] for r in results) / n
    us_air_mean = sum(r["us_air_lost"] for r in results) / n
    print("  守军撤出 均值 = %.0f 人 / %.1f%% (丁型驱逐舰+潜艇, 受美封锁制约)"
          % (evac_mean, evac_frac_mean * 100))
    print("  美舰损失 均值 = %.2f 艘(CV/CVL/BB新/CA/CL/DD 加权)" % us_ships_mean)
    print("  美机损失 均值 = %.0f 架" % us_air_mean)
    print("  ⇒ 日本'达成度'锚：杀伤 + 撤运；不翻转夺岛，但可大幅抬高美血腥度")

    print("\n[关键损失均值]")
    print("  美 CV 沉/重创 均值 = %.2f (初始 %d)" % (US_FLEET["CV"] - agg(["us", "CV"]), US_FLEET["CV"]))
    print("  日 CV 沉/重创 均值 = %.2f (初始 %d)" % (JP_FLEET["CV"] - agg(["jp", "CV"]), JP_FLEET["CV"]))
    print("  美 BB新 损失(夜战+拂晓) 均值 = %.2f"
          % (US_FLEET["BB_new"] - (agg(["us", "BB_new"]))))
    print("  日 航母机 消耗 均值 = %.1f / 初始 %d (跨越轰炸双波次+空战)"
          % (JP_FLEET["carrier_aircraft"] - agg(["jp", "carrier_aircraft"]),
             JP_FLEET["carrier_aircraft"]))

    print("\n[空战交换比锚]  日/美 = %.2f (aircraft_dogfight_fem, fork 金星零战 vs US_fork)"
          % EXCH_DOGFIGHT)
    print("[诚实边界] 战役数量乘数(日×1.3/美×0.8)、跨越轰炸双波次、潜艇命中率均")
    print("          为建模假设；承重墙＝日本航母/飞行员不可补充(铁律 #9/#11)。")
    print("=" * 82)
    return results

if __name__ == "__main__":
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    run(n=N)
