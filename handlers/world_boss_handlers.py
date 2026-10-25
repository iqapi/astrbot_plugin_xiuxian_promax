# handlers/world_boss_handlers.py
import time
from astrbot.api.event import AstrMessageEvent
from ..data import DataBase
from ..managers.world_boss_manager import WorldBossManager
from ..models import Player
from .utils import player_required

class WorldBossHandlers:
    def __init__(self, db: DataBase, wb_mgr: WorldBossManager):
        self.db = db
        self.wb_mgr = wb_mgr

    @player_required
    async def handle_challenge(self, player: Player, event: AstrMessageEvent):
        """挑战世界Boss"""
        success, msg = await self.wb_mgr.challenge_boss(player)
        yield event.plain_result(msg)

    async def handle_query(self, event: AstrMessageEvent):
        """查询世界Boss信息"""
        async with self.db.conn.execute("SELECT * FROM world_boss WHERE status = 1") as cursor:
            row = await cursor.fetchone()
            if not row:
                yield event.plain_result("👹 当前没有存活的世界Boss，请等待天道降临。")
                return
            boss = dict(row)
            
        hp_percent = (boss["current_hp"] / boss["max_hp"]) * 100
        
        msg = [
            f"👹 世界Boss：{boss['boss_name']}",
            f"━━━━━━━━━━━━━━━",
            f"❤️ 血量：{boss['current_hp']:,} / {boss['max_hp']:,} ({hp_percent:.1f}%)",
            f"⚔️ 攻击：{boss['atk']:,}",
            f"⏳ 剩余存活时间：{(boss['expire_time'] - int(time.time())) // 3600} 小时",
            f"━━━━━━━━━━━━━━━",
            f"💡 发送 /挑战世界Boss 参与讨伐（单次伤害上限3%）"
        ]

        # ===== 图片卡片：成功只发图，失败/关闭降级为纯文本 =====
        sent = False
        try:
            from ..utils.image_generator import render_card_async, card_enabled
            if card_enabled("CARD_BOSS"):
                remaining = max(0, boss['expire_time'] - int(time.time()))
                card_path = await render_card_async(
                    "boss",
                    f"世界Boss · {boss['boss_name']}",
                    "天道警示 · 全服共讨",
                    sections=[
                        {"name": "Boss状态", "rows": [
                            ("血量", f"{boss['current_hp']:,} / {boss['max_hp']:,}"),
                            ("血量百分比", f"{hp_percent:.1f}%"),
                            ("攻击力", f"{boss['atk']:,}"),
                            ("剩余时间", f"{remaining // 3600}小时{(remaining % 3600) // 60}分"),
                        ]},
                        {"name": "讨伐规则", "lines": [
                            "· 每日可挑战 3 次，每次间隔 5 分钟",
                            "· 单次伤害保底 0.5%，上限 3%",
                            "· 尾刀斩杀者获唯一称号【灭世魔神】",
                        ]},
                    ],
                    footer="/挑战世界Boss 参与讨伐",
                )
                if card_path:
                    yield event.image_result(card_path)
                    sent = True
        except Exception:
            pass
        if not sent:
            yield event.plain_result("\n".join(msg))