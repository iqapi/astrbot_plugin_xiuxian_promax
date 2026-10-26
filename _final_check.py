# 全局体检：py -3 -X utf8 _final_check.py
import ast
import json
import re
import glob
import sys

issues = []
files = [f for f in glob.glob('**/*.py', recursive=True) if not f.startswith('_') and 'tests' not in f]
for f in files:
    try:
        ast.parse(open(f, encoding='utf-8').read())
    except SyntaxError as e:
        issues.append(f"[语法] {f}:{e.lineno} {e.msg}")
print(f"1. 语法检查：{len(files)} 个文件")

for f in files:
    t = open(f, encoding='utf-8').read()
    if re.search(r'\blogger\.', t) and 'import' in t:
        if not re.search(r'from astrbot\.api import .*\blogger\b|^import logging|from astrbot\.api\.logger', t, re.M) \
           and 'logger = ' not in t:
            issues.append(f"[logger] {f} 使用了 logger 但未导入")
print("2. logger 导入检查完成")

main_t = open('main.py', encoding='utf-8').read()
const_map = dict(re.findall(r'^(CMD_\w+)\s*=\s*"([^"]+)"', main_t, re.M))
cmds = set()
for m in re.finditer(r'@filter\.command\(\s*([^,\s]+)\s*(?:,\s*"([^"]*)")?\s*\)', main_t):
    arg = m.group(1)
    if arg.startswith('"'):
        cmds.add(arg.strip('"'))
    elif arg in const_map:
        cmds.add(const_map[arg])
cmds = sorted(cmds)
help_t = open('handlers/misc_handler.py', encoding='utf-8').read()
missing_in_help = [c for c in cmds if c not in help_t]
if missing_in_help:
    issues.append(f"[帮助] 以下指令未出现在 /修仙帮助 中：{missing_in_help}")
print(f"3. 指令一致性：main.py 注册 {len(cmds)} 条指令，帮助覆盖缺失 {len(missing_in_help)} 条")

schema = json.load(open('_conf_schema.json', encoding='utf-8'))
card_keys = [k for k in schema.get('IMAGE_CARDS', {}).get('items', {})]
all_code = ""
for f in files:
    all_code += open(f, encoding='utf-8').read()
for k in card_keys:
    if k == 'ENABLED':
        continue
    if f'card_enabled("{k}")' not in all_code:
        issues.append(f"[配置] schema 键 {k} 未被任何 card_enabled 调用引用")

bgs = set(re.findall(r'render_card\(\s*\n?\s*"(\w+)"', all_code))
import os
for bg in bgs:
    if not os.path.exists(f'resources/backgrouds/{bg}.jpg'):
        issues.append(f"[资源] 卡片引用背景 {bg}.jpg 不存在")
print(f"4-5. 配置键/背景资源对账完成（卡片背景：{sorted(bgs)}）")

meta = open('metadata.yaml', encoding='utf-8').read()
readme = open('README.md', encoding='utf-8').read()
m_ver = re.search(r'version:\s*(\S+)', meta).group(1)
print(f"6. metadata 版本 {m_ver}，README 标题：{readme.splitlines()[0]}")

items = json.load(open('config/items.json', encoding='utf-8'))
item_names = {v['name'] for v in items.values()}
for needed in ('引雷符', '空间石', '化身傀儡', '迷神香', '洗练石', '强化石', '冰火双生花'):
    if needed not in item_names:
        issues.append(f"[物品] 代码依赖的物品【{needed}】不在 items.json")
print("7. 依赖物品存在性检查完成")

print("=" * 40)
if issues:
    print("发现问题：")
    for i in issues:
        print(" -", i)
    sys.exit(1)
else:
    print("全局体检全部通过 ✅")
