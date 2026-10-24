# handlers/forge_handlers.py
from astrbot.api.event import AstrMessageEvent
from ..data import DataBase
from ..managers.forge_manager import ForgeManager
from ..models import Player
from .utils import player_required

class ForgeHandlers:
    def __init__(self, db: DataBase, forge_mgr: ForgeManager):
        self.db = db
        self.forge_mgr = forge_mgr

    @player_required
    async def handle_enhance(self, player: Player, event: AstrMessageEvent):
        success, msg = await self.forge_mgr.enhance_equipment(player)
        yield event.plain_result(msg)

    @player_required
    async def handle_wash(self, player: Player, event: AstrMessageEvent):
        success, msg = await self.forge_mgr.wash_equipment(player)
        yield event.plain_result(msg)