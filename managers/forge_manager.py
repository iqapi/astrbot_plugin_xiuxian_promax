# managers/forge_manager.py
import random
import json
from typing import Tuple
from ..data import DataBase
from ..models import Player

class ForgeManager:
    """炼器与洗练管理器"""
    
    # 洗练词条池（随机抽取）
    AFFIX_POOL = [
        {"key": "crit_rate", "name": "暴击率", "value": 5, "desc": "战斗中增加5%暴击率"},
        {"key": "lifesteal", "name": "吸血", "value": 3, "desc": "战斗中增加3%吸血"},
        {"key": "counter_damage", "name": "反伤", "value": 5, "desc": "战斗中反弹5%伤害"},
        {"key": "combo_rate", "name": "连击率", "value": 5, "desc": "战斗中增加5%连击率"},
        {"key": "physical_damage_multiplier", "name": "物伤加成", "value": 0.05, "desc": "提升5%物伤"},
        {"key": "magic_damage_multiplier", "name": "法伤加成", "value": 0.05, "desc": "提升5%法伤"}
    ]

    def __init__(self, db: DataBase, config_manager, storage_ring_mgr):
        self.db = db
        self.config_manager = config_manager
        self.storage_ring_mgr = storage_ring_mgr

    def _get_bonus_data(self, player: Player) -> dict:
        """安全获取玩家 permanent_bonus 数据"""
        try:
            data = json.loads(player.permanent_bonus)
            if not isinstance(data, dict):
                return {"forge_level": 0, "affixes": []}
            if "forge_level" not in data:
                data["forge_level"] = 0
            if "affixes" not in data:
                data["affixes"] = []
            return data
        except Exception:
            return {"forge_level": 0, "affixes": []}

    def _get_pity(self, player: Player) -> int:
        """v3.40.0 强化保底：当前连败计数"""
        data = self._get_bonus_data(player)
        try:
            return max(0, int(data.get("forge_pity", 0)))
        except (TypeError, ValueError):
            return 0

    async def enhance_equipment(self, player: Player) -> Tuple[bool, str]:
        """强化当前装备（全局炼器等级）"""
        data = self._get_bonus_data(player)
        current_level = data.get("forge_level", 0)
        
        if current_level >= 15:
            return False, "❌ 你的炼器等级已达上限（+15）。"
            
        # 消耗公式：等级越高，消耗越多
        cost_stone = 10 + current_level * 5
        cost_sword = 10000 * (current_level + 1)

        # 炼器师专精：灵石消耗减半
        skill_note = ""
        if getattr(player, "life_skill", "") == "炼器师":
            cost_sword = cost_sword // 2
            skill_note = "\n⚒️ 炼器师专精生效：灵石消耗减半"

        if not self.storage_ring_mgr.has_item(player, "强化石", cost_stone):
            return False, f"❌ 你的储物戒里没有足够的【强化石】。\n需要：{cost_stone}个"

        if player.gold < cost_sword:
            return False, f"❌ 灵石不足！需要 {cost_sword:,} 灵石。"

        # v3.25.5：先条件原子扣灵石再扣材料（防快照过期透支；不再整行覆写）
        cursor = await self.db.conn.execute(
            "UPDATE players SET gold = gold - ? WHERE user_id = ? AND gold >= ?",
            (cost_sword, player.user_id, cost_sword)
        )
        await self.db.conn.commit()
        if cursor.rowcount == 0:
            return False, f"❌ 灵石不足！需要 {cost_sword:,} 灵石。"
        player.gold -= cost_sword
        await self.storage_ring_mgr.retrieve_item(player, "强化石", cost_stone)

        # 判定成功率（v3.40.0 强化保底：连败 3 次后成功率每败 +15%，最高 100%）
        success_rate = max(0.2, 1.0 - current_level * 0.05)
        pity = self._get_pity(player)
        if pity >= 3:
            success_rate = min(1.0, success_rate + (pity - 2) * 0.15)
        pity_note = f"\n🛡️ 强化保底生效：连败 {pity} 次，本次成功率提升至 {success_rate:.0%}" if pity >= 3 else ""

        if random.random() < success_rate:
            data["forge_level"] = current_level + 1
            if pity >= 3:
                data["forge_pity"] = 0
                pity_note = f"\n🛡️ 保底兑现：{pity} 次连败后终于成功，保底计数已清零"
            player.permanent_bonus = json.dumps(data)
            await self.db.update_player_fields(player.user_id, permanent_bonus=player.permanent_bonus)
            return True, f"✨ 炼器成功！你的炼器等级提升至 +{current_level + 1}。\n（全属性基础攻击/防御获得加成）{skill_note}{pity_note}"
        else:
            # v3.40.0：连败计数 +1（保底进度），定向落库
            data["forge_pity"] = pity + 1
            player.permanent_bonus = json.dumps(data)
            await self.db.update_player_fields(player.user_id, permanent_bonus=player.permanent_bonus)
            back_note = f"\n🛡️ 强化保底：已连败 {pity + 1} 次" + ("，下次成功率大幅提升！" if pity + 1 >= 3 else "（3 连败后触发保底加成）")
            return False, f"💥 炼器失败！由于火候不佳，消耗了材料和灵石，但等级未提升（当前 +{current_level}）。{skill_note}{back_note}"

    async def wash_equipment(self, player: Player) -> Tuple[bool, str]:
        """洗练装备词条"""
        data = self._get_bonus_data(player)
        
        # 每次洗练消耗一个洗练石
        if not self.storage_ring_mgr.has_item(player, "洗练石", 1):
            return False, "❌ 你的储物戒里没有【洗练石】。"
            
        await self.storage_ring_mgr.retrieve_item(player, "洗练石", 1)
        
        # 随机抽取一个新词条
        new_affix = random.choice(self.AFFIX_POOL).copy()
        # 数值浮动 ±20%
        multiplier = random.uniform(0.8, 1.2)
        if isinstance(new_affix["value"], float):
            new_affix["value"] = round(new_affix["value"] * multiplier, 3)
        else:
            new_affix["value"] = int(new_affix["value"] * multiplier)
            
        new_affix["display"] = f"{new_affix['name']}+{new_affix['value']}"
        if isinstance(new_affix["value"], float):
            new_affix["display"] = f"{new_affix['name']}+{new_affix['value']*100:.1f}%"
            
        # 最多保留 3 条词条
        affixes = data.get("affixes", [])
        affixes.append(new_affix)
        if len(affixes) > 3:
            affixes.pop(0)
            
        data["affixes"] = affixes
        player.permanent_bonus = json.dumps(data)
        # v3.25.5：只落 permanent_bonus，不再整行覆写
        await self.db.update_player_fields(player.user_id, permanent_bonus=player.permanent_bonus)
        
        msg = [
            "✨ 洗练成功！你获得了新词条：",
            f"👉 {new_affix['display']}",
            "━━━━━━━━━━━━━━━",
            "【当前装备总词条】"
        ]
        for a in affixes:
            msg.append(f"· {a['display']}")
            
        return True, "\n".join(msg)