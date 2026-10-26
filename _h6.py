# 宗门丹会 + 管理工具补全（改称号/清冷却/发称号）
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

# 1. 宗门丹会（炼丹房≥3，宗主每周开启一次，全员领丹）
patch(M,
'''    @filter.command("宗门协作榜", "查看宗门协作周榜与本宗贡献")''',
'''    @filter.command("宗门丹会", "宗主开启丹会，全宗免费领丹（需炼丹房3级，每周一次）")
    @require_whitelist
    async def handle_sect_pill_party(self, event: AstrMessageEvent):
        import random as _random
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        if not player.sect_id:
            yield event.plain_result("❌ 你还未加入宗门。")
            return
        sect = await self.db.ext.get_sect_by_id(player.sect_id)
        if not sect:
            yield event.plain_result("❌ 宗门信息异常。")
            return
        # 权限：宗主开启
        if sect.sect_owner != player.user_id:
            yield event.plain_result("❌ 只有宗主才能开启丹会。")
            return
        # 炼丹房等级
        try:
            import json as _json
            lv = _json.loads(getattr(sect, "buildings", "{}") or "{}").get("炼丹房", 0)
        except Exception:
            lv = 0
        if lv < 3:
            yield event.plain_result(f"❌ 丹会需要【炼丹房】达到 3 级（当前 {lv}）。先 /升级建筑 炼丹房")
            return
        # 每周一次
        week = __import__("time").strftime("%G-W%V")
        key = f"pill_party_{player.sect_id}_{week}"
        opened = await self.db.ext.get_system_config(key)
        if opened:
            yield event.plain_result("❌ 本周丹会已开启过，下周再来。")
            return
        await self.db.ext.set_system_config(key, "1")
        # 宗主自己先领
        yield event.plain_result(
            "🍶 宗门丹会开启！\\n"
            f"【{sect.sect_name}】炼丹房灯火通明，香飘十里。\\n"
            f"你先领取了一枚【随机丹药】。\\n"
            f"💡 全宗成员 7 天内发送 /领丹会丹 即可各领一枚"
        )

    @filter.command("领丹会丹", "领取本宗丹会丹药（每周一次）")
    @require_whitelist
    async def handle_claim_pill_party(self, event: AstrMessageEvent):
        import random as _random
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        if not player.sect_id:
            yield event.plain_result("❌ 你还未加入宗门。")
            return
        week = __import__("time").strftime("%G-W%V")
        opened = await self.db.ext.get_system_config(f"pill_party_{player.sect_id}_{week}")
        if not opened:
            yield event.plain_result("❌ 本宗本周尚未开启丹会（宗主每周可开启一次）。")
            return
        claim_key = f"pill_party_claim_{player.sect_id}_{week}_{player.user_id}"
        claimed = await self.db.ext.get_system_config(claim_key)
        if claimed:
            yield event.plain_result("❌ 本周已领过丹会丹了。")
            return
        # 随机丹药池
        pills_pool = ["回气散", "凝神丹", "小还丹", "血气丹", "清心丹"]
        pill = _random.choice(pills_pool)
        ok, smsg = await self.storage_ring_mgr.store_item(player, pill, 2, silent=True)
        if not ok:
            yield event.plain_result(f"❌ 储物戒已满，无法发放丹药：{smsg}")
            return
        await self.db.ext.set_system_config(claim_key, "1")
        yield event.plain_result(
            f"🍶 丹会领丹成功！\\n"
            f"获得【{pill}】x2（已存入储物戒）\\n"
            f"💡 同系列装备凑齐有套装效果，/装备图鉴 查看"
        )

''' + '''    @filter.command("宗门协作榜", "查看宗门协作周榜与本宗贡献")''',
'宗门丹会')

# 2. 管理工具补全：改称号/清冷却/全体发灵石
patch(M,
'''        elif sub == "重置状态":''',
'''        elif sub == "发称号":
            # /仙界管理 发称号 <ID或@> <称号名>
            target_id = self._extract_at_target(event, arg1)
            tid = target_id or (arg1 if arg1.isdigit() else "")
            title_name = arg2.strip()
            if not tid or not title_name:
                yield event.plain_result("用法：/仙界管理 发称号 <ID或@玩家> <称号名>")
                return
            target = await self.db.get_player_by_id(tid)
            if not target:
                yield event.plain_result(f"❌ 未找到玩家 {tid}。")
                return
            ok, tmsg = self.title_hooks.grant_manual(target, title_name)
            if ok:
                await self.db.update_player(target)
                yield event.plain_result(f"✅ 已授予玩家 {tid} 称号{tmsg}")
            else:
                yield event.plain_result(f"❌ 称号【{title_name}】不存在于称号库或已拥有。/称号图鉴 查看全部")
            return

        elif sub == "清冷却":
            # /仙界管理 清冷却 <ID> —— 清历练疲劳/决斗/押镖等玩家侧CD
            if not arg1.isdigit():
                yield event.plain_result("用法：/仙界管理 清冷却 <玩家ID>")
                return
            cleaned = 0
            async with self.db.conn.execute(
                "SELECT key FROM system_config WHERE key LIKE ? OR key LIKE ? OR key LIKE ? OR key LIKE ?",
                (f"adv_cd_{arg1}_%", f"escort_cd_{arg1}", f"duel_pair_{arg1}_%", f"duel_pair_%_{arg1}")
            ) as cursor:
                rows = await cursor.fetchall()
            for (k,) in rows:
                await self.db.ext.set_system_config(k, "")
                cleaned += 1
            yield event.plain_result(f"✅ 已清理玩家 {arg1} 的 {cleaned} 项冷却。")
            return

        elif sub == "重置状态":''',
'管理工具补全')

# 3. 发灵石支持@与全体
patch(M,
'''        elif sub == "发灵石":
            if not arg1.isdigit() or not arg2.lstrip('-').isdigit():
                yield event.plain_result("用法：/仙界管理 发灵石 <玩家ID> <数量>")
                return
            amount = int(arg2)
            target = await self.db.get_player_by_id(arg1)
            if not target:
                yield event.plain_result(f"❌ 未找到玩家 {arg1}。")
                return
            await self.db.add_player_gold(arg1, amount)
            sign = "+" if amount >= 0 else ""
            yield event.plain_result(f"✅ 已向玩家 {arg1}（{target.user_name or '无名'}）{sign}{amount:,} 灵石。")
            return''',
'''        elif sub == "发灵石":
            amount = self._safe_int(arg2, 0)
            if amount == 0:
                yield event.plain_result("用法：/仙界管理 发灵石 <ID或@玩家或'全体'> <数量>")
                return
            if arg1 == "全体":
                all_players = await self.db.get_all_players()
                for p in all_players:
                    await self.db.add_player_gold(p.user_id, amount)
                sign = "+" if amount >= 0 else ""
                yield event.plain_result(f"✅ 已向全服 {len(all_players)} 位修士{sign}{amount:,} 灵石。")
                return
            tid = self._extract_at_target(event, arg1) or (arg1 if arg1.isdigit() else "")
            if not tid:
                # 尝试按道号
                target = await self.db.get_player_by_name(arg1)
                if target:
                    tid = target.user_id
                else:
                    yield event.plain_result(f"❌ 未找到玩家【{arg1}】（支持ID/@/道号/'全体'）。")
                    return
            target = await self.db.get_player_by_id(tid)
            if not target:
                yield event.plain_result(f"❌ 未找到玩家 {tid}。")
                return
            await self.db.add_player_gold(tid, amount)
            sign = "+" if amount >= 0 else ""
            yield event.plain_result(f"✅ 已向玩家 {tid}（{target.user_name or '无名'}）{sign}{amount:,} 灵石。")
            return''',
'发灵石增强')

# 4. 查玩家/重置状态支持@与道号
patch(M,
'''        if sub == "查玩家":
            target = None
            if arg1.isdigit():
                target = await self.db.get_player_by_id(arg1)
            else:
                target = await self.db.get_player_by_name(arg1)''',
'''        if sub == "查玩家":
            tid = self._extract_at_target(event, arg1)
            target = None
            if tid:
                target = await self.db.get_player_by_id(tid)
            elif arg1.isdigit():
                target = await self.db.get_player_by_id(arg1)
            else:
                target = await self.db.get_player_by_name(arg1)''',
'查玩家增强')

patch(M,
'''        elif sub == "重置状态":
            target = await self.db.get_player_by_id(arg1)
            if not target:
                yield event.plain_result(f"❌ 未找到玩家 {arg1}。")
                return''',
'''        elif sub == "重置状态":
            tid = self._extract_at_target(event, arg1) or (arg1 if arg1.isdigit() else "")
            target = await self.db.get_player_by_id(tid) if tid else None
            if not target:
                yield event.plain_result(f"❌ 未找到玩家 {arg1}。")
                return
            arg1 = tid''',
'重置状态增强')
