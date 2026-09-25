# -*- coding: utf-8 -*-
"""
main.py · 入口
====================
  GUI 模式    :  cd ww2_surface_sim && python main.py
  无头模式    :  python main.py --headless --scenario 瓜岛 --ticks 20
  命令行交互  :  python main.py --cli --scenario 塔拉瓦
  （无头加 --report 可打印每 tick 五段报告）

无头 / CLI 模式便于 CI、可复现校验与"命令行可玩"（无需显示器、无需 tkinter）。
"""
import argparse
from sim.engine import Engine
from sim import scenarios as SC
from sim.intros import INTROS, scenario_settings_text

LABS = {"gunnery": "炮战实验室", "torpedo": "鱼雷对决", "air": "航空战"}

# 场景英文别名（便于命令行 / .bat 传参，规避中文编码乱码）
_ALIAS = {"guadao": "瓜岛", "g": "瓜岛",
          "midway": "中途岛", "m": "中途岛",
          "tarawa": "塔拉瓦", "t": "塔拉瓦"}


def _resolve(name):
    """把英文别名映射到中文 REGISTRY 键；已是中文则原样返回。"""
    if name is None:
        return name
    return _ALIAS.get(name.strip().lower(), name)


def _tally(sc, snap):
    jp_dead = sum(1 for u in sc.sides[0].units if not u.alive)
    us_dead = sum(1 for u in sc.sides[1].units if not u.alive)
    flag = "  [战斗结束]" if snap.get("over") else ""
    return (f"T+{snap['time_s']:>5}s  日沉 {jp_dead:>2}  美沉 {us_dead:>2}  "
            f"接触 {snap['contacts']:>2}  outcome={snap.get('outcome')}{flag}")


def headless(name="瓜岛", ticks=60, seed=42, report=False):
    name = _resolve(name)
    sc = SC.REGISTRY[name]()
    eng = Engine(sc, seed=seed, step_sec=30)
    print(f"=== {sc.name} · 无头推演 seed={seed} step={eng.step_sec}s ===")
    print(INTROS.get(name, "").splitlines()[0] if INTROS.get(name) else "",
          "（完整背景见 CLI 模式或 GUI「背景」按钮）")
    for _ in range(ticks):
        snap = eng.step()
        if report:
            print(snap["report"])
        print(_tally(sc, snap))
        if snap["over"]:
            break
    print("战术结局:", eng.outcome(), "| 战役判定:", eng.campaign_result())
    return eng


def _print_status(sc):
    for side in sc.sides:
        print(f"--- {side.name} ---")
        for u in side.units:
            print(f"  {u.name:<18} {u.cls:<3} hp={u.hp:5.1f} "
                  f"mor={u.morale:4.2f} [{u.status}]")


def _print_airfields(sc):
    any_af = False
    for side in sc.sides:
        for u in side.units:
            if u.cls == "AF":
                any_af = True
                state = "失能" if not u.alive else ("受损" if u.hp < 30 else "完好")
                print(f"  {side.name} {u.name:<14} 完好度 {u.hp:5.1f}%  [{state}]")
    if not any_af:
        print("  (本场景无机场单位)")


def cli(name="瓜岛", seed=42):
    name = _resolve(name)
    sc = SC.REGISTRY[name]()
    eng = Engine(sc, seed=seed, step_sec=30)
    print("=" * 64)
    print(f"二战水面战 · 命令行推演  [{sc.name}]")
    print(f"mission={sc.mission}  objective={sc.objective}")
    jp_n = len(sc.sides[0].units)
    us_n = len(sc.sides[1].units)
    jp_r = sum(len(s.reinforcements) for s in sc.sides if s.name == "JP")
    us_r = sum(len(s.reinforcements) for s in sc.sides if s.name == "US")
    print(f"日方初始 {jp_n} 单位 | 美方初始 {us_n} 单位 | "
          f"增援波次 JP {jp_r} / US {us_r}")
    print("命令: step | run N | status | airfields | settings | outcome | quit")
    print("=" * 64)
    intro = INTROS.get(name, "")
    if intro:
        print(intro)
        print("=" * 64)
    while True:
        try:
            cmd = input("推演> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[退出]")
            break
        if cmd in ("quit", "q", "exit"):
            break
        elif cmd == "step":
            snap = eng.step()
            print(snap["report"])
            print(_tally(sc, snap))
        elif cmd.startswith("run"):
            parts = cmd.split()
            n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
            last = None
            for _ in range(n):
                last = eng.step()
                print(_tally(sc, last))
                if last["over"]:
                    break
            if last is not None:
                print("-- 末 tick 阶段报告 --")
                print(last["report"])
        elif cmd == "status":
            _print_status(sc)
        elif cmd == "airfields":
            _print_airfields(sc)
        elif cmd == "outcome":
            print("战术结局:", eng.outcome())
            print("战役判定:", eng.campaign_result())
        elif cmd == "settings":
            print(scenario_settings_text(sc))
        else:
            print("未知命令。可用: step / run N / status / airfields / settings / outcome / quit")
    return eng


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--cli", action="store_true", help="命令行交互推演")
    ap.add_argument("--scenario", default="瓜岛")
    ap.add_argument("--ticks", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--report", action="store_true", help="无头模式打印每 tick 五段报告")
    ap.add_argument("--smoke", action="store_true",
                    help="GUI 自检：窗口自动开-关（验证打包运行时）")
    ap.add_argument("--lab", choices=list(LABS),
                    help="实验室子模块：gunnery=炮战 / torpedo=鱼雷对决 / air=航空战")
    args = ap.parse_args()
    if args.lab:
        import importlib
        lab = importlib.import_module(f"sim.{args.lab}_lab")
        lab.interactive()
    elif args.cli:
        cli(args.scenario, args.seed)
    elif args.headless:
        headless(args.scenario, args.ticks, args.seed, args.report)
    else:
        from gui.app import main
        main(smoke=args.smoke)
