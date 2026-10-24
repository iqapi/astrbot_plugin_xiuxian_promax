# handlers/blessed_land_handlers.py
"""洞天福地处理器"""
from astrbot.api.event import AstrMessageEvent
from ..data import DataBase
from ..managers.blessed_land_manager import BlessedLandManager
from ..models import Player
from .utils import player_required

__all__ = ["BlessedLandHandlers"]


class BlessedLandHandlers:
    """洞天福地处理器"""
    
    def __init__(self, db: DataBase, blessed_land_mgr: BlessedLandManager):
        self.db = db
        self.mgr = blessed_land_mgr
    
    @player_required
    async def handle_blessed_land_info(self, player: Player, event: AstrMessageEvent):
        """查看洞天信息"""
        info = await self.mgr.get_blessed_land_info(player.user_id)
        yield event.plain_result(info)
    
    @player_required
    async def handle_purchase(self, player: Player, event: AstrMessageEvent, land_type: int = 0):
        """购买洞天"""
        if land_type <= 0:
            yield event.plain_result(
                "🏔️ 购买洞天\n"
                "━━━━━━━━━━━━━━━\n"
                "初始只能购买小洞天，通过进阶系统提升洞天品质。\n\n"
                "1. 小洞天 - 10,000灵石 (+5%修炼)\n"
                "━━━━━━━━━━━━━━━\n"
                "💡 使用 /购买洞天 1"
            )
            return
        
        success, msg = await self.mgr.purchase_blessed_land(player, land_type)
        yield event.plain_result(msg)
    
    @player_required
    async def handle_upgrade(self, player: Player, event: AstrMessageEvent):
        """升级洞天"""
        success, msg = await self.mgr.upgrade_blessed_land(player)
        yield event.plain_result(msg)
    
    @player_required
    async def handle_collect(self, player: Player, event: AstrMessageEvent):
        """收取洞天产出"""
        success, msg = await self.mgr.collect_income(player)
        yield event.plain_result(msg)
    
    @player_required
    async def handle_advance(self, player: Player, event: AstrMessageEvent, target_type: int = 0):
        """进阶洞天"""
        if target_type <= 0:
            yield event.plain_result(
                "🏔️ 进阶洞天\n"
                "━━━━━━━━━━━━━━━\n"
                "请指定目标洞天类型：\n"
                "2. 中洞天 (从小洞天进阶)\n"
                "3. 大洞天 (从中洞天进阶)\n"
                "4. 福地 (从大洞天进阶)\n"
                "5. 洞天福地 (从福地进阶)\n"
                "━━━━━━━━━━━━━━━\n"
                "💡 使用 /进阶洞天 <编号>"
            )
            return
        
        success, msg = await self.mgr.advance_blessed_land(player, target_type)
        yield event.plain_result(msg)
