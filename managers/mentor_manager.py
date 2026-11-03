# managers/mentor_manager.py
"""仙府传功（v3.37.0 新玩法）：前辈提携后辈，双向增益

- 高境界修士（≥15）可 /传功 @后辈（对方境界 ≤8 且非自己）
- 后辈即刻获得修为（随传功者境界成长）；传功者积功德 +1（行善同源）
- 传功者每日 3 次、受功者每日 1 次（原子限次）；同对师徒/道友亦可传功
- 全部走原子原语，无新表
"""

import time
from typing import Tuple

from ..data.data_manager import DataBase

__all__ = ["MentorManager"]


class MentorManager:
    """仙府传功：薪火相传，仙道不孤"""

    MENTOR_MIN_LEVEL = 15
    JUNIOR_MAX_LEVEL = 8
    MENTOR_DAILY = 3
    JUNIOR_DAILY = 1
    EXP_PER_LEVEL = 250

    @staticmethod
    def _mentor_key(uid: str) -> str:
        return f"mentor_cnt_{uid}_{time.strftime('%Y%m%d')}"

    @staticmethod
    def _junior_key(uid: str) -> str:
        return f"mentored_{uid}_{time.strftime('%Y%m%d')}"

    async def transfer(self, db: DataBase, mentor, junior) -> Tuple[bool, str]:
        mentor_id = mentor.user_id
        junior_id = junior.user_id

        if mentor.level_index < self.MENTOR_MIN_LEVEL:
            return False, f"❌ 传功需自身境界 ≥ {self.MENTOR_MIN_LEVEL}（当前 {mentor.level_index}）——自身道行不足，难以度人。"
        if junior.level_index > self.JUNIOR_MAX_LEVEL:
            return False, f"❌ 受功者境界需 ≤ {self.JUNIOR_MAX_LEVEL}（对方 {junior.level_index}），后辈根骨方能承接。"

        if not await db.ext.syscfg_claim_slot(self._mentor_key(mentor_id), self.MENTOR_DAILY):
            return False, f"❌ 你今日传功次数已用尽（每日 {self.MENTOR_DAILY} 次），功德也不可急于一日。"
        if not await db.ext.syscfg_claim_slot(self._junior_key(junior_id), self.JUNIOR_DAILY):
            await db.ext.syscfg_adjust_number(self._mentor_key(mentor_id), -1)  # 退回名额
            return False, "❌ 对方今日已受过一次传功，明日再来。"

        exp_gain = self.EXP_PER_LEVEL * mentor.level_index
        await db.add_player_exp(junior_id, exp_gain)
        await db.conn.execute(
            "UPDATE players SET karma = karma + 1 WHERE user_id = ?", (mentor_id,)
        )
        await db.conn.commit()

        mname = mentor.user_name or mentor_id[:8]
        jname = junior.user_name or junior_id[:8]
        return True, (
            f"🏮【仙府传功】{mname} 指点 {jname} 修行！\n"
            "━━━━━━━━━━━━━━━\n"
            f"📈 {jname} 获得修为：+{exp_gain:,}\n"
            f"🪷 {mname} 功德 +1（传功亦是修行）\n"
            "━━━━━━━━━━━━━━━\n"
            f"💡 传功者每日 {self.MENTOR_DAILY} 次 · 受功者每日 1 次"
        )
