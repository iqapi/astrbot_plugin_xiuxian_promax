# 七日行为记录：cultivate/adventure/rift/good(行善+签到)
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

M = 'main.py'

# cultivate
patch(M,
'''        # 悬赏联动（spar/pvp tag）''',
'''        # 七日任务：cultivate 记录在 player_handler（出关处）也可；这里不可靠，改在出关处
        pass
        # 悬赏联动（spar/pvp tag）''', 'noop-spar')  # 占位不生效

# 直接接：出关（player_handler）
PH = 'handlers/player_handler.py'
patch(PH,
'''        # 智能下一步提示
        try:
            from ..managers.next_step import NextStepAdvisor
            tutorial_msg += await NextStepAdvisor(self.db).advise(player, "cultivate")
        except Exception:
            pass''',
'''        # 智能下一步提示
        try:
            from ..managers.next_step import NextStepAdvisor
            tutorial_msg += await NextStepAdvisor(self.db).advise(player, "cultivate")
        except Exception:
            pass
        # 七日任务：闭关
        try:
            if getattr(self, "first_week_ref", None):
                await self.first_week_ref.record_action(player, "cultivate")
        except Exception:
            pass''',
'七日闭关')

# 历练
patch(M,
'''            await self.db.ext.add_task_progress(user_id, "adventure", 1)
            await self._title_bump(user_id, "adventure_count")''',
'''            await self.db.ext.add_task_progress(user_id, "adventure", 1)
            await self._title_bump(user_id, "adventure_count")
            # 七日任务：历练
            try:
                p_adv = await self.db.get_player_by_id(user_id)
                if p_adv:
                    await self.first_week.record_action(p_adv, "adventure")
            except Exception:
                pass''',
'七日历练')

# 秘境
patch(M,
'''                # 智能下一步提示
                try:
                    advise = await self.advisor.advise(player, "rift")
                    if advise: msg += advise
                except Exception:
                    pass''',
'''                # 智能下一步提示
                try:
                    advise = await self.advisor.advise(player, "rift")
                    if advise: msg += advise
                except Exception:
                    pass
                # 七日任务：秘境
                try:
                    await self.first_week.record_action(player, "rift")
                except Exception:
                    pass''',
'七日秘境')

# 行善
patch(M,
'''        # 称号：功德
        try:
            tmsg = await self.title_hooks.bump_value(player, "karma", player.karma)
            if tmsg: yield event.plain_result(tmsg)
        except Exception:
            pass''',
'''        # 称号：功德
        try:
            tmsg = await self.title_hooks.bump_value(player, "karma", player.karma)
            if tmsg: yield event.plain_result(tmsg)
        except Exception:
            pass
        # 七日任务：行善
        try:
            await self.first_week.record_action(player, "good")
        except Exception:
            pass''',
'七日行善')

# 签到（player_handler handle_check_in）
patch(PH,
'''            self._last_checkin_title = await self.title_hooks.bump(player, "checkin_count") if getattr(self, "title_hooks", None) else ""''',
'''            self._last_checkin_title = await self.title_hooks.bump(player, "checkin_count") if getattr(self, "title_hooks", None) else ""
            if getattr(self, "first_week_ref", None):
                await self.first_week_ref.record_action(player, "checkin")''',
'七日签到')

# 注入 first_week_ref 到 PlayerHandler
patch(M,
'''        self.player_handler.social_mgr_ref = self.social_mgr''',
'''        self.player_handler.social_mgr_ref = self.social_mgr
        self.player_handler.first_week_ref = self.first_week''',
'first_week_ref注入')
