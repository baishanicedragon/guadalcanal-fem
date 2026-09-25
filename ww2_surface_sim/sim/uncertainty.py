# -*- coding: utf-8 -*-
"""
uncertainty.py · 二战专属「多维耦合不确定性」模型
================================================
这是本框架与鱼叉（现代 C4ISRK 稳定链）的根本区别，也是用户反复强调的点：
二战海战的噪声不是单一"散布系数"，而是 **4 个相互耦合的维度同时抖动**：

  1) 探测不稳定  detection instability   —— 传感器原始、夜战/天气、无相干 C4ISR
  2) 心态/态势不稳定 morale instability  —— 指挥混乱、怯战/狂热、OODA 抖动
  3) 武器质量浮动 weapon lot variance     —— Mk-15 引信灾难、九三式可靠、火药批差
  4) 炮弹散步 shell dispersion            —— 基础弹道散布（被上面放大）

关键点：这些维度**不是独立乘系数**，而是共享一个"战场的迷雾与摩擦"潜变量，
彼此相关：探测越差 → 火控解算越短越糙 → 命中越差；士气越低 → OODA 越慢、越早撤。
所以每 tick 先采一个 Friction 状态，再让它驱动下游所有阶段。

全部走传入的 rng（固定 seed 可复现）。
"""
import random
import math


class Friction:
    """每 tick 采样的战场摩擦状态（共享潜变量，保证各维度相关）。"""

    def __init__(self, rng: random.Random, night: bool = True, weather: float = 0.0):
        self.night = night
        self.weather = weather
        # 共享潜变量 fog ∈ [0,1]：越大越糟（迷雾越浓、指挥越乱）
        self.fog = min(1.0, max(0.0, rng.gauss(0.5 if night else 0.2, 0.18)))
        # 通讯/指挥可靠性：被 fog 拉低
        self.comms = min(1.0, max(0.05, rng.gauss(0.85, 0.12) - 0.3 * self.fog))
        # 探测能见度：夜战/天气/迷雾三重惩罚
        mean_vis = (0.25 if night else 0.9) - 0.3 * weather - 0.2 * self.fog
        self.visibility = min(1.0, max(0.03, rng.gauss(mean_vis, 0.12)))


def detection_modifier(sensor: "object", fr: Friction, rng: random.Random) -> float:
    """探测不稳定：在干净视距上叠加夜战/天气/通讯/传感器可靠性的噪声。"""
    if sensor.kind == "optical":
        vis = 0.35 + 0.65 * fr.visibility          # 光学夜战极不稳
    else:  # radar / sonar / esm
        vis = 0.70 + 0.30 * fr.visibility          # 早期雷达也受干扰
    rel = max(0.1, rng.gauss(sensor.reliability, 0.15))
    return max(0.05, vis * (0.5 + 0.5 * fr.comms) * rel)


def morale_step(unit, fr: Friction, rng: random.Random) -> float:
    """心态不稳定（每船每 tick 一次）：未交火时士气向高基准回中，而非被迷雾单调打压；
    只有实际交火/损失才会把士气打下去（在 engine 的损伤阶段处理）。"""
    base = 0.80                                  # 高基准：训练有素的舰员
    drift = rng.gauss(0.0, 0.03)
    reversion = 0.10 * (base - unit.morale)      # 向基准回归
    jitter = -0.02 * fr.fog                      # 迷雾只造成轻微抖动
    unit.morale = min(1.0, max(0.0, unit.morale + drift + reversion + jitter))
    return unit.morale


def weapon_lot_factor(weapon, rng: random.Random):
    """武器质量浮动：每条武器按 reliability 伯努利（Mk-15≈0.07 多数哑火）；
    再抽火药批差放大散布。返回 (是否发射成功, 散布乘数)。"""
    fires = rng.random() < weapon.reliability
    disp_mult = max(0.6, rng.gauss(1.0, weapon.disp_factor))
    return fires, disp_mult


def fire_control_modifier(unit, fr: Friction, contact_s: float) -> float:
    """火控解算质量（鱼叉 6.3 的 WWII 抖动版）：
    受士气、通讯、接触时长共同决定；比现代更抖。"""
    morale_q = 0.4 + 0.6 * unit.morale
    comms_q = 0.3 + 0.7 * fr.comms
    maturity = min(1.0, contact_s / 180.0)
    q = 0.5 * morale_q + 0.3 * comms_q + 0.2 * maturity
    return max(0.02, q)
