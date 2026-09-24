# -*- coding: utf-8 -*-
"""
瓜岛推演·蒙特卡洛 + 有限元（单舰/单炮/单弹）模拟器  v2
================================================================
设计原则（用户 2026-09-18 指出）:
  ❌ 聚合式模型（总发射数 × 命中率 → 战力百分比）会制造
     "先手方虐杀到底"的伪正反馈：先手打崩对方火力系数 → 对方打得更少
     → 差距指数放大。这是数学伪影，不是战争现实。
  ✅ 修正为有限元式：每次炮击落一条记录；距离是状态量；毁伤是单舰
     部位的局部事件；某舰火控失效只影响它自己，不传染全队。

数据结构:
  ShipState  : 单舰的 部位级 状态（舵机/火控/炮塔/进水/火灾/结构）
  ShotRecord : 一次发射的完整记录（时间/射手/目标/距离/弹种/命中/部位/毁伤）
  所有 ShotRecord 累积入 shots 表，可导出 CSV 供外部核验（这就是"落数据表"）

与史实标定（2026-09-18 核定）:
  泗水海战 1942-02-27: 1,619发8in / 15,000-26,000码 -> 5发命中 = 0.31%
  1942-03-02 Atago/Takao 星弹夜战 / 6,000码 -> 166发沉1驱 ≈ 1-2%
  1942-11-14 华盛顿伏击雾岛 / 7,000米 -> 55-75发命中9-20 = 20-27%（伏击例外）
  本案（用户设定）: 三川预警, 交战距离 15,000-18,000米(16.4-19.7kyd)

用法:
  python mc_fem.py --n 2000 --scenario gambler
  python mc_fem.py --n 2000 --scenario gambler --shots-csv out/shots.csv
"""
import argparse
import copy
import csv
import json
import math
from collections import defaultdict
import random
import statistics as st
from dataclasses import dataclass, field, asdict
from typing import Optional

# ============================================================
# 0. 常数与经验分布
# ============================================================
DECISIVE_SAMPLES = [1]*9 + [2]*5 + [3]*2 + [5]*3 + [7, 10, 13, 35]

# 弹种穿透概率
PEN = {
    "AP":   {"BB": 0.55, "CA": 0.90, "CL": 0.85, "DD": 0.85},
    "HE":   {"BB": 0.10, "CA": 0.75, "CL": 0.80, "DD": 0.95},
    "SANS": {"BB": 0.03, "CA": 0.20, "CL": 0.25, "DD": 0.35},
}
# 弹种致命度
LETH = {"AP": 1.00, "HE": 0.70, "SANS": 0.35}

# ============================================================
# 0b. 主炮口径权重（用户 2026-09-18 自检发现的结构性错误）
# ============================================================
# 上一版：任何穿甲弹命中都造成 uniform(1.0, 4.0) 的结构损伤，
# 【不分口径】。后果是"驱逐舰的 5 寸炮打驱逐舰"与"战列舰的 16 寸炮
# 打驱逐舰"毁伤完全一样 → 日方 6 艘驱逐舰在 6-7 km 上把美方 5 艘
# 驱逐舰打成 84% 沉没率，而美驱还击只有 15%。
#
# 正确的做法：单发毁伤量级必须随【主炮口径】缩放。二战 5 寸弹丸
# 约 2-3 kg 装药、14-16 寸弹丸约 15-25 kg 装药，能量差一个数量级；
# 对驱逐舰这种无装甲薄壳目标，5 寸弹是"打穿但不解体"，14 寸弹是
# "命中即失能"。
#
# ⇒ 引入 CALIBER_FACTOR：以 8 寸（重巡）为 1.0 基准
#     BB 14-16 寸 ≈ 2.2 ｜ BB 大和 18 寸 ≈ 2.8
#     CA 8 寸     ≈ 1.0 ｜ CL 6 寸     ≈ 0.55 ｜ DD 5 寸 ≈ 0.40
CALIBER_FACTOR = {
    ("BB", 18): 2.8, ("BB", 16): 2.2, ("BB", 14): 2.0, ("BB", 12): 1.6,
    ("CA", 10): 1.25, ("CA", 8): 1.0,
    ("CL", 6): 0.55, ("CL", 5.5): 0.50,
    ("DD", 5): 0.40, ("DD", 4.7): 0.36,
    ("CV", 5): 0.40,
}


def caliber_factor(cls: str, guns: int) -> float:
    """按舰型 + 主炮门数估口径权重（门数少 → 通常口径更大）"""
    if cls == "BB":
        # 大和 9 门 = 18 寸；伊势/扶桑 6 门 = 14 寸；日向 5 门（已废一塔）
        if guns >= 9:
            return 2.8
        if guns >= 8:
            return 2.2
        if guns >= 6:
            return 2.0
        return 1.6
    if cls == "CA":
        return 1.25 if guns >= 10 else 1.0
    if cls == "CL":
        return 0.55
    if cls == "DD":
        return 0.40
    return 0.40


# 口径 × 目标舰型 → "能否击穿"的乘数（用户 2026-09-18 结构修正）
#   物理依据：5 寸炮在 15-18 km 上【不可能】击穿战列舰主装甲带/炮塔正面，
#   只能打上层建筑与无装甲区。旧模型只让口径影响"毁伤量"，却让 5 寸弹
#   保有 55% 击穿率 → 美方用大量 5 寸/6 寸弹刷"击穿→炮塔瘫痪→弹药库"。
#   表按口径降序；取第一个 caliber >= 阈值的档。
PEN_CALIBER_TBL = {
    "BB": [(2.8, 1.00), (2.2, 1.00), (2.0, 0.95), (1.6, 0.85),
           (1.25, 0.30), (1.0, 0.22), (0.55, 0.05), (0.40, 0.02)],
    "CA": [(2.8, 1.00), (2.2, 1.00), (2.0, 1.00), (1.6, 1.00),
           (1.25, 0.95), (1.0, 0.90), (0.55, 0.45), (0.40, 0.30)],
    "CL": [(2.8, 1.00), (2.2, 1.00), (2.0, 1.00), (1.6, 1.00),
           (1.25, 1.00), (1.0, 0.98), (0.55, 0.80), (0.40, 0.55)],
    "DD": [(2.8, 1.00), (2.2, 1.00), (2.0, 1.00), (1.6, 1.00),
           (1.25, 1.00), (1.0, 1.00), (0.55, 0.95), (0.40, 0.90)],
}


def pen_caliber_factor(caliber: float, target_cls: str) -> float:
    """口径对"能否击穿"的乘数"""
    tbl = PEN_CALIBER_TBL.get(target_cls, PEN_CALIBER_TBL["DD"])
    for c, f in tbl:
        if caliber >= c:
            return f
    return tbl[-1][1]


# ============================================================
# 0a. 舰型尺度：生命值 / 炮塔投影 / 鱼雷韧性（用户 2026-09-18 指定）
# ============================================================
# 结构生命值（"沉没"所需的总结构损伤；BB 是 DD 的十倍量级）
# ⚠ 用户 2026-09-18 修正："非战列舰的生命值低了，只有 40 不到"。
#   旧值 CA=42 / CL=32 相对 BB=100 偏低。史实依据：重巡在 1942 夜战中
#   挨 20-30 发 8 寸弹仍能浮航（旧金山被数十发命中未沉），轻巡也远超
#   "挨十几发就沉"的强度 ⇒ 上调 CA/CL/DD，维持 BB 为基准 100。
HULL_HP = {
    "BB": 100.0,     # 基准
    "CA": 58.0,      # 重巡（1 万吨级，装甲盒 + 双层底）
    "CL": 46.0,      # 轻巡（含亚特兰大级 7,400t 与海伦娜 1 万吨级）
    "DD": 15.0,      # 驱逐舰（2,000-2,500t，无装甲盒）
    "CV": 62.0,
}
# 基准航速（节）—— 用于追击可行性判定（追击方速度 >= 逃跑方才能咬住）
# 取 1942 年该舰型的典型设计/实战航速。
# ⚠ 注意：本表是【设计/巡航最高速】，用于追击判定；
#   战列舰的【炮击交战航速】另有上限（用户 2026-09-24 #15：
#   历史上 BB 编队炮击从未超过 18 节），在 single_shot_p 里封顶。
# 射击周期（秒/轮）—— 用户 2026-09-18 指定
#   战列舰 主炮 30 秒一轮（约 2 发/分/门）
#   驱逐舰 / 巡洋舰 主炮 10 秒一轮（约 6 发/分/门）；6 寸炮可到 8 秒
# ⇒ 时间步必须按【该舰自己的射击周期】来推进，不能用全队统一 30 秒，
#   否则驱逐舰的火力被强行降到战列舰的节奏（用户指出的"迭代步不对"）。
# 主炮最大有效射程（米）—— 用户 2026-09-18 指定
#   战列舰 ~30,000+ m ；巡洋舰 8in ~26,000 m / 6in ~20,000 m
#   驱逐舰 5in ~10,000 m（用户明确："通常驱逐舰射程不会超过10000米，
#   所以驱逐舰不会在双方一开始就对射，只会在鱼雷冲锋时交火并交换鱼雷"）
# ⇒ 交战在 15,000-18,000 m 时，日美双方的驱逐舰【根本打不到】，
#   它们只能等接近到 10,000 m 以内才开火 —— 而那是鱼雷冲锋阶段。
GUN_RANGE_M = {
    "BB": 30000.0,
    "CA": 24000.0,   # 8 寸
    "CL": 20000.0,   # 6 寸（海伦娜/亚特兰大/北上/大井的 5.5 寸更短）
    "DD": 10000.0,   # 5 寸 —— 硬上限
    "CV": 20000.0,
}
GUN_RANGE_CL55 = 15000.0   # 北上/大井 5.5 寸（140mm）实际射程更短

# 基准航速（节）—— 用户 2026-09-18: "追击是散乱追击……需要进行剩余航速比对，
# 速度慢的不能追上跑得快的。"
#   ⇒ 追击阶段必须逐舰比较 speed_kt；慢的追不上快的，只能咬住落单的慢舰。
SPEED_KT = {
    "BB": 27.0,      # 战列舰（大和/长门 27、扶桑 25、金刚型 30）
    "CA": 33.0,
    "CL": 33.0,
    "DD": 36.0,
    "CV": 30.0,
}

CYCLE_SEC = {
    "BB": 30.0,   # 战列舰主炮：约 30-40 秒/轮
    "CA": 20.0,   # 重巡 8 寸：20 秒/轮（用户指定）
    "CL": 10.0,   # 美方轻巡 5/6 寸：10 秒/轮（用户指定）
    "DD": 10.0,   # 驱逐舰 5 寸：10 秒/轮（用户指定）
    "CV": 30.0,
}
CYCLE_SEC_CL = 10.0  # 美方轻巡（海伦娜/朱诺/亚特兰大）
CYCLE_SEC_CL_JP = 20.0   # 日方轻巡（北上/大井 5.5 寸）：20 秒/轮
# 炮塔投影面积（占总投影的比例）——炮塔是独立的凸出目标
# 命中分布: 舰体 / 炮塔 / 上层建筑 / 水线附近
TURRET_SILHOUETTE = {
    "BB": 0.18,      # 战列舰炮塔群投影大（3-5座）
    "CA": 0.20,
    "CL": 0.16,
    "DD": 0.12,
}
# 鱼雷韧度：命中几发导致"严重受损/击沉"（用户指定）
# DD: 1发即沉; CA/CL: 1发重创; BB: 2发以上严重受损
TORPEDO_LETHALITY = {
    "DD": {"sink": 1.0, "severe": 1.0},    # 1 发即沉
    "CL": {"sink": 2.5, "severe": 1.0},    # 1 发重创 / 2.5 发沉
    "CA": {"sink": 2.5, "severe": 1.0},    # 同上
    # ⚠ 用户 2026-09-18 修正：「TDS 深度基本不够」→ 93 式 490kg 装药
    #   对 1942 年战列舰（TDS 纵深 3-5m）而言，1 发【几乎必然丧失战斗力】，
    #   2 发【必沉】。旧值 sink=3.0 是把 TDS 想得太有效了。
    "BB": {"sink": 2.0, "severe": 1.0},
    "CV": {"sink": 2.0, "severe": 1.0},
}

# ---- 鱼雷命中位置的 TDS 分类（用户 2026-09-18 指定）----
# 战列舰吃鱼雷，后果【取决于命中位置相对 TDS（防雷隔舱）的关系】：
#   ① 命中 TDS 主体区（舷侧中段，隔舱纵深最大）→ 损害通常有限：
#      进水被隔舱吸收，能继续战斗，但【航速必然下降】（进水增重、纵倾）
#   ② 命中 TDS 削弱区（前后端）→ 隔舱纵深小，大量进水，可能失去动力
#   ③ 93 式长矛（490 kg 装药，水下深处爆炸）→ 有概率贯穿 TDS，
#      直接损毁机舱/弹药舱（这才是真正的战沉原因）
TDS_HIT_ZONES = {
    # zone: (权重, 隔舱纵深系数, 是否可能贯穿核心)
    "TDS主体":  (0.55, 1.00, True),
    "TDS削弱区": (0.30, 0.45, True),
    "舰首舰尾":  (0.15, 0.25, False),
}

# ============================================================
# 0b. 弹药储备与弹种配比（用户 2026-09-18 指定）
# ============================================================
# 单门主炮备弹量（发）——按舰型
AMMO_PER_GUN = {
    "BB": (80, 120),    # 大和级约100-120/门; 扶桑级约80-100/门
    "CA": (90, 120),
    "CL": (120, 200),
    "DD": (60, 100),
}
# 单场交战实际可发射的主炮弹药预算（发/门）——按舰型
#   【用户 2026-09-23 校正（消息 #11）】：旧模型战列舰"遭遇即全速射击"，
#   会一路打光 AMMO_PER_GUN 满额储备（9 门 BB ≈ 720-1080 发）触发"弹药耗尽→误标脱离"。
#   史实夜战雾岛仅向南海打 117 发、华盛顿近+远约 175-275 发——单场交战根本打不光储备。
#   ⇒ 新增【单场弹药预算】与储备解耦：储备(ammo_main)保持不变，交战只受 ammo_battle 约束。
AMMO_BATTLE_PER_GUN = {
    "BB": (12, 24),    # 单场 ~144-216 发（锚定：雾岛117 / 华盛顿175-275）
    "CA": (15, 30),
    "CL": (20, 40),
    "DD": (12, 24),
}
# 弹种配比
# 用户 2026-09-18 两次指定，第二次为定稿口径：
#   ① "日本的战舰会携带30%高爆弹和三式弹用于炮击陆地，其他是穿甲弹。
#       美国穿甲弹比例约80%。"  —— 这是【携弹量】
#   ② "因为预期会打美军，所以日本人4艘战列舰和大和都是带AP。三式弹不会
#       用于海战，最后保留对地轰炸。"  —— 这是【用弹】定稿
# ⇒ 结论：日方5艘主力战列舰（日向/伊势/扶桑/山城/大和）本次全部携 AP 打舰；
#    三式弹（SANS）与高爆弹（HE）只留作对亨德森机场的岸轰，不进入舰对舰结算。
CARRY_JP = {"AP": 0.70, "HE": 0.30}     # 日方携弹（用户指定）
CARRY_US = {"AP": 0.80, "HE": 0.20}     # 美方携弹（用户指定）

# 舰对舰交战：日方 100% AP（用户定稿口径）
DOCTRINE_SURFACE_JP = {"AP": 1.00}
DOCTRINE_SURFACE_US = {"AP": 0.90, "HE": 0.10}

# 岸轰阶段（对亨德森机场）：三式弹 + 高爆弹
DOCTRINE_BOMBARD_JP = {"AP": 0.05, "HE": 0.50, "SANS": 0.45}

# 致命区域（用户指定: 炮塔/船体/指挥/舵机 均为致命区, 有概率爆沉）
FATAL_AREAS = ["炮塔", "船体", "指挥所", "舵机", "弹药库", "机舱"]


def roll_shell(mix: dict, rng: random.Random, jp: bool) -> str:
    """按配比抽取这一发的弹种"""
    table = mix if mix else (DOCTRINE_SURFACE_JP if jp else DOCTRINE_SURFACE_US)
    r = rng.random()
    acc = 0.0
    for k, v in table.items():
        acc += v
        if r < acc:
            return k
    return list(table)[-1]


# ============================================================
# 1. 有限元：单舰部位级状态
# ============================================================
@dataclass
class ShipState:
    name: str
    cls: str
    guns: int
    rof: float
    shell: str
    armor: float
    torpedo_tubes: int = 0
    torpedo_reload: bool = False
    radar: bool = False
    order: int = 0            # 在己方纵队中的位置（0=前导）—— 用于 1对1 单挑配对
    speed_base: float = 0.0   # 基准航速（节）—— 追击可行性判定用

    # ---- 部位级损伤 ----
    struct_dmg: float = 0.0   # 结构损伤绝对值（单位与 HULL_HP 同）
    flood: float = 0.0        # 进水 0-1
    speed_frac: float = 1.0   # 可用航速比例（鱼雷命中/进水必然下降）
    fire: float = 0.0         # 火灾 0-1
    steering: float = 0.0     # 舵机失效 0-1
    firecontrol: float = 0.0  # 火控失效 0-1
    turrets_dead: int = 0
    turrets_total: int = 0
    torpedo_hits_taken: int = 0   # 已中鱼雷数（用户指定的鱼雷韧性）

    dead: bool = False
    scuttled: bool = False
    withdrawn: bool = False   # 已脱离战线去后方抢修（用户 2026-09-18）
    withdrawn_at: float = -1.0   # 脱离时刻（绝对分钟）—— "最后脱离者"优先被追上

    # ---- 弹药储备（用户 2026-09-18 指定）----
    ammo_main: int = 0
    ammo_battle: int = 0      # 单场交战弹药预算（与储备 ammo_main 解耦，2026-09-23）

    # ---- 副炮（用户 2026-09-18 指出：主炮打干后仍可用副炮岸轰）----
    # 扶桑级/伊势级：16 门 140mm/50（独立弹药库）；大和：12 门 155mm 三年式。
    sec_guns: int = 0          # 副炮门数（0 = 未建模副炮）
    ammo_sec: int = 0          # 副炮备弹总数（岸轰用，独立于主炮弹药池）
    sec_kg: float = 38.0       # 副炮弹重 kg（140mm=38 / 155mm=55.5 / 12.7cm=23）

    def __post_init__(self):
        if self.turrets_total == 0:
            self.turrets_total = max(1, self.guns // 2)
        if self.ammo_main == 0:
            lo, hi = AMMO_PER_GUN.get(self.cls, (80, 120))
            self.ammo_main = int(self.guns * (lo + hi) / 2)
        if self.ammo_battle == 0:
            lo, hi = AMMO_BATTLE_PER_GUN.get(self.cls, (15, 30))
            self.ammo_battle = int(self.guns * (lo + hi) / 2)
        if self.speed_base <= 0:
            self.speed_base = SPEED_KT.get(self.cls, 28.0)

    @property
    def speed_kt(self) -> float:
        """当前可用航速（节）—— 基准 × 可用比例（用户 2026-09-18）"""
        return self.speed_base * self.speed_frac

    @property
    def hull_hp(self) -> float:
        return HULL_HP.get(self.cls, 40.0)

    @property
    def gun_range_m(self) -> float:
        """本舰主炮最大有效射程（米）"""
        if self.cls == "CL" and self.guns <= 6:
            return GUN_RANGE_CL55      # 北上/大井的 5.5 寸
        return GUN_RANGE_M.get(self.cls, 20000.0)

    @property
    def cycle_sec(self) -> float:
        """本舰主炮的射击周期（秒/轮，用户 2026-09-18 指定）

        · 战列舰 ≈ 30-40 s
        · 美重巡 / 日轻巡 / 日重巡 ≈ 20 s
        · 驱逐舰 / 美轻巡 ≈ 10 s
        日方雷巡（北上/大井，5.5 寸、仅 4 门）按 20 s。
        """
        if self.cls == "CL":
            if self.guns <= 6:          # 日方雷巡 5.5 寸
                return CYCLE_SEC_CL_JP
            return CYCLE_SEC_CL         # 美方轻巡
        return CYCLE_SEC.get(self.cls, 30.0)

    @property
    def struct(self) -> float:
        """结构损失比例 0-1（对外保持原接口）"""
        return min(1.0, self.struct_dmg / self.hull_hp)

    # ---- 派生量 ----
    def gun_availability(self) -> float:
        """主炮可用比例（受炮塔损失、结构、火灾影响）

        注：进水的惩罚【不放在这里】，而放在 accuracy_factor。
        理由（史实校验）：南达科他 1942-11-14 挨了 26 发仍能射击，
        舰体倾斜影响的是【打得准不准】，不是【炮还能不能响】。
        """
        if self.dead:
            return 0.0
        if self.ammo_main <= 0:
            return 0.0          # 弹药打空 → 停火
        t = 1.0 - self.turrets_dead / max(1, self.turrets_total)
        s = max(0.0, 1.0 - self.struct * 0.95)
        f = max(0.0, 1.0 - self.fire * 0.35)
        return max(0.0, t * s * f)

    def accuracy_factor(self) -> float:
        """本舰火控对命中率的影响（火灾控=0 则该舰几乎打不中）"""
        if self.dead or self.firecontrol >= 0.95:
            return 0.0
        base = max(0.0, 1.0 - self.firecontrol) * max(0.0, 1.0 - self.fire * 0.4)
        # 用户 2026-09-18: 进水导致横倾 → 舰体倾斜 → 射击不稳定 → 精度骤降
        # 进水 0.5 时精度约剩 45%，进水 0.8 时约剩 22%
        return base * max(0.05, 1.0 - self.flood * 1.1)

    def damage_control(self, dt_min: float):
        """损管：抽水 / 堵漏 / 灭火（用户 2026-09-18 隐含要求）

        没有这一步，进水会在 30 分钟里单调累积到 1.0，
        把任何一艘战列舰的主炮可用度压到 5-10% —— 与史实不符。
        模型：
          · 进水向"永久底数"回落（船体破口以下的进水抽不干净）
          · 火灾可以扑灭（但有残余）
        """
        if self.dead:
            return
        # 抽水/堵漏：向永久底数回落（破口越大底数越高）
        floor = min(0.45, self.struct * 0.45)
        if self.flood > floor:
            self.flood = max(floor, self.flood - 0.11 * dt_min)
        # 灭火
        if self.fire > 0:
            self.fire = max(0.0, self.fire - 0.14 * dt_min)
        # 航速部分恢复（抽水后吃水变浅）
        if self.speed_frac < 1.0 and self.struct < 0.6:
            self.speed_frac = min(1.0, self.speed_frac + 0.03 * dt_min)

    def mobility(self) -> float:
        """机动能力（舵机损坏/降速→难以规避，成为固定靶）"""
        if self.dead:
            return 0.0
        return (max(0.0, 1.0 - self.steering)
                * max(0.0, 1.0 - self.flood * 0.9)
                * max(0.2, self.speed_frac))

    def combat_capable(self) -> bool:
        return ((not self.dead) and (not self.withdrawn)
                and self.gun_availability() > 0.05)

    def should_withdraw(self) -> bool:
        """重伤退队判定（用户 2026-09-18）

        "受损严重的船，比如起火，失去动力，会退出队列，退到后方修理。"
        ⇒ 触发条件（任一）：
          · 严重进水（>0.55）—— 抽水跟不上，舰体在持续下沉
          · 起火（>0.60）—— 火灾失控
          · 舵机几乎全失（>0.80）—— 无法保持队形
          · 结构严重受损（>0.65）
          · 丧失动力（可用航速 ≤0.25）
        """
        if self.dead or self.withdrawn:
            return False
        if self.flood >= 0.55:
            return True
        if self.fire >= 0.60:
            return True
        if self.steering >= 0.80:
            return True
        if self.struct >= 0.65:
            return True
        if self.speed_frac <= 0.25:
            return True
        return False


# ============================================================
# 2. 单发记录（"落数据表"）
# ============================================================
@dataclass
class ShotRecord:
    t_min: float
    shooter: str
    shooter_cls: str
    target: str
    target_cls: str
    distance_kyd: float
    shell: str
    hit: bool
    penetrated: bool
    location: str          # 命中部位
    dmg: float
    target_dead_after: bool
    sank_now: bool
    phase: str
    is_bombard: bool = False   # 岸轰记账行（非炮术事件，不计入命中统计）


# ============================================================
# 3. 命中率（距离分档，泗水标定）
# ============================================================
def clock_to_abs(hhmm: float) -> float:
    """HHMM（如 2305 / 15）→ 自 10/24 23:00 起的绝对分钟数。
    这样 23:05 → 5，00:15（次日）→ 75，排序天然正确。"""
    h = int(hhmm // 100)
    m = hhmm - h * 100
    mm = h * 60 + m
    if mm < 23 * 60:
        mm += 24 * 60
    return mm - 23 * 60


def abs_to_clock(dm: float) -> str:
    """绝对分钟 → 时钟字符串（HH:MM:SS）

    用户 2026-09-18：进入炮击后按 20 秒迭代，故必须显示到【秒】，
    否则 23:05:00 / 23:05:20 / 23:05:40 会在"分钟"刻度上重复。
    """
    total_s = int(round(dm * 60)) + 23 * 3600
    total_s %= 24 * 3600
    return f"{total_s // 3600:02d}:{(total_s % 3600) // 60:02d}:{total_s % 60:02d}"


# ============================================================
# 0c. 航速对炮击命中率的修正（用户 2026-09-24 #12 / #14）
#   夜战双方 20+ 节但【匀速前进】保光学测距 ⇒ 速度是"平台扰动"而非"剧烈规避"。
#   史实：美方有陀螺稳定 + 雷达火控 → 航速扰动温和；日方无陀螺、靠光学测距
#   → 对航速敏感（AskHistorians：日方未用陀螺稳定炮架，美方可在剧烈机动下维持解）。
#   目标【匀速】→ 易预测，仅轻微 lead 误差。
#   ⇒ 基准曲线改为【零/低速基线】，航速惩罚由 _speed_gun_factor 单独施加
#     （原曲线把"含航速的观测命中率"直接当基准，属双重计入，已在本次重标定修正）。
GUN_SPEED_OWN_STABLE = 0.006      # 美方：每节 0.6% 下降（陀螺稳定）
GUN_SPEED_OWN_UNSTABLE = 0.012    # 日方：每节 1.2% 下降（光学无陀螺）
GUN_SPEED_OWN_UNSTABLE2 = 0.0002  # 日方二次项
GUN_SPEED_TGT = 0.004             # 目标匀速：每节 0.4% 下降
GUN_SPEED_OWN_FLOOR = 0.55
GUN_SPEED_TGT_FLOOR = 0.80


def _speed_gun_factor(own_spd: float, tgt_spd: float, stable: bool) -> float:
    """航速→命中率乘子。own_spd/tgt_spd 单位节；stable=本方是否有陀螺稳定火控(借 radar 代理)。"""
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


def base_hit_rate(d_kyd: float) -> float:
    """距离-命中率基准曲线（【低速/稳态】基线，未含航速惩罚）。

    用户 2026-09-24 #12/#14 重标定：原曲线是"含航速的实测命中率"被直接当基准；
    现抬升约 2.6× 作为零/低速基线，使 22 节匀速时经 _speed_gun_factor 折减后
    落到 §5.2 锚点（光学 1.7% / 雷达近距 12%）。"""
    if d_kyd <= 6:
        return 0.0390
    if d_kyd <= 10:
        return 0.0390 - (d_kyd - 6) / 4 * (0.0390 - 0.0208)   # 3.90% -> 2.08%
    if d_kyd <= 16:
        return 0.0208 - (d_kyd - 10) / 6 * (0.0208 - 0.0091)  # 2.08% -> 0.91%
    if d_kyd <= 20:
        return 0.0091 - (d_kyd - 16) / 4 * (0.0091 - 0.0039)  # 0.91% -> 0.39%
    return max(0.0005, 0.0039 * math.exp(-(d_kyd - 20) / 10))


SIZE = {"BB": 1.00, "CA": 0.80, "CL": 0.70, "DD": 0.55, "CV": 1.15}


def single_shot_p(shooter, target, d_kyd: float,
                  mods: dict, rng: random.Random, ambush: bool = False,
                  shell: str = "AP") -> float:
    """
    单发命中率。
    用户 2026-09-18 修正要点:
      ① 修正因子【不能连乘到底】—— 历史上大量军械研究早已指出，
         "乘法叠加诸元误差"会指数化放大：五个 0.8 的因子乘起来是 0.33，
         但实战中人不是每项都同时最差。改用【加权几何平均 + 下限】。
      ② 奇袭（ambush）是【一次性窗口】，不是持续 10 分钟的常态。
         ×6 只应在换目标后的最初 1-2 分钟生效，之后回落。
      ③ 交战距离 15-18 km 时基准已很低，双方都该落在同一量级。
    """
    p = base_hit_rate(d_kyd) * SIZE.get(target.cls, 0.7)
    # 本舰火控
    p *= shooter.accuracy_factor()
    # 火控雷达（远距测距优势）
    if shooter.radar and not ambush:
        p *= 1.45
    # 奇袭窗口（幅度降到 ×3.0，且由 run_once 控制只作用于最初窗口）
    if ambush:
        p *= 3.0
    # 目标无法机动 → 固定靶
    p *= (0.60 + 0.40 * target.mobility())
    # ---- 航速→炮击命中率（用户 2026-09-24 #12/#14/#15）----
    # 双方夜战为【匀速】保光学测距 ⇒ 航速是"平台扰动"而非剧烈规避。
    # 战列舰炮击航速封顶 18 节（史实：BB 编队炮击从未超 18 节）；
    # BC/CA 可更高，但已受光学不稳定惩罚（stable=False 走 1.2%/kt 曲线）。
    # stable 借 radar 代理：美舰有陀螺稳定+雷达火控 → 温和惩罚；
    # 日舰光学无陀螺 → 敏感惩罚。
    own_gun_spd = min(shooter.speed_kt, 18.0) if shooter.cls == "BB" else shooter.speed_kt
    tgt_gun_spd = min(target.speed_kt, 18.0) if target.cls == "BB" else target.speed_kt
    p *= _speed_gun_factor(own_gun_spd, tgt_gun_spd, stable=bool(shooter.radar))
    # 战场修正 —— 加权几何平均，避免乘法崩塌
    # 权重：surprise .30 / crossing_T .15 / confusion .25 / smoke .15 / illum .15
    f_surp = mods.get("surprise", 1.0)
    f_cross = mods.get("crossing_T", 1.0)
    f_conf = mods.get("confusion", 1.0)
    f_smoke = mods.get("smoke_jam", 1.0)
    f_illum = mods.get("illumination", 1.0)
    geo = (f_surp ** 0.30) * (f_cross ** 0.15) * (f_conf ** 0.25) \
          * (f_smoke ** 0.15) * (f_illum ** 0.15)
    # 下限：任何战场混乱也不至于比基准再低 55%（人不会五坏同时最坏）
    p *= max(0.45, geo)
    # 撤离方效率（用户 2026-09-18: "放弃战斗一方只能被迫继续开火，
    # 但是效果会打折"）—— 边打边退，射击不稳定、观察受限
    p *= mods.get("disengaged", 1.0)
    # 弹种对命中率的微调（三式弹散布稍差）
    if shell == "SANS":
        p *= 0.9
    # 逐发随机波动
    p *= rng.uniform(0.5, 1.8)
    return max(0.0001, min(0.35, p))


# ============================================================
# 4. 单发毁伤（部位级，带"关键部位"概率）
# ============================================================
CRIT_LOCS = ["舵机", "弹药库", "火控室", "炮塔", "机舱", "指挥所"]


def apply_shot(target, shell: str, rng: random.Random,
               hit_body: bool = True, jp_shooter: bool = False,
               caliber: float = 1.0) -> tuple[bool, str, float]:
    """
    单发毁伤（部位级 + 致命区 + 舰型生命值 + 炮塔投影 + 主炮口径）。
    用户 2026-09-18 指定:
      - 三类舰生命值不同（HULL_HP）: BB=100 / CA=42 / CL=32 / DD=11
      - 炮塔投影单独考虑: 命中分布 舰体/炮塔/上层建筑/水线
      - 致命区: 炮塔 / 船体 / 指挥 / 舵机（+弹药库/机舱），有概率爆沉

    caliber: 主炮口径权重（见 caliber_factor）。单发毁伤随口径缩放 ——
      这是修正"驱逐舰 5 寸炮与战列舰 16 寸炮毁伤等量"这一结构性错误的
      关键参数（2026-09-18 自检发现）。

    标定（形式约束，可核验）:
      史实 1942 夜战大口径炮弹"平均约 30 发命中换 1 艘重巡"（巴尔/旧金山
      级 30 发以上才失能）。按每艘 CA 生命值 42、caliber=1.0 时平均单发
      毁伤约 1.2 计, 需 35 发上下 → 量级吻合。故 8 寸穿甲弹结构毁伤量级
      取 1-4, 未穿 0.3-1.2。深弹（弹药库爆沉）为独立小概率事件。
    """
    p_pen = (PEN[shell][target.cls]
             * pen_caliber_factor(caliber, target.cls)
             * (0.80 + 0.20 * (1 - target.armor)))
    pen = rng.random() < p_pen
    # 穿甲弹: 命中舰体的结构毁伤（不含部位加成）—— 随口径缩放
    if pen:
        dmg = rng.uniform(1.0, 4.0) * LETH[shell] * caliber
    else:
        dmg = rng.uniform(0.3, 1.2) * max(0.5, caliber * 0.7)   # 未击穿: 破片/跳弹
    loc = "-"

    target.struct_dmg += dmg

    if pen:
        if rng.random() < 0.10:
            target.fire = min(1.0, target.fire + rng.uniform(0.04, 0.10))
        if rng.random() < 0.07:
            target.flood = min(1.0, target.flood + rng.uniform(0.03, 0.07))

        # ---- 命中分布（含炮塔投影）----
        r = rng.random()
        sil = TURRET_SILHOUETTE.get(target.cls, 0.15)
        if r < sil:
            # 命中炮塔区
            loc = "炮塔"
            # 炮塔被击穿 → 大比例失能（但非必死：二战多数炮塔命中只瘫一座）
            # ⚠ 小口径弹打不瘫重装甲炮塔（caliber 缩放）
            if rng.random() < 0.55 * min(1.6, caliber):
                if target.turrets_dead < target.turrets_total:
                    target.turrets_dead += 1
                dmg += rng.uniform(2, 5) * caliber
                # 炮塔火灾经扬弹机传弹药库 —— 小概率、仍是可能事件
                if rng.random() < 0.008 * caliber:
                    target.dead = True
            else:
                dmg += rng.uniform(0.5, 1.5) * caliber   # 擦过/被装甲弹开
        elif r < sil + 0.60:
            loc = "船体"
            # 船体/水线段
            if rng.random() < 0.22:            # 水线附近
                target.flood = min(1.0, target.flood + rng.uniform(0.04, 0.12))
                target.speed_frac = max(0.30, target.speed_frac - rng.uniform(0.02, 0.08))
                dmg += rng.uniform(1.5, 4.0) * caliber
            else:
                dmg += rng.uniform(0.5, 2.0) * caliber
        else:
            # 上层建筑/指挥区（面积小，后果局部但可能致命）
            loc = rng.choice(["指挥所", "机舱", "舵机", "弹药库"])
            if loc == "指挥所":
                target.firecontrol = min(1.0, target.firecontrol + rng.uniform(0.15, 0.40))
                dmg += rng.uniform(1.0, 2.5) * caliber
            elif loc == "机舱":
                target.flood = min(1.0, target.flood + rng.uniform(0.05, 0.14))
                dmg += rng.uniform(2.0, 4.5) * caliber
                if rng.random() < 0.15:
                    target.steering = min(1.0, target.steering + rng.uniform(0.2, 0.5))
            elif loc == "舵机":
                target.steering = min(1.0, target.steering + rng.uniform(0.35, 0.85))
                # 舵机舱在水线附近, 顺带进水（阿部弘毅的死因）
                target.flood = min(1.0, target.flood + rng.uniform(0.04, 0.12))
                dmg += rng.uniform(2.0, 4.5) * caliber
            else:  # 弹药库（深部核心区，命中率低但后果极重）
                # ⚠ 弹药库爆沉概率必须随口径缩放：5 寸弹几乎不可能引爆
                #   战列舰弹药库（有装甲盒保护），16 寸弹才有可能。
                boom = rng.uniform(15, 40) * LETH[shell] * caliber
                dmg += boom
                if rng.random() < 0.12 * min(1.5, caliber):
                    target.dead = True

    # 沉没判定（结构超过生命值 / 进水失控）
    was_alive = not target.dead
    if target.struct_dmg >= target.hull_hp or target.flood >= 1.0:
        target.dead = True
    sank = was_alive and target.dead
    return pen, loc, dmg, sank


# ============================================================
# 5. 场景
# ============================================================
def _bb(name, guns, rof, shell, armor, turrets, radar=False, tt=0, tr=False,
        sec_guns=0, ammo_sec=0, sec_kg=38.0):
    return ShipState(name=name, cls="BB", guns=guns, rof=rof, shell=shell,
                     armor=armor, turrets_total=turrets, radar=radar,
                     torpedo_tubes=tt, torpedo_reload=tr,
                     sec_guns=sec_guns, ammo_sec=ammo_sec, sec_kg=sec_kg)


SCENARIOS = {
    "gambler": {
        "jp": [
            # 用户 2026-09-18 编制修正：
            #   · 金刚、榛名【没有参战】→ 删除
            #   · 战列舰只有 日向/伊势/扶桑/山城（4 艘）+ 大和；全部带 AP
            #   · 巡洋舰只有 鸟海、衣笠（北上/大井为雷巡，另计）
            # 2026-09-18 二次修正（用户拍板）：「23」是【炮塔数】，不是炮数。
            #   扶桑/山城/伊势 各 6 座双联 = 12 门；日向 5 号炮塔 1942-05-05
            #   爆报废拆除（−1 座 = −2 门）→ 10 门。四舰合计 23 座 = 46 门 356mm。
            #   携弹按 AMMO_PER_GUN["BB"]≈100发/门 自动随炮数放大。
            _bb("日向", 10, 1.2, "AP", 0.90, 5,
                sec_guns=16, ammo_sec=16 * 150),   # 16门140mm/50，备弹150发/门
            _bb("伊势", 12, 1.2, "AP", 0.90, 6,
                sec_guns=16, ammo_sec=16 * 150),
            _bb("扶桑", 12, 1.0, "AP", 0.85, 6,
                sec_guns=16, ammo_sec=16 * 150),
            _bb("山城", 12, 1.0, "AP", 0.85, 6,
                sec_guns=16, ammo_sec=16 * 150),
            _bb("大和", 9, 1.5, "AP", 1.00, 3,
                sec_guns=12, ammo_sec=12 * 150, sec_kg=55.5),  # 12门155mm三年式
            ShipState("鸟海", "CA", 10, 3.0, "AP", 0.50, turrets_total=5,
                      sec_guns=8, ammo_sec=8 * 100, sec_kg=23.0),  # 12.7cm 高炮（次要）
            ShipState("衣笠", "CA", 10, 3.0, "AP", 0.50, turrets_total=5,
                      sec_guns=8, ammo_sec=8 * 100, sec_kg=23.0),
            # 雷巡（鱼雷管未拆完）—— 主战价值在 24 管 93 式，火炮很弱
            ShipState("北上", "CL", 4, 2.5, "AP", 0.45, turrets_total=2,
                      torpedo_tubes=24, torpedo_reload=True),
            ShipState("大井", "CL", 4, 2.5, "AP", 0.45, turrets_total=2,
                      torpedo_tubes=24, torpedo_reload=True),
            *[ShipState(f"日驱{i}", "DD", 5, 4.0, "AP", 0.20, turrets_total=2,
                        torpedo_tubes=8, torpedo_reload=(i % 2 == 0))
              for i in range(1, 7)],
        ],
        "us": [
            # 用户 2026-09-18 编制修正：
            #   · 巡洋舰 = 旧金山 / 波特兰 / 海伦娜 / 朱诺 / 亚特兰大（并入战列线，
            #     与战列舰一起参加纵队炮战）
            _bb("华盛顿", 9, 1.7, "AP", 1.00, 3, radar=True),
            _bb("南达科他", 9, 1.7, "AP", 1.00, 3),
            ShipState("旧金山", "CA", 9, 3.0, "AP", 0.50, turrets_total=4, radar=True),
            ShipState("波特兰", "CA", 9, 3.0, "AP", 0.50, turrets_total=4, radar=True),
            ShipState("海伦娜", "CL", 15, 5.0, "AP", 0.35, turrets_total=5, radar=True),
            ShipState("朱诺", "CL", 16, 5.0, "AP", 0.30, turrets_total=8),
            ShipState("亚特兰大", "CL", 16, 5.0, "AP", 0.30, turrets_total=8),
            *[ShipState(f"美驱{i}", "DD", 5, 5.0, "AP", 0.20, turrets_total=2,
                        torpedo_tubes=10) for i in range(1, 6)],
        ],
        "jp_mods": {"surprise": 1.30, "crossing_T": 1.10, "confusion": 1.0,
                    "smoke_jam": 1.0, "illumination": 1.45},
        "us_mods": {"surprise": 0.85, "crossing_T": 0.95, "confusion": 0.80,
                    "smoke_jam": 0.70, "illumination": 1.0},
        # FEM 可靠性干扰因子（torpedo_fem.py 第5节，2026-09-24）：
        #   93 式 ≈ 0.80（接触引信可靠、浅定深、远射程突防）
        #   Mk-15(1942) ≈ 0.07（磁引信灾难性失效 + 深弹道从 3m 跑成 10m）
        "jp_torp_quality": 0.80,
        "us_torp_quality": 0.07,
        "yamato_minutes": 30,
        "engage_range": (16.4, 19.7),   # 15,000-18,000 米
    },
    "historical": {
        "jp": [
            _bb("比睿", 8, 1.3, "SANS", 0.80, 4),   # 史实: 三式弹为主
            _bb("雾岛", 8, 1.3, "SANS", 0.80, 4),
            *[ShipState(f"日驱{i}", "DD", 5, 4.0, "AP", 0.20, turrets_total=2,
                        torpedo_tubes=8, torpedo_reload=(i % 2 == 0))
              for i in range(1, 7)],
        ],
        "us": [
            _bb("华盛顿", 9, 1.7, "AP", 1.00, 3, radar=True),
            _bb("南达科他", 9, 1.7, "AP", 1.00, 3),
            ShipState("旧金山", "CA", 9, 3.0, "AP", 0.50, turrets_total=4, radar=True),
            ShipState("亚特兰大", "CL", 16, 5.0, "AP", 0.30, turrets_total=8),
            *[ShipState(f"美驱{i}", "DD", 5, 5.0, "AP", 0.20, turrets_total=2,
                        torpedo_tubes=10) for i in range(1, 6)],
        ],
        "jp_mods": {"surprise": 1.0, "crossing_T": 0.95, "confusion": 1.0,
                    "smoke_jam": 1.0, "illumination": 1.15},
        "us_mods": {"surprise": 1.0, "crossing_T": 1.0, "confusion": 0.90,
                    "smoke_jam": 1.0, "illumination": 1.0},
        # FEM 可靠性干扰因子（torpedo_fem.py 第5节，2026-09-24）：
        #   93 式 ≈ 0.80（接触引信可靠、浅定深、远射程突防）
        #   Mk-15(1942) ≈ 0.07（磁引信灾难性失效 + 深弹道从 3m 跑成 10m）
        "jp_torp_quality": 0.80,
        "us_torp_quality": 0.07,
        "yamato_minutes": 0,
        "engage_range": (3.0, 8.0),     # 史实: 3800-8000米贴脸混战
    },
}


# ============================================================
# 6. 有限元推进：按 30 秒步长推进，逐发结算
# ============================================================
# ---- 目标分配（用户 2026-09-18 关键纠正）----
# "一战、二战基准的炮击（尤其是光学瞄准炮击）基本上以单挑为主。
#  在战列舰/巡洋舰编队射击时，通常按威胁度从大到小，舰队从前到后
#  1对1 单挑。只有必要时会集火。"
#
# ⇒ 不能用 rng.choice(alive)（随机分配）：随机分配会把火力均匀摊开，
#   既不符合光学炮术的实际（每艘舰的火控指挥仪锁定一个目标），
#   也抹掉了日方 7 艘战列舰对 2 艘的数量优势。
#
# 威胁度由大到小：BB > CA > CL > DD（CV 视为高威胁）。
# 同型内按舰队纵队顺序（order：0=前导）配对。
CLASS_THREAT_RANK = {"BB": 0, "CV": 1, "CA": 2, "CL": 3, "DD": 4}


def build_target_map(shooters, targets) -> dict:
    """按【威胁度从大到小】排序后，舰队从前到后 1 对 1 单挑。

    用户 2026-09-18 口径：
      "一战、二战基准的炮击（尤其是光学瞄准炮击）基本上以单挑为主。在战列舰/
       巡洋舰编队射击时，通常按威胁度从大到小，舰队从前到后 1对1 单挑。
       只有必要时会集火。"
      "这不是问题，因为那天晚上美国巡洋舰数量不少，也加入了战列线。"

    ⚠ 结构修正（2026-09-18 二次自检）：
      上一版我自作主张改成"同级优先配对"（BB打BB、CA打CA），结果美方巡洋舰
      只打日方巡洋舰，日方 5 艘战列舰里有 3 艘【全程无人还击】
      （扶桑/山城/大和 终局残余 99.5-99.9%）—— 这才是真正的"先手方虐杀"。
      正确做法就是用户说的【纯威胁度顺序 1:1】：美方战列线 = 2BB+2CA+3CL，
      与日方战列线（5BB+2CA+2CL）按威胁度顺序面对面配对，
      ⇒ 美方巡洋舰【会】打到日方战列舰（它们是战线的一部分）。
      攻方多出的舰 → 轮转分配（"必要时集火"，但不全挤在首舰上）。
    """
    live_sh = [s for s in shooters if not s.dead and not s.withdrawn]
    live_tg = [t for t in targets if not t.dead and not t.withdrawn]
    if not live_sh:
        return {}
    if not live_tg:
        # 对方全部脱离/沉没 → 退化为打仍在场的（含已脱离的，追击性质）
        live_tg = [t for t in targets if not t.dead]
    if not live_tg:
        return {}
    key = lambda s: (CLASS_THREAT_RANK.get(s.cls, 5), s.order)
    sh_sorted = sorted(live_sh, key=key)
    tg_sorted = sorted(live_tg, key=key)
    m = {}
    n = len(tg_sorted)
    for i, sh in enumerate(sh_sorted):
        m[sh.name] = tg_sorted[i].name if i < n else tg_sorted[i % n].name
    return m


def step_fire(t_min: float, side_a, side_b, mods_a, mods_b, d_kyd,
              rng, shots: list, phase: str, ambush_a=False, ambush_b=False,
              duration_sec: float = 30.0, a_is_jp: bool = True, b_is_jp: bool = False,
              bombard_a: bool = False, focus_lead_dd: bool = False,
              target_map: dict | None = None, allow_withdrawn: bool = False):
    """
    在 [t_min, t_min + duration_sec] 这段时间里，按【各舰自己的射击周期】
    逐轮推进；每轮每门炮各发一发（整轮齐射，符合二战主炮齐射战术）。

    用户 2026-09-18 修正：
      ① 战列舰 30 秒/轮，驱逐舰/巡洋舰 10 秒/轮（轻巡 6 寸 8 秒）
         → 不能用全队统一 30 秒迭代；驱逐舰在 30 秒里应打 3 轮。
      ② 每一次射击都要落表，含弹种、命中、部位、毁伤、战沉。
      ③ 某舰火控失效只影响它自己；弹药打空即停火。
    """
    def fire(side, targets, mods, ambush, is_jp, is_bombard):
        # ---- 本时间片实际能开火的舰（射程门限 + 存活 + 未脱离 + 有弹 + 炮可用）----
        able = [sh for sh in side
                if not sh.dead and not sh.withdrawn and sh.ammo_main > 0
                and sh.ammo_battle > 0
                and sh.gun_availability() > 0.02
                and d_kyd * 914.4 <= sh.gun_range_m]
        if not able:
            return
        # ---- 目标池：追击阶段可以把"已脱离的舰"也纳入（含落单慢舰）----
        if allow_withdrawn:
            tg_pool = [t for t in targets if not t.dead]
        else:
            tg_pool = [t for t in targets if not t.dead and not t.withdrawn]
            if not tg_pool:
                tg_pool = [t for t in targets if not t.dead]
        # ---- 目标分配 ----
        # ① 显式目标表（追击等自定义选靶）
        # ② 驱逐舰对冲段：集火对方带头驱逐舰
        # ③ 常规：按威胁度 1对1 单挑
        if target_map is not None:
            tmap = dict(target_map)
        else:
            tmap = build_target_map(able, tg_pool)
        if focus_lead_dd:
            # ---- 集火"带头驱逐舰"（用户 2026-09-18）----
            # ⚠ 修正（2026-09-18 自检）：上一版锁定【对方全队纵队的首舰】，
            #   导致日方 6 艘驱逐舰整场只打美驱1（累计 130 发命中）而美驱2
            #   只吃到 48 发 —— 火力被"粘"在一艘已经打成筛子的船上，既不
            #   符合"打瘫带头舰后转向次舰"的海战实际，也人为放大了某一舰
            #   的承受量。正确做法：只集火【对方带头的驱逐舰】，且当该舰
            #   已被重创（结构损伤 > 60%）时，自动转到下一艘尚可战的驱逐舰。
            live_dd = sorted([t for t in tg_pool
                              if not t.dead and t.cls == "DD"],
                             key=lambda t: t.order)
            # 挑第一艘"还没被打残"的（结构损伤 <= 60%），全残则退回第一艘
            lead = None
            for t in live_dd:
                if t.struct_dmg / max(1.0, t.hull_hp) <= 0.60:
                    lead = t
                    break
            if lead is None and live_dd:
                lead = live_dd[0]
            if lead is not None:
                for sh in able:
                    if sh.cls == "DD":
                        tmap[sh.name] = lead.name
        for sh in able:
            if sh.dead or sh.ammo_main <= 0 or sh.ammo_battle <= 0:
                continue
            ga = sh.gun_availability()
            if ga <= 0.02:
                continue
            cyc = sh.cycle_sec
            n_cycles = duration_sec / cyc
            # 这个时间片里它能打几轮（含小数概率）
            n_whole = int(n_cycles)
            if rng.random() < (n_cycles - n_whole):
                n_whole += 1
            for _ in range(n_whole):
                if sh.dead or sh.ammo_main <= 0 or sh.ammo_battle <= 0:
                    break
                ga = sh.gun_availability()
                if ga <= 0.02:
                    break
                # 本轮齐射的炮数（ga 决定几门炮能响）
                guns_up = sh.guns * ga
                n_g = int(guns_up)
                if rng.random() < (guns_up - n_g):
                    n_g += 1
                for _ in range(n_g):
                    if sh.ammo_main <= 0 or sh.ammo_battle <= 0:
                        break
                    # ---- 目标：优先打配对目标；配对目标已沉则重分配 ----
                    tname = tmap.get(sh.name)
                    tgt = next((t for t in tg_pool
                                if t.name == tname and not t.dead), None)
                    if tgt is None:
                        alive = sorted([t for t in tg_pool if not t.dead],
                                       key=lambda t: (CLASS_THREAT_RANK.get(t.cls, 5),
                                                      t.order))
                        if not alive:
                            return
                        tgt = alive[0]          # 集火到最高威胁的存活目标
                        tmap[sh.name] = tgt.name
                    if is_bombard:
                        shell = roll_shell(DOCTRINE_BOMBARD_JP, rng, jp=True)
                    else:
                        shell = roll_shell(None, rng, jp=is_jp)
                    p = single_shot_p(sh, tgt, d_kyd, mods, rng,
                                      ambush=ambush, shell=shell)
                    hit = rng.random() < p
                    pen, loc, dmg, sank = False, "-", 0.0, False
                    if hit:
                        pen, loc, dmg, sank = apply_shot(
                            tgt, shell, rng, jp_shooter=is_jp,
                            caliber=caliber_factor(sh.cls, sh.guns))
                    sh.ammo_main -= 1
                    sh.ammo_battle -= 1
                    shots.append(ShotRecord(
                        t_min=round(t_min, 2), shooter=sh.name,
                        shooter_cls=sh.cls, target=tgt.name,
                        target_cls=tgt.cls, distance_kyd=round(d_kyd, 2),
                        shell=shell, hit=hit, penetrated=pen, location=loc,
                        dmg=round(dmg, 2), target_dead_after=tgt.dead,
                        sank_now=sank, phase=phase))

    fire(side_a, side_b, mods_a, ambush_a, a_is_jp, bombard_a)
    fire(side_b, side_a, mods_b, ambush_b, b_is_jp, False)

    # ---- 损管推进（用户 2026-09-18 隐含要求）----
    # 没有这一步，进水会单调累积到 1.0，把主炮可用度压到 5-10%。
    dt_min = duration_sec / 60.0
    for s in list(side_a) + list(side_b):
        s.damage_control(dt_min)


# ---- FEM 标定的鱼雷命中率（torpedo_fem.py 有限元推算，2026-09-24）----
# 干净几何底 per-target（直航雷打匀速编队，3° 散布，BB 半长 110m，N=9 编队）：
#   D=15km → 9.1% ; D=18km → 7.4% ; D=20km → 6.7%（torpedo_fem.py 第1节）
# quality 在此语义改为【可靠性干扰因子】（FEM 第5节）：
#   93 式 ≈ 0.80（接触引信可靠、浅定深、远射程突防）
#   Mk-15(1942) ≈ 0.07（磁引信灾难性失效 + 深弹道从 3m 跑成 10m）
# #17 减速致命：中弹减速 → 不可机动 → 更易命中（torpedo_fem.py 第4节）
def _torp_clean_p(dist_m: float) -> float:
    """FEM 干净几何底 per-target（距离相关，线性插值，夹紧到 15-20 km）。"""
    d = max(15000.0, min(20000.0, dist_m))
    if d <= 15000.0:
        return 0.091
    if d >= 20000.0:
        return 0.067
    return 0.091 + (d - 15000.0) / 5000.0 * (0.067 - 0.091)


def _torp_slowdown(speed_frac: float) -> float:
    """#17：满速 0.55（可机动规避），停车 1.20（死靶）。"""
    sf = max(0.0, min(1.0, speed_frac))
    return 0.55 + 0.65 * (1.0 - sf)


def torpedo_strike(t_min: float, attackers, targets, quality, rng,
                   shots: list, phase: str, rounds: int = 2,
                   screen=None, screen_break: float = 1.0,
                   dist_kyd: float = 0.0, is_jp: bool = True):
    """
    鱼雷齐射：逐条落表（在【抵达时刻】结算）。

    用户 2026-09-18 战场切分模型：
      · 驱逐舰忙于对射与放雷 → 美驱突破日驱防线打到日战列舰的概率很低
      · 93 式却能穿过美驱部队抵达美舰战线
      ⇒ screen      = 对方驱逐舰幕（拦截方）
        screen_break = 一条鱼雷穿过该幕、抵达预定目标的概率
          · 93 式打美战列线：screen = 美驱，screen_break ≈ 0.75（穿幕容易）
          · 美 Mk-15 打日战列线：screen = 日驱，screen_break ≈ 0.15（很难突破）
      被幕拦下的鱼雷不是凭空消失——它在幕上打成驱逐舰（或空耗）。

    战果口径（用户定稿）: DD 1发即沉 / CL·CA 1发重创 / BB 1发重伤、
      2发以上必严重受损（TDS 命中位置决定是否贯穿核心区）。
    """
    alive = [t for t in targets if not t.dead]
    screen_alive = [s for s in (screen or []) if not s.dead]
    for sh in attackers:
        if sh.dead or sh.torpedo_tubes == 0:
            continue
        for r in range(rounds):
            if r == 1 and not sh.torpedo_reload:
                break
            per = sh.torpedo_tubes // max(1, rounds)
            for _ in range(per):
                # ---- 先决定这一条打谁（是否被驱逐舰幕拦下）----
                if screen_alive and rng.random() >= screen_break:
                    pool = screen_alive        # 被幕拦下 → 打在驱逐舰上
                else:
                    pool = alive               # 穿过幕 → 打预定目标
                if not pool:
                    pool = alive or screen_alive
                if not pool:
                    return
                # ⚠ 目标选取修正（2026-09-18 自检发现）：
                #   上一版 rng.choice(pool) 是【均匀随机】。美方编成里 DD 占
                #   5/11 → 白白吃掉 45% 的 93 式，而 DD "1 发即沉" → 60 轮里
                #   205 发鱼雷命中 DD、205 艘当场沉没（US DD 沉没率 66%，
                #   日 DD 2%）。这与史实完全不符：九三式射程 20-40 km、装药
                #   490 kg，雷击指挥官瞄准的是【最大的舰影】，驱逐舰被命中
                #   属误中/顺带。史实萨沃岛、塔萨法隆加，Long Lance 的猎物
                #   都是巡洋舰与战列舰。
                #   ⇒ 按【舰型投影/价值】加权：BB 3.5 / CA 2.4 / CL 2.0 /
                #     DD 1.0 / CV 4.0。这样主力舰蚕食掉大部分雷击份额，
                #     驱逐舰只在"穿幕失败被拦下"时被动接雷。
                TORP_AIM_W = {"BB": 3.5, "CV": 4.0, "CA": 2.4, "CL": 2.0, "DD": 1.0}
                wts = [TORP_AIM_W.get(t.cls, 1.0) for t in pool]
                tgt = rng.choices(pool, weights=wts, k=1)[0]
                # 单管鱼雷命中率（FEM 标定，torpedo_fem.py 2026-09-24）：
                #   p = 干净几何底(距离) × 可靠性(quality) × 舰型 × 减速因子(#17)
                #   干净底 @18km=7.4% × 93可靠0.80 × BB1.25 × 满速0.55 ≈ 4.1%
                #     —— 落在用户定的 3-5% 区间，且可审计来源。
                #   Mk-15 可靠0.07 → 0.36% ≈ 史实"1942 全年零战果"。
                #   匀速编队本身是直线雷的好靶子（FEM per-any ≈ 44% @18km），
                #   故实测差异几乎全在【引信/定深可靠性】，不在几何。
                dist_m = dist_kyd * 914.4 if dist_kyd > 0 else 18000.0
                p = _torp_clean_p(dist_m)
                p *= quality                      # 可靠性干扰因子（93≈0.80 / Mk-15≈0.07）
                if tgt.cls == "BB":
                    p *= 1.25
                elif tgt.cls == "DD":
                    p *= 0.75
                p *= _torp_slowdown(tgt.speed_frac)   # #17 中弹减速=最致命
                p *= 0.65
                hit = rng.random() < p
                loc, dmg, pen = "-", 0.0, False
                sank = False
                was_alive = (not tgt.dead)
                if hit:
                    pen = True
                    tgt.torpedo_hits_taken += 1
                    n = tgt.torpedo_hits_taken
                    tl = TORPEDO_LETHALITY.get(tgt.cls, {"sink": 3.0, "severe": 1.0})

                    # 舰型依赖的毁伤（用户 2026-09-18 定稿口径）:
                    #   DD  : 1 发即秒沉（任务杀伤）
                    #   CL/CA: 1 发重创（可能当场沉，也可能残存但失去战力）
                    #   BB  : 1 发重伤但【不沉】；2 发以上必严重受损（可沉）
                    # 注意：单发毁伤上限受船体尺度约束，
                    #       BB 结构 100 点，单发鱼雷最多削掉 55-70 点，
                    #       不会出现"一发秒战列舰"（吴港轰炸除外）。
                    if tgt.cls == "DD":
                        # 驱逐舰吃一发 93 式：多数当场断成两截/迅速沉没，
                        # 但有相当比例是"被打瘫但浮着"（拖回去报废）。
                        # 用户口径"基本秒驱逐舰"→ 取 0.72 而非 0.88
                        dmg = tgt.hull_hp * rng.uniform(1.0, 1.8)
                        tgt.struct_dmg += dmg
                        tgt.flood = min(1.0, tgt.flood + rng.uniform(0.55, 0.95))
                        tgt.speed_frac = 0.0
                        if rng.random() < 0.72:
                            tgt.dead = True
                        loc = "船体/断成两截"
                    elif tgt.cls == "BB":
                        # 战列舰吃 93 式 —— 用户 2026-09-18 定稿口径：
                        #   "TDS 深度基本不够" ⇒ ① 单发几乎必然丧失战斗力
                        #                        ② 两发必沉
                        zones = list(TDS_HIT_ZONES.keys())
                        wts = [TDS_HIT_ZONES[z][0] for z in zones]
                        zone = rng.choices(zones, weights=wts, k=1)[0]
                        depth_c, can_core = TDS_HIT_ZONES[zone][1], TDS_HIT_ZONES[zone][2]
                        # 贯穿核心区概率：TDS 纵深越小越容易贯穿
                        # （旧值 0.19-0.43 把 TDS 想得太有效，与用户判断矛盾）
                        P_CORE_BY_ZONE = {"TDS主体": 0.55, "TDS削弱区": 0.85,
                                          "舰首舰尾": 0.0}
                        # 贯穿核心区概率：TDS 纵深越小越易贯穿；93式装药(490kg)
                        # 大于 Mk-15(360kg)，故日方战雷贯穿略强（warhead 因子）。
                        _warhead = 1.10 if is_jp else 0.90
                        p_core = min(0.95, P_CORE_BY_ZONE.get(zone, 0.0)
                                     * (0.75 + 0.35 * _warhead))
                        core = rng.random() < p_core
                        if core:
                            frac = rng.uniform(0.35, 0.70)
                            dmg = tgt.hull_hp * frac
                            tgt.struct_dmg += dmg
                            tgt.flood = min(0.95, tgt.flood + rng.uniform(0.40, 0.70))
                            loc = rng.choice(["动力舱/TDS贯穿", "弹药舱/TDS贯穿",
                                              "机舱/TDS贯穿"])
                            if "弹药舱" in loc:
                                tgt.struct_dmg += tgt.hull_hp * rng.uniform(0.20, 0.45)
                                if rng.random() < 0.55:
                                    tgt.dead = True
                            else:
                                tgt.steering = min(1.0, tgt.steering + rng.uniform(0.5, 1.0))
                                tgt.firecontrol = min(1.0, tgt.firecontrol + rng.uniform(0.3, 0.6))
                        else:
                            # 未贯穿核心区，但 TDS 仍被撕开 → 大量进水
                            dmg = tgt.hull_hp * rng.uniform(0.10, 0.25)
                            tgt.struct_dmg += dmg
                            tgt.flood = min(0.95, tgt.flood + rng.uniform(0.20, 0.40))
                            loc = f"舷侧/{zone}进水"
                        # 动力/舵机（纵深越浅越容易失动力）
                        if rng.random() < 0.45 + 0.30 * (1 - depth_c):
                            tgt.steering = min(1.0, tgt.steering + rng.uniform(0.2, 0.6))
                        tgt.speed_frac = max(0.0, tgt.speed_frac - rng.uniform(0.20, 0.50))
                        if rng.random() < 0.40:
                            tgt.firecontrol = min(1.0, tgt.firecontrol + rng.uniform(0.15, 0.40))

                        # ---- 用户口径：1 发几乎必然丧失战斗力；2 发必沉 ----
                        if n >= 1:
                            tgt.flood = min(1.0, max(tgt.flood, rng.uniform(0.45, 0.80)))
                            tgt.speed_frac = min(tgt.speed_frac, rng.uniform(0.0, 0.25))
                            if rng.random() < 0.85:
                                tgt.firecontrol = min(1.0, max(
                                    tgt.firecontrol, rng.uniform(0.55, 0.95)))
                            if rng.random() < 0.55:
                                tgt.steering = 1.0
                            if rng.random() < 0.88:
                                tgt.withdrawn = True      # 丧失战斗力 → 退出战线
                                if tgt.withdrawn_at < 0:
                                    tgt.withdrawn_at = t_min
                        if n >= tl["sink"]:               # 2 发必沉
                            tgt.dead = True
                    else:
                        # 巡洋舰：一发重创（用户口径"重创巡洋舰"≠沉没）
                        # ⚠ 修正（2026-09-18 自检发现）：上一版 frac =
                        #   uniform(0.60,1.05)*quality(1.5) = 0.90-1.58 × 全HP
                        #   → 单发即 100%+ 结构损伤 → 【每命中沉没率 75%】。
                        #   这套口径把"重创"写成了"当场沉没"，与用户明确
                        #   给的"1 发重创、2.5 发沉"矛盾，也把 93 式的战果
                        #   放大到荒谬（60 轮里 192 条鱼雷沉掉 5.5 艘美舰）。
                        #   史实：萨沃岛 6 条 Long Lance 命中并未当场沉掉美巡
                        #   洋舰（沉没是鱼雷+炮击+数小时进水的合力）。
                        #   ⇒ 单发毁伤收敛到 0.22-0.48 × HP（重创但不即刻沉），
                        #     累计到 tl["sink"]=2.5 发（即第 3 发）才判沉。
                        frac = rng.uniform(0.22, 0.48) * (1.10 if is_jp else 0.90)
                        dmg = tgt.hull_hp * frac
                        tgt.struct_dmg += dmg
                        tgt.flood = min(1.0, tgt.flood + rng.uniform(0.25, 0.55))
                        loc = "船体/水线"
                        if rng.random() < 0.30:
                            loc = rng.choice(["舵机", "机舱", "弹药库"])
                            if loc == "舵机":
                                tgt.steering = min(1.0, tgt.steering + rng.uniform(0.6, 1.0))
                                tgt.flood = min(1.0, tgt.flood + rng.uniform(0.15, 0.30))
                            elif loc == "机舱":
                                tgt.flood = min(1.0, tgt.flood + rng.uniform(0.30, 0.60))
                                tgt.struct_dmg += tgt.hull_hp * 0.10
                            else:
                                tgt.struct_dmg += tgt.hull_hp * rng.uniform(0.10, 0.28)
                        if n >= tl["sink"]:
                            tgt.dead = True
                        # CL/CA 1 发即"重创"(severe=1.0)
                        if n >= tl["severe"]:
                            tgt.firecontrol = min(1.0, tgt.firecontrol + rng.uniform(0.35, 0.75))
                            tgt.steering = min(1.0, tgt.steering + rng.uniform(0.25, 0.55))
                        tgt.speed_frac = max(0.10, tgt.speed_frac - rng.uniform(0.25, 0.55))

                    if tgt.struct_dmg >= tgt.hull_hp or tgt.flood >= 1.0:
                        tgt.dead = True
                    sank = was_alive and tgt.dead

                shots.append(ShotRecord(
                    t_min=round(t_min, 2), shooter=sh.name, shooter_cls=sh.cls,
                    target=tgt.name, target_cls=tgt.cls,
                    # 鱼雷的"距离"= 发射时的交战距离（码→kyd）；
                    # 由 schedule_torp 传入的 dist_kyd 记录，便于事后核验
                    distance_kyd=round(dist_kyd, 2) if dist_kyd else -1.0,
                    shell="93鱼雷" if is_jp else "Mk15鱼雷",
                    hit=hit, penetrated=pen, location=loc, dmg=round(dmg, 2),
                    target_dead_after=tgt.dead, sank_now=sank, phase=phase))
                if tgt.dead:
                    alive = [t for t in alive if not t.dead]
                    screen_alive = [t for t in screen_alive if not t.dead]


# ============================================================
# 6b. 鱼雷航行延迟（用户 2026-09-18 战场切分模型）
# ============================================================
# 用户："战场可以切分……鱼雷到之后再计算即可（日本 93 可以穿过美国驱逐舰
#      部队抵达战列舰战线，但美国驱逐舰想穿过日本驱逐舰去雷击日本战列舰
#      概率很低）"
#   ⇒ 发射时刻只决定【管数 / 目标 / 是否被幕拦下 / 是否命中】，
#     毁伤要等鱼雷【航行到位】才落表。Mk-15 慢（45 kt → 约 1.6 kyd/min），
#     93 式快（48-50 kt → 约 1.7 kyd/min），故 15 kyd 交战距离下
#     航行时间约 9-10 分钟 —— 足以让战列线先换位、驱逐舰先互怼。
#
# 实现：用模块级队列 _TORP_QUEUE 存 (arrive_min, 结算闭包)，
#       flush_torp(t_now) 把 arrive_min <= t_now 的全部弹出结算。
_TORP_QUEUE: list = []

# 鱼雷速度（码/分）—— 二战长矛 ≈ 48 kt ≈ 1620 yd/min；Mk-15 ≈ 45 kt
_TORP_SPEED_YPM = {"93": 1620.0, "Mk15": 1520.0}


def schedule_torp(t_fire: float, attackers, targets, quality: float,
                  phase: str, distance_m: float,
                  screen=None, screen_break: float = 1.0,
                  rounds: int = 1, is_jp: bool = True):
    """把一次鱼雷齐射【排入】航行队列，抵达时再结算毁伤。

    t_fire       ：发射绝对分钟
    distance_m   ：发射时距离（米）→ 换算航程算航行时间
    screen       ：对方驱逐舰幕（拦截方舰船列表）
    screen_break ：单条鱼雷穿过该幕的概率
    """
    if not attackers:
        return
    ypm = _TORP_SPEED_YPM["93"] if is_jp else _TORP_SPEED_YPM["Mk15"]
    dist_yd = max(600.0, distance_m / 0.9144)      # 米 → 码
    travel_min = dist_yd / ypm                     # 航行时间（分钟）
    arrive = t_fire + travel_min

    # ⚠ 快照：鱼雷在发射时刻就把"目标集"锁定（用发射时刻的存活舰）。
    #   但真正结算时，被幕拦下的那条打的是"当时还活着的护卫舰"。
    _TORP_QUEUE.append({
        "arrive": arrive, "fire": t_fire,
        "attackers": list(attackers), "targets": list(targets),
        "quality": quality, "phase": phase, "rounds": rounds,
        "screen": list(screen) if screen else None,
        "screen_break": screen_break, "is_jp": is_jp,
        "dist_kyd": distance_m / 914.4,      # 发射时交战距离（kyd），供核验
    })


def flush_torp(t_now: float):
    """结算所有已抵达（arrive <= t_now）的鱼雷齐射，返回结算条数。"""
    global _TORP_QUEUE
    due = [q for q in _TORP_QUEUE if q["arrive"] <= t_now + 1e-9]
    _TORP_QUEUE = [q for q in _TORP_QUEUE if q["arrive"] > t_now + 1e-9]
    n = 0
    for q in sorted(due, key=lambda d: d["arrive"]):
        # 发射舰若在航行途中被击沉/瘫痪 → 已射出的鱼雷不受影响（照常抵达）；
        # 其未射出的管数在 torpedo_strike 内部按"已沉没则跳过"处理。
        torpedo_strike(
            q["arrive"], q["attackers"], q["targets"], q["quality"],
            _FLUSH_RNG[0], _FLUSH_SHOTS[0],
            q["phase"], rounds=q["rounds"],
            screen=q["screen"], screen_break=q["screen_break"],
            dist_kyd=q.get("dist_kyd", 0.0))
        n += 1
    return n


# flush 需要的 rng / shots 句柄（由 run_once 注入，避免污染函数签名）
_FLUSH_RNG = [None]
_FLUSH_SHOTS = [None]


def _torp_clear():
    """清空跨次推演的鱼雷队列（run_once 开头调用，防止蒙特卡洛串场）。"""
    global _TORP_QUEUE
    _TORP_QUEUE = []


# ============================================================
# 7. 单次推演（按用户时间轴）
# ============================================================
def run_once(cfg, rng) -> dict:
    """
    单次推演 —— 按用户 2026-09-18 时间轴（肖特兰起航版）逐拍推进。

    时间轴（T = 10/24 夜）：
      19:00  日舰自肖特兰出航（不在本函数内，已在上游阶段完成）
      21:30  水上侦察机在铁底湾投照明弹
      22:00  通过萨沃海峡进入射击海域
      23:05  三川（鸟海/衣笠）前出诱饵 → 吸引美舰火力
      23:30  美舰转移火力 → 日方战列舰进入奇袭窗口
      23:40  日方 93 式长矛鱼雷齐射
      23:45  美方 Mk-15 鱼雷反击
      23:55  双方进入持续炮战
      00:15  大和外围主炮支援（限 30 分钟）
      00:45  大和退出，转入对亨德森机场岸轰
      01:40  岸轰结束
    """
    jp = copy.deepcopy(cfg["jp"])
    us = copy.deepcopy(cfg["us"])
    # ---- 纵队顺序：按编队列表的先后（0=前导）—— 用于 1对1 单挑配对 ----
    for i, s in enumerate(jp):
        s.order = i
    for i, s in enumerate(us):
        s.order = i
    jm, um = dict(cfg["jp_mods"]), dict(cfg["us_mods"])
    rng_lo, rng_hi = cfg["engage_range"]
    shots: list[ShotRecord] = []

    # ---- 鱼雷航行队列初始化（防止蒙特卡洛各次推演串场）----
    _torp_clear()
    _FLUSH_RNG[0] = rng
    _FLUSH_SHOTS[0] = shots

    jp_bb = [s for s in jp if s.cls == "BB" and s.name != "大和"]
    us_bb = [s for s in us if s.cls == "BB"]
    yamato = next((s for s in jp if s.name == "大和"), None)
    jp_dd = [s for s in jp if s.cls == "DD"]
    us_dd = [s for s in us if s.cls == "DD"]
    jp_torp = [s for s in jp if s.torpedo_tubes > 0]
    us_torp = [s for s in us if s.torpedo_tubes > 0]

    # ---- 迭代表：每 20 秒采一帧各舰状态（用户 2026-09-18 要求）----
    snapshots: list = []
    last_snap_t = [None]

    def snap(t_abs: float, note: str = ""):
        """把当前所有舰的状态落一帧。t_abs = 自 10/24 23:00 起的绝对分钟。

        用户 2026-09-18：
          · 进入双方炮击后按【20 秒】步长迭代（STEP_MIN = 1/3 分钟）
          · 岸上目标不落帧、不列表（那不是舰对舰交战）
        去重键用 round(ts, 3)，避免 1/3 步长被 2 位小数四舍五入吞掉。
        """
        ts = round(t_abs, 3)
        if last_snap_t[0] is not None and abs(last_snap_t[0] - ts) < 1e-6:
            return
        last_snap_t[0] = ts
        for s in jp + us:
            snapshots.append({
                "t": ts, "t_str": abs_to_clock(ts),
                "side": "日" if s in jp else "美",
                "name": s.name, "cls": s.cls,
                "guns": round(s.gun_availability(), 4),
                "hp": round(max(0.0, 1.0 - s.struct), 4),
                "firecontrol": round(1.0 - s.firecontrol, 4),
                "mobility": round(s.mobility(), 4),
                "speed": round(s.speed_frac, 4),
                "flood": round(s.flood, 4),
                "fire": round(s.fire, 4),
                "turrets": f"{s.turrets_dead}/{s.turrets_total}",
                "ammo": s.ammo_main,
                "ammo_battle": s.ammo_battle,
                "dead": s.dead,
                # ⚠ 2026-09-18 修正：必须把【真正脱离】与【弹药打空停火】分开落表。
                #   以前渲染器用 "guns<=0.001" 反推脱离，而 gun_availability()
                #   在 ammo_main<=0 时直接返回 0 → 弹药打空的舰被误标成「⛔脱离」。
                "withdrawn": s.withdrawn,
                "w_at": round(s.withdrawn_at, 3),
                "note": note,
            })

    # ================= 迭代节拍：进入炮击后统一 20 秒（= 1/3 分钟）=================
    # 用户 2026-09-18："迭代步长按 20 秒一次（进入双方炮击后）"
    #   DD / 美 CL ≈ 10s 一炮；美 CA / 日 CL / CA ≈ 20s；BB ≈ 30-40s
    #   鱼雷齐射 20s 内打完 4 联装
    STEP_SEC = 20.0
    STEP_MIN = STEP_SEC / 60.0            # 0.3333... 分钟
    starts = [clock_to_abs(h) for h in (2305, 2330, 2355, 15)]   # 各阶段起点（绝对分钟）
    clock_abs = [starts[0]]               # 当前绝对分钟，逐拍推进

    def advance(phase_i: int, phase_start_abs: float, i: int) -> float:
        """返回第 phase_i 阶段第 i 拍（从 0 起）的绝对分钟"""
        return phase_start_abs + i * STEP_MIN

    snap(clock_to_abs(2300), "开战前")

    # ---------- P1  23:05-23:15  三川诱饵承伤（10 min = 30 拍）----------
    # 用户时间轴：三川（鸟海/衣笠）前出诱饵，把美舰火力吸过来，
    # 掩护主力战列舰在暗处完成测距。此阶段只有这两舰在打。
    sanchuan = [s for s in jp if s.name in ("鸟海", "衣笠")]
    P1_START = starts[0]                              # 23:05
    P1_N = int(round(10 / STEP_MIN))                  # 30 拍 = 10 min
    for i in range(P1_N):
        t_abs = P1_START + i * STEP_MIN
        step_fire(t_abs, sanchuan, us_bb, jm, um,
                  rng.uniform(15.0, 18.0), rng, shots, "P1三川诱饵",
                  duration_sec=STEP_SEC)
        snap(t_abs)

    # ---------- 主战阶段 23:30-00:00（30 min = 90 拍）----------
    # 用户 2026-09-18 时间轴：23:30 美舰确认日方战列舰 → 排纵队、集火战列舰
    #                       23:40 双方驱逐舰进入鱼雷射程、开始对冲
    #                       23:50 第二轮鱼雷
    # ⇒ 战列舰纵队炮战与驱逐舰对冲是【同时发生】的，必须在一个时间循环里
    #   逐拍并行推进，不能拆成两个顺序阶段（否则时间轴错位）。
    um2 = dict(um); um2["confusion"] = 0.80           # 奇袭窗口
    um4 = dict(um); um4["confusion"] = 0.75           # 窗口之后
    jp_heavy = [s for s in jp if s.cls in ("BB", "CA", "CL")]
    us_heavy = [s for s in us if s.cls in ("BB", "CA", "CL")]

    # ================= 脱离 / 放弃战斗 / 追击（用户 2026-09-18）=================
    # "受损严重的船（起火/失动力）会退出队列，退到后方修理。退出交战期间……
    #  基本停止和对手交火，但是可能被鱼雷击中。对手的火力会优先转移去对付
    #  没有受伤的对手。当某一方大部分船只受损/撤退/沉没，且选择放弃战斗时，
    #  另一方会开始追击，此时放弃战斗一方只能被迫继续开火，但是效果会打折，
    #  直到追击方撤离或逃跑方沉没。"
    # "大和不深入追击可视为日本追击的限制指标。" ⇒ 追击硬边界 = 大和 30 分钟。
    def check_withdraw(t_now: float = -1.0):
        for s in jp + us:
            if s.should_withdraw():
                s.withdrawn = True
                if s.withdrawn_at < 0:
                    s.withdrawn_at = t_now

    def strength(side):
        """仍能战斗的舰的加权战力（0-1）"""
        tot = 0.0
        for s in side:
            if s.dead or s.withdrawn:
                continue
            tot += (1.0 - s.struct) * (1 - 0.5 * s.flood) * (1 - 0.4 * s.fire)
        return tot / max(1, len(side))

    def ratio_out(side):
        """沉没 + 脱离 占全队比例"""
        return sum(1 for s in side if s.dead or s.withdrawn) / max(1, len(side))

    def ratio_hurt(side):
        """受损/脱离/沉没 占比（结构损失 > 35% 即视为"受损"）

        用户 2026-09-18："当某一方【大部分船只受损/撤退/沉没】，且选择
        放弃战斗时……" ⇒ 判定必须把"受损"计入，而不只是"沉没/已脱离"。
        """
        n = 0
        for s in side:
            if s.dead or s.withdrawn or s.struct >= 0.35:
                n += 1
        return n / max(1, len(side))

    def do_abandon(side, t_now: float):
        """宣布放弃战斗 → 全队剩余舰脱离（掉头撤退）"""
        for s in side:
            if not s.dead:
                s.withdrawn = True
                if s.withdrawn_at < 0:
                    s.withdrawn_at = t_now

    def catchable(pursuer, target) -> bool:
        """追击可行性（用户 2026-09-18）：慢的追不上快的。

        规则补充：若目标已脱离战斗（在跑），则比较【当前航速】；
        若目标仍在战斗，则按"散乱追击"仍以航速为准。
        留 3 节余量：只有明显更快（>3kt）才能完成占位与持续跟踪。
        """
        return pursuer.speed_kt > target.speed_kt + 3.0

    def pick_pursuit_target(pursuer, pool):
        """散乱追击的目标选择：优先【最后脱离】且【最慢】的落单舰。

        用户："从美军舰队脱离战斗最晚、且速度最慢的开始追击。"
        ⇒ 排序键：先按能否追上（追不上直接排除），再按
          (脱离越晚 → 越优先) + (航速越低 → 越优先)。
        """
        cand = [t for t in pool
                if not t.dead and catchable(pursuer, t)]
        if not cand:
            return None
        # 越晚脱离越优先（withdrawn_at 大）；未脱离的按 -1 视作最早
        cand.sort(key=lambda t: (-t.withdrawn_at, t.speed_kt))
        return cand[0]

    us_abandoned = jp_abandoned = False

    MAIN_START = starts[1]                            # 23:30
    N_MAIN = int(round(30 / STEP_MIN))                # 90 拍 = 30 min
    T_TORP1 = 10.0                                    # 23:40（相对分钟）
    T_TORP2 = 20.0                                    # 23:50
    T_DD    = 10.0                                    # 23:40 驱逐舰开始对冲
    torp1_done = torp2_done = False

    for i in range(N_MAIN):
        t_rel = i * STEP_MIN                          # 相对 23:30 的分钟
        t_abs = MAIN_START + t_rel

        # ---- ⓪ 重伤脱离 + 放弃战斗判定（用户 2026-09-18）----
        check_withdraw(t_abs)
        if not us_abandoned and (ratio_hurt(us) >= 0.60 or strength(us) < 0.30):
            us_abandoned = True
            do_abandon(us, t_abs)          # 全队掉头撤退
        if not jp_abandoned and (ratio_hurt(jp) >= 0.60 or strength(jp) < 0.30):
            jp_abandoned = True
            do_abandon(jp, t_abs)
        # 放弃战斗一方"被迫继续开火，但效果打折"
        um_step = dict(um2 if t_rel < 4.0 else um4)
        jm_step = dict(jm)
        if us_abandoned:
            um_step["disengaged"] = 0.55
        if jp_abandoned:
            jm_step["disengaged"] = 0.55

        # ---- ① 战列舰/巡洋舰纵队炮战（15-18 km，缓慢接近）----
        d_h = max(10.5, rng.uniform(rng_lo, rng_hi) - t_rel * 0.12)
        if t_rel < 4.0:                               # 前 4 分钟 = 奇袭窗口
            step_fire(t_abs, jp_heavy, us_heavy, jm_step, um_step, d_h, rng,
                      shots, "P2纵队奇袭", ambush_a=True, duration_sec=STEP_SEC)
        else:
            step_fire(t_abs, jp_heavy, us_heavy, jm_step, um_step, d_h, rng,
                      shots, "P4纵队炮战", duration_sec=STEP_SEC)

        # ---- ② 驱逐舰对冲（23:40 起，10 km → 7.0 km，集火对方带头 DD）----
        # ⚠ 结构修正（2026-09-18，自检发现）：
        #   上一版把双方 DD 一路压到 5.5 km 做"对等混战"，结果 US DD 沉没率
        #   高达 88%、日 DD 仅 11% —— 8 倍不对称。原因不是标定，而是【结构性
        #   不公平】：日方是 6 DD + 2 艘 24 管雷巡（北上/大井）= 96 管齐射，
        #   美方只有 5 DD × 10 管；且美 DD 的 5 寸炮射程（10 km）以外全程被
        #   日方战列舰单方面射击。史实上 1942 年美军既无可靠鱼雷战法（Mk-15
        #   磁引信问题），也不会主动钻进日方的夜战肉搏距离 —— 美方的实际
        #   反应是【保持距离、以 5 寸炮和雷达占位】。
        #   ⇒ 美 DD 只压到 7.0 km（不再进 5.5 km），日 DD 仍压到 6.0 km
        #     （体现 93 式射程优势与激进夜战教条）。
        if t_rel >= T_DD:
            dd_i = int((t_rel - T_DD) / STEP_MIN)
            d_dd_jp = max(6.0, 10.0 - dd_i * 0.28)     # 日方压得更近
            d_dd_us = max(7.0, 10.0 - dd_i * 0.20)     # 美方保持距离
            # 日方 DD 打美方 DD（近距）
            step_fire(t_abs, jp_dd, us_dd, jm_step, um_step, d_dd_jp, rng, shots,
                      "P5驱逐舰对冲", duration_sec=STEP_SEC, focus_lead_dd=True)
            # 美方 DD 还击（距离略远 → 命中略低，但至少不会被单方面屠杀）
            step_fire(t_abs, us_dd, jp_dd, um_step, jm_step, d_dd_us, rng, shots,
                      "P5美驱还击", duration_sec=STEP_SEC, focus_lead_dd=True)

        # ---- ③ 鱼雷齐射（发射 → 航行 → 抵达结算，用户 2026-09-18）----
        # 用户："战场可以切分……鱼雷到之后再计算即可（日本 93 可以穿过美国
        #      驱逐舰部队抵达战列舰战线，但美国驱逐舰想穿过日本驱逐舰去雷击
        #      日本战列舰概率很低）"
        #   ⇒ 发射时刻决定管数/目标/命中；抵达时刻才落毁伤（航行延迟）。
        dist_m = d_h * 914.4
        if (not torp1_done) and t_rel >= T_TORP1:
            jp_line = [s for s in jp_torp if not s.dead]
            # ⚠ 修正（2026-09-18 自检发现）：上一版有【两路】日方鱼雷 ——
            #   一路"打战列线"（screen=us_dd, break=0.75），一路"打驱逐群"
            #   （screen=None, break=1.0，即整 96 管齐射专打美驱，无幕阻）。
            #   结果 30 轮里 69 发 93 式命中美驱、美驱沉没率 66%（日驱 3%）。
            #   这是模型自造的战术：九三式雷击指挥官瞄准的是【最大的舰影】
            #   （战列舰/巡洋舰），不会专门把 96 管齐射倾泻到驱逐舰群上；
            #   驱逐舰被命中是"穿幕失败被拦下"的副产物。
            #   ⇒ 删除"打驱逐群"这一路。日方鱼雷只打【美战列线】，
            #     美驱幕以 0.75 的穿透率被动拦截 —— 这正是用户原话
            #     "93 可以穿过美国驱逐舰部队抵达战列舰战线"的意思。
            schedule_torp(t_abs, jp_line, us_heavy, cfg["jp_torp_quality"],
                          "P3日93(打战列线)", dist_m,
                          screen=us_dd, screen_break=0.75, rounds=1, is_jp=True)
            # 美方 Mk-15：试图穿日驱幕打日战列线，突破概率很低
            schedule_torp(t_abs, us_torp, jp_heavy, cfg["us_torp_quality"],
                          "P3美Mk15(突日战列线)", dist_m,
                          screen=jp_dd, screen_break=0.15, rounds=1, is_jp=False)
            torp1_done = True
        if (not torp2_done) and t_rel >= T_TORP2:
            # 第二轮：大井/北上 24 管重雷装 + 具再装填能力的驱逐舰
            jp2 = [s for s in jp_torp if not s.dead
                   and (s.torpedo_reload or s.torpedo_tubes >= 20)]
            schedule_torp(t_abs, jp2, us_heavy, cfg["jp_torp_quality"],
                          "P3日93二轮(打战列线)", dist_m,
                          screen=us_dd, screen_break=0.75, rounds=1, is_jp=True)
            torp2_done = True

        flush_torp(t_abs)
        snap(t_abs, "奇袭窗口" if t_rel < 4.0 else
             ("驱逐舰对冲" if T_DD <= t_rel < T_TORP2 else ""))

    # 补算仍在航的鱼雷（战列线脱离后再结算一次）
    flush_torp(MAIN_START + 60.0)

    # ---------- P6  00:15-00:45  散乱追击（大和 30 分钟 = 追击硬边界）----------
    # 用户 2026-09-18:
    #   "当某一方……选择放弃战斗时，另一方会开始追击……直到追击方撤离或逃跑方
    #    沉没。""大和不深入追击可视为日本追击的限制指标。"
    #   "追击是【对方开始散乱追击】——不是整齐队列。追击需要进行【剩余航速
    #    比对】：速度慢的不能追上跑得快的。所以如果美国战败，那么大和和驱逐舰
    #    会从美军舰队脱离战斗最晚、且速度最慢的开始追击。"
    # ⇒ ① 逐舰按 speed_kt 判"追得上吗"（留 3 节余量）
    #    ② 追得上时，优先咬【最后脱离 + 最慢】的落单舰
    #    ③ 追击在 00:45（大和 30 分钟到点）无条件终止 = "追击方撤离"
    yamato_fired = False
    if yamato and cfg["yamato_minutes"] > 0 and not yamato.dead:
        yamato_fired = True
        P6_START = starts[3]
        P6_MIN = cfg["yamato_minutes"]                 # 30 分钟（硬边界）
        P6_N = int(round(P6_MIN / STEP_MIN))           # 90 拍
        um_pursuit = dict(um4)
        if us_abandoned:
            um_pursuit["disengaged"] = 0.55            # 撤退方低效还击
        jm_pursuit = dict(jm)
        if jp_abandoned:
            jm_pursuit["disengaged"] = 0.55
        for i in range(P6_N):
            t_abs = advance(3, P6_START, i)
            check_withdraw(t_abs)
            # 逃跑方全部沉没 → 追击自然结束
            if not any((not s.dead) for s in us):
                break
            d = rng.uniform(12.0, 16.0)
            # 日方追击兵力：大和 + 其他尚可战的战列舰 + 驱逐舰（快的能追上）
            pursuers = [s for s in jp if not s.dead and not s.withdrawn
                        and s.cls in ("BB", "DD")]
            if not pursuers:
                break
            # ---- 逐舰按航速挑目标（散乱追击，不是 1对1 队列）----
            pmap = {}
            for p in pursuers:
                t = pick_pursuit_target(p, us)
                if t is not None:
                    pmap[p.name] = t.name
            if pmap:
                step_fire(t_abs, pursuers, us, jm_pursuit, um_pursuit, d, rng,
                          shots, "P6追击", duration_sec=STEP_SEC,
                          target_map=pmap, allow_withdrawn=True)
            # 美方尚能战斗的舰还击（"被迫继续开火，但效果打折"）
            us_fight = [s for s in us if not s.dead and not s.withdrawn]
            if us_fight:
                step_fire(t_abs, us_fight, pursuers, um_pursuit, jm_pursuit,
                          d, rng, shots, "P6追击·美方还击",
                          duration_sec=STEP_SEC, allow_withdrawn=True)
            snap(t_abs, f"追击{i}" if i % 15 == 0 else "")

    # ---------- P7  岸轰（00:40-01:40）----------
    # 用户 2026-09-18: "对岸上目标不需要蒙特卡洛分析，也不需要列表"
    #   ⇒ 岸轰是对固定陆地目标的弹药投掷，不是舰对舰交战：
    #     不落逐发记录、不进迭代表、不计命中率。
    #     只统计【弹药消耗】（对陆弹 = 高爆 + 三式）与【岸轰战果口径】。
    bombard_rounds = 0                 # 对陆弹总消耗（主炮HE+副炮）
    bombard_sec_rounds = 0             # 其中副炮
    bombard_fill_kg = 0.0              # 对陆【装药量】kg —— 主指标（用户 2026-09-18：
                                       #   140/155mm 副炮弹=陆军口径，单发毁伤效率高于巨炮弹）
    bombard_tons = 0.0                 # 投射弹重（吨，参考指标）
    bombard_by_ship: dict = {}
    airfield_rounds = 0                # 70% 打机场
    line_rounds = 0                    # 30% 打美军防线
    BOMB_RATE_HR = 90.0                # 持续岸轰射速（发/门/小时，60min 窗口，保守值）
    for s in jp:
        if s.dead or s.withdrawn:      # 沉没/脱离去后方者无法岸轰
            continue
        r = 0
        tons = 0.0
        fill = 0.0
        # (a) 主炮对陆弹：只有带 HE/三式的舰才记账；AP 延迟引信对陆=钻土，
        #     不计入有效岸轰（本编制全 AP ⇒ 通常为 0）
        rm = rng.randint(20, 45) if s.shell != "AP" else 0
        rm = min(rm, s.ammo_main)
        s.ammo_main -= rm
        r += rm
        if rm:
            kg = 1360.0 if (s.cls == "BB" and s.guns >= 9) else 625.0
            tons += rm * kg / 1000.0
            fill += rm * kg * 0.10     # 大口径对陆有效装药占比≈10%（钻土损耗后）
        # (b) 副炮：独立弹药库，与主炮是否打干无关（用户 2026-09-18 指出）；
        #     140/155mm 弹=陆军支援口径，是岸轰/协同陆军的主力（用户二补）
        if s.sec_guns > 0:
            cap = int(s.sec_guns * BOMB_RATE_HR * (60.0 / 60.0))
            rs = int(min(s.ammo_sec, cap) * max(0.0, 1.0 - s.struct))  # 按结构剩余率折减
            s.ammo_sec -= rs
            r += rs
            tons += rs * s.sec_kg / 1000.0
            fill += rs * s.sec_kg * 0.12   # 中口径弹装药占比≈12%
            bombard_sec_rounds += rs
        bombard_rounds += r
        bombard_tons += tons
        bombard_fill_kg += fill
        bombard_by_ship[s.name] = r
        # 按 70/30 分配（按用户时间轴：70% 机场 / 30% 防线）
        af = int(round(r * 0.70))
        airfield_rounds += af
        line_rounds += r - af

    # ---------- 判定（只报状态量，不作道德判断/预设结论）----------
    def frac(side):
        tot = 0.0
        for s in side:
            if s.dead:
                continue
            tot += (1.0 - s.struct) * (1 - 0.5 * s.flood) * (1 - 0.4 * s.fire)
        return tot / max(1, len(side))

    jp_frac, us_frac = frac(jp), frac(us)
    us_dead = sum(1 for s in us if s.dead)
    jp_dead = sum(1 for s in jp if s.dead)

    us_bb_state = {
        s.name: {
            "dead": s.dead,
            "struct_loss": round(s.struct, 3),
            "guns_ok": round(s.gun_availability(), 3),
            "firecontrol_loss": round(s.firecontrol, 3),
            "steering_loss": round(s.steering, 3),
            "torpedo_hits": s.torpedo_hits_taken,
        } for s in us if s.cls == "BB"
    }
    jp_bb_state = {
        s.name: {
            "dead": s.dead,
            "struct_loss": round(s.struct, 3),
            "guns_ok": round(s.gun_availability(), 3),
            "firecontrol_loss": round(s.firecontrol, 3),
            "steering_loss": round(s.steering, 3),
            "torpedo_hits": s.torpedo_hits_taken,
        } for s in jp if s.cls == "BB"
    }
    jp_he_rounds = bombard_rounds      # 对陆弹总消耗（岸轰，不落逐发记录）

    return {
        "jp_frac": jp_frac,
        "us_frac": us_frac,
        "jp_loss": 1 - jp_frac,
        "us_loss": 1 - us_frac,
        "jp_sunk": jp_dead,
        "us_sunk": us_dead,
        "us_bb_state": us_bb_state,
        "jp_bb_state": jp_bb_state,
        "jp_he_rounds": jp_he_rounds,
        "bombard_by_ship": bombard_by_ship,
        "bombard_airfield": airfield_rounds,
        "bombard_line": line_rounds,
        "bombard_sec_rounds": bombard_sec_rounds,
        "bombard_tons": bombard_tons,
        "bombard_fill_kg": bombard_fill_kg,
        "yamato_fired": yamato_fired,
        "n_shots": len(shots),
        "n_hits": sum(1 for s in shots if s.hit),
        # ---- 分口径统计 ----
        "n_gun_shots": sum(1 for s in shots if "鱼雷" not in s.shell),
        "n_gun_hits": sum(1 for s in shots if s.hit and "鱼雷" not in s.shell),
        "n_torp_shots": sum(1 for s in shots if "鱼雷" in s.shell),
        "n_torp_hits": sum(1 for s in shots if s.hit and "鱼雷" in s.shell),
        "_shots": shots,
        "_us": us, "_jp": jp,
        "_snapshots": snapshots,
    }


# ============================================================
# 8. 主流程
# ============================================================
def run_sim(scenario: str, n: int, seed: int = 42, shots_csv: Optional[str] = None):
    cfg = SCENARIOS[scenario]
    rng = random.Random(seed)
    results = [run_once(cfg, rng) for _ in range(n)]

    k = lambda key: [r[key] for r in results]

    # 汇总
    out = {
        "scenario": scenario, "n": n,
        # 相对战力（0-1, 1=完好）
        "jp_loss_mean": st.mean(k("jp_loss")),
        "us_loss_mean": st.mean(k("us_loss")),
        # 沉没数
        "jp_sunk_mean": st.mean(k("jp_sunk")),
        "us_sunk_mean": st.mean(k("us_sunk")),
        "jp_sunk_p50": st.median(k("jp_sunk")),
        "us_sunk_p50": st.median(k("us_sunk")),
        "jp_sunk_p90": st.quantiles(k("jp_sunk"), n=10)[8] if n >= 10 else st.mean(k("jp_sunk")),
        "us_sunk_p90": st.quantiles(k("us_sunk"), n=10)[8] if n >= 10 else st.mean(k("us_sunk")),
        "jp_sunk_max": max(k("jp_sunk")),
        "us_sunk_max": max(k("us_sunk")),
        # 状态量
        "yamato_rate": sum(r["yamato_fired"] for r in results) / n,
        "jp_he_rounds_mean": st.mean(k("jp_he_rounds")),
        "bombard_sec_rounds_mean": st.mean(k("bombard_sec_rounds")),
        "bombard_tons_mean": st.mean(k("bombard_tons")),
        "bombard_fill_kg_mean": st.mean(k("bombard_fill_kg")),
        "avg_total_shots": st.mean(k("n_shots")),
        "avg_total_hits": st.mean(k("n_hits")),
        "overall_hit_rate": sum(r["n_hits"] for r in results) / max(1, sum(r["n_shots"] for r in results)),
        # 分口径命中率
        "gun_shots_mean": st.mean(k("n_gun_shots")),
        "gun_hits_mean": st.mean(k("n_gun_hits")),
        "gun_hit_rate": (sum(r["n_gun_hits"] for r in results)
                         / max(1, sum(r["n_gun_shots"] for r in results))),
        "torp_shots_mean": st.mean(k("n_torp_shots")),
        "torp_hits_mean": st.mean(k("n_torp_hits")),
        "torp_hit_rate": (sum(r["n_torp_hits"] for r in results)
                          / max(1, sum(r["n_torp_shots"] for r in results))),
        # 分布（供外部核验）
        "jp_sunk_hist": {str(i): sum(1 for r in results if r["jp_sunk"] == i)
                         for i in sorted(set(k("jp_sunk")))},
        "us_sunk_hist": {str(i): sum(1 for r in results if r["us_sunk"] == i)
                         for i in sorted(set(k("us_sunk")))},
        # 美舰单舰状态均值
        "us_bb_state_mean": {},
    }

    # 美舰单舰状态均值
    bb_names = set()
    for r in results:
        bb_names.update(r["us_bb_state"].keys())
    for nm in sorted(bb_names):
        vals = [r["us_bb_state"][nm] for r in results if nm in r["us_bb_state"]]
        if not vals:
            continue
        out["us_bb_state_mean"][nm] = {
            "dead_rate": round(sum(v["dead"] for v in vals) / len(vals), 4),
            "struct_loss_mean": round(st.mean(v["struct_loss"] for v in vals), 4),
            "guns_ok_mean": round(st.mean(v["guns_ok"] for v in vals), 4),
            "firecontrol_loss_mean": round(st.mean(v["firecontrol_loss"] for v in vals), 4),
            "steering_loss_mean": round(st.mean(v["steering_loss"] for v in vals), 4),
            "torpedo_hits_mean": round(st.mean(v["torpedo_hits"] for v in vals), 4),
        }

    # ---- 逐舰统计（用户 2026-09-18 要求：每艘船平均中弹）----
    # 只聚合，不触碰 rng —— 全舰队汇总数字与不带本块时完全一致。
    recv = defaultdict(lambda: {"runs": 0, "hits": 0.0, "gun_hits": 0.0,
                                "torp_hits": 0.0, "pen": 0.0,
                                "inflicted": 0.0, "fired": 0.0,
                                "dead": 0.0, "withdrawn": 0.0, "struct": 0.0})
    ship_meta = {}
    for r in results:
        name2side = {}
        for s in r["_jp"]:
            name2side[s.name] = "jp"
        for s in r["_us"]:
            name2side[s.name] = "us"
        for side, s in (("jp", x) for x in r["_jp"]):
            key = f"{side}:{s.name}"
            m = recv[key]
            m["runs"] += 1
            m["dead"] += 1.0 if (s.dead or s.scuttled) else 0.0
            m["withdrawn"] += 1.0 if s.withdrawn else 0.0
            m["struct"] += s.struct_dmg / s.hull_hp
            ship_meta[key] = (side, s.cls)
        for side, s in (("us", x) for x in r["_us"]):
            key = f"{side}:{s.name}"
            m = recv[key]
            m["runs"] += 1
            m["dead"] += 1.0 if (s.dead or s.scuttled) else 0.0
            m["withdrawn"] += 1.0 if s.withdrawn else 0.0
            m["struct"] += s.struct_dmg / s.hull_hp
            ship_meta[key] = (side, s.cls)
        for sh in r["_shots"]:
            if sh.is_bombard:
                continue
            sh_side = name2side.get(sh.shooter)
            if sh_side is not None:
                recv[f"{sh_side}:{sh.shooter}"]["fired"] += 1
            if not sh.hit:
                continue
            tg_side = name2side.get(sh.target)
            if tg_side is not None:
                m = recv[f"{tg_side}:{sh.target}"]
                m["hits"] += 1
                if "鱼雷" in sh.shell:
                    m["torp_hits"] += 1
                else:
                    m["gun_hits"] += 1
                if sh.penetrated:
                    m["pen"] += 1
            if sh_side is not None:
                recv[f"{sh_side}:{sh.shooter}"]["inflicted"] += 1

    per_ship = {"jp": [], "us": []}
    for key, m in recv.items():
        side, cls = ship_meta[key]
        nm = key.split(":", 1)[1]
        per_ship[side].append({
            "name": nm, "cls": cls,
            "hits_recv_mean": round(m["hits"] / m["runs"], 2),
            "gun_hits_mean": round(m["gun_hits"] / m["runs"], 2),
            "torp_hits_mean": round(m["torp_hits"] / m["runs"], 2),
            "pen_mean": round(m["pen"] / m["runs"], 2),
            "hits_inflicted_mean": round(m["inflicted"] / m["runs"], 2),
            "shots_fired_mean": round(m["fired"] / m["runs"], 1),
            "dead_rate": round(m["dead"] / m["runs"], 4),
            "withdrawn_rate": round(m["withdrawn"] / m["runs"], 4),
            "struct_loss_mean": round(m["struct"] / m["runs"], 4),
        })
    for side in per_ship:
        per_ship[side].sort(key=lambda d: -d["hits_recv_mean"])
    out["per_ship"] = per_ship

    # 存"数据表"（流式写入，避免 n 大时 MemoryError）
    if shots_csv:
        n_rows = 0
        with open(shots_csv, "w", newline="", encoding="utf-8-sig") as f:
            w = None
            for i, r in enumerate(results):
                for s in r["_shots"]:
                    d = asdict(s)
                    d["sim"] = i
                    if w is None:
                        w = csv.DictWriter(f, fieldnames=list(d.keys()))
                        w.writeheader()
                    w.writerow(d)
                    n_rows += 1
        out["shots_csv"] = shots_csv
        out["shots_rows"] = n_rows

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--scenario", default="gambler", choices=list(SCENARIOS))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--shots-csv", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    res = run_sim(a.scenario, a.n, a.seed, a.shots_csv)
    if a.json:
        print(json.dumps({kk: vv for kk, vv in res.items() if kk != "_shots"},
                         ensure_ascii=False, indent=2))
        return

    print(f"=== MC+FEM 模拟 | {a.scenario} | n={a.n} | seed={a.seed} ===")
    print(f"交战距离          {SCENARIOS[a.scenario]['engage_range']} kyd")
    print()
    print(f"【日军损失(相对战力)】{res['jp_loss_mean']*100:7.1f}%")
    print(f"【美军损失(相对战力)】{res['us_loss_mean']*100:7.1f}%")
    print(f"【日军沉没(均值/中位/最大)】 {res['jp_sunk_mean']:5.2f} / {res['jp_sunk_p50']:.0f} / {res['jp_sunk_max']}")
    print(f"【美军沉没(均值/中位/最大)】 {res['us_sunk_mean']:5.2f} / {res['us_sunk_p50']:.0f} / {res['us_sunk_max']}")
    print(f"【大和参战率】      {res['yamato_rate']*100:6.1f}%")
    print(f"【日方对陆弹投射】  {res['jp_he_rounds_mean']:8.1f} 发/次")
    print()
    print(f"【平均发弹数】      {res['avg_total_shots']:8.1f}  (含岸轰 {res['jp_he_rounds_mean']:.0f})")
    print(f"【平均命中数】      {res['avg_total_hits']:8.1f}")
    print(f"【炮术】  发弹 {res['gun_shots_mean']:7.1f}  命中 {res['gun_hits_mean']:6.1f}"
          f"  命中率 {res['gun_hit_rate']*100:6.3f}%")
    print(f"【鱼雷】  发射 {res['torp_shots_mean']:7.1f}  命中 {res['torp_hits_mean']:6.1f}"
          f"  命中率 {res['torp_hit_rate']*100:6.3f}%")
    print()
    print("【美舰状态均值】")
    for nm, v in res["us_bb_state_mean"].items():
        print(f"  {nm:<8} 沉没率 {v['dead_rate']*100:5.1f}% | 结构损失 {v['struct_loss_mean']*100:5.1f}%"
              f" | 主炮可用 {v['guns_ok_mean']*100:5.1f}% | 火控损失 {v['firecontrol_loss_mean']*100:5.1f}%"
              f" | 舵机损失 {v['steering_loss_mean']*100:5.1f}% | 中雷 {v['torpedo_hits_mean']:.2f}")
    if res.get("shots_csv"):
        print(f"\n数据表已存: {res['shots_csv']}  ({res['shots_rows']} 行)")


if __name__ == "__main__":
    main()
