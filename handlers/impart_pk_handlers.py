# handlers/impart_pk_handlers.py
"""传承PK处理器"""
import re
from astrbot.api.event import AstrMessageEvent
from ..data import DataBase
from ..managers.impart_pk_manager import ImpartPkManager
from ..models import Player
from .utils import player_required

__all__ = ["ImpartPkHandlers"]


class ImpartPkHandlers:
    """传承PK处理器"""
    
    def __init__(self, db: DataBase, impart_pk_mgr: ImpartPkManager):
        self.db = db
        self.impart_pk_mgr = impart_pk_mgr
    
    @player_required
    async def handle_impart_challenge(self, player: Player, event: AstrMessageEvent, target_info: str = ""):
        """发起传承挑战"""
        # 解析目标
        target_id = self._extract_user_id(target_info)
        if not target_id:
            yield event.plain_result(
                "⚔️ 传承挑战\n"
                "━━━━━━━━━━━━━━━\n"
                "争夺对方的传承加成！\n"
                "胜利：获得传承ATK加成\n"
                "失败：损失1%修为\n"
                "━━━━━━━━━━━━━━━\n"
                "💡 用法：/传承挑战 @某人"
            )
            return
        
        if target_id == player.user_id:
            yield event.plain_result("❌ 不能挑战自己。")
            return
        
        # 获取目标玩家
        target = await self.db.get_player_by_id(target_id)
        if not target:
            yield event.plain_result("❌ 对方还未踏入修仙之路。")
            return
        
        # 发起挑战
        wins, log, rewards = await self.impart_pk_mgr.challenge_impart(player, target)
        
        if wins:
            result_msg = (
                f"🎉 传承挑战胜利！\n"
                f"━━━━━━━━━━━━━━━\n"
                f"对手：{target.user_name or target_id[:8]}\n"
                f"获得ATK传承：+{rewards.get('impart_atk_gain', 0):.2%}\n"
            )
        else:
            result_msg = (
                f"💀 传承挑战失败...\n"
                f"━━━━━━━━━━━━━━━\n"
                f"对手：{target.user_name or target_id[:8]}\n"
                f"损失修为：-{rewards.get('exp_loss', 0):,}\n"
            )
        
        yield event.plain_result(result_msg)
    
    @player_required
    async def handle_impart_ranking(self, player: Player, event: AstrMessageEvent):
        """传承排行榜"""
        rankings = await self.impart_pk_mgr.get_impart_ranking(10)
        
        if not rankings:
            yield event.plain_result("📊 传承排行榜暂无数据。")
            return
        
        lines = ["🏆 传承排行榜\n━━━━━━━━━━━━━━━"]
        for i, r in enumerate(rankings, 1):
            lines.append(f"{i}. {r['user_name']} - ATK+{r['atk_per']:.1%}")
        lines.append("━━━━━━━━━━━━━━━")
        
        yield event.plain_result("\n".join(lines))
    
    def _extract_user_id(self, msg: str) -> str:
        """从消息中提取用户ID"""
        if not msg:
            return ""
        # 匹配 @xxx 或纯数字
        at_match = re.search(r'\[CQ:at,qq=(\d+)\]', msg)
        if at_match:
            return at_match.group(1)
        # 纯数字
        num_match = re.search(r'(\d{5,12})', msg)
        if num_match:
            return num_match.group(1)
        return ""
