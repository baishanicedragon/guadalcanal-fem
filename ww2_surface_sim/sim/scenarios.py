# -*- coding: utf-8 -*-
"""
scenarios.py · 场景数据（OOB）
================================
瓜岛：完整填充，数据来自金山文档《瓜岛推演稿-不疯的山本》的单位编成表。
中途岛 / 塔拉瓦：结构占位，数据待从金山文档 / GitHub 仓库回填（同项目）。

注意：武器 reliability 直接编码了"武器质量浮动"——
  九三式≈0.80（接触引信可靠），Mk-15≈0.07（1942 磁引信灾难）。
"""
from . import model as M


def _w(name, kind, caliber, rng_m, rpm, rel, disp=0.10, pk=0.10):
    return M.Weapon(name=name, kind=kind, caliber=caliber, range_m=rng_m,
                    rate_per_min=rpm, reliability=rel, disp_factor=disp, p_k=pk)


def _av(name, kind, rel=0.80):
    """航空武器占位：引擎当前跳过 aircraft/aerial_* 这些 kind，仅作 OOB 数据
    与后续航空整合（aerial_torpedo_fem / aircraft_dogfight_fem）使用。"""
    return M.Weapon(name=name, kind=kind, caliber=0.0, range_m=0.0,
                    rate_per_min=0.0, reliability=rel, disp_factor=0.10, p_k=0.10)


def _spread(units, x):
    """给某方所有单位按序布置初始 pos（纵向拉开）。"""
    for i, u in enumerate(units):
        u.pos = (x, float(i * 600))


def _af(name, side, sensor, ftr, torp, db):
    """机场单位（cls="AF"）：固定不动，hp=完好度%；挂航空武器(战斗机CAP + 攻击机 + 轰炸机)。
    受岸轰/空袭降完好度→出动率节流（见 engine._phase_damage / _phase_engage）。"""
    return M.Unit(name, side, "AF", hp=100, speed_kt=0, sensors=[sensor],
                  weapons=[_av("战斗机", "aircraft", 0.85),
                           _av("攻击机", "aerial_torpedo", 0.70),
                           _av("轰炸机", "aerial_bomb", 0.70)],
                  ammo={"战斗机": ftr, "攻击机": torp, "轰炸机": db})


def guadalcanal() -> M.Scenario:
    jp_optical = M.Sensor(kind="optical", band="medium", active_range_nm=22.0,
                          passive=True, reliability=0.55)
    us_radar = M.Sensor(kind="radar", band="high", active_range_nm=30.0,
                        passive=True, reliability=0.70)

    # —— 日方突击群 ——
    yamato = M.Unit("大和", "JP", "BB", hp=100, speed_kt=27, sensors=[jp_optical],
                    weapons=[_w("46cm_AP", "gun", 46, 30000, 2, 0.95),
                             _w("93式", "torpedo", 0, 18000, 0, 0.80, pk=0.30)],
                    ammo={"46cm_AP": 100, "93式": 12})
    hyuga = M.Unit("日向", "JP", "BB", hp=100, sensors=[jp_optical],
                   weapons=[_w("35.6cm_AP", "gun", 35.6, 30000, 2, 0.92)],
                   ammo={"35.6cm_AP": 80})
    isez = M.Unit("伊势", "JP", "BB", hp=100, sensors=[jp_optical],
                  weapons=[_w("35.6cm_AP", "gun", 35.6, 30000, 2, 0.92)],
                  ammo={"35.6cm_AP": 80})
    fuso = M.Unit("扶桑", "JP", "BB", hp=100, sensors=[jp_optical],
                  weapons=[_w("35.6cm_AP", "gun", 35.6, 30000, 2, 0.92)],
                  ammo={"35.6cm_AP": 80})
    yamashiro = M.Unit("山城", "JP", "BB", hp=100, sensors=[jp_optical],
                       weapons=[_w("35.6cm_AP", "gun", 35.6, 30000, 2, 0.92)],
                       ammo={"35.6cm_AP": 80})
    kongo = M.Unit("金刚", "JP", "BB", hp=100, sensors=[jp_optical],
                   weapons=[_w("35.6cm_AP", "gun", 35.6, 30000, 2, 0.92)],
                   ammo={"35.6cm_AP": 80})
    haruna = M.Unit("榛名", "JP", "BB", hp=100, sensors=[jp_optical],
                    weapons=[_w("35.6cm_AP", "gun", 35.6, 30000, 2, 0.92)],
                    ammo={"35.6cm_AP": 80})
    chokai = M.Unit("鸟海", "JP", "CA", hp=70, sensors=[jp_optical],
                    weapons=[_w("20.3cm_AP", "gun", 8, 24000, 3, 0.90)],
                    ammo={"20.3cm_AP": 100})
    kinugasa = M.Unit("衣笠", "JP", "CA", hp=70, sensors=[jp_optical],
                      weapons=[_w("20.3cm_AP", "gun", 8, 24000, 3, 0.90)],
                      ammo={"20.3cm_AP": 100})
    kitsukami = M.Unit("北上", "JP", "CL", hp=50, sensors=[jp_optical],
                       weapons=[_w("14cm_AP", "gun", 14, 15000, 2.5, 0.90),
                                _w("93式", "torpedo", 0, 18000, 0, 0.80, pk=0.30)],
                       ammo={"14cm_AP": 150, "93式": 24})
    oi = M.Unit("大井", "JP", "CL", hp=50, sensors=[jp_optical],
                weapons=[_w("14cm_AP", "gun", 14, 15000, 2.5, 0.90),
                         _w("93式", "torpedo", 0, 18000, 0, 0.80, pk=0.30)],
                ammo={"14cm_AP": 150, "93式": 24})
    jp_dds = [M.Unit(f"日驱{i}", "JP", "DD", hp=30, sensors=[jp_optical],
                     weapons=[_w("12.7cm", "gun", 5, 10000, 4, 0.90),
                              _w("93式", "torpedo", 0, 18000, 0, 0.80, pk=0.30)],
                     ammo={"12.7cm": 80, "93式": 8}) for i in range(1, 7)]

    # 初始位置：肖特兰南下，铁底湾接敌（约 10 km 间隔，机动接敌）
    for i, u in enumerate([yamato, hyuga, isez, fuso, yamashiro, kongo, haruna,
                           chokai, kinugasa, kitsukami, oi] + jp_dds):
        u.pos = (0.0, float(i * 800))

    # —— 美方拦截群 ——
    washington = M.Unit("华盛顿", "US", "BB", hp=100, sensors=[us_radar],
                        weapons=[_w("16in_AP", "gun", 16, 30000, 2, 0.95)],
                        ammo={"16in_AP": 100})
    southdakota = M.Unit("南达科他", "US", "BB", hp=100, sensors=[us_radar],
                         weapons=[_w("16in_AP", "gun", 16, 30000, 2, 0.95)],
                         ammo={"16in_AP": 100})
    sf = M.Unit("旧金山", "US", "CA", hp=70, sensors=[us_radar],
                weapons=[_w("8in_AP", "gun", 8, 24000, 3, 0.90)],
                ammo={"8in_AP": 100})
    helena = M.Unit("海伦娜", "US", "CL", hp=50, sensors=[us_radar],
                    weapons=[_w("6in_AP", "gun", 6, 20000, 5, 0.90)],
                    ammo={"6in_AP": 150})
    atlanta = M.Unit("亚特兰大", "US", "CL", hp=50, sensors=[us_radar],
                     weapons=[_w("5in_AP", "gun", 5, 20000, 4, 0.90)],
                     ammo={"5in_AP": 150})
    us_dds = [M.Unit(f"美驱{i}", "US", "DD", hp=30, sensors=[us_radar],
                     weapons=[_w("5in_AP", "gun", 5, 10000, 4, 0.90),
                              _w("Mk15", "torpedo", 0, 18000, 0, 0.07, pk=0.30)],
                     ammo={"5in_AP": 80, "Mk15": 8}) for i in range(1, 6)]

    for i, u in enumerate([washington, southdakota, sf, helena, atlanta] + us_dds):
        u.pos = (7000.0, float(i * 800))

    # —— 机场（AF）：受岸轰/空袭降完好度→出动率节流 ——
    henderson = _af("亨德森机场", "US", us_radar, 30, 18, 40)
    henderson.pos = (7000.0, 3000.0)
    buin = _af("布干维尔机场", "JP", jp_optical, 25, 16, 36)
    buin.pos = (0.0, 6000.0)
    # —— 战役层增援（对称，到 tick=18 入场）——
    jp_reinf = [M.Unit(f"増援CA{i}", "JP", "CA", hp=70, sensors=[jp_optical],
                       weapons=[_w("20.3cm_AP", "gun", 8, 24000, 3, 0.90)],
                       ammo={"20.3cm_AP": 100}) for i in range(1, 3)]
    us_reinf = [M.Unit(f"増援CL{i}", "US", "CL", hp=50, sensors=[us_radar],
                       weapons=[_w("6in_AP", "gun", 6, 20000, 5, 0.90)],
                       ammo={"6in_AP": 150}) for i in range(1, 3)]
    jp_list = [yamato, hyuga, isez, fuso, yamashiro, kongo, haruna,
               chokai, kinugasa, kitsukami, oi] + jp_dds + [buin]
    us_list = [washington, southdakota, sf, helena, atlanta] + us_dds + [henderson]
    jp = M.Side("JP", jp_list, doctrine="bb_line",
                reinforcements=[M.Reinforcement(arrive_tick=18, label="jp_second_wave",
                                                units=jp_reinf)])
    us = M.Side("US", us_list, doctrine="surface",
                reinforcements=[M.Reinforcement(arrive_tick=18, label="us_second_wave",
                                                units=us_reinf)])
    return M.Scenario("瓜岛·不疯的山本", "surface", [jp, us], seed=42,
                     night=True, weather=0.1)


# 官僚主/C2 惩罚——可调旋钮（默认关闭）。历史 IJN 中途岛发挥不当很大程度源于
# 官僚主义（条令混乱、换弹犹豫、各部队信息割裂），抽象为 JP 方探测/火控质量折减。
# 设 0.15~0.30 模拟"狭缝"条令混乱导致的发挥不当；设 0.0 = 理想 C2（不展示历史失误）。
MIDWAY_BUREAUCRACY_PENALTY = 0.0


def midway() -> M.Scenario:
    """中途岛（史实编成 1942-06-04）· mission="carrier" · 昼战 / 晴天。

    数据锚点（金山文档 kdocs，已在本会话读取）：
      · 《红色联盟-男主中途岛观点概括.txt》——陈泰"中途岛=必败者主动求败的自导自演"。
      · 《红色联盟-中途岛正史狭缝与男主推论论证.txt》——七处"狭缝"论证（无雷达 /
        换弹混乱 / 6 架警戒机捉襟见肘 / 机库汽油引爆）说明日航母败局由技术条令必然推出。
    设定学说的落点（非 OOB 改动，史实编成不变）：
      · JP doctrine="bait_operation"：山本以航母+登陆部队为诱饵逼美军决战；
        日航母仅配 optical 传感器（史实无雷达），体现"无雷达→机库致命点"脆弱性。
      · US doctrine="carrier"：靠破译全貌 + 舰载机俯冲收割（麦克拉斯基转弯）。
    官僚主义抽象：JP Side.c2_penalty = MIDWAY_BUREAUCRACY_PENALTY（默认 0，仅作可调项，
    非主要机制——用户判定"官僚主义影响发挥"是历史副因，应可关可开，不进核心）。
    OOB 编成（赤城/加贺/苍龙/飞龙 + 利根筑摩/最上铃谷熊野 + 榛名雾岛 + 驱逐；
    企业/大黄蜂/约克城 + 重轻巡+驱逐 + 中途岛守军航空队）为史实重建，
    与 GitHub 仓库同项目口径一致。
    """
    us_radar = M.Sensor(kind="radar", band="high", active_range_nm=30.0,
                       passive=True, reliability=0.70)
    jp_optical = M.Sensor(kind="optical", band="medium", active_range_nm=22.0,
                         passive=True, reliability=0.55)

    # —— 美军（TF16 企业/大黄蜂 + TF17 约克城） ——
    us_units = []
    for nm, ftr, torp, db in [("企业号 Enterprise", 27, 14, 37),
                              ("大黄蜂号 Hornet", 27, 15, 35),
                              ("约克城号 Yorktown", 25, 13, 37)]:
        us_units.append(M.Unit(
            nm, "US", "CV", hp=130, speed_kt=32, sensors=[us_radar],
            weapons=[_av("舰载战斗机", "aircraft", 0.90),
                     _av("舰载鱼雷机", "aerial_torpedo", 0.65),
                     _av("舰载俯冲轰炸机", "aerial_bomb", 0.70)],
            ammo={"舰载战斗机": ftr, "舰载鱼雷机": torp, "舰载俯冲轰炸机": db}))

    for nm in ["新奥尔良 NewOrleans", "明尼阿波利斯 Minneapolis", "文森斯 Vincennes",
               "北安普顿 Northampton", "彭萨科拉 Pensacola", "阿斯托里亚 Astoria",
               "波特兰 Portland"]:
        us_units.append(M.Unit(
            nm, "US", "CA", hp=70, speed_kt=32, sensors=[us_radar],
            weapons=[_w("8in_AP", "gun", 8, 24000, 3, 0.90)],
            ammo={"8in_AP": 100}))

    for nm in ["亚特兰大 Atlanta", "圣胡安 SanJuan", "圣路易斯 StLouis"]:
        us_units.append(M.Unit(
            nm, "US", "CL", hp=50, speed_kt=32, sensors=[us_radar],
            weapons=[_w("5in_AP", "gun", 5, 20000, 4, 0.90)],
            ammo={"5in_AP": 150}))

    for i in range(1, 11):
        us_units.append(M.Unit(
            f"美驱{i}", "US", "DD", hp=30, speed_kt=36, sensors=[us_radar],
            weapons=[_w("5in_AP", "gun", 5, 10000, 4, 0.90),
                     _w("Mk15", "torpedo", 0, 18000, 0, 0.07, pk=0.30)],
            ammo={"5in_AP": 80, "Mk15": 8}))

    us_units.append(M.Unit(
        "中途岛守军航空队", "US", "AF", hp=130, speed_kt=0, sensors=[us_radar],
        weapons=[_av("岸基战斗机", "aircraft", 0.80),
                 _av("岸基鱼雷机", "aerial_torpedo", 0.60),
                 _av("岸基轰炸机", "aerial_bomb", 0.65)],
        ammo={"岸基战斗机": 40, "岸基鱼雷机": 30, "岸基轰炸机": 50}))

    # —— 日军（机动部队 Kido Butai） ——
    jp_units = []
    for nm, ftr, torp, db in [("赤城 Akagi", 21, 21, 21),
                              ("加贺 Kaga", 21, 30, 21),
                              ("苍龙 Soryu", 21, 18, 21),
                              ("飞龙 Hiryu", 21, 18, 21)]:
        jp_units.append(M.Unit(
            nm, "JP", "CV", hp=130, speed_kt=34, sensors=[jp_optical],
            weapons=[_av("舰载战斗机", "aircraft", 0.85),
                     _av("舰载鱼雷机", "aerial_torpedo", 0.75),
                     _av("舰载俯冲轰炸机", "aerial_bomb", 0.75)],
            ammo={"舰载战斗机": ftr, "舰载鱼雷机": torp, "舰载俯冲轰炸机": db}))

    for nm in ["利根 Tone", "筑摩 Chikuma", "三隈 Mikuma", "最上 Mogami",
               "铃谷 Suzuya", "熊野 Kumano"]:
        jp_units.append(M.Unit(
            nm, "JP", "CA", hp=70, speed_kt=35, sensors=[jp_optical],
            weapons=[_w("20.3cm_AP", "gun", 8, 24000, 3, 0.90)],
            ammo={"20.3cm_AP": 100}))

    for nm in ["榛名 Haruna", "雾岛 Kirishima"]:
        jp_units.append(M.Unit(
            nm, "JP", "BB", hp=100, speed_kt=29, sensors=[jp_optical],
            weapons=[_w("35.6cm_AP", "gun", 35.6, 30000, 2, 0.92)],
            ammo={"35.6cm_AP": 80}))

    for i in range(1, 11):
        jp_units.append(M.Unit(
            f"日驱{i}", "JP", "DD", hp=30, speed_kt=34, sensors=[jp_optical],
            weapons=[_w("12.7cm", "gun", 5, 10000, 4, 0.90),
                     _w("93式", "torpedo", 0, 18000, 0, 0.80, pk=0.30)],
            ammo={"12.7cm": 80, "93式": 8}))

    jp_units.append(M.Unit(
        "日岸基航空队", "JP", "AF", hp=130, speed_kt=0, sensors=[jp_optical],
        weapons=[_av("岸基侦察机", "aircraft", 0.70),
                 _av("岸基攻击机", "aerial_torpedo", 0.70)],
        ammo={"岸基侦察机": 20, "岸基攻击机": 25}))

    _spread(jp_units, 0.0)
    _spread(us_units, 9000.0)

    jp = M.Side("JP", jp_units, doctrine="bait_operation",
                c2_penalty=MIDWAY_BUREAUCRACY_PENALTY)
    us = M.Side("US", us_units, doctrine="carrier")
    return M.Scenario("中途岛·史实编成(1942-06-04)", "carrier", [jp, us],
                      seed=42, night=False, weather=0.0)


def tarawa() -> M.Scenario:
    """塔拉瓦 1943 末 · 联合推演（fork 1943-11 基线）· 见下注释。

    数据来源：GitHub baishanicedragon/ww2-naval-battle-compute
            - src/joint_tarawa_wargame.py（第一来源，fork 1943-11 基线兵力）
            - cases/tarawa_1943_fork/塔拉瓦1943末·fork推演.md（确认三因子设定）
    mission 单值取 land_based_aviation（源文件含水面与航空兵两套，水面单位一并纳入）；
    若要以水面为主，可改 "surface"。
    """
    us_radar = M.Sensor(kind="radar", band="high", active_range_nm=30.0,
                       passive=True, reliability=0.70)
    jp_radar = M.Sensor(kind="radar", band="high", active_range_nm=30.0,
                       passive=True, reliability=0.70)   # fork：双方雷达都用上
    jp_optical = M.Sensor(kind="optical", band="medium", active_range_nm=22.0,
                         passive=True, reliability=0.55)

    # —— 美军（fork：TF50 可用联队 ×0.8） ——
    us_units = []
    _us_cv = [("美舰队航母%d" % i, 28, 16, 26) for i in range(1, 5)] + \
             [("美轻航母%d" % i, 22, 12, 20) for i in range(1, 5)]
    for nm, ftr, torp, db in _us_cv:
        us_units.append(M.Unit(
            nm, "US", "CV", hp=130, speed_kt=32, sensors=[us_radar],
            weapons=[_av("舰载战斗机", "aircraft", 0.90),
                     _av("舰载鱼雷机", "aerial_torpedo", 0.65),
                     _av("舰载俯冲轰炸机", "aerial_bomb", 0.70)],
            ammo={"舰载战斗机": ftr, "舰载鱼雷机": torp, "舰载俯冲轰炸机": db}))

    for i in range(1, 6):
        us_units.append(M.Unit(
            f"美新锐战列舰{i}", "US", "BB", hp=100, speed_kt=27, sensors=[us_radar],
            weapons=[_w("16in_AP", "gun", 16, 30000, 2, 0.95)],
            ammo={"16in_AP": 100}))

    for i in range(1, 10):
        us_units.append(M.Unit(
            f"美重巡{i}", "US", "CA", hp=70, speed_kt=32, sensors=[us_radar],
            weapons=[_w("8in_AP", "gun", 8, 24000, 3, 0.90)],
            ammo={"8in_AP": 100}))

    for i in range(1, 9):
        us_units.append(M.Unit(
            f"美轻巡{i}", "US", "CL", hp=50, speed_kt=32, sensors=[us_radar],
            weapons=[_w("6in_AP", "gun", 6, 20000, 5, 0.90)],
            ammo={"6in_AP": 150}))

    for i in range(1, 29):
        us_units.append(M.Unit(
            f"美驱{i}", "US", "DD", hp=30, speed_kt=36, sensors=[us_radar],
            weapons=[_w("5in_AP", "gun", 5, 10000, 4, 0.90),
                     _w("Mk15", "torpedo", 0, 18000, 0, 0.07, pk=0.30)],
            ammo={"5in_AP": 80, "Mk15": 8}))

    # —— 日军（fork：油旁训练+产能无忧+金星零战交付，航空兵 ×1.3） ——
    jp_units = []
    _jp_cv = [
        ("翔鹤 Shokaku", 30, 21, 21), ("瑞鹤 Zuikaku", 30, 21, 21),
        ("隼鹰 Junyo", 24, 16, 15), ("飞鹰 Hiyo", 24, 16, 15),
        ("龙凤 Ryuho", 18, 11, 11), ("大凤 Taiho", 24, 18, 18),
        ("伊势 Ise", 15, 10, 10), ("日向 Hyuga", 15, 10, 10),
    ]
    for nm, ftr, torp, db in _jp_cv:
        jp_units.append(M.Unit(
            nm, "JP", "CV", hp=130, speed_kt=32, sensors=[jp_radar],
            weapons=[_av("舰载战斗机", "aircraft", 0.85),
                     _av("舰载鱼雷机", "aerial_torpedo", 0.78),
                     _av("舰载俯冲轰炸机", "aerial_bomb", 0.78)],
            ammo={"舰载战斗机": ftr, "舰载鱼雷机": torp, "舰载俯冲轰炸机": db}))
    jp_units.append(M.Unit(
        "瑞凤 Zuiho", "JP", "CV", hp=130, speed_kt=31, sensors=[jp_radar],
        weapons=[_av("舰载战斗机", "aircraft", 0.85)],
        ammo={"舰载战斗机": 36}))

    for nm in ["大和 Yamato", "武藏 Musashi"]:
        jp_units.append(M.Unit(
            nm, "JP", "BB", hp=100, speed_kt=27, sensors=[jp_radar],
            weapons=[_w("46cm_AP", "gun", 46, 30000, 2, 0.95)],
            ammo={"46cm_AP": 100}))

    for nm in ["金刚 Kongo", "比叡 Hiei", "榛名 Haruna", "雾岛 Kirishima"]:
        jp_units.append(M.Unit(
            nm, "JP", "BB", hp=100, speed_kt=30, sensors=[jp_radar],
            weapons=[_w("35.6cm_AP", "gun", 35.6, 30000, 2, 0.92)],
            ammo={"35.6cm_AP": 80}))

    for i in range(1, 11):
        jp_units.append(M.Unit(
            f"日重巡{i}", "JP", "CA", hp=70, speed_kt=35, sensors=[jp_radar],
            weapons=[_w("20.3cm_AP", "gun", 8, 24000, 3, 0.90)],
            ammo={"20.3cm_AP": 100}))

    for i in range(1, 9):
        jp_units.append(M.Unit(
            f"日轻巡{i}", "JP", "CL", hp=50, speed_kt=35, sensors=[jp_radar],
            weapons=[_w("14cm_AP", "gun", 14, 15000, 2.5, 0.90),
                     _w("93式", "torpedo", 0, 18000, 0, 0.80, pk=0.30)],
            ammo={"14cm_AP": 150, "93式": 24}))

    for i in range(1, 37):
        jp_units.append(M.Unit(
            f"日驱{i}", "JP", "DD", hp=30, speed_kt=34, sensors=[jp_radar],
            weapons=[_w("12.7cm", "gun", 5, 10000, 4, 0.90),
                     _w("93式", "torpedo", 0, 18000, 0, 0.80, pk=0.30)],
            ammo={"12.7cm": 80, "93式": 8}))

    jp_units.append(M.Unit(
        "日陆攻队", "JP", "CV", hp=130, speed_kt=0, sensors=[jp_radar],
        weapons=[_av("陆攻战斗机", "aircraft", 0.82),
                 _av("陆攻鱼雷机", "aerial_torpedo", 0.75),
                 _av("陆攻轰炸机", "aerial_bomb", 0.75)],
        ammo={"陆攻战斗机": 30, "陆攻鱼雷机": 45, "陆攻轰炸机": 45}))
    jp_units.append(M.Unit(
        "塔拉瓦驻扎零战", "JP", "CV", hp=130, speed_kt=0, sensors=[jp_radar],
        weapons=[_av("驻扎战斗机", "aircraft", 0.82)],
        ammo={"驻扎战斗机": 45}))

    # —— 战役层增援（对称，到 tick=40 入场）——
    jp_reinf = [M.Unit(f"増援CA{i}", "JP", "CA", hp=70, speed_kt=35,
                       sensors=[jp_radar],
                       weapons=[_w("20.3cm_AP", "gun", 8, 24000, 3, 0.90)],
                       ammo={"20.3cm_AP": 100}) for i in range(1, 3)]
    us_reinf = [M.Unit(f"増援CA{i}", "US", "CA", hp=70, speed_kt=32,
                       sensors=[us_radar],
                       weapons=[_w("8in_AP", "gun", 8, 24000, 3, 0.90)],
                       ammo={"8in_AP": 100}) for i in range(1, 3)]

    _spread(jp_units, 0.0)
    _spread(us_units, 8000.0)

    # —— 机场（AF）：贝蒂奥(日)/马金(美)，受岸轰/空袭降完好度。
    # 放在 _spread 之后，保留手动坐标（否则 _spread 会把机场拉进舰队列）——
    betio = _af("贝蒂奥机场", "JP", jp_radar, 40, 24, 50)
    betio.pos = (0.0, 5000.0)
    makin = _af("马金机场", "US", us_radar, 30, 18, 40)
    makin.pos = (8000.0, 5000.0)
    jp_units.append(betio)
    us_units.append(makin)

    jp = M.Side("JP", jp_units, doctrine="cv_first",
                reinforcements=[M.Reinforcement(arrive_tick=40, label="jp_reinforce",
                                                units=jp_reinf)])
    us = M.Side("US", us_units, doctrine="surface",
                reinforcements=[M.Reinforcement(arrive_tick=40, label="us_reinforce",
                                                units=us_reinf)])
    return M.Scenario("塔拉瓦1943末·联合推演(fork)", "land_based_aviation",
                      [jp, us], seed=42, night=True, weather=0.1,
                      objective="hold_airfield")


REGISTRY = {
    "瓜岛": guadalcanal,
    "中途岛": midway,
    "塔拉瓦": tarawa,
}
