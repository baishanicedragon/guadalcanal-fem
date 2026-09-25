# -*- coding: utf-8 -*-
"""
intros.py · 三场景战役背景介绍
================================
口径来源（用户文档，金山云文档已核读）：
  瓜岛  ：《瓜岛推演稿-不疯的山本.md》（MC+FEM 反事实推演稿）
  中途岛：《红色联盟-男主中途岛观点概括.txt》+《中途岛正史狭缝与男主推论论证.txt》
  塔拉瓦：GitHub fork 基线（joint_tarawa_wargame.py，1943-11）——
          用户设定："假定瓜岛胜利后的理想日本"的反事实分支
"""

INTROS = {
    "瓜岛": """【瓜岛 · 不疯的山本（反事实推演，1942-10-24 夜）】

史实背景：1942 年 8 月美军登陆瓜达尔卡纳尔，日本陷入"东京特快"运输消耗战——
夜战屡胜（萨沃岛）但亨德森机场始终不瘫痪、运输线被断、舰载机飞行员持续损耗。
消耗战日本拖不起：这是"算定必败"的山本必须速决的原因。

本场景反事实：山本不疯版——放弃添油，把联合舰队主力一次压上：
· 集结在肖特兰（300 海里，一夜往返物理成立；拉包尔 620 海里则不成立）；
· 三川舰队当诱饵承伤、放烟雾把美军引向战列舰部队；
· 美方以为拦截的是 2 艘战列舰，实际是 6 艘（大和/日向/伊势/扶桑/山城/金刚级×2）；
· 九三式长矛鱼雷是决胜手（远距 2.5-3.5%，但仍数倍于炮战命中率）；
· 大和限 30 分钟射击、不追击；随后战列舰岸轰亨德森机场。

模型校准锚点（《瓜岛推演稿》）：持续炮战 0.305% vs 泗水海战史实 0.31%；
奇袭窗口 ×3.0 仅作用最初 2 分钟；Mk-15 磁引信灾难（reliability 0.07）。
1000 次推演结论：日方战力损失 15.3%（几乎全是驱逐舰）、美方 37.2%；
胜负手在鱼雷不在炮；"全歼"是幻觉——美方 20.3% 概率全身而退。

引擎口径：夜战/微雨；JP doctrine=bb_line，US doctrine=surface；
双方 tick=18 对称增援；AF=亨德森(美)/布干维尔(日)。""",

    "中途岛": """【中途岛 · 史实编成（1942-06-04，昼战）】

正史：山本以约三倍兵力发动中途岛，战役目的白纸黑字="占领中途岛，引出美军
主力决战"（诱饵战，正史自己承认）。6 月 4 日晨南云突击部队遭添油式打击，
换弹两难（"决不能摧毁机场"——一木支队登陆后要立即进驻）+ 无雷达→舰载机
不能甲板系留→全收机库 + 每航母仅 6 架 CAP 的条令 + 人力推车加油、加贺号
加油枪忘拔机库布满汽油；麦克拉斯基"惊人转弯"找到日航母，SBD 从容俯冲
引爆机库。赤城/加贺/苍龙/飞龙四舰全灭，美损约克城。

男主读法（《正史狭缝论证》七处狭缝）：正史把"必然"洗成"偶然"——
无雷达/无语音无线电/25mm 机炮散布过大/高炮无雷达指挥全是正史承认的
技术短板，短板+条令+约束=败局必然，无需运气参与；串起珍珠港紫码延误、
山本谢幕等反常，指向"必败者主动求败的自导自演"。

引擎口径：JP doctrine=bait_operation、日航母仅光学传感器（无雷达脆弱性）；
US doctrine=carrier（破译全貌+舰载机收割）；AF=中途岛守军(美)/日岸基航空队。
官僚主义旋钮（GUI 滑杆/JP.c2_penalty）模拟条令混乱对发挥的影响：
0=理想 C2；0.15~0.30≈史实"狭缝"混乱；实测 0.25 可让战局倒转（可调项，非核心）。""",

    "塔拉瓦": """【塔拉瓦 1943 末 · 联合推演 fork（反事实分支，1943-11）】

史实：1943-11 美军中太平洋反攻，吉尔伯特群岛塔拉瓦环礁，贝蒂奥机场
守军死战，美军 TF50 以绝对航空兵力碾压——此时的日本舰队航母残破、
-trained 飞行员已在瓜岛/所罗门消耗殆尽。

本场景反事实（用户设定："假定瓜岛胜利后的理想日本"）：
瓜岛反事实推演里日本赢了（水面胜+机场压制），于是到 1943-11——
· 舰队航母仍完整（翔鹤/瑞鹤/大凤/隼鹰等 9 艘 CV + 伊势日向航空战列化）；
· 飞行员未枯竭：油旁训练无忧、产能无忧、金星零战交付（fork 航空兵 ×1.3）；
· 雷达已上舰（fork 口径：日方同样用雷达，对消美方传感器优势）；
· 大和/武藏健在，日驱 36 艘——正面迎击美军 TF50 可用联队（×0.8）。

数据源：GitHub baishanicedragon/ww2-naval-battle-compute 的
joint_tarawa_wargame.py（fork 1943-11 基线，129 单位）。

引擎口径：mission=land_based_aviation，objective=hold_airfield
（战役判定：双方控机场=contested，一方控=strategic_win，皆毁=stalemate）；
双方 tick=40 对称增援；AF=贝蒂奥(日)/马金(美)。""",
}


def scenario_settings_text(sc) -> str:
    """设定明细（用户要求：示例战役必须告知玩家可见度/官僚水平/探测能力/舰艇性能）。"""
    if sc.night:
        vis = "夜战·晴(视距≈标称)" if sc.weather < 0.3 else "夜战·雨雾(能见度很差)"
    else:
        vis = "昼战·晴" if sc.weather < 0.3 else "昼战·薄雾/雨"
    lines = ["【设定明细】%s" % sc.name,
             "任务: %s | 战役目标: %s" % (sc.mission, sc.objective),
             "环境/可见度: %s   (night=%s, weather=%.1f)" % (vis, sc.night, sc.weather),
             ""]
    for side in sc.sides:
        c2 = getattr(side, "c2_penalty", 0.0)
        c2_note = ("0=理想C2" if c2 <= 1e-9 else
                   "≈条令混乱" if c2 >= 0.15 else "轻度")
        lines.append("【%s】官僚水平 c2_penalty=%.2f（%s） | 学说=%s | 初始 %d 单位"
                     % (side.name, c2, c2_note, side.doctrine, len(side.units)))
        seen = {}
        for u in side.units:
            for s in u.sensors:
                seen[(s.kind, round(s.active_range_nm, 1), round(s.reliability, 2))] = None
        if seen:
            det = "; ".join("%s %.0fnm 可靠%.2f" % (k[0], k[1], k[2]) for k in seen)
            lines.append("  探测能力: %s" % det)
        groups = {}
        for u in side.units:
            g = groups.setdefault(u.cls, [])
            g.append(u)
        for cls in ("BB", "CV", "CA", "CL", "DD", "AF"):
            if cls not in groups:
                continue
            g = groups[cls]
            sample = g[0]
            if cls == "AF":
                lines.append("  %-3s ×%-3d  hp(完好度)=%.0f  武器: %s"
                             % (cls, len(g), sample.hp,
                                ", ".join("%s×%d" % (w.name, sample.ammo.get(w.name, 0))
                                          for w in sample.weapons)))
                continue
            wsp = []
            for w in sample.weapons:
                if w.kind == "aircraft":
                    wsp.append("%s×%d" % (w.name, sample.ammo.get(w.name, 0)))
                elif w.kind in ("aerial_torpedo", "aerial_bomb"):
                    wsp.append("%s(可靠%.2f)×%d" % (w.name, w.reliability,
                                                    sample.ammo.get(w.name, 0)))
                else:
                    wsp.append("%s %dkm 速率%.1f 可靠%.2f"
                               % (w.name, w.range_m // 1000, w.rate_per_min, w.reliability))
            lines.append("  %-3s ×%-3d  hp=%.0f 航速=%.0f节  %s"
                         % (cls, len(g), sample.hp, sample.speed_kt,
                            " | ".join(wsp)))
        if getattr(side, "reinforcements", None):
            r0 = side.reinforcements[0]
            lines.append("  增援: tick=%d 入场 ×%d 单位" % (r0.arrive_tick, len(r0.units)))
        lines.append("")
    lines.append("（性能取同类舰统计模板口径；93式/Mk15 等武器质量差异已编码进 reliability，"
                 "详见《瓜岛推演稿》校准锚点。）")
    return "\n".join(lines)
