# managers/spirit_tide_manager.py
"""灵潮事件（v3.32.0 新玩法）：全服随机增益窗口

- 主控定时任务每 5 分钟掷骰：每个 30 分钟时段至多判定一次（CAS 防重复），18% 概率开启灵潮
- 灵潮持续 25 分钟：全服闭关/历练修为收益 +30%（由出关结算与历练结算读取接线）
- 状态仅两个 system_config 键（lichao_until / lichao_roll_{slot}），无新表
"""

import random
import time

from astrbot.api import logger

from ..data.data_manager import DataBase

__all__ = ["SpiritTideManager"]


class SpiritTideManager:
    """灵潮：天地灵气涨落，机缘不可强求"""

    UNTIL_KEY = "lichao_until"
    ROLL_PREFIX = "lichao_roll_"
    SLOT_SECONDS = 1800        # 每 30 分钟一个判定时段
    CHANCE = 0.18              # 开启概率
    DURATION = 1500            # 持续 25 分钟
    BONUS = 0.30               # 收益加成 +30%

    def __init__(self, db: DataBase):
        self.db = db

    async def is_active(self) -> bool:
        until = await self.db.ext.get_system_config(self.UNTIL_KEY)
        try:
            return bool(until) and int(time.time()) < int(until)
        except (TypeError, ValueError):
            return False

    async def remain_seconds(self) -> int:
        until = await self.db.ext.get_system_config(self.UNTIL_KEY)
        try:
            return max(0, int(until) - int(time.time())) if until else 0
        except (TypeError, ValueError):
            return 0

    async def maybe_start(self) -> str:
        """主控定时调用：判定是否开启灵潮。返回广播文案（空=无事发生）"""
        now = int(time.time())
        if await self.is_active():
            return ""
        slot = now // self.SLOT_SECONDS
        # CAS 抢占本时段判定权（多实例/重复触发只掷一次）
        claimed = await self.db.ext.syscfg_cas(f"{self.ROLL_PREFIX}{slot}", "1", None)
        if not claimed:
            return ""
        if random.random() >= self.CHANCE:
            return ""
        await self.db.ext.set_system_config(self.UNTIL_KEY, str(now + self.DURATION))
        logger.info(f"[灵潮] 灵潮开启，持续 {self.DURATION // 60} 分钟")
        return (
            "🌌【天地异象】灵潮汹涌而至！\n"
            "━━━━━━━━━━━━━━━\n"
            f"磅礴灵气自地脉喷涌，未来 {self.DURATION // 60} 分钟内全服\n"
            f"闭关/历练修为收益 +{int(self.BONUS * 100)}%！\n"
            "━━━━━━━━━━━━━━━\n"
            "💡 机不可失：/闭关 /开始历练 /除妖 马上安排！"
        )

    async def get_status(self) -> str:
        active = await self.is_active()
        remain = await self.remain_seconds()
        lines = ["🌌【灵潮观测】", "━━━━━━━━━━━━━━━"]
        if active:
            lines.append(f"🌊 灵潮汹涌中！全服闭关/历练修为 +{int(self.BONUS * 100)}%")
            lines.append(f"⏳ 剩余：{remain // 60} 分 {remain % 60} 秒")
            lines.append("💡 /闭关 或 /开始历练 立刻吃满增益！")
        else:
            lines.append("🌫 灵潮平息，地脉如常。")
            lines.append("💡 灵潮随机降临（每 30 分钟一判，18% 概率），留意全服播报")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("💡 灵潮为全服共享增益，与天气/求签/道心等个人加成可叠加")
        return "\n".join(lines)
