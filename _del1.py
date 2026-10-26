# 删除旧Boss系统（main 指令×3、boss_handlers、boss_manager、广播×2、帮助清理、称号迁移）
import re

# ===== 1. main.py 删3条旧指令 + 相关调用 =====
t = open('main.py', encoding='utf-8').read()

# 删除旧Boss信息/挑战/生成区块
old1 = re.search(r'    # ===== 旧Boss =====\n(?:    @filter\.command\(CMD_BOSS_INFO.*\n|    @require_whitelist\n|    async def handle_boss_info.*\n|    async for.*\n|.)*?@filter\.command\(CMD_BOSS_FIGHT.*?yield event\.plain_result\(msg\)\n(?:.*\n)*?            await self\._broadcast_boss_defeat\(player_name, battle_result\)\n\n', t)
# 简化：直接用字符串锚点切三大块
i1 = t.find('    # ===== 旧Boss =====')
if i1 > 0:
    i2 = t.find('    # ===== 排行榜 =====', i1)
    assert i1 > 0 and i2 > i1, f'锚点失败 {i1} {i2}'
    t = t[:i1] + t[i2:]
    print('旧Boss指令区块已删除')
else:
    print('警告: 未找到旧Boss区块')

# 2. 删除 _broadcast_boss_defeat / _broadcast_boss_spawn 函数
for fn in ('_broadcast_boss_defeat', '_broadcast_boss_spawn'):
    i = t.find(f'    async def {fn}')
    if i > 0:
        j = t.find('    async def ', i + 10)
        t = t[:i] + t[j:]
        print(f'删除 {fn}')

# 3. 删除 boss_handlers / boss_mgr 实例化
t = t.replace('        self.boss_handlers = BossHandlers(self.db, self.boss_mgr)\n', '', 1)
t = t.replace('        self.boss_mgr = BossManager(self.db, self.combat_mgr, self.config_manager, self.storage_ring_mgr)\n', '', 1)
# 导入清理
t = t.replace('    BossHandlers, CombatHandlers, RankingHandlers,\n', '    CombatHandlers, RankingHandlers,\n', 1)
t = t.replace('    CombatManager, SectManager, BossManager, RiftManager,\n', '    CombatManager, SectManager, RiftManager,\n', 1)

open('main.py', 'w', encoding='utf-8').write(t)
import ast; ast.parse(t)
print('main.py 清理完成')

# ===== 4. 删除旧Boss调用残留（boss_damage 任务在旧Boss挑战中，删除后检查）=====
t2 = open('main.py', encoding='utf-8').read()
# 查剩余 boss_handlers/boss_mgr 引用
left = re.findall(r'self\.boss_handlers\.\w+|self\.boss_mgr\.\w+', t2)
print('main 剩余旧Boss引用:', left or '无')
if left:
    raise SystemExit('有残留，停止')
