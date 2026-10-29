# managers/ascension_project_manager.py
"""登仙台 · 全服世界工程（v3.22.0 新玩法）

全服共建一座登仙台：所有人 /助登仙台 <灵石> 捐资，达到阶段目标自动进阶：
- 6 个阶段：残垣→基石→台身→灵坛→仙门→通天（需求 5万/15万/40万/100万/250万/600万）
- 每进阶一阶：全服每人发奖（灵石+修为）+ 全服永久修炼加成 +1%（满阶 +6%）
- 全服集体目标，天然产生"差一点就够"的群聊动员场景
"""

import json
from typing import Tuple

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["AscensionProjectManager"]


class AscensionProjectManager:
    """登仙台世界工程"""

    STAGES = [
        {"name": "残垣", "need": 50000},
        {"name": "基石", "need": 150000},
        {"name": "台身", "need": 400000},
        {"name": "灵坛", "need": 1000000},
        {"name": "仙门", "need": 2500000},
        {"name": "通天", "need": 6000000},
    ]
    STAGE_NAMES = ["残垣", "基石", "台身", "灵坛", "仙门", "通天"]
    REWARD_GOLD_PER_STAGE = [300, 800, 2000, 5000, 12000, 30000]   # 进阶全服奖励（每人）
    REWARD_EXP_PER_STAGE = [500, 1500, 4000, 10000, 25000, 60000]
    BONUS_PER_STAGE = 0.01    # 每阶段全服修炼加成 +1%

    def __init__(self, db: DataBase):
        self.db = db

    def _key(self) -> str:
        return "ascension_project"

    async def _load(self) -> dict:
        raw = await self.db.ext.get_system_config(self._key())
        if not raw:
            return {"stage": 0, "funds": 0}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {"stage": 0, "funds": 0}
        except (json.JSONDecodeError, TypeError):
            return {"stage": 0, "funds": 0}

    async def get_bonus(self) -> float:
        """全服登仙台修炼加成（供闭关结算；异常安全返回 0.0）"""
        try:
            stage = await self.db.ext.syscfg_get_number("ascension_stage")
            return min(0.06, stage * self.BONUS_PER_STAGE)
        except Exception:
            return 0.0

    async def donate(self, player: Player, amount: int) -> Tuple[bool, str]:
        """/助登仙台 <灵石>
        v3.23.0 原子化：funds 用数值键原子累加、stage 用 CAS 抢占进阶权，
        并发捐献不再双发全服阶段奖励；先落库再发奖，崩溃不重发。"""
        if not (100 <= amount <= 1000000):
            return False, "❌ 单次捐献需在 100 - 1,000,000 灵石之间。"
        if player.gold < amount:
            return False, f"❌ 灵石不足（当前持有 {player.gold:,}）。"

        stage = await self.db.ext.syscfg_get_number("ascension_stage")
        if stage >= len(self.STAGES):
            return False, "⛩️ 登仙台已通天完工，全服共享仙泽。无需再捐。"

        await self.db.add_player_gold(player.user_id, -amount)
        funds = await self.db.ext.syscfg_adjust_number("ascension_funds", amount)
        lines = [f"⛩️ 你为登仙台捐献了 {amount:,} 灵石！（累计 {funds:,}）"]

        # 阶段进阶检查（CAS 抢占每一阶的进阶权，抢到者才发全服奖）
        while stage < len(self.STAGES) and funds >= self.STAGES[stage]["need"]:
            claimed = await self.db.ext.syscfg_cas(
                "ascension_stage", str(stage + 1), str(stage)
            )
            if not claimed:
                break  # 其他并发捐献者已完成本阶进阶
            stage += 1
            gold_reward = self.REWARD_GOLD_PER_STAGE[stage - 1]
            exp_reward = self.REWARD_EXP_PER_STAGE[stage - 1]
            # v3.24.0 轻量查询 + 批量 SQL 发放（不再逐人构造完整 Player 对象）
            player_ids = await self.db.get_all_player_ids()
            await self.db.conn.execute(
                "UPDATE players SET gold = gold + ?, experience = experience + ?",
                (gold_reward, exp_reward)
            )
            await self.db.conn.commit()
            lines.append(
                f"\n⛩️【登仙台进阶 · {self.STAGE_NAMES[stage - 1]} → {self.STAGE_NAMES[stage] if stage < len(self.STAGE_NAMES) else '通天完工'}】\n"
                f"全服 {len(player_ids)} 位道友各得：{gold_reward:,} 灵石 + {exp_reward:,} 修为！\n"
                f"全服修炼加成提升至 +{min(6, stage)}%！"
            )
        return True, "\n".join(lines)

    async def handle_board(self, event) -> str:
        """/登仙台 查看进度"""
        stage = await self.db.ext.syscfg_get_number("ascension_stage")
        funds = await self.db.ext.syscfg_get_number("ascension_funds")
        lines = ["⛩️【登仙台 · 全服世界工程】", "━━━━━━━━━━━━━━━"]
        for i, name in enumerate(self.STAGE_NAMES):
            if i < stage:
                lines.append(f"✅ {name}（已建成）")
            elif i == stage and stage < len(self.STAGES):
                need = self.STAGES[i]["need"]
                prev_need = self.STAGES[i - 1]["need"] if i > 0 else 0
                cur = funds - prev_need
                span = need - prev_need
                pct = min(100, int(cur * 100 / max(1, span)))
                lines.append(f"🔧 {name} 建设中：{cur:,}/{span:,} 灵石（{pct}%）")
            else:
                lines.append(f"🔒 {name}")
        lines.append("━━━━━━━━━━━━━━━")
        if stage >= len(self.STAGE_NAMES):
            lines.append(f"⛩️ 登仙台已通天！全服修炼加成 +{min(6, stage)}% 永久生效。")
        else:
            lines.append(f"🌟 当前全服修炼加成：+{min(6, stage)}%")
            lines.append("💡 /助登仙台 <灵石> 共襄盛举，每进阶一阶全服人人有奖！")
        return "\n".join(lines)

    async def cleanup_check(self) -> str:
        """定时兜底：无（阶段进阶在捐献时即时结算，无需定时）。保留接口以备扩展"""
        return ""
