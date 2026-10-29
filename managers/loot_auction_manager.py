# managers/loot_auction_manager.py
"""世界Boss战利品拍卖行（v3.20.0 新玩法）

世界Boss被击杀后掉落稀有战利品，全服公开竞价拍卖：
- 同一时间全服只有一场拍卖（loot_auction_state，存 system_config，JSON）
- 出价即托管：出价全额扣款，被超越者自动退还旧出价（同一玩家可多次加价，净额托管）
- 拍期 30 分钟，到期价高者得；无人出价则流拍（托管款已在各自出价时扣除/退还，流拍无款可退）
- 设计目的：Boss 尾刀 2 万灵石、满级押镖 30 分钟 2 万灵石的水位下，
  拍卖品价值 5-20 万灵石当量，作为大额灵石回收口抑制通货膨胀
"""

import json
import time
from typing import Tuple

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["LootAuctionManager"]


class LootAuctionManager:
    """世界Boss战利品拍卖行"""

    STATE_KEY = "loot_auction_state"   # system_config 键
    DURATION_SECONDS = 30 * 60         # 拍期 30 分钟
    MIN_BID = 1_000                    # 最低出价
    MAX_BID = 1_000_000                # 最高出价
    MIN_INCREMENT = 1_000              # 加价最小幅度

    # 拍品表：tier -> 拍品（价值 5-20 万灵石当量，大额灵石回收口）
    LOOT_TABLE = {
        1: {"name": "魔核残片", "exp": 30_000, "gold": 20_000, "desc": "深渊魔龙残躯中剥落的魔核碎片，蕴含精纯魔气"},
        2: {"name": "魔王遗宝", "exp": 80_000, "gold": 50_000, "desc": "远古天魔陨落时遗落的至宝，灵光冲天，价值连城"},
    }

    def __init__(self, db: DataBase):
        self.db = db

    # ---------- 状态读写（system_config JSON） ----------

    async def _load_state(self) -> dict:
        raw = await self.db.ext.get_system_config(self.STATE_KEY)
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    async def _save_state(self, state: dict):
        await self.db.ext.set_system_config(self.STATE_KEY, json.dumps(state, ensure_ascii=False))

    @staticmethod
    def _top_bid(state: dict) -> Tuple[str, int]:
        """返回当前最高价出价者 (uid, amount)，无人出价返回 ("", 0)"""
        bids = state.get("bids") or {}
        top_uid, top_amt = "", 0
        for uid, info in bids.items():
            amt = int(info.get("amount", 0))
            if amt > top_amt:
                top_uid, top_amt = uid, amt
        return top_uid, top_amt

    @staticmethod
    def _ranking(bids: dict) -> list:
        """按出价从高到低排序 [(uid, amount, name), ...]"""
        items = [(uid, int(info.get("amount", 0)), info.get("name", "?")) for uid, info in (bids or {}).items()]
        items.sort(key=lambda x: -x[1])
        return items

    # ---------- 核心玩法 ----------

    async def open_auction(self, boss_name: str, tier: int) -> Tuple[bool, str]:
        """世界Boss击杀时主控调用：开启全服拍卖（拍期 30 分钟）
        v3.23.0：旧拍卖若尚有未退托管款（结算延迟窗口），先退款再开新拍"""
        state = await self._load_state()
        now = int(time.time())
        if state.get("open") and now < state.get("end_ts", 0):
            return False, "❌ 当前已有一场拍卖正在进行，无法重复开拍。"
        # 旧拍卖未结算（定时 300 秒延迟窗口内）：先退全部托管款再覆盖
        old_bids = state.get("bids") or {}
        if old_bids:
            await self._refund_bids(old_bids)
            logger.info("[loot_auction] 旧拍卖未结算托管款已退还")

        loot = dict(self.LOOT_TABLE.get(tier, self.LOOT_TABLE[1]))
        state = {
            "open": True,
            "boss_name": boss_name,
            "tier": tier,
            "loot": loot,
            "end_ts": now + self.DURATION_SECONDS,
            "bids": {},   # uid -> {amount, name}
        }
        await self._save_state(state)

        est_value = loot["exp"] + loot["gold"] * 5  # 价值量级参考（修为按灵石 1:5 估算）
        msg = (
            f"🔨【天机阁拍卖会】开拍！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👹 来源：世界Boss【{boss_name}】战利品\n"
            f"✨ 拍品：【{loot['name']}】\n"
            f"📜 「{loot['desc']}」\n"
            f"💎 落槌可得：修为 {loot['exp']:,} + 灵石 {loot['gold']:,}（价值约 {est_value // 10000} 万灵石当量）\n"
            f"⏳ 拍期：30 分钟（发送 /拍卖行 查看战况）\n"
            f"💰 出价即托管灵石，被超越自动退还！\n"
            f"💡 /竞拍 <金额> 参与竞价（{self.MIN_BID:,} - {self.MAX_BID:,}，价高者得）"
        )
        return True, msg

    async def bid(self, player: Player, amount: int) -> Tuple[bool, str]:
        """/竞拍 <金额>：出价即托管，被超越自动退款，可多次加价
        v3.23.0：余额取数据库实时值（不信命令快照）"""
        state = await self._load_state()
        now = int(time.time())
        if not state.get("open"):
            return False, "❌ 当前没有进行中的拍卖。\n💡 世界Boss被击杀后战利品将开拍，留意全服播报。"
        if now >= state.get("end_ts", 0):
            return False, "⏰ 本场拍卖已截止，等待结算中…\n💡 发送 /拍卖行 查看结果。"

        amount = int(amount)
        if not (self.MIN_BID <= amount <= self.MAX_BID):
            return False, f"❌ 出价需在 {self.MIN_BID:,} - {self.MAX_BID:,} 灵石之间。"

        top_uid, top_amt = self._top_bid(state)
        if top_uid and amount < top_amt + self.MIN_INCREMENT:
            return False, (
                f"❌ 出价太低！当前最高价 {top_amt:,} 灵石"
                f"（需至少 {top_amt + self.MIN_INCREMENT:,}）。\n💡 /竞拍 <金额> 加价至少 {self.MIN_INCREMENT:,} 灵石"
            )

        bids = state.setdefault("bids", {})
        my_bid = bids.get(player.user_id)
        refund = 0
        fresh = await self.db.get_player_by_id(player.user_id)
        live_gold = fresh.gold if fresh else 0
        if my_bid:
            # 同一玩家加价：先退还其旧出价托管款，再扣新价（净额托管）
            refund = int(my_bid.get("amount", 0))
            if refund > 0:
                await self.db.add_player_gold(player.user_id, refund)
                live_gold += refund
        if live_gold < amount:
            # 退款已到账，直接回滚状态判断（不再写回旧出价）
            if refund > 0:
                await self.db.add_player_gold(player.user_id, -refund)
            return False, f"❌ 灵石不足！出价 {amount:,} 需全额托管（当前持有 {live_gold:,}）。"

        await self.db.add_player_gold(player.user_id, -amount)
        bids[player.user_id] = {"amount": amount, "name": player.user_name or player.user_id[:8]}
        await self._save_state(state)

        remain = max(0, state["end_ts"] - now)
        rank = 1 + sum(1 for u, i in bids.items() if u != player.user_id and i.get("amount", 0) > amount)
        lines = [
            f"🔨 竞价成功！【{player.user_name or player.user_id[:8]}】出价 {amount:,} 灵石"
            f"（已托管{'，退回旧出价 ' + format(refund, ',') + ' 灵石' if refund else ''}）",
            f"📊 当前排名：第 {rank} 名 · 剩余 {remain // 60} 分 {remain % 60} 秒",
        ]
        if top_uid and top_uid != player.user_id:
            lines.append(f"⚠️ 你已超越前最高价（{top_amt:,}），若被再次超越将自动退款，可继续加价。")
        return True, "\n".join(lines)

    async def _refund_bids(self, bids: dict):
        """退还全部托管出价款（旧拍卖兜底/结算共用）"""
        for uid, info in (bids or {}).items():
            try:
                amt = int(info.get("amount", 0)) if isinstance(info, dict) else int(info or 0)
                if amt > 0:
                    await self.db.add_player_gold(uid, amt)
            except Exception as e:
                logger.warning(f"[loot_auction] 退款失败 uid={uid}: {e}")

    async def settle(self) -> str:
        """定时调用（主控 300 秒循环）：到期则落槌结算，返回结算广播文本（空=未到期/未开拍）
        v3.23.0：先退款/发奖，全部完成后才清 bids——中途异常不丢托管款"""
        state = await self._load_state()
        if not state.get("open"):
            return ""
        now = int(time.time())
        if now < state.get("end_ts", 0):
            return ""

        loot = state.get("loot", {})
        loot_name = loot.get("name", "神秘宝物")
        bids = state.get("bids") or {}
        ranking = self._ranking(bids)

        # CAS 抢占结算权（把 open 置 False），失败=另一路径已在结算
        settled = await self.db.ext.syscfg_cas(
            "loot_auction_state",
            json.dumps({**state, "open": False}, ensure_ascii=False),
            json.dumps(state, ensure_ascii=False),
        )
        if not settled:
            return ""
        # 保留 bids 数据直到退款完成（此时 open 已为 False，不会再有新出价）
        state["open"] = False
        await self._save_state(state)

        if not ranking:
            # 流拍：无人出价即无托管款，无退款处理；清 bids 收尾
            state["bids"] = {}
            await self._save_state(state)
            return (
                f"🔇【天机阁拍卖会】流拍！\n"
                f"━━━━━━━━━━━━━━━\n"
                f"拍品【{loot_name}】30 分钟内无人出价，已被天机阁收回封存。"
            )

        win_uid, win_amt, win_name = ranking[0]
        # 发拍品奖励：修为 + 灵石（拍品奖励与托管款无关，单独发放）
        winner = await self.db.get_player_by_id(win_uid)
        if winner:
            await self.db.add_player_exp(win_uid, int(loot.get("exp", 0)))
            await self.db.add_player_gold(win_uid, int(loot.get("gold", 0)))
        else:
            logger.warning(f"拍卖落槌：赢家 {win_uid} 不存在，拍品奖励未发放（托管款 {win_amt:,} 已收取）")

        lines = [
            f"🔔【天机阁拍卖会】落槌！\n━━━━━━━━━━━━━━━",
            f"✨ 拍品：【{loot_name}】以 {win_amt:,} 灵石成交！",
            f"👑 得主：【{win_name}】",
            f"💎 获得拍品奖励：修为 {loot.get('exp', 0):,} + 灵石 {loot.get('gold', 0):,}（已发放）",
            f"💸 托管竞价款 {win_amt:,} 灵石已被天机阁收讫（不退还）",
        ]
        if len(ranking) > 1:
            lines.append("━━━━━━━━━━━━━━━")
            lines.append("📉 以下是落选者的托管退款记录：")
            for uid, amt, name in ranking[1:]:
                await self.db.add_player_gold(uid, amt)
                lines.append(f"   ↩️ {name}：退回 {amt:,} 灵石（已到账）")
        # 全部退款完成后才清 bids
        state["bids"] = {}
        await self._save_state(state)
        return "\n".join(lines)

    async def handle_board(self, event) -> str:
        """/拍卖行 查看当前拍品、最高价、剩余时间"""
        state = await self._load_state()
        now = int(time.time())
        if not state.get("open") or now >= state.get("end_ts", 0):
            return (
                "🔨【天机阁拍卖行】\n━━━━━━━━━━━━━━━\n"
                "📭 当前没有进行中的拍卖。\n"
                "💡 世界Boss被击杀后，其战利品将在此开拍，留意全服播报！"
            )

        loot = state.get("loot", {})
        bids = state.get("bids") or {}
        ranking = self._ranking(bids)
        remain = max(0, state["end_ts"] - now)
        top_uid, top_amt = self._top_bid(state)

        lines = [
            "🔨【天机阁拍卖行】",
            "━━━━━━━━━━━━━━━",
            f"✨ 拍品：【{loot.get('name', '?')}】（来自世界Boss【{state.get('boss_name', '?')}】）",
            f"📜 「{loot.get('desc', '')}」",
            f"💎 落槌可得：修为 {loot.get('exp', 0):,} + 灵石 {loot.get('gold', 0):,}",
            f"⏳ 剩余时间：{remain // 60} 分 {remain % 60} 秒",
        ]
        if ranking:
            lines.append(f"💰 当前最高价：{top_amt:,} 灵石（{ranking[0][2]}）")
            lines.append("━━━━━━━━━━━━━━━")
            lines.append("📋 出价榜：")
            for i, (uid, amt, name) in enumerate(ranking[:5], start=1):
                medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}."
                lines.append(f"   {medal} {name} - {amt:,} 灵石")
        else:
            lines.append("💰 暂无人出价，抢先出手！")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append(f"💡 /竞拍 <金额> 参与竞价（{self.MIN_BID:,} - {self.MAX_BID:,}，出价即托管）")
        return "\n".join(lines)
