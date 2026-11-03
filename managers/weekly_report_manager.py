# managers/weekly_report_manager.py
"""修炼周报（v3.49.0 新玩法）：本周修炼数据总览

- 自动追踪本周关键行为（原子计数，周键 %G-W%V 自动轮转）
- /修炼周报 面板：除妖/突破/科举/切磋/决斗/红包/宗门捐献等本周累计
- 零写路径侵入：各系统已有原子原语处按需调 record()（异常安全不影响主流程）
"""

import time

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["WeeklyReportManager"]


class WeeklyReportManager:
    """修炼周报：你这一周，天道都看着"""

    def __init__(self, db: DataBase):
        self.db = db

    @staticmethod
    def _week() -> str:
        return time.strftime('%G-W%V')

    @classmethod
    def _key(cls, uid: str, action: str) -> str:
        return f"weekly_{action}_{uid}_{cls._week()}"

    async def record(self, uid: str, action: str, count: int = 1):
        """记录一次行为（各系统一行调用，异常安全）"""
        try:
            await self.db.ext.syscfg_adjust_number(self._key(uid, action), count)
        except Exception as e:
            logger.warning(f"[周报] 记录 {action} 失败: {e}")

    async def get_count(self, uid: str, action: str) -> int:
        return await self.db.ext.syscfg_get_number(self._key(uid, action))

    # 各系统调用的便捷方法
    async def record_hunt(self, uid): await self.record(uid, "hunt")
    async def record_hunt_win(self, uid): await self.record(uid, "hunt_win")
    async def record_breakthrough(self, uid): await self.record(uid, "breakthrough")
    async def record_quiz(self, uid): await self.record(uid, "quiz")
    async def record_duel_win(self, uid): await self.record(uid, "duel_win")
    async def record_duel_lose(self, uid): await self.record(uid, "duel_lose")
    async def record_spar(self, uid): await self.record(uid, "spar")
    async def record_donate(self, uid, amount: int): await self.record(uid, "donate", amount)
    async def record_tower(self, uid): await self.record(uid, "tower")
    async def record_expedition(self, uid): await self.record(uid, "expedition")
    async def record_escort(self, uid): await self.record(uid, "escort")
    async def record_rob(self, uid): await self.record(uid, "rob")
    async def record_gift(self, uid): await self.record(uid, "gift")

    async def get_report(self, player: Player) -> str:
        uid = player.user_id
        g = self.db.ext.syscfg_get_number

        hunt = await g(self._key(uid, "hunt"))
        hunt_win = await g(self._key(uid, "hunt_win"))
        bt = await g(self._key(uid, "breakthrough"))
        quiz = await g(self._key(uid, "quiz"))
        duel_w = await g(self._key(uid, "duel_win"))
        duel_l = await g(self._key(uid, "duel_lose"))
        spar = await g(self._key(uid, "spar"))
        donate = await g(self._key(uid, "donate"))
        tower = await g(self._key(uid, "tower"))
        expedition = await g(self._key(uid, "expedition"))
        escort = await g(self._key(uid, "escort"))
        rob = await g(self._key(uid, "rob"))
        gift = await g(self._key(uid, "gift"))

        total_actions = hunt + bt + quiz + duel_w + duel_l + spar + tower + expedition + escort + rob + gift
        hunt_rate = f"{hunt_win * 100 // hunt}%" if hunt else "—"
        duel_total = duel_w + duel_l
        duel_rate = f"{duel_w * 100 // duel_total}%" if duel_total else "—"

        lines = [
            "📋【修炼周报】",
            f"📅 {self._week()}",
            "━━━━━━━━━━━━━━━",
            "【⚔️ 战斗】",
            f"  · 除妖 {hunt} 次（胜率 {hunt_rate}）",
            f"  · 决斗 {duel_total} 场（胜率 {duel_rate}）· 切磋 {spar} 次",
            f"  · 镇妖塔 {tower} 次",
            "【📚 修炼】",
            f"  · 突破 {bt} 次 · 科举 {quiz} 场",
            "【🚶 行走】",
            f"  · 灵兽探险 {expedition} 次 · 押镖 {escort} 次 · 劫镖 {rob} 次",
            "【💰 社交】",
            f"  · 宗门捐献 {donate:,} 灵石 · 赠礼 {gift} 次",
            "━━━━━━━━━━━━━━━",
        ]
        if total_actions == 0:
            lines.append("💭 本周尚无动静——天道不养闲人，快去 /闭关 /除妖 /历练 吧！")
        else:
            lines.append(f"📊 本周总活跃：{total_actions} 次行为")
        lines.append("💡 每周一自动重置（%G-W%V 周键）")
        return "\n".join(lines)
