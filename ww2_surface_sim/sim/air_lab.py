# -*- coding: utf-8 -*-
"""
air_lab.py · 航空战实验室（可独立加载子模块）
==============================================
两种模式：
  A 空战 dogfight —— 战斗机质量代差（零战二一 / 金星零战(fork) / F4F / F6F）
  B 对舰攻击 attack —— CAP 拦截 → 防空火力 → 幸存攻击机命中

校准锚点：
  · 《瓜岛推演稿》：干净底俯冲投弹 900m 命中率≈96% 属贴脸口径；
    本实验室 p_hit=0.30 为通用中距标称
  · 中途岛美军 SBD 对机动日航母实战命中 10-20%
  · 金星零战 = 用户 fork 设定（瓜岛胜利后金星发动机换装+练度未损，1943）
公式（主代理定死）：
  空战每轮损失率 = 0.055 * 敌方atk / 我方def，共 6 轮，逐轮 ×uniform(0.5,1.5)
  对舰攻击：拦截损失率 = min(0.9, 0.06*cap_n*atk)；
            防空每机被击落 p = 0.04*aa_level；
            每架幸存攻击机命中 p = 0.30 * size(target)
"""
import random

FIGHTERS = {
    "零战二一型(1942)":      {"atk": 1.00, "def": 0.70},
    "金星零战(fork,1943)":   {"atk": 1.25, "def": 0.80},
    "F4F野猫(1942)":         {"atk": 0.90, "def": 1.10},
    "F6F地狱猫(1943+)":      {"atk": 1.20, "def": 1.50},
}
TSIZE = {"DD": 0.75, "CL": 0.95, "CA": 1.10, "CV": 1.35}
TRIALS = 1000

PARAMS = [
    {"key": "mode", "label": "模式", "kind": "option", "values": ["空战", "对舰攻击"]},
    {"key": "jp_n", "label": "日方战斗机数", "kind": "spin", "from": 1, "to": 200, "init": 40},
    {"key": "jp_f", "label": "日方机型", "kind": "option", "values": list(FIGHTERS)},
    {"key": "us_n", "label": "美方战斗机数", "kind": "spin", "from": 1, "to": 200, "init": 40},
    {"key": "us_f", "label": "美方机型", "kind": "option", "values": list(FIGHTERS)},
    {"key": "bombers", "label": "攻击机数(对舰)", "kind": "spin", "from": 1, "to": 100, "init": 20},
    {"key": "cap_n", "label": "守军CAP数(对舰)", "kind": "spin", "from": 0, "to": 100, "init": 24},
    {"key": "cap_f", "label": "CAP机型", "kind": "option", "values": list(FIGHTERS)},
    {"key": "aa_level", "label": "防空等级(0-4)", "kind": "spin", "from": 0, "to": 4, "init": 2},
    {"key": "target", "label": "目标舰种(对舰)", "kind": "option", "values": list(TSIZE)},
]


def _dogfight_report(jp_n, jp_f, us_n, us_f) -> str:
    rng = random.Random(42)
    ja, jd = FIGHTERS[jp_f]["atk"], FIGHTERS[jp_f]["def"]
    ua, ud = FIGHTERS[us_f]["atk"], FIGHTERS[us_f]["def"]
    jp_left, us_left = [], []
    for _ in range(TRIALS):
        j, u = float(jp_n), float(us_n)
        for _r in range(6):
            if j <= 0 or u <= 0:
                break
            j = max(0.0, j - u * (0.055 * ja / ud) * rng.uniform(0.5, 1.5))
            u = max(0.0, u - j * (0.055 * ua / jd) * rng.uniform(0.5, 1.5))
        jp_left.append(j)
        us_left.append(u)
    mj, mu = sum(jp_left) / TRIALS, sum(us_left) / TRIALS
    lj, lu = jp_n - mj, us_n - mu
    ex = (lu / lj) if lj > 0 else float("inf")
    return "\n".join([
        "【航空战·空战】日 %s×%d vs 美 %s×%d（6 轮交换，1000 次试验）" % (jp_f, jp_n, us_f, us_n),
        "  日方：平均剩余 %.1f 架（损失 %.1f）   美方：平均剩余 %.1f 架（损失 %.1f）"
        % (mj, lj, mu, lu),
        "  交换比（美损/日损）= %.2f" % ex,
        "  机型口径：atk=火力/速度档，def=防御档（装甲+结构）。",
    ])


def _attack_report(bombers, cap_n, cap_f, aa_level, target) -> str:
    rng = random.Random(42)
    atk = FIGHTERS[cap_f]["atk"]
    size = TSIZE[target]
    intercept_frac = min(0.9, 0.06 * cap_n * atk)
    p_aa = 0.04 * aa_level
    p_hit = 0.30 * size
    hit_hist = []
    for _ in range(TRIALS):
        alive = 0
        for _b in range(bombers):
            if rng.random() < intercept_frac:
                continue                      # 被 CAP 击落
            if rng.random() < p_aa:
                continue                      # 被防空火力击落
            alive += 1
        hits = sum(1 for _ in range(alive) if rng.random() < p_hit)
        hit_hist.append(hits)
    hit_hist.sort()
    mean_hits = sum(hit_hist) / TRIALS
    at_least_1 = sum(1 for h in hit_hist if h >= 1) / TRIALS
    exp_intercept = bombers * intercept_frac
    exp_aa = (bombers - exp_intercept) * p_aa
    return "\n".join([
        "【航空战·对舰攻击】攻击机×%d → CAP(%s×%d) + 防空L%d → %s"
        % (bombers, cap_f, cap_n, aa_level, target),
        "  CAP 拦截：期望击落 %.1f 架（%.0f%%）；防空：期望击落 %.1f 架"
        % (exp_intercept, intercept_frac * 100, exp_aa),
        "  幸存攻击机每架命中 p=%.1f%%；1000 次试验：期望命中 %.2f | 中位 %d | 最大 %d"
        % (p_hit * 100, mean_hits, hit_hist[TRIALS // 2], hit_hist[-1]),
        "  至少一命中概率 = %.1f%%" % (at_least_1 * 100),
        "  锚点：干净底投弹 900m≈96% 属贴脸口径；中途岛 SBD 实战对机动目标 10-20%。",
    ])


def run(params) -> str:
    if params["mode"] == "空战":
        return _dogfight_report(int(params["jp_n"]), params["jp_f"],
                                int(params["us_n"]), params["us_f"])
    return _attack_report(int(params["bombers"]), int(params["cap_n"]),
                          params["cap_f"], int(params["aa_level"]), params["target"])


def interactive():
    print("=== 航空战实验室（q 退出） ===")
    fnames = list(FIGHTERS)
    while True:
        try:
            s = input("模式(空战/对舰攻击) 回车进入分菜单 > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if s.lower() in ("q", "quit", "exit"):
            break
        try:
            if s == "空战":
                jn = int(input("日方架数 [40] > ") or 40)
                jf = input("日方机型(%s) [0] > " % "|".join(fnames) or "0")
                jf = fnames[int(jf)] if jf.isdigit() else (jf if jf in FIGHTERS else fnames[0])
                un = int(input("美方架数 [40] > ") or 40)
                uf = input("美方机型 [3] > ") or "3"
                uf = fnames[int(uf)] if uf.isdigit() else (uf if uf in FIGHTERS else fnames[3])
                print(_dogfight_report(jn, jf, un, uf))
            else:
                b = int(input("攻击机数 [20] > ") or 20)
                cn = int(input("守军CAP数 [24] > ") or 24)
                cf = input("CAP机型 [1] > ") or "1"
                cf = fnames[int(cf)] if cf.isdigit() else (cf if cf in FIGHTERS else fnames[1])
                aa = int(input("防空等级0-4 [2] > ") or 2)
                tg = input("目标舰种(CV/CA/CL/DD) [CV] > ") or "CV"
                print(_attack_report(b, cn, cf, aa, tg))
        except Exception as e:
            print("输入无效:", e)


if __name__ == "__main__":
    interactive()
