# managers/tower_manager.py
"""镇妖塔（v3.26.0 新玩法）：逐层爬塔 PVE

设计：
- /镇妖塔 挑战「最高通关层 + 1」（每日 3 次），层数越高妖兽越强
- 通关层数永久记录；扫荡已通关最高层可快速拿奖（每日 2 次，60% 收益）
- 每 5 层额外掉落稀有物品；打破全服记录时返回首通播报文案
- 状态全部存 system_config 数值键（tower_best_* / tower_sweep_* / tower_record），不建新表
- 奖励与层数记录全走原子原语（syscfg_cas / syscfg_adjust_number / add_player_*）
"""

from typing import Tuple, Optional, List

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["TowerManager"]


class TowerManager:
    """镇妖塔：逐层挑战妖兽，冲击更高层数"""

    DAILY_CHALLENGES = 3      # 每日挑战次数
    DAILY_SWEEPS = 2          # 每日扫荡次数
    SWEEP_RATE = 0.6          # 扫荡收益比例（按最高层单层奖励）
    GLOBAL_RECORD_KEY = "tower_record"

    # 妖兽名（按层数段位轮换）
    MONSTER_NAMES = [
        "灰毛妖鼠", "赤目狼妖", "铁甲蜈妖", "噬魂鬼婢", "血煞蛛母",
        "百目蟾妖", "阴风老魅", "枯骨魔将", "九婴残魂", "堕仙傀儡",
        "炎狱魔君", "玄冥妖圣", "噬天凶兽", "上古塔灵",
    ]

    def __init__(self, db: DataBase, config_manager=None, storage_ring_mgr=None):
        self.db = db
        self.config_manager = config_manager
        self.storage_ring_mgr = storage_ring_mgr

    # ===== 内部工具 =====

    @staticmethod
    def _best_key(uid: str) -> str:
        return f"tower_best_{uid}"

    async def get_best(self, uid: str) -> int:
        """当前最高通关层"""
        return await self.db.ext.syscfg_get_number(self._best_key(uid))

    @staticmethod
    def _sweep_key(uid: str) -> str:
        return f"tower_sweep_{uid}"

    @staticmethod
    def _challenge_key(uid: str) -> str:
        return f"tower_cnt_{uid}_{__import__('time').strftime('%Y%m%d')}"

    def _monster_name(self, floor: int) -> str:
        idx = min((floor - 1) // 3, len(self.MONSTER_NAMES) - 1)
        return self.MONSTER_NAMES[idx]

    @staticmethod
    def _floor_rewards(floor: int) -> Tuple[int, int]:
        """第 floor 层通关奖励（修为, 灵石）：线性 + 平方缓增"""
        exp = 300 * floor + 20 * floor * floor
        gold = 150 * floor + 10 * floor * floor
        return exp, gold

    def _bonus_item(self, floor: int) -> Optional[str]:
        """里程碑层额外掉落"""
        if floor % 10 == 0:
            return "空间石"
        if floor % 5 == 0:
            return "洗练石"
        if floor % 3 == 0:
            return "引雷符"
        return None

    # ===== 公开方法 =====

    async def challenge(self, player: Player) -> Tuple[bool, str, bool]:
        """挑战下一层。返回 (成功, 消息, 是否打破全服记录)"""
        uid = player.user_id

        best = await self.db.ext.syscfg_get_number(self._best_key(uid))
        target = best + 1

        # 每日限次（原子认领，并发连发不可绕过）
        if not await self.db.ext.syscfg_claim_slot(self._challenge_key(uid), self.DAILY_CHALLENGES):
            return False, f"❌ 今日镇妖塔挑战次数已用尽（每日 {self.DAILY_CHALLENGES} 次），明日再战！", False

        # 组装玩家战斗属性（含传承与装备加成，与 Boss 挑战同源）
        try:
            from .combat_manager import CombatManager, CombatStats
            from ..core import EquipmentManager
            cm = CombatManager()
        except Exception as e:
            logger.error(f"[镇妖塔] 加载战斗组件失败: {e}")
            return False, "❌ 镇妖塔暂时关闭，请稍后再试。", False

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

        # 妖兽属性：指数递增（1 层约等于炼气后期，20 层需元婴战力）
        m_hp = int(900 * (1.17 ** (target - 1)))
        m_atk = int(70 * (1.14 ** (target - 1)))
        m_def = int(8 * target)
        boss_stats = CombatStats(
            user_id=str(target),
            name=f"第{target}层·{self._monster_name(target)}",
            hp=m_hp, max_hp=m_hp, mp=0, max_mp=0,
            atk=m_atk, defense=m_def, crit_rate=10,
        )

        result = cm.player_vs_boss(player_stats, boss_stats)
        win = result.get("winner") == uid
        exp_reward, gold_reward = self._floor_rewards(target)

        if win:
            # 通关：层数 CAS 推进（防并发重复拿首通奖励），奖励原子发放
            claimed = await self.db.ext.syscfg_cas(
                self._best_key(uid), str(target), str(best) if best else None
            )
            if not claimed:
                # 并发下他人协程已推进层数 → 本次按失败重试提示
                await self.db.ext.syscfg_adjust_number(self._challenge_key(uid), -1)
                return False, "⚠️ 层数记录刚刚被推进，请稍后再挑战。", False

            await self.db.add_player_exp(uid, exp_reward)
            await self.db.add_player_gold(uid, gold_reward)

            item_lines = []
            bonus = self._bonus_item(target)
            if bonus and self.storage_ring_mgr:
                ok, _ = await self.storage_ring_mgr.store_item(player, bonus, 1, silent=True)
                item_lines.append(f"📦 里程碑奖励：【{bonus}】x1" + ("" if ok else "（储物戒已满，丢失）"))

            # 全服记录
            new_record = False
            record = await self.db.ext.syscfg_get_number(self.GLOBAL_RECORD_KEY)
            if target > record:
                if await self.db.ext.syscfg_cas(
                    self.GLOBAL_RECORD_KEY, str(target), str(record) if record else None
                ):
                    new_record = True

            lines = [
                f"🗼【镇妖塔】第 {target} 层通关！",
                "━━━━━━━━━━━━━━━",
                f"⚔️ 击败：{self._monster_name(target)}（{result.get('rounds', '?')} 回合）",
                f"📈 修为：+{exp_reward:,}",
                f"💰 灵石：+{gold_reward:,}",
            ]
            lines.extend(item_lines)
            lines.append(f"🧭 当前最高通关：第 {target} 层")
            if new_record:
                lines.append("🏆 你刷新了全服最高纪录！镇妖塔为你震荡三日夜！")
            return True, "\n".join(lines), new_record

        # 挑战失败：保底安慰奖 + 气血受创
        lose_exp = int(exp_reward * 0.2)
        await self.db.add_player_exp(uid, lose_exp)
        new_hp = max(1, player.hp // 3)
        await self.db.update_player_fields(uid, hp=new_hp)

        lines = [
            f"🗼【镇妖塔】第 {target} 层挑战失败",
            "━━━━━━━━━━━━━━━",
            f"💀 {self._monster_name(target)} 太过凶悍，你被迫退出塔外",
            f"📈 淬炼心得：修为 +{lose_exp:,}（保底）",
            f"💔 气血大损（剩余 {new_hp}），休息一下再战",
            f"🧭 当前最高通关：第 {best} 层",
            "💡 提升装备（/强化 /洗练）、服丹、佩戴称号后再来挑战",
        ]
        return True, "\n".join(lines), False

    async def sweep(self, player: Player) -> Tuple[bool, str]:
        """扫荡已通关最高层（每日 2 次，60% 单层收益，不掉落物品）"""
        uid = player.user_id
        best = await self.db.ext.syscfg_get_number(self._best_key(uid))
        if best < 1:
            return False, "❌ 你还未通关任何一层，先 /镇妖塔 挑战第 1 层吧！"

        if not await self.db.ext.syscfg_claim_slot(self._sweep_key(uid), self.DAILY_SWEEPS):
            return False, f"❌ 今日扫荡次数已用尽（每日 {self.DAILY_SWEEPS} 次），明日再来。"

        exp_reward, gold_reward = self._floor_rewards(best)
        exp_reward = int(exp_reward * self.SWEEP_RATE)
        gold_reward = int(gold_reward * self.SWEEP_RATE)
        await self.db.add_player_exp(uid, exp_reward)
        await self.db.add_player_gold(uid, gold_reward)

        remain = self.DAILY_SWEEPS - await self.db.ext.syscfg_get_number(self._sweep_key(uid))
        return True, (
            f"⚡【镇妖塔·扫荡】第 {best} 层\n"
            f"━━━━━━━━━━━━━━━\n"
            f"你以昔日战绩碾压重演，收获（60%收益，无物品掉落）：\n"
            f"📈 修为：+{exp_reward:,}\n"
            f"💰 灵石：+{gold_reward:,}\n"
            f"💡 今日剩余扫荡次数：{max(0, remain)}\n"
            f"🎯 冲击第 {best + 1} 层可获得全额奖励与里程碑掉落"
        )

    async def get_panel(self, player: Player) -> str:
        """镇妖塔面板（进度 + 规则）"""
        uid = player.user_id
        best = await self.db.ext.syscfg_get_number(self._best_key(uid))
        record = await self.db.ext.syscfg_get_number(self.GLOBAL_RECORD_KEY)
        used = await self.db.ext.syscfg_get_number(self._challenge_key(uid))
        exp_reward, gold_reward = self._floor_rewards(best + 1)

        lines = [
            "🗼【镇妖塔】",
            "━━━━━━━━━━━━━━━",
            f"🧭 你的最高通关：第 {best} 层",
            f"🏆 全服纪录：第 {record} 层",
            f"🎫 今日剩余挑战：{max(0, self.DAILY_CHALLENGES - used)}/{self.DAILY_CHALLENGES}",
            "━━━━━━━━━━━━━━━",
            f"⏭️ 下一层：第 {best + 1} 层 · {self._monster_name(best + 1)}",
            f"   通关可得：修为 {exp_reward:,} + 灵石 {gold_reward:,}",
            "   每 3/5/10 层有里程碑物品掉落",
            "━━━━━━━━━━━━━━━",
            f"💡 /镇妖塔 挑战（每日{self.DAILY_CHALLENGES}次）· /镇妖塔扫荡（每日{self.DAILY_SWEEPS}次，60%收益）",
            "💡 /镇妖塔榜 查看全服登塔英杰",
        ]
        return "\n".join(lines)

    async def get_ranking(self, limit: int = 10) -> str:
        """全服登塔排行（扫描 tower_best_* 数值键）"""
        async with self.db.conn.execute(
            "SELECT key, value FROM system_config WHERE key LIKE 'tower_best_%'"
        ) as cursor:
            rows = await cursor.fetchall()

        entries: List[Tuple[str, int]] = []
        for key, value in rows:
            uid = key.replace("tower_best_", "")
            try:
                floor = int(value)
            except (TypeError, ValueError):
                continue
            if floor > 0:
                entries.append((uid, floor))
        entries.sort(key=lambda x: -x[1])

        if not entries:
            return "🗼【镇妖塔·登塔榜】\n━━━━━━━━━━━━━━━\n尚无人登塔，发 /镇妖塔 成为第一个破阵者！"

        lines = ["🗼【镇妖塔·登塔榜】", "━━━━━━━━━━━━━━━"]
        medals = ["🥇", "🥈", "🥉"]
        for i, (uid, floor) in enumerate(entries[:limit], 1):
            p = await self.db.get_player_by_id(uid)
            name = (p.user_name if p and p.user_name else uid[:8])
            medal = medals[i - 1] if i <= 3 else f"{i}."
            lines.append(f"{medal} {name} —— 第 {floor} 层")
        record = await self.db.ext.syscfg_get_number(self.GLOBAL_RECORD_KEY)
        lines.append("━━━━━━━━━━━━━━━")
        lines.append(f"🏆 全服纪录：第 {record} 层 · 发 /镇妖塔 挑战！")
        return "\n".join(lines)
