# handlers/combat_handlers.py
import re
import time
from astrbot.api.event import AstrMessageEvent
from astrbot.api.all import *
from ..managers.combat_manager import CombatManager, CombatStats
from ..data.data_manager import DataBase
from ..core import EquipmentManager, PillManager
from .utils import player_required
from ..models import Player
from ..models_extended import UserStatus

DUEL_COOLDOWN = 300
SPAR_COOLDOWN = 60

class CombatHandlers:
    def __init__(self, db: DataBase, combat_mgr: CombatManager, config_manager=None):
        self.db = db
        self.combat_mgr = combat_mgr
        self.config_manager = config_manager
        self.equipment_mgr = EquipmentManager(db, config_manager)
        self.pill_mgr = PillManager(db, config_manager)
        self.last_duel_result = None  # 记录最近一场决斗结果，供任务进度判定
    
    async def _get_combat_cooldown(self, user_id: str) -> dict:
        try:
            async with self.db.conn.execute("SELECT last_duel_time, last_spar_time FROM combat_cooldowns WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row: return {"last_duel_time": row[0], "last_spar_time": row[1]}
        except: pass
        return {"last_duel_time": 0, "last_spar_time": 0}
    
    async def _update_combat_cooldown(self, user_id: str, combat_type: str):
        now = int(time.time())
        try:
            if combat_type == "duel":
                await self.db.conn.execute("INSERT INTO combat_cooldowns (user_id, last_duel_time, last_spar_time) VALUES (?, ?, 0) ON CONFLICT(user_id) DO UPDATE SET last_duel_time = ?", (user_id, now, now))
            else:
                await self.db.conn.execute("INSERT INTO combat_cooldowns (user_id, last_duel_time, last_spar_time) VALUES (?, 0, ?) ON CONFLICT(user_id) DO UPDATE SET last_spar_time = ?", (user_id, now, now))
            await self.db.conn.commit()
        except: pass

    async def _get_target_id(self, event: AstrMessageEvent, arg: str) -> str:
        """解析目标ID，兼容 At 组件和纯文本"""
        message_chain = []
        if hasattr(event, "message_obj") and event.message_obj:
            message_chain = getattr(event.message_obj, "message", []) or []
        for component in message_chain:
            if isinstance(component, At):
                candidate = None
                for attr in ("qq", "target", "uin", "user_id"):
                    candidate = getattr(component, attr, None)
                    if candidate: break
                if candidate: return str(candidate).lstrip("@")
        if arg:
            cleaned = arg.strip().lstrip("@")
            if cleaned.isdigit(): return cleaned
        
        message_text = ""
        if hasattr(event, "message_str"): message_text = event.message_str or ""
        match = re.search(r'(\d{5,})', message_text)
        if match: return match.group(1)
        return None

    def _calculate_equipment_bonus(self, player) -> dict:
        bonus = {"atk": 0, "defense": 0}
        if not self.config_manager: return bonus
        if player.weapon and player.weapon in self.config_manager.weapons_data:
            data = self.config_manager.weapons_data[player.weapon]
            bonus["atk"] += data.get("atk", 0) + data.get("physical_damage", 0) + data.get("magic_damage", 0)
        if player.armor and player.armor in self.config_manager.items_data:
            data = self.config_manager.items_data[player.armor]
            bonus["defense"] += data.get("physical_defense", 0) + data.get("magic_defense", 0)
        return bonus

    async def _prepare_combat_stats(self, user_id: str) -> CombatStats:
        """准备战斗属性（包含装备、功法、灵兽、丹药加成）"""
        player = await self.db.get_player_by_id(user_id)
        if not player: return None
        
        # 获取并应用丹药临时效果
        await self.pill_mgr.update_temporary_effects(player)
        pill_multipliers = self.pill_mgr.calculate_pill_attribute_effects(player)
        
        impart_info = await self.db.ext.get_impart_info(user_id)
        hp_buff = impart_info.impart_hp_per if impart_info else 0.0
        mp_buff = impart_info.impart_mp_per if impart_info else 0.0
        atk_buff = impart_info.impart_atk_per if impart_info else 0.0
        
        # 计算基础面板
        base_hp, base_mp = self.combat_mgr.calculate_hp_mp(player.experience, hp_buff, mp_buff)
        # 气血受丹药倍率影响
        hp = int(base_hp * max(pill_multipliers.get("physical_damage", 1.0), pill_multipliers.get("magic_damage", 1.0)))
        mp = base_mp
        
        base_atk = self.combat_mgr.calculate_atk(player.experience, player.atkpractice, atk_buff, player.physical_damage, player.magic_damage, player.cultivation_type)
        # 攻击力受丹药倍率加成
        final_atk_multiplier = max(pill_multipliers.get("physical_damage", 1.0), pill_multipliers.get("magic_damage", 1.0))
        base_atk = int(base_atk * final_atk_multiplier)
        
        equip_bonus = self._calculate_equipment_bonus(player)
        final_atk = base_atk + equip_bonus["atk"]
        
        # 获取功法/装备/词条特效
        effects = self.equipment_mgr.get_combat_effects(player)

        # ===== v6.17 称号加成（最高品阶生效）=====
        title_magic = 0
        title_def_bonus = 0
        try:
            from ..managers.title_manager import TitleManager
            tm = TitleManager(self.db)
            tstats = tm.get_active_bonus(player)
            if tstats:
                final_atk += int(tstats.get("atk", 0))
                title_magic = int(tstats.get("magic", 0))
                title_def_bonus = int(tstats.get("phys_def", 0)) + int(tstats.get("magic_def", 0))
                effects["crit_rate"] = effects.get("crit_rate", 0) + int(tstats.get("crit", 0))
                effects["lifesteal"] = effects.get("lifesteal", 0) + int(tstats.get("lifesteal", 0))
        except Exception:
            pass

        # 获取灵兽特效并注入
        from ..managers.pet_manager import PetManager
        pet_mgr = PetManager(self.db)
        pet = await pet_mgr.get_pet(user_id)
        if pet:
            pet_effects = pet_mgr.get_pet_combat_effects(pet)
            for k, v in pet_effects.items():
                effects[k] = effects.get(k, 0) + v
            triggered, log_msg, mult = await pet_mgr.pet_coop_attack(pet)
            if triggered:
                effects["pet_damage_mult"] = mult
                
        # 防御力受丹药倍率加成
        final_defense = int(equip_bonus["defense"] * max(pill_multipliers.get("physical_defense", 1.0), pill_multipliers.get("magic_defense", 1.0)))
        # 称号防御/法伤加成
        final_defense += title_def_bonus
        final_atk += title_magic
        
        player.hp = hp
        player.mp = mp
        player.atk = final_atk
        await self.db.update_player(player)

        return CombatStats(
            user_id=user_id,
            name=player.user_name if player.user_name else f"道友{user_id}",
            hp=hp, max_hp=hp, mp=mp, max_mp=mp,
            atk=final_atk,
            defense=final_defense,
            exp=player.experience,
            effects=effects,
            # 五行属性：优先配置显式标注（主修心法 > 武器），其次名称推断
            element=(self._get_element_of(player.main_technique) or self._get_element_of(player.weapon))
        )

    def _get_element_of(self, item_name: str) -> str:
        if not item_name:
            return ""
        if self.config_manager and hasattr(self.config_manager, "get_item_element"):
            explicit = self.config_manager.get_item_element(item_name)
            if explicit:
                return explicit
        return self.combat_mgr.get_element_from_name(item_name)

    async def handle_duel(self, event: AstrMessageEvent, target: str):
        """决斗 (受丹药/装备/灵兽加成，战后恢复满血)"""
        user_id = event.get_sender_id()
        target_id = await self._get_target_id(event, target)
        if not target_id:
            yield event.plain_result(
                "❌ 未识别到对手！请 @对方 或输入对方QQ号。\n"
                "用法：/决斗 @道友\n（同一目标5分钟内只能决斗一次）"
            )
            return
        if user_id == target_id:
            yield event.plain_result("❌ 不能和自己决斗，左手打右手是不行的。")
            return

        # 决斗冷却检查（5分钟）
        cooldowns = await self._get_combat_cooldown(user_id)
        now = int(time.time())
        remaining_cd = DUEL_COOLDOWN - (now - cooldowns["last_duel_time"])
        if cooldowns["last_duel_time"] and remaining_cd > 0:
            yield event.plain_result(
                f"❌ 决斗调息中，请 {remaining_cd // 60} 分 {remaining_cd % 60} 秒后再战。"
            )
            return

        p1_stats = await self._prepare_combat_stats(user_id)
        p2_stats = await self._prepare_combat_stats(target_id)
        if not p1_stats or not p2_stats:
            yield event.plain_result("❌ 双方都需要踏入修仙之路（对方可能还没创建角色），请先发送 /我要修仙。")
            return

        result = self.combat_mgr.player_vs_player(p1_stats, p2_stats, combat_type=2)
        self.last_duel_result = result
        
        # ===== 核心修复：决斗结束后，强制恢复双方满状态 =====
        await self.db.ext.update_player_hp_mp(user_id, p1_stats.max_hp, p1_stats.max_mp)
        await self.db.ext.update_player_hp_mp(target_id, p2_stats.max_hp, p2_stats.max_mp)
        # =======================================================

        await self._update_combat_cooldown(user_id, "duel")
        
        yield event.plain_result("\n".join(result['combat_log']))

    async def handle_spar(self, event: AstrMessageEvent, target: str):
        """切磋 (受丹药/装备/灵兽加成，战后恢复满血)"""
        user_id = event.get_sender_id()
        target_id = await self._get_target_id(event, target)
        if not target_id:
            yield event.plain_result(
                "❌ 未识别到对手！请 @对方 或输入对方QQ号。\n"
                "用法：/切磋 @道友\n（切磋冷却1分钟）"
            )
            return
        if user_id == target_id:
            yield event.plain_result("❌ 不能和自己切磋。")
            return

        # 切磋冷却检查（1分钟）
        cooldowns = await self._get_combat_cooldown(user_id)
        now = int(time.time())
        remaining_cd = SPAR_COOLDOWN - (now - cooldowns["last_spar_time"])
        if cooldowns["last_spar_time"] and remaining_cd > 0:
            yield event.plain_result(
                f"❌ 切磋调息中，请 {remaining_cd // 60} 分 {remaining_cd % 60} 秒后再战。"
            )
            return

        p1_stats = await self._prepare_combat_stats(user_id)
        p2_stats = await self._prepare_combat_stats(target_id)
        if not p1_stats or not p2_stats:
            yield event.plain_result("❌ 双方都需要踏入修仙之路（对方可能还没创建角色），请先发送 /我要修仙。")
            return

        result = self.combat_mgr.player_vs_player(p1_stats, p2_stats, combat_type=1)
        self.last_spar_fought = True  # 真正开打了，供任务进度判定
        
        # ===== 核心修复：切磋结束后，强制恢复双方满状态 =====
        await self.db.ext.update_player_hp_mp(user_id, p1_stats.max_hp, p1_stats.max_mp)
        await self.db.ext.update_player_hp_mp(target_id, p2_stats.max_hp, p2_stats.max_mp)
        # =======================================================

        await self._update_combat_cooldown(user_id, "spar")
        
        yield event.plain_result("\n".join(result['combat_log']))