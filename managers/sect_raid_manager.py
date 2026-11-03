# managers/sect_raid_manager.py
"""宗门秘境（v3.33.0 新玩法）：宗门协力 Boss 召唤战

- 宗主/长老消耗 2000 宗门资材召唤秘境妖王（HP 随宗门人数成长），存续 12 小时
- 成员各自 /讨伐宗门Boss（每日 2 次），伤害累计扣减全服共享 HP 池（原子数值键，钳 0）
- HP 归零的斩杀者触发全宗结算：全员灵石+修为，伤害榜 Top1/2/3 追加洗练石
- 到期未斩杀 → 妖王遁走，资材不退
- 状态全部 system_config 键（sectboss_active_{sid} / sectboss_hp_{sid} /
  sectboss_dmg_{sid}_{uid}），无新表；数值键原子扣血天然防并发双杀
"""

import json
import time
from typing import Tuple, Optional

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["SectRaidManager"]


class SectRaidManager:
    """宗门秘境：全宗同心，共讨妖王"""

    SUMMON_COST = 2000       # 宗门资材
    DURATION = 12 * 3600     # 存续 12 小时
    DAILY_HUNTS = 2          # 每人每日讨伐次数

    RAID_NAMES = ["沉渊古蛟", "焚天炎魁", "九幽冥将", "噬界巨螯", "堕星魔犀"]

    def __init__(self, db: DataBase, config_manager=None, storage_ring_mgr=None):
        self.db = db
        self.config_manager = config_manager
        self.storage_ring_mgr = storage_ring_mgr

    # ===== 键位 =====

    @staticmethod
    def _active_key(sect_id: int) -> str:
        return f"sectboss_active_{sect_id}"

    @staticmethod
    def _hp_key(sect_id: int) -> str:
        return f"sectboss_hp_{sect_id}"

    @staticmethod
    def _dmg_prefix(sect_id: int) -> str:
        return f"sectboss_dmg_{sect_id}_"

    @staticmethod
    def _cnt_key(uid: str) -> str:
        import time
        return f"sectboss_cnt_{uid}_{time.strftime('%Y%m%d')}"

    # ===== 状态 =====

    async def get_active(self, sect_id: int) -> Optional[dict]:
        raw = await self.db.ext.get_system_config(self._active_key(sect_id))
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None

    # ===== 召唤 =====

    async def summon(self, player: Player, sect) -> Tuple[bool, str]:
        """宗主/长老消耗资材召唤秘境妖王"""
        sect_id = sect.sect_id
        if await self.get_active(sect_id):
            return False, "❌ 本宗秘境妖王已在肆虐，先讨伐它！/讨伐宗门Boss"
        if int(getattr(sect, "sect_materials", 0) or 0) < self.SUMMON_COST:
            return False, f"❌ 宗门资材不足！召唤需要 {self.SUMMON_COST:,} 资材（/宗门捐献 积累）。"

        # CAS 抢占召唤权（两位长老并发召唤只成功一次）
        rng = __import__("random")
        name = rng.choice(self.RAID_NAMES)
        members = await self.db.ext.get_sect_members(sect_id)
        member_count = max(1, len(members))
        max_hp = 40000 + 25000 * member_count
        state = {"name": name, "max_hp": max_hp, "end_ts": int(time.time()) + self.DURATION}
        claimed = await self.db.ext.syscfg_cas(
            self._active_key(sect_id), json.dumps(state, ensure_ascii=False), None
        )
        if not claimed:
            return False, "❌ 妖王已被其他宗门管理者抢先召唤！"
        await self.db.ext.update_sect_materials(sect_id, self.SUMMON_COST, 2)

        await self.db.ext.set_system_config(self._hp_key(sect_id), str(max_hp))
        return True, (
            f"🐉【宗门秘境】开启！\n"
            "━━━━━━━━━━━━━━━\n"
            f"妖王：【{name}】降世！\n"
            f"❤️ 血量：{max_hp:,}（随本宗 {member_count} 位修士规模成长）\n"
            f"⏳ 存续：12 小时（逾期妖王遁走，资材不退）\n"
            f"🏛️ 消耗宗门资材：{self.SUMMON_COST:,}\n"
            "━━━━━━━━━━━━━━━\n"
            f"💡 全宗成员 /讨伐宗门Boss（每日{self.DAILY_HUNTS}次），血量归零全宗发奖！"
        )

    # ===== 讨伐 =====

    async def challenge(self, player: Player, sect_id: int) -> Tuple[bool, str]:
        """成员讨伐妖王：战斗结算 → 原子扣血 → 斩杀结算"""
        uid = player.user_id
        state = await self.get_active(sect_id)
        if not state:
            return False, "❌ 本宗当前没有秘境妖王。请宗主/长老 /召唤宗门Boss。", False
        if time.time() > int(state.get("end_ts", 0)):
            # 逾期清理
            await self.db.ext.delete_system_config(self._active_key(sect_id))
            await self.db.ext.delete_system_config(self._hp_key(sect_id))
            return False, "⌛ 妖王已遁走（本宗未能及时斩杀）。宗主可再次召唤。", False

        if not await self.db.ext.syscfg_claim_slot(self._cnt_key(uid), self.DAILY_HUNTS):
            return False, f"❌ 今日讨伐次数已用尽（每日 {self.DAILY_HUNTS} 次），明日再战。", False

        # 战斗（与镇妖塔同源）
        try:
            from .combat_manager import CombatManager, CombatStats
            from ..core import EquipmentManager
            cm = CombatManager()
        except Exception as e:
            logger.error(f"[宗门秘境] 加载战斗组件失败: {e}")
            await self.db.ext.syscfg_adjust_number(self._cnt_key(uid), -1)
            return False, "❌ 秘境暂时关闭，请稍后再试。", False

        hp, mp = cm.calculate_hp_mp(player.experience)
        atk = cm.calculate_atk(
            player.experience, player.atkpractice, 0,
            player.physical_damage, player.magic_damage, player.cultivation_type
        )
        effects = {}
        try:
            effects = EquipmentManager(self.db, self.config_manager).get_combat_effects(player)
        except Exception:
            effects = {}
        element = cm.get_element_from_name(player.main_technique) or cm.get_element_from_name(player.weapon)

        # 妖王属性随血池规模成长
        max_hp = int(state.get("max_hp", 100000))
        boss_stats = CombatStats(
            user_id=str(sect_id), name=f"秘境妖王·{state['name']}",
            hp=max_hp, max_hp=max_hp, mp=0, max_mp=0,
            atk=int(120 * (1 + max_hp / 300000)), defense=60, crit_rate=12,
        )
        p_stats = CombatStats(
            user_id=uid, name=player.user_name or f"道友{uid[:6]}",
            hp=hp, max_hp=hp, mp=mp, max_mp=mp, atk=atk,
            exp=player.experience, effects=effects, element=element,
        )
        result = cm.player_vs_boss(p_stats, boss_stats)
        raw_damage = int(result.get("damage_to_boss", 0) or 0)
        if raw_damage <= 0:
            raw_damage = max(1, int(p_stats.atk * 2))

        # 原子扣血池（钳 0）：实际生效伤害 = 扣减前后差值
        before = await self.db.ext.syscfg_get_number(self._hp_key(sect_id))
        after = await self.db.ext.syscfg_adjust_number(self._hp_key(sect_id), -raw_damage)
        applied = min(raw_damage, before)

        # 记录个人伤害（原子累加）
        my_total = await self.db.ext.syscfg_adjust_number(self._dmg_prefix(sect_id) + uid, applied)

        lines = [
            f"⚔️【讨伐秘境妖王】{state['name']}",
            "━━━━━━━━━━━━━━━",
            f"💥 你造成伤害：{applied:,}",
            f"🧮 你的累计伤害：{my_total:,}",
            f"❤️ 妖王剩余血量：{max(0, after):,} / {max_hp:,}",
        ]

        # 斩杀判定：血池归零且此前未归零（并发下只有一个协程看到 after==0 且 before>0）
        if after <= 0 and before > 0:
            settle_msg = await self._settle(sect_id, state, uid)
            lines.append(settle_msg)
            return True, "\n".join(lines), True
        lines.append("💡 血量归零时触发全宗结算，Top 伤害追加洗练石！")
        return True, "\n".join(lines), False

    async def _settle(self, sect_id: int, state: dict, killer_id: str) -> str:
        """斩杀结算：全宗发奖 + 伤害榜 Top3 追加"""
        # 抢占结算权：CAS 把 active 状态清掉
        claimed = await self.db.ext.syscfg_cas(self._active_key(sect_id), "", json.dumps(state, ensure_ascii=False))
        if not claimed:
            return ""
        await self.db.ext.delete_system_config(self._hp_key(sect_id))

        SETTLE_GOLD, SETTLE_EXP = 3000, 8000
        try:
            await self.db.conn.execute(
                "UPDATE players SET gold = gold + ?, experience = experience + ? WHERE sect_id = ?",
                (SETTLE_GOLD, SETTLE_EXP, sect_id)
            )
            await self.db.conn.commit()
        except Exception as e:
            logger.error(f"[宗门秘境] 全宗发奖失败: {e}")

        # 伤害榜
        ranking = []
        try:
            async with self.db.conn.execute(
                "SELECT key, value FROM system_config WHERE key LIKE ?", (self._dmg_prefix(sect_id) + "%",)
            ) as cursor:
                rows = await cursor.fetchall()
            for key, value in rows:
                uid = key[len(self._dmg_prefix(sect_id)):]
                try:
                    ranking.append((uid, int(value)))
                except (TypeError, ValueError):
                    continue
            ranking.sort(key=lambda x: -x[1])
        except Exception as e:
            logger.error(f"[宗门秘境] 伤害榜读取失败: {e}")

        # 清理全部个人伤害键（防泄漏；Top3 奖励发放后逐个删除）
        cleaned = set()
        for uid_key, _ in ranking:
            if uid_key not in cleaned:
                await self.db.ext.delete_system_config(self._dmg_prefix(sect_id) + uid_key)
                cleaned.add(uid_key)

        extra_lines = []
        medals = {0: ("🥇", 2, 5000), 1: ("🥈", 1, 3000), 2: ("🥉", 1, 2000)}
        for i, (uid, dmg) in enumerate(ranking[:3]):
            _, stones, gold = medals[i]
            if self.storage_ring_mgr:
                p = await self.db.get_player_by_id(uid)
                if p:
                    await self.storage_ring_mgr.store_item(p, "洗练石", stones, silent=True)
            await self.db.add_player_gold(uid, gold)
            p = await self.db.get_player_by_id(uid)
            name = (p.user_name if p and p.user_name else uid[:8])
            extra_lines.append(f"{medals[i][0]} {name}：伤害 {dmg:,} → 洗练石x{stones} + {gold:,} 灵石")

        lines = [
            "━━━━━━━━━━━━━━━",
            f"🎉 妖王【{state['name']}】被斩杀！（终结者：<{killer_id[:8]}>）",
            f"🏆 全宗每位修士获得：{SETTLE_GOLD:,} 灵石 + {SETTLE_EXP:,} 修为",
        ]
        lines.extend(extra_lines)
        lines.append("💡 宗主可再次 /召唤宗门Boss 开启下一场")
        return "\n".join(lines)

    async def get_panel(self, player, sect) -> str:
        sect_id = sect.sect_id
        state = await self.get_active(sect_id)
        lines = ["🐉【宗门秘境】", "━━━━━━━━━━━━━━━"]
        if not state:
            cur = await self.db.ext.get_sect_by_id(sect_id)
            lines.append("🌫 本宗秘境风平浪静。")
            lines.append(f"🏛️ 宗门资材：{getattr(cur, 'sect_materials', 0):,}")
            lines.append("💡 宗主/长老 /召唤宗门Boss（消耗 2000 资材，12 小时存续）")
            lines.append("💡 /讨伐宗门Boss 全宗协力讨伐，斩杀后全宗发奖！")
        else:
            hp = await self.db.ext.syscfg_get_number(self._hp_key(sect_id))
            max_hp = int(state.get("max_hp", 1))
            remain = max(0, int(state.get("end_ts", 0)) - int(time.time()))
            pct = min(100.0, hp * 100.0 / max(1, max_hp))
            filled = int(pct // 5)
            bar = "█" * filled + "░" * (20 - filled)
            lines.append(f"👹 妖王：【{state['name']}】")
            lines.append(f"❤️ 血量 [{bar}] {pct:.1f}%（{max(0, hp):,}/{max_hp:,}）")
            lines.append(f"⏳ 剩余：{remain // 3600} 小时 {(remain % 3600) // 60} 分")
            lines.append(f"⚔️ /讨伐宗门Boss（每日{self.DAILY_HUNTS}次）")
        lines.append("━━━━━━━━━━━━━━━")
        return "\n".join(lines)
