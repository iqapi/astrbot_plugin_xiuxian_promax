# managers/auction_manager.py
import time
from typing import Tuple
from astrbot.api import logger
from ..data import DataBase
from ..models import Player

class AuctionManager:
    """玩家交易坊市管理器"""
    
    TAX_RATE = 0.05 # 系统收取 5% 的交易税，用于回收灵石

    def __init__(self, db: DataBase, storage_ring_mgr):
        self.db = db
        self.storage_ring_mgr = storage_ring_mgr

    async def list_item(self, player: Player, item_name: str, count: int, price: int) -> Tuple[bool, str]:
        """上架物品"""
        if count <= 0:
            return False, "❌ 上架数量必须大于 0。"
        if price <= 0:
            return False, "❌ 单价必须大于 0。"
            
        # 检查物品是否真实存在于配置中（防止上架幽灵物品）
        if not self.storage_ring_mgr.has_item(player, item_name, count):
            return False, f"❌ 你的储物戒中没有足够的【{item_name}】。"
   
         # ===== 修复点：检查物品是否绑定 =====
        items_data = player.get_storage_ring_items()
        item_info = items_data.get(item_name)
        if isinstance(item_info, dict) and item_info.get("bound"):
            return False, f"❌【{item_name}】是角色绑定物品，无法上架坊市交易！"

        # 从储物戒扣除物品
        success, msg = await self.storage_ring_mgr.retrieve_item(player, item_name, count)
        if not success:
            return False, f"❌ 扣除物品失败：{msg}"

        # 写入坊市表
        now = int(time.time())
        await self.db.conn.execute(
            "INSERT INTO auction_items (seller_id, item_name, count, price, create_time) VALUES (?, ?, ?, ?, ?)",
            (player.user_id, item_name, count, price, now)
        )
        await self.db.conn.commit()
        
        total = price * count
        return True, f"✅ 上架成功！\n物品：【{item_name}】x{count}\n单价：{price:,} 灵石\n总价：{total:,} 灵石"

    async def get_market_list(self) -> str:
        """查看坊市列表"""
        # 按最新上架的排在前面
        async with self.db.conn.execute("SELECT * FROM auction_items ORDER BY id DESC LIMIT 30") as cursor:
            items = [dict(r) for r in await cursor.fetchall()]

        if not items:
            return "🕊️ 坊市目前空空如也，快去上架第一件商品吧！"

        msg = ["🏪 玩家交易坊市 (最近30条)", "━━━━━━━━━━━━━━━"]
        for item in items:
            # 查询卖家名字
            seller = await self.db.get_player_by_id(item["seller_id"])
            seller_name = seller.user_name if seller and seller.user_name else item["seller_id"][:6]
            if seller and seller.title:
                seller_name = f"【{seller.title}】{seller_name}"

            total_price = item["price"] * item["count"]

            # 截断过长的物品名，防止群聊刷屏
            display_name = item['item_name'] if len(item['item_name']) <= 12 else item['item_name'][:12] + "..."

            msg.append(f"[{item['id']}] {display_name} x{item['count']}")
            msg.append(f"  └ 总价: {total_price:,} 灵石 | 卖家: {seller_name}")

        msg.append("━━━━━━━━━━━━━━━")
        msg.append(f"💡 购买：/坊市购买 <编号> (系统收取 {self.TAX_RATE:.0%} 交易税)")
        msg.append("💡 上架：/坊市上架 <物品名> <数量> <单价>")
        msg.append("💡 下架：/坊市下架 <编号>")
        return "\n".join(msg)

    async def get_market_items(self, limit: int = 10) -> list:
        """获取最近上架的坊市条目（供图片卡片使用）"""
        async with self.db.conn.execute(
            "SELECT * FROM auction_items ORDER BY id DESC LIMIT ?", (limit,)
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]

    async def buy_item(self, buyer: Player, auction_id: int) -> Tuple[bool, str]:
        """购买物品（带事务与防并发处理）"""
        await self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            # 1. 检查商品是否存在
            async with self.db.conn.execute("SELECT * FROM auction_items WHERE id = ?", (auction_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    await self.db.conn.rollback()
                    return False, "❌ 该商品不存在或已被其他玩家买走。"
                item_data = dict(row)

            if item_data["seller_id"] == buyer.user_id:
                await self.db.conn.rollback()
                return False, "❌ 不能购买自己上架的物品，如需撤回请使用下架功能。"

            total_price = item_data["price"] * item_data["count"]
            if buyer.gold < total_price:
                await self.db.conn.rollback()
                return False, f"❌ 灵石不足！\n需要 {total_price:,} 灵石，你只有 {buyer.gold:,} 灵石。"

            # 2. 尝试存入买家储物戒
            success, store_msg = await self.storage_ring_mgr.store_item(
                buyer, item_data["item_name"], item_data["count"], 
                external_transaction=True, silent=True
            )
            if not success:
                await self.db.conn.rollback()
                return False, f"❌ 购买失败：你的储物戒空间不足，请先清理背包。"

            # 3. 扣除买家灵石
            buyer.gold -= total_price
            await self.db.update_player(buyer, commit=False)

            # 4. 给卖家打款（扣除 5% 交易税）
            seller = await self.db.get_player_by_id(item_data["seller_id"])
            if seller:
                seller_income = int(total_price * (1 - self.TAX_RATE))
                seller.gold += seller_income
                await self.db.update_player(seller, commit=False)

            # 5. 从坊市删除该记录
            await self.db.conn.execute("DELETE FROM auction_items WHERE id = ?", (auction_id,))
            await self.db.conn.commit()
            
            return True, f"✅ 购买成功！\n花费：{total_price:,} 灵石\n获得：【{item_data['item_name']}】x{item_data['count']}（已存入储物戒）"

        except Exception as e:
            await self.db.conn.rollback()
            logger.error(f"坊市购买异常: {e}")
            return False, "❌ 交易异常，已取消购买，请联系管理员。"

    async def cancel_item(self, player: Player, auction_id: int) -> Tuple[bool, str]:
        """下架物品"""
        await self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            async with self.db.conn.execute("SELECT * FROM auction_items WHERE id = ?", (auction_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    await self.db.conn.rollback()
                    return False, "❌ 该商品不存在或已被买走。"
                item_data = dict(row)

            if item_data["seller_id"] != player.user_id:
                await self.db.conn.rollback()
                return False, "❌ 只能下架自己上架的物品。"

            # 退回储物戒
            success, msg = await self.storage_ring_mgr.store_item(
                player, item_data["item_name"], item_data["count"], 
                external_transaction=True, silent=True
            )
            if not success:
                await self.db.conn.rollback()
                return False, f"❌ 储物戒已满，无法下架退回物品。请清理背包后再试。"

            await self.db.conn.execute("DELETE FROM auction_items WHERE id = ?", (auction_id,))
            await self.db.conn.commit()
            
            return True, f"✅ 下架成功！\n【{item_data['item_name']}】x{item_data['count']} 已退回到你的储物戒。"
        except Exception as e:
            await self.db.conn.rollback()
            logger.error(f"坊市下架异常: {e}")
            return False, "❌ 下架异常，请稍后再试。"