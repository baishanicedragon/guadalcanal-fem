# -*- coding: utf-8 -*-
"""
app.py · Tkinter GUI（零依赖，与仓库 stdlib-only 哲学一致）
==============================================================
模块化（对标鱼叉的学习价值，用户口径）：
  - 完整战役：瓜岛/中途岛/塔拉瓦 + 自定义战役
  - 炮战实验室 / 鱼雷对决 / 航空战：可独立加载的子模块（sim/*_lab.py）

完整战役功能：
  - 载入默认史实编成 → 双方舰队各自增删；舰种目录按时代（1942史实/1943fork/1944）
    向任意一方加造单位；双击列表项编辑性能（hp/航速）
  - 全局旋钮：可见度 / 官僚水平(JP+US) / 探测倍率 —— 取值范围玩家可改
  - 「开始」用当前编成构造引擎 Scenario（deepcopy，可反复开局）
  - 「设定」按钮 = 全参数披露（可见度/官僚/探测/舰艇性能明细）
  - 「背景」按钮 = 战役背景介绍（口径来自用户文档）

v0.9：模块化 + 时代化 + 参数披露（用户要求：像鱼叉那样"能学东西"）。
"""
import copy
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

from sim.engine import Engine
from sim import scenarios as SC
from sim import catalog
from sim import model as M
from sim.intros import INTROS, scenario_settings_text
from sim import gunnery_lab, torpedo_lab, air_lab
from gui.chart_helpers import draw_contact_diamond, side_color
from gui.state_markers import draw_status_token, draw_legend, outcome_cn

LABS = {"炮战实验室": gunnery_lab,
        "鱼雷对决": torpedo_lab,
        "航空战": air_lab}

# 可见度 → (night, weather)（引擎 Friction 口径）
VIS_MAP = {"昼·晴": (False, 0.0), "昼·薄雾": (False, 0.5),
           "夜·晴": (True, 0.0), "夜·雨雾": (True, 0.7)}


def _spread(units, x, step=800.0):
    """纵向拉开布置初始 pos（AF 固定坐标在 _build_scenario 里单独处理）。"""
    for i, u in enumerate(units):
        u.pos = (x, float(i * step))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("二战水面战舰模拟 · WWII Surface Warfare Sim")
        self.geometry("1400x760")
        self.engine = None
        self._jp_units = []      # 自定义日方舰队（M.Unit 列表）
        self._us_units = []      # 自定义美方舰队
        self._base = None        # 基准场景（提供环境/学说/增援模板）
        self._build()

    # ---------------------------------------------------------------- UI 骨架
    def _build(self):
        frm = ttk.Frame(self)
        frm.pack(fill="x", padx=8, pady=4)

        ttk.Label(frm, text="模块:").pack(side="left")
        self.module_var = tk.StringVar(value="完整战役")
        ttk.OptionMenu(frm, self.module_var, "完整战役", "完整战役", *LABS.keys(),
                       command=self._switch_module).pack(side="left", padx=4)

        # —— 战役工具条 ——
        ttk.Label(frm, text="场景:").pack(side="left")
        self.scenario_var = tk.StringVar(value="瓜岛")
        ttk.OptionMenu(frm, self.scenario_var, "瓜岛",
                       *SC.REGISTRY.keys(),
                       command=lambda _: self._load_scenario()).pack(side="left", padx=4)

        ttk.Label(frm, text="可见度:").pack(side="left")
        self.vis_var = tk.StringVar(value="夜·晴")
        self.vis_menu = ttk.OptionMenu(frm, self.vis_var, "夜·晴", *VIS_MAP.keys())
        self.vis_menu.pack(side="left", padx=4)

        for label, var, tip in (("官僚JP:", "c2_var", "JP 方指挥控制/官僚惩罚"),
                                ("官僚US:", "c2us_var", "US 方指挥控制惩罚"),
                                ("探测倍率:", "sens_var", "双方传感器范围 ×0.5~2.0")):
            ttk.Label(frm, text=label).pack(side="left")
            v = tk.DoubleVar(value=0.0 if var != "sens_var" else 1.0)
            setattr(self, var, v)
            top = 0.4 if var != "sens_var" else 2.0
            ttk.Scale(frm, from_=(0.0 if var != "sens_var" else 0.5), to=top,
                      variable=v, orient="horizontal",
                      length=70).pack(side="left", padx=2)

        self._battle_buttons = []
        for text, cmd in (("载入", self._load_scenario), ("背景", self._show_intro),
                          ("设定", self._show_settings), ("开始", self._start),
                          ("单步 30s", self._step),
                          ("快进 x10", lambda: self._step(10))):
            b = ttk.Button(frm, text=text, command=cmd)
            b.pack(side="left", padx=3)
            self._battle_buttons.append(b)

        # —— 战役主区（模块=完整战役时显示）——
        self._battle_frame = ttk.Frame(self)
        self._build_battle(self._battle_frame)
        self._battle_frame.pack(fill="both", expand=True, padx=8)

        # —— 实验室主区（模块=实验室时显示）——
        self._lab_frame = ttk.Frame(self)
        self._lab_frame.pack_forget()

    def _build_battle(self, mid):
        # 列 0：日方舰队
        left = ttk.Frame(mid)
        left.grid(row=0, column=0, sticky="ns")
        ttk.Label(left, text="日方舰队（JP）").grid(row=0, column=0)
        self.jp_list = tk.Listbox(left, height=26, width=26, exportselection=False)
        self.jp_list.grid(row=1, column=0, sticky="ns")
        self.jp_list.bind("<Double-1>", lambda e: self._edit_unit("JP"))
        ttk.Button(left, text="移除选中",
                   command=lambda: self._remove_selected("JP")).grid(row=2, column=0, sticky="ew")

        # 列 1：舰种目录（时代化 + 自定义单位）
        ctl = ttk.Frame(mid)
        ctl.grid(row=0, column=1, padx=6, sticky="ns")
        ttk.Label(ctl, text="舰种目录").grid(row=0, column=0, columnspan=2)
        ttk.Label(ctl, text="时代:").grid(row=1, column=0, sticky="e")
        self.era_var = tk.StringVar(value=catalog.ERAS[0])
        ttk.OptionMenu(ctl, self.era_var, catalog.ERAS[0], *catalog.ERAS).grid(
            row=1, column=1, sticky="ew")
        ttk.Label(ctl, text="舰种:").grid(row=2, column=0, sticky="e")
        self.cls_var = tk.StringVar(value="CA")
        ttk.OptionMenu(ctl, self.cls_var, "CA", *catalog.CLASSES).grid(
            row=2, column=1, sticky="ew")
        ttk.Label(ctl, text="数量:").grid(row=3, column=0, sticky="e")
        self.num_var = tk.IntVar(value=1)
        ttk.Spinbox(ctl, from_=1, to=20, textvariable=self.num_var,
                    width=5).grid(row=3, column=1, sticky="ew")
        ttk.Button(ctl, text="→ 加入日方",
                   command=lambda: self._add_units("JP")).grid(row=4, column=0,
                                                               columnspan=2, sticky="ew", pady=2)
        ttk.Button(ctl, text="→ 加入美方",
                   command=lambda: self._add_units("US")).grid(row=5, column=0,
                                                               columnspan=2, sticky="ew", pady=2)
        ttk.Label(ctl, text="载入=史实编成；\n双方各自增删；\n双击列表项=编辑性能；\n"
                            "开始=用当前编成+旋钮推演。",
                  justify="center").grid(row=6, column=0, columnspan=2, pady=8)

        # 列 2：美方舰队
        right = ttk.Frame(mid)
        right.grid(row=0, column=2, sticky="ns")
        ttk.Label(right, text="美方舰队（US）").grid(row=0, column=0)
        self.us_list = tk.Listbox(right, height=26, width=26, exportselection=False)
        self.us_list.grid(row=1, column=0, sticky="ns")
        self.us_list.bind("<Double-1>", lambda e: self._edit_unit("US"))
        ttk.Button(right, text="移除选中",
                   command=lambda: self._remove_selected("US")).grid(row=2, column=0, sticky="ew")

        # 列 3：海图 + 日志
        pane = ttk.Frame(mid)
        pane.grid(row=0, column=3, rowspan=2, sticky="ns")
        self.canvas = tk.Canvas(pane, width=380, height=300, bg="white")
        self.canvas.pack()
        self.log = scrolledtext.ScrolledText(pane, width=62, height=22)
        self.log.pack(fill="both", expand=True)

    # ---------------------------------------------------------------- 模块切换
    def _switch_module(self, mod):
        if mod == "完整战役":
            self._lab_frame.pack_forget()
            self._battle_frame.pack(fill="both", expand=True, padx=8)
            for b in self._battle_buttons:
                b.state(["!disabled"])
        else:
            self._battle_frame.pack_forget()
            self._build_lab_panel(LABS[mod], mod)
            self._lab_frame.pack(fill="both", expand=True, padx=8)
            for b in self._battle_buttons:
                b.state(["disabled"])

    def _build_lab_panel(self, lab, title):
        for w in self._lab_frame.winfo_children():
            w.destroy()
        left = ttk.Frame(self._lab_frame)
        left.pack(side="left", fill="y", padx=8, pady=6)
        ttk.Label(left, text=f"{title} · 参数").grid(row=0, column=0, columnspan=2)
        self._lab_vars = {}
        r = 1
        for spec in lab.PARAMS:
            ttk.Label(left, text=spec["label"] + ":").grid(row=r, column=0, sticky="e", pady=2)
            if spec["kind"] == "option":
                var = tk.StringVar(value=spec["values"][0])
                ttk.OptionMenu(left, var, spec["values"][0], *spec["values"]).grid(
                    row=r, column=1, sticky="ew")
            else:
                var = tk.IntVar(value=spec["init"])
                ttk.Spinbox(left, from_=spec["from"], to=spec["to"],
                            textvariable=var, width=7).grid(row=r, column=1, sticky="ew")
            self._lab_vars[spec["key"]] = var
            r += 1
        ttk.Button(left, text="运行（1000 次蒙特卡洛）",
                   command=lambda: self._run_lab(lab)).grid(
            row=r, column=0, columnspan=2, sticky="ew", pady=8)
        out = ttk.Frame(self._lab_frame)
        out.pack(side="left", fill="both", expand=True, padx=8, pady=6)
        self.lab_out = scrolledtext.ScrolledText(out, width=90, height=30,
                                                 font=("Arial", 11))
        self.lab_out.pack(fill="both", expand=True)
        self.lab_out.insert("1.0",
                            "改左侧参数后点「运行」。\n"
                            "校准锚点见各报告尾部与《瓜岛推演稿-不疯的山本》。\n")

    def _run_lab(self, lab):
        params = {k: (v.get() if isinstance(v, (tk.StringVar, tk.IntVar, tk.DoubleVar))
                      else v) for k, v in self._lab_vars.items()}
        try:
            text = lab.run(params)
        except Exception as e:
            text = f"运行失败: {e}"
        self.lab_out.insert(tk.END, "\n" + text + "\n")
        self.lab_out.see(tk.END)

    # ---------------------------------------------------------------- 背景与设定
    def _show_intro(self):
        self._text_window(f"背景介绍 · {self.scenario_var.get()}",
                          INTROS.get(self.scenario_var.get(), "（暂无）"))

    def _show_settings(self):
        if self._base is None:
            self._load_scenario()
        if self._base is None:
            messagebox.showinfo("提示", "先「载入」一个场景")
            return
        self._text_window(f"设定明细 · {self.scenario_var.get()}",
                          scenario_settings_text(self._base))

    def _text_window(self, title, text):
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("760x560")
        txt = scrolledtext.ScrolledText(win, wrap="word", font=("Arial", 11))
        txt.pack(fill="both", expand=True, padx=6, pady=6)
        txt.insert("1.0", text)
        txt.configure(state="disabled")   # 只读

    # ---------------------------------------------------------------- 舰队编辑
    def _fleet(self, side):
        return self._jp_units if side == "JP" else self._us_units

    def _listbox(self, side):
        return self.jp_list if side == "JP" else self.us_list

    def _refresh_fleet_lists(self):
        for side in ("JP", "US"):
            lb = self._listbox(side)
            lb.delete(0, tk.END)
            for u in self._fleet(side):
                lb.insert(tk.END, f"{u.name} ({u.cls}) hp{int(u.hp)} {u.speed_kt:.0f}节")

    def _load_scenario(self):
        try:
            sc = SC.REGISTRY[self.scenario_var.get()]()
        except NotImplementedError:
            messagebox.showinfo("提示", "该场景数据待回填（同项目 kdocs / GitHub）")
            return
        self._base = sc
        # 官僚主义惩罚旋钮：仅中途岛默认取场景常量，其余场景为 0（可调项，非核心机制）
        c2 = SC.MIDWAY_BUREAUCRACY_PENALTY if self.scenario_var.get() == "中途岛" else 0.0
        self.c2_var.set(c2)
        self.c2us_var.set(0.0)
        self.sens_var.set(1.0)
        # 可见度菜单按场景环境回填
        self.vis_var.set("夜·晴" if sc.night and sc.weather < 0.3 else
                         "夜·雨雾" if sc.night else
                         "昼·薄雾" if sc.weather >= 0.3 else "昼·晴")
        self._jp_units = list(sc.sides[0].units)
        self._us_units = list(sc.sides[1].units)
        self._refresh_fleet_lists()
        self.engine = None
        self._last_snap = None

    def _add_units(self, side):
        if self._base is None:
            messagebox.showinfo("提示", "先「载入」一个场景")
            return
        cls = self.cls_var.get()
        era = self.era_var.get()
        n = max(1, min(20, int(self.num_var.get())))
        fleet = self._fleet(side)
        seq = sum(1 for u in fleet if u.cls == cls)
        tag = "日" if side == "JP" else "美"
        for _ in range(n):
            seq += 1
            fleet.append(catalog.build(side, cls, f"自建{tag}{cls}-{seq}", era))
        self._refresh_fleet_lists()

    def _remove_selected(self, side):
        lb = self._listbox(side)
        sel = lb.curselection()
        if not sel:
            return
        fleet = self._fleet(side)
        for idx in sorted(sel, reverse=True):
            if 0 <= idx < len(fleet):
                fleet.pop(idx)
        self._refresh_fleet_lists()

    def _edit_unit(self, side):
        """双击列表项：编辑单位性能（hp / 航速）——玩家可改取值范围。"""
        lb = self._listbox(side)
        sel = lb.curselection()
        if not sel:
            messagebox.showinfo("提示", "先选中一个单位")
            return
        u = self._fleet(side)[sel[0]]
        win = tk.Toplevel(self)
        win.title(f"编辑性能 · {u.name}")
        ttk.Label(win, text="hp(生命力/机场=完好度):").grid(row=0, column=0, sticky="e")
        hp_v = tk.DoubleVar(value=u.hp)
        ttk.Spinbox(win, from_=1, to=500, textvariable=hp_v, width=8).grid(row=0, column=1)
        ttk.Label(win, text="航速(节):").grid(row=1, column=0, sticky="e")
        sp_v = tk.DoubleVar(value=u.speed_kt)
        ttk.Spinbox(win, from_=0, to=60, textvariable=sp_v, width=8).grid(row=1, column=1)
        ttk.Label(win, text="（弹药/武器暂由模板决定；时代决定质量档）").grid(
            row=2, column=0, columnspan=2)
        def _ok():
            u.hp = max(1.0, hp_v.get())
            u.speed_kt = max(0.0, sp_v.get())
            self._refresh_fleet_lists()
            win.destroy()
        ttk.Button(win, text="确定", command=_ok).grid(row=3, column=0, columnspan=2)

    # ---------------------------------------------------------------- 推演控制
    def _build_scenario(self) -> M.Scenario:
        """用当前双方编成 + 全局旋钮构造引擎场景：deepcopy 保证可反复开局。
        旋钮：可见度→night/weather；官僚→c2_penalty(JP/US)；探测倍率→传感器范围缩放。"""
        base = self._base
        jp_units = copy.deepcopy(self._jp_units)
        us_units = copy.deepcopy(self._us_units)
        mult = self.sens_var.get()
        for u in jp_units + us_units:
            for s in u.sensors:
                s.active_range_nm = s.active_range_nm * mult
        _spread(jp_units, 0.0)
        _spread(us_units, 9000.0)
        for units, x in ((jp_units, 0.0), (us_units, 9000.0)):
            for u in units:
                if u.cls == "AF":
                    u.pos = (x, 5000.0)
        night, weather = VIS_MAP.get(self.vis_var.get(), (True, 0.0))
        bjp, bus = base.sides[0], base.sides[1]
        jp = M.Side("JP", jp_units, doctrine=bjp.doctrine,
                    c2_penalty=round(self.c2_var.get() / 0.05) * 0.05,
                    reinforcements=copy.deepcopy(bjp.reinforcements))
        us = M.Side("US", us_units, doctrine=bus.doctrine,
                    c2_penalty=round(self.c2us_var.get() / 0.05) * 0.05,
                    reinforcements=copy.deepcopy(bus.reinforcements))
        return M.Scenario(f"{base.name}(自定义)", base.mission, [jp, us],
                          seed=42, night=night, weather=weather,
                          objective=base.objective)

    def _start(self):
        if self._base is None:
            self._load_scenario()
        if not self._jp_units or not self._us_units:
            messagebox.showinfo("提示", "双方舰队均需至少 1 个单位")
            return
        sc = self._build_scenario()
        self._scenario = sc
        self.engine = Engine(sc, seed=42, step_sec=30)
        self._last_snap = None
        self.log.insert(tk.END, f"=== 推演开始：{sc.name}  "
                                f"日 {len(sc.sides[0].units)} 单位 / "
                                f"美 {len(sc.sides[1].units)} 单位 ===\n")
        self._draw()

    def _step(self, n=1):
        if not self.engine:
            messagebox.showinfo("提示", "先点「开始」")
            return
        for _ in range(n):
            snap = self.engine.step()
            self._last_snap = snap
            jp_dead = sum(1 for u in self._scenario.sides[0].units if not u.alive)
            us_dead = sum(1 for u in self._scenario.sides[1].units if not u.alive)
            self.log.insert(tk.END, snap["report"] + "\n")
            self.log.insert(tk.END,
                f"  >> 战果: 日沉 {jp_dead} / 美沉 {us_dead}"
                + ("  [战斗结束]" if snap.get("over") else "") + "\n")
            if snap.get("over"):
                self.log.insert(tk.END,
                    f"  >> 结局判定: {outcome_cn(snap.get('outcome'))}\n")
                break
        self.log.see(tk.END)
        self._draw()

    # ---------------------------------------------------------------- 海图
    def _draw(self):
        self.canvas.delete("all")
        if not hasattr(self, "_scenario"):
            return
        # 自适应缩放：取双方单位极大坐标，映射到画布（留边，不放大只缩小）
        xs = [u.pos[0] for s in self._scenario.sides for u in s.units]
        ys = [u.pos[1] for s in self._scenario.sides for u in s.units]
        max_x = max((abs(v) for v in xs), default=1.0) or 1.0
        max_y = max((abs(v) for v in ys), default=1.0) or 1.0
        W, H, M = 380, 300, 30
        sx = (W - 2 * M) / (2 * max_x) if max_x > 0 else 1.0
        sy = (H - 2 * M) / (2 * max_y) if max_y > 0 else 1.0
        s = min(sx, sy, 1.0)
        tx = lambda px: W / 2 + px * s
        ty = lambda py: H / 2 + py * s
        # 舰船状态图元（engaged/withdrawing/routed/destroyed 分色）
        for side in self._scenario.sides:
            for u in side.units:
                draw_status_token(self.canvas, tx(u.pos[0]), ty(u.pos[1]),
                                  side.name, u.status,
                                  label=f"{u.name[:4]}{int(u.hp)}")
        # 接触不确定菱形（鱼叉式：观测方颜色 + 虚线 + 不确定度决定大小）
        snap = getattr(self, "_last_snap", None)
        if snap:
            for c in snap.get("contact_points", []):
                draw_contact_diamond(self.canvas, tx(c["tgt_pos"][0]),
                                     ty(c["tgt_pos"][1]), 7.0,
                                     c["uncertainty"], side_color(c["obs"]))
        draw_legend(self.canvas)
        if snap and snap.get("over"):
            self.canvas.create_text(W / 2, H - 14,
                text="结局: " + outcome_cn(snap.get("outcome", "")),
                font=("Arial", 12, "bold"), fill="#222222")

    # ---------------------------------------------------------------- 自检
    def _self_test(self):
        """--smoke 全流程自检：载入→加舰(时代)→删舰→编辑→开局→推 2 步→设定文本→实验室运行。
        结果写 _selftest_result.txt（windowed exe 的 stdout 不可见）。"""
        result = []
        try:
            self._load_scenario()
            n0 = len(self._jp_units)
            self.cls_var.set("CA")
            self.num_var.set(2)
            self.era_var.set(catalog.ERAS[1])          # fork 时代
            self._add_units("JP")
            assert len(self._jp_units) == n0 + 2, "加舰失败"
            self.jp_list.selection_set(0)
            self._remove_selected("JP")
            assert len(self._jp_units) == n0 + 1, "删舰失败"
            n0u = len(self._us_units)
            self.us_list.selection_set(0)
            self._remove_selected("US")
            assert len(self._us_units) == n0u - 1, "美方删舰失败"
            self._start()
            assert len(self.engine.scenario.sides[0].units) == n0 + 1, "引擎未吃用户编成(JP)"
            assert len(self.engine.scenario.sides[1].units) == n0u - 1, "引擎未吃用户编成(US)"
            self._step(2)
            assert scenario_settings_text(self._scenario), "设定明细为空"
            r = gunnery_lab.run({"gun": "US 16in", "range_km": 7, "vis": "夜·有雷达",
                                 "surprise": "是", "target": "BB", "shells": 200})
            assert "23." in r or "24." in r or "22." in r, "炮战实验室锚点漂移"
            result.append(f"GUI_SELFTEST_OK  JP={len(self.engine.scenario.sides[0].units)} "
                          f"US={len(self.engine.scenario.sides[1].units)}")
        except Exception as e:
            result.append(f"GUI_SELFTEST_FAIL: {e}")
        finally:
            with open("_selftest_result.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(result) + "\n")
            self.after(100, self.destroy)


def main(smoke: bool = False):
    """smoke=True：自动跑全流程自检后关窗（打包 exe 后验证用）。"""
    app = App()
    if smoke:
        app.after(400, app._self_test)
    app.mainloop()


if __name__ == "__main__":
    import sys as _sys
    main(smoke=("--smoke" in _sys.argv))
