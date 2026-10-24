import glob, re
for f in glob.glob('**/*.py', recursive=True):
    if f.startswith('_'):
        continue
    t = open(f, encoding='utf-8').read()
    for i, line in enumerate(t.splitlines(), 1):
        if re.search(r'灵修|体修|魔修|剑修|鬼修|佛修|御兽', line):
            print(f'{f}:{i}: {line.strip()[:120]}')
