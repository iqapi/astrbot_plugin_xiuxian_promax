# 出关/历练/秘境/签到 场景接入
n = 0

def patch(path, old, new, label):
    global n
    t = open(path, encoding='utf-8').read()
    if label in t:
        print(f'SKIP: {label}')
        return
    assert old in t, f'NOT FOUND: {label}'
    t = t.replace(old, new, 1)
    open(path, 'w', encoding='utf-8').write(t)
    import ast; ast.parse(t)
    n += 1
    print(f'OK: {label}')

PH = 'handlers/player_handler.py'
M = 'main.py'

# 1. 出关（cultivate）——player_handler 内已有 title bump，但 player_handler 没有 advisor
#    给 PlayerHandler 注入 advisor 引用（main 构造后），此处直接用延迟导入
patch(PH,
'''        try:
            tmsg = await self.title_hooks.bump(player, "cultivate_count")
            if tmsg: tutorial_msg += tmsg
        except Exception:
            pass''',
'''        try:
            tmsg = await self.title_hooks.bump(player, "cultivate_count")
            if tmsg: tutorial_msg += tmsg
        except Exception:
            pass
        # 智能下一步提示（延迟导入避免循环依赖）
        try:
            from ..managers.next_step import NextStepAdvisor
            tutorial_msg += await NextStepAdvisor(self.db).advise(player, "cultivate")
        except Exception:
            pass''',
'出关提示')

# 2. 签到（checkin）——player_handler.handle_check_in 结尾
patch(PH,
'''            if card_path:
                yield event.image_result(card_path)
            else:
                yield event.plain_result(reply_msg)
        except Exception:
            yield event.plain_result(reply_msg)''',
'''            if card_path:
                yield event.image_result(card_path)
            else:
                yield event.plain_result(reply_msg)
            advise_sent = True
        except Exception:
            advise_sent = False
        # 智能下一步提示（文本路径下追加；图片路径下也补发一条精简提示）
        try:
            from ..managers.next_step import NextStepAdvisor
            advise = await NextStepAdvisor(self.db).advise(player, "checkin")
            if advise:
                yield event.plain_result(advise)
        except Exception:
            pass''',
'签到提示')

# 3. 历练归来（main.handle_adventure_complete）
patch(M,
'''            # 奇遇系统：历练归来概率触发三选一事件
            try:
                encounter_msg = await self.encounter_mgr.maybe_trigger(player)
                if encounter_msg:
                    msg += encounter_msg
                    await self._title_bump(user_id, "luck_event")
            except Exception as e:
                logger.warning(f"奇遇触发异常: {e}")''',
'''            # 奇遇系统：历练归来概率触发三选一事件
            try:
                encounter_msg = await self.encounter_mgr.maybe_trigger(player)
                if encounter_msg:
                    msg += encounter_msg
                    await self._title_bump(user_id, "luck_event")
            except Exception as e:
                logger.warning(f"奇遇触发异常: {e}")

            # 智能下一步提示
            try:
                advise = await self.advisor.advise(player, "adventure")
                if advise: msg += advise
            except Exception:
                pass''',
'历练提示')

# 4. 秘境完成（main.handle_rift_complete）
patch(M,
'''                # 奇遇系统：秘境归来概率触发三选一事件（25%）
                try:
                    encounter_msg = await self.encounter_mgr.maybe_trigger(player, base_chance=25)
                    if encounter_msg: msg += encounter_msg
                except Exception as e:
                    logger.warning(f"秘境奇遇触发异常: {e}")''',
'''                # 奇遇系统：秘境归来概率触发三选一事件（25%）
                try:
                    encounter_msg = await self.encounter_mgr.maybe_trigger(player, base_chance=25)
                    if encounter_msg: msg += encounter_msg
                except Exception as e:
                    logger.warning(f"秘境奇遇触发异常: {e}")

                # 智能下一步提示
                try:
                    advise = await self.advisor.advise(player, "rift")
                    if advise: msg += advise
                except Exception:
                    pass''',
'秘境提示')

# 5. 拜师空参提示强化（原提示较朴素，改成显眼版）
patch(M,
'''        if not master_id:
            yield event.plain_result(
                "🎓 拜师\\n━━━━━━━━━━━━━━━\\n"
                "用法：/拜师 @高境界道友\\n"
                "条件：对方境界须高于你 5 级，且门下未满（2人）\\n"
                "收益：师父带你成长，出师双方获大礼"
            )
            return''',
'''        if not master_id:
            yield event.plain_result(
                "🎓【拜师系统】\\n"
                "━━━━━━━━━━━━━━━\\n"
                "📌 用法：/拜师 @高境界道友\\n"
                "📌 条件：对方境界须高于你 5 级，且门下未满（2人）\\n"
                "💰 收益：弟子突破时师父得师德点；出师双方获大礼\\n"
                "📍 出师：弟子达筑基期后，师父发 /出师 @弟子\\n"
                "━━━━━━━━━━━━━━━\\n"
                "💡 师父也可主动 /师徒 查看门下弟子情况"
            )
            return''',
'拜师提示强化')

print(f'共 {n} 处接入')
