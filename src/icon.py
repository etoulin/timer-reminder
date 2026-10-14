"""程序图标：使用 Pillow 动态绘制，避免额外的二进制资源依赖。"""

from __future__ import annotations

from PIL import Image, ImageDraw

BG = (37, 99, 235, 255)        # 蓝色底
FG = (255, 255, 255, 255)      # 白色前景


def create_image(size: int = 64) -> Image.Image:
    """绘制一个圆形闹钟图标（RGBA）。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size

    # 顶部两个铃铛耳
    d.ellipse([s * 0.06, s * 0.02, s * 0.28, s * 0.26], fill=FG)
    d.ellipse([s * 0.72, s * 0.02, s * 0.94, s * 0.26], fill=FG)

    # 钟体
    d.ellipse([s * 0.06, s * 0.14, s * 0.94, s * 0.98], fill=BG, outline=FG, width=max(1, s // 24))

    # 指针
    cx, cy = s * 0.5, s * 0.56
    d.line([cx, cy, cx, cy - s * 0.26], fill=FG, width=max(2, s // 16))
    d.line([cx, cy, cx + s * 0.18, cy], fill=FG, width=max(2, s // 16))
    d.ellipse([cx - s * 0.03, cy - s * 0.03, cx + s * 0.03, cy + s * 0.03], fill=FG)
    return img


def as_ico(path: str, size: int = 64) -> str:
    """导出 .ico 文件（用于窗口标题栏图标），返回路径。"""
    img = create_image(size)
    img.save(path, format="ICO", sizes=[(size, size)])
    return path
