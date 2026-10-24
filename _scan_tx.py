import re, glob
for f in glob.glob('**/*.py', recursive=True):
    if f.startswith('_'):
        continue
    lines = open(f, encoding='utf-8').read().splitlines()
    in_tx = False
    for i, ln in enumerate(lines, 1):
        if 'BEGIN IMMEDIATE' in ln:
            in_tx = True
        if in_tx and ('conn.commit()' in ln or 'conn.rollback()' in ln):
            in_tx = False
        if in_tx and re.search(r'(store_item|retrieve_item|discard_item)\(', ln) \
           and 'external_transaction=True' not in ln and 'def ' not in ln:
            print(f'{f}:{i}: {ln.strip()}')
print('nested-tx scan done')
