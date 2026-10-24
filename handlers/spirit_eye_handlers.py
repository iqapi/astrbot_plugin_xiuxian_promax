# handlers/spirit_eye_handlers.py
"""天地灵眼处理器"""
from astrbot.api.event import AstrMessageEvent
from ..data import DataBase
from ..managers.spirit_eye_manager import SpiritEyeManager
from ..models import Player
from .utils import player_required

__all__ = ["SpiritEyeHandlers"]


class SpiritEyeHandlers:
    """天地灵眼处理器"""
    
    def __init__(self, db: DataBase, eye_mgr: SpiritEyeManager):
        self.db = db
        self.mgr = eye_mgr
    
    @player_required
    async def handle_spirit_eye_info(self, player: Player, event: AstrMessageEvent):
        """查看灵眼信息"""
        info = await self.mgr.get_spirit_eye_info(player.user_id)
        yield event.plain_result(info)
    
    @player_required
    async def handle_claim(self, player: Player, event: AstrMessageEvent, eye_id: int = 0):
        """抢占灵眼"""
        if eye_id <= 0:
            yield event.plain_result("❌ 请指定灵眼ID，例如：/抢占灵眼 1")
            return
        
        success, msg = await self.mgr.claim_spirit_eye(player, eye_id)
        yield event.plain_result(msg)
    
    @player_required
    async def handle_collect(self, player: Player, event: AstrMessageEvent):
        """收取灵眼收益"""
        success, msg = await self.mgr.collect_spirit_eye(player)
        yield event.plain_result(msg)
    
    @player_required
    async def handle_release(self, player: Player, event: AstrMessageEvent):
        """释放灵眼"""
        success, msg = await self.mgr.release_spirit_eye(player.user_id)
        yield event.plain_result(msg)
