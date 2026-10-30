#!/usr/bin/env python3
"""
merge_commands.py —— 把 commands/base.py 与 commands/feature_commands.py 内联进 main.py

用法：
    1. 把本脚本放到插件根目录（与 main.py 同级）
    2. 确保 commands/base.py 与 commands/feature_commands.py 仍是拆分状态
    3. 运行：python merge_commands.py
    4. 自动生成 main.py（原文件备份为 main.py.bak）
"""
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "main.py"
BASE = ROOT / "commands" / "base.py"
FEAT = ROOT / "commands" / "feature_commands.py"

for p in (MAIN, BASE, FEAT):
    if not p.exists():
        raise SystemExit(f"❌ 找不到文件: {p}")


def strip_leading_docstring(src: str) -> str:
    """去掉文件开头三引号 docstring"""
    return re.sub(r'^\s*""".*?"""\s*\n', '', src, count=1, flags=re.S)


def drop_line(src: str, pattern: str) -> str:
    return re.sub(pattern, '', src, flags=re.M)


# ---------- base.py ----------
base_src = strip_leading_docstring(BASE.read_text(encoding="utf-8"))
# 删除 main.py 已具备的 import
base_src = drop_line(base_src, r'^from functools import wraps\s*\n')
base_src = drop_line(base_src, r'^from astrbot\.api\.event import AstrMessageEvent[^\n]*\n')
# 相对导入降级（commands/ 子目录 → 插件根）
base_src = base_src.replace('from ..', 'from .')
base_src = base_src.strip()

# ---------- feature_commands.py ----------
feat_src = strip_leading_docstring(FEAT.read_text(encoding="utf-8"))
feat_src = drop_line(feat_src, r'^from astrbot\.api\.event import AstrMessageEvent[^\n]*\n')
feat_src = drop_line(feat_src, r'^from astrbot\.api\.event import filter[^\n]*\n')
feat_src = drop_line(feat_src, r'^from \.base import [^\n]*\n')
feat_src = feat_src.replace('from ..', 'from .')
feat_src = feat_src.strip()

# ---------- main.py ----------
main_src = MAIN.read_text(encoding="utf-8")
main_src = drop_line(main_src, r'^from \.commands\.base import [^\n]*\n')
main_src = drop_line(main_src, r'^from \.commands\.feature_commands import [^\n]*\n')

# 插入点 1：CMD_REBIRTH 之后（require_whitelist / CardMixin）
anchor1 = 'CMD_REBIRTH = "弃道重修"'
if anchor1 not in main_src:
    raise SystemExit("❌ main.py 中找不到 CMD_REBIRTH 锚点")
i1 = main_src.index(anchor1)
e1 = main_src.index('\n', i1) + 1
main_src = (main_src[:e1]
            + "\n\n# ===== 原 commands/base.py（已内联） =====\n\n"
            + base_src + "\n\n"
            + main_src[e1:])

# 插入点 2：class XiuXianPlugin 之前（FeatureCommandsMixin）
anchor2 = 'class XiuXianPlugin'
if anchor2 not in main_src:
    raise SystemExit("❌ main.py 中找不到 XiuXianPlugin 锚点")
i2 = main_src.index(anchor2)
main_src = (main_src[:i2]
            + "# ===== 原 commands/feature_commands.py（已内联） =====\n\n"
            + feat_src + "\n\n\n"
            + main_src[i2:])

# 备份 + 写回
bak = MAIN.with_suffix(".py.bak")
if not bak.exists():
    shutil.copy2(MAIN, bak)
    print(f"📦 已备份原文件 → {bak.name}")
MAIN.write_text(main_src, encoding="utf-8")
print(f"✅ 合并完成 → {MAIN}")
print("   建议：先 git diff 检查，确认无误后可删除 commands/ 目录")