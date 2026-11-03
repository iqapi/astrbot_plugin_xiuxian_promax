# managers/treasure_map_manager.py
"""秘境藏宝图（v3.45.0 新玩法）：碎片收集 → 合成 → 探寻宝藏

- 除妖胜利 / 秘境完成时概率掉落「藏宝图碎片」（除妖 15% / 秘境 20%）
- 5 张碎片 → 1 张藏宝图（/合成藏宝图）；/探寻宝藏 消耗 1 张开启寻宝
- 宝藏池：高价值物品与大额灵石（远超常规产出，作为长线收集回报）
- 碎片/藏宝图均为 syscfg 数值键（原子增减），无新表
"""

import random
from typing import Tuple

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["TreasureMapManager"]


class TreasureMapManager:
    """秘境藏宝图：集齐残卷，掘开上古秘藏"""

    FRAG_PER_MAP = 5
    FRAG_DROP_HUNT = 0.15
    FRAG_DROP_RIFT = 0.20

    # 探寻宝藏池：(类型, 名称/说明, 数量, 权重)
    TREASURE_POOL = [
        ("gold", "上古灵石窖藏", 15000, 25),
        ("gold", "前人遗落的行囊", 8000, 25),
        ("item", "空间石", 1, 15),
        ("item", "洗练石", 2, 15),
        ("item", "强化石", 3, 10),
        ("item", "引雷符", 2, 8),
        ("jackpot", "仙府秘藏", 50000, 2),
    ]
    _TOTAL_WEIGHT = sum(w for _, _, _, w in TREASURE_POOL)

    def __init__(self, db: DataBase, storage_ring_mgr=None):
        self.db = db
        self.storage_ring_mgr = storage_ring_mgr

    @staticmethod
    def _frag_key(uid: str) -> str:
        return f"mapfrag_{uid}"

    @staticmethod
    def _map_key(uid: str) -> str:
        return f"treasure_maps_{uid}"

    async def get_frags(self, uid: str) -> int:
        return await self.db.ext.syscfg_get_number(self._frag_key(uid))

    async def get_maps(self, uid: str) -> int:
        return await self.db.ext.syscfg_get_number(self._map_key(uid))

    async def drop_fragment(self, uid: str) -> bool:
        """掉落一张碎片（原子累加）"""
        new = await self.db.ext.syscfg_adjust_number(self._frag_key(uid), 1)
        return new > 0

    async def get_panel(self, player: Player) -> str:
        uid = player.user_id
        frags = await self.get_frags(uid)
        maps = await self.get_maps(uid)
        lines = [
            "🗺️【秘境藏宝图】",
            "━━━━━━━━━━━━━━━",
            f"🧩 藏宝图碎片：{frags} / {self.FRAG_PER_MAP}",
            f"🗺️ 完整藏宝图：{maps} 张",
            "━━━━━━━━━━━━━━━",
        ]
        if frags >= self.FRAG_PER_MAP:
            lines.append("✅ 碎片已集齐，可 /合成藏宝图")
        lines.append("💡 除妖胜利 15% / 秘境探索完成 20% 概率获得碎片")
        lines.append("💡 /探寻宝藏 消耗 1 张藏宝图，掘开上古秘藏（含 5 万灵石仙府秘藏大奖）")
        return "\n".join(lines)

    async def synth(self, player: Player) -> Tuple[bool, str]:
        """5 碎片 → 1 藏宝图（syscfg_spend 原子扣碎片防透支）"""
        uid = player.user_id
        if not await self.db.ext.syscfg_spend(self._frag_key(uid), self.FRAG_PER_MAP):
            frags = await self.get_frags(uid)
            return False, f"❌ 碎片不足！合成需要 {self.FRAG_PER_MAP} 张（你只有 {frags}）。"
        await self.db.ext.syscfg_adjust_number(self._map_key(uid), 1)
        maps = await self.get_maps(uid)
        return True, f"🗺️ 合成成功！碎片拼合成一张完整的藏宝图（现有 {maps} 张）。\n💡 /探寻宝藏 开启寻宝！"

    async def explore(self, player: Player) -> Tuple[bool, str]:
        """探寻宝藏：消耗 1 张藏宝图，按权重随机秘藏"""
        uid = player.user_id
        if not await self.db.ext.syscfg_spend(self._map_key(uid), 1):
            maps = await self.get_maps(uid)
            return False, f"❌ 没有藏宝图！先集齐 {self.FRAG_PER_MAP} 张碎片 /合成藏宝图（现有 {maps} 张）。"

        roll = random.randint(1, self._TOTAL_WEIGHT)
        acc = 0
        kind, label, value, _ = self.TREASURE_POOL[-1]
        for entry in self.TREASURE_POOL:
            acc += entry[3]
            if roll <= acc:
                kind, label, value, _ = entry
                break

        lines = [
            "🗺️【探寻宝藏】",
            "━━━━━━━━━━━━━━━",
        ]
        try:
            if kind == "gold":
                await self.db.add_player_gold(uid, value)
                lines.append(f"💰 挖出【{label}】：灵石 +{value:,}！")
            elif kind == "jackpot":
                await self.db.add_player_gold(uid, value)
                lines.append(f"🌟 传闻成真！你掘开了【{label}】：灵石 +{value:,}！！")
                lines.append("📣 天地异象，四方修士投来羡慕的目光……")
            else:
                if self.storage_ring_mgr:
                    ok, msg = await self.storage_ring_mgr.store_item(player, label, value, silent=True)
                    if ok:
                        lines.append(f"🎁 挖出【{label}】x{value}（已存入储物戒）")
                    else:
                        await self.db.add_player_gold(uid, value * 3000)  # 储物戒满 → 折算灵石
                        lines.append(f"📦 挖出【{label}】但储物戒已满，折算 {value * 3000:,} 灵石")
                else:
                    await self.db.add_player_gold(uid, value * 3000)
                    lines.append(f"📦 挖出【{label}】，折算 {value * 3000:,} 灵石")
        except Exception as e:
            logger.error(f"[藏宝图] 结算异常: {e}")
            # 补偿：退还藏宝图
            await self.db.ext.syscfg_adjust_number(self._map_key(uid), 1)
            return False, "❌ 寻宝异常，藏宝图已退还。"
        lines.append("━━━━━━━━━━━━━━━")
        left = await self.get_maps(uid)
        lines.append(f"🗺️ 剩余藏宝图：{left} 张 · 继续收集碎片再接再厉")
        return True, "\n".join(lines)
