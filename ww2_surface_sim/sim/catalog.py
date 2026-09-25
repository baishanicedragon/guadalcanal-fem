# -*- coding: utf-8 -*-
"""
catalog.py · 舰种目录（自定义舰队用，时代化）
================================================
JP/US 双方各配 BB/CV/CA/CL/DD/AF 六类模板，参数取自 scenarios.py 各场景 OOB
的同类舰统计口径。build() 每次返回全新 M.Unit（引擎会原地改 hp/ammo，
绝不能共享实例）。

三个时代档（用户要求"选取不同时代参战战舰"，对标鱼叉的学习价值）：
  1942(史实)          —— Mk15 磁引信灾难(0.07)、零战二一、F4F、JP 纯光学
  1943(fork·理想日本) —— 瓜岛胜利后的日本：金星零战交付、练度未损、
                         雷达上舰（fork 口径）；美方 Mk15 mod3 修复(0.45)、F6F 上舰
  1944(史实后期)      —— 日方精英飞行员损耗(航空质量下滑)、日方雷达量产；
                         美方雷达/防空进一步优化
传感器口径：JP 光学 22nm/0.55（著名 IJN 光学）；雷达档 30nm（可靠性随时代）；
US 雷达 30nm/0.70 → 1944 0.75。
"""
from . import model as M

ERAS = ["1942(史实)", "1943(fork·理想日本)", "1944(史实后期)"]


def _w(name, kind, caliber, rng_m, rpm, rel, disp=0.10, pk=0.10):
    return M.Weapon(name=name, kind=kind, caliber=caliber, range_m=rng_m,
                    rate_per_min=rpm, reliability=rel, disp_factor=disp, p_k=pk)


def _av(name, kind, rel=0.80):
    return M.Weapon(name=name, kind=kind, caliber=0.0, range_m=0.0,
                    rate_per_min=0.0, reliability=rel, disp_factor=0.10, p_k=0.10)


def _sensor(kind, rng_nm, rel):
    return M.Sensor(kind=kind, band="high" if kind == "radar" else "medium",
                    active_range_nm=rng_nm, passive=True, reliability=rel)


def _jp_sensor(era):
    """JP 传感器：1942/1943fork 纯光学（fork 只给航母编队雷达，此处口径取光学）；
    1944 雷达量产（可靠性 0.45，仍逊美方）。"""
    if era.startswith("1944"):
        return _sensor("radar", 30.0, 0.45)
    return _sensor("optical", 22.0, 0.55)


def _us_sensor(era):
    rel = 0.75 if era.startswith("1944") else 0.70
    return _sensor("radar", 30.0, rel)


def _jp_cv_wing(era):
    """JP 舰载机联队质量：1942 零战二一 / 1943fork 金星零战交付+练度足 /
    1944 精英损耗（史实马里亚纳火鸡猎杀口径）。"""
    if era.startswith("1942"):
        return 0.85, 0.75, 0.75
    if era.startswith("1943"):
        return 0.92, 0.78, 0.78          # 金星零战 + 老练飞行员
    return 0.72, 0.62, 0.62              # 1944 精英已逝


def _us_cv_wing(era):
    if era.startswith("1942"):
        return 0.90, 0.65, 0.70          # F4F/SBD/TBD
    return 0.95, 0.70, 0.75              # F6F 地狱猫上舰


def _us_dd_torp(era):
    """Mk15：1942 磁引信灾难 rel=0.07（瓜岛口径）；1943+ mod3 修复 rel=0.45。"""
    return 0.07 if era.startswith("1942") else 0.45


def build(side: str, cls: str, name: str, era: str = ERAS[0]) -> M.Unit:
    """按阵营+舰种+时代模板构造全新单位。AF 为机场（固定/hp=完好度）。"""
    if cls == "AF":
        if side == "JP":
            return M.Unit(name, side, "AF", hp=100, speed_kt=0, sensors=[_jp_sensor(era)],
                          weapons=[_av("岸基战斗机", "aircraft", 0.82),
                                   _av("岸基鱼雷机", "aerial_torpedo", 0.70),
                                   _av("岸基轰炸机", "aerial_bomb", 0.70)],
                          ammo={"岸基战斗机": 40, "岸基鱼雷机": 24, "岸基轰炸机": 50})
        return M.Unit(name, side, "AF", hp=100, speed_kt=0, sensors=[_us_sensor(era)],
                      weapons=[_av("岸基战斗机", "aircraft", 0.80),
                               _av("岸基鱼雷机", "aerial_torpedo", 0.60),
                               _av("岸基轰炸机", "aerial_bomb", 0.65)],
                      ammo={"岸基战斗机": 30, "岸基鱼雷机": 18, "岸基轰炸机": 40})

    if side == "JP":
        if cls == "BB":
            weapons = [_w("46cm_AP", "gun", 46, 30000, 2, 0.95),
                       _w("93式", "torpedo", 0, 18000, 0, 0.80, pk=0.30)]
            ammo = {"46cm_AP": 100, "93式": 12}
            return M.Unit(name, side, cls, hp=100, speed_kt=27,
                          sensors=[_jp_sensor(era)], weapons=weapons, ammo=ammo)
        if cls == "CV":
            f, t, b = _jp_cv_wing(era)
            return M.Unit(name, side, cls, hp=130, speed_kt=34,
                          sensors=[_jp_sensor(era)],
                          weapons=[_av("舰载战斗机", "aircraft", f),
                                   _av("舰载鱼雷机", "aerial_torpedo", t),
                                   _av("舰载俯冲轰炸机", "aerial_bomb", b)],
                          ammo={"舰载战斗机": 21, "舰载鱼雷机": 18, "舰载俯冲轰炸机": 21})
        if cls == "CA":
            return M.Unit(name, side, cls, hp=70, speed_kt=35,
                          sensors=[_jp_sensor(era)],
                          weapons=[_w("20.3cm_AP", "gun", 8, 24000, 3, 0.90)],
                          ammo={"20.3cm_AP": 100})
        if cls == "CL":
            return M.Unit(name, side, cls, hp=50, speed_kt=35,
                          sensors=[_jp_sensor(era)],
                          weapons=[_w("14cm_AP", "gun", 14, 15000, 2.5, 0.90),
                                   _w("93式", "torpedo", 0, 18000, 0, 0.80, pk=0.30)],
                          ammo={"14cm_AP": 150, "93式": 24})
        if cls == "DD":
            return M.Unit(name, side, cls, hp=30, speed_kt=34,
                          sensors=[_jp_sensor(era)],
                          weapons=[_w("12.7cm", "gun", 5, 10000, 4, 0.90),
                                   _w("93式", "torpedo", 0, 18000, 0, 0.80, pk=0.30)],
                          ammo={"12.7cm": 80, "93式": 8})
    else:
        if cls == "BB":
            return M.Unit(name, side, cls, hp=100, speed_kt=27,
                          sensors=[_us_sensor(era)],
                          weapons=[_w("16in_AP", "gun", 16, 30000, 2, 0.95)],
                          ammo={"16in_AP": 100})
        if cls == "CV":
            f, t, b = _us_cv_wing(era)
            return M.Unit(name, side, cls, hp=130, speed_kt=32,
                          sensors=[_us_sensor(era)],
                          weapons=[_av("舰载战斗机", "aircraft", f),
                                   _av("舰载鱼雷机", "aerial_torpedo", t),
                                   _av("舰载俯冲轰炸机", "aerial_bomb", b)],
                          ammo={"舰载战斗机": 27, "舰载鱼雷机": 14, "舰载俯冲轰炸机": 37})
        if cls == "CA":
            return M.Unit(name, side, cls, hp=70, speed_kt=32,
                          sensors=[_us_sensor(era)],
                          weapons=[_w("8in_AP", "gun", 8, 24000, 3, 0.90)],
                          ammo={"8in_AP": 100})
        if cls == "CL":
            return M.Unit(name, side, cls, hp=50, speed_kt=32,
                          sensors=[_us_sensor(era)],
                          weapons=[_w("6in_AP", "gun", 6, 20000, 5, 0.90)],
                          ammo={"6in_AP": 150})
        if cls == "DD":
            rel = _us_dd_torp(era)
            return M.Unit(name, side, cls, hp=30, speed_kt=36,
                          sensors=[_us_sensor(era)],
                          weapons=[_w("5in_AP", "gun", 5, 10000, 4, 0.90),
                                   _w("Mk15", "torpedo", 0, 18000, 0, rel, pk=0.30)],
                          ammo={"5in_AP": 80, "Mk15": 8})
    raise ValueError(f"未知舰种: {side}/{cls}")


CLASSES = ["BB", "CV", "CA", "CL", "DD", "AF"]
