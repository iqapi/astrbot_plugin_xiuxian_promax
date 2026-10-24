# utils/image_generator.py
"""信息卡片渲染器 - 磨砂玻璃质感图片生成"""
from __future__ import annotations  # 延迟求值注解：未安装 Pillow 时模块也能安全导入

import os
import uuid
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, List, Tuple, TYPE_CHECKING

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from astrbot.api import logger

# ===== 资源路径 =====
RES_DIR = Path(__file__).resolve().parents[1] / "resources"
BG_DIR = RES_DIR / "backgrouds"
FONT_PATH = RES_DIR / "LXGWWenKaiGB.ttf"
CARD_TEMP_DIR = Path(tempfile.gettempdir()) / "xiuxian_cards"

# ===== 主题配色 =====
COLOR_TITLE = (245, 230, 200)        # 标题：暖金
COLOR_SUBTITLE = (200, 212, 228)     # 副标题：月白
COLOR_SECTION = (255, 215, 128)      # 区块名：亮金
COLOR_LABEL = (196, 208, 224)        # 字段名：雾蓝
COLOR_VALUE = (250, 250, 252)        # 字段值：亮白
COLOR_ACCENT = (255, 200, 100)       # 强调条
COLOR_FOOTER = (168, 178, 194)       # 脚注：灰蓝
GLASS_TINT = (255, 255, 255)         # 玻璃色调
GLASS_ALPHA = 64                     # 玻璃不透明度


# ===== 卡片开关（由 main.py 根据插件配置注入）=====
_CARD_FLAGS: Dict[str, bool] = {"__enabled__": True}


def set_card_flags(flags: Dict[str, bool]):
    """注入配置开关（IMAGE_CARDS 组）"""
    if isinstance(flags, dict):
        _CARD_FLAGS.update(flags)


def card_enabled(key: str) -> bool:
    """某界面的卡片是否启用（总开关优先）"""
    if not _CARD_FLAGS.get("__enabled__", True):
        return False
    return _CARD_FLAGS.get(key, True)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """加载霞鹜文楷字体（带缓存）"""
    if not hasattr(_load_font, "_cache"):
        _load_font._cache = {}
    if size not in _load_font._cache:
        if FONT_PATH.exists():
            _load_font._cache[size] = ImageFont.truetype(str(FONT_PATH), size)
        else:
            _load_font._cache[size] = ImageFont.load_default()
    return _load_font._cache[size]


def _cover_resize(img: Image.Image, w: int, h: int) -> Image.Image:
    """背景图按 cover 模式裁剪缩放"""
    sw, sh = img.size
    scale = max(w / sw, h / sh)
    nw, nh = int(sw * scale + 1), int(sh * scale + 1)
    img = img.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - w) // 2, (nh - h) // 2
    return img.crop((x, y, x + w, y + h))


def _glass_panel(canvas: Image.Image, box: Tuple[int, int, int, int],
                 radius: int = 26, blur: int = 14, alpha: int = GLASS_ALPHA) -> Image.Image:
    """在 canvas 上绘制一块磨砂玻璃面板：背景模糊 + 半透明白色蒙版"""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return canvas

    base = canvas.convert("RGBA")

    # 1. 取面板下方背景做高斯模糊，模拟磨砂
    crop = base.crop(box).filter(ImageFilter.GaussianBlur(blur))
    crop = ImageEnhance.Brightness(crop).enhance(1.06)

    # 2. 圆角蒙版
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)

    # 3. 贴回模糊背景 + 半透明白色玻璃蒙版 + 细描边
    base.paste(crop, (x0, y0), mask)
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle(box, radius=radius, fill=GLASS_TINT + (alpha,),
                         outline=(255, 255, 255, 90), width=2)
    return Image.alpha_composite(base, overlay)


def _trunc(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    """超宽文本截断加省略号"""
    text = str(text)
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text + "…"


def render_card(
    bg_name: str,
    title: str,
    subtitle: str = "",
    sections: Optional[List[Dict]] = None,
    footer: str = "",
    width: int = 1000,
) -> Optional[str]:
    """渲染磨砂玻璃质感的信息卡片，返回图片文件路径（失败返回 None）

    sections 格式：
      [{"name": "区块名", "rows": [("字段", "值"), ...]}]
      或 [{"name": "区块名", "lines": ["整行文本", ...]}]
    """
    if not HAS_PIL:
        return None

    bg_path = BG_DIR / f"{bg_name}.jpg"
    if not bg_path.exists():
        bg_path = BG_DIR / "default.jpg"
    if not bg_path.exists():
        return None

    sections = sections or []

    try:
        f_title = _load_font(56)
        f_sub = _load_font(30)
        f_section = _load_font(38)
        f_row = _load_font(30)
        f_foot = _load_font(24)

        pad = 48
        inner = 36
        row_h = 52
        section_gap = 34

        # ===== 预排版计算高度 =====
        probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        body_height = 0
        for sec in sections:
            body_height += row_h + 12  # 区块名行
            rows = sec.get("rows")
            if rows:
                body_height += row_h * len(rows)
            for _ in sec.get("lines", []):
                body_height += row_h
            body_height += section_gap

        header_h = 150 if subtitle else 120
        footer_h = 60 if footer else 24
        height = header_h + inner + body_height + inner + footer_h + pad
        height = max(height, 620)

        # ===== 背景 =====
        bg = Image.open(bg_path).convert("RGB")
        canvas = _cover_resize(bg, width, height)
        # 整体轻微压暗 + 增强对比，保证文字可读
        canvas = ImageEnhance.Brightness(canvas).enhance(0.88)
        canvas = ImageEnhance.Color(canvas).enhance(1.08)
        canvas = canvas.convert("RGBA")

        # ===== 磨砂玻璃主面板 =====
        panel_y0 = header_h - 20
        canvas = _glass_panel(canvas, (pad, panel_y0, width - pad, height - footer_h))

        draw = ImageDraw.Draw(canvas)

        # ===== 标题（带柔和阴影）=====
        title = _trunc(draw, title, f_title, width - pad * 2)
        tw = draw.textlength(title, font=f_title)
        draw.text(((width - tw) / 2 + 2, 46 + 2), title, font=f_title, fill=(0, 0, 0, 160))
        draw.text(((width - tw) / 2, 46), title, font=f_title, fill=COLOR_TITLE)

        # ===== 副标题 =====
        y_cursor = panel_y0 + inner
        if subtitle:
            subtitle = _trunc(draw, subtitle, f_sub, width - pad * 2 - inner * 2)
            sw = draw.textlength(subtitle, font=f_sub)
            draw.text(((width - sw) / 2, 108), subtitle, font=f_sub, fill=COLOR_SUBTITLE)

        # ===== 区块内容 =====
        label_x = pad + inner + 18
        value_right = width - pad - inner - 12
        label_max = (width - label_x) // 2 - 10
        value_max = value_right - (label_x + label_max + 20)

        for sec in sections:
            # 区块名 + 金色强调条
            name = _trunc(draw, sec.get("name", ""), f_section, width - pad * 2 - inner * 2 - 20)
            draw.rounded_rectangle(
                (pad + inner, y_cursor + 8, pad + inner + 6, y_cursor + 34),
                radius=3, fill=COLOR_ACCENT
            )
            draw.text((pad + inner + 18, y_cursor), name, font=f_section, fill=COLOR_SECTION)
            y_cursor += row_h + 12

            # 分割细线
            draw.line(
                (pad + inner, y_cursor - 6, width - pad - inner, y_cursor - 6),
                fill=(255, 255, 255, 40), width=1
            )

            for label, value in sec.get("rows", []):
                label_s = _trunc(draw, label, f_row, label_max)
                value_s = _trunc(draw, value, f_row, value_max)
                draw.text((label_x, y_cursor), label_s, font=f_row, fill=COLOR_LABEL)
                vw = draw.textlength(value_s, font=f_row)
                draw.text((value_right - vw, y_cursor), value_s, font=f_row, fill=COLOR_VALUE)
                y_cursor += row_h

            for line in sec.get("lines", []):
                line_s = _trunc(draw, line, f_row, width - pad * 2 - inner * 2)
                draw.text((label_x, y_cursor), line_s, font=f_row, fill=COLOR_VALUE)
                y_cursor += row_h

            y_cursor += section_gap

        # ===== 脚注 =====
        if footer:
            footer_s = _trunc(draw, footer, f_foot, width - pad * 2)
            fw = draw.textlength(footer_s, font=f_foot)
            draw.text(((width - fw) / 2, height - footer_h + 14), footer_s,
                      font=f_foot, fill=COLOR_FOOTER)

        # ===== 落盘 =====
        CARD_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        out_path = CARD_TEMP_DIR / f"card_{uuid.uuid4().hex[:12]}.jpg"
        canvas.convert("RGB").save(str(out_path), format="JPEG", quality=90)

        # 简单清理：目录超过 40 张旧卡时删除最旧的
        try:
            cards = sorted(CARD_TEMP_DIR.glob("card_*.jpg"), key=os.path.getmtime)
            for old in cards[:-40]:
                old.unlink(missing_ok=True)
        except Exception:
            pass

        return str(out_path)
    except Exception as e:
        logger.error(f"渲染卡片失败: {e}")
        return None


# ===== 兼容旧接口（原 ImageGenerator）=====
if HAS_PIL:
    ASSETS_PATH = RES_DIR
    FONT_PATH_LEGACY = FONT_PATH
    IMG_PATH = BG_DIR

    class ImageGenerator:
        def __init__(self):
            self.has_pil = HAS_PIL

        async def generate_user_info_card(self, user_id: str, detail_map: Dict) -> Optional[BytesIO]:
            path = render_card(
                "info",
                detail_map.get("道号", f"道友{user_id}"),
                f"ID: {user_id}",
                sections=[{"name": "基本信息", "rows": [
                    (k, str(v)) for k, v in detail_map.items() if k != "道号"
                ]}],
            )
            if path:
                with open(path, "rb") as f:
                    buf = BytesIO(f.read())
                return buf
            return None
else:
    class ImageGenerator:
        def __init__(self):
            self.has_pil = False

        async def generate_user_info_card(self, user_id: str, detail_map: Dict):
            return None
