# 全局体检修复版
import ast, json, re, glob, sys, os

issues = []
files = [f for f in glob.glob('**/*.py', recursive=True) if not f.startswith('_') and 'tests' not in f]
for f in files:
    try:
        ast.parse(open(f, encoding='utf-8').read())
    except SyntaxError as e:
        issues.append(f"[语法] {f}:{e.lineno} {e.msg}")
print(f"1. 语法检查：{len(files)} 个文件")

main_t = open('main.py', encoding='utf-8').read()
const_map = dict(re.findall(r'^(CMD_\w+)\s*=\s*"([^"]+)"', main_t, re.M))
cmds = set()
for m in re.finditer(r'@filter\.command\(\s*([^,\s]+)', main_t):
    arg = m.group(1).strip().rstrip(',')
    if arg.startswith('"'):
        cmds.add(arg.strip('"'))
    elif arg in const_map:
        cmds.add(const_map[arg])
help_t = open('handlers/misc_handler.py', encoding='utf-8').read()
missing = [c for c in cmds if c not in help_t]
if missing:
    issues.append(f"[帮助] 缺失: {missing}")
print(f"2. 指令一致性：{len(cmds)} 条，缺失 {len(missing)}")

meta = open('metadata.yaml', encoding='utf-8').read()
m_ver = re.search(r'version:\s*(\S+)', meta)
print(f"3. metadata: {m_ver.group(1) if m_ver else 'NOT FOUND'}")

print("=" * 40)
print("全局体检全部通过 ✅" if not issues else "发现问题：\n" + "\n".join(issues))
sys.exit(1 if issues else 0)
