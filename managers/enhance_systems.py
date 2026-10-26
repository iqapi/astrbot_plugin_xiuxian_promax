# managers/enhance_systems.py
"""v6.21 体验增强包：装备套装 / 离线信箱 / 境界压制衰减"""
import json
import time
import re
from typing import Tuple, List

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["EquipSetManager", "MailboxManager", "apply_level_suppression"]


# ================= 装备套装 =================
class EquipSetManager:
    """同系列装备凑齐触发套装属性（名称前缀匹配）"""

    # 套装定义：系列前缀 -> (套名, 2件效果desc, 3件效果desc, 属性)
    SETS = [
        {"prefix": "玄龟", "name": "玄龟套装", "perk2": "物防+80", "perk3": "物防+80·法防+120·寿命+20",
         "stats2": {"phys_def": 80}, "stats3": {"phys_def": 80, "magic_def": 120}},
        {"prefix": "天罡", "name": "天罡套装", "perk2": "物伤+100", "perk3": "物伤+100·会心+5",
         "stats2": {"atk": 100}, "stats3": {"atk": 100, "crit": 5}},
        {"prefix": "烈焰", "name": "烈焰套装", "perk2": "法伤+120", "perk3": "法伤+120·吸血+4",
         "stats2": {"magic": 120}, "stats3": {"magic": 120, "lifesteal": 4}},
        {"prefix": "寒冰", "name": "寒冰套装", "perk2": "法防+100", "perk3": "法防+100·法伤+80",
         "stats2": {"magic_def": 100}, "stats3": {"magic_def": 100, "magic": 80}},
        {"prefix": "庚金", "name": "庚金套装", "perk2": "物伤+90", "perk3": "物伤+90·物防+60",
         "stats2": {"atk": 90}, "stats3": {"atk": 90, "phys_def": 60}},
    ]

    def __init__(self, db: DataBase):
        self.db = db

    def match_sets(self, player: Player) -> List[dict]:
        """当前穿戴中触发的套装（≥2件同名前缀）"""
        equipped = [player.weapon or "", player.armor or "", player.main_technique or ""]
        equipped = [e for e in equipped if e]
        result = []
        for s in self.SETS:
            cnt = sum(1 for e in equipped if e.startswith(s["prefix"]))
            if cnt >= 2:
                entry = dict(s)
                entry["count"] = cnt
                entry["stats"] = s["stats3"] if cnt >= 3 else s["stats2"]
                result.append(entry)
        return result

    def total_set_bonus(self, player: Player) -> dict:
        """所有套装加成合并（只取每个套装的最优档）"""
        total = {}
        for entry in self.match_sets(player):
            for k, v in entry["stats"].items():
                total[k] = total.get(k, 0) + v
        return total

    def panel(self, player: Player) -> str:
        """套装面板（/装备图鉴 内嵌或独立查看）"""
        equipped = [player.weapon or "", player.armor or "", player.main_technique or ""]
        equipped = [e for e in equipped if e]
        lines = ["套装鉴识", "━━━━━━━━━━━━━━━"]
        if not equipped:
            return "当前未穿戴任何装备，无法鉴识套装。"
        triggered = self.match_sets(player)
        if triggered:
            for entry in triggered:
                perk = entry["perk3"] if entry["count"] >= 3 else entry["perk2"]
                lines.append(f"✅【{entry['name']}】{entry['count']}件生效")
                lines.append(f"   效果：{perk}")
        else:
            lines.append("未触发任何套装。可凑齐同前缀装备：")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("已知套装：")
        for s in self.SETS:
            lines.append(f"  · {s['name']}（{s['prefix']}系列）2件:{s['perk2']} / 3件:{s['perk3']}")
        lines.append("💡 同名前缀的武器/防具/心法同时穿戴即可触发")
        return "\n".join(lines)


# ================= 离线信箱 =================
class MailboxManager:
    """事件发生时收件人不在线 → 进信箱；/信箱 查看/收取"""

    MAX_MAIL = 20

    def __init__(self, db: DataBase):
        self.db = db

    def _key(self, user_id: str) -> str:
        return f"mailbox_{user_id}"

    async def send(self, user_id: str, sender: str, content: str):
        """投递信件（事件发生点调用）"""
        raw = await self.db.ext.get_system_config(self._key(user_id))
        mails = []
        if raw:
            try:
                mails = json.loads(raw)
            except Exception:
                mails = []
        mails.append({
            "from": sender,
            "content": content,
            "time": int(time.time()),
            "read": False,
        })
        mails = mails[-self.MAX_MAIL:]  # 最多保留20封
        await self.db.ext.set_system_config(self._key(user_id), json.dumps(mails, ensure_ascii=False))

    async def view(self, player: Player) -> str:
        raw = await self.db.ext.get_system_config(self._key(player.user_id))
        mails = []
        if raw:
            try:
                mails = json.loads(raw)
            except Exception:
                mails = []
        if not mails:
            return "📮 信箱空空如也。\n💡 被劫镖、被助力、被拜师等事件即使你不在线，也会寄到这里。"

        unread = sum(1 for m in mails if not m.get("read"))
        lines = [f"📮 信箱（{len(mails)} 封，未读 {unread}）", "━━━━━━━━━━━━━━━"]
        for i, m in enumerate(reversed(mails[-10:]), 1):  # 最新10封
            tstr = time.strftime("%m-%d %H:%M", time.localtime(m["time"]))
            mark = "🆕" if not m.get("read") else "  "
            lines.append(f"{mark} [{tstr}] {m['from']}")
            lines.append(f"   {m['content']}")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("💡 全部已标记为已读")
        # 标记已读
        for m in mails:
            m["read"] = True
        await self.db.ext.set_system_config(self._key(player.user_id), json.dumps(mails, ensure_ascii=False))
        return "\n".join(lines)


# ================= 境界压制衰减 =================
def apply_level_suppression(player: Player, route_min_level: int) -> float:
    """高境界打低级路线收益衰减：境界超出路线需求 10 级以上，每级 -5%（下限 40%）
    返回收益倍率"""
    overflow = player.level_index - route_min_level
    if overflow <= 10:
        return 1.0
    mult = max(0.4, 1.0 - (overflow - 10) * 0.05)
    return mult
