# flavor 接入：出关/历练/突破/炼丹/押镖 五个高频场景
def patch(path, old, new, label):
    t = open(path, encoding='utf-8').read()
    if label in t:
        print(f'SKIP: {label}')
        return
    assert old in t, f'NOT FOUND: {label}'
    t = t.replace(old, new, 1)
    open(path, 'w', encoding='utf-8').write(t)
    import ast; ast.parse(t)
    print(f'OK: {label}')

PH = 'handlers/player_handler.py'
M = 'main.py'
AM = 'managers/alchemy_manager.py'
EM = 'managers/escort_manager.py'
CM = 'core/breakthrough_manager.py'

# 1. 出关（player_handler 内）
patch(PH,
'''        # 智能下一步提示（延迟导入避免循环依赖）
        try:
            from ..managers.next_step import NextStepAdvisor
            tutorial_msg += await NextStepAdvisor(self.db).advise(player, "cultivate")
        except Exception:
            pass''',
'''        # 智能下一步提示（延迟导入避免循环依赖）
        try:
            from ..managers.next_step import NextStepAdvisor
            tutorial_msg += await NextStepAdvisor(self.db).advise(player, "cultivate")
        except Exception:
            pass
        # 风味文案
        try:
            from ..managers.flavor import flavor
            tutorial_msg += flavor("cultivate_out")
        except Exception:
            pass''',
'flavor出关')

# 2. 突破成功（breakthrough_manager 成功分支尾部）
patch(CM,
'''            # 师徒联动：弟子突破，师父得师德（v6.16）
            try:
                from ..managers.social_manager import SocialManager
                social = SocialManager(self.db)
                _, mentor_msg = await social.on_disciple_breakthrough(player.user_id)
                if mentor_msg:
                    success_msg += mentor_msg
            except Exception:
                pass''',
'''            # 师徒联动：弟子突破，师父得师德（v6.16）
            try:
                from ..managers.social_manager import SocialManager
                social = SocialManager(self.db)
                _, mentor_msg = await social.on_disciple_breakthrough(player.user_id)
                if mentor_msg:
                    success_msg += mentor_msg
            except Exception:
                pass

            # 风味文案
            try:
                from ..managers.flavor import flavor
                success_msg += flavor("breakthrough_ok")
            except Exception:
                pass''',
'flavor突破')

# 3. 炼丹成功（alchemy_manager 成功消息）
patch(AM,
'''                perfect_note = "\\n🌟 天时地利！此丹竟是【极品】！额外多得一枚同款丹药"''',
'''                perfect_note = "\\n🌟 天时地利！此丹竟是【极品】！额外多得一枚同款丹药"
                try:
                    from ..managers.flavor import flavor
                    perfect_note += flavor("craft_ok")
                except Exception:
                    pass''',
'flavor炼丹')

# 4. 押镖成功（escort_manager finish）
patch(EM,
'''            f"✨ 护镖有功，功德 +1（当前 {player.karma}）"
        )''',
'''            f"✨ 护镖有功，功德 +1（当前 {player.karma}）"
        )
        try:
            from ..managers.flavor import flavor
            msg += flavor("escort_ok")
        except Exception:
            pass
        return True, msg''',
'flavor押镖')

print('flavor 接入完成')
