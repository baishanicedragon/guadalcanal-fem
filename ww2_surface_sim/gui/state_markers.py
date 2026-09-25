# -*- coding: utf-8 -*-
"""海图单位状态标记（纯 Tkinter Canvas，零依赖）。
初稿由本地 Ollama(qwen3:1.7b) 起草、主代理审校定稿（双管齐下策略）。

四种交战状态分色区分（对应 engine 的 Unit.status）：
  engaged     接战      —— 实心三角（己方色）
  withdrawing 指挥官专业撤离 —— 空心三角（有序撤退，非士气溃散）
  routed      溃散      —— 灰色阴影三角 + 红字（士气崩溃、失控脱离、不可重整）
  destroyed   沉没      —— 灰色 X
"""
def status_color(side: str) -> str:
    if side == "JP":
        return "#c0392b"
    if side == "US":
        return "#2980b9"
    return "#555555"


def draw_status_token(canvas, cx: float, cy: float, side: str,
                      status: str, label: str = None):
    col = status_color(side)
    half_w, half_h = 7, 9
    pts = [(cx, cy - half_h), (cx + half_w, cy + half_h), (cx - half_w, cy + half_h)]
    if status == "destroyed":
        canvas.create_line(cx - 6, cy - 6, cx + 6, cy + 6, fill="#888888", width=1)
        canvas.create_line(cx - 6, cy + 6, cx + 6, cy - 6, fill="#888888", width=1)
        return
    if status == "routed":
        canvas.create_polygon(pts, outline="#a00000", width=1,
                              fill="#bbbbbb", stipple="gray50")
        canvas.create_text(cx, cy + half_h + 6, text="溃",
                          font=("Arial", 8), fill="#a00000")
        return
    if status == "withdrawing":
        # 空心三角（白填充=透明，仅留轮廓）：有序撤离，非士气溃散
        canvas.create_polygon(pts, outline=col, width=1, fill="white")
        canvas.create_text(cx, cy + half_h + 6, text="撤",
                          font=("Arial", 8), fill=col)
        return
    # engaged
    canvas.create_polygon(pts, outline="#222222", width=1, fill=col)
    if label:
        canvas.create_text(cx, cy + half_h + 6, text=label,
                          font=("Arial", 8), fill=col)


def draw_legend(canvas, x: int = 6, y: int = 6):
    """左上角图例：四种状态 + 接触菱形含义。"""
    rows = [
        ("■ 接战", "#2980b9"),
        ("□ 专业撤离", "#2980b9"),
        ("▦ 溃散", "#a00000"),
        ("✕ 沉没", "#888888"),
    ]
    for i, (txt, c) in enumerate(rows):
        canvas.create_text(x, y + i * 14, text=txt, font=("Arial", 9),
                          fill=c, anchor="nw")


_OUTCOME_CN = {
    "JP_win": "日方胜利",
    "US_win": "美方胜利",
    "draw": "平局",
    "mutual_defeat": "双方惨败",
    "ongoing": "交战中",
}


def outcome_cn(outcome: str) -> str:
    return _OUTCOME_CN.get(outcome, outcome)
