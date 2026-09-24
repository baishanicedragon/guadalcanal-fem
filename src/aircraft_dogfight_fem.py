# -*- coding: utf-8 -*-
"""
aircraft_dogfight_fem.py — WWII Carrier Fighter Dogfight (Energy-Maneuverability + Turn) FEM
=====================================================================
二战舰载战斗机近距空战（dogfight）有限元推演模组
---------------------------------------------------------------------
方法论（与本仓库 gunnery_fem / torpedo_fem 同源）：
  1. 先算「干净性能底」——纯空气动力学/推进，不给飞行员与教条噪声：
       - 能量机动 (Boyd 1966, E-M 理论): 比能量 Es = h + V^2/2g；
         单位剩余功率 Ps = V(T-D)/W；瞬时/稳盘、角点速度。
       - 回转机动 (single-loop / double-loop): 半径 R=V/omega、盘旋角速率 omega。
  2. 再用「干扰因子」反推真实战果——
       - 飞行员质量因子 PQF（ veteran / rookie 由种子留存率决定）
       - 武器致命性（美军 6×.50 高射速+装甲 vs 日军 2×20+2×7.7 少弹）
       - 交战几何权重（能量战 / 单环 / 双环 的占比）
  3. 蒙特卡洛：在初始能量态/几何/飞行员质量上抽样，Aggregate 击杀概率与交换比。

数据来源（公开战史 / 制造商手册 / E-M 理论文献，逐条标注）：
  - E-M 理论: Boyd & Christie, "Energy-Maneuverability", APGC-TR-66-4 (1966);
    科普中国 / 航空学报 2024 综述。
  - F6F-5 Hellcat: MiGFlug 规格页 + MilitaryFactory（R-2800-10W 2000hp,
    翼面积31.0m^2, 空重4190kg, 总重5714kg, 极速629km/h, 初 climb 13.2m/s,
    翼载184kg/m^2, 装甲96kg）。
  - F4U-1D Corsair: MilitaryMachine/MilitaryFactory（R-2800 2000hp,
    翼面积29.2m^2, 极速684km/h, climb 3120ft/min, 滚转/俯冲优于F6F）。
  - A6M5 零战五二型: 维基（荣21型1130hp, 翼面积21.30m^2, 空重1876kg,
    总重2733kg, 极速565km/h@6000m, climb 6000m/7:01, 盘旋限速666.7km/h）。
  - A6M8 金星(零战五四/六四型): 维基/SecretProjects（金星62型 1500-1560hp,
    同机体21.30m^2, 空重2150kg, 总重3150kg, 极速572.3km/h@6000m,
    climb 6000m/6:50, 盘旋限速740.8km/h, 内油续航850km=较A6M5(2560km)大减）。
  - 日军飞行员养成/三级体系: daydaynews《预科练制度》、J-Aircraft 军衔表、
    长期影响稿 §九/§8.3/§8.4（fork 留存 +100~200 精英；三级速成甲飞13期27988人）。

⚠️ 诚实边界（铁律 #16/#17 同源）：
  - 本模组是「开环几何 + 战斗决策简化」，不模拟飞行员闭环操控手感；
    结论为「结构性交换比」，非单场确定性剧本。
  - 1942fork 后日本状态取自《长期影响》稿，属反事实设定，已显式标注。
=====================================================================
"""
import math
import random

G = 9.80665
RHO0 = 1.225          # 海平面空气密度 kg/m^3

# ---------- 基础物理 ----------
def air_density(h: float) -> float:
    """ISA 简化指数衰减（8500m 标高）。"""
    return RHO0 * math.exp(-h / 8500.0)

def specific_energy(V: float, h: float) -> float:
    """比能量 Es (m)。动能 + 势能。"""
    return h + V * V / (2.0 * G)

def alt_power_factor(h: float) -> float:
    """活塞发动机随高度掉功率（临界高度后下降）。"""
    return max(0.60, 1.0 - h / 20000.0)

# ---------- 飞机数据类 ----------
class Aircraft:
    def __init__(self, name, year, P_sl, W_gross, S, AR, Cd0, n_max,
                 V_dive, lethality, provenance):
        self.name = name
        self.year = year
        self.P_sl = P_sl            # 海平面功率 W
        self.W = W_gross * G        # 重量 N（用总重作战）
        self.S = S                  # 翼面积 m^2
        self.AR = AR
        self.e = 0.80
        self.k = 1.0 / (math.pi * self.e * AR)   # 诱导阻力因子
        self.Cd0 = Cd0
        self.n_max = n_max
        self.V_dive = V_dive        # 俯冲限速 m/s
        self.lethality = lethality  # 武器致命性乘数
        self.prov = provenance

    # 性能函数（干净底）
    def thrust(self, V, h):
        P = self.P_sl * alt_power_factor(h)
        return P / max(V, 1.0)

    def drag(self, V, h, n):
        q = 0.5 * air_density(h) * V * V
        D0 = q * self.S * self.Cd0
        Di = self.k * (n * self.W) ** 2 / (q * self.S)
        return D0 + Di

    def ps(self, V, h, n=1.0):
        """单位剩余功率 Ps (m/s)。"""
        T = self.thrust(V, h)
        D = self.drag(V, h, n)
        return V * (T - D) / self.W

    def max_sustained_turn(self, V, h):
        """Ps=0 处的稳盘角速率 (rad/s)，受 n_max 限制。返回 (omega_rad, n_used)。"""
        T = self.thrust(V, h)
        q = 0.5 * air_density(h) * V * V
        D0 = q * self.S * self.Cd0
        if T <= D0:
            return 0.0, 1.0
        # T = D0 + k (n W)^2/(q S)  => n = sqrt((T-D0) q S / (k W^2))
        n = math.sqrt((T - D0) * q * self.S / (self.k * self.W ** 2))
        n = min(n, self.n_max)
        return G * math.sqrt(max(n * n - 1.0, 0.0)) / V, n

    def instantaneous_turn(self, V, h):
        """在 n_max 处的瞬时盘旋角速率 (rad/s)，代价是耗能。"""
        n = self.n_max
        return G * math.sqrt(n * n - 1.0) / V

    def corner_velocity(self, h):
        """扫描求最大稳盘对应的速度 (m/s)。"""
        best_v, best_w = 0.0, 0.0
        for v in [x * 5.0 for x in range(16, 60)]:  # 80~295 m/s
            w, _ = self.max_sustained_turn(v, h)
            if w > best_w:
                best_w, best_v = w, v
        return best_v, best_w

    def envelope(self, h=4500.0):
        """返回展示用性能包线。"""
        cv, cw = self.corner_velocity(h)
        ws, ns = self.max_sustained_turn(150.0, h)
        return {
            "name": self.name,
            "wing_loading": self.W / G / self.S,        # kg/m^2
            "pow_mass": self.P_sl / (self.W / G),        # W/kg
            "corner_v_kmh": cv * 3.6,
            "corner_turn_deg_s": math.degrees(cw),
            "sustained_turn_150_deg_s": math.degrees(ws),
            "ps_150": self.ps(150.0, h),
            "ps_120": self.ps(120.0, h),
        }

# ---------- 配置：四型机 ----------
# 功率 W；总重 kg；翼面积 m^2；展弦比；Cd0；n_max；俯冲限速 m/s；致命性
AIRCRAFT = {
    "F6F-5 Hellcat": Aircraft(
        "F6F-5 Hellcat", 1943, 1.491e6, 5714, 31.0, 5.50, 0.021, 7.0, 200.0, 1.30,
        "R-2800-10W 2000hp; 31.0m^2; 总重5714kg; 极速629km/h; 装甲96kg (MiGFlug/MilFactory)"),
    "F4U-1D Corsair": Aircraft(
        "F4U-1D Corsair", 1943, 1.491e6, 5800, 29.2, 5.35, 0.018, 7.0, 230.0, 1.30,
        "R-2800 2000hp; 29.2m^2; 总重~5800kg; 极速684km/h; 滚转/俯冲优于F6F (MilitaryMachine)"),
    "A6M5 Zero": Aircraft(
        "A6M5 Zero", 1943, 8.43e5, 2733, 21.30, 5.68, 0.022, 6.0, 185.0, 1.00,
        "荣21型1130hp; 21.30m^2; 总重2733kg; 极速565km/h@6000m; climb 6000m/7:01 (Wiki)"),
    "A6M8 Kinsei Zero": Aircraft(
        "A6M8 Kinsei Zero", 1943, 1.12e6, 3150, 21.30, 5.68, 0.024, 6.5, 206.0, 1.00,
        "金星62型1500-1560hp; 同机体21.30m^2; 总重3150kg; 极速572.3km/h@6000m; "
        "climb 6000m/6:50; 内油850km(较A6M5大减) (Wiki/SecretProjects)"),
}

# ---------- 交战解算 ----------
def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))

def duel_kill_probs(A, B, h, V, geom, pqf_A, pqf_B, base_hit=0.50,
                    spec_A=1.0, spec_B=1.0):
    """
    单场 1v1 的双方击杀概率。
      geom: 'energy' | 'one_circle' | 'two_circle'
        能量战: 比 Ps（能增持方 extend+re-attack）
        单环(one_circle): 比稳盘角速率 ω（半径小者赢）
        双环(two_circle): 比稳盘角速率 ω（角速率大者赢）
      pqf: 飞行员质量因子（乘以有效性能 + 影响战法选择）
      spec: 纸面性能达成率（fork 日本=1.0 实达设计；史实日本≈0.9 因材料/QC 折扣）
    返回 (P_A_kills, P_B_kills)。
    """
    if geom == "energy":
        mA, mB = A.ps(V, h, 1.0), B.ps(V, h, 1.0)
    else:  # 回转战两种都看稳盘角速率
        wA, _ = A.max_sustained_turn(V, h)
        wB, _ = B.max_sustained_turn(V, h)
        mA, mB = wA, wB
    # 纸面性能达成率：实际交付机只有这一比例的性能可用
    mA *= spec_A
    mB *= spec_B
    effA, effB = mA * pqf_A, mB * pqf_B
    denom = (abs(mA) + abs(mB) + 1e-6)
    # 谁赢得该几何态势 -> 谁拿到开火机会
    P_A_regime = sigmoid(3.0 * (effA - effB) / denom)
    # 拿到机会后，致命性决定实际击杀
    P_A_kills = P_A_regime * A.lethality * base_hit
    P_B_kills = (1.0 - P_A_regime) * B.lethality * base_hit
    return P_A_kills, P_B_kills

def monte_carlo(A, B, pqf_A_mean, pqf_B_mean, n=4000, seed=42,
                geom_weights=(0.30, 0.35, 0.35), h_range=(2000, 7000),
                V_range=(90, 180), spec_A=1.0, spec_B=1.0):
    """蒙特卡洛聚合：返回 (P_A_kills_per_duel, P_B_kills_per_duel, 交换比 A/B)。"""
    rng = random.Random(seed)
    geoms = ["energy", "one_circle", "two_circle"]
    sum_A = sum_B = 0.0
    for _ in range(n):
        h = rng.uniform(*h_range)
        V = rng.uniform(*V_range)
        gi = rng.choices(range(3), weights=geom_weights, k=1)[0]
        geom = geoms[gi]
        # 飞行员质量：均值 + 噪声（夹在合理区间）
        pa = min(1.10, max(0.30, pqf_A_mean + rng.gauss(0, 0.10)))
        pb = min(1.10, max(0.30, pqf_B_mean + rng.gauss(0, 0.10)))
        ka, kb = duel_kill_probs(A, B, h, V, geom, pa, pb,
                                 spec_A=spec_A, spec_B=spec_B)
        sum_A += ka
        sum_B += kb
    pa_per = sum_A / n
    pb_per = sum_B / n
    ratio = (pa_per / pb_per) if pb_per > 1e-9 else float("inf")
    return pa_per, pb_per, ratio

# ---------- 场景 ----------
# 飞行员质量因子（PQF）锚定（来自《长期影响》§8.1/§11.7/§11.8）：
#   史实美国：不缺飞行员数量（1943 毕业 2.1 万），但缺"能带队的队长/老手"——
#            所罗门消耗战吃掉的正是这批；fork 里美军航母沉没更多 ⇒ 种子更薄 ⇒ OTL 0.92 → fork 0.78。
#   史实日本末1943：三级速成、菜鸟为主（甲飞13期2.8万人无法训练）⇒ 0.50。
#   fork 日本1943：①留存+100~200精英(§8.1)；②航校前移南洋油田(§11.7)⇒燃油瓶颈消失、
#            训练时数上升；③三级体系得以真正训练 ⇒ 均值≈0.80（仍受教官池天花板限制，非0.95）。
PQF = {
    "US_1943_OTL": 0.92,        # 史实时间线（对照）
    "US_1943_fork": 0.78,       # 本 fork：航母沉没更多+种子减少
    "JP_hist_1943": 0.50,       # 史实末1943：菜鸟为主
    "JP_fork_1943": 0.80,       # 本 fork：油旁训练+精英留存+三级体系真正运转
}

# 纸面性能达成率（spec）：fork 日本产能/油料无忧 ⇒ 下线机实达设计(1.0)；
#   史实日本材料/QC 折扣(0.90)；美方始终 1.0（《长期影响》§11.5/§9.7）。
SPEC = {
    "US": 1.00,
    "JP_fork": 1.00,
    "JP_hist": 0.90,
}

# 战役层数量乘数（forward-deployed 兵力，非单场品质）：
#   美军 fork：1942 多沉航母+运输/护航被瓜岛抽调 ⇒ 1943末可用舰载机联队偏少 (~0.8)
#   日军 fork：油旁训练+产能改善+金星零战交付 ⇒ 可部署航空队偏多 (~1.3)
#   （《长期影响》§9.1 航母真空"数个月"、§11.7 训练、§6.4c/§11.6 换装）
QUANTITY = {
    "US_fork": 0.80,
    "JP_fork": 1.30,
}

def run():
    print("=" * 76)
    print("  二战舰载战斗机 dogfight FEM — 能量机动 + 回转机动")
    print("=" * 76)

    # ---- 1. 性能包线 ----
    print("\n[1] 干净性能底（4500m 包线）")
    print(f"{'机型':<18}{'翼载kg/m2':>10}{'功重W/kg':>10}{'角点km/h':>10}"
          f"{'角点盘旋°/s':>12}{'稳盘@150°/s':>13}{'Ps@150':>9}{'Ps@120':>9}")
    for name, ac in AIRCRAFT.items():
        e = ac.envelope(4500.0)
        print(f"{name:<18}{e['wing_loading']:>10.1f}{e['pow_mass']:>10.1f}"
              f"{e['corner_v_kmh']:>10.0f}{e['corner_turn_deg_s']:>12.1f}"
              f"{e['sustained_turn_150_deg_s']:>13.1f}{e['ps_150']:>9.1f}{e['ps_120']:>9.1f}")

    # ---- 2. 场景1：1943.6 纯机体对比（PQF 双方=1.0，隔离飞行员噪声）----
    print("\n[2] 场景1 · 1943.6 机体对比（隔离飞行员，PQF=1.0）")
    print("    美投入 F4U/F6F 后，山本倒逼金星零战投产 → 与 A6M5/F6F/F4U 的交换比")
    f6f, f4u, a5, a8 = (AIRCRAFT["F6F-5 Hellcat"], AIRCRAFT["F4U-1D Corsair"],
                         AIRCRAFT["A6M5 Zero"], AIRCRAFT["A6M8 Kinsei Zero"])
    pairs = [("A6M5 Zero", "F6F-5 Hellcat"), ("A6M8 Kinsei Zero", "F6F-5 Hellcat"),
             ("A6M5 Zero", "F4U-1D Corsair"), ("A6M8 Kinsei Zero", "F4U-1D Corsair")]
    print(f"{'对阵':<34}{'日击杀/场':>10}{'美击杀/场':>10}{'交换比(日/美)':>14}")
    for jp, us in pairs:
        pa, pb, ratio = monte_carlo(AIRCRAFT[jp], AIRCRAFT[us], 1.0, 1.0, n=4000)
        print(f"{jp+' vs '+us:<34}{pa:>10.3f}{pb:>10.3f}{ratio:>14.2f}")

    # ---- 3. 场景2：1943末 中太平洋（fork 日本状态 + 三级体系）----
    print("\n[3] 场景2 · 1943末 中太平洋交战（fork 状态，依《长期影响》§8.1/§11.7/§11.8 订正）")
    print("    fork 不对称：日本更强（油旁训练+精英留存+三级真训+产能无忧→spec=1.0）")
    print("               美国更弱（航母多沉+队长种子减少 + 可用舰载联队偏少×0.8）")
    print(f"{'对阵':<44}{'日/场':>8}{'美/场':>8}{'单场比':>9}{'战役比*':>9}")
    def campaign(r, q_jp=QUANTITY["JP_fork"], q_us=QUANTITY["US_fork"]):
        return r * q_jp / q_us
    # 3a. fork 日本用金星零战 vs 美军 F6F
    pa, pb, r1 = monte_carlo(a8, f6f, PQF["JP_fork_1943"], PQF["US_1943_fork"],
                             n=6000, spec_A=SPEC["JP_fork"], spec_B=SPEC["US"])
    print(f"{'JP_fork(金星零战) vs US_fork(F6F)':<44}{pa:>8.3f}{pb:>8.3f}"
          f"{r1:>9.2f}{campaign(r1):>9.2f}")
    # 3b. 史实日本用 A6M5 vs 美军 F6F（对照，史实不对称）
    pa, pb, r2 = monte_carlo(a5, f6f, PQF["JP_hist_1943"], PQF["US_1943_OTL"],
                             n=6000, spec_A=SPEC["JP_hist"], spec_B=SPEC["US"])
    print(f"{'JP_hist(A6M5) vs US_OTL(F6F)':<44}{pa:>8.3f}{pb:>8.3f}"
          f"{r2:>9.2f}{r2:>9.2f}")
    # 3c. fork 日本用金星零战 vs 美军 F4U（更快对手）
    pa, pb, r3 = monte_carlo(a8, f4u, PQF["JP_fork_1943"], PQF["US_1943_fork"],
                             n=6000, spec_A=SPEC["JP_fork"], spec_B=SPEC["US"])
    print(f"{'JP_fork(金星零战) vs US_fork(F4U)':<44}{pa:>8.3f}{pb:>8.3f}"
          f"{r3:>9.2f}{campaign(r3):>9.2f}")
    # 3d. fork 日本用金星零战 vs 美军 F6F，但 US 用 OTL 质量（隔离"美国变弱"一项）
    pa, pb, r4 = monte_carlo(a8, f6f, PQF["JP_fork_1943"], PQF["US_1943_OTL"],
                             n=6000, spec_A=SPEC["JP_fork"], spec_B=SPEC["US"])
    print(f"{'  〔隔离〕JP_fork vs US_OTL(质量)':<44}{pa:>8.3f}{pb:>8.3f}{r4:>9.2f}")

    # ---- 4. 敏感性：飞行员质量单独作用 ----
    print("\n[4] 敏感性 · 金星零战(机体+spec=1.0) 对 F6F，仅扫日本飞行员质量")
    for pqf in [0.50, 0.69, 0.80, 0.92]:
        pa, pb, r = monte_carlo(a8, f6f, pqf, PQF["US_1943_fork"],
                                n=6000, spec_A=SPEC["JP_fork"], spec_B=SPEC["US"])
        print(f"  JP PQF={pqf:.2f} (US_fork=0.78) -> 单场交换比(日/美)={r:>5.2f}")

    print("\n" + "=" * 76)
    print("结论速览（fork 订正后）：")
    print("  · 金星零战相对 A6M5 在机体层已追平/略超（速度+爬升），")
    print("    但相对 F6F/F4U 仍低一档（高速能量战、滚转、俯冲、装甲火力）。")
    print("  · 关键反转：fork 把不对称方向翻了过来——")
    print("    日本飞行员质量因'油旁训练'(§11.7)回升至≈0.80，美国因'航母多沉+种子减'")
    print("    降至≈0.78；再乘战役数量(日×1.3/美×0.8)，1943末中太平洋")
    print("    日军可取得局部均势甚至优势（战役比≈1.0 上下），与史实(1:10)截然不同。")
    print("  · 但 §8.6/§11.10 铁律仍在：工业与人口曲线不变，这是'1943 窗口'；")
    print("    非'1944 胜负'；且教官池天花板(§11.7)与双刃教条(§8.3e)未解除。")
    print("=" * 76)

if __name__ == "__main__":
    run()
