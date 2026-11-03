# managers/dao_bet_manager.py
"""天道盘（v3.36.0 新玩法）：全服每日赌盘

- 每日开盘：押「赤」或「玄」，100 - 50000 灵石，每人每色可多押（累计）
- 当日 24 点（惰性触发：次日首次交互时结算）天道掷骰定胜负
- 赢方按注额比例瓜分总奖池的 90%（10% 天道抽成，灵石回收口）
- 池体 JSON 读-改-写全部走 syscfg_cas（同 tribbet 模式），扣款条件原子、CAS 失败退款
"""

import json
import random
import time
from typing import Tuple, Optional

from astrbot.api import logger

from ..data.data_manager import DataBase

__all__ = ["DaoBetManager"]


class DaoBetManager:
    """天道盘：孤注一掷，还是落袋为安？"""

    STATE_PREFIX = "daopan_"
    MIN_BET, MAX_BET = 100, 50000
    HOUSE_CUT = 0.10
    SIDES = {"红": "red", "赤": "red", "玄": "blue", "蓝": "blue"}

    def __init__(self, db: DataBase):
        self.db = db

    @staticmethod
    def _today() -> str:
        return time.strftime("%Y-%m-%d")

    def _key(self, date: str) -> str:
        return f"{self.STATE_PREFIX}{date}"

    async def _load_raw(self, date: str) -> str:
        return await self.db.ext.get_system_config(self._key(date)) or ""

    @staticmethod
    def _parse(raw: str) -> Optional[dict]:
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None

    async def _get_or_create(self) -> Tuple[str, dict]:
        date = self._today()
        raw = await self._load_raw(date)
        state = self._parse(raw)
        if not state:
            state = {"date": date, "red_pool": 0, "blue_pool": 0, "bets": {}, "settled": False}
        return date, state

    async def _settle_if_due(self) -> str:
        """次日惰性结算：天道掷骰定胜负，赢方按比例瓜分 90% 奖池"""
        yesterday = self._today()
        # 检查"昨天"及之前未结算的盘（含停服跨日）
        try:
            async with self.db.conn.execute(
                "SELECT key, value FROM system_config WHERE key LIKE ? AND value NOT LIKE '%\"settled\": true%'",
                (self.STATE_PREFIX + "%",)
            ) as cursor:
                rows = await cursor.fetchall()
        except Exception as e:
            logger.error(f"[天道盘] 扫描未结算盘失败: {e}")
            return ""

        results = []
        for key, raw in rows:
            state = self._parse(raw)
            if not state or state.get("settled") or state.get("date") >= yesterday:
                continue
            # CAS 抢占结算权
            claimed = await self.db.ext.syscfg_cas(
                key, json.dumps({**state, "settled": True}, ensure_ascii=False), raw
            )
            if not claimed:
                continue
            total = int(state.get("red_pool", 0)) + int(state.get("blue_pool", 0))
            if total <= 0:
                continue
            win_side = "red" if random.random() < 0.5 else "blue"
            win_pool = int(state.get(f"{win_side}_pool", 0))
            prize_pool = int(total * (1 - self.HOUSE_CUT))
            date_str = state.get("date", "?")

            results.append(f"🎲【天道盘 · {date_str}】开盤！天意落在【{'赤龙' if win_side == 'red' else '玄虎'}】！")
            if win_pool <= 0:
                results.append("💸 押中者：无。总奖池被天道收讫（全押错了……）")
                continue
            # 比例瓜分
            for uid, bet in (state.get("bets") or {}).items():
                if bet.get("side") != win_side:
                    continue
                amount = int(bet.get("amount", 0))
                if amount <= 0:
                    continue
                payout = int(prize_pool * amount / win_pool)
                if payout > 0:
                    await self.db.add_player_gold(uid, payout)
                    results.append(f"🎉 {bet.get('name', uid[:8])} 押中 {amount:,} → 赢得 {payout:,} 灵石")
            results.append(f"💰 总奖池 {total:,} 灵石（天道抽成 {int(self.HOUSE_CUT * 100)}%）")
        return "\n".join(results)

    async def bet(self, player, side_str: str, amount_str: str) -> Tuple[bool, str]:
        settle_msg = await self._settle_if_due()
        uid = player.user_id
        side = self.SIDES.get((side_str or "").strip())
        if not side:
            return False, (settle_msg + "\n❌ 用法：/天道盘 押 <红|玄> <灵石>（100 - 50000）").strip()
        try:
            amount = int(str(amount_str).strip().translate(str.maketrans("０１２３４５６７８９", "0123456789")))
        except (TypeError, ValueError):
            return False, "❌ 押注金额须为整数。"
        if not (self.MIN_BET <= amount <= self.MAX_BET):
            return False, f"❌ 单注需在 {self.MIN_BET:,} - {self.MAX_BET:,} 灵石之间。"

        date, state = await self._get_or_create()
        bets = dict(state.get("bets") or {})
        my = bets.get(uid) or {}
        if my.get("side") and my.get("side") != side:
            return False, "❌ 本日你已押过另一边，天意不可三心二意（明日再来）。"

        # 条件原子扣款
        cursor = await self.db.conn.execute(
            "UPDATE players SET gold = gold - ? WHERE user_id = ? AND gold >= ?",
            (amount, uid, amount)
        )
        await self.db.conn.commit()
        if cursor.rowcount == 0:
            return False, f"❌ 灵石不足！你当前持有 {player.gold:,}。"

        # CAS 更新池体（失败退款重试）
        for _ in range(3):
            raw = await self._load_raw(date)
            cur = self._parse(raw)
            if not cur:
                cur = {"date": date, "red_pool": 0, "blue_pool": 0, "bets": {}, "settled": False}
            if cur.get("settled"):
                await self.db.add_player_gold(uid, amount)
                return False, "⏰ 本日天道盘已结算，押注资金已退还。明日请早！"
            new_bets = dict(cur.get("bets") or {})
            mine = new_bets.get(uid) or {}
            new_bets[uid] = {
                "side": side,
                "amount": int(mine.get("amount", 0)) + amount,
                "name": player.user_name or uid[:8],
            }
            new_state = {**cur,
                         f"{side}_pool": int(cur.get(f"{side}_pool", 0)) + amount,
                         "bets": new_bets}
            if await self.db.ext.syscfg_cas(self._key(date), json.dumps(new_state, ensure_ascii=False), raw or None):
                state = new_state
                break
            await self.db.add_player_gold(uid, amount)  # 回滚
        else:
            return False, "⚠️ 天道盘正忙，请稍后再试。"

        red, blue = int(state.get("red_pool", 0)), int(state.get("blue_pool", 0))
        my_amt = int((state.get("bets") or {}).get(uid, {}).get("amount", 0))
        odds = f"{red / max(1, blue):.2f}" if side == "red" else f"{blue / max(1, red):.2f}"
        lines = [
            "🎲【天道盘】押注成功！",
            "━━━━━━━━━━━━━━━",
            f"你押了【{'赤龙' if side == 'red' else '玄虎'}】{amount:,} 灵石（本日累计 {my_amt:,}）",
            f"📊 当前盘口：赤龙 {red:,} vs 玄虎 {blue:,}",
            f"⚖️ 若天意降临你方，预计赔率约 ×{odds}",
        ]
        if settle_msg:
            lines.insert(0, settle_msg)
            lines.insert(1, "━━━━━━━━━━━━━━━")
        return True, "\n".join(lines)

    async def get_board(self, player) -> str:
        settle_msg = await self._settle_if_due()
        date, state = await self._get_or_create()
        red, blue = int(state.get("red_pool", 0)), int(state.get("blue_pool", 0))
        uid = player.user_id
        my = (state.get("bets") or {}).get(uid) or {}
        lines = [
            "🎲【天道盘 · 今日】",
            "━━━━━━━━━━━━━━━",
            f"🐉 赤龙盘：{red:,} 灵石",
            f"🐅 玄虎盘：{blue:,} 灵石",
            "⚖️ 赔率随两盘比例浮动，赢方瓜分总奖池 90%",
        ]
        if my:
            lines.append(f"🪙 我的押注：{'赤龙' if my.get('side') == 'red' else '玄虎'} × {int(my.get('amount', 0)):,}")
        else:
            lines.append("🪙 我还未押注")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("💡 /天道盘 押 <红|玄> <灵石>（100-50000，当日 24 点开奖）")
        lines.append("💡 押中按注额比例瓜分奖池，押错血本无归——孤注一掷，还是落袋为安？")
        if settle_msg:
            lines.insert(0, settle_msg)
        return "\n".join(lines)
