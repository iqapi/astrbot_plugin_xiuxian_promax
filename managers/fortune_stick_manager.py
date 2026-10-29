# managers/fortune_stick_manager.py
"""每日求签（v3.22.0 新玩法）

- /求签 每日 1 次，抽得当日运势签（存 system_config：fortune_{uid}_{date}）
- 签文影响当日收益：修为倍率（闭关/历练）、灵石倍率、奇遇触发率
- 不建新表，状态全存 system_config（JSON）
"""

import json
import random
import time
from typing import Tuple, Optional

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["FortuneStickManager"]


class FortuneStickManager:
    """每日求签"""

    # tier -> (名称, 权重, 签文, 修为倍率, 灵石倍率, 奇遇加成)
    STICKS = {
        "best":    ("上上签", 5,  "☁️ 紫气东来三万里，今日仙缘顶天！大道可期，诸事皆宜。", 1.10, 1.00, 0.00),
        "good":    ("上签",   15, "🌸 云开月明照丹心，小有进益。稳中求进，福泽绵绵。",     1.05, 1.00, 0.00),
        "mid":     ("中签",   40, "🍃 风平浪静一日游，无波无澜。守常即可，不必强求。",     1.00, 1.00, 0.00),
        "bad":     ("下签",   25, "🌧️ 阴云蔽日心绪沉，修行滞涩。谨言慎行，静待云开。",     0.95, 1.00, 0.00),
        "worst":   ("下下签", 10, "⚡ 走石飞沙劫数临，诸事不顺。今日宜闭关苟命，忌出头。", 0.90, 1.00, 0.00),
        "surprise":("惊签",   3,  "🌈 惊雷破空显异象，机缘乍现！今日奇遇造化远超常人。",   1.00, 1.00, 0.15),
        "wealth":  ("财签",   2,  "🪙 金光铺地宝气冲霄，财星高照！今日灵石收益大增。",     1.00, 1.20, 0.00),
    }

    def __init__(self, db: DataBase):
        self.db = db

    # ===== 存取 =====

    def _date_str(self) -> str:
        return time.strftime("%Y%m%d")

    def _key(self, uid: str) -> str:
        return f"fortune_{uid}_{self._date_str()}"

    async def _load_today(self, uid: str) -> Optional[dict]:
        try:
            raw = await self.db.ext.get_system_config(self._key(uid))
            if not raw:
                return None
            data = json.loads(raw)
            return data if isinstance(data, dict) and data.get("tier") else None
        except Exception:
            return None

    async def _save_today(self, uid: str, tier: str):
        tier_name, _, text, _, _, _ = self.STICKS[tier]
        await self.db.ext.set_system_config(
            self._key(uid),
            json.dumps({"tier": tier, "name": tier_name, "text": text, "date": self._date_str()},
                       ensure_ascii=False),
        )

    # ===== 抽签 =====

    def _roll_tier(self) -> str:
        tiers = list(self.STICKS.keys())
        weights = [self.STICKS[t][1] for t in tiers]
        return random.choices(tiers, weights=weights, k=1)[0]

    async def draw(self, player: Player) -> Tuple[bool, str]:
        """/求签：每日 1 次"""
        exist = await self._load_today(player.user_id)
        if exist:
            return False, (
                f"🪧 你今日已求过签了。\n"
                f"━━━━━━━━━━━━━━━\n"
                f"【{exist.get('name', '？')}】\n"
                f"{exist.get('text', '')}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💡 /今日运势 可随时查看，明日再来。"
            )
        tier = self._roll_tier()
        await self._save_today(player.user_id, tier)
        name, _, text, exp_m, gold_m, adv_add = self.STICKS[tier]

        effect = []
        if exp_m != 1.0:
            effect.append(f"今日修为获取 {'+' if exp_m > 1 else ''}{int((exp_m - 1) * 100)}%")
        if gold_m != 1.0:
            effect.append(f"今日灵石收益 +{int((gold_m - 1) * 100)}%")
        if adv_add:
            effect.append(f"今日奇遇触发率 +{int(adv_add * 100)}%")
        effect_txt = ("✨ 效果：" + "，".join(effect)) if effect else "✨ 效果：平平淡淡才是真"

        return True, (
            f"🪧【每日求签】\n"
            f"━━━━━━━━━━━━━━━\n"
            f"你诚心摇动签筒，一支竹签跃出——\n\n"
            f"🎋【{name}】\n"
            f"「{text}」\n\n"
            f"{effect_txt}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 /今日运势 查看当日运势"
        )

    # ===== 倍率查询（供主控挂闭关/历练/灵石结算） =====

    async def _today_tier(self, uid: str) -> Optional[str]:
        data = await self._load_today(uid)
        return data.get("tier") if data else None

    async def get_exp_mult(self, player: Player) -> float:
        """当日修为倍率（0.9~1.1）；无签/异常返回 1.0"""
        try:
            tier = await self._today_tier(player.user_id)
            if tier and tier in self.STICKS:
                return self.STICKS[tier][3]
        except Exception as e:
            logger.error(f"求签修为倍率查询异常: {e}")
        return 1.0

    async def get_gold_mult(self, player: Player) -> float:
        """当日灵石收益倍率（财签 1.2）；无签/异常返回 1.0"""
        try:
            tier = await self._today_tier(player.user_id)
            if tier and tier in self.STICKS:
                return self.STICKS[tier][4]
        except Exception as e:
            logger.error(f"求签灵石倍率查询异常: {e}")
        return 1.0

    async def get_adventure_bonus(self, player: Player) -> float:
        """当日奇遇触发率加成（惊签 +0.15）；无签/异常返回 0.0"""
        try:
            tier = await self._today_tier(player.user_id)
            if tier and tier in self.STICKS:
                return self.STICKS[tier][5]
        except Exception as e:
            logger.error(f"求签奇遇加成查询异常: {e}")
        return 0.0

    # ===== 查询 =====

    async def handle_today(self, player: Player, event) -> str:
        """/今日运势"""
        data = await self._load_today(player.user_id)
        if not data:
            return (
                "🪧 你今日还未求签。\n"
                "━━━━━━━━━━━━━━━\n"
                "签筒静候多时，天机未定。\n"
                "💡 发送 /求签 抽取今日运势！"
            )
        tier = data.get("tier")
        name, _, _, exp_m, gold_m, adv_add = self.STICKS.get(tier, ("？", 0, "", 1.0, 1.0, 0.0))
        effect = []
        if exp_m != 1.0:
            effect.append(f"修为 {'+' if exp_m > 1 else ''}{int((exp_m - 1) * 100)}%")
        if gold_m != 1.0:
            effect.append(f"灵石收益 +{int((gold_m - 1) * 100)}%")
        if adv_add:
            effect.append(f"奇遇率 +{int(adv_add * 100)}%")
        effect_txt = "，".join(effect) if effect else "无特殊加成"
        return (
            f"🪧【今日运势 · {self._date_str()}】\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🎋【{name}】\n"
            f"「{data.get('text', '')}」\n\n"
            f"✨ 生效加成：{effect_txt}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 每日 0 点更新，/求签 抽新签"
        )
