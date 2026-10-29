# managers/achievement_manager.py
"""成就系统 v1.0 - 复用称号钩子的现成行为计数（v3.20.0 新玩法）

零额外钩子：直接读取 title_hooks 已写入 system_config 的累计计数
    key 格式：title_cnt_<key>_<uid>
    现成 key：checkin_count / cultivate_count / adventure_count / rift_count /
              craft_count / forge_count / spar_count / boss_kill 等

成就分三类：
- 累计类：签到 / 闭关 / 历练 / 炼丹 / 决斗等累计次数
- 境界类：level_index 达到指定境界
- 财富类：持有灵石达到门槛

约定：
- 状态全存 system_config（JSON），不建新表
- 领取记录存 ach_claimed_{uid}（JSON 列表）
- 主控负责指令注册；/成就 查看、/成就领取 <编号> 领奖
"""

import json
from typing import Optional, Tuple, Dict, List, Callable

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["AchievementManager", "ACHIEVEMENTS"]


def _cnt(counter: Dict[str, int], key: str) -> int:
    """容错读取计数（可能为 None / 非数字）"""
    try:
        return int(counter.get(key, 0))
    except (TypeError, ValueError):
        return 0


# ===== 成就表 =====
# check(player, counter) -> bool ；counter 为该玩家的 title_cnt_* 计数集合
ACHIEVEMENTS: List[Dict] = [
    # --- 累计类 ---
    {"id": "a01", "name": "初入山门", "desc": "累计签到 7 天",
     "check": lambda p, c: _cnt(c, "checkin_count") >= 7,
     "reward_gold": 2000, "reward_exp": 3000},
    {"id": "a02", "name": "风雨无阻", "desc": "累计签到 30 天",
     "check": lambda p, c: _cnt(c, "checkin_count") >= 30,
     "reward_gold": 5000, "reward_exp": 10000},
    {"id": "a03", "name": "道心如磐", "desc": "累计签到 100 天",
     "check": lambda p, c: _cnt(c, "checkin_count") >= 100,
     "reward_gold": 30000, "reward_exp": 50000},
    {"id": "a04", "name": "闭关小成", "desc": "累计闭关 50 次",
     "check": lambda p, c: _cnt(c, "cultivate_count") >= 50,
     "reward_gold": 5000, "reward_exp": 10000},
    {"id": "a05", "name": "面壁大师", "desc": "累计闭关 200 次",
     "check": lambda p, c: _cnt(c, "cultivate_count") >= 200,
     "reward_gold": 30000, "reward_exp": 80000},
    {"id": "a06", "name": "初历红尘", "desc": "累计历练 30 次",
     "check": lambda p, c: _cnt(c, "adventure_count") >= 30,
     "reward_gold": 5000, "reward_exp": 8000},
    {"id": "a07", "name": "行走天下", "desc": "累计历练 100 次",
     "check": lambda p, c: _cnt(c, "adventure_count") >= 100,
     "reward_gold": 30000, "reward_exp": 60000},
    {"id": "a08", "name": "丹道学徒", "desc": "累计炼丹 20 次",
     "check": lambda p, c: _cnt(c, "craft_count") >= 20,
     "reward_gold": 5000, "reward_exp": 8000},
    {"id": "a09", "name": "炼器新人", "desc": "累计锻造 20 次",
     "check": lambda p, c: _cnt(c, "forge_count") >= 20,
     "reward_gold": 5000, "reward_exp": 8000},
    {"id": "a10", "name": "切磋常客", "desc": "累计切磋/决斗 10 场",
     "check": lambda p, c: _cnt(c, "spar_count") >= 10,
     "reward_gold": 3000, "reward_exp": 5000},
    {"id": "a11", "name": "秘境探索者", "desc": "累计秘境探索 10 次",
     "check": lambda p, c: _cnt(c, "rift_count") >= 10,
     "reward_gold": 4000, "reward_exp": 8000},
    {"id": "a12", "name": "斩妖除魔", "desc": "累计讨伐首领 20 次",
     "check": lambda p, c: _cnt(c, "boss_kill") >= 20,
     "reward_gold": 8000, "reward_exp": 15000},
    {"id": "a13", "name": "魔道克星", "desc": "累计讨伐首领 50 次",
     "check": lambda p, c: _cnt(c, "boss_kill") >= 50,
     "reward_gold": 30000, "reward_exp": 60000},
    # --- 境界类 ---
    {"id": "b01", "name": "初窥门径", "desc": "境界达到第 10 重",
     "check": lambda p, c: p.level_index >= 10,
     "reward_gold": 5000, "reward_exp": 20000},
    {"id": "b02", "name": "小有所成", "desc": "境界达到第 20 重",
     "check": lambda p, c: p.level_index >= 20,
     "reward_gold": 20000, "reward_exp": 50000},
    {"id": "b03", "name": "名震一方", "desc": "境界达到第 30 重",
     "check": lambda p, c: p.level_index >= 30,
     "reward_gold": 50000, "reward_exp": 80000},
    {"id": "b04", "name": "问鼎巅峰", "desc": "境界达到第 35 重",
     "check": lambda p, c: p.level_index >= 35,
     "reward_gold": 100000, "reward_exp": 100000},
    # --- 财富类 ---
    {"id": "c01", "name": "小有积蓄", "desc": "持有灵石达到 10 万",
     "check": lambda p, c: p.gold >= 100000,
     "reward_gold": 5000, "reward_exp": 20000},
    {"id": "c02", "name": "富甲一方", "desc": "持有灵石达到 100 万",
     "check": lambda p, c: p.gold >= 1000000,
     "reward_gold": 50000, "reward_exp": 100000},
]

ACH_ID_SET = {a["id"] for a in ACHIEVEMENTS}


def _claimed_key(uid: str) -> str:
    return f"ach_claimed_{uid}"


class AchievementManager:
    """成就系统：基于称号钩子的现成行为计数"""

    def __init__(self, db: DataBase):
        self.db = db

    # ===== 存取 =====

    async def _load_counters(self, uid: str) -> Dict[str, int]:
        """读取该玩家所有现成计数 key（可能为 None/非数字，容错 0）"""
        keys = ("checkin_count", "cultivate_count", "adventure_count",
                "rift_count", "craft_count", "forge_count", "spar_count",
                "boss_kill")
        counters: Dict[str, int] = {}
        try:
            for key in keys:
                raw = await self.db.ext.get_system_config(f"title_cnt_{key}_{uid}")
                try:
                    counters[key] = int(raw) if raw and str(raw).strip().lstrip("-").isdigit() else 0
                except (TypeError, ValueError):
                    counters[key] = 0
        except Exception as e:
            logger.error(f"[成就] 读取计数失败 uid={uid}: {e}")
        return counters

    async def _load_claimed(self, uid: str) -> List[str]:
        raw = await self.db.ext.get_system_config(_claimed_key(uid))
        if not raw:
            return []
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, TypeError, ValueError):
            return []

    async def _save_claimed(self, uid: str, claimed: List[str]):
        await self.db.ext.set_system_config(
            _claimed_key(uid), json.dumps(claimed, ensure_ascii=False)
        )

    # ===== 公开方法 =====

    async def handle_list(self, player: Player, event) -> str:
        """/成就：展示全部成就与完成状态"""
        try:
            uid = player.user_id
            counters = await self._load_counters(uid)
            claimed = await self._load_claimed(uid)
            claimed_set = set(claimed)

            total = len(ACHIEVEMENTS)
            done_cnt = sum(1 for a in ACHIEVEMENTS if a["check"](player, counters))
            lines = [
                "🏆 修仙成就录",
                f"进度：{done_cnt}/{total} 完成 · 已领取 {len(claimed_set & ACH_ID_SET)} 项",
                "━━━━━━━━━━━━━━━",
            ]
            for a in ACHIEVEMENTS:
                done = a["check"](player, counters)
                if a["id"] in claimed_set:
                    mark = "✅"
                elif done:
                    mark = "🎉"
                else:
                    mark = "🔒"
                lines.append(
                    f"{mark} [{a['id']}] {a['name']} · {a['desc']}\n"
                    f"     💰{a['reward_gold']:,} 灵石 + ✨{a['reward_exp']:,} 修为"
                )
            lines.append("━━━━━━━━━━━━━━━")
            lines.append("💡 /成就领取 <编号> 领取已达成成就的奖励")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"[成就] 查询失败: {e}")
            return "❌ 查询失败，请稍后再试。"

    async def claim(self, player: Player, ach_id: str) -> Tuple[bool, str]:
        """/成就领取 <编号>：达成且未领则发奖（灵石 + 修为）"""
        try:
            ach_id = (ach_id or "").strip().lower()
            ach = next((a for a in ACHIEVEMENTS if a["id"] == ach_id), None)
            if not ach:
                return False, f"❌ 未找到成就编号「{ach_id or '空'}」，/成就 查看编号列表。"

            uid = player.user_id
            claimed = await self._load_claimed(uid)
            if ach_id in claimed:
                return False, f"✅ 成就【{ach['name']}】的奖励已领取过，不可重复领取。"

            counters = await self._load_counters(uid)
            if not ach["check"](player, counters):
                return False, f"🔒 成就【{ach['name']}】尚未达成：{ach['desc']}"

            # v3.23.0：CAS 抢占领取记录（并发连点不再双发）
            claimed_ok = await self.db.ext.syscfg_cas(
                _claimed_key(uid),
                json.dumps(claimed + [ach_id]),
                json.dumps(claimed),
            )
            if not claimed_ok:
                return False, "❌ 领取请求冲突，请稍后再试。"

            await self.db.add_player_gold(uid, ach["reward_gold"])
            await self.db.add_player_exp(uid, ach["reward_exp"])

            return True, (
                f"🏆 成就达成：【{ach['name']}】\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📜 {ach['desc']}\n"
                f"🎁 奖励：{ach['reward_gold']:,} 灵石 + {ach['reward_exp']:,} 修为\n"
                f"💡 /成就 查看更多成就"
            )
        except Exception as e:
            logger.error(f"[成就] 领取失败: {e}")
            return False, "❌ 领取失败，请稍后再试。"

    async def get_claimed_ids(self, uid: str) -> List[str]:
        """查询已领取的成就编号（供主控展示，无副作用）"""
        try:
            return await self._load_claimed(uid)
        except Exception as e:
            logger.error(f"[成就] 查询已领取失败: {e}")
            return []
