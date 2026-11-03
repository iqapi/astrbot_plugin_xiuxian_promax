# managers/hunt_manager.py
"""除妖系统（v3.27.0 新玩法）：野外随机战斗 PVE 日常

与镇妖塔的分工：塔是"固定阶梯的进度挑战"，除妖是"每日随机的刷怪产出"。
- /除妖 挑战一只按自身境界随机生成的妖兽（每日 5 次）
- 妖兽属性随境界缩放并带随机浮动，同境界收益期望稳定、个体有波动
- 胜：修为/灵石 + 20% 概率物品；败：气血大损 + 保底 10% 修为
- 状态存 system_config 数值键（hunt_cnt_* / hunt_total_*），无新表；奖励全走原子原语
"""

import random
from typing import Tuple

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["HuntManager"]


class HuntManager:
    """除妖卫道：猎杀野外妖兽，换取修炼资粮"""

    DAILY_HUNTS = 5

    # 妖兽名池（随机组合前缀+本体，产出多样感）
    PREFIXES = ["残暴的", "嗜血的", "上古的", "变异的", "癫狂的", "藏锋的", "裹尸布下的"]
    BODIES = ["野猪妖", "黑风蟒", "赤炼蝎", "鬼面枭", "食气貘", "雷翼蝠", "腐骨蜈", "摄魂狸"]

    DROP_POOL = [("引雷符", 0.09), ("洗练石", 0.07), ("强化石", 0.06), ("空间石", 0.02)]

    def __init__(self, db: DataBase, config_manager=None, storage_ring_mgr=None):
        self.db = db
        self.config_manager = config_manager
        self.storage_ring_mgr = storage_ring_mgr

    @staticmethod
    def _cnt_key(uid: str) -> str:
        import time
        return f"hunt_cnt_{uid}_{time.strftime('%Y%m%d')}"

    @staticmethod
    def _total_key(uid: str) -> str:
        return "hunt_total_"

    async def get_total(self, uid: str) -> int:
        """累计除妖数（称号进度用）"""
        return await self.db.ext.syscfg_get_number(self._total_key(uid))

    async def hunt(self, player: Player) -> Tuple[bool, str, bool]:
        """除妖一次。返回 (有战报, 消息, 是否胜利)"""
        uid = player.user_id

        # 每日限次（原子认领）
        if not await self.db.ext.syscfg_claim_slot(self._cnt_key(uid), self.DAILY_HUNTS):
            return False, f"❌ 今日除妖体力已耗尽（每日 {self.DAILY_HUNTS} 次），明日再来。", False

        try:
            from .combat_manager import CombatManager, CombatStats
            from ..core import EquipmentManager
            cm = CombatManager()
        except Exception as e:
            logger.error(f"[除妖] 加载战斗组件失败: {e}")
            await self.db.ext.syscfg_adjust_number(self._cnt_key(uid), -1)  # 回滚次数
            return False, "❌ 除妖系统暂时关闭，请稍后再试。", False

        # 玩家战斗属性（与镇妖塔同源：传承+装备+五行）
        impart_hp = impart_mp = impart_atk = impart_crit = 0.0
        try:
            info = await self.db.ext.get_impart_info(uid)
            if info:
                impart_hp = info.impart_hp_per
                impart_mp = info.impart_mp_per
                impart_atk = info.impart_atk_per
                impart_crit = info.impart_know_per
        except Exception:
            pass
        hp, mp = cm.calculate_hp_mp(player.experience, impart_hp, impart_mp)
        atk = cm.calculate_atk(
            player.experience, player.atkpractice, impart_atk,
            player.physical_damage, player.magic_damage, player.cultivation_type
        )
        effects = {}
        try:
            em = EquipmentManager(self.db, self.config_manager)
            effects = em.get_combat_effects(player)
        except Exception:
            effects = {}
        element = cm.get_element_from_name(player.main_technique) or cm.get_element_from_name(player.weapon)

        player_stats = CombatStats(
            user_id=uid,
            name=player.user_name or f"道友{uid[:6]}",
            hp=hp, max_hp=hp, mp=mp, max_mp=mp,
            atk=atk, crit_rate=int(impart_crit * 100),
            exp=player.experience, effects=effects, element=element,
        )

        # 妖兽：按境界缩放 + 随机浮动
        lv = player.level_index
        name = random.choice(self.PREFIXES) + random.choice(self.BODIES)
        m_hp = int((500 + 260 * lv) * random.uniform(0.85, 1.25))
        m_atk = int((60 + 46 * lv) * random.uniform(0.85, 1.20))
        m_def = 5 + 6 * lv
        monster = CombatStats(
            user_id="hunt",
            name=name,
            hp=m_hp, max_hp=m_hp, mp=0, max_mp=0,
            atk=m_atk, defense=m_def, crit_rate=8,
        )

        result = cm.player_vs_boss(player_stats, monster)
        win = result.get("winner") == uid

        if win:
            # 奖励与妖兽强度挂钩（强度本身随境界增长）
            exp_reward = int(m_hp * 0.35)
            gold_reward = int(m_hp * 0.16)
            await self.db.add_player_exp(uid, exp_reward)
            await self.db.add_player_gold(uid, gold_reward)

            # 累计击杀（称号用）
            total = await self.db.ext.syscfg_adjust_number("hunt_total_" + uid, 1)

            lines = [
                f"⚔️【除妖】你斩杀了{name}！",
                "━━━━━━━━━━━━━━━",
                f"战斗回合数：{result.get('rounds', '?')}",
                f"📈 修为：+{exp_reward:,}",
                f"💰 灵石：+{gold_reward:,}",
            ]
            roll = random.random()
            acc = 0.0
            for item_name, chance in self.DROP_POOL:
                acc += chance
                if roll < acc:
                    if self.storage_ring_mgr:
                        ok, _ = await self.storage_ring_mgr.store_item(player, item_name, 1, silent=True)
                        lines.append(f"🎁 掉落：【{item_name}】x1" + ("" if ok else "（储物戒已满，丢失）"))
                    break
            lines.append(f"🗡️ 累计除妖：{total} 只")
            return True, "\n".join(lines), True

        # 战败：气血大损 + 保底
        lose_exp = int(m_hp * 0.035)
        await self.db.add_player_exp(uid, lose_exp)
        new_hp = max(1, player.hp // 3)
        await self.db.update_player_fields(uid, hp=new_hp)
        return True, (
            f"💀【除妖】你被{name}击退了！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"战斗回合数：{result.get('rounds', '?')}\n"
            f"📈 败中悟道：修为 +{lose_exp:,}（保底）\n"
            f"💔 气血大损（剩余 {new_hp}）\n"
            f"💡 妖兽有强弱浮动，提升装备后再战"
        ), False

    async def get_panel(self, player: Player) -> str:
        """除妖面板"""
        import time
        uid = player.user_id
        used = await self.db.ext.syscfg_get_number(self._cnt_key(uid))
        total = await self.db.ext.syscfg_get_number("hunt_total_" + uid)
        return (
            "🗡️【除妖卫道】\n"
            "━━━━━━━━━━━━━━━\n"
            f"🎫 今日剩余：{max(0, self.DAILY_HUNTS - used)}/{self.DAILY_HUNTS}\n"
            f"🗡️ 累计除妖：{total} 只\n"
            "━━━━━━━━━━━━━━━\n"
            "💡 /除妖 挑战一只与自身境界相当的妖兽（有强弱浮动）\n"
            "💡 战利品：修为/灵石 + 概率掉落引雷符/洗练石/强化石/空间石"
        )
