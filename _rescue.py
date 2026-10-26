t = open('main.py', encoding='utf-8').read()

# 1. 定位误插到头部的月度块（从开头到 "await self.db.ext.set_system_config(f"month_title_{month_key}", "1")" 之后直到块尾）
lines = t.splitlines(keepends=True)
# 找月度块结束：最后一个 broadcast 行
end_idx = next(i for i, l in enumerate(lines) if '_broadcast_world_boss_spawn(broadcast)' in l)
# 块之后紧跟着可能还有残留 except（原结构的）
block = lines[0:end_idx+1]
rest = lines[end_idx+1:]
# 剥离 rest 开头的孤儿 except（如果有）
while rest and rest[0].strip().startswith(('except', 'pass', 'break', 'logger.error', 'await asyncio.sleep(60)')):
    rest.pop(0)
# 也可能 rest 开头还有 '# =====' 注释前的空行——保留
block_text = ''.join(block).lstrip('\n')
t = ''.join(rest)
# 2. 现在 main.py 头部应该是原 import 区（被剪切后还原了吗？没有！原 import 区在块之前的 lines 已被切掉）
# 检查：rest 里有没有 import asyncio？
print('rest 头 200 字符:', ''.join(rest)[:200])
open('main.py', 'w', encoding='utf-8').write(t)
open('_month_block.txt', 'w', encoding='utf-8').write(block_text)
print('月度块已暂存到 _month_block.txt')
