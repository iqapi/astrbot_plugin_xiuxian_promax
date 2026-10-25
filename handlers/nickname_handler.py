# handlers/nickname_handler.py
"""道号系统处理器"""
import re
from astrbot.api.event import AstrMessageEvent
from ..data import DataBase
from ..models import Player
from .utils import player_required

__all__ = ["NicknameHandler"]

class NicknameHandler:
    """道号系统处理器"""
    
    def __init__(self, db: DataBase):
        self.db = db
    
    @player_required
    async def handle_change_nickname(self, player: Player, event: AstrMessageEvent, new_name: str = ""):
        """处理改道号指令"""
        if not new_name or new_name.strip() == "":
            yield event.plain_result(
                "📛 道号系统\n"
                "━━━━━━━━━━━━━━━\n"
                f"当前道号：{player.user_name if player.user_name else '无'}\n"
                "━━━━━━━━━━━━━━━\n"
                "💡 使用方法：/改道号 <新道号>\n"
                "⚠️ 道号长度：2-12个字符"
            )
            return
        
        new_name = new_name.strip()
        
        # 验证道号长度
        if len(new_name) < 2 or len(new_name) > 12:
            yield event.plain_result(
                f"❌ 道号长度必须在2-12个字符之间（当前 {len(new_name)} 字）。\n"
                f"示例：/改道号 云兮"
            )
            return

        # 验证道号内容（禁止特殊字符）
        if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9_]+$', new_name):
            yield event.plain_result(
                "❌ 道号只能包含中文、英文、数字和下划线，不能有空格或特殊符号。\n"
                "示例：/改道号 云兮"
            )
            return

        # 检查道号是否已被使用
        existing = await self.db.get_player_by_name(new_name)
        if existing and existing.user_id != player.user_id:
            yield event.plain_result(
                f"❌ 道号『{new_name}』已被其他修士使用。\n"
                f"💡 换一个试试，或加个前后缀区分（如：{new_name}真君）"
            )
            return
        
        old_name = player.user_name if player.user_name else "无"
        player.user_name = new_name
        await self.db.update_player(player)
        
        yield event.plain_result(
            "✅ 道号修改成功！\n"
            "━━━━━━━━━━━━━━━\n"
            f"原道号：{old_name}\n"
            f"新道号：{new_name}\n"
            "━━━━━━━━━━━━━━━\n"
            "从此踏上新的修仙之路！"
        )
