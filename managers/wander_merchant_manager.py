# managers/wander_merchant_manager.py
"""云游商人（v3.29.0 新玩法）：每 2 小时刷新的限时特惠货郎

- 货品与折扣由时间种子确定性生成（每 2 小时一换，全服同步），无需持久化
- 每位玩家每件商品每个刷新期限购 1 份（syscfg_claim_slot 原子限购）
- 丹药入丹药背包、其余入储物戒；扣款条件原子、失败不扣
"""

import random
import time
from typing import Tuple, List, Dict

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["WanderMerchantManager"]


class WanderMerchantManager:
    """云游商人：行脚四方，货卖有缘人"""

    REFRESH_SECONDS = 7200   # 每 2 小时刷新

    # 特供池：(名称, 原价, 类型) —— 名称均存在于项目配置
    POOL = [
        ("引雷符", 3000, "item"),
        ("空间石", 6000, "item"),
        ("护府令", 30000, "item"),
        ("强化石", 2500, "item"),
        ("洗练石", 4000, "item"),
        ("聚灵丹", 8000, "pill"),
        ("凝神丹", 12000, "pill"),
        ("回气散", 2000, "pill"),
        ("灵草", 1500, "item"),
        ("血灵草", 4000, "item"),
    ]
    GREETINGS = [
        "一位斗笠行者踏风而来，褡裢里透出灵光……",
        "驼铃叮当，云游商人卸下了行囊。",
        "「道友留步，老夫今日有稀罕物件。」",
        "风尘仆仆的货郎冲你神秘一笑。",
    ]

    def __init__(self, db: DataBase, storage_ring_mgr=None, pill_manager=None):
        self.db = db
        self.storage_ring_mgr = storage_ring_mgr
        self.pill_manager = pill_manager

    # ===== 内部 =====

    @staticmethod
    def _seed() -> int:
        return int(time.time() // WanderMerchantManager.REFRESH_SECONDS)

    @classmethod
    def _goods(cls) -> List[Dict]:
        """当前期的 3 件货（确定性）：随机挑 3 件并各打随机折扣"""
        rng = random.Random(cls._seed() * 7919)
        picks = rng.sample(cls.POOL, 3)
        goods = []
        for idx, (name, base, gtype) in enumerate(picks):
            discount = rng.choice([0.5, 0.6, 0.7, 0.8])
            goods.append({
                "idx": idx + 1,
                "name": name,
                "type": gtype,
                "base": base,
                "price": max(1, int(base * discount)),
                "discount": discount,
            })
        return goods

    def _limit_key(self, uid: str, idx: int) -> str:
        return f"wmerch_{self._seed()}_{uid}_{idx}"

    # ===== 公开 =====

    async def get_board(self) -> str:
        goods = self._goods()
        remain = self.REFRESH_SECONDS - (int(time.time()) % self.REFRESH_SECONDS)
        lines = [
            f"🧳【云游商人】{random.Random(self._seed()).choice(self.GREETINGS)}",
            "━━━━━━━━━━━━━━━",
        ]
        for g in goods:
            lines.append(
                f"[{g['idx']}] {g['name']} —— {g['price']:,} 灵石"
                f"（原价 {g['base']:,}，{int(g['discount'] * 10)} 折特惠）"
            )
        lines.append("━━━━━━━━━━━━━━━")
        lines.append(f"⏳ {remain // 60} 分钟后离开，货品随缘刷新")
        lines.append("💡 /云游购买 <编号> （每件限购 1 份）")
        return "\n".join(lines)

    async def buy(self, player: Player, idx: int) -> Tuple[bool, str]:
        goods = self._goods()
        target = next((g for g in goods if g["idx"] == idx), None)
        if not target:
            return False, "❌ 无效的编号。发 /云游商人 查看当前货品。"

        # 原子限购（每期每人每件 1 份）
        if not await self.db.ext.syscfg_claim_slot(self._limit_key(player.user_id, idx), 1):
            return False, "❌ 这件特惠你本期限购的 1 份已经买走了。等下一批货吧。"

        # 条件原子扣款
        cursor = await self.db.conn.execute(
            "UPDATE players SET gold = gold - ? WHERE user_id = ? AND gold >= ?",
            (target["price"], player.user_id, target["price"])
        )
        await self.db.conn.commit()
        if cursor.rowcount == 0:
            await self.db.ext.syscfg_adjust_number(self._limit_key(player.user_id, idx), -1)  # 释放限购
            return False, f"❌ 灵石不足！需要 {target['price']:,} 灵石。"

        # 发货：丹药入丹药背包，其余入储物戒
        try:
            if target["type"] == "pill" and self.pill_manager:
                await self.pill_manager.add_pill_to_inventory(player, target["name"], 1)
                where = "（已放入丹药背包）"
            elif self.storage_ring_mgr:
                ok, msg = await self.storage_ring_mgr.store_item(player, target["name"], 1, silent=True)
                if not ok:
                    # 退款
                    await self.db.add_player_gold(player.user_id, target["price"])
                    await self.db.ext.syscfg_adjust_number(self._limit_key(player.user_id, idx), -1)
                    return False, f"❌ 储物戒已满，无法交付（{msg}）。灵石已退还。"
                where = "（已存入储物戒）"
            else:
                await self.db.add_player_gold(player.user_id, target["price"])
                await self.db.ext.syscfg_adjust_number(self._limit_key(player.user_id, idx), -1)
                return False, "❌ 交付系统未加载，灵石已退还。"
        except Exception as e:
            logger.error(f"[云游商人] 交付异常: {e}")
            await self.db.add_player_gold(player.user_id, target["price"])
            await self.db.ext.syscfg_adjust_number(self._limit_key(player.user_id, idx), -1)
            return False, "❌ 交付异常，灵石已退还。"

        return True, (
            f"🧳 成交！【{target['name']}】x1 {where}\n"
            f"💰 支付 {target['price']:,} 灵石（原价 {target['base']:,}，省下 {target['base'] - target['price']:,}）"
        )
