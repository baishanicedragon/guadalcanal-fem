# -*- coding: utf-8 -*-
"""
engine.py · 30 秒 tick 模拟引擎（headless，可被 GUI / CLI 调用）
==============================================================
每 tick 依次跑 5 个阶段（对应鱼叉公开逻辑 + 你仓库的 FEM）：

  P1 索敌 search        —— 探测不稳定（uncertainty.detection_modifier）
  P2 火控解算 fire_ctl  —— 火控质量（uncertainty.fire_control_modifier）
  P3 交战命中 engage    —— 调 fem_bridge 拿干净底 × 多维不确定性
  P4 损伤 damage        —— HP/进水/炮塔/士气/击沉（口径因子 + TDS 简化）
  P5 撤退/溃散 retreat  —— 溃散(士气崩)与指挥官专业撤离(损失/战力比)分离判定

与"不疯的山本"案一致：固定 seed 可复现、每发必落表、命中率∈[0,1]、击穿≤命中。
"""
import random
import math
from . import model as M
from . import uncertainty as U
from . import fem_bridge as FB


class Engine:
    def __init__(self, scenario: M.Scenario, seed: int = None, step_sec: int = 30):
        self.scenario = scenario
        self.rng = random.Random(seed if seed is not None else scenario.seed)
        self.step_sec = step_sec
        self.tick = 0
        self.log: list = []
        self.last_snap = None
        self._spawned_r = set()   # 已抵达增援的 id 集合
        for side in scenario.sides:
            for u in side.units:
                self._init_unit(u)

    def _init_unit(self, u):
        """单位入场初始化（初始编成与战役增援共用）：炮塔数 = 主炮数。"""
        u.turrets_ok = sum(1 for w in u.weapons if w.kind == "gun")

    # ---------------------------------------------------------------- 主循环
    def step(self) -> dict:
        self.tick += 1
        self._spawn_reinforcements()      # 战役层：到点增援整批入场
        fr = U.Friction(self.rng, night=self.scenario.night,
                        weather=self.scenario.weather)
        self._fog = fr.fog              # 本 tick 共享迷雾值，供阶段报告使用
        self._phase_move(fr)            # 接敌 / 脱离（阵位机动）
        detections = self._phase_search(fr)
        solutions = self._phase_fire_control(detections, fr)
        hits = self._phase_engage(solutions, fr)
        before = {id(u): (u.withdrawing, u.routed) for s in self.scenario.sides
                  for u in s.units if u.alive}
        self._phase_damage(hits)
        self._phase_retreat(fr)
        new_retreats = [u for s in self.scenario.sides for u in s.units
                        if u.alive and not before.get(id(u), (True, False))[0]
                        and u.withdrawing]
        new_routs = [u for s in self.scenario.sides for u in s.units
                     if u.alive and not before.get(id(u), (True, False))[1]
                     and u.routed]
        snap = self._snapshot(detections, new_routs)
        snap["report"] = self._build_report(detections, solutions, hits,
                                             new_retreats, new_routs)
        self.log.append(snap)
        self.last_snap = snap
        return snap

    # ---------------------------------------------------------------- 战役层：增援
    def _spawn_reinforcements(self):
        """到点（arrive_tick）把整批增援单位加入本方队列，从本方存活单位质心后方入场。"""
        for side in self.scenario.sides:
            for r in side.reinforcements:
                if id(r) in self._spawned_r:
                    continue
                if self.tick < r.arrive_tick:      # 未到入场 tick，先挂着
                    continue
                alive = [u for u in side.units if u.alive]
                if alive:
                    cx = sum(u.pos[0] for u in alive) / len(alive)
                    cy = sum(u.pos[1] for u in alive) / len(alive)
                else:
                    cx, cy = 0.0, 0.0
                for i, u in enumerate(r.units):
                    self._init_unit(u)
                    u.pos = (cx - 2500.0, cy + float(i * 800))
                    side.units.append(u)
                self._spawned_r.add(id(r))

    # ---------------------------------------------------------------- 阶段报告
    def _build_report(self, detections, solutions, hits, new_retreats, new_routs) -> str:
        """每轮推演的 5 阶段人类可读摘要（索敌/火控/交战/损伤/撤退）。"""
        n_hit = sum(h[3] for h in hits)
        lines = [
            f"【T+{self.tick * self.step_sec}s】迷雾 fog={self._fog:.2f}",
            f"  索敌  : {len(detections)} 个接触（达到火控门限）",
            f"  火控  : {len(solutions)} 个解算（探测×火控质量）",
        ]
        if hits:
            by_w = {}
            for sh, tg, w, nh, p in hits:
                by_w[w.name] = by_w.get(w.name, 0) + nh
            det = ", ".join(f"{k}×{v}" for k, v in by_w.items())
            lines.append(f"  交战  : {len(hits)} 次开火，命中 {n_hit} 发（{det}）")
        else:
            lines.append("  交战  : 无命中")
        if new_retreats:
            names = ", ".join(u.name for u in new_retreats)
            lines.append(f"  撤离  : {names} 指挥官判断不利，有序退出接触")
        if new_routs:
            names = ", ".join(u.name for u in new_routs)
            lines.append(f"  溃散  : {names} 士气崩溃，失控脱离战场")
        return "\n".join(lines)

    # ---------------------------------------------------------------- 阵位机动
    def _phase_move(self, fr: U.Friction):
        """接敌 / 脱离：每个存活单位朝敌方质心机动，逼近到最佳炮战距离后保持阵位；
        已撤退单位反向脱离（逃跑的船照样会被追上击沉）。同时每船每 tick 只漂移一次士气。"""
        GUN_RANGE_M = 3500.0            # 抵近到 ~3.5km 即进入稳定炮战距离
        for side in self.scenario.sides:
            enemies = [u for s in self.scenario.sides if s is not side
                       for u in s.units if u.alive]
            if not enemies:
                continue
            cx = sum(e.pos[0] for e in enemies) / len(enemies)
            cy = sum(e.pos[1] for e in enemies) / len(enemies)
            for u in side.units:
                if not u.alive:
                    continue
                U.morale_step(u, fr, self.rng)   # 每船每 tick 一次心态不稳定
                dx, dy = cx - u.pos[0], cy - u.pos[1]
                d = math.hypot(dx, dy) or 1.0
                step_m = u.speed_kt * 0.514444 * self.step_sec
                if u.withdrawing:                # 脱离：远离敌质心
                    nx = u.pos[0] - dx / d * step_m
                    ny = u.pos[1] - dy / d * step_m
                else:
                    if d <= GUN_RANGE_M:
                        continue                # 已抵最佳炮战距离，保持阵位
                    nx = u.pos[0] + dx / d * step_m
                    ny = u.pos[1] + dy / d * step_m
                u.pos = (nx, ny)

    # ---------------------------------------------------------------- P1 索敌
    def _phase_search(self, fr: U.Friction) -> list:
        out = []
        units = [u for side in self.scenario.sides for u in side.units if u.alive]
        for sh in units:
            for tg in units:
                if tg is sh or tg.side == sh.side or not tg.alive:
                    continue
                # 撤退/溃散的"射击方"停火，但撤退单位仍可被瞄准、击沉（逃跑的船照样沉）
                if sh.withdrawing or sh.routed:
                    continue
                best = 0.0
                for s in sh.sensors:
                    rng_nm = s.active_range_nm * U.detection_modifier(s, fr, self.rng)
                    # 距离（nm）：用 pos 欧氏 / 1852
                    d_nm = math.dist(sh.pos, tg.pos) / 1852.0
                    if d_nm <= rng_nm:
                        best = max(best, 1.0 - d_nm / max(1e-3, rng_nm))
                if best > 0.15:   # 达到最低接触质量才进火控
                    sh.contact_s += self.step_sec
                    out.append((sh, tg, best * (1.0 - self._c2(sh.side))))
        return out

    # ---------------------------------------------------------------- P2 火控
    MAX_TARGETS_PER_SHOOTER = 2      # 炮术现实：一艘舰每 tick 仅锁定最近 1-2 个目标，
                                     # 而非对"所有探测"齐射，否则伤害体积爆炸、瞬间一边倒。

    def _phase_fire_control(self, detections, fr: U.Friction) -> list:
        # 按射击方分组，每方仅保留探测质量最高的前 MAX_TARGETS_PER_SHOOTER 个目标
        groups: dict = {}          # id(sh) -> [sh, [(tg, q_det), ...]]
        for sh, tg, q_det in detections:
            g = groups.get(id(sh))
            if g is None:
                g = [sh, []]; groups[id(sh)] = g
            g[1].append((tg, q_det))
        out = []
        for sh, tgs in groups.values():
            sh.fire_control = U.fire_control_modifier(sh, fr, sh.contact_s) \
                             * (1.0 - self._c2(sh.side))
            # 注意：士气漂移在 _phase_move 里每船每 tick 只更新一次，
            # 绝不在"每个接触"里更新（否则多头接触会把士气一 tick 内打崩）。
            tgs.sort(key=lambda x: x[1], reverse=True)
            for tg, q_det in tgs[: self.MAX_TARGETS_PER_SHOOTER]:
                out.append((sh, tg, q_det * sh.fire_control))
        return out

    # ---------------------------------------------------------------- P3 交战
    def _phase_engage(self, solutions, fr: U.Friction) -> list:
        hits = []
        for sh, tg, q in solutions:
            if q <= 0.02:
                continue
            for w in sh.weapons:
                if w.kind in ("aircraft",):
                    # 战斗机仅提供 CAP（拦截来袭航空兵），不直接造成舰船伤害；
                    # 其威胁折算在守军 _cap_factor 里（见下）。
                    continue
                if w.kind not in ("gun", "torpedo", "bomb",
                                  "aerial_torpedo", "aerial_bomb"):
                    continue
                avail = sh.ammo.get(w.name, 0)
                if avail <= 0:
                    continue
                fires, disp_mult = U.weapon_lot_factor(w, self.rng)
                if not fires:
                    continue  # 武器质量浮动：哑火
                if w.kind in ("aerial_torpedo", "aerial_bomb"):
                    # 航空打击：飞机飞抵目标，与两舰间距解耦（不受机动靠拢影响）
                    range_m = 1200.0
                else:
                    range_m = max(500.0, math.dist(sh.pos, tg.pos))
                if w.kind == "gun":
                    p = FB.gunnery_hit_rate(sh, tg, range_m, disp_mult, self.rng)
                elif w.kind == "torpedo":
                    p = FB.torpedo_hit_rate(sh, tg, range_m, self.rng)
                elif w.kind == "aerial_torpedo":
                    p = FB.aerial_torpedo_hit_rate(sh, tg, range_m, self.rng)
                else:  # bomb / aerial_bomb
                    p = FB.air_hit_rate(sh, tg, range_m, self.rng)
                if w.kind in ("aerial_torpedo", "aerial_bomb"):
                    p *= self._cap_factor(tg)      # 守军 CAP 拦截折算
                p *= q                              # 火控/探测质量折减
                # 固定机场(AF)不吃鱼雷（鱼雷对岸上目标无效）
                if tg.cls == "AF" and w.kind in ("torpedo", "aerial_torpedo"):
                    continue
                # 航空打击以"攻击波"为单位（每 tick 一个波次，4 架级），受弹药约束；
                # 炮/雷仍按 rate_per_min。
                if w.kind in ("aerial_torpedo", "aerial_bomb"):
                    shots = min(4, avail)
                else:
                    shots = min(max(1, int(w.rate_per_min * self.step_sec / 60.0)), avail)
                # 机场毁伤模型：机场完好度(<30%)→出动率节流（跑道/机库被毁→出动架次下降）
                if sh.cls == "AF" and sh.hp < 30.0:
                    shots = max(1, int(shots * sh.hp / 30.0))
                sh.ammo[w.name] = avail - shots
                n_hit = sum(1 for _ in range(shots) if self.rng.random() < p)
                if n_hit:
                    hits.append((sh, tg, w, n_hit, p))
        return hits

    def _cap_factor(self, target) -> float:
        """守军 CAP（战斗机拦截）对来袭航空打击的折减：本方存活单位战斗机弹药越多，
        拦截越强。约 100 架战斗机 → 折到 0.6 下限。战斗机不消耗弹药（持久 CAP 抽象），
        仅以其存量表征拦截强度。"""
        cap = 0
        for s in self.scenario.sides:
            if s is target.side:
                for u in s.units:
                    if u.alive and not u.withdrawing:
                        for w in u.weapons:
                            if w.kind == "aircraft":
                                cap += u.ammo.get(w.name, 0)
        return max(0.6, 1.0 - 0.004 * cap)

    # ---------------------------------------------------------------- P4 损伤
    def _phase_damage(self, hits):
        hit_ids = set()              # 每 tick 每目标只记一次"被命中"士气惩罚
        sunk_this_tick = []
        for sh, tg, w, n_hit, p in hits:
            cf = sh.caliber_factor() if w.kind == "gun" else 1.0
            for _ in range(n_hit):
                dmg = max(0.5, (4.0 + 6.0 * cf) * (0.6 + 0.8 * self.rng.random()))
                if tg.cls == "AF":
                    # 机场毁伤：仅降完好度(intact=hp)，不进水/不心态；完好度<30 出动率
                    # 已在 P3 节流；完好度=0 视为机场失能（alive=False）。
                    tg.hp = max(0.0, tg.hp - dmg)
                    if tg.hp <= 0 and tg.alive:
                        tg.alive = False
                        tg.hp = 0.0
                    continue
                tg.hp = max(0.0, tg.hp - dmg)
                tg.flooding = min(1.0, tg.flooding + 0.03 * cf)
                if tg.turrets_ok > 0 and self.rng.random() < 0.05 * cf:
                    tg.turrets_ok -= 1
            hit_ids.add(id(tg))
            if tg.cls != "AF" and tg.hp <= 0 and tg.alive:
                tg.alive = False
                tg.hp = 0.0
                sunk_this_tick.append(tg)
        # 被命中→心态不稳（每目标每 tick 封顶一次）
        for tg in (u for s in self.scenario.sides for u in s.units):
            if id(tg) in hit_ids and tg.alive:
                torp = any(h[1] is tg and h[2].kind == "torpedo" for h in hits)
                tg.morale = max(0.0, tg.morale - (0.06 if torp else 0.04))
        # 目睹同袍沉没→全队心态受冲击
        if sunk_this_tick:
            sunk_ids = {id(u) for u in sunk_this_tick}
            for side in self.scenario.sides:
                for u in side.units:
                    if u.alive and id(u) not in sunk_ids:
                        u.morale = max(0.0, u.morale - 0.04)

    # ---------------------------------------------------------------- P5 撤退 / 溃散
    def _phase_retreat(self, fr: U.Friction):
        """两类"退出接触"严格分离（用户设计铁律）：
        (1) 溃散 routed：士气跌破 rout_threshold，纯心理崩溃、不可控、脱离战场、不可重整。
        (2) 指挥官专业撤离 withdrawing：指挥官基于本方主力损失 / 战力比判断"继续打不划算"
            而有序撤出，属专业决策（非士气问题）；若敌方也已无接战能力则可回收阵位（不弃场）。
        两类状态对双方对称生效（rules.symmetric）。"""
        R = self.scenario.rules
        for side in self.scenario.sides:
            enemy = next(s for s in self.scenario.sides if s is not side)
            # —— (1) 士气崩溃 → 溃散（不可控，永不复原）——
            for u in side.units:
                if not u.alive or u.routed or u.cls == "AF":
                    continue
                if u.morale < R.rout_threshold:
                    u.routed = True
            # —— (2) 指挥官专业撤离判定（按本方主力损失 + 战力比）——
            cap_total = [u for u in side.units if u.cls in ("CV", "BB", "CA")]
            cap_loss = 1.0 - len([u for u in cap_total if u.alive]) / max(1, len(cap_total))
            pow_ratio = self._side_power(side) / max(1.0, self._side_power(enemy))
            cmd_withdraw = (cap_loss >= R.commander_withdraw_cap_loss) or \
                           (pow_ratio < R.commander_withdraw_pow_ratio)
            for u in side.units:
                if not u.alive or u.routed or u.cls == "AF":
                    continue
                has_gun_torp = any(w.kind in ("gun", "torpedo") for w in u.weapons)
                ammo_out = has_gun_torp and all(
                    u.ammo.get(w.name, 0) <= 0
                    for w in u.weapons if w.kind in ("gun", "torpedo"))
                material_out = u.hp < 25.0 or ammo_out
                if u.withdrawing:
                    # 重整：敌已无接战能力（互相撤离/全灭）→ 回收阵位（专业指挥官不弃已控战场）
                    if not any(self._can_fight(e) for e in enemy.units):
                        if u.morale >= 0.50 and u.hp >= 40.0:
                            u.withdrawing = False
                elif cmd_withdraw or material_out:
                    u.withdrawing = True

    # ---------------------------------------------------------------- 快照
    def _snapshot(self, detections=None, new_routs=None) -> dict:
        """每 tick 态势快照：供 GUI 海图与无头日志消费。
        contact_points：本 tick 探测到的接触（含观测方/目标坐标与不确定度分级），
        供鱼叉式不确定菱形渲染。sides[...] 含 routed / status 供海图分色。"""
        dets = detections or []
        contact_points = []
        for sh, tg, q in dets:
            lvl = "exact" if q >= 0.7 else "area" if q >= 0.35 else "bearing_only"
            contact_points.append({
                "obs": sh.side, "obs_pos": list(sh.pos),
                "tgt": tg.side, "tgt_pos": list(tg.pos),
                "tgt_name": tg.name, "uncertainty": lvl,
            })
        return {
            "tick": self.tick,
            "time_s": self.tick * self.step_sec,
            "contacts": len(dets),
            "contact_points": contact_points,
            "over": self.is_over(),
            "outcome": self.outcome(),
            "airfields": [
                {"side": s.name, "name": u.name, "integrity": round(u.hp, 1),
                 "alive": u.alive}
                for s in self.scenario.sides for u in s.units if u.cls == "AF"
            ],
            "sides": {
                s.name: [{"name": u.name, "cls": u.cls, "hp": round(u.hp, 1),
                          "alive": u.alive, "morale": round(u.morale, 2),
                          "withdrawing": u.withdrawing, "routed": u.routed,
                          "status": u.status}
                         for u in s.units]
                for s in self.scenario.sides
            },
        }

    # ---------------------------------------------------------------- 战斗力 / 结局
    def _c2(self, side_name: str) -> float:
        """本方指挥控制/官僚主义惩罚(0-1)，折减探测与火控质量。默认 0（关闭）。"""
        for s in self.scenario.sides:
            if s.name == side_name:
                return max(0.0, min(1.0, getattr(s, "c2_penalty", 0.0)))
        return 0.0

    def _can_fight(self, u: M.Unit) -> bool:
        """单位当前能否实际开火：存活 + 未溃散 + 未专业撤离 + 确有可开火武器。"""
        if not u.alive or u.routed or u.withdrawing:
            return False
        return any(w.kind in ("gun", "torpedo", "aerial_torpedo", "aerial_bomb")
                   for w in u.weapons)

    def _side_power(self, side: M.Side) -> float:
        """本方存活可战单位的加权战力（舰型粗略加权）。"""
        w = {"BB": 3.0, "CA": 2.0, "CV": 2.5, "CL": 1.0, "DD": 0.6}
        return sum((u.hp / 100.0) * w.get(u.cls, 1.0)
                   for u in side.units if self._can_fight(u))

    def is_over(self) -> bool:
        """战斗实质结束：任一方全灭，或任一方已无任何能接战(engaged)的存活单位
        （含溃散/专业撤离/弹尽/重创）。双方规则对称。"""
        for s in self.scenario.sides:
            alive = [u for u in s.units if u.alive]
            if not alive:
                return True
            if not any(self._can_fight(u) for u in alive):
                return True
        return False

    def outcome(self) -> str:
        """严肃海上模拟的对称结局判定（用户设计铁律）：
        双方约束对称生效时，结局偏向「平局 draw」或「双方惨败 mutual_defeat」，
        而非一方干净获胜。仅当一方主力损失明显更大时才判该方失利。
        取值：ongoing / JP_win / US_win / draw / mutual_defeat。"""
        jp, us = self.scenario.sides[0], self.scenario.sides[1]
        def cap_loss(side):
            cap = [u for u in side.units if u.cls in ("CV", "BB", "CA")]
            return 1.0 - len([u for u in cap if u.alive]) / max(1, len(cap))
        jp_l, us_l = cap_loss(jp), cap_loss(us)
        jp_eng = any(self._can_fight(u) for u in jp.units if u.alive)
        us_eng = any(self._can_fight(u) for u in us.units if u.alive)
        if not jp_eng and not us_eng:
            if jp_l >= 0.40 and us_l >= 0.40:
                return "mutual_defeat"          # 双方惨败
            if abs(jp_l - us_l) <= 0.15:
                return "draw"                   # 损失相当 → 平局
            return "JP_win" if jp_l < us_l else "US_win"
        if not jp_eng:
            return "US_win"
        if not us_eng:
            return "JP_win"
        return "ongoing"

    # ---------------------------------------------------------------- 战役层判定
    def _airfields(self, side: M.Side):
        return [u for u in side.units if u.cls == "AF"]

    def campaign_result(self) -> dict:
        """战役层战略判定（在战术 outcome() 之上）：依 scenario.objective 解释战略胜负。
        - annihilate / breakthrough：直接采用对称战术结局。
        - hold_airfield：双方各控机场→contested(未决)；一方控→该方战略胜；
          双方机场皆失能→stalemate（目标已无意义）。"""
        obj = self.scenario.objective
        tac = self.outcome()
        if obj == "hold_airfield":
            jp_af = self._airfields(self.scenario.sides[0])
            us_af = self._airfields(self.scenario.sides[1])
            jp_ctrl = any(u.alive and u.hp >= 30.0 for u in jp_af)
            us_ctrl = any(u.alive and u.hp >= 30.0 for u in us_af)
            if jp_ctrl and not us_ctrl:
                strat = "JP_strategic_win"
            elif us_ctrl and not jp_ctrl:
                strat = "US_strategic_win"
            elif jp_ctrl and us_ctrl:
                strat = "contested"
            else:
                strat = "stalemate"
            return {"objective": obj, "tactical": tac, "strategic": strat}
        return {"objective": obj, "tactical": tac, "strategic": tac}
