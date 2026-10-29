# utils/image_generator.py
"""信息卡片渲染器 v3 - 国风绢帛·墨金·多字体层次"""
from __future__ import annotations

import os
import re
import uuid
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, List, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from astrbot.api import logger

# ===== 资源路径 =====
RES_DIR = Path(__file__).resolve().parents[1] / "resources"
BG_DIR = RES_DIR / "backgrouds"
FONT_KAI = RES_DIR / "LXGWWenKaiGB.ttf"                 # 文楷（末位兜底，不再主用）
FONT_HEAVY = RES_DIR / "SourceHanSerifSC-Heavy.otf"     # 大标题：最重碑刻
FONT_BOLD = RES_DIR / "SourceHanSerifSC-Bold.otf"       # 区块名：鎏金碑刻
FONT_SEMI = RES_DIR / "SourceHanSerifSC-SemiBold.otf"   # 数值：清晰醒目
FONT_MED = RES_DIR / "SourceHanSerifSC-Medium.otf"      # 字段名/正文
FONT_XINGKAI = RES_DIR / "MaShanZheng-Regular.ttf"      # 行楷：副标题/脚注墨迹
FONT_EMOJI = RES_DIR / "OpenMoji-black-glyf.ttf"        # OpenMoji：装饰符号（程序镀金）
CARD_TEMP_DIR = Path(tempfile.gettempdir()) / "xiuxian_cards"

# emoji 渲染：需要 109px 的 OpenMoji 无所谓，但 Noto 需要固定尺寸；OpenMoji 自由
EMOJI_RENDER_SIZE = 96  # emoji 高清渲染基准，之后缩放

# ===== 国风配色 =====
INK_BG_TOP = (38, 32, 26)
INK_PANEL = (48, 40, 32, 228)
INK_PANEL_EDGE = (198, 161, 91)
INK_GOLD = (232, 196, 122)         # 鎏金标题
INK_GOLD_DIM = (176, 148, 100)     # 暗金副标题
INK_TEXT = (242, 232, 214)         # 宣纸白（数值）
INK_LABEL = (186, 166, 134)        # 淡墨金（字段名）
INK_SECTION = (236, 202, 132)      # 区块名·亮金
INK_ACCENT = (176, 141, 87)
INK_FOOTER = (160, 140, 110)
INK_DIVIDER = (110, 94, 72)
INK_SHADOW = (0, 0, 0, 180)

# ===== 卡片开关 =====
_CARD_FLAGS: Dict[str, bool] = {"__enabled__": True}


def set_card_flags(flags: Dict[str, bool]):
    if isinstance(flags, dict):
        _CARD_FLAGS.update(flags)


def card_enabled(key: str) -> bool:
    if not _CARD_FLAGS.get("__enabled__", True):
        return False
    return _CARD_FLAGS.get(key, True)


def _pick(*paths) -> Optional[Path]:
    for p in paths:
        if p and Path(p).exists():
            return Path(p)
    return None


_font_cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}


def _load_font(size: int, style: str = "text"):
    """五级字体层次（缺失自动降级，最终兜底文楷/默认）：
    heavy=大标题 / bold=区块 / semi=数值 / text=字段正文 / xing=行楷点缀"""
    key = (style, size)
    if key in _font_cache:
        return _font_cache[key]
    table = {
        "heavy": (FONT_HEAVY, FONT_BOLD, FONT_MED),
        "bold": (FONT_BOLD, FONT_HEAVY, FONT_MED),
        "semi": (FONT_SEMI, FONT_BOLD, FONT_MED),
        "text": (FONT_MED, FONT_SEMI, FONT_KAI),
        "xing": (FONT_XINGKAI, FONT_MED, FONT_KAI),
    }
    f = None
    for cand in table.get(style, (FONT_MED, FONT_KAI)):
        if cand and Path(cand).exists():
            f = ImageFont.truetype(str(cand), size)
            break
    if f is None:
        # 所有候选字体缺失：降级到点阵默认字体（中文大字会渲染成豆腐块），必须留痕便于排查
        f = ImageFont.load_default()
        try:
            from astrbot.api import logger
            logger.warning(f"字体加载失败，已降级为默认点阵字体（中文显示会异常）: style={style} size={size}")
        except Exception:
            pass
    _font_cache[key] = f
    return f


def _cover_resize(img, w: int, h: int):
    sw, sh = img.size
    scale = max(w / sw, h / sh)
    img = img.resize((int(sw * scale) + 1, int(sh * scale) + 1), Image.LANCZOS)
    x, y = (img.size[0] - w) // 2, (img.size[1] - h) // 2
    return img.crop((x, y, x + w, y + h))


def _draw_corner_clouds(draw, w: int, h: int, alpha: int = 30):
    gold = INK_ACCENT + (alpha,)
    r = 46
    for cx, cy, dx, dy in ((56, 56, 1, 1), (w - 56, 56, -1, 1), (56, h - 56, 1, -1), (w - 56, h - 56, -1, -1)):
        draw.arc([cx - r, cy - r, cx + r, cy + r], start=0 if dx > 0 else 90, end=90 if dx > 0 else 180, fill=gold, width=2)
        draw.arc([cx + dx * 20 - 26, cy + dy * 20 - 26, cx + dx * 20 + 26, cy + dy * 20 + 26],
                 start=0 if dx > 0 else 90, end=90 if dx > 0 else 180, fill=gold, width=2)
    cx = w // 2
    draw.polygon([(cx - 8, 30), (cx, 22), (cx + 8, 30), (cx, 38)], outline=gold, width=2)


def _font_textlen(font, text: str) -> float:
    """用字体对象度量文本宽度（无 Draw 时的探针）"""
    if hasattr(font, "getlength"):
        return font.getlength(text)
    return font.getbbox(text)[2]


_XINGKAI_SAFE = re.compile(r'^[\u4e00-\u9fff\u3400-\u4dbf a-zA-Z0-9，。：；！？、「」『』（）()\-\+/%＆%,.:;!?~*×\u3000]*$')


def _xing_font_for(text: str, size: int):
    """行楷字体只用于纯中文/常规标点文本（缺 emoji 字形会渲染豆腐块）；
    含特殊符号时自动回退宋体。"""
    if _XINGKAI_SAFE.match(text or "") and FONT_XINGKAI.exists():
        return ImageFont.truetype(str(FONT_XINGKAI), size)
    return _load_font(size, "semi")


def _trunc(draw, text: str, font, max_width: int) -> str:
    text = str(text)
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text + "…"


def _shadow(draw, xy, text, font, fill):
    x, y = xy
    draw.text((x + 1, y + 2), text, font=font, fill=INK_SHADOW)
    draw.text((x, y), text, font=font, fill=fill)


_GRAD_CACHE: Dict[int, Image.Image] = {}


def _vgrad(w: int, h: int, top=(238, 206, 128), bottom=(176, 132, 62)) -> Image.Image:
    """竖向鎏金渐变（v3.24.0：按高度缓存，替代逐像素 putpixel）"""
    key = (w, h, top, bottom)
    if key in _GRAD_CACHE:
        return _GRAD_CACHE[key]
    grad = Image.new("RGB", (1, h))
    for yy in range(h):
        t = yy / max(1, h - 1)
        grad.putpixel((0, yy), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    grad = grad.resize((w, h))
    if len(_GRAD_CACHE) > 128:
        _GRAD_CACHE.clear()
    _GRAD_CACHE[key] = grad
    return grad


def _gold_gradient_text(canvas, xy, text, font) -> Tuple[int, int]:
    """烫金渐变文字：上亮金下暗金，带墨色柔影与微光晕。返回 (宽, 高)
    v3.24.0：影/晕/金字合并进一个小图块，单次 alpha_composite(dest) 上屏
    （旧实现每个文字建 3 个全画布图层，O(全卡尺寸) 内存开销）"""
    x, y = xy
    tw = int(_font_textlen(font, text)) + 8
    th = font.size + 14
    # 文字蒙版
    mask = Image.new("L", (tw, th), 0)
    md = ImageDraw.Draw(mask)
    md.text((4, 4), text, font=font, fill=255)
    bbox = mask.getbbox()
    if not bbox:
        draw.text((x, y), text, font=font, fill=INK_GOLD)
        return tw, th
    mask = mask.crop(bbox)
    w2, h2 = mask.size
    grad = _vgrad(w2, h2, (248, 218, 148), (176, 132, 62))
    # 合成小图块：光晕 + 墨影 + 金字（pad 预留模糊溢出空间）
    pad = 10
    tile = Image.new("RGBA", (w2 + pad * 2, h2 + pad * 2), (0, 0, 0, 0))
    glow = Image.new("RGBA", tile.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.text((pad + bbox[0] - 4, pad + bbox[1] - 4), text, font=font, fill=(230, 190, 110, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(6))
    tile.alpha_composite(glow)
    shadow = Image.new("RGBA", tile.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.text((pad + bbox[0] - 2, pad + bbox[1] - 1), text, font=font, fill=INK_SHADOW)
    shadow = shadow.filter(ImageFilter.GaussianBlur(2))
    tile.alpha_composite(shadow)
    glyph = Image.new("RGBA", (w2, h2), (0, 0, 0, 0))
    glyph.paste(grad, (0, 0), mask)
    tile.alpha_composite(glyph, (pad, pad))
    canvas.alpha_composite(tile, (int(x + bbox[0] - 4 - pad), int(y + bbox[1] - 4 - pad)))
    return tw, th


_EMOJI_RE = re.compile(
    '['
    '\U0001F300-\U0001FAFF'   # 主要 emoji 区块
    '\U00002600-\U000027BF'   # 杂项符号（⚔✡☯等）
    '\U0001F000-\U0001F02F'
    '\U00002190-\U000021FF'   # 箭头
    '\U00002B00-\U00002BFF'
    ']'
)


def _split_emoji(text: str) -> List[Tuple[str, bool]]:
    """把文本切成 (片段, 是否emoji) 序列"""
    parts = []
    last = 0
    for m in _EMOJI_RE.finditer(text):
        if m.start() > last:
            parts.append((text[last:m.start()], False))
        # emoji 含可选 VS16
        end = m.end()
        if end < len(text) and text[end] == '\uFE0F':
            end += 1
        parts.append((text[m.start():end], True))
        last = end
    if last < len(text):
        parts.append((text[last:], False))
    return [(p, e) for p, e in parts if p]


def _draw_mixed(canvas_draw_image, xy, text, font, emoji_px: int, fill,
                emoji_color=(232, 196, 122), shadow=True):
    """中文+emoji 混排绘制：中文用字体，emoji 用 OpenMoji 镀金位图。
    canvas_draw_image: RGBA Image（用于 emoji 粘贴）；xy 为基线左上角。返回结束 x。"""
    x, y = xy
    d = ImageDraw.Draw(canvas_draw_image)
    emoji_font = None
    if FONT_EMOJI.exists():
        emoji_font = ImageFont.truetype(str(FONT_EMOJI), emoji_px * 3)  # 高清渲染 3x
    for part, is_emoji in _split_emoji(text):
        if is_emoji:
            if emoji_font is None:
                d.text((x, y), part, font=font, fill=fill)
                x += d.textlength(part, font=font)
                continue
            # 高清渲染 emoji 剪影
            ew = int(emoji_px * 1.6)
            eh = int(emoji_px * 1.35)
            tmp = Image.new('L', (ew * 3, eh * 3), 0)
            td = ImageDraw.Draw(tmp)
            try:
                td.text((6, 0), part, font=emoji_font, fill=255)
            except Exception:
                d.text((x, y), part, font=font, fill=fill)
                x += d.textlength(part, font=font)
                continue
            bbox = tmp.getbbox()
            if not bbox:
                d.text((x, y), part, font=font, fill=fill)
                x += d.textlength(part, font=font)
                continue
            tmp = tmp.crop(bbox)
            scale = emoji_px / tmp.height
            tmp = tmp.resize((max(1, int(tmp.width * scale)), emoji_px), Image.LANCZOS)
            # v3.24.0：镀金 + 柔影合并进小图块，单次 alpha_composite(dest) 上屏
            # （旧实现每个 emoji 建 2 个全画布图层，O(全卡尺寸) 开销）
            grad = _vgrad(tmp.width, tmp.height, (238, 206, 128), (176, 150, 74))
            glyph = Image.new('RGBA', tmp.size, (0, 0, 0, 0))
            glyph.paste(grad, (0, 0), tmp)
            gx, gy = int(x), int(y + emoji_px * 0.12)
            pad_l, pad_t = (2 if shadow else 0), (3 if shadow else 0)
            tile = Image.new('RGBA', (glyph.width + pad_l + 1, glyph.height + pad_t + 1), (0, 0, 0, 0))
            if shadow:
                tile.paste((0, 0, 0, 150), (pad_l + 1, pad_t + 2), tmp)
            tile.alpha_composite(glyph, (pad_l, pad_t))
            canvas_draw_image.alpha_composite(tile, (gx - pad_l, gy - pad_t))
            x += tmp.width + emoji_px * 0.18
        else:
            if shadow:
                d.text((x + 1, y + 2), part, font=font, fill=INK_SHADOW)
            d.text((x, y), part, font=font, fill=fill)
            x += d.textlength(part, font=font)
    return x


def _mixed_width(text: str, font, emoji_px: int) -> float:
    """混排文本总宽度（供居中/右对齐计算）"""
    w = 0.0
    for part, is_emoji in _split_emoji(text):
        if is_emoji:
            w += emoji_px * 1.18
        else:
            w += _font_textlen(font, part)
    return w


# ===== v3.25.0 仙侠视觉：水墨远山 / 朱红印章 / 金角饰 / 粒子 =====

def _draw_ink_mountains(canvas, width, height, seed: int):
    """层叠远山剪影（低透明度，营造水墨意境）"""
    import random as _r
    rng = _r.Random(seed)
    layers = [
        (int(height * 0.42), 90, 42, (70, 84, 112)),
        (int(height * 0.55), 120, 32, (55, 66, 90)),
        (int(height * 0.70), 150, 24, (42, 51, 70)),
    ]
    for base_y, amp, alpha, color in layers:
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        pts = [(0, height)]
        x = 0
        phase = rng.uniform(0, 6.28)
        while x <= width:
            y = base_y + amp * 0.4 * abs(((x * 0.011 + phase) % 6.28) - 3.14) \
                + amp * 0.25 * (((x * 0.037 + phase * 2) % 6.28) - 3.14) / 3.14
            pts.append((x, y))
            x += 14
        pts.append((width, height))
        d.polygon(pts, fill=color + (alpha,))
        canvas.alpha_composite(layer)


def _draw_gold_particles(canvas, width, height, seed: int, count: int = 46):
    """飘散金尘粒子（顶部密、往下疏）"""
    import random as _r
    rng = _r.Random(seed)
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(count):
        x = rng.uniform(10, width - 10)
        y = rng.uniform(10, height * 0.75)
        r = rng.uniform(1.0, 2.8)
        a = int(150 * (1 - y / height) + 30)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(238, 206, 128, a))
    canvas.alpha_composite(layer)


def _draw_seal(canvas, x: int, y: int, char: str, size: int = 64):
    """朱红印章（圆角方、白字、微旋转、描边微糙）"""
    tile = Image.new("RGBA", (size + 12, size + 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    d.rounded_rectangle([6, 6, size + 6, size + 6], radius=10, fill=(172, 42, 36, 235),
                        outline=(238, 206, 128, 180), width=2)
    f = _load_font(int(size * 0.62), "heavy")
    w = d.textlength(char, font=f)
    d.text(((size + 12 - w) / 2, size * 0.14), char, font=f, fill=(248, 238, 220, 255))
    tile = tile.rotate(-4, expand=True, resample=Image.BICUBIC)
    canvas.alpha_composite(tile, (x, y))


def _draw_cloud_divider(draw, cx: int, y: int, half_span: int, color):
    """云头纹分隔线：中菱形 + 两侧弧形云头 + 细线"""
    d = draw
    d.polygon([(cx - 7, y), (cx, y - 6), (cx + 7, y), (cx, y + 6)], fill=color)
    for sgn in (-1, 1):
        x0 = cx + sgn * 16
        xa, xb = sorted((x0, x0 + sgn * 44))
        d.arc([xa, y - 8, xb, y + 8], start=270 if sgn > 0 else 90, end=90 if sgn > 0 else 270, fill=color, width=2)
        x1 = cx + sgn * 56
        xa2, xb2 = sorted((x1, x1 + sgn * 70))
        d.arc([xa2, y - 6, xb2, y + 6], start=270 if sgn > 0 else 90, end=90 if sgn > 0 else 270, fill=color, width=1)
        d.line([(x1 + sgn * 70, y), (cx + sgn * (half_span - 20), y)], fill=color, width=1)


def _draw_corner_ornaments(draw, width, height, color, pad: int = 26, arm: int = 46):
    """四角金饰：L 形双线 + 端点菱形（color 支持 3/4 元组）"""
    rgb = tuple(color[:3])
    base_a = color[3] if len(color) > 3 else 255
    for cx, cy, dx, dy in ((pad, pad, 1, 1), (width - pad, pad, -1, 1),
                           (pad, height - pad, 1, -1), (width - pad, height - pad, -1, -1)):
        draw.line([(cx, cy + dy * arm), (cx, cy), (cx + dx * arm, cy)], fill=rgb + (base_a,), width=3)
        draw.line([(cx + dx * 8, cy + dy * (arm - 10)), (cx + dx * 8, cy + dy * 8), (cx + dx * (arm - 10), cy + dy * 8)],
                  fill=rgb + (150,), width=1)
        d = 5
        tx, ty = cx + dx * arm, cy
        draw.polygon([(tx + dx * d, ty), (tx, ty - d), (tx - dx * d, ty), (tx, ty + d)], fill=rgb + (base_a,))


def render_card(
    bg_name: str,
    title: str,
    subtitle: str = "",
    sections: Optional[List[Dict]] = None,
    footer: str = "",
    width: int = 1000,
) -> Optional[str]:
    """渲染国风绢帛·墨金·多字体层次信息卡片，返回图片路径（失败返回 None）"""
    if not HAS_PIL:
        return None

    bg_path = BG_DIR / f"{bg_name}.jpg"
    if not bg_path.exists():
        bg_path = BG_DIR / "default.jpg"
    # v3.25.0：背景已程序化绘制，bg 图缺失亦可渲染（图仅作低透明纹理）

    sections = sections or []

    try:
        f_title = _load_font(56, "heavy")     # 大标题：最重
        f_section = _load_font(34, "bold")    # 区块名：碑刻
        f_value = _load_font(31, "semi")      # 数值：醒目
        f_label = _load_font(27, "text")      # 字段名：清峻（比数值小一号，拉开层次）
        f_foot = None                          # 脚注：行楷（按内容动态选择）
        f_xing_sub = None                      # 副标题：行楷（按内容动态选择）

        pad, inner = 54, 40
        row_h = 56
        section_gap = 32

        probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))

        # ===== 预排版：智能列宽（数值自适应扩展，杜绝截断）=====
        VALUE_RATIO_MAX = 0.62   # 数值列最多占内容宽 62%
        LABEL_RATIO_MIN = 0.24   # 字段列最少 24%
        content_w = width - pad * 2 - inner * 2 - 40
        body_height = 0
        max_value_w = 0.0
        for sec in sections:
            body_height += row_h + 14
            for label, value in sec.get("rows", []):
                lw = _font_textlen(f_label, str(label))
                vw = _font_textlen(f_value, str(value))
                max_value_w = max(max_value_w, vw, lw + 30)
            body_height += row_h * len(sec.get("rows", []))
            body_height += row_h * len(sec.get("lines", []))
            body_height += section_gap + 44   # v3.25.0：每个区块独立子面板的上下留白
        # 数值列宽 = min(最长数值, 上限)，且保证字段列 >= 最低占比
        value_col = int(min(max(max_value_w, content_w * 0.40), content_w * VALUE_RATIO_MAX))
        value_col = max(value_col, int(content_w * (1 - LABEL_RATIO_MIN)) - 0)
        label_col = content_w - value_col

        header_h = 176 if subtitle else 138
        footer_h = 70 if footer else 30
        height = max(640, header_h + inner + body_height + inner + footer_h + pad)

        # ===== 背景：水墨夜空 + 层叠远山 + 金尘（bg 图降级为低透明纹理叠层）=====
        if bg_path.exists():
            bg = Image.open(bg_path).convert("RGB")
            tex = _cover_resize(bg, width, height)
            tex = ImageEnhance.Brightness(tex).enhance(0.35).convert("RGBA")
            tex.putalpha(52)
            canvas = Image.new("RGBA", (width, height), (14, 17, 26, 255))
            canvas.alpha_composite(tex)
        else:
            canvas = Image.new("RGBA", (width, height), (14, 17, 26, 255))
        # 顶部月华光晕
        moon = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        md = ImageDraw.Draw(moon)
        md.ellipse([width * 0.58, -height * 0.22, width * 1.25, height * 0.30], fill=(96, 110, 150, 70))
        moon = moon.filter(ImageFilter.GaussianBlur(60))
        canvas.alpha_composite(moon)
        # 墨色纵向渐变（上浅下深）
        grad = Image.new("L", (1, height))
        for y in range(height):
            grad.putpixel((0, y), int(30 + 70 * y / height))
        dark = Image.new("RGBA", (width, height), (8, 10, 16, 0))
        dark.putalpha(grad.resize((width, height)))
        canvas = Image.alpha_composite(canvas, dark)
        _draw_ink_mountains(canvas, width, height, seed=abs(hash(title)) % 99991)
        _draw_gold_particles(canvas, width, height, seed=abs(hash(subtitle or title)) % 99991)

        # ===== 主面板：深色毛玻璃 + 双层金边 =====
        px0, py0, px1, py1 = pad, header_h - 26, width - pad, height - footer_h
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rounded_rectangle([px0 - 3, py0 - 3, px1 + 3, py1 + 3], radius=30, fill=(10, 12, 20, 150))
        canvas = Image.alpha_composite(canvas, overlay.filter(ImageFilter.GaussianBlur(10)))
        panel = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(panel).rounded_rectangle([px0, py0, px1, py1], radius=26, fill=(20, 23, 34, 175))
        canvas = Image.alpha_composite(canvas, panel)

        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle([px0, py0, px1, py1], radius=26, outline=INK_PANEL_EDGE, width=2)
        draw.rounded_rectangle([px0 + 6, py0 + 6, px1 - 6, py1 - 6], radius=21, outline=(232, 196, 122, 90), width=1)
        # 面板底缘鎏金渐变细线
        for i, a in enumerate(range(150, 20, -10)):
            draw.line([(px0 + 40 + i * 2, py1 - 3), (px1 - 40 - i * 2, py1 - 3)], fill=(232, 196, 122, a), width=1) if i == 0 else None
        _draw_corner_ornaments(draw, width, height, (232, 196, 122, 220))

        # ===== 鎏金大标题 + 朱红印章 =====
        title_s = _trunc(draw, title, f_title, width - pad * 2 - 60)
        emoji_px_title = 46
        tw = _mixed_width(title_s, f_title, emoji_px_title)
        title_end_x = _draw_mixed(canvas, ((width - tw) / 2, 38), title_s, f_title, emoji_px_title, None)
        draw = ImageDraw.Draw(canvas)
        seal_char = "仙"
        for _ch in title_s:
            if _ch.strip() and not _EMOJI_RE.match(_ch) and _ch not in "\uFE0F":
                seal_char = _ch
                break
        # v3.25.0：印章锚定混排真实结束坐标 + 安全边距（防止压住标题末字）
        seal_x = min(int(title_end_x) + 18, px1 - 100)
        _draw_seal(canvas, seal_x, 30, seal_char, 58)
        # 两侧云头纹
        _draw_cloud_divider(draw, width // 2, 42 + 42, int(width * 0.40), (232, 196, 122, 200))
        draw = ImageDraw.Draw(canvas)

        # ===== 行楷副标题（emoji 镀金点缀）=====
        y_cursor = py0 + inner
        if subtitle:
            f_xing_sub = _xing_font_for(subtitle, 30)
            sub_s = _trunc(draw, subtitle, f_xing_sub, width - pad * 2 - inner * 2 - 60)
            emoji_px_sub = 30
            sw = _mixed_width(sub_s, f_xing_sub, emoji_px_sub)
            _draw_mixed(canvas, ((width - sw) / 2, 112), sub_s, f_xing_sub, emoji_px_sub, INK_GOLD_DIM)
            draw = ImageDraw.Draw(canvas)

        # ===== 区块子面板（独立毛玻璃 + 金色渐变侧条）=====
        label_x = pad + inner + 16
        value_right = width - pad - inner - 10
        emoji_px_val = 30
        panel_x0, panel_x1 = px0 + 14, px1 - 14

        for sec in sections:
            sec_top = y_cursor - 10
            name = _trunc(draw, sec.get("name", ""), f_section, width - pad * 2 - inner * 2 - 40)
            rows = sec.get("rows", [])
            lines_list = sec.get("lines", [])
            sec_h = 44 + row_h * len(rows) + row_h * len(lines_list) + 26
            # 子面板
            sub = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            sd = ImageDraw.Draw(sub)
            sd.rounded_rectangle([panel_x0, sec_top, panel_x1, sec_top + sec_h], radius=16,
                                 fill=(255, 250, 240, 10), outline=(232, 196, 122, 42), width=1)
            # 左侧金色渐变竖条
            for i in range(4):
                sd.line([(panel_x0 + 10 + i, sec_top + 12), (panel_x0 + 10 + i, sec_top + sec_h - 12)],
                        fill=(232, 196, 122, 160 - i * 35), width=1)
            canvas = Image.alpha_composite(canvas, sub)
            draw = ImageDraw.Draw(canvas)

            # 区块名 + 尾部序号
            draw.text((label_x + 22, y_cursor + 1), name, font=f_section, fill=INK_SECTION)
            nw = draw.textlength(name, font=f_section)
            draw.line([(label_x + 22 + nw + 26, y_cursor + 19), (panel_x1 - 20, y_cursor + 19)],
                      fill=INK_DIVIDER, width=1)
            y_cursor += row_h + 8

            for label, value in rows:
                label_s = _trunc(draw, str(label), f_label, label_col)
                value_s = _trunc(draw, str(value), f_value, value_col)
                draw.text((label_x + 6, y_cursor + 3), label_s, font=f_label, fill=INK_LABEL)
                vw = _mixed_width(value_s, f_value, emoji_px_val)
                _draw_mixed(canvas, (value_right - vw, y_cursor), value_s, f_value, emoji_px_val, INK_TEXT)
                draw = ImageDraw.Draw(canvas)
                # 行间点线
                if (y_cursor // row_h) % 2 == 0:
                    lx_end = label_x + 6 + draw.textlength(label_s, font=f_label)
                    for dx in range(int(lx_end + 12), int(value_right - vw - 14), 26):
                        draw.ellipse([dx, y_cursor + 27, dx + 3, y_cursor + 29], fill=INK_DIVIDER + (110,))
                y_cursor += row_h

            for line in lines_list:
                line_s = _trunc(draw, str(line), f_value, width - pad * 2 - inner * 2 - 10)
                _draw_mixed(canvas, (label_x + 6, y_cursor), line_s, f_value, emoji_px_val, INK_TEXT)
                draw = ImageDraw.Draw(canvas)
                y_cursor += row_h

            y_cursor += section_gap + 30

        # ===== 行楷脚注（emoji 镀金点缀 + 菱形分隔）=====
        if footer:
            f_foot = _xing_font_for(footer, 26)
            foot_s = _trunc(draw, footer, f_foot, width - pad * 2)
            fw = _mixed_width(foot_s, f_foot, 26)
            fy = height - footer_h + 14
            _draw_cloud_divider(draw, width // 2, fy + 4, int(width * 0.36), (110, 94, 72, 160))
            _draw_mixed(canvas, ((width - fw) / 2, fy + 8), foot_s, f_foot, 26, INK_FOOTER)

        # ===== 落盘 =====
        CARD_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        out_path = CARD_TEMP_DIR / f"card_{uuid.uuid4().hex[:12]}.jpg"
        canvas.convert("RGB").save(str(out_path), format="JPEG", quality=92)
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


async def render_card_async(bg_name: str, title: str, subtitle: str = "",
                            sections: Optional[List[Dict]] = None, footer: str = "",
                            width: int = 1000) -> Optional[str]:
    """异步版本；失败/关闭返回 None"""
    import asyncio
    return await asyncio.to_thread(render_card, bg_name, title, subtitle, sections, footer, width)


# ===== 兼容旧接口 =====
if HAS_PIL:
    class ImageGenerator:
        def __init__(self):
            self.has_pil = HAS_PIL

        async def generate_user_info_card(self, user_id: str, detail_map: Dict) -> Optional[BytesIO]:
            path = render_card("info", detail_map.get("道号", f"道友{user_id}"), f"ID: {user_id}",
                               sections=[{"name": "基本信息", "rows": [(k, str(v)) for k, v in detail_map.items() if k != "道号"]}],
                               )
            if path:
                with open(path, "rb") as f:
                    return BytesIO(f.read())
            return None
else:
    class ImageGenerator:
        def __init__(self):
            self.has_pil = False

        async def generate_user_info_card(self, user_id: str, detail_map: Dict):
            return None
