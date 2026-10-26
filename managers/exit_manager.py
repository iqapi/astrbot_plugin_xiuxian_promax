# managers/exit_manager.py
"""提前退出系统 v6.18：秘境/历练 中途退出按已进行时长比例结算奖励（向下取整）"""
import time
from typing import Tuple

from ..data.data_manager import DataBase
from ..models import Player
from ..models_extended import UserStatus

__all__ = ["ExitManager"]


class ExitManager:
    def __init__(self, db: DataBase):
        self.db = db

    async def early_exit(self, player: Player) -> Tuple[bool, str]:
        """提前退出当前挂机活动（历练/秘境），按比例结算"""
        user_id = player.user_id
        user_cd = await self.db.ext.get_user_cd(user_id)
        if not user_cd:
            return False, "❌ 你当前没有进行中的挂机活动（历练/秘境）。"

        if user_cd.type == UserStatus.ADVENTURING:
            return await self._exit_adventure(player, user_cd)
        elif user_cd.type == UserStatus.EXPLORING:
            return await self._exit_rift(player, user_cd)
        else:
            status_name = UserStatus.get_name(user_cd.type)
            return False, (
                f"❌ 当前状态【{status_name}】不支持提前退出。\n"
                f"💡 仅历练/秘境支持按比例结算退出；其余活动请走对应指令。"
            )

    async def _exit_adventure(self, player: Player, user_cd) -> Tuple[bool, str]:
        """历练提前退出：按已进行时长比例结算该路线收益"""
        import json as _json
        extra = {}
        try:
            extra = user_cd.get_extra_data() if hasattr(user_cd, "get_extra_data") else _json.loads(user_cd.extra_data or "{}")
        except Exception:
            extra = {}
        route_key = extra.get("route_key", "scout")

        from .adventure_manager import AdventureManager
        adv = AdventureManager(self.db, None)  # 无储物戒依赖（不处理掉落）
        route = adv.routes.get(route_key) or next(iter(adv.routes.values()))

        now = int(time.time())
        elapsed = max(0, now - user_cd.create_time)
        full_duration = max(1, user_cd.scheduled_time - user_cd.create_time)
        ratio = min(1.0, elapsed / full_duration)

        # 比例结算（向下取整）：基础收益 × 时间比例（不含完成奖励——未完成没有完成奖）
        minutes = max(0, elapsed // 60)
        base_exp = minutes * route.get("base_exp_per_min", 40)
        base_gold = minutes * route.get("base_gold_per_min", 10)
        level_bonus_exp = player.level_index * route.get("level_bonus_exp", 10)
        level_bonus_gold = player.level_index * route.get("level_bonus_gold", 2)
        exp_reward = int((base_exp + level_bonus_exp * (minutes / max(1, full_duration // 60))))
        gold_reward = int((base_gold + level_bonus_gold * (minutes / max(1, full_duration // 60))))

        # 状态清空（不发完成奖励、不触发奇遇/悬赏/疲劳）
        await self.db.ext.set_user_free(user_id)

        player.gold += gold_reward
        player.experience += exp_reward
        await self.db.update_player(player)

        pct = f"{ratio * 100:.0f}%"
        return True, (
            f"🏃 提前退出历练【{route['name']}】\n"
            f"━━━━━━━━━━━━━━━\n"
            f"已进行：{minutes} 分钟（完成度 {pct}）\n"
            f"按比例结算（向下取整，无完成奖励）：\n"
            f"  修为：+{exp_reward:,}\n"
            f"  灵石：+{gold_reward:,}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 坚持完成可获得完成奖励与物品掉落"
        )

    async def _exit_rift(self, player: Player, user_cd) -> Tuple[bool, str]:
        """秘境提前退出：按已进行时长比例结算该秘境奖励区间中值（向下取整，无物品掉落）"""
        import json as _json
        extra = {}
        try:
            extra = user_cd.get_extra_data() if hasattr(user_cd, "get_extra_data") else _json.loads(user_cd.extra_data or "{}")
        except Exception:
            extra = {}
        rift_id = extra.get("rift_id", 0)
        rift = await self.db.ext.get_rift_by_id(rift_id) if rift_id else None

        if rift:
            rewards_cfg = rift.get_rewards()
            exp_range = rewards_cfg.get("exp", [1000, 5000])
            gold_range = rewards_cfg.get("gold", [500, 2000])
            rift_name = rift.rift_name
        else:
            exp_range, gold_range, rift_name = [1000, 5000], [500, 2000], "未知秘境"

        now = int(time.time())
        elapsed = max(0, now - user_cd.create_time)
        full_duration = max(1, user_cd.scheduled_time - user_cd.create_time)
        ratio = min(1.0, elapsed / full_duration)

        # 区间中值 × 时间比例（向下取整）
        exp_mid = (exp_range[0] + exp_range[1]) // 2
        gold_mid = (gold_range[0] + gold_range[1]) // 2
        exp_reward = int(exp_mid * ratio)
        gold_reward = int(gold_mid * ratio)

        await self.db.ext.set_user_free(user_id)

        player.gold += gold_reward
        player.experience += exp_reward
        await self.db.update_player(player)

        pct = f"{ratio * 100:.0f}%"
        minutes = max(0, elapsed // 60)
        return True, (
            f"🏃 提前退出秘境【{rift_name}】\n"
            f"━━━━━━━━━━━━━━━\n"
            f"已探索：{minutes} 分钟（完成度 {pct}）\n"
            f"按比例结算（区间中值×完成度，向下取整，无物品掉落）：\n"
            f"  修为：+{exp_reward:,}\n"
            f"  灵石：+{gold_reward:,}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 坚持完成可获得全额奖励与稀有物品掉落"
        )
