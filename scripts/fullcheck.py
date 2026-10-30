import io, os, re, sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
issues = []
warns = []

# ---------- 1. 遗留临时文件 ----------
leftovers = [p.name for p in ROOT.iterdir() if p.name.startswith(('fullcheck', '_num', '_render', '_resolver', '_card_samples', '_main_import', '_card_check', '_schema_dump', '_hits', '_splice', '_readme_', '_license_', '_fix_tail', '_revert', '_stripbom', '_render_test', '_render_err', '_final_check.bak'))]
if leftovers:
    issues.append(f"遗留临时文件: {leftovers}")

# ---------- 2. BOM 检查（py/md/json/yaml）----------
for p in list(ROOT.rglob('*.py')) + list(ROOT.rglob('*.md')) + list(ROOT.rglob('*.json')) + list(ROOT.rglob('*.yaml')):
    if '__pycache__' in str(p) or '.serena' in str(p) or 'scripts' in str(p):
        continue
    head = p.read_bytes()[:3]
    if head == b'\xef\xbb\xbf':
        warns.append(f"BOM: {p.name}")

# ---------- 3. 失效引用 ----------
main_t = (ROOT / 'main.py').read_text(encoding='utf-8')
if re.search(r'from \.\.[\w.]+ import', main_t):
    issues.append("main.py 仍存在 `..` 越界相对导入")
if 'commands.feature_commands' in main_t or 'FeatureCommandsMixin' in main_t:
    issues.append("main.py 仍引用已删除的 commands 包/Mixin")
for f in ROOT.rglob('*.py'):
    if '__pycache__' in str(f) or f.name == 'fullcheck.py':
        continue
    t = f.read_text(encoding='utf-8', errors='ignore')
    if 'from .commands' in t or 'commands.feature_commands' in t:
        issues.append(f"残留 commands 引用: {f.name}")

# ---------- 4. 装饰器配对 ----------
lines = main_t.splitlines()
dangling = []
for i, l in enumerate(lines):
    s = l.strip()
    if s.startswith('@filter.command') or s == '@require_whitelist':
        nxt = lines[i].strip() if i + 1 < len(lines) else ''
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ''
        if not (nxt.startswith('@') or nxt.startswith('async def ')):
            dangling.append(i + 1)
if dangling:
    issues.append(f"悬空装饰器行: {dangling}")

# ---------- 5. 指令重复注册 ----------
cmds = re.findall(r'@filter\.command\(\s*([^,\s]+)', main_t)
cmd_names = [c.strip().strip('"') for c in cmds]
dup = {c for c in cmd_names if cmd_names.count(c) > 1}
if dup:
    issues.append(f"重复注册指令: {dup}")

# ---------- 6. 版本一致性 ----------
meta = (ROOT / 'metadata.yaml').read_text(encoding='utf-8')
m_ver = re.search(r'version:\s*(\S+)', meta).group(1)
readme = (ROOT / 'README.md').read_text(encoding='utf-8')
if f'version-{m_ver}' not in readme:
    issues.append(f"README 徽章版本与 metadata 不一致（{m_ver}）")
if f'**插件版本:** {m_ver}' not in readme:
    issues.append(f"README 插件版本行与 metadata 不一致（{m_ver}）")
if not readme.startswith('<p align'):
    if readme.startswith('﻿'):
        warns.append("README 仍带 BOM（GitHub 可渲染，建议去除）")

# ---------- 7. README 引用的本地文件存在性 ----------
for ref in ['logo.png', 'LICENSE', 'scripts/_final_check.py', 'scripts/check_syntax.py',
            'tests/test_core_logic.py', 'tests/test_atomic_primitives.py',
            'ruff.toml', '.github/workflows/ci.yml', 'scripts/docs_command_graph.html']:
    if not (ROOT / ref).exists():
        issues.append(f"README/工程引用的文件不存在: {ref}")

# ---------- 8. requirements vs 实际依赖 ----------
req = (ROOT / 'requirements.txt').read_text(encoding='utf-8')
if 'aiosqlite' not in req:
    issues.append("requirements 缺 aiosqlite")
if 'Pillow' not in req:
    issues.append("requirements 缺 Pillow")
uses_pil = 'from PIL import' in (ROOT / 'utils' / 'image_generator.py').read_text(encoding='utf-8')
if uses_pil and 'Pillow' not in req:
    issues.append("image_generator 用 PIL 但 requirements 未声明")

# ---------- 9. AGENTS.md 规范：帮助文本含全部指令（粗查新增玩法）----------
misc = (ROOT / 'handlers' / 'misc_handler.py').read_text(encoding='utf-8')
for cmd in ['修仙天气', '天骄榜', '观礼', '轮回宝阁', '灵植园', '道侣试炼', '灵脉战',
            '扫荡秘境', '悬赏行会', '收集图鉴', '签到里程碑', '科举', '罗盘', '结契',
            '成就', '灵兽出战', '夺宝', '登仙台', '称号熔炼', '求签', '修仙群史',
            '宗门科技', '拍卖行', '斗法台']:
    if f'/{cmd}' not in misc and cmd not in misc:
        issues.append(f"/修仙帮助 缺指令: {cmd}")

# ---------- 10. TODO/FIXME 残留 ----------
todo_count = 0
for f in ROOT.rglob('*.py'):
    if '__pycache__' in str(f) or f.name == 'fullcheck.py':
        continue
    t = f.read_text(encoding='utf-8', errors='ignore')
    todo_count += len(re.findall(r'\b(TODO|FIXME|XXX)\b', t))
warns.append(f"代码中 TODO/FIXME/XXX 标记: {todo_count} 处")

# ---------- 11. .gitignore 基本项 ----------
gi = (ROOT / '.gitignore').read_text(encoding='utf-8')
for need in ['__pycache__', '*.db']:
    if need not in gi:
        warns.append(f".gitignore 缺 {need}")

# ---------- 12. resources 字体（渲染依赖）----------
res = ROOT / 'resources'
fonts = list(res.rglob('*.ttf')) + list(res.rglob('*.otf')) if res.exists() else []
warns.append(f"resources 字体文件: {len(fonts)} 个（缺失时卡片自动降级并记 warning）")

# ---------- 输出 ----------
print(f"metadata 版本: {m_ver}")
print(f"指令注册: {len(cmd_names)} 条")
print(f"字体文件: {len(fonts)}")
print("=" * 40)
print(f"ISSUES ({len(issues)}):")
for x in issues:
    print("  [X]", x)
print(f"WARNINGS ({len(warns)}):")
for x in warns:
    print("  [!]", x)
print("DONE")
