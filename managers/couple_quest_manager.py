# managers/couple_quest_manager.py
"""道侣双修任务链 v1.0 - 每周道侣共同任务（依赖仙灵结缘系统的 npc_partners 表）

约定：
- 状态存 system_config（JSON），不建新表
- 道侣关系复用 managers/social_manager.py 的仙灵道侣（npc_partners 表，npc_id 存仙灵名）
- 主控负责指令注册；本模块在 adventure/checkin/dual 等玩法结算点由主控回调 record_action
"""

import json
import random
import time
from typing import Optional, Tuple, Dict

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["CoupleQuestManager", "COUPLE_QUEST_POOL", "CLAIM_GOLD", "CLAIM_EXP"]

# 领奖水位：双方各得（实际发放给领取者本人）
CLAIM_GOLD = 8000
CLAIM_EXP = 20000

# ===== 每周任务池：action 与主控回调点对应 =====
COUPLE_QUEST_POOL = [
    {"action": "adventure", "target": 3, "text": "本周与你道侣共同完成历练 3 次"},
    {"action": "checkin",   "target": 5, "text": "本周与你道侣共同签到 5 次"},
    {"action": "dual",      "target": 1, "text": "本周与道侣完成 1 次双修"},
]


def current_week() -> str:
    """当前周标识（YYYYWW）"""
    return time.strftime("%Y%W")


class CoupleQuestManager:
    """道侣试炼：每周一道侣共同任务，完成后双方领奖"""

    def __init__(self, db: DataBase):
        self.db = db

    # ===== 存取 =====

    def _quest_key(self, uid: str) -> str:
        return f"couple_week_{current_week()}_{uid}"

    async def _load_quest(self, uid: str) -> Optional[Dict]:
        raw = await self.db.ext.get_system_config(self._quest_key(uid))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    async def _save_quest(self, uid: str, quest: Optional[Dict]):
        await self.db.ext.set_system_config(
            self._quest_key(uid), json.dumps(quest, ensure_ascii=False) if quest else ""
        )

    async def _ensure_quest(self, uid: str, npc_name: str) -> Dict:
        """取当周任务，不存在则从任务池随机一个"""
        quest = await self._load_quest(uid)
        if not quest:
            task = random.choice(COUPLE_QUEST_POOL)
            quest = {
                "action": task["action"],
                "target": task["target"],
                "text": task["text"],
                "progress": 0,
                "claimed": False,
                "npc": npc_name,
            }
            await self._save_quest(uid, quest)
        return quest

    async def get_companion_name(self, uid: str) -> Optional[str]:
        """查询仙灵道侣名（复用 npc_partners 表，与 social_manager 同方式）"""
        try:
            async with self.db.conn.execute(
                "SELECT npc_id FROM npc_partners WHERE user_id = ?", (uid,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"[道侣试炼] 查询道侣失败: {e}")
            return None

    # ===== 公开方法 =====

    async def record_action(self, player: Player, action: str, count: int = 1):
        """回调点：历练/签到/双修结算时由主控调用。无副作用、异常安全"""
        try:
            if action not in ("adventure", "checkin", "dual") or count <= 0:
                return
            uid = player.user_id
            quest = await self._load_quest(uid)
            if not quest or quest.get("claimed"):
                return
            if quest.get("action") != action:
                return
            if quest.get("progress", 0) >= quest.get("target", 1):
                return
            quest["progress"] = min(quest.get("target", 1), quest.get("progress", 0) + count)
            await self._save_quest(uid, quest)
        except Exception as e:
            logger.error(f"[道侣试炼] 记录进度失败: {e}")

    async def claim(self, player: Player) -> Tuple[bool, str]:
        """/道侣试炼 领取：完成当周任务后双方各得 8000 灵石 + 2 万修为（发给本人）"""
        try:
            uid = player.user_id
            npc_name = await self.get_companion_name(uid)
            if not npc_name:
                return False, (
                    "💔 你还没有仙灵道侣，无从双修。\n"
                    "发送 /仙灵结缘 查看五位仙灵并结缘，再来做道侣试炼吧！"
                )

            quest = await self._ensure_quest(uid, npc_name)
            if quest.get("claimed"):
                return False, "✅ 本周道侣试炼奖励已领取，下周再会（每周一次）。"
            if quest.get("progress", 0) < quest.get("target", 1):
                return False, (
                    f"⏳ 本周试炼未完成：{quest.get('text')}\n"
                    f"当前进度：{quest.get('progress', 0)}/{quest.get('target', 1)}"
                )

            quest["claimed"] = True
            await self._save_quest(uid, quest)

            # 奖励发给玩家本人（NPC 道侣无法持有资产，文本提示转告）
            await self.db.add_player_gold(uid, CLAIM_GOLD)
            await self.db.add_player_exp(uid, CLAIM_EXP)

            return True, (
                f"💞 道侣试炼完成！\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📋 任务：{quest.get('text')}\n"
                f"💗 道侣：【{npc_name}】\n"
                f"🎁 你获得：{CLAIM_GOLD:,} 灵石 + {CLAIM_EXP:,} 修为\n"
                f"🎁 {npc_name} 同样获得了等额奖赏（记得转告她/他一声）。\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💡 下周一刷新新的道侣共同任务。"
            )
        except Exception as e:
            logger.error(f"[道侣试炼] 领取失败: {e}")
            return False, "❌ 领取失败，请稍后再试。"

    async def handle_quest(self, player: Player, event) -> str:
        """/道侣试炼：无参查看进度，带「领取」参数领奖"""
        try:
            uid = player.user_id
            npc_name = await self.get_companion_name(uid)
            if not npc_name:
                return (
                    "💔 你还没有仙灵道侣。\n"
                    "发送 /仙灵结缘 查看五位仙灵，先结一段仙缘再来试炼吧！"
                )

            msg = (getattr(event, "message_str", "") or "") if event else ""
            if "领取" in msg or "领奖" in msg:
                ok, text = await self.claim(player)
                return text

            quest = await self._ensure_quest(uid, npc_name)
            progress = quest.get("progress", 0)
            target = quest.get("target", 1)
            done = progress >= target
            bar = "█" * min(target, progress) + "░" * max(0, target - progress)

            lines = [
                "💞 道侣试炼（每周一刷新）",
                "━━━━━━━━━━━━━━━",
                f"💗 道侣：【{npc_name}】",
                f"📋 本周任务：{quest.get('text')}",
                f"📊 进度：{progress}/{target} {''.join(bar)}",
            ]
            if quest.get("claimed"):
                lines.append("✅ 本周奖励已领取，下周再会。")
            elif done:
                lines.append("🎉 已达成！发送 /道侣试炼 领取 双方各得 8000 灵石 + 2 万修为")
            else:
                lines.append("🎁 奖励：完成后双方各得 8000 灵石 + 2 万修为")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"[道侣试炼] 查询失败: {e}")
            return "❌ 查询失败，请稍后再试。"
