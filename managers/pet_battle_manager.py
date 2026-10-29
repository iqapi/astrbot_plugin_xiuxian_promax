# managers/pet_battle_manager.py
"""灵宠出战：让契约灵兽协修主人（v3.20.0 新玩法）

每名玩家仅一只灵兽（pet_manager 体系），出战=开启协修开关：
- 出战加成：历练/闭关修为 +（宠物等级 × 0.2%，上限 5%）
- 主控接入点：player_handler 出关结算 / adventure_manager 历练结算
"""

from typing import Tuple

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["PetBattleManager"]


class PetBattleManager:
    """灵宠出战管理器"""

    RATE_PER_LEVEL = 0.002   # 每级 +0.2%
    MAX_BONUS = 0.05         # 上限 5%

    def __init__(self, db: DataBase):
        self.db = db

    def _key(self, user_id: str) -> str:
        return f"battle_pet_{user_id}"

    async def set_battle_pet(self, player: Player) -> Tuple[bool, str]:
        """/灵兽出战：让契约灵兽进入出战位协修"""
        async with self.db.conn.execute(
            "SELECT pet_name, level FROM player_pets WHERE user_id = ?",
            (player.user_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return False, "❌ 你还没有契约灵兽。/孵化灵兽 <名> 先契约一只吧。"
        pet_name, level = row[0], int(row[1] or 1)

        raw = await self.db.ext.get_system_config(self._key(player.user_id))
        if raw == str(pet_name):
            return False, f"❌ 【{pet_name}】已经在出战协修中了。"

        await self.db.ext.set_system_config(self._key(player.user_id), str(pet_name))
        bonus = min(self.MAX_BONUS, level * self.RATE_PER_LEVEL)
        return True, (
            f"🐾【{pet_name}】进入出战位，灵光缠绕周身！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"协修加成：修炼/历练收益 +{bonus:.1%}（当前 Lv.{level}）\n"
            f"💡 灵兽升级会自动提升协修加成（上限 +5%）\n"
            f"使用 /灵兽休战 可收回"
        )

    async def unset(self, player: Player) -> Tuple[bool, str]:
        """/灵兽休战"""
        raw = await self.db.ext.get_system_config(self._key(player.user_id))
        if not raw:
            return False, "❌ 你当前没有出战的灵兽。"
        await self.db.ext.set_system_config(self._key(player.user_id), "")
        return True, f"🕊️ 出战灵兽【{raw}】已收回休战，协修加成暂停。"

    async def get_exp_bonus(self, user_id: str) -> float:
        """出战协修加成（供闭关/历练结算调用；异常安全返回 0）"""
        try:
            pet_name = await self.db.ext.get_system_config(self._key(user_id))
            if not pet_name:
                return 0.0
            async with self.db.conn.execute(
                "SELECT level FROM player_pets WHERE user_id = ? AND pet_name = ?",
                (user_id, pet_name)
            ) as cursor:
                row = await cursor.fetchone()
            if not row:
                return 0.0
            return min(self.MAX_BONUS, int(row[0] or 1) * self.RATE_PER_LEVEL)
        except Exception as e:
            logger.warning(f"灵宠协修加成查询异常: {e}")
            return 0.0

    async def handle_info(self, player: Player, event):
        """/出战信息"""
        raw = await self.db.ext.get_system_config(self._key(player.user_id))
        if not raw:
            yield event.plain_result(
                "🐾【灵宠出战】\n━━━━━━━━━━━━━━━\n当前没有出战灵兽。\n"
                "💡 /灵兽出战 让契约灵兽协修（修炼/历练收益 +0.2%/级，上限 5%）"
            )
            return
        async with self.db.conn.execute(
            "SELECT level FROM player_pets WHERE user_id = ? AND pet_name = ?",
            (player.user_id, raw)
        ) as cursor:
            row = await cursor.fetchone()
        level = int(row[0] or 1) if row else 1
        bonus = min(self.MAX_BONUS, level * self.RATE_PER_LEVEL)
        yield event.plain_result(
            f"🐾【出战信息】\n━━━━━━━━━━━━━━━\n"
            f"出战灵兽：{raw}（Lv.{level}）\n"
            f"协修加成：+{bonus:.1%}（修炼/历练收益）\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 /灵兽休战 可收回；灵兽升级自动提升加成"
        )
