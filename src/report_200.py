# -*- coding: utf-8 -*-
"""
瓜岛夜战 · 200 次蒙特卡洛 · 双方成败数字与逐舰下场报告
=========================================================
命令（可复现，铁律 #16）：
  python mc_fem.py 的 run_sim(scenario, n=200, seed=42)
  版本：mc_fem.py（含 torpedo_fem 标定 + _speed_gun_factor 接入 + SPEED_KT 去重）
  日期：2026-09-24

说明：
  · gambler   = 用户的 fork 决战模型（4 旧 BB + 大和 + 照明弹，即"把老舰押上 + 多带照明弹"）
  · historical = 史实瓜岛夜战（比睿/雾岛 vs 华盛顿/南达科他，无大和）
  · 驱逐舰不列真名，统一用代号 JP-Dx / US-Dx。
"""
import json
from mc_fem import run_sim, SCENARIOS

N = 200
SEED = 42


def code_name(side, name, cls):
    """驱逐舰→代号；主力舰保留代号(已是日文舰名)。"""
    if cls == "DD":
        prefix = "JP-D" if side == "jp" else "US-D"
        # 名称形如 "日驱3" / "美驱2"
        digits = "".join(ch for ch in name if ch.isdigit())
        return f"{prefix}{digits}"
    return name


def fate_label(d):
    """根据 dead_rate / withdrawn_rate / struct_loss 给一句定性下场。"""
    dr = d["dead_rate"]
    wr = d["withdrawn_rate"]
    sl = d["struct_loss_mean"]
    if dr >= 0.5:
        return f"大概率沉没（P={dr*100:.0f}%）"
    if dr >= 0.2:
        return f"约 {dr*100:.0f}% 沉没，余下多重伤退出"
    if wr >= 0.5 or sl >= 0.6:
        return "重创退出战线（少沉多残）"
    if sl >= 0.3:
        return "中度受损、可续战但战力打折"
    return "基本完好 / 轻伤"


def run(scenario):
    return run_sim(scenario, N, SEED)


def agg_line(res, side):
    loss = res[f"{side}_loss_mean"]
    sunk = res[f"{side}_sunk_mean"]
    sunk_p50 = res[f"{side}_sunk_p50"]
    sunk_max = res[f"{side}_sunk_max"]
    return (f"相对战力损失 {loss*100:5.1f}% | 沉没 均值 {sunk:4.2f} / "
            f"中位 {sunk_p50:.0f} / 最大 {sunk_max}")


def main():
    print("# 瓜岛夜战 · 200 次蒙特卡洛决定性报告（2026-09-24）\n")
    print(f"模型版本：mc_fem.py（torpedo_fem 标定 + 航速炮击因子接入 + SPEED_KT 去重）")
    print(f"运行：n={N}, seed={SEED}, 交战序列遵循用户时间轴（肖特兰出航→照明弹→"
          f"三川诱饵→战列进入→93式齐射→Mk-15反击→炮战→大和支援→岸轰）\n")

    for scen in ["gambler", "historical"]:
        res = run(scen)
        print("=" * 74)
        tag = "【fork 决战模型】4旧BB+大和+照明弹" if scen == "gambler" \
              else "【史实瓜岛夜战】比睿/雾岛 vs 华盛顿/南达科他"
        print(f"场景：{tag}  （engage_range = {SCENARIOS[scen]['engage_range']} kyd）")
        print("-" * 74)
        print(f"  日军：{agg_line(res, 'jp')}")
        print(f"  美军：{agg_line(res, 'us')}")
        print(f"  炮术命中率 {res['gun_hit_rate']*100:5.3f}%  |  "
              f"鱼雷命中率 {res['torp_hit_rate']*100:5.3f}%  |  "
              f"综合命中率 {res['overall_hit_rate']*100:5.3f}%")
        print(f"  大和参战率 {res['yamato_rate']*100:4.1f}%  |  "
              f"日方对陆弹投射 {res['jp_he_rounds_mean']:.0f} 发/次")
        print()
        print("  逐舰大概率下场（驱逐舰用代号）：")
        for side in ["jp", "us"]:
            label = "日" if side == "jp" else "美"
            print(f"    —— {label}方 ——")
            rows = res["per_ship"][side]
            rows_sorted = sorted(rows, key=lambda d: -d["dead_rate"])
            for d in rows_sorted:
                nm = code_name(side, d["name"], d["cls"])
                cls = {"BB": "战列", "CA": "重巡", "CL": "轻巡", "DD": "驱逐"}[d["cls"]]
                fate = fate_label(d)
                print(f"      {nm:<8}({cls}) 沉没{d['dead_rate']*100:5.1f}%  "
                      f"退出{d['withdrawn_rate']*100:5.1f}%  "
                      f"结构损{d['struct_loss_mean']*100:5.1f}%  "
                      f"中弹{d['hits_recv_mean']:4.1f}(炮{d['gun_hits_mean']:3.1f}/雷{d['torp_hits_mean']:3.1f})"
                      f"  → {fate}")
        print()

    # 关键对照：fork vs 史实，谁赢得"真空期"
    print("=" * 74)
    print("结论速览：")
    g = run_sim("gambler", N, SEED)
    h = run_sim("historical", N, SEED)
    print(f"  fork 模型：日军损失 {g['jp_loss_mean']*100:.1f}% / 美军 {g['us_loss_mean']*100:.1f}%"
          f" → 美军沉没均值 {g['us_sunk_mean']:.2f}")
    print(f"  史实模型：日军损失 {h['jp_loss_mean']*100:.1f}% / 美军 {h['us_loss_mean']*100:.1f}%"
          f" → 美军沉没均值 {h['us_sunk_mean']:.2f}")
    print("  差异来自：① 4 旧 BB 提供的炮管数量（补偿光学夜战低命中率）；")
    print("            ② 照明弹直接打击'无光源→命中归零'这一首要干扰因子；")
    print("            ③ 大和 30 分钟主炮支援（仅 fork）。")


if __name__ == "__main__":
    main()
