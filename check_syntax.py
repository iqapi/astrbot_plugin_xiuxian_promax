import ast, glob, sys
bad = []
for f in glob.glob('**/*.py', recursive=True):
    base = f.replace('\\', '/').split('/')[-1]
    if base == 'check_syntax.py' or f.startswith('.'):
        continue
    try:
        ast.parse(open(f, encoding='utf-8').read())
    except SyntaxError as e:
        bad.append(f"{f}:{e.lineno} {e.msg}")
print("ALL SYNTAX OK" if not bad else "\n".join(bad))
sys.exit(1 if bad else 0)
