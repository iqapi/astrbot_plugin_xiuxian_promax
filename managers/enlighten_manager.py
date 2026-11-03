# managers/enlighten_manager.py
"""顿悟与道心（v3.28.0 新玩法）：闭关修炼的高光时刻与长期沉淀

- 顿悟：每次出关 15% 概率触发，本次修炼收益 ×1.5 / ×2.0 / ×3.0（权重 60/30/10），
  每日至多 1 次（原子认领防连刷）
- 道心：每次顿悟 +1 点；每 10 点道心提供闭关收益 +1%（上限 +10%）——
  纯累积型被动，不消耗、不折损，修行的见证
- 状态存 system_config 数值键（wudao_* / daoxin_*），无新表
"""

import random
import time
from typing import Tuple

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["EnlightenManager"]


class EnlightenManager:
    """顿悟与道心：灵光乍现的狂喜，水滴石穿的沉淀"""

    CHANCE = 0.15
    DAILY_LIMIT = 1
    DAIXIN_PER_PERCENT = 10   # 每 10 道心 +1%
    PASSIVE_CAP = 0.10        # 被动上限 +10%

    def __init__(self, db: DataBase):
        self.db = db

    @staticmethod
    def _daily_key(uid: str) -> str:
        return f"wudao_{uid}_{time.strftime('%Y%m%d')}"

    @staticmethod
    def _daoxin_key(uid: str) -> str:
        return f"daoxin_{uid}"

    async def get_daoxin(self, uid: str) -> int:
        return await self.db.ext.syscfg_get_number(self._daoxin_key(uid))

    async def get_passive(self, uid: str) -> float:
        """道心被动加成（小数，0.01 = +1%）"""
        n = await self.get_daoxin(uid)
        return min(self.PASSIVE_CAP, (n // self.DAIXIN_PER_PERCENT) * 0.01)

    async def roll_enlighten(self, player: Player) -> Tuple[float, str]:
        """出关结算时调用。返回 (倍率, 提示)；未触发返回 (1.0, "")。
        先掷骰再原子认领每日名额——未掷中不消耗当日机会。"""
        uid = player.user_id
        if random.random() >= self.CHANCE:
            return 1.0, ""
        if not await self.db.ext.syscfg_claim_slot(self._daily_key(uid), self.DAILY_LIMIT):
            return 1.0, ""  # 今日已顿悟过
        mult = random.choices([1.5, 2.0, 3.0], weights=[60, 30, 10])[0]
        await self.db.ext.syscfg_adjust_number(self._daoxin_key(uid), 1)
        logger.info(f"[顿悟] {uid} 顿悟成功 ×{mult}")
        return mult, f"\n⚡ 顿悟！道法圆融，本次修炼收益 ×{mult}（道心 +1）"

    async def get_panel(self, player: Player) -> str:
        uid = player.user_id
        daoxin = await self.get_daoxin(uid)
        passive = await self.get_passive(uid)
        used = await self.db.ext.syscfg_get_number(self._daily_key(uid))
        to_next = self.DAIXIN_PER_PERCENT - (daoxin % self.DAIXIN_PER_PERCENT)
        return (
            "🧘【悟道】\n"
            "━━━━━━━━━━━━━━━\n"
            f"☯ 道心：{daoxin} 点\n"
            f"🌟 道心被动：闭关收益 +{int(passive * 100)}%（每 10 点 +1%，上限 +10%）\n"
            f"📏 距下一层加成：还差 {to_next} 点\n"
            f"⚡ 今日顿悟：{'已有过灵光（明日再试）' if used else '尚未触发'}\n"
            "━━━━━━━━━━━━━━━\n"
            "💡 每次出关有 15% 概率顿悟（收益 ×1.5/×2/×3），每日至多一次\n"
            "💡 顿悟同时累积道心，道心是永不折损的修行见证"
        )
