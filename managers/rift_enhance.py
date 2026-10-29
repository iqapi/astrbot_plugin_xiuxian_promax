# managers/rift_enhance.py
"""秘境增强：每日全服词缀 + 秘境扫荡（v3.19.0 新玩法）

词缀接入点（主控负责）：
  managers/rift_manager.py finish_exploration() 计算 exp_reward/gold_reward 之后：
      from .rift_enhance import RiftEnhanceManager
      mod = await RiftEnhanceManager(self.db).get_modifier()
      if "exp_mult" in mod: exp_reward = int(exp_reward * mod["exp_mult"])
      if "gold_mult" in mod: gold_reward = int(gold_reward * mod["gold_mult"])
"""

import json
import random
import time
from typing import Tuple, Dict

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player
from ..models_extended import UserStatus

__all__ = ["RiftEnhanceManager"]


class RiftEnhanceManager:
    """秘境每日词缀 + 扫荡"""

    SWEEP_DAILY_LIMIT = 3     # 每天每种秘境扫荡次数
    SWEEP_RATE = 0.8          # 扫荡收益 = 平均收益的 80%
    SWEEP_FEE_RATE = 0.2      # 扫荡门票 = 基础灵石奖励均值的 20%

    AFFIXES = [
        {"name": "灵气潮汐", "desc": "秘境灵气异常充沛，探索修为 +50%", "exp_mult": 1.5, "weight": 20},
        {"name": "魔气反噬", "desc": "魔气弥漫，修为 -20%，但妖兽巢穴财宝更多（灵石 +50%）", "exp_mult": 0.8, "gold_mult": 1.5, "weight": 20},
        {"name": "机缘日", "desc": "天缘巧合，探索修为 +25%、灵石 +25%", "exp_mult": 1.25, "gold_mult": 1.25, "weight": 20},
        {"name": "大雾弥漫", "desc": "迷雾遮目，探索收益全面 -25%", "exp_mult": 0.75, "gold_mult": 0.75, "weight": 15},
        {"name": "风平浪静", "desc": "今日秘境一切如常", "weight": 25},
    ]

    def __init__(self, db: DataBase):
        self.db = db

    # ===== 每日词缀 =====

    async def ensure_today(self) -> dict:
        """获取（必要时生成）今日全服秘境词缀"""
        try:
            today = time.strftime("%Y%m%d")
            key = f"rift_affix_{today}"
            raw = await self.db.ext.get_system_config(key)
            if raw:
                try:
                    data = json.loads(raw)
                    if data.get("date") == today:
                        return data
                except (json.JSONDecodeError, TypeError):
                    pass
            total = sum(a["weight"] for a in self.AFFIXES)
            roll = random.randint(1, total)
            upto = 0
            chosen = self.AFFIXES[-1]
            for a in self.AFFIXES:
                upto += a["weight"]
                if roll <= upto:
                    chosen = a
                    break
            data = {"date": today, "name": chosen["name"], "desc": chosen["desc"],
                    "exp_mult": chosen.get("exp_mult", 1.0), "gold_mult": chosen.get("gold_mult", 1.0)}
            await self.db.ext.set_system_config(key, json.dumps(data, ensure_ascii=False))
            # 清理 7 天前的旧词缀，防 system_config 无限膨胀
            cutoff = int(time.strftime("%Y%m%d", time.localtime(time.time() - 7 * 86400)))
            try:
                await self.db.conn.execute("DELETE FROM system_config WHERE key LIKE 'rift_affix_%' AND CAST(SUBSTR(key, 12) AS INTEGER) < ?", (cutoff,))
                await self.db.conn.commit()
            except Exception:
                pass
            return data
        except Exception as e:
            logger.error(f"秘境词缀生成异常: {e}")
            return {"date": "", "name": "风平浪静", "desc": "今日秘境一切如常", "exp_mult": 1.0, "gold_mult": 1.0}

    async def get_modifier(self) -> dict:
        """获取今日词缀倍率（给结算处调用；永不抛异常，无词缀返回 {}）"""
        try:
            data = await self.ensure_today()
            mod = {}
            if data.get("exp_mult", 1.0) != 1.0:
                mod["exp_mult"] = data["exp_mult"]
            if data.get("gold_mult", 1.0) != 1.0:
                mod["gold_mult"] = data["gold_mult"]
            return mod
        except Exception:
            return {}

    async def handle_affix(self, event):
        """/秘境词缀 查看今日词缀"""
        data = await self.ensure_today()
        yield event.plain_result(
            f"🌀【今日秘境词缀】{data['name']}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"{data['desc']}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 每日全服共用一个词缀，出探索前先看看天时"
        )

    # ===== 秘境扫荡 =====

    def _sweep_key(self, user_id: str, rift_id: int) -> str:
        return f"sweep_{user_id}_{time.strftime('%Y%m%d')}_{rift_id}"

    async def sweep(self, player: Player, rift_id: int) -> Tuple[bool, str]:
        """/扫荡秘境 <编号>：战力碾压的秘境可跳过等待直领 80% 平均收益"""
        user_cd = await self.db.ext.get_user_cd(player.user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            return False, f"❌ 你当前正{UserStatus.get_name(user_cd.type)}，无法扫荡！"

        rift = await self.db.ext.get_rift_by_id(rift_id)
        if not rift:
            return False, "❌ 秘境不存在！使用 /秘境列表 查看可用秘境"

        # 战力碾压判定：境界超出需求 10 级以上才可扫荡
        if player.level_index < rift.required_level + 10:
            return False, (
                f"❌ 扫荡需要境界碾压：该秘境需境界 {rift.required_level}，"
                f"扫荡要求你的境界 ≥ {rift.required_level + 10}（当前 {player.level_index}）。"
            )

        # 每日限次（v3.23.0 原子认领）
        key = self._sweep_key(player.user_id, rift_id)
        if not await self.db.ext.syscfg_claim_slot(key, self.SWEEP_DAILY_LIMIT):
            return False, f"❌ 今日该秘境已扫荡 {self.SWEEP_DAILY_LIMIT} 次（每种秘境每日 3 次），明日再来。"
        used = await self.db.ext.syscfg_get_number(key)

        rewards_config = rift.get_rewards()
        exp_range = rewards_config.get("exp", [1000, 5000])
        gold_range = rewards_config.get("gold", [500, 2000])
        avg_exp = (exp_range[0] + exp_range[1]) // 2
        avg_gold = (gold_range[0] + gold_range[1]) // 2

        exp_reward = int(avg_exp * self.SWEEP_RATE)
        gold_reward = int(avg_gold * self.SWEEP_RATE)
        fee = int(avg_gold * self.SWEEP_FEE_RATE)

        # v3.23.0：费用与奖励全走原子接口（不再整行覆写 player 快照）
        fresh = await self.db.get_player_by_id(player.user_id)
        if not fresh or fresh.gold < fee:
            return False, f"❌ 扫荡需缴纳门票 {fee:,} 灵石（当前持有 {fresh.gold if fresh else 0:,}）。"
        await self.db.add_player_gold(player.user_id, gold_reward - fee)
        await self.db.add_player_exp(player.user_id, exp_reward)

        return True, (
            f"⚡【扫荡】{rift.rift_name}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"你以碾压之势荡平秘境，收获颇丰：\n"
            f"📈 修为：+{exp_reward:,}\n"
            f"💰 灵石：+{gold_reward:,}（门票 -{fee:,}）\n"
            f"━━━━━━━━━━━━━━━\n"
            f"今日剩余扫荡次数：{self.SWEEP_DAILY_LIMIT - used - 1}\n"
            f"💡 手动探索收益期望更高且可能掉落物品，扫荡胜在省时"
        )
