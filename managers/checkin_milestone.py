# managers/checkin_milestone.py
"""签到里程碑 v6.18 - 按自然月累计签到次数发放阶梯灵石奖励"""
import json
import time
from typing import List

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["CheckinMilestoneManager"]


class CheckinMilestoneManager:
    """自然月累计签到里程碑：7/15/25 天各一档，奖励仅灵石资源。
    状态存 system_config：
      ckms_{uid}_{YYYYMM}          = 本月累计签到次数（换月天然重置）
      ckms_claimed_{uid}_{YYYYMM}  = 本月已领档位天数列表（JSON）
    注：on_checkin 须在签到处理成功后调用（每日仅成功签到一次）。"""

    MILESTONES = [
        {"days": 7, "gold": 3000},
        {"days": 15, "gold": 8000},
        {"days": 25, "gold": 20000},
    ]

    def __init__(self, db: DataBase):
        self.db = db

    # ================= 内部工具 =================

    @staticmethod
    def _month_tag() -> str:
        return time.strftime("%Y%m")

    @staticmethod
    def _month_name(tag: str) -> str:
        try:
            return f"{int(tag[:4])}年{int(tag[4:6])}月"
        except Exception:
            return tag

    async def _get_count(self, user_id: str) -> int:
        try:
            raw = await self.db.ext.get_system_config(
                f"ckms_{user_id}_{self._month_tag()}"
            )
            return int(raw) if raw and str(raw).strip().isdigit() else 0
        except Exception:
            return 0

    async def _load_claimed(self, user_id: str) -> List[int]:
        try:
            raw = await self.db.ext.get_system_config(
                f"ckms_claimed_{user_id}_{self._month_tag()}"
            )
            data = json.loads(raw) if raw else []
            return data if isinstance(data, list) else []
        except Exception:
            return []

    async def _save_claimed(self, user_id: str, claimed: List[int]):
        try:
            await self.db.ext.set_system_config(
                f"ckms_claimed_{user_id}_{self._month_tag()}", json.dumps(claimed)
            )
        except Exception:
            logger.error(f"【签到里程碑】保存已领档位失败 uid={user_id}")

    # ================= 核心逻辑 =================

    async def on_checkin(self, player: Player) -> str:
        """签到成功后调用：累计本月签到数并发放达标档位奖励。
        返回奖励提示文本（可为空）。"""
        try:
            user_id = player.user_id
            count = await self._get_count(user_id) + 1
            await self.db.ext.set_system_config(
                f"ckms_{user_id}_{self._month_tag()}", str(count)
            )

            claimed = await self._load_claimed(user_id)
            new_claims = [
                ms for ms in self.MILESTONES
                if ms["days"] not in claimed and count >= ms["days"]
            ]
            if not new_claims:
                return ""

            msgs = []
            for ms in new_claims:
                claimed.append(ms["days"])
                await self.db.add_player_gold(user_id, ms["gold"])
                msgs.append(
                    f"\n🏅【签到里程碑】本月累计签到 {ms['days']} 天！"
                    f"奖励 {ms['gold']:,} 灵石！"
                )
            await self._save_claimed(user_id, claimed)
            return "".join(msgs)
        except Exception as e:
            logger.error(f"【签到里程碑】on_checkin 异常: {e}")
            return ""

    # ================= 指令展示 =================

    async def handle_milestone(self, player: Player, event):
        """/签到里程碑 指令：输出本月进度与各档位奖励状态。"""
        try:
            user_id = player.user_id
            tag = self._month_tag()
            count = await self._get_count(user_id)
            claimed = await self._load_claimed(user_id)

            lines = [
                f"📅 签到里程碑（{self._month_name(tag)}）",
                "━━━━━━━━━━━━━━━",
                f"本月累计签到：{count} 天",
                "",
            ]
            for ms in self.MILESTONES:
                status = "✅ 已领取" if ms["days"] in claimed else (
                    "🎯 已达成" if count >= ms["days"] else "🔒 未达成"
                )
                lines.append(f"  {status} 累计 {ms['days']} 天：{ms['gold']:,} 灵石")

            next_ms = next(
                (ms for ms in self.MILESTONES
                 if ms["days"] not in claimed and count < ms["days"]),
                None,
            )
            lines.append("━━━━━━━━━━━━━━━")
            if next_ms:
                lines.append(f"🎯 下一档：{next_ms['days']} 天，还差 {next_ms['days'] - count} 天")
            else:
                lines.append("🏆 本月档位已全部领取，月月坚持，道行日深！")
            lines.append("💡 每自然月进度独立计算，月初重新开始累计")
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            logger.error(f"【签到里程碑】handle_milestone 异常: {e}")
            yield event.plain_result("❌ 里程碑查询失败，请稍后再试。")
