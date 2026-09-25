# -*- coding: utf-8 -*-
# 海图图元绘制助手（纯 Tkinter Canvas，无第三方依赖）。
# 初稿由本地 Ollama(qwen3:1.7b) 起草，主代理审校修正（stipple 未定义 NameError、
# 舰首朝向、出处标注）后定稿。
def draw_ship_token(canvas, cx, cy, color, alive, label=None):
    """在画布坐标 (cx, cy) 画一艘舰的小三角形（舰首朝上），底边宽 14、高 18，以 (cx, cy) 为中心。"""
    half_w, half_h = 7, 9
    pts = [
        (cx, cy - half_h),            # 舰首（朝上）
        (cx + half_w, cy + half_h),   # 右下
        (cx - half_w, cy + half_h),   # 左下
    ]
    if alive:
        canvas.create_polygon(pts, outline="#222222", width=1, fill=color)
    else:
        canvas.create_polygon(pts, outline="#666666", width=1,
                              fill="#888888", stipple="gray50")
    if label is not None:
        canvas.create_text(cx, cy + half_h + 6, text=label,
                          font=("Arial", 9), fill="#222222")

def draw_contact_diamond(canvas, cx, cy, base_r, uncertainty, color):
    r = base_r * 0.5 if uncertainty == 'exact' else base_r * 1.0 if uncertainty == 'area' else base_r * 2.0
    points = [
        (cx, cy - r),
        (cx + r, cy),
        (cx, cy + r),
        (cx - r, cy)
    ]
    canvas.create_polygon(points, outline=color, fill='', dash=(4, 3))

def side_color(side):
    if side == 'JP':
        return '#c0392b'
    elif side == 'US':
        return '#2980b9'
    else:
        return '#555555'
