# 二战水面战舰模拟游戏 · 软件框架（v0.9 模块化）

> 完全合法、开源、带 GUI 的二战水面战舰模拟游戏。
> 与 GitHub `ww2-naval-battle-compute` 是**同一个项目**：本框架复用其 FEM 命中率模块，
> 并补上"战役循环"缺失的两层（探测门控 + 火控解算质量），外加 WWII 专属的多维耦合不确定性。

---

## 1. 设计目标与边界

- **合法**：只用公开资料与用户自有数据（金山文档反事实推演、GitHub FEM），不接触任何商业游戏二进制。
- **零依赖**：仅 Python 标准库（`dataclass` / `tkinter` / `random` / `math`）。与仓库铁律一致。
- **可复现**：所有随机性走 `engine.rng`（固定 `seed`），每发必落表，命中率 ∈ [0,1]。
- **数据驱动**：场景/OOB 集中在 `sim/scenarios.py`，可审计、可改写。

## 2. 架构（目录）

```
ww2_surface_sim/
├── main.py              # 入口（GUI / --headless）
├── FRAMEWORK.md         # 本文件
├── sim/
│   ├── model.py         # 数据模型：Unit / Weapon / Sensor / Side / Scenario + 口径因子
│   ├── uncertainty.py   # ★ WWII 多维耦合不确定性（与鱼叉的根本区别）
│   ├── fem_bridge.py    # 交战命中率桥接：优先用 gunnery_fem 等，否则内置简化底
│   ├── engine.py        # 30s tick 引擎：6 阶段（机动→索敌→火控→交战→损伤→撤退）+ 阶段报告
│   └── scenarios.py     # OOB：瓜岛(完整) / 中途岛(锚定金山专文·bait_operation) / 塔拉瓦(GitHub fork)
└── gui/
    ├── chart_helpers.py # 海图图元：舰三角 + 鱼叉式不确定菱形（本地 Ollama 起草/主代理审校）
    ├── state_markers.py # 单位状态分色：engaged/withdrawing/routed/destroyed（本地 Ollama 起草/审校）
    └── app.py           # Tkinter：场景/任务/单位选择 + 单步/快进 + 海图 + 阶段日志 + 官僚主义滑杆 + 结局横幅
```

## 3. 30 秒 tick 的 6 个阶段（对应鱼叉公开逻辑 + 你的 FEM）

| 阶段 | 引擎方法 | 来源 / 说明 |
|------|----------|-------------|
| P0 阵位机动 move | `_phase_move` | 接敌：朝敌质心逼近到 ~3.5km 炮战距离后保持阵位；撤退单位反向脱离（逃跑照样被追上击沉）。每船每 tick 仅漂移一次士气。 |
| P1 索敌 search | `_phase_search` | 鱼叉 rule 5.0：每传感器探测，主动/被动，接触分级。**本框架加入探测不稳定**。 |
| P2 火控解算 fire_ctl | `_phase_fire_control` | 鱼叉 rule 6.3：解算质量 Good/Fair/Poor。本框架用火控质量折减命中率。 |
| P3 交战命中 engage | `_phase_engage` | 调 `fem_bridge` 拿干净底 × 多维不确定性 × 火控质量。 |
| P4 损伤 damage | `_phase_damage` | HP/进水/炮塔/士气/击沉；口径因子（8in=1.0/5in=0.40/18in=2.8）。被命中/目睹同袍沉没→心态受冲击（每目标每 tick 封顶）。 |
| P5 撤退/溃散 retreat | `_phase_retreat` | **两类退出接触严格分离**：(1) 溃散 routed=士气崩（不可控、脱离战场、不可重整）；(2) 指挥官专业撤离 withdrawing=基于本方主力损失/战力比判断"不划算"而有序撤出（专业决策、非士气问题；敌已无接战能力则可回收阵位）。双方对称生效。 |
| 阶段报告 | `step().report` | 每轮产出人类可读的「索敌/火控/交战/撤退」摘要，GUI 日志与无头均可消费。 |

> **关键修正（v0.2）**：早期版本有两个致命 bug——(1) `morale_step` 在火控循环里"每接触调用一次"导致士气一 tick 被打崩、全军误撤；
> (2) 无机动模型导致双方永远够不着、或一方撤退后变成无敌僵局。已通过"每船每 tick 一次士气漂移（向高基准回中，仅交火事件下拉）"+
> "P0 机动 + 撤退目标仍可被瞄准击沉 + `is_over()` 结束判定"修复。现无头 60 tick 内可复现地分出胜负。
>
> **关键修正（v0.3 · 多场景收尾）**：接入中途岛/塔拉瓦后暴露三个结构性缺陷，已修复——
> (1) **航母对峙死局 / 航空 inert**：航母只挂 `aerial_*` 武器，原被引擎跳过。v0.4 已把
> `aerial_torpedo` / `aerial_bomb` 接入 P3 交战（飞机飞抵目标、与舰间距解耦），并新增守军
> CAP 拦截折减 `_cap_factor`；`is_over().can_fight` 纳入 `aerial_torpedo`/`aerial_bomb`，
> 纯战斗机(aircraft)仅提供 CAP、不计入战斗力（不能击沉敌舰，避免"双方仅剩战斗机"死局）。
> (2) **永久撤退级联**：先手优势瞬间放大成全灭（太假、也不符"实战反复"）。增加 P5 重整：士气回升且未重创可重新接敌。
> (3) **伤害体积爆炸**：129 单位对"所有探测目标"齐射 → 2 分钟一边倒。改为每射击方每 tick 仅锁定最近 2 个目标（`MAX_TARGETS_PER_SHOOTER`）。
> 现三场景均能在 12–30 tick 干净结束、双向均有交火、航母会真正被舰载机击沉。
>
> **关键修正（v0.4 · 航空整合 + 海图）**：P3 接入航空兵（见上）；GUI 海图改用 `gui/chart_helpers`
> 的鱼叉式图元（`draw_ship_token` 舰三角 + `draw_contact_diamond` 不确定菱形 exact/area/bearing_only），
> 引擎 `_snapshot` 暴露 `contact_points`（含观测方/目标坐标与不确定度分级）供菱形渲染。初稿由本地
> Ollama(qwen3:1.7b) 起草 `chart_helpers`，主代理审校修正后定稿（呼应"发动本地 AI 写低难度代码"）。
> **已知平衡现象（非 bug，属校准范畴）**：三场景实测 US 方均因士气崩溃"全撤"收场（JP 口径/九三式
> 鱼雷优势 + 先手命中拉低 US 士气）。校准旋钮见第 7 节 #3。
>
> **关键修正（v0.5 · 溃散/专业撤离分离 + 对称结局 + 官僚主义旋钮）**：用户设计铁律——严肃海上
> 模拟在双方约束对称生效时，结局应偏向「平局 draw」或「双方惨败 mutual_defeat」而非一方干净获胜；
> 且"指挥官判断不利撤离"是专业决策，不能等同于"士气低下溃散"。落地：
> (1) **状态二分**（`model.Unit`）：`routed`（士气崩溃、不可控、不可重整）与 `withdrawing`
> （指挥官基于本方主力损失≥50% 或战力比<0.6 有序撤离、敌无接战能力时可重整）彻底分离；P5 同时
> 判定两类，对双方对称（`rules.symmetric`）。(2) **对称结局分类**（`engine.outcome()`）：双方均无
> 接战能力时，双方主力损失均≥40% → 双方惨败；损失差≤15% → 平局；否则损失小的一方胜。
> `is_over()` 改用 `_can_fight`（存活+未溃散+未撤离+有可开火武器）。(3) **官僚主义作为可调旋钮**
> （非核心）：`Side.c2_penalty`（默认 0）经 `_c2()` 折减 JP 探测与火控质量；中途岛默认取场景常量
> `MIDWAY_BUREAUCRACY_PENALTY=0.0`，GUI 滑杆可调 0~0.4 模拟"狭缝"条令混乱导致的发挥不当。用户判定：
> 官僚主义是历史副因，应可关可开，不进核心机制。(4) **GUI 同步**（双管齐下：本地模型起草、主代理审校）：
> 新增 `gui/state_markers.py` 四类分色图元 + 图例；`app.py` 海图按 `u.status` 分色、显示结局横幅、
> 加"官僚主义惩罚(JP)"滑杆（开始即写入 `side.c2_penalty`）。
>
> **关键修正（v0.6 · 全战斗模型收口 + 命令行可玩）**：按用户"先把所有战斗模型做完"的要求，
> 补上最后两块，并把命令行做成第一可玩界面（GUI 暂缓打磨）：
> (1) **机场毁伤模型（#5）**：机场以 `Unit(cls="AF")` 表示（固定不动、`hp`=完好度%）；岸轰/空袭
> 降其完好度（鱼雷对固定机场无效，已在 P3 跳过；炮/炸弹/空袭可毁），完好度<30% 时 P3 对其出击
> 波次节流（跑道/机库被毁→出动率下降），完好度=0 视为机场失能。瓜岛(亨德森/布干维尔)、中途岛
> (守军/岸基航空队改为 AF)、塔拉瓦(贝蒂奥/马金)均已落地。
> (2) **战役层（#6）**：`Side.reinforcements`（`Reinforcement(arrive_tick, units)`）到 tick 整批
> 入场（从本方质心后方加入）；`Scenario.objective` 驱动 `engine.campaign_result()` 战略判定——
> `hold_airfield`（双方控机场→contested / 一方控→该方战略胜 / 皆失→stalemate）、`annihilate`/
> `breakthrough` 直接采用对称战术结局。塔拉瓦设为 `hold_airfield`。
> (3) **命令行可玩**：`main.py --cli` 交互推演（step / run N / status / airfields / outcome / quit），
> 无头加 `--report` 打印每 tick 五段报告；结束打印战术+战役判定。GUI 暂缓（环境/打磨留待后续）。
> 注：本版迭代时沙箱 shell 因权限黑箱暂不可用，未能本地实跑；代码经静态核对，shell 恢复后
> `python -m py_compile main.py sim/*.py gui/*.py` 与 `python main.py --cli --scenario 瓜岛` 即可验证。

## 4. ★ 二战专属「多维耦合不确定性」（`uncertainty.py`）

这是用户强调的、与鱼叉（现代 C4ISRK 稳定链）的根本区别：

```
Friction（每 tick 共享潜变量 fog / comms / visibility）
   ├─ 探测不稳定  → detection_modifier（夜战光学极不稳、早期雷达受扰）
   ├─ 心态不稳定  → morale_step（向高基准回中，仅被命中/目睹沉没下拉） + fire_control_modifier
   ├─ 武器质量浮动 → weapon_lot_factor（九三式≈0.80 / Mk-15≈0.07 伯努利 + 火药批差）
   └─ 炮弹散步    → 被上面放大（disp_mult 进 fem_bridge）
```

关键点：**不是独立乘系数**，而是共享一个 `fog` 潜变量 → 探测差→火控糙→命中差、士气低→早撤，
互相耦合。这正是"参谋推演再漂亮，实战也未必好"的量化落地。

## 5. 与已有资料/数据的对接

- **GitHub FEM**：`fem_bridge.gunnery_hit_rate` 优先 `from gunnery_fem import clean_floor`；
  同仓库运行时自动启用真实弹道底，否则退回内置简化底（量级对齐）。
- **金山文档《瓜岛推演稿-不疯的山本》**：单位编成表 → `scenarios.guadalcanal()` 已完整填充
  （大和/日向/伊势/扶桑/山城/金刚/榛名/鸟海/衣笠/北上/大井/日驱×6，
  华盛顿/南达科他/旧金山/海伦娜/亚特兰大/美驱×5），口径因子、TDS 贯穿思路已落地。
- **塔拉瓦**：`tarawa()` 已从 GitHub `baishanicedragon/ww2-naval-battle-compute`
  （`src/joint_tarawa_wargame.py` + `cases/tarawa_1943_fork/`）回填，取 fork 1943-11 基线兵力
  （含水面 + 航空兵两套，IJN 超大和级/金刚级/九三式/陆攻队/驻扎零战等），mission=`land_based_aviation`。
- **中途岛**：`midway()` 已锚定金山文档专文（kdocs MCP 已注入，本会话读取）——JP doctrine=`bait_operation`
  （山本自导自演诱饵战），日航母仅配 optical 传感器（无雷达→机库致命点脆弱性）；US doctrine=`carrier`
  （破译+舰载机收割）。OOB 仍为史实编成（赤城/加贺/苍龙/飞龙 + 美三航母 + 守军航空队），昼战晴天，
  mission=`carrier`。学说落点仅改 doctrine 与注释出处，不动史实编成（用户在正典优先级中明确"最新口径为准"）。

## 6. 运行

**命令行（推荐，无需 GUI / 显示器，最适合"命令行可玩"）**

```bash
cd ww2_surface_sim
run_cli.bat            # 双击：交互推演，默认瓜岛；可带参 run_cli.bat midway
run_headless.bat       # 双击：无头跑塔拉瓦并打印每 tick 五段报告
# 或直接在 cmd / Git Bash 里：
python main.py --cli --scenario guadao          # 交互推演（step/run N/status/airfields/outcome/quit）
python main.py --headless --scenario tarawa --ticks 80 --report   # 无头，打印每 tick 报告 + 结局
```

> **场景英文别名**（bat 用别名规避中文编码乱码）：`guadao`=瓜岛、`midway`=中途岛、`tarawa`=塔拉瓦（单字母 `g`/`m`/`t` 亦可）；直接传中文 `瓜岛` 也行。
> CLI 子命令：`step`(推 1 tick) / `run N`(连推 N tick) / `status`(全单位状态) / `airfields`(机场完好度) / `outcome`(战术+战役判定) / `quit`。

**GUI（需桌面标准 Python，tkinter 为内置库）**

```bash
cd ww2_surface_sim
python main.py                                  # 启动 Tkinter GUI
python main.py --smoke                          # GUI 自检：窗口自动开-关（验证运行时）
```

GUI：选场景/任务 → 双击把单位加入"我方舰队" → 开始 → 单步 30s / 快进 ×10，海图与日志实时刷新；
日志每轮打印 `索敌→火控→交战(武器×命中)→撤退` 五段摘要，符合"每 30 秒推算一轮"的需求。

> 注意：Tkinter 在部分精简 Python 构建里缺失（本沙箱即如此），无头模式不受影响；GUI 在你本机标准 Python 下可直接运行。

**独立可执行版（免装 Python，双击即玩）**

```
dist/ww2_surface_sim/ww2_surface_sim.exe   # GUI 完整版（双击启动窗口，无黑框）
dist/ww2_cli/ww2_cli.exe                   # CLI 控制台版（cmd 里跑：ww2_cli.exe --cli --scenario midway）
```

- PyInstaller onedir 打包（各约 26MB，`--collect-all tkinter` 显式捆绑 Tcl/Tk 运行时）；
- 打包环境：系统 Python 3.13.0（含 tkinter）venv + 清华镜像装 pyinstaller；
- `--smoke` 自检参数已打进 exe（结果写 `_selftest_result.txt`，windowed 无 stdout）；
- ⚠️ 360 等国产杀软对无签名 PyInstaller exe 常见误报，可把 `dist/` 加入白名单；
- ⚠️ 重打包前先 `mv dist dist_old`（沙箱安全删除拦截会挡 PyInstaller 清理大目录）。

## 6b. 模块化子模块（v0.9，对标鱼叉的学习价值）

**实验室（可独立加载，`python main.py --lab <name>` 或 GUI 顶部"模块"菜单）**

| 模块 | 文件 | 学习点 | 校准锚点 |
|---|---|---|---|
| 炮战实验室 | `sim/gunnery_lab.py` | 命中率×距离×能见度×雷达×奇袭窗口×目标舰种 | 泗水 0.31%@15-18km；华盛顿-雾岛 7km 奇袭 20-27%（齐射口径，模型 23.7%） |
| 鱼雷对决 | `sim/torpedo_lab.py` | 93式 vs Mk15 引信灾难/修复；齐射/航速/队形/能见度 | 93式近距奇袭 12-15% / 远距 2.5-3.5%；DD 一雷沉 / BB TDS 7.8% |
| 航空战 | `sim/air_lab.py` | 机型代差空战交换比；CAP 拦截→防空→命中链 | 零战二一 vs F4F 交换比 1.42；干净底 96% 贴脸 vs 实战 10-20% |

每个实验室暴露 `PARAMS`（GUI 参数表）+ `run(params)->str`（1000 次蒙特卡洛）+ `interactive()`（CLI）。

**完整战役的参数披露与自定义（用户要求"像鱼叉那样能学东西"）**
- 「设定」按钮 / CLI `settings` 命令：可见度、官僚水平(c2_penalty)、探测能力
  （传感器型号/范围/可靠性）、舰艇性能明细（舰种×数量/hp/航速/武器射速射程可靠度/弹药/增援）全表披露；
- 「背景」按钮 / CLI 开局：三战役背景介绍（口径来自用户文档：《瓜岛推演稿-不疯的山本》
  《男主中途岛观点概括》《正史狭缝论证》、GitHub fork 基线）；
- 自定义战役：时代选择（1942史实 / 1943fork·理想日本=金星零战+雷达上舰+Mk15修复 /
  1944后期=日精英损耗）、可见度菜单（昼晴/昼雾/夜晴/夜雨雾）、官僚水平双侧滑杆、
  探测倍率(0.5~2.0)、双击舰队列表项直接改单位 hp/航速。

## 7. 下一步（按优先级）

1. ~~**中途岛换 kdocs 专文**~~ ✅ 已完成：`midway()` 锚定金山文档《红色联盟-男主中途岛观点概括》+《正史狭缝论证》，JP=`bait_operation`、日航母 optical only，OOB 仍史实编成。
2. ~~**航母/基地航空兵任务**~~ ✅ 已完成：`aerial_torpedo`/`aerial_bomb` 接入 P3（飞机飞抵目标、与舰间距解耦），新增 `_cap_factor` 守军 CAP 拦截；`is_over().can_fight` 纳入 `aerial_*`、纯战斗机仅提供 CAP；`fem_bridge.aerial_torpedo_hit_rate` 已落地。三场景实测航母会被舰载机真正击沉。
3. **平衡校准（用户兵棋设计活儿）**：v0.5 已将"士气全撤"拆为 rout(崩溃) 与 withdrawing(专业撤离)，并加对称结局分类——原"US 全撤"误标已消解：现在 US 撤离会按主力损失比例被公正判为「美方失利 / 平局 / 双方惨败」，而非单方面溃逃。若想让战斗更多由"击沉"而非"撤离"收场，可调 `Rules.commander_withdraw_cap_loss`(0.50)/`commander_withdraw_pow_ratio`(0.60) 或 `uncertainty.morale_step` 被命中士气惩罚(0.04/0.06)；要让双方更对称，可给 JP 设 `c2_penalty`（官僚主义惩罚）抵消其口径/九三式优势。其余旋钮：`MAX_TARGETS_PER_SHOOTER`、`_phase_damage` 的 `dmg` 系数、`CALIBER_FACTOR`、`Sensor.reliability`、开局间距 `_spread`、航空攻击波 `shots=4`、`_cap_factor` 斜率(0.004)。
4. ~~**海图升级**~~ ✅ 已完成：GUI 改用 `gui/chart_helpers` 鱼叉式图元（舰三角 + 不确定菱形 exact/area/bearing_only）+ `gui/state_markers` 四类状态分色（接战/撤离/溃散/沉没）+ 图例 + 结局横幅；引擎 `_snapshot` 暴露 `contact_points` 与 `outcome`。
5. ~~**机场毁伤模型**~~ ✅ 已完成：机场= `Unit(cls="AF")`（固定、hp=完好度%），P3 鱼雷对机场无效、炮/炸弹可毁，完好度<30% 出动率节流、=0 失能；瓜岛/中途岛/塔拉瓦均含 AF。
6. ~~**撤退判定接战役层**~~ ✅ 已完成：`Side.reinforcements` 到 tick 整批入场；`Scenario.objective` + `engine.campaign_result()` 战略判定（hold_airfield / annihilate / breakthrough）；塔拉瓦=hold_airfield。
