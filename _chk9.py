import ast
t = open('main.py', encoding='utf-8').read()
ast.parse(t)
print('语法状态:')
i = t.find('# 悬赏联动（spar/pvp tag）')
print(repr(t[max(0,i-200):i+80]) if i>0 else 'spar hook 不存在?')
