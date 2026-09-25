# -*- coding: utf-8 -*-
"""
model.py · 数据模型（OOB / 武器 / 传感器 / 场景）
================================================
全部用 dataclass，数据驱动。框架独立可跑；接入 GitHub 仓库的 FEM 时，
Weapon.reliability / caliber 等字段直接喂给 gunnery_fem / torpedo_fem。

设计铁律（沿用 ww2-naval-battle-compute）：
  - 仅标准库（dataclass 属标准库）
  - 所有随机性走 engine.rng（固定 seed 可复现）
  - 参数集中在场景文件，可审计、可改写
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Tuple


# 舰型半长/半宽（米）—— 命中判定用，来自 gunnery_fem.SHIP
SHIP_HALF = {"BB": (110.0, 16.0), "CA": (90.0, 10.0),
             "CL": (70.0, 8.0), "DD": (50.0, 4.0), "CV": (130.0, 18.0)}

# 口径伤害因子（来自"不疯的山本"案修正 #3）：8in=1.0 / 5in=0.40 / 18in=2.8
CALIBER_FACTOR = {5: 0.40, 6: 0.55, 8: 1.0, 12.7: 1.6, 14: 1.7,
                  16: 2.2, 18: 2.8, 35.6: 2.4, 46: 3.0}


@dataclass
class Sensor:
    kind: str            # radar / optical / sonar / esm
    band: str = "medium" # low / medium / high（雷达视距表档）
    active_range_nm: float = 30.0
    passive: bool = False
    reliability: float = 0.9   # WWII 不稳定：光学夜战可低至 0.3，早期雷达 0.7


@dataclass
class Weapon:
    name: str
    kind: str            # gun / torpedo / bomb
    caliber: float = 0.0     # 火炮口径（英寸）；鱼雷/炸弹填 0
    range_m: float = 0.0
    rate_per_min: float = 0.0
    reliability: float = 1.0  # 武器质量浮动：九三式≈0.80，Mk-15≈0.07
    disp_factor: float = 0.10 # 散布批差（ powders/lot variance）
    p_k: float = 0.10         # 基础单发击杀概率（兜底）


@dataclass
class Unit:
    name: str
    side: str            # JP / US
    cls: str             # BB / CA / CL / DD / CV / AF(机场：固定不动，hp=完好度%)
    hp: float = 100.0
    speed_kt: float = 18.0
    sensors: List[Sensor] = field(default_factory=list)
    weapons: List[Weapon] = field(default_factory=list)
    ammo: Dict[str, int] = field(default_factory=dict)
    # —— 交战状态（每 tick 由 engine 更新）——
    pos: Tuple[float, float] = (0.0, 0.0)
    alive: bool = True
    withdrawing: bool = False   # 指挥官专业撤离（有序，可重整）
    routed: bool = False        # 士气崩溃→溃散（不可控，脱离战场，不可重整）
    fire_control: float = 1.0   # 0-1 火控解算质量（受士气/摩擦调制）
    morale: float = 1.0         # 0-1 心态稳定度
    flooding: float = 0.0       # 0-1 进水
    turrets_ok: int = 0
    contact_s: float = 0.0      # 与本方交战目标的累计接触秒数

    @property
    def status(self) -> str:
        """交战状态：destroyed 沉没 / routed 溃散 / withdrawing 专业撤离 / engaged 接战。"""
        if not self.alive:
            return "destroyed"
        if self.routed:
            return "routed"
        if self.withdrawing:
            return "withdrawing"
        return "engaged"

    def caliber_factor(self) -> float:
        guns = [w for w in self.weapons if w.kind == "gun"]
        if not guns:
            return 1.0
        c = max(g.caliber for g in guns)
        return CALIBER_FACTOR.get(round(c), 1.0)


@dataclass
class Side:
    name: str
    units: List[Unit] = field(default_factory=list)
    doctrine: str = "default"   # bb_line / cv_first / surface ...
    c2_penalty: float = 0.0     # 指挥控制/官僚主义惩罚(0-1)：降低本方探测与火控质量。
                                # 仅作可调旋钮（历史 IJN C2 失误的抽象），默认关闭。
    reinforcements: List["Reinforcement"] = field(default_factory=list)  # 战役层增援（按 tick 整批抵达）


@dataclass
class Rules:
    """对称约束（双方共同有效）—— 严肃海上模拟的结局偏向平局/双方惨败的旋钮。
    全部可调，非硬编码；默认值即"双方同规则"。"""
    rout_threshold: float = 0.15               # 士气低于此 → 溃散（不可控）
    commander_withdraw_cap_loss: float = 0.50  # 主力舰损失过半 → 指挥官下令撤离
    commander_withdraw_pow_ratio: float = 0.60 # 战力比低于此 → 指挥官下令撤离
    symmetric: bool = True                     # 双方同规则（溃散/撤离/结局对称）


@dataclass
class Reinforcement:
    """战役层增援：到 arrive_tick 时整批加入本方（引擎在 step 起始检测）。"""
    arrive_tick: int
    units: List[Unit] = field(default_factory=list)
    label: str = ""


@dataclass
class Scenario:
    name: str
    mission: str                # surface / carrier / based_aviation
    sides: List[Side] = field(default_factory=list)
    rules: Rules = field(default_factory=Rules)
    objective: str = "annihilate"  # annihilate / hold_airfield / breakthrough（战役层战略判定）
    seed: int = 42
    night: bool = True
    weather: float = 0.0        # 0-1
