# handlers/pet_handlers.py
from astrbot.api.event import AstrMessageEvent
from ..data import DataBase
from ..managers.pet_manager import PetManager
from ..models import Player
from .utils import player_required

class PetHandlers:
    def __init__(self, db: DataBase, pet_mgr: PetManager):
        self.db = db
        self.pet_mgr = pet_mgr

    @player_required
    async def handle_my_pet(self, player: Player, event: AstrMessageEvent):
        pet = await self.pet_mgr.get_pet(player.user_id)
        if not pet:
            yield event.plain_result("🐾 你当前没有携带任何灵兽。\n💡 发送 `/孵化灵兽 <名字>` 契约一只。")
            return
            
        pet_info = self.pet_mgr.PET_TYPES.get(pet["pet_type"], {"desc": "未知"})
        msg = (
            f"🐾 你的灵兽：{pet['pet_name']}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"等级：Lv.{pet['level']} ({pet['exp']}/{pet['level']*500})\n"
            f"特性：{pet_info['desc']}\n"
            f"协战概率：{int((0.2 + pet['level'] * 0.01) * 100)}%\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 发送 `/喂养灵兽` 提升等级"
        )
        yield event.plain_result(msg)

        # ===== 图片卡片（磨砂玻璃质感，失败自动降级为纯文本）=====
        try:
            from ..utils.image_generator import render_card, card_enabled
            if not card_enabled("CARD_PET"):
                return
            card_path = render_card(
                "pet",
                f"灵兽 · {pet['pet_name']}",
                pet_info.get("desc", ""),
                sections=[
                    {"name": "状态", "rows": [
                        ("等级", f"Lv.{pet['level']}"),
                        ("经验", f"{pet['exp']}/{pet['level'] * 500}"),
                        ("协战概率", f"{int((0.2 + pet['level'] * 0.01) * 100)}%"),
                        ("类型", pet.get("pet_type", "未知")),
                    ]},
                ],
                footer="/喂养灵兽 提升等级 · 协战等级越高触发越频繁",
            )
            if card_path:
                yield event.image_result(card_path)
        except Exception:
            pass

    @player_required
    async def handle_adopt(self, player: Player, event: AstrMessageEvent, pet_name: str = ""):
        if not pet_name:
            available = "\n".join([f"· {k}：{v['desc']}" for k, v in self.pet_mgr.PET_TYPES.items()])
            yield event.plain_result(f"请指定你要契约的灵兽名称（消耗10万灵石）：\n{available}")
            return
            
        success, msg = await self.pet_mgr.adopt_pet(player, pet_name)
        yield event.plain_result(msg)

    @player_required
    async def handle_feed(self, player: Player, event: AstrMessageEvent):
        # 灵兽窝：洞天家具，喂养消耗-20%
        cost_mult = 1.0
        try:
            async with self.db.conn.execute(
                "SELECT furniture FROM blessed_lands WHERE user_id = ?", (player.user_id,)
            ) as cursor:
                row = await cursor.fetchone()
            if row and row[0] and "灵兽窝" in row[0]:
                cost_mult = 0.8
        except Exception:
            pass
        success, msg = await self.pet_mgr.feed_pet(player, cost_mult)
        if success and cost_mult < 1.0:
            msg += "\n🛋️ 灵兽窝生效：喂养消耗-20%"
        yield event.plain_result(msg)

    @player_required
    async def handle_release(self, player: Player, event: AstrMessageEvent):
        success, msg = await self.pet_mgr.release_pet(player)
        yield event.plain_result(msg)

    @player_required
    async def handle_devour(self, player: Player, event: AstrMessageEvent):
        success, msg = await self.pet_mgr.devour_pet(player)
        yield event.plain_result(msg)