# managers/reincarnation_manager.py
import json
import math
from typing import Tuple
from ..data import DataBase
from ..models import Player

class ReincarnationManager:
    """飞升转生管理器 - 支持传家宝封印与仙缘商店"""
    
    def __init__(self, db: DataBase, config_manager, storage_ring_mgr):
        self.db = db
        self.config_manager = config_manager
        self.storage_ring_mgr = storage_ring_mgr

    async def try_reincarnate(self, player: Player, heirloom_name: str = "") -> tuple[bool, str]:
        """尝试飞升转生
        v3.25.5 幂等锁：并发双开飞升会双发轮回玉（原子累加），先 CAS 抢占仪式权"""
        lock_key = f"reinc_lock_{player.user_id}"
        if not await self.db.ext.syscfg_cas(lock_key, "1", None):
            return False, "❌ 飞升仪式正在进行中，请勿重复操作。"
        try:
            return await self._do_reincarnate(player, heirloom_name)
        finally:
            await self.db.ext.delete_system_config(lock_key)

    async def _do_reincarnate(self, player: Player, heirloom_name: str = "") -> tuple[bool, str]:
        """执行飞升转生（由 try_reincarnate 持锁调用）"""
        level_data = self.config_manager.get_level_data(player.cultivation_type)
        max_level = len(level_data) - 1
        
        if player.level_index < max_level:
            return False, "❌ 你的境界尚未达到巅峰，无法飞升。"
            
        # 解析并扣除传家宝
        heirloom_data = {}
        if heirloom_name and heirloom_name.strip():
            heirloom_name = heirloom_name.strip()
            items = player.get_storage_ring_items()
            
            if heirloom_name not in items or items[heirloom_name] <= 0:
                return False, f"❌ 你的储物戒中并没有【{heirloom_name}】，无法将其封印为传家宝。"
            
            items[heirloom_name] -= 1
            if items[heirloom_name] <= 0: 
                del items[heirloom_name]
            player.set_storage_ring_items(items)
            heirloom_data = {"name": heirloom_name, "sealed": True}
            
        # 计算仙缘点
        base_points = 100 + int(math.log10(max(player.experience, 1)) * 10)
        bonus_points = player.reincarnation_count * 50
        earned_points = base_points + bonus_points
        old_level_name = level_data[player.level_index]["level_name"]
        lifetime_exp = player.experience  # v3.19.0 轮回周目：按前世总修为发放轮回玉

        # 轮回玉：前世修为的 1%（异常安全）
        jade_msg = ""
        try:
            from .samsara_manager import SamsaraManager
            jade = await SamsaraManager(self.db).grant_jade(player.user_id, lifetime_exp)
            if jade > 0:
                jade_msg = f"\n🎐 前世修为凝结为【轮回玉】x{jade}，/轮回宝阁 可兑换周目珍宝。"
        except Exception:
            pass
        
        # 读取旧有的永久加成（仙缘商店买的、传家宝等）
        try:
            bonus_data = json.loads(player.permanent_bonus) if player.permanent_bonus else {}
        except Exception:
            bonus_data = {}
        
        # 写入传家宝封印
        if heirloom_data:
            bonus_data["heirloom"] = heirloom_data
        else:
            bonus_data.pop("heirloom", None)
        
        # 执行飞升重置
        player.level_index = 0
        player.experience = 0
        player.gold = 1000
        player.hp = 0
        player.mp = 0
        player.atk = 0
        player.atkpractice = 0
        player.spiritual_qi = 100
        player.max_spiritual_qi = 1000
        player.blood_qi = 0
        player.max_blood_qi = 0
        player.magic_damage = 10
        player.physical_damage = 10
        player.magic_defense = 5
        player.physical_defense = 5
        player.mental_power = 100
        
        player.weapon = ""
        player.armor = ""
        player.main_technique = ""
        player.set_techniques_list([])
        
        player.set_storage_ring_items({})
        player.set_pills_inventory({})
        player.active_pill_effects = "[]"
        player.permanent_pill_gains = "{}"
        
        player.tutorial_step = 0
        player.reincarnation_count += 1
        player.fate_points += earned_points

        # 保存永久加成（含传家宝）
        player.permanent_bonus = json.dumps(bonus_data, ensure_ascii=False)
        await self.db.update_player(player)

        # 强制清理附属产业
        await self.db.conn.execute("DELETE FROM blessed_lands WHERE user_id = ?", (player.user_id,))
        await self.db.conn.execute("DELETE FROM spirit_farms WHERE user_id = ?", (player.user_id,))
        await self.db.conn.execute("UPDATE spirit_eyes SET owner_id = NULL, owner_name = NULL, claim_time = NULL WHERE owner_id = ?", (player.user_id,))
        await self.db.conn.commit()
        
        seal_msg = f"\n🔒 你的【{heirloom_name}】已被封印为传家宝，静待重见天日。" if heirloom_name else ""
        
        return True, (
            f"✨ 飞升成功！✨\n"
            f"━━━━━━━━━━━━━━━\n"
            f"你已从【{old_level_name}】破碎虚空，飞升上界！\n"
            f"境界与装备已全部化为虚无，洞天灵田也随风消散...\n"
            f"但你的修仙记忆化为了【仙缘】。{seal_msg}\n"
            f"获得仙缘点：{earned_points}\n"
            f"转生次数：{player.reincarnation_count}\n"
            f"当前仙缘点：{player.fate_points}"
            f"{jade_msg}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 使用 `/仙缘商店` 可兑换永久加成，重新踏上仙途吧！"
        )

    async def unseal_heirloom(self, player: Player) -> tuple[bool, str]:
        """解封传家宝"""
        try:
            bonus_data = json.loads(player.permanent_bonus) if player.permanent_bonus else {}
        except Exception:
            bonus_data = {}
            
        heirloom = bonus_data.get("heirloom")
        if not heirloom or not heirloom.get("sealed"):
            return False, "❌ 你没有处于封印状态的传家宝。"

        # 限制解封境界（筑基期 level_index >= 3）
        if player.level_index < 3:
            return False, "❌ 解封传家宝需要至少达到【筑基期】！请继续努力修行。"
            
        heirloom_name = heirloom.get("name")
        success, msg = await self.storage_ring_mgr.store_item(player, heirloom_name, 1, silent=True)
        if not success:
            return False, f"❌ 解封失败：你的储物戒已满或无法存入。\n{msg}"
            
        bonus_data.pop("heirloom", None)
        player.permanent_bonus = json.dumps(bonus_data, ensure_ascii=False)
        # v3.25.5：只写受影响字段，不再整行覆写并发变更
        await self.db.update_player_fields(player.user_id, permanent_bonus=player.permanent_bonus)

        return True, f"✨ 传家宝解封成功！【{heirloom_name}】已存入你的储物戒。"

    async def buy_fate_shop_item(self, player: Player, item_id: int) -> tuple[bool, str]:
        """仙缘商店兑换
        v3.25.5：仙缘点改条件原子扣款（原快照扣点+整行回写，并发下可双花/丢点）；
        属性提升改定向增量，不再整行覆写"""
        costs = {1: 100, 2: 50, 3: 500}
        if item_id not in costs:
            return False, "❌ 无效的商品编号。"
        cost = costs[item_id]

        cursor = await self.db.conn.execute(
            "UPDATE players SET fate_points = fate_points - ? WHERE user_id = ? AND fate_points >= ?",
            (cost, player.user_id, cost)
        )
        await self.db.conn.commit()
        if cursor.rowcount == 0:
            return False, f"❌ 仙缘点不足，需要 {cost} 点。"
        player.fate_points = max(0, player.fate_points - cost)

        try:
            bonus_data = json.loads(player.permanent_bonus) if player.permanent_bonus else {}
        except Exception:
            bonus_data = {}

        if item_id == 1:
            # 1. 修炼加速
            current_mult = bonus_data.get("global_cultivation_multiplier", 0.0)
            bonus_data["global_cultivation_multiplier"] = current_mult + 0.1
            msg = "🌟 兑换成功！你的闭关修炼速度永久提升了 10%。"

        elif item_id == 2:
            # 2. 初始灵石
            await self.db.add_player_gold(player.user_id, 10000)
            msg = "💰 兑换成功！你获得了 10,000 灵石。"

        else:
            # 3. 大道馈赠（全属性）：定向增量更新
            await self.db.conn.execute(
                """UPDATE players SET
                       mental_power = mental_power + 100,
                       max_spiritual_qi = max_spiritual_qi + 100,
                       max_blood_qi = max_blood_qi + 100,
                       magic_damage = magic_damage + 20,
                       physical_damage = physical_damage + 20,
                       magic_defense = magic_defense + 10,
                       physical_defense = physical_defense + 10
                   WHERE user_id = ?""",
                (player.user_id,)
            )
            await self.db.conn.commit()
            msg = "✨ 兑换成功！大道之力加身，你的各项基础属性获得了永久提升！"

        player.permanent_bonus = json.dumps(bonus_data, ensure_ascii=False)
        await self.db.update_player_fields(player.user_id, permanent_bonus=player.permanent_bonus)
        return True, f"{msg}\n当前剩余仙缘点：{player.fate_points}"

    # ===== v3.50.0 仙缘突破卷 =====

    BT_CHARGE_COST = 150       # 每张突破卷费用
    BT_CHARGE_BONUS = 0.08     # 每张 +8%
    BT_CHARGE_MAX = 3          # 最多囤 3 张

    async def buy_bt_charge(self, player: Player) -> Tuple[bool, str]:
        """购买仙缘突破卷：条件原子扣仙缘点，permanent_bonus["bt_charges"] 累加"""
        try:
            bonus_data = json.loads(player.permanent_bonus) if player.permanent_bonus else {}
        except Exception:
            bonus_data = {}
        charges = int(bonus_data.get("bt_charges", 0))
        if charges >= self.BT_CHARGE_MAX:
            return False, f"❌ 突破卷已囤满（{charges}/{self.BT_CHARGE_MAX}），先去 /突破 消耗吧！"
        cursor = await self.db.conn.execute(
            "UPDATE players SET fate_points = fate_points - ? WHERE user_id = ? AND fate_points >= ?",
            (self.BT_CHARGE_COST, player.user_id, self.BT_CHARGE_COST)
        )
        await self.db.conn.commit()
        if cursor.rowcount == 0:
            return False, f"❌ 仙缘点不足！每张突破卷需 {self.BT_CHARGE_COST} 点（当前 {player.fate_points}）。"
        player.fate_points = max(0, player.fate_points - self.BT_CHARGE_COST)
        bonus_data["bt_charges"] = charges + 1
        player.permanent_bonus = json.dumps(bonus_data, ensure_ascii=False)
        await self.db.update_player_fields(player.user_id, permanent_bonus=player.permanent_bonus)
        return True, (
            f"📜 仙缘突破卷购买成功！（{charges + 1}/{self.BT_CHARGE_MAX}）\n"
            f"💰 消耗仙缘点 {self.BT_CHARGE_COST}\n"
            f"✨ 下次 /突破 自动消耗一张，成功率 +{int(self.BT_CHARGE_BONUS * 100)}%\n"
            f"💡 可囤 {self.BT_CHARGE_MAX - charges - 1} 张，突破时自动逐张消耗"
        )

    @staticmethod
    def get_bt_charge_bonus(player: Player) -> Tuple[float, int]:
        """读取当前突破卷加成与剩余张数。返回 (加成小数, 张数)"""
        try:
            data = json.loads(player.permanent_bonus) if player.permanent_bonus else {}
            charges = int(data.get("bt_charges", 0))
            return min(charges, 3) * 0.08, charges
        except Exception:
            return 0.0, 0

    @staticmethod
    async def consume_bt_charge(db, player: Player) -> Tuple[float, str]:
        """突破时消耗一张突破卷。返回 (加成, 提示)；无卷返回 (0.0, "")"""
        try:
            data = json.loads(player.permanent_bonus) if player.permanent_bonus else {}
            charges = int(data.get("bt_charges", 0))
            if charges <= 0:
                return 0.0, ""
            data["bt_charges"] = charges - 1
            player.permanent_bonus = json.dumps(data, ensure_ascii=False)
            await db.update_player_fields(player.user_id, permanent_bonus=player.permanent_bonus)
            return 0.08, f"\n📜 仙缘突破卷生效！成功率 +8%（剩余 {charges - 1} 张）"
        except Exception:
            return 0.0, ""

    # ===== v3.31.0 轮回天赋树 =====

    TALENT_MAX = 10
    # 节点 -> (属性字段, 每级加成, 说明)；加成直接落到玩家永久属性（大道馈赠同模式）
    TALENTS = {
        "破煞": ("physical_damage", 25, "物伤 +25/级"),
        "玄芒": ("magic_damage", 25, "法伤 +25/级"),
        "铁骨": ("physical_defense", 15, "物防 +15/级"),
        "御灵": ("magic_defense", 15, "法防 +15/级"),
        "悟道": ("mental_power", 50, "精神力 +50/级"),
    }

    def _load_talents(self, player: Player) -> dict:
        try:
            data = json.loads(player.permanent_bonus) if player.permanent_bonus else {}
        except Exception:
            data = {}
        t = data.get("talents")
        return t if isinstance(t, dict) else {}

    async def get_talents_panel(self, player: Player) -> str:
        talents = self._load_talents(player)
        lines = [
            "🌟【轮回天赋】",
            "━━━━━━━━━━━━━━━",
            f"✨ 仙缘点：{player.fate_points}",
            "（天赋唯有历经飞升者方可参悟，跨周目永久生效）",
            "━━━━━━━━━━━━━━━",
        ]
        for name, (_attr, per, desc) in self.TALENTS.items():
            lv = int(talents.get(name, 0))
            cost = 20 * (lv + 1)
            cur = per * lv
            status = "已臻圆满" if lv >= self.TALENT_MAX else f"下一级 {cost} 点"
            lines.append(f"⚡ {name} Lv.{lv}/{self.TALENT_MAX}（已加成 +{cur}）· {desc} · {status}")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("💡 /轮回悟道 <节点名> 消耗仙缘点参悟（如 /轮回悟道 破煞）")
        lines.append("💡 仙缘点来源：/飞升（按境界）· 出师（+20）")
        return "\n".join(lines)

    async def upgrade_talent(self, player: Player, name: str) -> Tuple[bool, str]:
        """参悟天赋：条件原子扣仙缘点 + 属性原子增量 + 永久落库"""
        if player.reincarnation_count < 1:
            return False, "❌ 轮回天赋唯有经历过飞升的修士方可参悟（需至少转生 1 次）。"
        name = (name or "").strip()
        if name not in self.TALENTS:
            return False, "❌ 未知天赋节点。可选：" + " / ".join(self.TALENTS.keys())

        talents = self._load_talents(player)
        lv = int(talents.get(name, 0))
        if lv >= self.TALENT_MAX:
            return False, f"❌【{name}】已参悟至第 {self.TALENT_MAX} 层，无法再进。"
        cost = 20 * (lv + 1)
        if player.fate_points < cost:
            return False, f"❌ 仙缘点不足！参悟【{name}】第 {lv + 1} 层需 {cost} 点（当前 {player.fate_points}）。"

        # 条件原子扣仙缘点
        cursor = await self.db.conn.execute(
            "UPDATE players SET fate_points = fate_points - ? WHERE user_id = ? AND fate_points >= ?",
            (cost, player.user_id, cost)
        )
        await self.db.conn.commit()
        if cursor.rowcount == 0:
            return False, f"❌ 仙缘点不足！参悟【{name}】第 {lv + 1} 层需 {cost} 点。"
        player.fate_points = max(0, player.fate_points - cost)

        # 属性原子增量
        attr, per, desc = self.TALENTS[name]
        await self.db.conn.execute(
            f"UPDATE players SET {attr} = {attr} + ? WHERE user_id = ?",
            (per, player.user_id)
        )
        await self.db.conn.commit()

        # 天赋等级落库（跨周目永久）
        talents[name] = lv + 1
        try:
            bonus_data = json.loads(player.permanent_bonus) if player.permanent_bonus else {}
        except Exception:
            bonus_data = {}
        bonus_data["talents"] = talents
        player.permanent_bonus = json.dumps(bonus_data, ensure_ascii=False)
        await self.db.update_player_fields(player.user_id, permanent_bonus=player.permanent_bonus)

        return True, (
            f"🌟【{name}】参悟至第 {lv + 1} 层！\n"
            f"📈 {desc}（累计 +{per * (lv + 1)}）\n"
            f"✨ 消耗仙缘点 {cost}（剩余 {player.fate_points}）"
        )