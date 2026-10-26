# 删除管理员手动生成Boss入口（风险排查：spawn 仅在手动指令中调用；自动调度走 world_boss_mgr.spawn_boss）
t = open('main.py', encoding='utf-8').read()

# 1. 删除新Boss手动生成
old1 = '''    @filter.command("生成世界Boss", "手动召唤世界Boss(管理员)")
    @require_whitelist
    async def handle_spawn_world_boss(self, event: AstrMessageEvent):
        if not self._check_boss_admin(event):
            yield event.plain_result("❌ 你没有权限！")
            return
        success, msg = await self.world_boss_mgr.spawn_boss()
        yield event.plain_result(msg)

'''
assert old1 in t, 'spawn_world_boss not found'
t = t.replace(old1, '', 1)

# 2. 删除旧Boss手动生成
old2 = '''    @filter.command(CMD_SPAWN_BOSS, "生成世界Boss(旧)")
    @require_whitelist
    async def handle_spawn_boss(self, event: AstrMessageEvent):
        if not self._check_boss_admin(event):
            yield event.plain_result("❌ 你没有权限生成Boss！")
            return
        success, msg, boss = await self.boss_handlers.handle_spawn_boss()
        yield event.plain_result(msg)
        if success and boss:
            await self._broadcast_boss_spawn(boss)

'''
assert old2 in t, 'spawn_boss not found'
t = t.replace(old2, '', 1)

# 3. 帮助菜单移除"生成Boss/生成世界Boss"
old3 = '''            "  /生成世界Boss /生成Boss /开启魔潮\\n"'''
new3 = '''            "  /开启魔潮 (Boss每周自动降临3次,无需手动)\\n"'''
assert old3 in t
t = t.replace(old3, new3, 1)

open('main.py', 'w', encoding='utf-8').write(t)
import ast; ast.parse(t)
print('手动生成入口删除 OK')
