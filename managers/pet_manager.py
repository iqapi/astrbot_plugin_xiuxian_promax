# managers/pet_manager.py
import random
import time
from typing import Tuple, Dict, Optional
from ..data import DataBase
from ..models import Player

class PetManager:
    """灵兽管理器"""
    
    # 灵兽种类库
    PET_TYPES = {
        "火灵狐": {"desc": "攻击时附带灼烧，增加主人暴击率", "attr": "crit_rate", "val": 10},
        "冰晶兽": {"desc": "拥有极寒护盾，增加主人防御力", "attr": "defense", "val": 50},
        "噬金鼠": {"desc": "嗅觉敏锐，增加日常灵石掉落", "attr": "gold_bonus", "val": 0.1},
        "青龙幼崽": {"desc": "神兽血脉，全面增加主人属性", "attr": "all", "val": 20}
    }

    def __init__(self, db: DataBase, storage_ring_mgr=None):
        self.db = db
        # v3.40.2 修复：探险收取的掉落发放需要储物戒（此前未注入，命中掉落概率即 AttributeError，
        # 导致 8 小时探险成果丢失）
        self.storage_ring_mgr = storage_ring_mgr

    async def get_pet(self, user_id: str) -> Optional[Dict]:
        """获取玩家灵兽信息"""
        async with self.db.conn.execute("SELECT * FROM player_pets WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def adopt_pet(self, player: Player, pet_name: str) -> Tuple[bool, str]:
        """孵化/捕捉灵兽"""
        if pet_name not in self.PET_TYPES:
            return False, f"❌ 未知的灵兽种类！可用灵兽：{', '.join(self.PET_TYPES.keys())}"

        cost = 100000
        if player.gold < cost:
            return False, f"❌ 捕捉【{pet_name}】需要 {cost:,} 灵石。"

        # v3.25.5 修复落库顺序：先 INSERT 占坑（UNIQUE 冲突→友好提示已有灵兽），
        # 再条件原子扣款（防透支）；原顺序先扣款后 INSERT，并发双契约时第二条
        # 撞 UNIQUE 直接抛异常，10 万灵石已扣而宠物没有
        try:
            await self.db.conn.execute(
                "INSERT INTO player_pets (user_id, pet_name, pet_type, level, exp) VALUES (?, ?, ?, 1, 0)",
                (player.user_id, pet_name, pet_name)
            )
            await self.db.conn.commit()
        except Exception as e:
            if "UNIQUE" in str(e):
                return False, "❌ 你已经契约了灵兽，无法携带第二只。\n💡 如果需要更换，请先使用 /放生灵兽 或 /吞噬灵兽。"
            raise

        cursor = await self.db.conn.execute(
            "UPDATE players SET gold = gold - ? WHERE user_id = ? AND gold >= ?",
            (cost, player.user_id, cost)
        )
        await self.db.conn.commit()
        if cursor.rowcount == 0:
            # 扣款失败：释放占坑
            await self.db.conn.execute("DELETE FROM player_pets WHERE user_id = ?", (player.user_id,))
            await self.db.conn.commit()
            return False, f"❌ 灵石不足！捕捉【{pet_name}】需要 {cost:,} 灵石。"

        pet_info = self.PET_TYPES[pet_name]
        return True, f"🎉 恭喜！你成功契约了【{pet_name}】！\n特性：{pet_info['desc']}"

    async def release_pet(self, player: Player) -> Tuple[bool, str]:
        """放生灵兽"""
        pet = await self.get_pet(player.user_id)
        if not pet:
            return False, "❌ 你当前没有携带灵兽。"
        
        pet_name = pet["pet_name"]
        await self.db.conn.execute("DELETE FROM player_pets WHERE user_id = ?", (player.user_id,))
        await self.db.conn.commit()
        
        return True, f"🕊️ 你已解开契约，将【{pet_name}】放归山林。\n当前灵兽栏已空，可以契约新灵兽了。"

    async def devour_pet(self, player: Player) -> Tuple[bool, str]:
        """吞噬灵兽（返还少量资源）"""
        pet = await self.get_pet(player.user_id)
        if not pet:
            return False, "❌ 你当前没有携带灵兽。"
            
        pet_name = pet["pet_name"]
        level = pet["level"]

        # 返还公式：每级返还 500 灵石，250 修为（相比10万的契约费，吞噬是巨亏的，防止刷资源）
        refund_gold = level * 500
        refund_exp = level * 250

        # v3.25.5 修复落库顺序：先原子发返还，后删灵兽（连接为 autocommit，
        # 原 DELETE 先行生效、若随后 update_player 抛异常则灵兽没了返还没到账）；
        # 且改用原子接口，不再整行覆写玩家快照
        await self.db.add_player_gold(player.user_id, refund_gold)
        await self.db.add_player_exp(player.user_id, refund_exp)
        await self.db.conn.execute("DELETE FROM player_pets WHERE user_id = ?", (player.user_id,))
        await self.db.conn.commit()

        return True, f"🩸 你运转魔功，强行吞噬了【{pet_name}】！\n炼化获得：{refund_gold:,} 灵石，{refund_exp:,} 修为。\n（灵兽栏已空，可契约新灵兽）"

    async def feed_pet(self, player: Player, cost_mult: float = 1.0) -> Tuple[bool, str]:
        """喂养灵兽（消耗灵石和修为；cost_mult 为外部加成折扣）"""
        pet = await self.get_pet(player.user_id)
        if not pet:
            return False, "❌ 你还没有灵兽，请先捕捉。"

        if pet["level"] >= 50:
            return False, "❌ 你的灵兽已经满级（Lv.50）。"

        cost_gold = int(pet["level"] * 1000 * cost_mult)
        cost_exp = int(pet["level"] * 500 * cost_mult)
        
        if player.gold < cost_gold:
            return False, f"❌ 灵石不足，喂养需要 {cost_gold:,} 灵石。"
        if player.experience < cost_exp:
            return False, f"❌ 修为不足，喂养需要 {cost_exp:,} 修为（灵兽会吞噬你的修为）。"
            
        # v3.25.5：条件原子扣款（不再整行覆写快照）
        cursor = await self.db.conn.execute(
            "UPDATE players SET gold = gold - ? WHERE user_id = ? AND gold >= ?",
            (cost_gold, player.user_id, cost_gold)
        )
        if cursor.rowcount == 0:
            return False, f"❌ 灵石不足，喂养需要 {cost_gold:,} 灵石。"
        await self.db.add_player_exp(player.user_id, -cost_exp)

        # 增加经验，每100经验升1级
        new_exp = pet["exp"] + 100
        new_level = pet["level"]
        if new_exp >= new_level * 500: # 升级所需经验
            new_level += 1
            new_exp = 0

        await self.db.conn.execute(
            "UPDATE player_pets SET level = ?, exp = ? WHERE user_id = ?",
            (new_level, new_exp, player.user_id)
        )
        await self.db.conn.commit()
        
        return True, f"✨ 喂养成功！灵兽当前等级：Lv.{new_level} (经验：{new_exp}/{new_level*500})"

    # ===== v3.26.0 灵兽探险 =====

    EXPEDITION_HOURS = 8       # 探险时长
    EXP_KEY = "petexp_{uid}"   # 探险状态键（JSON）

    # 探险地点：收益侧重不同（gold/exp/item 概率）
    EXP_DESTS = {
        "万妖山脉": {"gold": (2000, 6000), "exp": (3000, 9000), "item": ("洗练石", 0.10)},
        "灵矿深处": {"gold": (6000, 15000), "exp": (1500, 4000), "item": ("强化石", 0.15)},
        "古修洞府": {"gold": (3000, 8000), "exp": (3000, 8000), "item": ("空间石", 0.08)},
        "灵草谷": {"gold": (2500, 7000), "exp": (2500, 7000), "item": ("引雷符", 0.12)},
        "天外陨星": {"gold": (1000, 4000), "exp": (2000, 6000), "item": ("护府令", 0.05)},
    }

    def _exp_key(self, uid: str) -> str:
        return self.EXP_KEY.format(uid=uid)

    async def get_expedition(self, uid: str) -> Optional[Dict]:
        """获取进行中/待收取的探险状态"""
        import json as _json
        raw = await self.db.ext.get_system_config(self._exp_key(uid))
        if not raw:
            return None
        try:
            data = _json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    async def start_expedition(self, player: Player, dest: str = "") -> Tuple[bool, str]:
        """派遣灵兽外出探险（8小时，随机或指定地点）"""
        import json as _json
        import random as _random

        pet = await self.get_pet(player.user_id)
        if not pet:
            return False, "❌ 你还没有灵兽，先 /孵化灵兽 <名> 契约一只。"

        existing = await self.get_expedition(player.user_id)
        now = int(time.time())
        if existing:
            if now < int(existing.get("end_ts", 0)):
                remain = int(existing["end_ts"]) - now
                return False, (
                    f"❌ 【{existing['pet_name']}】正在【{existing['dest']}】探险，"
                    f"还需 {remain // 3600} 小时 {(remain % 3600) // 60} 分钟。\n💡 /灵兽归来 到期收取"
                )
            return False, "⚠️ 上一次探险已结束，先 /灵兽归来 收取成果再派遣！"

        if dest and dest not in self.EXP_DESTS:
            return False, "❌ 未知探险地点。可选：" + " / ".join(self.EXP_DESTS.keys())
        dest = dest or _random.choice(list(self.EXP_DESTS.keys()))

        state = {
            "pet_name": pet["pet_name"],
            "pet_type": pet["pet_type"],
            "pet_level": pet["level"],
            "dest": dest,
            "start_ts": now,
            "end_ts": now + self.EXPEDITION_HOURS * 3600,
        }
        await self.db.ext.set_system_config(
            self._exp_key(player.user_id), _json.dumps(state, ensure_ascii=False)
        )
        return True, (
            f"🐾【灵兽探险】出发！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"灵兽：【{pet['pet_name']}】(Lv.{pet['level']})\n"
            f"目的地：【{dest}】\n"
            f"时长：{self.EXPEDITION_HOURS} 小时\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 到期后发送 /灵兽归来 收取收获（不同地点收益侧重不同）"
        )

    async def collect_expedition(self, player: Player) -> Tuple[bool, str]:
        """收取探险成果：灵石+修为（随宠物等级成长）+ 灵兽经验 + 概率物品"""
        import random as _random

        state = await self.get_expedition(player.user_id)
        if not state:
            return False, "❌ 你的灵兽没有在外探险。先 /灵兽派遣 出发！"
        now = int(time.time())
        if now < int(state.get("end_ts", 0)):
            remain = int(state["end_ts"]) - now
            return False, f"⏳ 【{state['pet_name']}】还在【{state['dest']}】游历，还需 {remain // 3600} 小时 {(remain % 3600) // 60} 分钟。"

        # 清理状态（一次性）
        await self.db.ext.delete_system_config(self._exp_key(player.user_id))

        dest_cfg = self.EXP_DESTS.get(state["dest"], self.EXP_DESTS["万妖山脉"])
        level = int(state.get("pet_level", 1))
        lv_mult = 1.0 + (level - 1) * 0.15  # 灵兽等级提升收获

        gold = int(_random.randint(*dest_cfg["gold"]) * lv_mult)
        exp = int(_random.randint(*dest_cfg["exp"]) * lv_mult)
        await self.db.add_player_gold(player.user_id, gold)
        await self.db.add_player_exp(player.user_id, exp)

        # 灵兽经验 +100（与喂养一致，就地升级）
        pet = await self.get_pet(player.user_id)
        pet_note = ""
        if pet and pet["pet_name"] == state.get("pet_name"):
            new_exp = pet["exp"] + 100
            new_level = pet["level"]
            if new_exp >= new_level * 500:
                new_level += 1
                new_exp = 0
            await self.db.conn.execute(
                "UPDATE player_pets SET level = ?, exp = ? WHERE user_id = ?",
                (new_level, new_exp, player.user_id)
            )
            await self.db.conn.commit()
            if new_level > pet["level"]:
                pet_note = f"\n🎉 灵兽历练有成，升级至 Lv.{new_level}！"
            else:
                pet_note = f"\n🐾 灵兽经验 +100（{new_exp}/{new_level*500}）"

        lines = [
            f"🐾【灵兽归来】{state['pet_name']} 自【{state['dest']}】满载而归！",
            "━━━━━━━━━━━━━━━",
            f"💰 灵石：+{gold:,}",
            f"📈 修为：+{exp:,}",
        ]
        if pet_note:
            lines.append(pet_note.strip())
        # 概率物品
        item_name, chance = dest_cfg["item"]
        ring = getattr(self, "storage_ring_mgr", None)
        if _random.random() < chance and ring:
            ok, _ = await ring.store_item(player, item_name, 1, silent=True)
            if ok:
                lines.append(f"🎁 意外收获：【{item_name}】x1（已存入储物戒）")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("💡 /灵兽派遣 可再次出发")
        return True, "\n".join(lines)

    def get_pet_combat_effects(self, pet: Optional[Dict]) -> dict:
        """获取灵兽提供的战斗特效"""
        if not pet:
            return {}
            
        pet_info = self.PET_TYPES.get(pet["pet_type"])
        if not pet_info:
            return {}
            
        level_mult = pet["level"] * 0.1
        base_val = pet_info["val"] * level_mult
        
        effects = {}
        if pet_info["attr"] == "crit_rate":
            effects["crit_rate"] = base_val
        elif pet_info["attr"] == "defense":
            effects["counter_damage"] = base_val / 5  # 转化为反伤
        elif pet_info["attr"] == "all":
            effects["crit_rate"] = base_val
            effects["lifesteal"] = base_val / 2
            
        return effects

    async def pet_coop_attack(self, pet: Optional[Dict], user_id: str = None) -> Tuple[bool, str, int]:
        """灵兽协战判定（每回合触发）；灵汐仙灵加成协战概率"""
        if not pet:
            return False, "", 0

        # 基础触发概率 20% + 等级加成 + 仙灵加成
        trigger_rate = 0.2 + (pet["level"] * 0.01)
        if user_id:
            try:
                from .social_manager import SocialManager
                comp_bonus = await SocialManager(self.db).companion_bonus_async(user_id, "pet")
                if comp_bonus > 0:
                    trigger_rate += comp_bonus * 0.5  # +5%起
            except Exception:
                pass
        
        if random.random() < trigger_rate:
            # 灵兽伤害基于主人境界（假设与玩家等级相关）
            damage_mult = pet["level"] * 0.5
            return True, f"🐾 【{pet['pet_name']}】扑向敌人，发起协同攻击！", damage_mult
            
        return False, "", 0