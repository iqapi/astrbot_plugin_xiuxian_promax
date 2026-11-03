# managers/pill_synth_manager.py
"""丹药合成（v3.39.0 新玩法）：三丹归一，点石成金

- 把 3 颗低阶丹药合成 1 颗高阶丹药（6 段进阶链，全部使用配置中真实存在的丹药）
- 每次合成消耗 1000 灵石炉费（灵石回收口）
- 丹药库存为玩家字段（JSON），单用户路径按项目既有模式定向落库
"""

from typing import Tuple

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["PillSynthManager"]


class PillSynthManager:
    """丹药合成：三丹归一，炉火见真章"""

    SYNTH_FEE = 1000

    # 产物 -> (原料, 原料数)；原料/产物均为 exp_pills.json 真实丹药
    CHAINS = {
        "聚灵丹": ("炼气丹", 3),
        "凝气丹": ("聚灵丹", 3),
        "培元丹": ("凝气丹", 3),
        "增元丹": ("培元丹", 3),
        "玄灵丹": ("增元丹", 3),
        "碧灵丹": ("玄灵丹", 3),
    }

    def __init__(self, db: DataBase, pill_manager=None):
        self.db = db
        self.pill_manager = pill_manager

    async def get_panel(self, player: Player) -> str:
        inventory = player.get_pills_inventory()
        lines = [
            "⚗️【丹药合成】三丹归一",
            "━━━━━━━━━━━━━━━",
            f"💰 炉费：{self.SYNTH_FEE:,} 灵石 / 次",
            "━━━━━━━━━━━━━━━",
        ]
        for product, (material, need) in self.CHAINS.items():
            have = int(inventory.get(material, 0))
            lines.append(f"  {material}×{need} → {product}×1（你有 {material} ×{have}）")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("💡 /合成丹药 <产物名> （如 /合成丹药 聚灵丹）")
        lines.append("💡 /丹药背包 查看丹药库存")
        return "\n".join(lines)

    async def synth(self, player: Player, product: str) -> Tuple[bool, str]:
        """合成：扣 3 颗原料 + 炉费 → 得 1 颗产物"""
        product = (product or "").strip()
        if product not in self.CHAINS:
            return False, "❌ 未知合成配方。发 /丹药合成 查看全部配方。"

        material, need = self.CHAINS[product]
        inventory = player.get_pills_inventory()
        have = int(inventory.get(material, 0))
        if have < need:
            return False, (
                f"❌ 原料不足！合成【{product}】需要 {material}×{need}（你只有 {have}）。\n"
                f"💡 /丹药合成 查看全部配方"
            )

        # 条件原子扣炉费
        cursor = await self.db.conn.execute(
            "UPDATE players SET gold = gold - ? WHERE user_id = ? AND gold >= ?",
            (self.SYNTH_FEE, player.user_id, self.SYNTH_FEE)
        )
        await self.db.conn.commit()
        if cursor.rowcount == 0:
            return False, f"❌ 灵石不足！合成需炉费 {self.SYNTH_FEE:,} 灵石。"

        # 扣原料 + 加产物（丹药背包定向落库）
        inventory[material] = have - need
        if inventory[material] <= 0:
            del inventory[material]
        inventory[product] = int(inventory.get(product, 0)) + 1
        player.set_pills_inventory(inventory)
        try:
            await self.db.update_player_fields(
                player.user_id, pills_inventory=player.pills_inventory
            )
        except Exception as e:
            # 回滚炉费
            logger.error(f"[丹药合成] 落库失败，退还炉费: {e}")
            await self.db.add_player_gold(player.user_id, self.SYNTH_FEE)
            return False, "❌ 合成落库异常，炉费已退还。"

        return True, (
            f"⚗️ 合成成功！{material}×{need} → 【{product}】×1\n"
            f"💰 炉费 -{self.SYNTH_FEE:,} 灵石\n"
            f"💊 /丹药背包 查看，/服用丹药 {product} 服用"
        )
