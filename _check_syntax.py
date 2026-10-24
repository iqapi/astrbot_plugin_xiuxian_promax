import ast, glob, sys
bad = []
for f in glob.glob('**/*.py', recursive=True):
    if f.startswith('_check'):
        continue
    try:
        ast.parse(open(f, encoding='utf-8').read())
    except SyntaxError as e:
        bad.append(f"{f}:{e.lineno} {e.msg}")
print("ALL SYNTAX OK" if not bad else "\n".join(bad))
sys.exit(1 if bad else 0)
