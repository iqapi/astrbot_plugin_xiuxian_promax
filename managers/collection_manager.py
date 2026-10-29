# managers/collection_manager.py
"""图鉴收集奖励 v6.18 - 按称号收集数发放永久修为加成与灵石奖励"""
import json
from typing import List

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["CollectionManager"]


class CollectionManager:
    """称号图鉴收集里程碑：集齐 10/30/60/90 个称号触发档位奖励。
    档位状态存 system_config：collect_{user_id} = JSON 已领档位称号数列表
    永久修为加成写入 player.permanent_bonus 的 "collect_bonus" 键（小数，如 0.05）。"""

    MILESTONES = [
        {"count": 10, "exp": 0.02, "gold": 5000},
        {"count": 30, "exp": 0.05, "gold": 20000},
        {"count": 60, "exp": 0.08, "gold": 50000},
        {"count": 90, "exp": 0.12, "gold": 100000},
    ]

    KEY_PREFIX = "collect_"
    BONUS_KEY = "collect_bonus"

    def __init__(self, db: DataBase, title_mgr):
        self.db = db
        self.title_mgr = title_mgr

    # ================= 内部工具 =================

    async def _load_claimed(self, user_id: str) -> List[int]:
        try:
            raw = await self.db.ext.get_system_config(f"{self.KEY_PREFIX}{user_id}")
            data = json.loads(raw) if raw else []
            return data if isinstance(data, list) else []
        except Exception:
            return []

    async def _save_claimed(self, user_id: str, claimed: List[int]):
        try:
            await self.db.ext.set_system_config(
                f"{self.KEY_PREFIX}{user_id}", json.dumps(claimed)
            )
        except Exception:
            logger.error(f"【图鉴收集】保存档位状态失败 uid={user_id}")

    def _set_bonus(self, player: Player, total_exp: float):
        """把图鉴总修为加成写入 permanent_bonus["collect_bonus"]。"""
        try:
            data = json.loads(player.permanent_bonus) if player.permanent_bonus else {}
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        data[self.BONUS_KEY] = round(total_exp, 4)
        player.permanent_bonus = json.dumps(data, ensure_ascii=False)

    # ================= 核心逻辑 =================

    async def check_and_grant(self, player: Player) -> str:
        """检查称号收集数并发放未领档位。幂等，可被频繁调用。
        返回奖励提示文本（可为空）。"""
        try:
            owned = self.title_mgr._load_owned(player)
            owned_count = len(owned)
            claimed = await self._load_claimed(player.user_id)

            msgs = []
            new_claims = []
            for ms in self.MILESTONES:
                if ms["count"] in claimed or owned_count < ms["count"]:
                    continue
                new_claims.append(ms)

            if not new_claims:
                return ""

            # v3.23.0：CAS 抢占领取记录（签到钩子与 /收集图鉴 并发不再双发）
            claimed_key = f"collect_{player.user_id}"
            new_claimed = claimed + [ms["count"] for ms in new_claims]
            claimed_ok = await self.db.ext.syscfg_cas(
                claimed_key, json.dumps(new_claimed), json.dumps(claimed)
            )
            if not claimed_ok:
                return ""
            claimed = new_claimed

            for ms in new_claims:
                await self.db.add_player_gold(player.user_id, ms["gold"])
                msgs.append(
                    f"\n🎁【图鉴里程碑】称号收集达 {ms['count']} 个！"
                    f"奖励 {ms['gold']:,} 灵石，永久修为获取 +{int(ms['exp'] * 100)}%！"
                )

            # 重算总加成（全量，保证与已领档位一致）
            total_exp = sum(
                ms["exp"] for ms in self.MILESTONES if ms["count"] in claimed
            )
            self._set_bonus(player, total_exp)
            await self.db.update_player(player)

            return "".join(msgs)
        except Exception as e:
            logger.error(f"【图鉴收集】check_and_grant 异常: {e}")
            return ""

    @staticmethod
    def get_exp_bonus(player: Player) -> float:
        """从 permanent_bonus 读取图鉴修为加成（小数，无则 0）。永不抛异常。"""
        try:
            data = json.loads(player.permanent_bonus) if player.permanent_bonus else {}
            if isinstance(data, dict):
                val = data.get(CollectionManager.BONUS_KEY, 0)
                return float(val) if isinstance(val, (int, float)) else 0.0
        except Exception:
            pass
        return 0.0

    # ================= 指令展示 =================

    async def handle_collection(self, player: Player, event):
        """/收集图鉴 指令：输出进度、各档位状态、下一档差距。"""
        try:
            owned = self.title_mgr._load_owned(player)
            owned_count = len(owned)
            claimed = await self._load_claimed(player.user_id)
            total_exp = sum(
                ms["exp"] for ms in self.MILESTONES if ms["count"] in claimed
            )

            lines = [
                f"📜 图鉴收集计划（当前称号 {owned_count} 个）",
                "━━━━━━━━━━━━━━━",
            ]
            for ms in self.MILESTONES:
                status = "✅ 已领取" if ms["count"] in claimed else (
                    "🎯 已达成，速来领取" if owned_count >= ms["count"] else "🔒 未达成"
                )
                lines.append(
                    f"  {status} 集 {ms['count']} 称号："
                    f"{ms['gold']:,} 灵石 + 永久修为 +{int(ms['exp'] * 100)}%"
                )

            next_ms = next(
                (ms for ms in self.MILESTONES
                 if ms["count"] not in claimed and owned_count < ms["count"]),
                None,
            )
            lines.append("━━━━━━━━━━━━━━━")
            if next_ms:
                lines.append(
                    f"🎯 下一档：集 {next_ms['count']} 称号，还差 {next_ms['count'] - owned_count} 个"
                )
            else:
                lines.append("🏆 已领取全部档位奖励，收集之道登峰造极！")
            if total_exp > 0:
                lines.append(f"✨ 当前图鉴加成：永久修为获取 +{int(total_exp * 100)}%")
            lines.append("💡 称号通过突破、历练、决斗等途径获得，发送 /称号图鉴 查看")
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            logger.error(f"【图鉴收集】handle_collection 异常: {e}")
            yield event.plain_result("❌ 图鉴查询失败，请稍后再试。")
