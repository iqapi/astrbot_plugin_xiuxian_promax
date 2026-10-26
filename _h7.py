# 月度称号（每月月初自动颁发给全服之最）+ 帮助/版本
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

# 1. 月度称号逻辑（追加到 calamity_manager.auto_check 同一调度里更合适，直接加到 main 的 tide_check）
t = open('main.py', encoding='utf-8').read()
old = '''                settled, msg = await self.calamity_mgr.auto_check()
                if settled and msg:
                    logger.info(f"【修仙插件】魔潮事件：{msg.splitlines()[0]}")
                    await self._broadcast_world_boss_spawn(msg)'''
new = old + '''

                # v6.21 月度称号：每月1日自动颁发全服之最
                try:
                    month_key = time.strftime("%Y%m")
                    done = await self.db.ext.get_system_config(f"month_title_{month_key}")
                    if not done and time.localtime().tm_mday == 1:
                        await self.db.ext.set_system_config(f"month_title_{month_key}", "1")
                        players = await self.db.get_all_players()
                        if players:
                            from .managers.title_manager import TitleManager
                            tm = TitleManager(self.db)
                            top_exp = max(players, key=lambda p: p.experience)
                            top_karma = max(players, key=lambda p: (p.karma or 0))
                            for p, title in ((top_exp, "月度人杰"), (top_karma, "月度大善")):
                                ok, tmsg = tm.grant(p, title)
                            broadcast = (
                                f"🏆【月度盛典】新的一月，天道册封上月之最：\\n"
                                f"  · 修为至尊：【{top_exp.user_name or top_exp.user_id[:8]}】\\n"
                                f"  · 第一大善：【{top_karma.user_name or top_karma.user_id[:8]}】\\n"
                                f"获得月度限定称号，全服敬仰！"
                            )
                            await self._broadcast_world_boss_spawn(broadcast)
            except Exception:
                pass'''
assert old in t
t = t.replace(old, new, 1)
open('main.py', 'w', encoding='utf-8').write(t)
import ast; ast.parse(t)
print('月度称号 OK')

# 2. 月度称号入称号池（manual 路径）
t2 = open('managers/title_data.py', encoding='utf-8').read()
if '"月度人杰"' not in t2:
    old2 = '''    # ========== 帝品（唯一性/隐藏，8）=========='''
    new2 = '''    T("月度人杰", 5, "manual", atk=300, exp=0.25, luck=15),
    T("月度大善", 5, "manual", atk=150, exp=0.20, luck=25),

    # ========== 帝品（唯一性/隐藏，8）=========='''
    assert old2 in t2
    t2 = t2.replace(old2, new2, 1)
    open('managers/title_data.py', 'w', encoding='utf-8').write(t2)
    ast.parse(t2)
    print('月度称号池 OK')

# 3. 帮助菜单
t3 = open('handlers/misc_handler.py', encoding='utf-8').read()
old3 = '''            "  /新手七日 (新道友必看) /仙谱 (全服排位)\\n"'''
new3 = '''            "  /新手七日 (新道友必看) /仙谱 (全服排位)\\n"
            "  /装备图鉴 (套装鉴识) /信箱 (离线事件)\\n"'''
assert old3 in t3
t3 = t3.replace(old3, new3, 1)
t3 = t3.replace("📖 修仙指令大全 v6.20 (天命可期版)", "📖 修仙指令大全 v6.21 (万象归一版)")
open('handlers/misc_handler.py', 'w', encoding='utf-8').write(t3)
print('帮助 OK')

# 4. 版本
t4 = open('metadata.yaml', encoding='utf-8').read()
t4 = t4.replace('version: v3.17.0', 'version: v3.18.0')
open('metadata.yaml', 'w', encoding='utf-8').write(t4)
print('版本 v3.18.0')
