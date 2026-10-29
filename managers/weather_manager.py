# managers/weather_manager.py
"""天象系统 v6.18 - 每日全服天象，影响闭关/历练/奇遇/突破/灵田收益"""
import random
import time
from typing import Dict, Optional

from ..data.data_manager import DataBase

__all__ = ["WeatherManager"]


class WeatherManager:
    """每日天象：按自然日（YYYYMMDD）全服统一，跨天自动重生成。
    状态存 system_config：weather_today_{YYYYMMDD} = JSON 字符串
    核心接口 get_multiplier(scene) 无副作用、永不抛异常，供主控接入各系统。"""

    # scene: cultivate=闭关 adventure=历练 encounter=奇遇触发 breakthrough=突破 farm=灵田
    WEATHERS = [
        {
            "key": "rain", "name": "灵雨", "icon": "🌧️",
            "desc": "天降灵雨，草木沐灵，最宜耕修",
            "weight": 16,
            "effects": {"cultivate": 1.15, "farm": 1.20},
        },
        {
            "key": "sun", "name": "烈日", "icon": "☀️",
            "desc": "烈日灼灼，灵田受旱，阳气助修",
            "weight": 16,
            "effects": {"cultivate": 1.10, "farm": 0.80},
        },
        {
            "key": "demon_wind", "name": "魔风", "icon": "🌑",
            "desc": "魔风过境，机遇与凶险并存，心魔易生",
            "weight": 12,
            "effects": {"encounter": 1.10, "breakthrough": 0.95},
        },
        {
            "key": "tide", "name": "灵潮", "icon": "🌊",
            "desc": "灵气如潮涌动，历练事半功倍",
            "weight": 14,
            "effects": {"adventure": 1.20},
        },
        {
            "key": "fog", "name": "大雾", "icon": "🌫️",
            "desc": "仙雾迷蒙，机缘隐现，行路维艰",
            "weight": 12,
            "effects": {"encounter": 1.15, "adventure": 0.90},
        },
        {
            "key": "sunny", "name": "晴", "icon": "🌤️",
            "desc": "风和日丽，天地清朗，一切如常",
            "weight": 30,
            "effects": {},
        },
    ]

    SCENE_NAMES = {
        "cultivate": "闭关修炼",
        "adventure": "出外历练",
        "encounter": "奇遇触发",
        "breakthrough": "突破成功率",
        "farm": "灵田产出",
    }

    def __init__(self, db: DataBase):
        self.db = db

    # ================= 内部工具 =================

    def _today_key(self) -> str:
        return f"weather_today_{time.strftime('%Y%m%d')}"

    def _load_weather(self, raw: Optional[str]) -> Optional[dict]:
        try:
            import json
            data = json.loads(raw) if raw else None
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    async def ensure_today(self) -> dict:
        """读取今日天象，无则按权重随机生成并写入（跨天自动重生成）。"""
        key = self._today_key()
        try:
            raw = await self.db.ext.get_system_config(key)
        except Exception:
            raw = None
        today = self._load_weather(raw)
        if today and today.get("date") == time.strftime("%Y%m%d"):
            return today

        weights = [w["weight"] for w in self.WEATHERS]
        chosen = random.choices(self.WEATHERS, weights=weights, k=1)[0]
        today = {
            "key": chosen["key"],
            "name": chosen["name"],
            "icon": chosen["icon"],
            "desc": chosen["desc"],
            "effects": dict(chosen["effects"]),
            "date": time.strftime("%Y%m%d"),
        }
        try:
            import json
            await self.db.ext.set_system_config(key, json.dumps(today, ensure_ascii=False))
        except Exception:
            pass
        return today

    # ================= 核心接口 =================

    async def get_multiplier(self, scene: str) -> float:
        """今日天象对指定场景的收益倍率（1.0 为无效果）。
        无副作用、永不抛异常，供闭关/历练/奇遇/突破/灵田等系统接入。"""
        try:
            raw = await self.db.ext.get_system_config(self._today_key())
            today = self._load_weather(raw)
            if not today or today.get("date") != time.strftime("%Y%m%d"):
                return 1.0
            effects = today.get("effects") or {}
            val = effects.get(scene, 1.0)
            return float(val) if isinstance(val, (int, float)) else 1.0
        except Exception:
            return 1.0

    # ================= 展示 =================

    async def get_weather_text(self) -> str:
        """天气播报文本（用于广播/查询）。"""
        try:
            today = await self.ensure_today()
        except Exception:
            return "🌤️ 天象莫测，暂时无法观测。"

        lines = [
            f"{today.get('icon', '🌤️')}【今日天象】{today.get('name', '未知')}",
            f"━━━━━━━━━━━━━━━",
            f"{today.get('desc', '天地如常')}",
        ]
        effects = today.get("effects") or {}
        if effects:
            for scene, val in effects.items():
                scene_name = self.SCENE_NAMES.get(scene, scene)
                pct = (float(val) - 1.0) * 100
                sign = "+" if pct >= 0 else ""
                lines.append(f"  · {scene_name}：{sign}{pct:.0f}%")
        else:
            lines.append("  · 各项收益均无变化")
        return "\n".join(lines)

    async def handle_weather(self, event):
        """/修仙天气 指令：输出今日天象与各场景效果。"""
        text = await self.get_weather_text()
        lines = [
            text,
            "━━━━━━━━━━━━━━━",
            "💡 天象每日更迭，全服同观。闭关、历练、耕田前不妨先观天象。",
        ]
        yield event.plain_result("\n".join(lines))
