# core/pill_manager.py

import time
from typing import Dict, List, Optional, Tuple
from astrbot.api import logger

from ..models import Player
from ..data import DataBase
from ..config_manager import ConfigManager


class PillManager:
    """丹药管理器 - 处理丹药效果、属性加成和限制机制"""

    def __init__(self, db: DataBase, config_manager: ConfigManager):
        self.db = db
        self.config_manager = config_manager

    def _ensure_non_negative_attributes(self, player: Player):
        """保证属性不为负，并同步能量上限约束"""
        attrs = [
            "lifespan",
            "experience",
            "physical_damage",
            "magic_damage",
            "physical_defense",
            "magic_defense",
            "mental_power",
            "spiritual_qi",
            "max_spiritual_qi",
            "blood_qi",
            "max_blood_qi",
        ]
        for attr in attrs:
            value = getattr(player, attr, 0)
            if value < 0:
                setattr(player, attr, 0)

        if player.spiritual_qi > player.max_spiritual_qi:
            player.spiritual_qi = player.max_spiritual_qi
        if player.blood_qi > player.max_blood_qi:
            player.blood_qi = player.max_blood_qi

    def get_pill_by_name(self, pill_name: str) -> Optional[dict]:
        """根据名称获取丹药配置"""
        pill = self.config_manager.pills_data.get(pill_name)
        if pill:
            return pill

        pill = self.config_manager.exp_pills_data.get(pill_name)
        if pill:
            return pill

        pill = self.config_manager.utility_pills_data.get(pill_name)
        if pill:
            return pill

        for item in self.config_manager.items_data.values():
            if item.get("name") == pill_name and item.get("type") == "丹药":
                return item

        return None

    def get_pill_kind(self, pill_data: dict) -> Tuple[str, str]:
        """丹药分类：返回 (类别名, 说明)。帮助玩家理解临时/永久/一次性"""
        subtype = pill_data.get("subtype", "")
        effect_type = pill_data.get("effect_type", "")
        if subtype == "breakthrough":
            return ("🔥破境丹", "仅在 /突破 时消耗，大幅提升成功率")
        if subtype == "resurrection":
            return ("🛡回生丹", "被动持有：死亡时自动抵消一次（一次性）")
        if subtype == "exp" or "exp_gain" in pill_data:
            return ("📈修为丹", "服用立即永久增加修为（一次性消耗）")
        if "effect" in pill_data or any(k.startswith("add_") for k in pill_data.keys()):
            return ("💊药力丹", "服用立即永久增加属性（一次性消耗）")
        if effect_type == "temporary":
            mins = pill_data.get("duration_minutes", 0)
            return (f"⏱临时丹", f"服用后 {mins} 分钟内生效，到期自动失效（不重复叠加）")
        if effect_type == "permanent":
            return ("🌟永久丹", "服用永久增加属性，受 30% 上限约束")
        if effect_type == "instant":
            return ("⚡恢复丹", "立即恢复灵气/气血（一次性消耗，满状态时服用浪费）")
        return ("❓未知", "效果未知，谨慎服用")

    async def update_temporary_effects(self, player: Player):
        """更新临时丹药效果，移除过期效果"""
        effects = player.get_active_pill_effects()
        current_time = int(time.time())
        updated_effects = []
        has_changes = False

        for effect in effects:
            if self._apply_periodic_effects(player, effect, current_time):
                has_changes = True

            expiry_time = effect.get("expiry_time", 0)
            if expiry_time <= 0 or current_time < expiry_time:
                updated_effects.append(effect)
            else:
                has_changes = True
                logger.info(f"玩家 {player.user_id} 的丹药效果 {effect.get('pill_name')} 已过期")

        if has_changes or len(updated_effects) != len(effects):
            player.set_active_pill_effects(updated_effects)
            await self.db.update_player(player)

    async def use_pill(
        self,
        player: Player,
        pill_name: str
    ) -> Tuple[bool, str]:
        """使用丹药"""
        inventory = player.get_pills_inventory()
        if pill_name not in inventory or inventory[pill_name] <= 0:
            return False, f"你的背包中没有【{pill_name}】！"

        pill_data = self.get_pill_by_name(pill_name)
        if not pill_data:
            return False, f"丹药【{pill_name}】配置不存在！"

        required_level = pill_data.get("required_level_index", 0)
        if player.level_index < required_level:
            level_data = self.config_manager.get_level_data(player.cultivation_type)
            level_name = f"境界{required_level}"
            if 0 <= required_level < len(level_data):
                level_name = level_data[required_level]["level_name"]
            return False, (
                f"❌ 境界不足，无法服用！\n"
                f"━━━━━━━━━━━━━━━\n"
                f"【{pill_name}】需要达到【{level_name}】（境界等级 {required_level}）\n"
                f"你当前境界等级：{player.level_index}（还差 {required_level - player.level_index} 级）\n"
                f"💡 丹药不会过期，先提升境界再来服用\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💡 通过 /闭关 /历练 提升修为后 /突破 提高境界"
            )

        effect_type = pill_data.get("effect_type", "instant")
        subtype = pill_data.get("subtype", "")

        if subtype == "breakthrough":
            return False, f"【{pill_name}】是破境丹，只能在突破时使用！"

        if subtype == "exp":
            return await self._use_exp_pill(player, pill_name, pill_data)
        elif subtype == "resurrection":
            return await self._use_resurrection_pill(player, pill_name, pill_data)
        elif effect_type == "temporary":
            return await self._use_temporary_pill(player, pill_name, pill_data)
        elif effect_type == "permanent":
            return await self._use_permanent_pill(player, pill_name, pill_data)
        elif effect_type == "instant":
            return await self._use_instant_pill(player, pill_name, pill_data)
        elif "effect" in pill_data or any(k.startswith("add_") for k in pill_data.keys()):
            # legacy 丹药（items.json 中 type=丹药，effect 字段直接含 add_xxx）
            return await self._use_legacy_pill(player, pill_name, pill_data)
        else:
            return False, f"未知的丹药类型：{effect_type}"

    async def _use_legacy_pill(self, player: Player, pill_name: str, pill_data: dict) -> Tuple[bool, str]:
        """服用 legacy 丹药（items.json：effect = {add_experience/add_hp/add_attack/...}）"""
        effect = pill_data.get("effect") or {}
        if not effect:
            # 兼容直接平铺 add_xxx 字段的写法
            effect = {k: v for k, v in pill_data.items() if k.startswith("add_")}
        if not effect:
            return False, f"【{pill_name}】没有可生效的药力（配置缺失），已联系天道修补。"

        msgs = []

        def apply(key, label, fn):
            if key in effect:
                v = int(effect[key])
                fn(v)
                msgs.append(f"{label}{'+' if v >= 0 else ''}{v:,}")

        if "add_experience" in effect:
            v = int(effect["add_experience"])
            player.experience = max(0, player.experience + v)
            msgs.append(f"修为+{v:,}")
        if "add_gold" in effect:
            v = int(effect["add_gold"])
            player.gold = max(0, player.gold + v)
            msgs.append(f"灵石+{v:,}")
        if "add_hp" in effect:
            v = int(effect["add_hp"])
            if player.cultivation_type == "体修":
                old = player.blood_qi
                player.blood_qi = max(0, min(player.max_blood_qi, player.blood_qi + v))
                msgs.append(f"气血+{player.blood_qi - old}")
            else:
                old = player.spiritual_qi
                player.spiritual_qi = max(0, min(player.max_spiritual_qi, player.spiritual_qi + v))
                msgs.append(f"灵气+{player.spiritual_qi - old}")
        if "add_max_hp" in effect:
            v = int(effect["add_max_hp"])
            if player.cultivation_type == "体修":
                player.max_blood_qi += v
                msgs.append(f"气血上限+{v}")
            else:
                player.max_spiritual_qi += v
                msgs.append(f"灵气上限+{v}")
        if "add_attack" in effect:
            v = int(effect["add_attack"])
            player.physical_damage = max(0, player.physical_damage + v)
            msgs.append(f"物伤+{v}")
        if "add_spiritual_power" in effect:
            v = int(effect["add_spiritual_power"])
            player.magic_damage = max(0, player.magic_damage + v)
            msgs.append(f"法伤+{v}")
        if "add_defense" in effect:
            v = int(effect["add_defense"])
            player.physical_defense = max(0, player.physical_defense + v)
            msgs.append(f"物防+{v}")
        if "add_mental_power" in effect:
            v = int(effect["add_mental_power"])
            player.mental_power = max(0, player.mental_power + v)
            msgs.append(f"精神力+{v}")

        if not msgs:
            return False, f"【{pill_name}】的药力配置无法解析。"

        # 扣丹
        inventory = player.get_pills_inventory()
        inventory[pill_name] -= 1
        if inventory[pill_name] <= 0:
            del inventory[pill_name]
        player.set_pills_inventory(inventory)
        await self.db.update_player(player)

        return True, (
            "✨ 服用【" + pill_name + "】成功！\n"
            "━━━━━━━━━━━━━━━\n"
            "💊 药力：" + "、".join(msgs) + "\n"
            "━━━━━━━━━━━━━━━"
        )

    async def _use_exp_pill(self, player: Player, pill_name: str, pill_data: dict) -> Tuple[bool, str]:
        """使用修为丹"""
        exp_gain = pill_data.get("exp_gain", 0)
        # v3.18.4 数值平衡：修为丹实际收益随境界衰减（每境界 -15%，等效于后期丹药涨价），
        # 否则"10 exp/灵石"的固定定价会让 60B 的满级需求与全服灵石产出差 4 个数量级
        level_decay = 1 + (player.level_index or 0) * 0.15
        effective_exp = max(1, int(exp_gain / level_decay))
        player.experience += effective_exp

        inventory = player.get_pills_inventory()
        inventory[pill_name] -= 1
        if inventory[pill_name] <= 0:
            del inventory[pill_name]
        player.set_pills_inventory(inventory)

        await self.db.update_player(player)

        decay_note = ""
        if effective_exp < exp_gain:
            decay_note = f"\n🌫️ 境界渐高，丹药药力折损为 {level_decay:.2f} 倍逆（高境界修为丹收益递减）"
        return True, (
            f"✨ 服用【{pill_name}】成功！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📈 获得修为：{effective_exp}{decay_note}\n"
            f"💫 当前修为：{player.experience}\n"
            f"━━━━━━━━━━━━━━━"
        )

    async def _use_resurrection_pill(self, player: Player, pill_name: str, pill_data: dict) -> Tuple[bool, str]:
        """使用回生丹"""
        if player.has_resurrection_pill:
            return False, "你已经拥有回生丹效果，无需重复使用！"

        player.has_resurrection_pill = True

        inventory = player.get_pills_inventory()
        inventory[pill_name] -= 1
        if inventory[pill_name] <= 0:
            del inventory[pill_name]
        player.set_pills_inventory(inventory)

        await self.db.update_player(player)

        return True, (
            f"✨ 服用【{pill_name}】成功！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🛡️ 你获得了起死回生的能力\n"
            f"下次死亡时将自动复活\n"
            f"（复活后所有属性减半）\n"
            f"━━━━━━━━━━━━━━━"
        )

    async def _use_temporary_pill(self, player: Player, pill_name: str, pill_data: dict) -> Tuple[bool, str]:
        """使用临时效果丹药"""
        duration_minutes = pill_data.get("duration_minutes", 60)
        current_time = int(time.time())
        expiry_time = current_time + duration_minutes * 60

        effect = {
            "pill_name": pill_name,
            "pill_id": pill_data.get("id", ""),
            "subtype": pill_data.get("subtype", ""),
            "start_time": current_time,
            "expiry_time": expiry_time,
            "duration_minutes": duration_minutes,
            "last_tick_time": current_time,
        }

        effect_keys = [
            "cultivation_multiplier", "physical_damage_multiplier", "magic_damage_multiplier",
            "physical_defense_multiplier", "magic_defense_multiplier",
            "lifespan_cost_per_minute", "lifespan_regen_per_minute",
            "spiritual_qi_regen_per_minute", "blood_qi_regen_per_minute", "blood_qi_cost_per_minute",
            "breakthrough_bonus"
        ]
        for key in effect_keys:
            if key in pill_data:
                effect[key] = pill_data[key]

        effects = player.get_active_pill_effects()
        effects.append(effect)
        player.set_active_pill_effects(effects)

        inventory = player.get_pills_inventory()
        inventory[pill_name] -= 1
        if inventory[pill_name] <= 0:
            del inventory[pill_name]
        player.set_pills_inventory(inventory)

        await self.db.update_player(player)

        effect_desc = []
        if "cultivation_multiplier" in pill_data:
            mult = pill_data["cultivation_multiplier"]
            effect_desc.append(f"修炼速度{'+' if mult > 0 else ''}{mult:.0%}")
        if "physical_damage_multiplier" in pill_data:
            mult = pill_data["physical_damage_multiplier"]
            effect_desc.append(f"物伤{'+' if mult > 0 else ''}{mult:.0%}")
        if "magic_damage_multiplier" in pill_data:
            mult = pill_data["magic_damage_multiplier"]
            effect_desc.append(f"法伤{'+' if mult > 0 else ''}{mult:.0%}")
        if "breakthrough_bonus" in pill_data:
            bonus = pill_data["breakthrough_bonus"]
            effect_desc.append(f"突破成功率{'+' if bonus > 0 else ''}{bonus:.0%}")

        effects_str = "、".join(effect_desc) if effect_desc else "特殊效果"

        return True, (
            f"✨ 服用【{pill_name}】成功！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⏱️ 持续时间：{duration_minutes}分钟\n"
            f"🎯 效果：{effects_str}\n"
            f"━━━━━━━━━━━━━━━"
        )

    async def _use_permanent_pill(self, player: Player, pill_name: str, pill_data: dict) -> Tuple[bool, str]:
        """使用永久属性丹药"""
        permanent_gains = player.get_permanent_pill_gains()
        level_key = f"level_{player.level_index}"

        if level_key not in permanent_gains:
            permanent_gains[level_key] = {
                "physical_damage": 0, "magic_damage": 0,
                "physical_defense": 0, "magic_defense": 0,
                "mental_power": 0, "lifespan": 0,
                "max_spiritual_qi": 0, "max_blood_qi": 0,
            }

        base_attrs = self._get_base_attributes_for_level(player, player.level_index)

        attr_mapping = {
            "physical_damage_gain": ("physical_damage", "物伤"),
            "magic_damage_gain": ("magic_damage", "法伤"),
            "physical_defense_gain": ("physical_defense", "物防"),
            "magic_defense_gain": ("magic_defense", "法防"),
            "mental_power_gain": ("mental_power", "精神力"),
            "lifespan_gain": ("lifespan", "寿命"),
            "max_spiritual_qi_gain": ("max_spiritual_qi", "最大灵气"),
            "max_blood_qi_gain": ("max_blood_qi", "最大气血"),
        }

        gains_applied = {}
        gains_blocked = {}

        for gain_key, (attr_key, attr_name) in attr_mapping.items():
            if gain_key not in pill_data:
                continue

            gain = pill_data[gain_key]
            if gain == 0:
                continue

            if gain > 0:
                current_gain = permanent_gains[level_key].get(attr_key, 0)
                base_value = base_attrs.get(attr_key, 100)
                limit = base_value * 0.3

                if current_gain >= limit:
                    gains_blocked[attr_name] = f"已达上限({limit:.0f})"
                    continue

                actual_gain = min(gain, limit - current_gain)
                if actual_gain < gain:
                    gains_blocked[attr_name] = f"部分受限(+{actual_gain:.0f}/{gain})"

                permanent_gains[level_key][attr_key] += actual_gain
                setattr(player, attr_key, getattr(player, attr_key) + int(actual_gain))
                gains_applied[attr_name] = int(actual_gain)
            else:
                permanent_gains[level_key][attr_key] += gain
                setattr(player, attr_key, getattr(player, attr_key) + int(gain))
                gains_applied[attr_name] = int(gain)

        if "cultivation_multiplier" in pill_data:
            cult_mult = pill_data["cultivation_multiplier"]
            if "cultivation_multiplier" not in permanent_gains[level_key]:
                permanent_gains[level_key]["cultivation_multiplier"] = 0
            permanent_gains[level_key]["cultivation_multiplier"] += cult_mult
            gains_applied["修炼速度"] = f"{cult_mult:+.0%}"

        if "death_protection_multiplier" in pill_data:
            death_mult = pill_data["death_protection_multiplier"]
            if "death_protection_multiplier" not in permanent_gains[level_key]:
                permanent_gains[level_key]["death_protection_multiplier"] = 1.0
            permanent_gains[level_key]["death_protection_multiplier"] *= death_mult
            gains_applied["突破死亡概率"] = f"降低{(1 - death_mult) * 100:.0f}%"

        if not gains_applied:
            return False, "该丹药的所有属性增益都已达到上限，无法使用！"

        self._ensure_non_negative_attributes(player)
        player.set_permanent_pill_gains(permanent_gains)

        inventory = player.get_pills_inventory()
        inventory[pill_name] -= 1
        if inventory[pill_name] <= 0:
            del inventory[pill_name]
        player.set_pills_inventory(inventory)

        await self.db.update_player(player)

        msg_parts = [f"✨ 服用【{pill_name}】成功！", "━━━━━━━━━━━━━━━", "💪 永久增益："]
        for attr_name, value in gains_applied.items():
            if isinstance(value, int):
                msg_parts.append(f"  {attr_name} +{value}")
            else:
                msg_parts.append(f"  {attr_name} {value}")

        if gains_blocked:
            msg_parts.append("\n⚠️ 受限提示：")
            for attr_name, reason in gains_blocked.items():
                msg_parts.append(f"  {attr_name} {reason}")

        msg_parts.append("━━━━━━━━━━━━━━━")
        msg_parts.append("注：每个境界的永久属性丹药增益最多为基础属性的30%")

        return True, "\n".join(msg_parts)

    async def _use_instant_pill(self, player: Player, pill_name: str, pill_data: dict) -> Tuple[bool, str]:
        """使用瞬间效果丹药"""
        msg_parts = [f"✨ 服用【{pill_name}】成功！", "━━━━━━━━━━━━━━━"]

        energy_restore = None
        energy_label = "灵气"
        current_energy = player.spiritual_qi
        max_energy = player.max_spiritual_qi

        if player.cultivation_type == "体修" and "blood_qi_restore" in pill_data:
            energy_restore = pill_data["blood_qi_restore"]
            energy_label = "气血"
            current_energy = player.blood_qi
            max_energy = player.max_blood_qi
        elif "spiritual_qi_restore" in pill_data:
            energy_restore = pill_data["spiritual_qi_restore"]
            if player.cultivation_type == "体修":
                energy_label = "气血"
                current_energy = player.blood_qi
                max_energy = player.max_blood_qi

        if energy_restore is not None:
            if energy_restore == -1:
                actual_restore = max_energy - current_energy  # 恢复至上限，实际恢复量为缺口
                current_energy = max_energy
            else:
                old_energy = current_energy
                current_energy = min(current_energy + energy_restore, max_energy)
                actual_restore = current_energy - old_energy

            if energy_label == "气血":
                player.blood_qi = current_energy
                msg_parts.append(f"🌟 恢复气血：+{actual_restore}")
                msg_parts.append(f"🩸 当前气血：{player.blood_qi}/{player.max_blood_qi}")
            else:
                player.spiritual_qi = current_energy
                msg_parts.append(f"🌟 恢复灵气：+{actual_restore}")
                msg_parts.append(f"💫 当前灵气：{player.spiritual_qi}/{player.max_spiritual_qi}")

        if pill_data.get("resets_permanent_pills"):
            reset_applied = self._reset_permanent_pill_effects(player)
            if reset_applied:
                msg_parts.append("🔄 已重置所有永久属性丹药增益")
                refund_ratio = pill_data.get("reset_refund_ratio", 0.5)
                refund = int(pill_data.get("price", 0) * refund_ratio)
                if refund > 0:
                    player.gold += refund
                    msg_parts.append(f"💰 返还灵石：{refund}")
            else:
                msg_parts.append("ℹ️ 当前没有可重置的永久增益")

        if pill_data.get("blocks_next_debuff"):
            if player.has_debuff_shield:
                msg_parts.append("🛡️ 定魂护盾已存在，无需重复使用")
            else:
                player.has_debuff_shield = True
                msg_parts.append("🛡️ 获得定魂护盾：下一次负面效果将被抵消")

        inventory = player.get_pills_inventory()
        inventory[pill_name] -= 1
        if inventory[pill_name] <= 0:
            del inventory[pill_name]
        player.set_pills_inventory(inventory)

        await self.db.update_player(player)
        msg_parts.append("━━━━━━━━━━━━━━━")
        return True, "\n".join(msg_parts)

    def _get_base_attributes_for_level(self, player: Player, level_index: int) -> dict:
        """获取当前境界的基础属性"""
        level_data = self.config_manager.get_level_data(player.cultivation_type)
        if not level_data:
            level_data = self.config_manager.level_data

        if level_data:
            level_index = min(level_index, len(level_data) - 1)
            level_config = level_data[level_index]
        else:
            level_config = {}

        return {
            "physical_damage": level_config.get("breakthrough_physical_damage_gain", 10),
            "magic_damage": level_config.get("breakthrough_magic_damage_gain", 10),
            "physical_defense": level_config.get("breakthrough_physical_defense_gain", 5),
            "magic_defense": level_config.get("breakthrough_magic_defense_gain", 5),
            "mental_power": level_config.get("breakthrough_mental_power_gain", 100),
            "lifespan": level_config.get("breakthrough_lifespan_gain", 100),
            "max_spiritual_qi": level_config.get("breakthrough_spiritual_qi_gain", 100),
            "max_blood_qi": level_config.get("breakthrough_blood_qi_gain", 100),
        }

    async def handle_resurrection(self, player: Player) -> bool:
        """处理玩家死亡时的回生丹效果"""
        if not player.has_resurrection_pill:
            return False

        logger.info(f"玩家 {player.user_id} 触发回生丹效果")
        player.has_resurrection_pill = False

        player.lifespan = player.lifespan // 2
        player.experience = player.experience // 2
        player.physical_damage = player.physical_damage // 2
        player.magic_damage = player.magic_damage // 2
        player.physical_defense = player.physical_defense // 2
        player.magic_defense = player.magic_defense // 2
        player.mental_power = player.mental_power // 2
        player.max_spiritual_qi = player.max_spiritual_qi // 2
        player.spiritual_qi = player.max_spiritual_qi // 2
        player.max_blood_qi = player.max_blood_qi // 2
        player.blood_qi = player.max_blood_qi // 2

        self._ensure_non_negative_attributes(player)
        await self.db.update_player(player)
        return True

    def calculate_pill_attribute_effects(self, player: Player) -> dict:
        """计算丹药对属性的影响"""
        effects = player.get_active_pill_effects()
        current_time = int(time.time())
        multipliers = {
            "physical_damage": 1.0,
            "magic_damage": 1.0,
            "physical_defense": 1.0,
            "magic_defense": 1.0,
            "cultivation_speed": 1.0,
        }

        for effect in effects:
            expiry_time = effect.get("expiry_time", 0)
            if expiry_time > 0 and current_time >= expiry_time:
                continue
            if "physical_damage_multiplier" in effect:
                multipliers["physical_damage"] += effect["physical_damage_multiplier"]
            if "magic_damage_multiplier" in effect:
                multipliers["magic_damage"] += effect["magic_damage_multiplier"]
            if "physical_defense_multiplier" in effect:
                multipliers["physical_defense"] += effect["physical_defense_multiplier"]
            if "magic_defense_multiplier" in effect:
                multipliers["magic_defense"] += effect["magic_defense_multiplier"]
            if "cultivation_multiplier" in effect:
                multipliers["cultivation_speed"] += effect["cultivation_multiplier"]

        permanent_gains = player.get_permanent_pill_gains()
        level_key = f"level_{player.level_index}"
        if level_key in permanent_gains:
            level_gains = permanent_gains[level_key]
            if "cultivation_multiplier" in level_gains:
                multipliers["cultivation_speed"] += level_gains["cultivation_multiplier"]

        for key in multipliers:
            multipliers[key] = max(0.0, multipliers[key])

        return multipliers

    def get_breakthrough_modifiers(self, player: Player) -> dict:
        """获取突破时的临时与永久加成信息"""
        effects = player.get_active_pill_effects()
        current_time = int(time.time())
        temp_bonus = 0.0
        has_temp_effects = False

        bonus_groups = {}
        for effect in effects:
            expiry_time = effect.get("expiry_time", 0)
            if expiry_time > 0 and current_time >= expiry_time:
                continue

            subtype = effect.get("subtype", "")
            if subtype in {"breakthrough_boost", "breakthrough_debuff"}:
                pill_name = effect.get("pill_name", "")
                group = "other"
                if any(x in pill_name for x in ["凝神增益丹", "破境增益丹", "渡劫增益丹", "化神增益丹"]):
                    group = "zengyi"
                
                current_bonus = effect.get("breakthrough_bonus", 0)
                if group not in bonus_groups or current_bonus > bonus_groups[group]:
                    bonus_groups[group] = current_bonus

        temp_bonus = sum(bonus_groups.values())
        has_temp_effects = len(bonus_groups) > 0
        temp_bonus = min(temp_bonus, 0.5)

        permanent_multiplier = 1.0
        permanent_gains = player.get_permanent_pill_gains()
        for level_gain in permanent_gains.values():
            permanent_multiplier *= level_gain.get("death_protection_multiplier", 1.0)

        return {
            "temp_bonus": temp_bonus,
            "has_temp_effects": has_temp_effects,
            "permanent_death_multiplier": max(0.0, min(1.0, permanent_multiplier)),
        }

    async def consume_breakthrough_effects(self, player: Player):
        """突破完成后移除相关临时丹药效果"""
        effects = player.get_active_pill_effects()
        remaining_effects = [
            effect for effect in effects
            if effect.get("subtype", "") not in {"breakthrough_boost", "breakthrough_debuff"}
        ]

        if len(remaining_effects) != len(effects):
            player.set_active_pill_effects(remaining_effects)
            await self.db.update_player(player)

    async def add_pill_to_inventory(self, player: Player, pill_name: str, count: int = 1, external_transaction: bool = False):
        """添加丹药到背包（修复事务冲突版本）"""
        inventory = player.get_pills_inventory()
        if pill_name in inventory:
            inventory[pill_name] += count
        else:
            inventory[pill_name] = count
        player.set_pills_inventory(inventory)
        
        if not external_transaction:
            await self.db.update_player(player)

    def get_pill_inventory_display(self, player: Player) -> str:
        """获取丹药背包显示文本"""
        inventory = player.get_pills_inventory()
        if not inventory:
            return "你的丹药背包是空的！"

        lines = ["--- 丹药背包 ---"]
        for pill_name, count in inventory.items():
            pill_data = self.get_pill_by_name(pill_name)
            if pill_data:
                rank = pill_data.get("rank", "未知")
                lines.append(f"[{rank}] {pill_name} × {count}")
            else:
                lines.append(f"{pill_name} × {count}")

        lines.append("-" * 20)
        return "\n".join(lines)

    def _apply_periodic_effects(self, player: Player, effect: dict, current_time: int) -> bool:
        """根据时间自动结算持续恢复/扣减"""
        expiry_time = effect.get("expiry_time", 0)
        tick_limit = min(current_time, expiry_time) if expiry_time > 0 else current_time
        last_tick = effect.get("last_tick_time", effect.get("start_time", current_time))

        if tick_limit <= last_tick:
            return False

        elapsed_seconds = tick_limit - last_tick
        minutes = elapsed_seconds // 60
        if minutes <= 0:
            return False

        effect["last_tick_time"] = last_tick + minutes * 60
        changed = False

        if "lifespan_cost_per_minute" in effect:
            total_cost = effect["lifespan_cost_per_minute"] * minutes
            player.lifespan = max(0, player.lifespan - total_cost)
            changed = True

        if "lifespan_regen_per_minute" in effect:
            total_regen = effect["lifespan_regen_per_minute"] * minutes
            player.lifespan += total_regen
            changed = True

        if "spiritual_qi_regen_per_minute" in effect:
            total_qi = effect["spiritual_qi_regen_per_minute"] * minutes
            player.spiritual_qi = min(player.max_spiritual_qi, player.spiritual_qi + total_qi)
            changed = True

        if "blood_qi_regen_per_minute" in effect:
            total_blood = effect["blood_qi_regen_per_minute"] * minutes
            player.blood_qi = min(player.max_blood_qi, player.blood_qi + total_blood)
            changed = True

        if "blood_qi_cost_per_minute" in effect:
            total_cost = effect["blood_qi_cost_per_minute"] * minutes
            player.blood_qi = max(0, player.blood_qi - total_cost)
            changed = True

        if changed:
            self._ensure_non_negative_attributes(player)

        return changed

    def _reset_permanent_pill_effects(self, player: Player) -> bool:
        """清空永久丹药增益并回退属性"""
        permanent_gains = player.get_permanent_pill_gains()
        if not permanent_gains:
            return False

        attr_keys = [
            "physical_damage",
            "magic_damage",
            "physical_defense",
            "magic_defense",
            "mental_power",
            "lifespan",
            "max_spiritual_qi",
            "max_blood_qi",
        ]

        changed = False
        for gain in permanent_gains.values():
            for attr_key in attr_keys:
                value = gain.get(attr_key, 0)
                if value:
                    delta = int(value)
                    setattr(player, attr_key, getattr(player, attr_key) - delta)
                    changed = True

            if "cultivation_multiplier" in gain:
                gain["cultivation_multiplier"] = 0
            if "death_protection_multiplier" in gain:
                gain["death_protection_multiplier"] = 1.0

        player.set_permanent_pill_gains({})
        return changed