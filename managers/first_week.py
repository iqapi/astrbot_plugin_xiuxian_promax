# managers/first_week.py —— 新手七日仙途
import time
import json
from typing import Tuple

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["FirstWeekManager"]

DAYS = [
    {"day": 1, "title": "初入仙途", "task": "创建角色并发送 /我的信息", "key": "created", "gold": 2000, "exp": 1000},
    {"day": 2, "title": "吐纳入门", "task": "完成一次 /闭关 并 /出关", "key": "cultivate", "gold": 3000, "exp": 3000},
    {"day": 3, "title": "行走人间", "task": "完成一次 /开始历练", "key": "adventure", "gold": 4000, "exp": 5000},
    {"day": 4, "title": "广结善缘", "task": "完成一次 /签到 并 /行善", "key": "good", "gold": 5000, "exp": 8000},
    {"day": 5, "title": "探秘寻宝", "task": "完成一次 /探索秘境", "key": "rift", "gold": 8000, "exp": 12000},
    {"day": 6, "title": "突破桎梏", "task": "完成一次 /突破", "key": "breakthrough", "gold": 10000, "exp": 15000},
    {"day": 7, "title": "仙途新星", "task": "完成以上全部，领取终极大礼", "key": "all", "gold": 20000, "exp": 30000},
]


class FirstWeekManager:
    """新手七日仙途：按自然日解锁阶段，行为达标后领取"""

    def __init__(self, db: DataBase):
        self.db = db

    def _key(self, user_id: str) -> str:
        return f"firstweek_{user_id}"

    async def get_state(self, player: Player) -> dict:
        raw = await self.db.ext.get_system_config(self._key(player.user_id))
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass
        # 初始化：记录开始日
        return {"start": time.strftime("%Y-%m-%d"), "claimed": [], "acts": {}}

    async def save_state(self, player: Player, state: dict):
        await self.db.ext.set_system_config(self._key(player.user_id), json.dumps(state, ensure_ascii=False))

    def _day_index(self, state: dict) -> int:
        """当前是第几天（从开始日起）"""
        try:
            start = time.mktime(time.strptime(state["start"], "%Y-%m-%d"))
            today = time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d"))
            return min(7, int((today - start) // 86400) + 1)
        except Exception:
            return 1

    async def onboarding_panel(self, player: Player) -> str:
        """七日面板（/新手七日 查看）"""
        state = await self.get_state(player)
        day = self._day_index(state)
        claimed = state.get("claimed", [])
        acts = state.get("acts", {})

        lines = ["🗓️【新手七日仙途】", "━━━━━━━━━━━━━━━"]
        for d in DAYS:
            done_all = d["key"] == "all"
            status = "✅已领" if d["title"] in claimed else ("🔓可领" if self._day_ready(state, d, day, acts) else ("⏳未达成" if d["day"] <= day else f"🔒第{d['day']}天解锁"))
            lines.append(f"[第{d['day']}日] {d['title']} {status}")
            lines.append(f"   任务：{d['task']}")
            lines.append(f"   奖励：{d['gold']:,}灵石 + {d['exp']:,}修为")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("💡 行为完成后自动记录，/新手七日 领取已达成的奖励")
        lines.append("💡 第7日领完全部奖励获得称号【仙途新星】")
        return "\n".join(lines)

    def _day_ready(self, state: dict, d: dict, day: int, acts: dict) -> bool:
        """该阶段奖励是否可领（日期到达 + 行为完成）"""
        if d["title"] in state.get("claimed", []):
            return False
        if d["day"] > day:
            return False
        if d["key"] == "all":
            # 第7天：前6天都领过
            return len(state.get("claimed", [])) >= 6
        return acts.get(d["key"], 0) > 0

    async def record_action(self, player: Player, key: str):
        """各玩法调用：记录行为（幂等计数）"""
        state = await self.get_state(player)
        state.setdefault("acts", {})
        state["acts"][key] = state["acts"].get(key, 0) + 1
        await self.save_state(player, state)

    async def claim(self, player: Player) -> Tuple[bool, str]:
        """领取全部已达成奖励（一键）"""
        state = await self.get_state(player)
        day = self._day_index(state)
        claimed = state.get("claimed", [])
        acts = state.get("acts", {})
        total_gold = total_exp = 0
        new_claims = []

        for d in DAYS:
            if d["title"] in claimed:
                continue
            if self._day_ready(state, d, day, acts):
                total_gold += d["gold"]
                total_exp += d["exp"]
                claimed.append(d["title"])
                new_claims.append(f"第{d['day']}日【{d['title']}】")

        if not new_claims:
            return False, "⏳ 暂无可领取的七日奖励。完成任务后 /新手七日 查看进度。"

        player.gold += total_gold
        player.experience += total_exp

        # 第7日全领 → 称号
        title_note = ""
        if len(claimed) >= 7:
            from .title_manager import TitleManager
            tm = TitleManager(self.db)
            ok, tmsg = tm.grant(player, "仙途新星")
            if not ok:
                # 称号池无此名则手动注入
                from .title_data import TITLES, TIERS
                TITLES.append({"name": "仙途新星", "tier": 2, "how": "manual", "condition": None, "atk": 40, "exp": 0.05})
                tm.grant(player, "仙途新星")
            title_note = "\n🏅 七日圆满！获得称号【仙途新星】（灵品·物伤+40 修为+5%）"

        state["claimed"] = claimed
        await self.save_state(player, state)
        await self.db.update_player(player)

        return True, (
            f"🎁【七日仙途】领取成功！\n"
            f"━━━━━━━━━━━━━━━\n"
            + "\n".join(f"✅ {c}" for c in new_claims)
            + f"\n━━━━━━━━━━━━━━━\n"
            f"💰 灵石：+{total_gold:,}\n"
            f"📈 修为：+{total_exp:,}"
            + title_note
        )
