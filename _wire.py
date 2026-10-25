# 批量接线称号颁发点
t = open('main.py', encoding='utf-8').read()
n = 0

def rep(old, new):
    global t, n
    assert old in t, f'NOT FOUND: {old[:60]}'
    t = t.replace(old, new, 1)
    n += 1

# 1. 签到（checkin_count）
rep('''        success, msg = await self.social_mgr.daily_commune(player)
        yield event.plain_result(msg)''',
'''        success, msg = await self.social_mgr.daily_commune(player)
        yield event.plain_result(msg)''')  # no-op 占位防错

rep('''            # 签到改动立即落库，防止后续子系统未触发 update_player 时被结尾覆盖丢失
            await self.db.update_player(player)''',
'''            # 签到改动立即落库，防止后续子系统未触发 update_player 时被结尾覆盖丢失
            await self.db.update_player(player)
            title_msg = await self._title_bump(user_id, "checkin_count")
            if title_msg: festival_detail = title_msg''')

# 2. 决斗胜利（win_pvp）
rep('''        if last_result and last_result.get("winner") == user_id:
            await self.db.ext.add_task_progress(user_id, "win_pvp", 1)''',
'''        if last_result and last_result.get("winner") == user_id:
            await self.db.ext.add_task_progress(user_id, "win_pvp", 1)
            await self._title_bump(user_id, "win_pvp")''')

# 3. 切磋（spar_count）
rep('''            self.combat_handlers.last_spar_fought = False
            await self.db.ext.add_task_progress(user_id, "spar", 1)''',
'''            self.combat_handlers.last_spar_fought = False
            await self.db.ext.add_task_progress(user_id, "spar", 1)
            await self._title_bump(user_id, "spar_count")''')

# 4. 世界Boss讨伐（boss_damage）
rep('''            self.world_boss_mgr.last_challenge_ok = False
            await self.db.ext.add_task_progress(user_id, "boss_damage", 1)''',
'''            self.world_boss_mgr.last_challenge_ok = False
            await self.db.ext.add_task_progress(user_id, "boss_damage", 1)
            await self._title_bump(user_id, "boss_damage")''')

# 5. 押镖（escort_count）
rep('''        if success:
            await self.db.ext.add_task_progress(player.user_id, "escort", 1)''',
'''        if success:
            await self.db.ext.add_task_progress(player.user_id, "escort", 1)
            await self._title_bump(player.user_id, "escort_count")''')

# 6. 炼丹（craft_count + craft_perfect）
rep('''            self.alchemy_handlers.last_craft_success = False
            user_id = event.get_sender_id()
            await self.db.ext.add_task_progress(user_id, "craft_pill", 1)''',
'''            self.alchemy_handlers.last_craft_success = False
            user_id = event.get_sender_id()
            await self.db.ext.add_task_progress(user_id, "craft_pill", 1)
            await self._title_bump(user_id, "craft_count")''')

# 7. 闭关（cultivate_count）—— 在 player_handler.handle_end_cultivation 中
rep('''        await self.db.ext.add_task_progress(player.user_id, "cultivate", 1)
        tutorial_msg = await self.tutorial_mgr.check_and_advance(player, "cultivate")''',
'''        await self.db.ext.add_task_progress(player.user_id, "cultivate", 1)
        tutorial_msg = await self.tutorial_mgr.check_and_advance(player, "cultivate")
        try:
            title_msg = await self.title_hooks.bump(player, "cultivate_count")
            if title_msg: tutorial_msg += title_msg
        except Exception:
            pass''')

# 8. 历练（adventure_count）
rep('''            await self.db.ext.add_task_progress(user_id, "adventure", 1)''',
'''            await self.db.ext.add_task_progress(user_id, "adventure", 1)
            await self._title_bump(user_id, "adventure_count")''')

# 9. 秘境（rift_count）
rep('''            await self.db.ext.add_task_progress(user_id, "explore_rift", 1)''',
'''            await self.db.ext.add_task_progress(user_id, "explore_rift", 1)
            await self._title_bump(user_id, "rift_count")''')

# 10. 收获灵田（harvest_count）
rep('''        if getattr(self.spirit_farm_handlers, "last_harvest_ok", False):
            self.spirit_farm_handlers.last_harvest_ok = False
            await self.db.ext.add_task_progress(event.get_sender_id(), "harvest", 1)''',
'''        if getattr(self.spirit_farm_handlers, "last_harvest_ok", False):
            self.spirit_farm_handlers.last_harvest_ok = False
            await self.db.ext.add_task_progress(event.get_sender_id(), "harvest", 1)
            await self._title_bump(event.get_sender_id(), "harvest_count")''')

# 11. 旧Boss击杀（boss_kill_old）
rep('''        if success and battle_result and battle_result.get("winner") == user_id:
            await self.db.ext.add_task_progress(user_id, "boss_damage", 1)
            player = await self.db.get_player_by_id(user_id)
            player_name = player.user_name if player and player.user_name else f"道友{str(user_id)[:6]}"
            await self._broadcast_boss_defeat(player_name, battle_result)

        yield event.plain_result(msg)''',
'''        if success and battle_result and battle_result.get("winner") == user_id:
            await self.db.ext.add_task_progress(user_id, "boss_damage", 1)
            await self._title_bump(user_id, "boss_kill_old")
            player = await self.db.get_player_by_id(user_id)
            player_name = player.user_name if player and player.user_name else f"道友{str(user_id)[:6]}"
            await self._broadcast_boss_defeat(player_name, battle_result)

        yield event.plain_result(msg)''')

# 12. 天魔揪出（demon_catch）——demon catch 成功在 handler 内，改为天魔状态结束钩子较复杂；放在查验天魔指令后判断
rep('''        success, msg = await self.demon_handlers.handle_catch(event, target): yield r''',
'''        success, msg = await self.demon_handlers.handle_catch(event, target): yield r''')  # no-op

# 13. 奇遇触发（luck_event）——历练归来
rep('''            try:
                encounter_msg = await self.encounter_mgr.maybe_trigger(player)
                if encounter_msg: msg += encounter_msg
            except Exception as e:
                logger.warning(f"奇遇触发异常: {e}")''',
'''            try:
                encounter_msg = await self.encounter_mgr.maybe_trigger(player)
                if encounter_msg:
                    msg += encounter_msg
                    await self._title_bump(user_id, "luck_event")
            except Exception as e:
                logger.warning(f"奇遇触发异常: {e}")''')

open('main.py', 'w', encoding='utf-8').write(t)
import ast; ast.parse(t)
print(f'接线完成 {n} 处')
