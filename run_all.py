# -*- coding: utf-8 -*-
"""
run_all.py — 一键运行三大 FEM 模块（海战 / 鱼雷机轰炸 / 空战）
=============================================================
Run all three core finite-element (Monte Carlo) models in sequence and
print their self-reports. Zero third-party dependencies.

Usage:
    python run_all.py
"""
import subprocess
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")

# (label shown to user, module filename under src/)
MODULES = [
    ("海战 · 舰炮命中率 (gunnery_fem)", "gunnery_fem.py"),
    ("鱼雷机轰炸 · 飞机投雷 (aerial_torpedo_fem)", "aerial_torpedo_fem.py"),
    ("空战 · dogfight 能量/回转机动 (aircraft_dogfight_fem)", "aircraft_dogfight_fem.py"),
]


def main():
    for i, (label, fname) in enumerate(MODULES, 1):
        print("\n" + "=" * 78)
        print(f"  {i}/{len(MODULES)}  {label}")
        print("=" * 78)
        cmd = [sys.executable, os.path.join(SRC, fname)]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"  [!] {fname} exited with code {e.returncode}")
            sys.exit(e.returncode)
    print("\n" + "=" * 78)
    print("  全部三大模块运行完毕。各模块标准输出亦见 results/ 与 cases/*/run_output.txt")
    print("=" * 78)


if __name__ == "__main__":
    main()
