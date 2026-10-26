def patch(path, old, new, label):
    t = open(path, encoding='utf-8').read()
    if label in t:
        print(f'SKIP: {label}')
        return
    assert old in t, f'NF: {label}'
    t = t.replace(old, new, 1)
    open(path, 'w', encoding='utf-8').write(t)
    import ast; ast.parse(t)
    print(f'OK: {label}')

EM = 'managers/escort_manager.py'
CAL = 'managers/calamity_manager.py'
CH = 'handlers/combat_handlers.py'

# 押镖CD写入
patch(EM,
'''        player.gold += escort_gold
        player.experience += escort_exp
        player.karma = (getattr(player, "karma", 0) or 0) + 1  # 护镖有功，功德+1
        await self.db.update_player(player)
        await self.db.ext.set_user_free(user_id)''',
'''        player.gold += escort_gold
        player.experience += escort_exp
        player.karma = (getattr(player, "karma", 0) or 0) + 1  # 护镖有功，功德+1
        await self.db.update_player(player)
        await self.db.ext.set_user_free(user_id)
        # 接单冷却（10分钟）
        await self.db.ext.set_system_config(f"escort_cd_{user_id}", str(int(time.time()) + 600))''',
'押镖CD写入')

# 魔潮日志
patch(CAL,
'''        players = await self.db.get_all_players()
        if len(players) < 3:
            return False, ""''',
'''        players = await self.db.get_all_players()
        if len(players) < 3:
            from astrbot.api import logger
            logger.warning(f"【修仙插件】今日为魔潮自动开启日，但全服仅 {len(players)} 人（需≥3），本次跳过")
            return False, ""''',
'魔潮日志')

# 决斗同对手冷却
patch(CH,
'''        # 决斗冷却检查（5分钟）
        cooldowns = await self._get_combat_cooldown(user_id)
        now = int(time.time())
        remaining_cd = DUEL_COOLDOWN - (now - cooldowns["last_duel_time"])
        if cooldowns["last_duel_time"] and remaining_cd > 0:
            yield event.plain_result(
                f"❌ 决斗调息中，请 {remaining_cd // 60} 分 {remaining_cd % 60} 秒后再战。"
            )
            return''',
'''        # 决斗冷却检查（5分钟，且同对手30分钟内不可重复挑战——防轮换刷称号）
        cooldowns = await self._get_combat_cooldown(user_id)
        now = int(time.time())
        remaining_cd = DUEL_COOLDOWN - (now - cooldowns["last_duel_time"])
        if cooldowns["last_duel_time"] and remaining_cd > 0:
            yield event.plain_result(
                f"❌ 决斗调息中，请 {remaining_cd // 60} 分 {remaining_cd % 60} 秒后再战。"
            )
            return
        # 同对手30分钟冷却
        duo_key = f"duel_pair_{user_id}_{target_id}"
        duo_val = await self.db.ext.get_system_config(duo_key)
        if duo_val and duo_val.isdigit() and now < int(duo_val):
            remain = int(duo_val) - now
            yield event.plain_result(
                f"❌ 你与该对手刚刚交过手（{remain // 60} 分 {remain % 60} 秒后可再战）。\\n"
                f"💡 换个对手，或等冷却结束。"
            )
            return''',
'决斗同对手冷却')

patch(CH,
'''        await self._update_combat_cooldown(user_id, "duel")
        
        yield event.plain_result("\\n".join(result['combat_log']))''',
'''        await self._update_combat_cooldown(user_id, "duel")
        await self.db.ext.set_system_config(f"duel_pair_{user_id}_{target_id}", str(now + 1800))
        
        yield event.plain_result("\\n".join(result['combat_log']))''',
'决斗CD写入')

print('三缺陷修复完成')
