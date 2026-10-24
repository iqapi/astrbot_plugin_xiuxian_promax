# handlers/auction_handlers.py
from astrbot.api.event import AstrMessageEvent
from ..data import DataBase
from ..managers.auction_manager import AuctionManager
from ..models import Player
from .utils import player_required

class AuctionHandlers:
    """玩家交易坊市处理器"""
    
    def __init__(self, db: DataBase, auction_mgr: AuctionManager):
        self.db = db
        self.auction_mgr = auction_mgr

    async def handle_list(self, event: AstrMessageEvent):
        """查看坊市"""
        msg = await self.auction_mgr.get_market_list()
        yield event.plain_result(msg)

        # ===== 坊市卡片（磨砂玻璃，开关关闭或生成失败则不发）=====
        try:
            from ..utils.image_generator import render_card, card_enabled
            if card_enabled("CARD_MARKET"):
                items = await self.auction_mgr.get_market_items(10)
                if items:
                    lines = []
                    for it in items:
                        name = it['item_name'] if len(it['item_name']) <= 14 else it['item_name'][:14] + "…"
                        lines.append(f"[{it['id']}] {name} x{it['count']} · {it['price'] * it['count']:,}灵石")
                    card_path = render_card(
                        "shop",
                        "🏪 玩家交易坊市",
                        f"在售 {len(items)} 件 · 交易税 5%",
                        sections=[{"name": "最新上架", "lines": lines}],
                        footer="/坊市购买 <编号> · /坊市上架 <物> <数> <价>",
                    )
                    if card_path:
                        yield event.image_result(card_path)
        except Exception:
            pass

    @player_required
    async def handle_list_item(self, player: Player, event: AstrMessageEvent, args: str = ""):
        """上架物品到坊市"""
        if not args or not args.strip():
            yield event.plain_result(
                "🏪 上架物品说明\n"
                "━━━━━━━━━━━━━━━\n"
                "用法：/坊市上架 <物品名> <数量> <单价>\n"
                "示例：/坊市上架 天阶·诛仙剑 1 50000"
            )
            return

        # 考虑到物品名称可能带空格，从右侧切分最后两个参数
        parts = args.strip().rsplit(" ", 2)
        if len(parts) < 3:
            yield event.plain_result("❌ 参数不足！请确保包含：物品名、数量、单价。\n示例：/坊市上架 极品灵草 5 1000")
            return

        item_name = parts[0].strip()
        try:
            count = int(parts[1])
            price = int(parts[2])
        except ValueError:
            yield event.plain_result("❌ 数量和单价必须是纯数字！")
            return

        if count <= 0 or price <= 0:
            yield event.plain_result("❌ 数量和单价必须大于 0。")
            return

        success, msg = await self.auction_mgr.list_item(player, item_name, count, price)
        yield event.plain_result(msg)

    @player_required
    async def handle_buy(self, player: Player, event: AstrMessageEvent, auction_id: str = "0"):
        """从坊市购买物品"""
        try:
            aid = int(auction_id)
        except ValueError:
            yield event.plain_result("❌ 请输入正确的商品编号！例如：/坊市购买 1")
            return
            
        if aid <= 0:
            yield event.plain_result("❌ 商品编号必须大于 0。")
            return
        
        success, msg = await self.auction_mgr.buy_item(player, aid)
        yield event.plain_result(msg)

    @player_required
    async def handle_cancel(self, player: Player, event: AstrMessageEvent, auction_id: str = "0"):
        """下架坊市物品"""
        try:
            aid = int(auction_id)
        except ValueError:
            yield event.plain_result("❌ 请输入正确的商品编号！例如：/坊市下架 1")
            return
            
        if aid <= 0:
            yield event.plain_result("❌ 商品编号必须大于 0。")
            return
            
        success, msg = await self.auction_mgr.cancel_item(player, aid)
        yield event.plain_result(msg)