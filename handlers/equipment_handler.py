# handlers/equipment_handler.py

from astrbot.api.event import AstrMessageEvent
from ..data import DataBase
from ..core import EquipmentManager, PillManager, StorageRingManager
from ..config_manager import ConfigManager
from ..models import Player
from .utils import player_required

CMD_SHOW_EQUIPMENT = "我的装备"
CMD_EQUIP_ITEM = "装备"
CMD_UNEQUIP_ITEM = "卸下"

__all__ = ["EquipmentHandler"]

class EquipmentHandler:
    """装备系统处理器"""

    def __init__(self, db: DataBase, config_manager: ConfigManager):
        self.db = db
        self.config_manager = config_manager
        self.storage_ring_manager = StorageRingManager(db, config_manager)
        self.equipment_manager = EquipmentManager(db, config_manager, self.storage_ring_manager)
        self.pill_manager = PillManager(db, config_manager)

    @player_required
    async def handle_show_equipment(self, player: Player, event: AstrMessageEvent):
        """显示玩家当前装备"""
        display_name = event.get_sender_name()

        # 获取所有已装备物品
        equipped_items = self.equipment_manager.get_equipped_items(
            player,
            self.config_manager.items_data,
            self.config_manager.weapons_data
        )

        await self.pill_manager.update_temporary_effects(player)
        pill_multipliers = self.pill_manager.calculate_pill_attribute_effects(player)

        # 构建装备显示
        equipment_lines = [
            f"=== {display_name} 的装备 ===\n",
            f"【武器】{player.weapon if player.weapon else '未装备'}\n",
            f"【防具】{player.armor if player.armor else '未装备'}\n",
            f"【主修心法】{player.main_technique if player.main_technique else '未装备'}\n",
        ]

        # 功法列表
        techniques_list = player.get_techniques_list()
        equipment_lines.append(f"【功法】({len(techniques_list)}/3)\n")
        if techniques_list:
            for i, tech in enumerate(techniques_list, 1):
                equipment_lines.append(f"  {i}. {tech}\n")
        else:
            equipment_lines.append("  未装备\n")

        # 总属性加成
        if equipped_items:
            equipment_lines.append("\n--- 装备属性加成 ---\n")
            total_attrs = player.get_total_attributes(equipped_items, pill_multipliers)

            # 计算加成值（总属性 - 基础属性）
            magic_damage_bonus = total_attrs["magic_damage"] - player.magic_damage
            physical_damage_bonus = total_attrs["physical_damage"] - player.physical_damage
            magic_defense_bonus = total_attrs["magic_defense"] - player.magic_defense
            physical_defense_bonus = total_attrs["physical_defense"] - player.physical_defense
            mental_power_bonus = total_attrs["mental_power"] - player.mental_power
            max_spiritual_qi_bonus = total_attrs["max_spiritual_qi"] - player.max_spiritual_qi
            exp_multiplier = total_attrs["exp_multiplier"]

            if magic_damage_bonus > 0:
                equipment_lines.append(f"⚔️ 法伤 +{magic_damage_bonus}\n")
            if physical_damage_bonus > 0:
                equipment_lines.append(f"🗡️ 物伤 +{physical_damage_bonus}\n")
            if magic_defense_bonus > 0:
                equipment_lines.append(f"🛡️ 法防 +{magic_defense_bonus}\n")
            if physical_defense_bonus > 0:
                equipment_lines.append(f"🪨 物防 +{physical_defense_bonus}\n")
            if mental_power_bonus > 0:
                equipment_lines.append(f"🧠 精神力 +{mental_power_bonus}\n")
            if max_spiritual_qi_bonus > 0:
                equipment_lines.append(f"✨ 灵气容量 +{max_spiritual_qi_bonus}\n")
            if exp_multiplier > 0:
                equipment_lines.append(f"📈 修为倍率 +{exp_multiplier:.1%}\n")

        equipment_lines.append("=" * 28)

        yield event.plain_result("".join(equipment_lines))

        # ===== 装备卡片（磨砂玻璃，开关关闭或失败自动跳过）=====
        try:
            from ..utils.image_generator import render_card, card_enabled
            if card_enabled("CARD_EQUIP"):
                element_of = lambda n: (self.config_manager.get_item_element(n) if n else "")
                equip_rows = [
                    ("武器", player.weapon or "未装备"),
                    ("防具", player.armor or "未装备"),
                    ("主修心法", player.main_technique or "未装备"),
                ]
                if element_of(player.main_technique) or element_of(player.weapon):
                    equip_rows.append(("五行属性",
                        element_of(player.main_technique) or element_of(player.weapon)))
                tech_lines = [f"{i}. {t}" for i, t in enumerate(techniques_list, 1)] or ["未装备"]
                card_path = render_card(
                    "combat",
                    f"{display_name} 的装备",
                    f"功法 {len(techniques_list)}/3",
                    sections=[
                        {"name": "装备栏", "rows": equip_rows},
                        {"name": "功法", "lines": tech_lines},
                        {"name": "加成总览", "lines": [
                            f"物伤 +{physical_damage_bonus} · 法伤 +{magic_damage_bonus}",
                            f"物防 +{physical_defense_bonus} · 法防 +{magic_defense_bonus}",
                            f"精神力 +{mental_power_bonus} · 修为倍率 +{exp_multiplier:.1%}",
                        ]},
                    ],
                    footer="装备 <物品名> · 卸下 <武器/防具/心法/功法名>",
                )
                if card_path:
                    yield event.image_result(card_path)
        except Exception:
            pass

    @player_required
    async def handle_equip_item(self, player: Player, event: AstrMessageEvent, item_name: str):
        """装备物品"""
        if not item_name or item_name.strip() == "":
            yield event.plain_result(f"请指定要装备的物品名称\n用法：{CMD_EQUIP_ITEM} 物品名称")
            return

        item_name = item_name.strip()

        # 检查物品是否存在于配置中（先查items再查weapons）
        item_config = self.config_manager.items_data.get(item_name)
        if not item_config:
            item_config = self.config_manager.weapons_data.get(item_name)

        if not item_config:
            yield event.plain_result(f"未找到物品：{item_name}")
            return

        # 检查物品类型是否可装备
        item_type = item_config.get("type", "")
        equippable_types = ["weapon", "armor", "main_technique", "technique"]
        
        # 兼容旧格式
        if item_type == "法器":
            subtype = item_config.get("subtype", "")
            if subtype == "武器":
                item_type = "weapon"
            elif subtype == "防具":
                item_type = "armor"
        elif item_type == "功法":
            item_type = "technique"
        
        if item_type not in equippable_types:
            yield event.plain_result(f"【{item_name}】不是可装备的物品类型")
            return

        # 检查储物戒中是否有该物品
        if not self.storage_ring_manager.has_item(player, item_name, 1):
            yield event.plain_result(
                f"❌ 储物戒中没有【{item_name}】\n"
                f"请先通过购买或获得该装备"
            )
            return

        # 从储物戒取出物品
        success, retrieve_msg = await self.storage_ring_manager.retrieve_item(player, item_name, 1)
        if not success:
            yield event.plain_result(f"❌ 无法从储物戒取出装备：{retrieve_msg}")
            return

        # 创建Item对象
        from ..models import Item
        item = Item(
            item_id=item_config.get("id", item_name),
            name=item_name,
            item_type=item_type,
            description=item_config.get("description", ""),
            rank=item_config.get("rank", ""),
            required_level_index=item_config.get("required_level_index", 0),
            weapon_category=item_config.get("weapon_category", ""),
            magic_damage=item_config.get("magic_damage", 0),
            physical_damage=item_config.get("physical_damage", 0),
            magic_defense=item_config.get("magic_defense", 0),
            physical_defense=item_config.get("physical_defense", 0),
            mental_power=item_config.get("mental_power", 0),
            exp_multiplier=item_config.get("exp_multiplier", 0.0),
            spiritual_qi=item_config.get("spiritual_qi", 0)
        )

        # 装备物品
        success, message = await self.equipment_manager.equip_item(player, item)

        if success:
            # 显示属性加成
            attr_display = item.get_attribute_display()
            result_msg = (
                f"✅ {message}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"属性加成：{attr_display}"
            )
            yield event.plain_result(result_msg)
        else:
            # 装备失败，将物品放回储物戒
            await self.storage_ring_manager.store_item(player, item_name, 1, silent=True)
            yield event.plain_result(f"❌ {message}")

    @player_required
    async def handle_unequip_item(self, player: Player, event: AstrMessageEvent, slot_or_name: str):
        """卸下装备"""
        if not slot_or_name or slot_or_name.strip() == "":
            yield event.plain_result(
                f"请指定要卸下的装备\n"
                f"用法：{CMD_UNEQUIP_ITEM} 武器/防具/心法/功法名称"
            )
            return

        slot_or_name = slot_or_name.strip()

        # 获取卸下前的装备名称，用于存入储物戒
        unequipped_item_name = None
        if slot_or_name in ["武器", "weapon"]:
            unequipped_item_name = player.weapon
        elif slot_or_name in ["防具", "armor"]:
            unequipped_item_name = player.armor
        elif slot_or_name in ["主修心法", "心法", "main_technique"]:
            unequipped_item_name = player.main_technique
        else:
            # 检查功法列表
            techniques_list = player.get_techniques_list()
            if slot_or_name in techniques_list:
                unequipped_item_name = slot_or_name

        # 卸下装备
        success, message = await self.equipment_manager.unequip_item(player, slot_or_name)

        if success:
            # 卸下成功后，将装备存入储物戒
            storage_msg = ""
            if unequipped_item_name:
                store_success, store_msg = await self.storage_ring_manager.store_item(
                    player, unequipped_item_name, 1, silent=True
                )
                if store_success:
                    storage_msg = f"\n已存入储物戒"
                else:
                    storage_msg = f"\n⚠️ 存入储物戒失败：{store_msg}"
            
            yield event.plain_result(f"✅ {message}{storage_msg}")
        else:
            yield event.plain_result(f"❌ {message}")
