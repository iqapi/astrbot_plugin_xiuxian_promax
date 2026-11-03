# managers/nest_defense_manager.py
"""妖兽巢穴入侵（v3.35.0 新玩法）：全服限时协力防御战

- 管理员 /开启巢穴入侵：30 分钟窗口，全服修士 /驰援巢穴 迎战浪潮妖兽
- 每场胜利的"镇压伤害"计入全服镇压值（原子数值累加，目标 = 全服玩家数 × 2000，下限 5 万）
- 镇压值达标 → 即刻胜利结算：全服每位修士 5000 灵石 + 8000 修为，贡献榜 Top3 追加洗练石
- 到期未达标 → 妖兽洗劫：全服灵石 -5%（下限保 1000）—— 群体共担，人人有责
- 状态 3 个键（nest_state JSON / nest_progress 数值 / nest_dmg_{eid}_{uid}），无新表；
  结算 CAS 抢占防双发；过期结算惰性触发（状态/驰援时检查）
"""

import json
import random
import time
from typing import Tuple, Optional

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["NestDefenseManager"]


class NestDefenseManager:
    """妖兽巢穴：倾巢之下无完卵，驰援者功在千秋"""

    STATE_KEY = "nest_state"
    PROGRESS_KEY = "nest_progress"
    DURATION = 30 * 60
    PER_CAPITA = 2000
    MIN_TARGET = 50000
    DAILY_HUNTS = 3
    VICTORY_GOLD, VICTORY_EXP = 5000, 8000
    RAID_LOSS_RATE = 0.05
    MIN_KEEP = 1000

    WAVE_NAMES = ["妖潮先锋", "兽潮中军", "巢穴守卫", "狂暴妖将"]

    def __init__(self, db: DataBase, config_manager=None, storage_ring_mgr=None):
        self.db = db
        self.config_manager = config_manager
        self.storage_ring_mgr = storage_ring_mgr

    def _dmg_prefix(self, event_id: str) -> str:
        return f"nest_dmg_{event_id}_"

    async def get_state(self) -> Optional[dict]:
        raw = await self.db.ext.get_system_config(self.STATE_KEY)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None

    async def start(self) -> Tuple[bool, str]:
        """管理员开启（CAS 防重复开启）"""
        if await self.get_state():
            return False, "❌ 妖兽巢穴入侵已在进行中！/巢穴状态 查看。"
        players = await self.db.get_all_players()
        target = max(self.MIN_TARGET, len(players) * self.PER_CAPITA)
        state = {
            "event_id": str(int(time.time())),
            "monster": random.choice(self.WAVE_NAMES),
            "end_ts": int(time.time()) + self.DURATION,
            "target": target,
        }
        claimed = await self.db.ext.syscfg_cas(
            self.STATE_KEY, json.dumps(state, ensure_ascii=False), None
        )
        if not claimed:
            return False, "❌ 开启失败（并发冲突），请重试。"
        await self.db.ext.set_system_config(self.PROGRESS_KEY, "0")
        return True, (
            "🐗【天道警示】妖兽巢穴异动，兽潮倾巢而出！\n"
            "━━━━━━━━━━━━━━━\n"
            f"👹 妖兽：{state['monster']} 率兽潮冲击修仙界！\n"
            f"⏳ 镇压窗口：30 分钟\n"
            f"🎯 全服镇压目标：{target:,} 点镇压值\n"
            "━━━━━━━━━━━━━━━\n"
            f"💡 全服修士 /驰援巢穴 迎战（每日{self.DAILY_HUNTS}次）！\n"
            "💡 镇压成功：全服 5000 灵石 + 8000 修为，贡献榜 Top3 追加洗练石\n"
            "💀 镇压失败：妖兽洗劫，全服灵石 -5%！"
        )

    async def _settle(self, state: dict, success: bool) -> str:
        """CAS 抢占结算权后一次性结算（胜利发奖 / 失败洗劫）"""
        claimed = await self.db.ext.syscfg_cas(
            self.STATE_KEY, json.dumps({**state, "open": False}, ensure_ascii=False),
            json.dumps(state, ensure_ascii=False),
        )
        if not claimed:
            return ""
        event_id = state["event_id"]
        prefix = self._dmg_prefix(event_id)

        # 读取贡献榜（同时收集贡献者）
        ranking = []
        try:
            async with self.db.conn.execute(
                "SELECT key, value FROM system_config WHERE key LIKE ?", (prefix + "%",)
            ) as cursor:
                rows = await cursor.fetchall()
            for key, value in rows:
                uid = key[len(prefix):]
                try:
                    ranking.append((uid, int(value)))
                except (TypeError, ValueError):
                    continue
            ranking.sort(key=lambda x: -x[1])
        except Exception as e:
            logger.error(f"[巢穴] 贡献榜读取失败: {e}")

        if success:
            # 全服奖励
            try:
                await self.db.conn.execute(
                    "UPDATE players SET gold = gold + ?, experience = experience + ?",
                    (self.VICTORY_GOLD, self.VICTORY_EXP)
                )
                await self.db.conn.commit()
            except Exception as e:
                logger.error(f"[巢穴] 全服发奖失败: {e}")
            extra = []
            medals = {0: ("🥇", 2), 1: ("🥈", 1), 2: ("🥉", 1)}
            for i, (uid, dmg) in enumerate(ranking[:3]):
                stones = medals[i][1]
                if self.storage_ring_mgr:
                    p = await self.db.get_player_by_id(uid)
                    if p:
                        await self.storage_ring_mgr.store_item(p, "洗练石", stones, silent=True)
                p = await self.db.get_player_by_id(uid)
                name = (p.user_name if p and p.user_name else uid[:8])
                extra.append(f"{medals[i][0]} {name}：镇压 {dmg:,} → 洗练石x{stones}")
            # 清理贡献键
            for uid, _ in ranking:
                await self.db.ext.delete_system_config(prefix + uid)
            await self.db.ext.delete_system_config(self.PROGRESS_KEY)
            lines = [
                "🎉【兽潮平定】全服修士同心，妖兽巢穴被彻底荡平！",
                f"🏆 全服每位修士获得：{self.VICTORY_GOLD:,} 灵石 + {self.VICTORY_EXP:,} 修为",
            ]
            lines.extend(extra)
            lines.append("💡 妖兽余孽已远遁，感谢每一位驰援的道友！")
            return "\n".join(lines)

        # 失败：全服洗劫（灵石 -5%，保底 1000）
        try:
            await self.db.conn.execute(
                "UPDATE players SET gold = MAX(?, gold - CAST(gold * ? AS INTEGER))",
                (self.MIN_KEEP, self.RAID_LOSS_RATE)
            )
            await self.db.conn.commit()
        except Exception as e:
            logger.error(f"[巢穴] 洗劫结算失败: {e}")
        for uid, _ in ranking:
            await self.db.ext.delete_system_config(prefix + uid)
        await self.db.ext.delete_system_config(self.PROGRESS_KEY)
        return (
            f"💀【妖兽洗劫】镇压失败！{state['monster']} 率兽潮洗劫了修仙界……\n"
            f"💸 全服修士灵石损失 {int(self.RAID_LOSS_RATE * 100)}%（保底留存 {self.MIN_KEEP:,}）\n"
            "💡 妖兽退去，下一次入侵请众志成城！"
        )

    async def _check_expire(self, state: dict) -> Optional[str]:
        """惰性过期结算"""
        if time.time() <= int(state.get("end_ts", 0)):
            return None
        progress = await self.db.ext.syscfg_get_number(self.PROGRESS_KEY)
        return await self._settle(state, progress >= int(state.get("target", 1)))

    async def contribute(self, player: Player) -> Tuple[bool, str]:
        """驰援巢穴：迎战浪潮妖兽，胜利的伤害计入镇压值"""
        uid = player.user_id
        state = await self.get_state()
        if not state:
            return False, "🌫 当前没有妖兽巢穴入侵。留意管理员开启！"
        expire_msg = await self._check_expire(state)
        if expire_msg:
            return True, expire_msg
        state = await self.get_state() or state

        event_id = state["event_id"]
        if not await self.db.ext.syscfg_claim_slot(f"nest_cnt_{event_id}_{uid}", self.DAILY_HUNTS):
            return False, f"❌ 今日驰援次数已用尽（每日 {self.DAILY_HUNTS} 次）。"

        # 迎战浪潮妖兽（强度按境界 + 随机）
        try:
            from .combat_manager import CombatManager, CombatStats
            cm = CombatManager()
        except Exception as e:
            logger.error(f"[巢穴] 加载战斗组件失败: {e}")
            await self.db.ext.syscfg_adjust_number(f"nest_cnt_{event_id}_{uid}", -1)
            return False, "❌ 战场暂时关闭，请稍后再试。"

        hp, mp = cm.calculate_hp_mp(player.experience)
        atk = cm.calculate_atk(
            player.experience, player.atkpractice, 0,
            player.physical_damage, player.magic_damage, player.cultivation_type
        )
        lv = player.level_index
        wave_hp = int((400 + 200 * lv) * random.uniform(0.9, 1.4))
        wave_atk = int((50 + 40 * lv) * random.uniform(0.9, 1.3))
        wave = CombatStats(
            user_id="wave", name=f"{state['monster']}·浪潮兵",
            hp=wave_hp, max_hp=wave_hp, mp=0, max_mp=0,
            atk=wave_atk, defense=4 + 5 * lv, crit_rate=8,
        )
        p_stats = CombatStats(
            user_id=uid, name=player.user_name or f"道友{uid[:6]}",
            hp=hp, max_hp=hp, mp=mp, max_mp=mp, atk=atk,
            exp=player.experience, element=cm.get_element_from_name(player.weapon),
        )
        result = cm.player_vs_boss(p_stats, wave)
        win = result.get("winner") == uid

        progress = await self.db.ext.syscfg_get_number(self.PROGRESS_KEY)
        target = int(state.get("target", 1))

        if not win:
            return True, (
                f"💔 你被浪潮妖兽击退了！\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📊 全服镇压值：{progress:,} / {target:,}\n"
                f"💡 整备再战（/强化 /服丹），每日还有 {self.DAILY_HUNTS} 次机会"
            )

        damage = max(1, int(wave_hp * 1.2))
        new_progress = await self.db.ext.syscfg_adjust_number(self.PROGRESS_KEY, damage)
        my_total = await self.db.ext.syscfg_adjust_number(self._dmg_prefix(event_id) + uid, damage)
        remain = max(0, target - new_progress)

        lines = [
            f"⚔️【驰援巢穴】你击溃了{state['monster']}·浪潮兵！",
            "━━━━━━━━━━━━━━━",
            f"💥 镇压伤害：+{damage:,}",
            f"🧮 你的累计镇压：{my_total:,}",
            f"📊 全服镇压值：{new_progress:,} / {target:,}",
        ]
        if new_progress >= target:
            settle_msg = await self._settle(state, True)
            if settle_msg:
                lines.append(settle_msg)
                return True, "\n".join(lines)
        pct = min(100.0, new_progress * 100.0 / max(1, target))
        lines.append(f"⏳ 镇压进度：{pct:.1f}%（还差 {remain:,}）")
        return True, "\n".join(lines)

    async def get_status(self) -> str:
        state = await self.get_state()
        if not state:
            return "🌫 当前没有妖兽巢穴入侵。管理员可 /开启巢穴入侵。"
        expire_msg = await self._check_expire(state)
        if expire_msg:
            return expire_msg
        state = await self.get_state() or state
        progress = await self.db.ext.syscfg_get_number(self.PROGRESS_KEY)
        target = int(state.get("target", 1))
        remain = max(0, int(state.get("end_ts", 0)) - int(time.time()))
        pct = min(100.0, progress * 100.0 / max(1, target))
        filled = int(pct // 5)
        bar = "█" * filled + "░" * (20 - filled)
        return (
            f"🐗【巢穴入侵·{state['monster']}】\n"
            "━━━━━━━━━━━━━━━\n"
            f"镇压值 [{bar}] {pct:.1f}%\n"
            f"📊 {progress:,} / {target:,}\n"
            f"⏳ 剩余：{remain // 60} 分 {remain % 60} 秒\n"
            "━━━━━━━━━━━━━━━\n"
            f"💡 /驰援巢穴 迎战浪潮妖兽（每日{self.DAILY_HUNTS}次）\n"
            f"💡 胜利伤害计入镇压值，达标全服有奖、失败全服洗劫！"
        )
