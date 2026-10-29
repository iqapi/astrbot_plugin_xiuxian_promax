# managers/lucky_wheel_manager.py
"""幸运罗盘（v3.20.0 新玩法）

8 格奖池按权重抽取：
- 每日 1 次免费（/罗盘）
- 付费 1000 灵石/次（/罗盘 抽 <次数>），每日付费上限 5 次
- 状态全部存 system_config（不建新表）
"""

import json
import time
import random
from typing import Tuple

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["LuckyWheelManager"]


class LuckyWheelManager:
    """幸运罗盘：免费/付费抽奖，灵石与修为奖励"""

    FREE_PER_DAY = 1        # 每日免费次数
    PAID_COST = 1000        # 付费单价（灵石/次）
    PAID_LIMIT = 5          # 每日付费次数上限

    # 奖池 8 格（权重合计 100）
    SLOTS = [
        {"name": "谢谢参与",   "icon": "💨", "type": "none",  "value": 0,     "weight": 25},
        {"name": "100 灵石",   "icon": "🪙", "type": "gold",  "value": 100,   "weight": 20},
        {"name": "500 灵石",   "icon": "💰", "type": "gold",  "value": 500,   "weight": 18},
        {"name": "1000 灵石",  "icon": "💵", "type": "gold",  "value": 1000,  "weight": 12},
        {"name": "3000 修为",  "icon": "✨", "type": "exp",   "value": 3000,  "weight": 10},
        {"name": "2000 灵石",  "icon": "🧧", "type": "gold",  "value": 2000,  "weight": 8},
        {"name": "8000 修为",  "icon": "🌟", "type": "exp",   "value": 8000,  "weight": 5},
        {"name": "大奖 10000 灵石", "icon": "🎊", "type": "gold", "value": 10000, "weight": 2},
    ]

    def __init__(self, db: DataBase):
        self.db = db

    # ================= 内部工具 =================

    def _free_key(self, uid: str) -> str:
        return f"wheel_free_{uid}_{time.strftime('%Y%m%d')}"

    def _paid_key(self, uid: str) -> str:
        return f"wheel_paid_{uid}_{time.strftime('%Y%m%d')}"

    async def _get_cnt(self, key: str) -> int:
        try:
            raw = await self.db.ext.get_system_config(key)
            return int(raw) if raw else 0
        except Exception:
            return 0

    async def _set_cnt(self, key: str, val: int):
        await self.db.ext.set_system_config(key, str(val))

    # ================= 核心接口 =================

    async def spin(self, player: Player, paid: bool) -> Tuple[bool, str]:
        """转动一次罗盘：paid=False 为每日免费抽，paid=True 为付费抽（1000 灵石/次）。
        v3.23.0：限次/扣费全部走原子设施（syscfg_claim_slot / syscfg_spend），并发不可绕过。"""
        uid = player.user_id
        if paid:
            if not await self.db.ext.syscfg_claim_slot(self._paid_key(uid), self.PAID_LIMIT):
                return False, f"❌ 今日付费抽取已达上限（{self.PAID_LIMIT} 次），明日再来！"
            # 余额用数据库实时值原子扣减（不用命令开始时的快照）
            fresh = await self.db.get_player_by_id(uid)
            if not fresh or fresh.gold < self.PAID_COST:
                # 退回次数占用并提示
                await self.db.ext.syscfg_adjust_number(self._paid_key(uid), -1)
                balance = fresh.gold if fresh else 0
                return False, f"❌ 灵石不足！付费转动需 {self.PAID_COST:,} 灵石（当前持有 {balance:,}）。"
            await self.db.add_player_gold(uid, -self.PAID_COST)
        else:
            if not await self.db.ext.syscfg_claim_slot(self._free_key(uid), self.FREE_PER_DAY):
                return False, (
                    "❌ 今日免费转动已用完！\n"
                    f"💡 可用 /罗盘 抽 <次数> 付费转动（{self.PAID_COST:,} 灵石/次，每日限 {self.PAID_LIMIT} 次）"
                )

        # 按权重抽取
        slot = random.choices(self.SLOTS, weights=[s["weight"] for s in self.SLOTS], k=1)[0]

        # 发放奖励
        gain_text = "💨 什么都没抽到…"
        try:
            if slot["type"] == "gold":
                await self.db.add_player_gold(uid, slot["value"])
                gain_text = f"{slot['icon']} 获得 {slot['value']:,} 灵石！"
            elif slot["type"] == "exp":
                await self.db.add_player_exp(uid, slot["value"])
                gain_text = f"{slot['icon']} 获得 {slot['value']:,} 修为！"
        except Exception as e:
            logger.error(f"[wheel] 发放奖励失败: {e}")
            return False, "❌ 奖励发放失败，请联系管理员核查。"

        return True, (
            f"🎡【幸运罗盘】指针飞速旋转……\n"
            f"━━━━━━━━━━━━━━━\n"
            f"停在：{slot['icon']}【{slot['name']}】\n"
            f"{gain_text}"
        )

    # ================= 指令入口 =================

    async def handle_wheel(self, player: Player, event, arg: str = ""):
        """统一入口：/罗盘（免费抽）· /罗盘 抽 <次数>（付费抽）"""
        arg = (arg or "").strip()
        if not arg:
            ok, msg = await self.spin(player, paid=False)
            yield event.plain_result(msg)
            return

        # "抽 N"
        parts = arg.split()
        if parts[0] not in ("抽", "抽奖", "转") or len(parts) < 2:
            yield event.plain_result(
                "❌ 用法：/罗盘（每日免费 1 次）\n"
                f"   /罗盘 抽 <次数>（{self.PAID_COST:,} 灵石/次，每日限 {self.PAID_LIMIT} 次）"
            )
            return
        try:
            times = int(parts[1])
        except ValueError:
            yield event.plain_result("❌ 次数需为数字，如 /罗盘 抽 3")
            return
        if not (1 <= times <= self.PAID_LIMIT):
            yield event.plain_result(f"❌ 付费次数需在 1 - {self.PAID_LIMIT} 之间。")
            return

        results = []
        total_cost = 0
        for _ in range(times):
            ok, msg = await self.spin(player, paid=True)
            results.append(msg)
            if not ok:
                break
            total_cost += self.PAID_COST

        lines = [f"🎡【幸运罗盘 · {len([r for r in results if not r.startswith('❌')])}/{times} 连抽】"]
        for i, msg in enumerate(results, start=1):
            # 只保留结果行
            tail = msg.split("━━━━━━━━━━━━━━━")[-1].strip()
            lines.append(f"▸ 第{i}抽：{tail}")
        lines.append(f"💸 本次共消耗 {total_cost:,} 灵石")
        yield event.plain_result("\n".join(lines))
