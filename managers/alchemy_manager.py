# managers/alchemy_manager.py
"""
炼丹系统管理器 - 处理炼丹、配方等逻辑（加入事务防并发）
"""

import json
import random
from typing import Tuple, List, Dict, Optional, TYPE_CHECKING
from ..data.data_manager import DataBase
from ..models import Player
from ..models_extended import UserStatus

if TYPE_CHECKING:
    from ..config_manager import ConfigManager
    from ..core import StorageRingManager


class AlchemyManager:
    """炼丹系统管理器（防并发版）"""
    
    def __init__(self, db: DataBase, config_manager: "ConfigManager" = None, storage_ring_manager: "StorageRingManager" = None):
        self.db = db
        self.config_manager = config_manager
        self.storage_ring_manager = storage_ring_manager
        self.config = config_manager.alchemy_config if config_manager else {}
        
        raw_recipes = {}
        if config_manager and hasattr(config_manager, 'alchemy_recipes') and config_manager.alchemy_recipes:
            raw_recipes = config_manager.alchemy_recipes
        
        self.recipes = {}
        for recipe in raw_recipes.values():
            if isinstance(recipe, dict) and recipe.get("id"):
                recipe_id = int(recipe["id"])
                self.recipes[recipe_id] = self._normalize_recipe(recipe_id, recipe)
    
    def _normalize_recipe(self, recipe_id: int, recipe: Dict) -> Dict:
        """标准化配方字段，兼容不同格式的配置"""
        name = recipe.get("name", f"丹药{recipe_id}")
        
        desc = recipe.get("desc", None)
        if not desc and self.config_manager:
            pill_config = self._get_pill_config_by_name(name)
            if pill_config:
                desc = self._generate_pill_desc(pill_config)
        if not desc:
            desc = "丹药效果"
        
        return {
            "id": recipe.get("id", recipe_id),
            "name": name,
            "level_required": recipe.get("level_required", recipe.get("level", 0)),
            "materials": recipe.get("materials", recipe.get("cost", {})),
            "success_rate": recipe.get("success_rate", recipe.get("success", 50)),
            "desc": desc
        }
    
    def _generate_pill_desc(self, pill_config: Dict) -> str:
        """根据丹药配置生成描述"""
        rank = pill_config.get("rank", "")
        
        if pill_config.get("exp_gain"):
            return f"增加{pill_config['exp_gain']}修为（{rank}修为丹）"
        
        if pill_config.get("breakthrough_bonus"):
            bonus = int(pill_config["breakthrough_bonus"] * 100)
            return f"提升{bonus}%突破成功率（{rank}破境丹）"
        
        if pill_config.get("description"):
            return pill_config["description"]
        
        return f"{rank}丹药"
    
    def _get_pill_config_by_name(self, name: str) -> Optional[Dict]:
        """根据丹药名称获取配置"""
        if not self.config_manager:
            return None
        if hasattr(self.config_manager, 'exp_pills_data') and name in self.config_manager.exp_pills_data:
            return self.config_manager.exp_pills_data[name]
        if hasattr(self.config_manager, 'utility_pills_data') and name in self.config_manager.utility_pills_data:
            return self.config_manager.utility_pills_data[name]
        if hasattr(self.config_manager, 'pills_data') and name in self.config_manager.pills_data:
            return self.config_manager.pills_data[name]
        return None
    
    def _get_bonus_data(self, player: Player) -> dict:
        """安全读取玩家永久加成数据"""
        try:
            data = json.loads(player.permanent_bonus) if player.permanent_bonus else {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get_furnace_level(self, player: Player) -> int:
        """丹炉等级（0-5），每级炼丹成功率 +3%"""
        return int(self._get_bonus_data(player).get("alchemy_furnace", 0))

    def get_furnace_bonus_rate(self, player: Player) -> int:
        """丹炉带来的成功率加成（百分点）"""
        return self.get_furnace_level(player) * 3

    async def upgrade_furnace(self, player: Player) -> Tuple[bool, str]:
        """升级丹炉（消耗灵石，等级越高越贵）"""
        level = self.get_furnace_level(player)
        if level >= 5:
            return False, "❌ 你的丹炉已达最高等级【五品玄天炉】。"

        cost = 20000 * (level + 1)
        if player.gold < cost:
            return False, f"❌ 灵石不足！升级丹炉到 {level + 1} 级需要 {cost:,} 灵石。"

        player.gold -= cost
        data = self._get_bonus_data(player)
        data["alchemy_furnace"] = level + 1
        player.permanent_bonus = json.dumps(data, ensure_ascii=False)
        await self.db.update_player(player)

        furnace_names = ["凡铁炉", "青石炉", "紫金炉", "灵纹炉", "八卦炉", "五品玄天炉"]
        return True, (
            f"🔥 丹炉升级成功！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"{furnace_names[level]} → 【{furnace_names[level + 1]}】\n"
            f"炼丹成功率加成：+{level * 3}% → +{(level + 1) * 3}%\n"
            f"花费：{cost:,} 灵石"
        )

    async def get_available_recipes(self, user_id: str) -> Tuple[bool, str]:
        """获取可用的丹药配方"""
        player = await self.db.get_player_by_id(user_id)
        if not player:
            return False, "❌ 你还未踏入修仙之路！"
        
        available_recipes = [r for r in self.recipes.values() if player.level_index >= r.get("level_required", 0)]
        if not available_recipes:
            return False, "❌ 你当前境界无法炼制任何丹药！"

        furnace_level = self.get_furnace_level(player)
        furnace_names = ["凡铁炉", "青石炉", "紫金炉", "灵纹炉", "八卦炉", "五品玄天炉"]

        msg = f"🔥 丹药配方（当前丹炉：【{furnace_names[furnace_level]}】成功率+{furnace_level * 3}%）\n━━━━━━━━━━━━━━━\n\n"
        for recipe in available_recipes:
            materials_str = ", ".join([f"{k}×{v}" for k, v in recipe["materials"].items()])
            msg += f"【{recipe['name']}】(ID:{recipe['id']})\n"
            msg += f"  需求境界：Lv.{recipe['level_required']}\n"
            msg += f"  材料：{materials_str}\n"
            msg += f"  成功率：{recipe['success_rate']}%\n"
            msg += f"  效果：{recipe['desc']}\n\n"
        
        msg += "使用 /炼丹 <丹药ID> 开始炼制"
        return True, msg
    
    async def craft_pill(self, user_id: str, pill_id: int) -> Tuple[bool, str, Optional[Dict]]:
        """炼制丹药（加入事务防并发）"""
        await self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            # 事务内重新获取玩家对象，确保数据是最新的
            player = await self.db.get_player_by_id(user_id)
            if not player:
                await self.db.conn.rollback()
                return False, "❌ 你还未踏入修仙之路！", None
            
            if pill_id not in self.recipes:
                await self.db.conn.rollback()
                return False, "❌ 无效的丹药ID！", None
            
            recipe = self.recipes[pill_id]
            
            if player.level_index < recipe["level_required"]:
                await self.db.conn.rollback()
                return False, f"❌ 炼制{recipe['name']}需要达到境界等级 {recipe['level_required']}！", None
            
            # 检查所有材料
            materials = recipe["materials"]
            missing_materials = []
            
            required_gold = materials.get("灵石", 0)
            if player.gold < required_gold:
                missing_materials.append(f"灵石（需要{required_gold}，拥有{player.gold}）")
            
            if self.storage_ring_manager:
                for material_name, required_count in materials.items():
                    if material_name == "灵石":
                        continue
                    current_count = self.storage_ring_manager.get_item_count(player, material_name)
                    if current_count < required_count:
                        missing_materials.append(f"{material_name}（需要{required_count}，拥有{current_count}）")
            
            if missing_materials:
                await self.db.conn.rollback()
                return False, f"❌ 材料不足！\n" + "\n".join(f"  · {m}" for m in missing_materials), None
            
            # 扣除材料（灵石和储物戒物品）
            player.gold -= required_gold
            consumed_materials = []
            
            if self.storage_ring_manager:
                items = player.get_storage_ring_items()
                for material_name, required_count in materials.items():
                    if material_name == "灵石":
                        continue
                    if material_name in items and items[material_name] >= required_count:
                        if items[material_name] == required_count:
                            del items[material_name]
                        else:
                            items[material_name] -= required_count
                        consumed_materials.append(f"{material_name}×{required_count}")
                player.set_storage_ring_items(items)
            
            # 判定成功率（丹炉等级每级+3%；宗门炼丹房每级+2%）
            success_rate = recipe["success_rate"]
            level_bonus = (player.level_index - recipe["level_required"]) * 2
            furnace_bonus = self.get_furnace_bonus_rate(player)
            sect_bonus = 0
            try:
                if player.sect_id:
                    sect = await self.db.ext.get_sect_by_id(player.sect_id)
                    if sect:
                        sect_bonus = int(json.loads(getattr(sect, "buildings", "{}") or "{}").get("炼丹房", 0)) * 2
            except Exception:
                sect_bonus = 0
            final_success_rate = min(95, success_rate + level_bonus + furnace_bonus + sect_bonus)
            
            is_success = random.randint(1, 100) <= final_success_rate
            
            # 构建消耗描述
            cost_lines = []
            if required_gold > 0:
                cost_lines.append(f"灵石 -{required_gold}")
            cost_lines.extend(consumed_materials)
            cost_str = "、".join(cost_lines) if cost_lines else "无"
            
            if is_success:
                # ===== 丹劫机制：高阶丹药出炉引来雷劫，需消耗引雷符抵消 =====
                tribulation_msg = ""
                pill_ruined = False
                if recipe["level_required"] >= 6 and random.randint(1, 100) <= 25:
                    # 事务内直接操作储物戒 JSON（retrieve_item 内部会开新事务，不能在此调用）
                    ring_items = player.get_storage_ring_items()
                    if self.storage_ring_manager and ring_items.get("引雷符", 0) >= 1:
                        if ring_items["引雷符"] <= 1:
                            del ring_items["引雷符"]
                        else:
                            ring_items["引雷符"] -= 1
                        player.set_storage_ring_items(ring_items)
                        tribulation_msg = ("\n⚡ 天降丹劫！你祭出【引雷符】引雷入体，"
                                           "雷光淬丹，丹药品质得以保全！（消耗引雷符x1）")
                    else:
                        pill_ruined = True
                        tribulation_msg = ("\n💥 天降丹劫！你没有【引雷符】护身，"
                                           "雷火焚炉，丹药在最后一刻化为灰烬...")
                # ============================================================

                if not pill_ruined:
                    # 炼制成功 - 存入丹药背包
                    pill_name = recipe["name"]
                    inventory = player.get_pills_inventory()
                    inventory[pill_name] = inventory.get(pill_name, 0) + 1
                    player.set_pills_inventory(inventory)
                else:
                    pill_name = recipe["name"]

                # 这里非常重要：commit=False，由外层事务统一提交
                await self.db.update_player(player, commit=False)

                if pill_ruined:
                    msg = f"""
💔 丹劫毁丹
━━━━━━━━━━━━━━━

炼制【{recipe['name']}】本已成功，却引来天雷降劫...

消耗：{cost_str}
成功率：{final_success_rate}%
{tribulation_msg}

💡 高阶丹药请随身携带【引雷符】（百宝阁有售）
                    """.strip()

                    result_data = {
                        "success": False,
                        "pill_name": recipe["name"],
                        "cost": required_gold,
                        "materials_consumed": consumed_materials,
                        "tribulation": True
                    }
                    await self.db.conn.commit()
                    return True, msg, result_data

                msg = f"""
🎉 炼丹成功！
━━━━━━━━━━━━━━━

你成功炼制了【{pill_name}】！
丹药已存入丹药背包

消耗：{cost_str}
成功率：{final_success_rate}%
{tribulation_msg}

💡 使用 /服用丹药 {pill_name} 可服用此丹药
💡 使用 /丹药背包 查看所有丹药
                """.strip()

                result_data = {
                    "success": True,
                    "pill_name": pill_name,
                    "cost": required_gold,
                    "materials_consumed": consumed_materials
                }
            else:
                # 炼制失败 - 扣除材料
                await self.db.update_player(player, commit=False)
                
                msg = f"""
💔 炼丹失败
━━━━━━━━━━━━━━━

炼制【{recipe['name']}】失败了...

材料已消耗
消耗：{cost_str}
成功率：{final_success_rate}%

再接再厉！
                """.strip()
                
                result_data = {
                    "success": False,
                    "pill_name": recipe["name"],
                    "cost": required_gold,
                    "materials_consumed": consumed_materials
                }
            
            await self.db.conn.commit()
            return True, msg, result_data
            
        except Exception as e:
            await self.db.conn.rollback()
            raise