# managers/encounter_manager.py
"""奇遇选项系统 - Roguelike 文字探险（历练/秘境归来概率触发三选一事件）"""
import time
import random
import json
from typing import Tuple, Optional, Dict, List

from ..data.data_manager import DataBase
from ..models import Player
from .encounter_events import EVENTS as EVENT_POOL

__all__ = ["EncounterManager"]


class EncounterManager:
    """奇遇管理器：触发后在限时内回复 /奇遇选择 <编号> 结算
    奖励随境界双向缩放（低境界打折/高境界放大），封顶4倍"""

    CHOICE_EXPIRE = 180      # 选择有效期（秒）
    STORAGE_KEY_PREFIX = "encounter_"

    def __init__(self, db: DataBase, storage_ring_mgr=None):
        self.db = db
        self.storage_ring_mgr = storage_ring_mgr
        self.events = {ev["key"]: ev for ev in EVENT_POOL}

    def _storage_key(self, user_id: str) -> str:
        return f"{self.STORAGE_KEY_PREFIX}{user_id}"

    # v3.18.4 数值平衡：奇遇奖励改为"低境界打折、高境界放大"的双向缩放。
    # 旧公式 (1 + 0.12*lv, 下限1) 会让炼气期抽中 25,000 灵石级事件（数日历练收入）
    REWARD_SCALE_PER_LEVEL = 0.08
    REWARD_SCALE_MAX = 4.0
    REWARD_SCALE_MIN = 0.2

    def _reward_scale(self, player: Player) -> float:
        return max(self.REWARD_SCALE_MIN, min(
            self.REWARD_SCALE_MAX,
            self.REWARD_SCALE_MIN + (player.level_index or 0) * self.REWARD_SCALE_PER_LEVEL
        ))

    def _level_gold_cap(self, player: Player) -> int:
        """单次奇遇灵石收益上限随境界增长（炼气 2,800 → 满级 30,000）"""
        return 2000 + (player.level_index or 0) * 800

    async def maybe_trigger(self, player: Player, base_chance: int = 20) -> Optional[str]:
        """历练(20%)/秘境(25%)归来时调用，概率触发奇遇。返回提示文本（None 表示未触发）"""
        # 功德越高奇遇越容易触发（每点+2%，上限+20%）
        chance = base_chance + max(0, min(10, getattr(player, "karma", 0) or 0) * 2)
        # v3.19.0 天象：魔风/大雾提升奇遇触发率（异常安全）
        try:
            from .weather_manager import WeatherManager
            em = await WeatherManager(self.db).get_multiplier("encounter")
            chance = int(chance * em)
        except Exception:
            pass
        # v3.22.0 惊签：奇遇触发加成（异常安全）
        try:
            from .fortune_stick_manager import FortuneStickManager
            chance = int(chance * (1 + await FortuneStickManager(self.db).get_adventure_bonus(player)))
        except Exception:
            pass
        if random.randint(1, 100) > chance:
            return None

        # 已有未结算的奇遇则不再叠加（但已过期的残留自动清除）
        existing = await self.db.ext.get_system_config(self._storage_key(player.user_id))
        if existing:
            try:
                old_payload = json.loads(existing)
                if int(time.time()) > int(old_payload.get("expire", 0)):
                    # 过期残留：清除并继续本次触发
                    await self.db.ext.set_system_config(self._storage_key(player.user_id), "")
                else:
                    return None  # 真正未结算且未过期
            except Exception:
                await self.db.ext.set_system_config(self._storage_key(player.user_id), "")

        # 按境界筛选可用事件
        eligible = [ev for ev in EVENT_POOL if player.level_index >= ev.get("min_level", 0)]
        if not eligible:
            return None
        event = random.choice(eligible)

        payload = {
            "key": event["key"],
            "expire": int(time.time()) + self.CHOICE_EXPIRE,
        }
        await self.db.ext.set_system_config(self._storage_key(player.user_id), json.dumps(payload, ensure_ascii=False))

        option_lines = "\n".join(
            f"  [{i}] {opt['label']}" for i, opt in enumerate(event["options"], 1)
        )
        return (
            f"\n\n✨【奇遇】{event['title']}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"{event['desc']}\n"
            f"{option_lines}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 发送 /奇遇选择 <编号> 做出抉择（{self.CHOICE_EXPIRE // 60}分钟内有效，过期视作离开）"
        )

    async def resolve_choice(self, player: Player, choice: int) -> Tuple[bool, str]:
        """处理玩家的奇遇选择"""
        raw = await self.db.ext.get_system_config(self._storage_key(player.user_id))
        if not raw:
            return False, "❌ 你当前没有进行中的奇遇。"

        try:
            payload = json.loads(raw)
        except Exception:
            await self.db.ext.set_system_config(self._storage_key(player.user_id), "")
            return False, "❌ 奇遇数据异常，已清除。"

        if int(time.time()) > int(payload.get("expire", 0)):
            await self.db.ext.set_system_config(self._storage_key(player.user_id), "")
            return False, "⌛ 奇遇已消散于风中（超时未选择）。"

        event = self.events.get(payload.get("key", ""))
        if not event:
            await self.db.ext.set_system_config(self._storage_key(player.user_id), "")
            return False, "❌ 未知奇遇事件，已清除。"

        if choice < 1 or choice > len(event["options"]):
            return False, f"❌ 请输入 1-{len(event['options'])} 的编号。"

        # 一经选择立即清除，防止重复结算
        await self.db.ext.set_system_config(self._storage_key(player.user_id), "")

        option = event["options"][choice - 1]
        weight = option.get("weight")

        # 离开类选项直接结算
        if weight == "leave":
            return True, "🚶 你谨慎地离开了，世间机缘，随缘而已。"

        # 风险类 55% 成功；善行必成；恶行 70% 成功；稳妥类 85% 成功
        fail = False
        if weight == "risk":
            fail = random.random() > 0.55
        elif weight == "evil":
            fail = random.random() > 0.7
        elif weight == "safe":
            fail = random.random() > 0.85
        elif weight == "good":
            fail = False

        outcome = option.get("lose") if fail else option.get("win")
        if not outcome:
            return True, "🤔 你尝试了一番，却一无所获……"

        lines = [f"🎲【{event['title']}】你选择了「{option['label']}」", "━━━━━━━━━━━━━━━"]

        if fail:
            lines.append("💀 事情朝糟糕的方向发展了...")
        else:
            lines.append("🎉 你的抉择带来了回报！")

        scale = self._reward_scale(player)
        # lose 中的 gold/exp 数值语义是"损失量"，失败时必须取负发放，否则输局反而发钱
        if fail:
            gold = -abs(int(outcome.get("gold", 0)))
            exp = -abs(int(outcome.get("exp", 0)))
        else:
            gold = int(outcome.get("gold", 0) * scale)
            exp = int(outcome.get("exp", 0) * scale)
            # 境界封顶：单次奇遇灵石收益不超过当前境界的水位（炼气 2,800 → 满级 30,000）
            gold = min(gold, self._level_gold_cap(player))
        hp_pct = float(outcome.get("hp_pct", 0))
        karma = int(outcome.get("karma", 0))
        item = outcome.get("item")

        if gold:
            player.gold = max(0, player.gold + gold)
            lines.append(f"{'获得' if gold > 0 else '损失'}灵石：{gold:+,}")
        if exp:
            player.experience = max(0, player.experience + exp)
            lines.append(f"{'获得' if exp > 0 else '损失'}修为：{exp:+,}")
        if hp_pct:
            lost = int(player.hp * hp_pct)
            player.hp = max(1, player.hp - lost)
            lines.append(f"损失气血：-{lost:,}")
        if karma > 0:
            player.karma = (getattr(player, "karma", 0) or 0) + karma
            lines.append(f"✨功德 +{karma}（当前功德 {player.karma}）：奇遇概率与突破成功率提升")
        elif karma < 0:
            player.karma = (getattr(player, "karma", 0) or 0) + karma
            lines.append(f"🌑业力 {karma}（当前 {player.karma}）：突破成功率降低，多行善可消解")

        need_save = bool(gold or exp or hp_pct or karma)

        if item and self.storage_ring_mgr and not fail:
            item_name = item.get("name", "")
            item_count = int(item.get("count", 1))
            success, _ = await self.storage_ring_mgr.store_item(player, item_name, item_count, silent=True)
            if success:
                lines.append(f"📦 获得物品：【{item_name}】x{item_count}（已存入储物戒）")
            else:
                lines.append(f"⚠️ 获得【{item_name}】x{item_count}，但储物戒已满，物品丢失")

        if need_save:
            await self.db.update_player(player)
        return True, "\n".join(lines)
