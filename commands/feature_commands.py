# commands/feature_commands.py
"""v3.19.0 ~ v3.22.0 新玩法指令 Mixin（v3.24.0 自 main.py 拆出）

XiuXianPlugin 继承本 Mixin；所有 handler 通过 self.* 访问主插件的管理器实例。
拆分仅为可维护性，指令注册语义不变（装饰器随类定义生效，继承链可被发现）。
"""
from astrbot.api.event import AstrMessageEvent  # noqa: F401
from astrbot.api.event import filter

from .base import require_whitelist, CardMixin


class FeatureCommandsMixin(CardMixin):
    """新玩法指令集合（斗法台/拍卖行/结契/科举/罗盘/登仙台/悬赏行会等）"""

    async def _board_card(self, event, text: str, bg: str, title: str, subtitle: str = "", footer: str = ""):
        """面板类文本 → 卡片（CardMixin.send_text_card 的薄封装）"""
        async for r in self.send_text_card(event, text, bg, title, subtitle, footer):
            yield r

    # ===== v3.19.0 新玩法指令 =====

    @filter.command("修仙天气", "查看今日天象与加成")
    @require_whitelist
    async def handle_weather_cmd(self, event: AstrMessageEvent):
        async for r in self.weather_mgr.handle_weather(event):
            yield r

    @filter.command("收集图鉴", "查看称号图鉴收集进度与奖励")
    @require_whitelist
    async def handle_collection_cmd(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        grant_msg = await self.collection_mgr.check_and_grant(player)
        async for r in self.collection_mgr.handle_collection(player, event):
            yield r
        if grant_msg:
            yield event.plain_result(grant_msg)

    @filter.command("签到里程碑", "查看本月签到进度与奖励")
    @require_whitelist
    async def handle_ckms_cmd(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        async for r in self.ckms_mgr.handle_milestone(player, event):
            yield r

    @filter.command("天骄榜", "查看天骄榜赛季排行")
    @require_whitelist
    async def handle_season_board(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        # v3.23.0：榜单只读——赛季推进/结算统一由定时循环触发，防并发双结算
        buf = []
        async for r in self.season_mgr.handle_board(player, event):
            buf.append(str(r))
        async for r in self._board_card(event, "\n".join(buf), "rank", "🏆 天骄榜", "90 天赛季 · 修为增量排行",
                                        footer="榜一：50000 灵石 + 限定称号"):
            yield r

    @filter.command("观礼", "查看渡劫观礼奖池")
    @require_whitelist
    async def handle_trib_pool(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        async for r in self.tribbet_mgr.handle_pool(player, event):
            yield r

    @filter.command("观礼下注", "渡劫观礼下注：/观礼下注 <金额> [败]")
    @require_whitelist
    async def handle_trib_bet(self, event: AstrMessageEvent, arg: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        parts = (arg or "").split()
        if not parts or not parts[0].isdigit():
            yield event.plain_result("用法：/观礼下注 <金额> [败]\n💡 末尾加'败'即押渡劫失败，不加则押成功。金额 100-100000。")
            return
        side = "fail" if len(parts) > 1 and "败" in parts[1] else "success"
        ok, msg = await self.tribbet_mgr.place_bet(player, int(parts[0]), side)
        yield event.plain_result(msg)

    @filter.command("轮回宝阁", "周目专属商店（轮回玉兑换）")
    @require_whitelist
    async def handle_samsara_shop(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        async for r in self.samsara_mgr.handle_shop(player, event):
            yield r

    @filter.command("轮回兑换", "轮回宝阁兑换：/轮回兑换 <编号>")
    @require_whitelist
    async def handle_samsara_buy(self, event: AstrMessageEvent, arg: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        async for r in self.samsara_mgr.handle_buy(player, event, arg):
            yield r

    @filter.command("轮回信息", "查看轮回周目信息")
    @require_whitelist
    async def handle_samsara_info(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        async for r in self.samsara_mgr.handle_info(player, event):
            yield r

    @filter.command("灵植园", "群聊灵植园：/灵植园 或 /灵植园 种下 <作物名>")
    @require_whitelist
    async def handle_garden_cmd(self, event: AstrMessageEvent, arg: str = ""):
        group_id = str(event.get_group_id() or "")
        if not group_id:
            yield event.plain_result("❌ 灵植园仅在群聊中开放。")
            return
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        if arg.strip().startswith("种下"):
            crop_name = arg.strip()[2:].strip()
            ok, msg = await self.garden_mgr.plant(group_id, player, crop_name)
            yield event.plain_result(msg)
            return
        msg = await self.garden_mgr.handle_garden(group_id, event)
        yield event.plain_result(msg)

    @filter.command("照料灵园", "照料群聊灵植园（每人每日2次）")
    @require_whitelist
    async def handle_garden_tend(self, event: AstrMessageEvent):
        group_id = str(event.get_group_id() or "")
        if not group_id:
            yield event.plain_result("❌ 灵植园仅在群聊中开放。")
            return
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        ok, msg = await self.garden_mgr.tend(group_id, player)
        yield event.plain_result(msg)

    @filter.command("收取灵园", "收取成熟的灵植园产出")
    @require_whitelist
    async def handle_garden_harvest(self, event: AstrMessageEvent):
        group_id = str(event.get_group_id() or "")
        if not group_id:
            yield event.plain_result("❌ 灵植园仅在群聊中开放。")
            return
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        ok, msg = await self.garden_mgr.harvest(group_id, player)
        yield event.plain_result(msg)

    @filter.command("道侣试炼", "与道侣的每周共同任务")
    @require_whitelist
    async def handle_couple_quest(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        msg = await self.couple_quest_mgr.handle_quest(player, event)
        yield event.plain_result(msg)

    @filter.command("灵脉战", "查看仙盟灵脉据点战况")
    @require_whitelist
    async def handle_stronghold_board(self, event: AstrMessageEvent):
        msg = await self.stronghold_mgr.handle_board(event)
        async for r in self._board_card(event, msg, "war", "⚔️ 灵脉据点战", "仙盟争霸 · 本周战况",
                                        footer="进攻灵脉 <编号> <灵石> · 1灵石=1分"):
            yield r

    @filter.command("进攻灵脉", "为宗门进攻灵脉据点：/进攻灵脉 <编号1-5> <灵石>")
    @require_whitelist
    async def handle_stronghold_attack(self, event: AstrMessageEvent, arg: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        parts = (arg or "").split()
        if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
            yield event.plain_result("用法：/进攻灵脉 <编号1-5> <灵石>")
            return
        ok, msg = await self.stronghold_mgr.attack(player, int(parts[0]), int(parts[1]))
        yield event.plain_result(msg)

    @filter.command("扫荡秘境", "战力碾压的秘境可跳过探索直领收益：/扫荡秘境 <编号>")
    @require_whitelist
    async def handle_rift_sweep(self, event: AstrMessageEvent, arg: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        if not (arg or "").strip().isdigit():
            yield event.plain_result("用法：/扫荡秘境 <秘境编号>（需境界超出该秘境需求 10 级以上）")
            return
        ok, msg = await self.rift_enhance_mgr.sweep(player, int(arg.strip()))
        yield event.plain_result(msg)

    @filter.command("秘境词缀", "查看今日全服秘境词缀")
    @require_whitelist
    async def handle_rift_affix(self, event: AstrMessageEvent):
        async for r in self.rift_enhance_mgr.handle_affix(event):
            yield r

    @filter.command("悬赏行会", "查看玩家悬赏池")
    @require_whitelist
    async def handle_pblty_board(self, event: AstrMessageEvent):
        buf = []
        async for r in self.pblty_mgr.handle_board(event):
            buf.append(str(r))
        async for r in self._board_card(event, "\n".join(buf), "market", "📜 悬赏行会", "玩家悬赏 · 赏金托管",
                                        footer="发布悬赏 <描述> <赏金> · 接玩家悬赏 <编号>"):
            yield r

    @filter.command("发布悬赏", "发布玩家悬赏：/发布悬赏 <描述> <赏金>")
    @require_whitelist
    async def handle_pblty_post(self, event: AstrMessageEvent, arg: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        parts = (arg or "").rsplit(maxsplit=1)
        if len(parts) < 2 or not parts[1].isdigit():
            yield event.plain_result("用法：/发布悬赏 <描述> <赏金>（描述 2-30 字，赏金 1000-500000，预扣托管）")
            return
        ok, msg = await self.pblty_mgr.post(player, parts[0].strip(), int(parts[1]))
        yield event.plain_result(msg)

    @filter.command("接玩家悬赏", "接取玩家悬赏：/接玩家悬赏 <编号>")
    @require_whitelist
    async def handle_pblty_take(self, event: AstrMessageEvent, arg: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        if not (arg or "").strip().isdigit():
            yield event.plain_result("用法：/接玩家悬赏 <编号>（/悬赏行会 查看）")
            return
        ok, msg = await self.pblty_mgr.take(player, int(arg.strip()))
        yield event.plain_result(msg)

    @filter.command("玩家悬赏完成", "提交玩家悬赏领取赏金：/玩家悬赏完成 <编号>")
    @require_whitelist
    async def handle_pblty_done(self, event: AstrMessageEvent, arg: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        if not (arg or "").strip().isdigit():
            yield event.plain_result("用法：/玩家悬赏完成 <编号>")
            return
        ok, msg = await self.pblty_mgr.verify_and_pay(player, int(arg.strip()))
        yield event.plain_result(msg)

    @filter.command("玩家悬赏取消", "取消自己发布的玩家悬赏：/玩家悬赏取消 <编号>")
    @require_whitelist
    async def handle_pblty_cancel(self, event: AstrMessageEvent, arg: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        if not (arg or "").strip().isdigit():
            yield event.plain_result("用法：/玩家悬赏取消 <编号>")
            return
        ok, msg = await self.pblty_mgr.cancel(player, int(arg.strip()))
        yield event.plain_result(msg)

    # ===== v3.20.0 第二批新玩法指令 =====

    @filter.command("科举", "修仙科举答题：每日3次，答对得修为")
    @require_whitelist
    async def handle_quiz(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        async for r in self.quiz_mgr.handle_quiz(player, event):
            yield r

    @filter.command("答题", "科举作答：/答题 <题号> <A/B/C/D>")
    @require_whitelist
    async def handle_quiz_answer(self, event: AstrMessageEvent, arg: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        parts = (arg or "").split()
        if len(parts) < 2 or not parts[0].isdigit():
            yield event.plain_result("用法：/答题 <题号> <A/B/C/D>")
            return
        ok, msg = await self.quiz_mgr.answer(player, int(parts[0]), parts[1].upper()[:1])
        yield event.plain_result(msg)

    @filter.command("罗盘", "幸运罗盘：每日免费1抽，/罗盘 抽 <N> 付费连抽")
    @require_whitelist
    async def handle_wheel(self, event: AstrMessageEvent, arg: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        async for r in self.wheel_mgr.handle_wheel(player, event, (arg or "").strip()):
            yield r

    @filter.command("结契", "与另一位道友结为道侣：/结契 @道友")
    @require_whitelist
    async def handle_marriage_propose(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        target_id = self._extract_at_target(event)
        if not target_id:
            yield event.plain_result("用法：/结契 @道友（对方发送 /接受结契 确认，5 分钟内有效）")
            return
        if target_id == player.user_id:
            yield event.plain_result("❌ 不能与自己结契。")
            return
        target = await self.db.get_player_by_id(target_id)
        if not target:
            yield event.plain_result(f"❌ 对方（QQ:{target_id}）尚未开始修仙。")
            return
        ok, msg = await self.marriage_mgr.propose(player, target)
        yield event.plain_result(msg)

    @filter.command("接受结契", "接受道友的结契提议")
    @require_whitelist
    async def handle_marriage_accept(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        ok, msg = await self.marriage_mgr.accept(player)
        yield event.plain_result(msg)

    @filter.command("解除结契", "解除道侣契约（需 1 万灵石分手费）")
    @require_whitelist
    async def handle_marriage_divorce(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        ok, msg = await self.marriage_mgr.divorce(player)
        yield event.plain_result(msg)

    @filter.command("结契信息", "查看道侣结契信息与羁绊加成")
    @require_whitelist
    async def handle_marriage_info(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        msg = await self.marriage_mgr.handle_info(player, event)
        yield event.plain_result(msg)

    @filter.command("成就", "查看修仙成就与完成状态")
    @require_whitelist
    async def handle_achievement(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        msg = await self.achievement_mgr.handle_list(player, event)
        async for r in self._board_card(event, msg, "ach", "🏅 修仙成就", "里程碑 · 一期一会",
                                        footer="成就领取 <编号> · 不可重复领取"):
            yield r

    @filter.command("成就领取", "领取已达成的成就奖励：/成就领取 <编号>")
    @require_whitelist
    async def handle_achievement_claim(self, event: AstrMessageEvent, arg: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        if not (arg or "").strip():
            yield event.plain_result("用法：/成就领取 <编号>（/成就 查看列表）")
            return
        ok, msg = await self.achievement_mgr.claim(player, arg.strip())
        yield event.plain_result(msg)

    @filter.command("灵兽出战", "让契约灵兽协修（修炼/历练加成）")
    @require_whitelist
    async def handle_pet_battle(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        ok, msg = await self.petbattle_mgr.set_battle_pet(player)
        yield event.plain_result(msg)

    @filter.command("灵兽休战", "收回出战灵兽")
    @require_whitelist
    async def handle_pet_unbattle(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        ok, msg = await self.petbattle_mgr.unset(player)
        yield event.plain_result(msg)

    @filter.command("出战信息", "查看出战灵兽与协修加成")
    @require_whitelist
    async def handle_pet_battle_info(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        async for r in self.petbattle_mgr.handle_info(player, event):
            yield r

    @filter.command("夺宝", "抢夺现世的天材地宝（先到先得）")
    @require_whitelist
    async def handle_treasure_grab(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        ok, msg = await self.treasure_mgr.grab(player)
        yield event.plain_result(msg)

    @filter.command("天材地宝", "查看天材地宝现世状态")
    @require_whitelist
    async def handle_treasure_status(self, event: AstrMessageEvent):
        async for r in self.treasure_mgr.handle_status(event):
            yield r

    # ===== v3.21.0 第三批新玩法指令 =====

    @filter.command("宗门科技", "查看宗门科技等级")
    @require_whitelist
    async def handle_sect_tech_board(self, event: AstrMessageEvent):
        msg = await self.sect_tech_mgr.handle_board(event)
        async for r in self._board_card(event, msg, "sect", "🏛️ 宗门科技", "全宗被动加成",
                                        footer="宗门研科技 <名称> <灵石>"):
            yield r

    @filter.command("宗门研科技", "宗主/副宗主捐资升级宗门科技：/宗门研科技 <名称> <灵石>")
    @require_whitelist
    async def handle_sect_tech_research(self, event: AstrMessageEvent, arg: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        parts = (arg or "").rsplit(maxsplit=1)
        if len(parts) < 2 or not parts[1].isdigit():
            yield event.plain_result("用法：/宗门研科技 <科技名称> <灵石>（/宗门科技 查看费用）")
            return
        ok, msg = await self.sect_tech_mgr.research(player, parts[0].strip(), int(parts[1]))
        yield event.plain_result(msg)

    @filter.command("斗法台", "斗法台锦标赛：/斗法台 查看，/斗法台 报名")
    @require_whitelist
    async def handle_tournament(self, event: AstrMessageEvent, arg: str = ""):
        if (arg or "").strip() == "报名":
            player = await self.db.get_player_by_id(event.get_sender_id())
            if not player:
                yield event.plain_result("❌ 道友尚未踏入仙途。")
                return
            ok, msg = await self.tournament_mgr.signup(player)
            yield event.plain_result(msg)
            return
        msg = await self.tournament_mgr.handle_board(event)
        async for r in self._board_card(event, msg, "pvp", "⚔️ 斗法台锦标赛", "天道压制 · 单败淘汰",
                                        footer="斗法台 报名 · 周五自动开赛"):
            yield r

    @filter.command("拍卖行", "查看世界Boss战利品拍卖")
    @require_whitelist
    async def handle_loot_auction_board(self, event: AstrMessageEvent):
        msg = await self.loot_auction_mgr.handle_board(event)
        async for r in self._board_card(event, msg, "market", "🔨 天机阁拍卖行", "世界Boss战利品竞拍",
                                        footer="竞拍 <金额> · 出价即托管"):
            yield r

    @filter.command("竞拍", "竞拍战利品：/竞拍 <金额>（全额托管，价高者得）")
    @require_whitelist
    async def handle_loot_auction_bid(self, event: AstrMessageEvent, arg: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        if not (arg or "").strip().isdigit():
            yield event.plain_result("用法：/竞拍 <金额>（1000-1000000，加价至少 1000）")
            return
        ok, msg = await self.loot_auction_mgr.bid(player, int(arg.strip()))
        yield event.plain_result(msg)

    # ===== v3.22.0 第四批新玩法指令 =====

    @filter.command("登仙台", "查看全服世界工程进度")
    @require_whitelist
    async def handle_ascension_board(self, event: AstrMessageEvent):
        msg = await self.ascension_mgr.handle_board(event)
        async for r in self._board_card(event, msg, "world", "⛩️ 登仙台", "全服世界工程",
                                        footer="助登仙台 <灵石> · 进阶全服有奖"):
            yield r

    @filter.command("助登仙台", "为登仙台捐献灵石：/助登仙台 <金额>")
    @require_whitelist
    async def handle_ascension_donate(self, event: AstrMessageEvent, arg: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        if not (arg or "").strip().isdigit():
            yield event.plain_result("用法：/助登仙台 <灵石>（100-1000000，进阶时全服人人有奖）")
            return
        ok, msg = await self.ascension_mgr.donate(player, int(arg.strip()))
        yield event.plain_result(msg)

    @filter.command("修仙群史", "查看昨日修仙界大事记")
    @require_whitelist
    async def handle_chronicle(self, event: AstrMessageEvent):
        msg = await self.chronicle_mgr.handle_history(event)
        async for r in self._board_card(event, msg, "info", "📜 修仙群史", "昨日大事记"):
            yield r

    @filter.command("称号熔炼", "3个同品阶称号熔炼高一品阶：/称号熔炼 <名1> <名2> <名3>")
    @require_whitelist
    async def handle_title_forge(self, event: AstrMessageEvent, arg: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        parts = (arg or "").split()
        if not parts:
            msg = await self.title_forge_mgr.handle_board(player, event)
            yield event.plain_result(msg)
            return
        if len(parts) != 3:
            yield event.plain_result("用法：/称号熔炼 <名1> <名2> <名3>（3 个已拥有的同品阶称号）")
            return
        ok, msg = await self.title_forge_mgr.forge(player, parts[0], parts[1], parts[2])
        yield event.plain_result(msg)

    @filter.command("求签", "每日求签，运势影响当日收益")
    @require_whitelist
    async def handle_fortune_draw(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        ok, msg = await self.fortune_mgr.draw(player)
        yield event.plain_result(msg)

    @filter.command("今日运势", "查看今日所求之签")
    @require_whitelist
    async def handle_fortune_today(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        msg = await self.fortune_mgr.handle_today(player, event)
        yield event.plain_result(msg)

