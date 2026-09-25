# 二战水面战舰模拟游戏（ww2_surface_sim）

**免装 Python、双击即玩的可执行版**，同时附完整 Python 源码与命令行入口。
本仓库前期的舰炮/鱼雷/空战 FEM 弹道计算内容已降级为旧版本文档，见 [`docs/README_v1_fem_compute.md`](docs/README_v1_fem_compute.md)——它们现在是本游戏的物理引擎底层。

---

## 快速开始（EXE，免装 Python）

`dist/` 下两个独立可执行（PyInstaller onedir，各约 26MB，整个文件夹拷走即可在别的 Windows 机器运行）：

| 文件 | 用途 |
|---|---|
| `dist/ww2_surface_sim/ww2_surface_sim.exe` | **GUI 完整版**（双击启动窗口） |
| `dist/ww2_cli/ww2_cli.exe` | CLI 控制台版（cmd 运行） |

```bat
:: GUI 自检（窗口 0.8s 自开自关，验证运行时）
ww2_surface_sim.exe --smoke

:: CLI 无头推演（场景英文别名 guadao / midway / tarawa）
ww2_cli.exe --headless --scenario midway --ticks 80 --seed 42

:: CLI 交互推演
ww2_cli.exe --cli --scenario guadao
```

> ⚠️ 360 等国产杀软对无签名 PyInstaller exe 常见误报，请把 `dist/` 加入白名单。

## GUI 玩法

1. **模块菜单**：完整战役 / 炮战实验室 / 鱼雷对决 / 航空战（四个可独立加载的模块）
2. **完整战役**：选场景 →「背景」看战役介绍 →「设定」看全参数明细 → 双击舰种目录向日/美双方舰队增删（开局即用你的编成）→ 开始 → 单步 30s / 快进 ×10
3. **实验室模块**：参数面板 + 1000 次蒙特卡洛，报告带史实锚点校准注释

## 三个示例战役（背景介绍内置于游戏）

| 场景 | 设定 | 学说锚点 |
|---|---|---|
| **瓜岛·不疯的山本** | 1942-11 夜战，萨沃岛反事实推演 | FEM 炮战/鱼雷模型 + 泗水海战校准（齐射命中率 0.31%） |
| **中途岛·史实编成** | 1942-06-04，日方 `bait_operation`（山本诱饵战）+ 无雷达脆弱性 | 「必败者主动求败的自导自演」读法：正史九处狭缝（换弹混乱/警戒机不足/机库汽油） |
| **塔拉瓦 1943末 fork** | **瓜岛胜利后的理想日本**（假定值）：金星零战 + 练度未损 + 雷达上舰，航空战力 ×1.3 | `hold_airfield` 战役目标：机场完好度决定战略判定 |

「设定」面板 / CLI `settings` 命令披露全部明细：可见度、官僚水平（c2_penalty）、探测能力（传感器/范围/可靠性）、舰艇性能（舰种×数量×hp×航速×武器射程射速×弹药）、增援 tick。

## 三个实验室子模块（可独立加载，`python main.py --lab gunnery|torpedo|air`）

| 模块 | 学习点 | 史实锚点（已校准） |
|---|---|---|
| **炮战** gunnery | 命中率 × 距离 × 能见度 × 雷达 × 奇袭窗口 × 目标舰种 | 华盛顿-雾岛 7km 夜雷达奇袭齐射 23.7%（史实 20-27%）；泗水 1619 发→5.2 命中（史实 5） |
| **鱼雷** torpedo | 93式酸素 vs Mk15 引信灾难/修复、队形/航速/能见度 | 同距 8km：93式 9.3% vs Mk15 mod0 0.8%（11.5 倍差）；DD 一雷沉 / BB TDS 7.8% |
| **航空** air | 机型代差空战交换比；CAP 拦截 → 防空 → 命中链 | 零战二一 vs F4F 交换比 1.42；CAP 24 架拦截 20 攻击机 90% |

## 自定义战役（对标鱼叉的"可学习"沙盒）

- **时代选择**：1942 史实（Mk15 引信灾难 0.07 / 零战二一 / F4F / 日方纯光学）、**1943 fork·理想日本**（金星零战 0.92 / 日方雷达上舰 / Mk15 mod3 修复 0.45 / F6F）、1944 后期（日精英损耗 0.72）
- **旋钮**：可见度（昼晴/昼雾/夜晴/夜雨雾）、官僚水平（日/美双滑杆，0~0.4）、探测倍率（0.5~2.0）
- **单位编辑**：双击舰队列表项直接改 hp / 航速
- **增援波次**：到 `arrive_tick` 整批入场

## 引擎机制（30s/tick，六阶段 + 摩擦耦合）

```
P1 机动 → P2 索敌 → P3 火控 → P4 交战 → P5 损伤 → P6 撤退/重整
  └─ fog/comms/visibility 共享潜变量（uncertainty.py 多维耦合不确定性）
```

- **溃散(routed) ≠ 专业撤离(withdrawing)**：士气崩溃不可重整 vs 指挥官基于损失比(≥50%)或战力比(<0.6)的有序撤出——两条独立状态
- **对称结局**：规则双方同等生效；双方主力损失均≥40% → 双方惨败，损失差≤15% → 平局
- **官僚主义 = 可调旋钮非核心**：`Side.c2_penalty` 折减探测与火控（中途岛 c2=0.25 时日方从 4:10 胜变 20:0 惨败——方向符合"IJN 发挥不当源于官僚主义"）
- **机场毁伤**：AF 单位 hp=完好度%，鱼雷无效、<30% 出击节流；战役层 `hold_airfield` 目标判定
- **增援**：`Reinforcement(arrive_tick, units)` 到点从本方质心后方入场

## 从源码运行 / 打包

```bash
cd ww2_surface_sim
python main.py                          # Tkinter GUI
python main.py --cli --scenario 塔拉瓦   # 命令行交互（step/run N/status/airfields/settings/outcome）
python main.py --headless --scenario 瓜岛 --ticks 60 --seed 42   # 无头可复现
python _diag_outcome.py                 # 三场景终局分布 + 官僚主义旋钮对比
```

```bash
# PyInstaller 打包（需含 tkinter 的 Python；venv 场景需设 TCL_LIBRARY 指向系统 Python 的 tcl 目录）
pyinstaller --noconfirm --windowed --name ww2_surface_sim --collect-all tkinter --hidden-import _tkinter main.py
pyinstaller --noconfirm --console  --name ww2_cli           --collect-all tkinter --hidden-import _tkinter main.py
```

## 目录结构

```
ww2_surface_sim/
├── main.py              # 入口：GUI / CLI / 无头 / 实验室
├── FRAMEWORK.md         # 架构设计文档（v0.9）
├── run_cli.bat / run_headless.bat
├── sim/
│   ├── model.py         # Unit/Side/Weapon/Sensor/Rules/Reinforcement
│   ├── engine.py        # 30s tick 六阶段引擎 + 对称结局 + 战役层
│   ├── uncertainty.py   # 多维耦合不确定性（共享潜变量摩擦）
│   ├── fem_bridge.py    # FEM 弹道模型桥接（炮/雷/空命中率）
│   ├── scenarios.py     # 三战役 OOB（含机场与增援）
│   ├── catalog.py       # 时代化舰种目录（1942/1943fork/1944）
│   ├── intros.py        # 战役背景介绍 + 设定明细披露
│   ├── gunnery_lab.py / torpedo_lab.py / air_lab.py   # 三实验室
│   └── ...
└── gui/
    ├── app.py           # Tkinter 主程序（模块选择/编成/旋钮/海图）
    ├── chart_helpers.py # 海图图元（舰三角 + 鱼叉式不确定菱形）
    └── state_markers.py # 状态分色图元 + 结局映射
```

## 旧版本（FEM 弹道计算）

v1 的独立 Python 脚本群（舰炮命中率、鱼雷命中、空战 FEM 计算）移至 `docs/README_v1_fem_compute.md` 所述位置，其物理模型经 `sim/fem_bridge.py` 桥接进本游戏引擎。
