# managers/treasure_hunt_manager.py
"""天材地宝：全服定时刷新的抢夺型玩法（v3.20.0 新玩法）

主控定时（约每 30 分钟的循环里）调用 try_spawn()：
- 30% 概率在无活跃宝物时刷新一个，生成文本供全服广播
- 玩家 /夺宝 先到先得，每次刷新仅 1 人可得
- 24 小时未抢自动消散
"""

import json
import random
import time
from typing import Tuple

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["TreasureHuntManager"]


class TreasureHuntManager:
    """天材地宝争夺"""

    SPAWN_CHANCE = 0.30
    EXPIRE_SECONDS = 24 * 3600

    TREASURES = [
        {"name": "千年灵芝", "desc": "药香十里，服之修为大进", "exp": 30000, "gold": 0, "weight": 15},
        {"name": "龙血草", "desc": "赤红如血，蕴含精纯灵气", "exp": 15000, "gold": 0, "weight": 20},
        {"name": "灵石矿髓", "desc": "一块未经雕琢的灵石母矿", "exp": 0, "gold": 8000, "weight": 20},
        {"name": "星辰砂", "desc": "炼器师的梦寐以求，折现 5000 灵石", "exp": 0, "gold": 5000, "weight": 15},
        {"name": "悟道古叶", "desc": "上古道树残叶，观之顿生明悟", "exp": 20000, "gold": 0, "weight": 10},
        {"name": "地脉乳泉", "desc": "一瓮地乳，饮之气血充盈", "exp": 10000, "gold": 3000, "weight": 12},
        {"name": "凤尾羽", "desc": "传说神禽遗羽，宝光流转", "exp": 0, "gold": 20000, "weight": 5},
        {"name": "无名残卷", "desc": "残页上隐有道纹流转", "exp": 8000, "gold": 5000, "weight": 18},
    ]

    def __init__(self, db: DataBase):
        self.db = db

    def _active_key(self) -> str:
        return "treasure_active"

    async def _load_active(self) -> dict:
        raw = await self.db.ext.get_system_config(self._active_key())
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    async def try_spawn(self) -> Tuple[bool, str]:
        """定时调用：30% 概率刷新宝物（有活跃未过期的不刷新）。返回播报文本（空=无事发生）"""
        try:
            now = int(time.time())
            active = await self._load_active()
            if active and active.get("spawn_ts", 0) + self.EXPIRE_SECONDS > now and not active.get("claimed"):
                return False, ""
            if active and (active.get("claimed") or active.get("spawn_ts", 0) + self.EXPIRE_SECONDS <= now):
                # 消散已被抢/过期的旧宝物（v3.23.0 修复：必须清空状态键，否则永久卡死刷新）
                if not active.get("claimed") and active.get("spawn_ts", 0) + self.EXPIRE_SECONDS <= now:
                    gone_name = active.get("name", "?")
                    await self.db.ext.set_system_config(self._active_key(), "")
                    return False, f"💨 天材地宝【{gone_name}】无人问津，已随风消散。"
                await self.db.ext.set_system_config(self._active_key(), "")

            if random.random() > self.SPAWN_CHANCE:
                return False, ""

            total = sum(t["weight"] for t in self.TREASURES)
            roll = random.randint(1, total)
            upto = 0
            chosen = self.TREASURES[0]
            for t in self.TREASURES:
                upto += t["weight"]
                if roll <= upto:
                    chosen = t
                    break
            data = {
                "name": chosen["name"],
                "desc": chosen["desc"],
                "exp": chosen["exp"],
                "gold": chosen["gold"],
                "spawn_ts": now,
                "expire_ts": now + self.EXPIRE_SECONDS,
                "claimed": False,
            }
            await self.db.ext.set_system_config(self._active_key(), json.dumps(data, ensure_ascii=False))
            return True, (
                f"🌈【天道异象】天材地宝【{chosen['name']}】现世！\n"
                f"━━━━━━━━━━━━━━━\n"
                f"{chosen['desc']}\n"
                f"⏳ 24 小时内先到先得，全服仅此一份！\n"
                f"💡 手快有手慢无：/夺宝"
            )
        except Exception as e:
            logger.error(f"天材地宝刷新异常: {e}")
            return False, ""

    async def grab(self, player: Player) -> Tuple[bool, str]:
        """/夺宝：先到先得（v3.23.0 改 CAS 抢占：修改后的 JSON 原子覆写，失败即被人抢先）"""
        now = int(time.time())
        active = await self._load_active()
        if not active or active.get("claimed"):
            return False, "🏜️ 原野空空，当前没有现世的天材地宝。静待天道异象吧。"
        if now > active.get("expire_ts", 0):
            return False, "💨 宝物灵光已散（已过期消散）。"

        # CAS 抢占：以当前完整 JSON 为期望旧值，原子写入已领取状态
        active["claimed"] = True
        active["claimed_by"] = player.user_name or player.user_id[:8]
        old_raw = json.dumps({**active, "claimed": False, "claimed_by": None}, ensure_ascii=False)
        claimed = await self.db.ext.syscfg_cas(self._active_key(), json.dumps(active, ensure_ascii=False), old_raw)
        if not claimed:
            return False, "💨 差之毫厘！宝物刚被其他道友夺走……"

        exp_gain = int(active.get("exp", 0))
        gold_gain = int(active.get("gold", 0))
        if gold_gain > 0:
            await self.db.add_player_gold(player.user_id, gold_gain)
        if exp_gain > 0:
            await self.db.add_player_exp(player.user_id, exp_gain)

        lines = [f"🌈 你赶在所有道友之前，夺得了【{active['name']}】！"]
        if exp_gain:
            lines.append(f"📈 修为：+{exp_gain:,}")
        if gold_gain:
            lines.append(f"💰 灵石：+{gold_gain:,}")
        lines.append("江湖险恶，得宝莫张扬……")
        return True, "\n".join(lines)

    async def handle_status(self, event):
        """/天材地宝 查看当前状态"""
        now = int(time.time())
        active = await self._load_active()
        if not active:
            yield event.plain_result(
                "🌈【天材地宝】\n━━━━━━━━━━━━━━━\n当前没有宝物现世。\n"
                "💡 天道偶尔降下异象，全服广播出现时手快者得（/夺宝）"
            )
            return
        if active.get("claimed"):
            yield event.plain_result(
                f"🌈【天材地宝】\n━━━━━━━━━━━━━━━\n"
                f"【{active['name']}】已被【{active.get('claimed_by', '?')}】夺走。\n"
                f"静待下一次天道异象吧。"
            )
            return
        if now > active.get("expire_ts", 0):
            yield event.plain_result(f"💨【{active['name']}】灵光已散，无人问津。")
            return
        remain_h = (active["expire_ts"] - now) // 3600
        yield event.plain_result(
            f"🌈【天材地宝 · 现世中】\n━━━━━━━━━━━━━━━\n"
            f"【{active['name']}】{active['desc']}\n"
            f"⏳ 剩余 {remain_h} 小时 · 全服仅一份\n"
            f"⚔️ 立即 /夺宝 ！"
        )
