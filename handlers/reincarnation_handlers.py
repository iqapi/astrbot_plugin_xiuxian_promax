# handlers/reincarnation_handlers.py
from astrbot.api.event import AstrMessageEvent
from ..data import DataBase
from ..managers.reincarnation_manager import ReincarnationManager
from ..models import Player
from .utils import player_required

class ReincarnationHandlers:
    """飞升转生与仙缘商店处理器"""
    
    def __init__(self, db: DataBase, reinc_mgr: ReincarnationManager):
        self.db = db
        self.reinc_mgr = reinc_mgr

    @player_required
    async def handle_reincarnate(self, player: Player, event: AstrMessageEvent, heirloom_name: str = ""):
        """处理飞升指令（支持指定传家宝）"""
        success, msg = await self.reinc_mgr.try_reincarnate(player, heirloom_name)
        yield event.plain_result(msg)

    @player_required
    async def handle_unseal(self, player: Player, event: AstrMessageEvent):
        """处理解封传家宝指令"""
        success, msg = await self.reinc_mgr.unseal_heirloom(player)
        yield event.plain_result(msg)

    @player_required
    async def handle_fate_shop(self, player: Player, event: AstrMessageEvent):
        """查看仙缘商店"""
        msg = (
            f"🌟 仙缘商店（当前仙缘点：{player.fate_points}）\n"
            f"━━━━━━━━━━━━━━━\n"
            f"1. 兑换【修炼加速】：消耗 100 仙缘点，永久修炼速度+10%\n"
            f"2. 兑换【初始灵石】：消耗 50 仙缘点，获得 10,000 灵石\n"
            f"3. 兑换【大道馈赠】：消耗 500 仙缘点，永久增加大量全属性\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 使用 `/仙缘兑换 <编号>` 进行购买"
        )
        yield event.plain_result(msg)

    @player_required
    async def handle_fate_exchange(self, player: Player, event: AstrMessageEvent, item_id: str = "0"):
        """处理仙缘商店购买指令"""
        try:
            idx = int(item_id)
        except ValueError:
            yield event.plain_result("❌ 请输入正确的商品编号！例如：/仙缘兑换 1")
            return
            
        if idx <= 0:
            yield event.plain_result("❌ 请输入正确的商品编号！例如：/仙缘兑换 1")
            return
            
        success, msg = await self.reinc_mgr.buy_fate_shop_item(player, idx)
        yield event.plain_result(msg)