# managers/title_forge_manager.py
"""称号熔炼（v3.22.0 新玩法）

- 玩家从【已拥有】的称号中挑 3 个同品阶熔炼
- 70% 成功：随机获得一个高一品阶且尚未拥有的称号
- 30% 失败：仅损失 1 个随机参与称号（另两个保留），并获得 3000 灵石安慰奖
- 帝品（tier 6）为最高品阶，不可再熔炼
- 状态不落新表：称号图鉴仍在 permanent_bonus["titles"]，由 TitleManager 统一管理
"""

import random
import time
from typing import Tuple, List

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player
from .title_data import TIERS

__all__ = ["TitleForgeManager"]


class TitleForgeManager:
    """称号熔炼"""

    SUCCESS_RATE = 0.70          # 熔炼成功率
    COMFORT_GOLD = 3000          # 失败安慰奖灵石
    MAX_TIER = 6                 # 帝品为顶，不可再熔

    def __init__(self, db: DataBase, title_mgr):
        self.db = db
        self.title_mgr = title_mgr  # TitleManager 实例

    # ===== 内部辅助 =====

    def _tier_name(self, tier: int) -> str:
        return TIERS.get(tier, (f"未知({tier})",))[0]

    def _owned_titles(self, player: Player) -> dict:
        """{称号名: 时间戳}"""
        return self.title_mgr._load_owned(player)

    def _upper_pool(self, tier: int, owned: dict) -> List[str]:
        """高一品阶中玩家尚未拥有的称号池"""
        return [
            name for name, t in self.title_mgr.titles.items()
            if t["tier"] == tier + 1 and name not in owned
        ]

    # ===== 熔炼 =====

    async def forge(self, player: Player, name1: str, name2: str, name3: str) -> Tuple[bool, str]:
        """/称号熔炼 <名1> <名2> <名3>"""
        owned = self._owned_titles(player)

        # 容错匹配（去空格/@）
        def match(raw: str):
            key = (raw or "").strip().lstrip("@")
            if key in owned:
                return key
            for k in owned:
                if k.strip() == key:
                    return k
            return None

        names = []
        for raw in (name1, name2, name3):
            key = match(raw)
            if not key:
                return False, f"❌ 你尚未拥有称号【{(raw or '').strip().lstrip('@')}】，无法作为熔炼材料。"
            names.append(key)

        if len(set(names)) < 3:
            return False, "❌ 三个材料称号不能重复。"

        tiers = {self.title_mgr.titles[n]["tier"] for n in names if n in self.title_mgr.titles}
        if len(tiers) != 1:
            return False, "❌ 三个材料称号品阶不一致，必须为同一品阶才能熔炼。"
        tier = tiers.pop()

        if tier >= self.MAX_TIER:
            return False, f"❌ 【{self._tier_name(tier)}】已是最高品阶（帝品），无法继续熔炼。"

        upper_pool = self._upper_pool(tier, owned)
        if not upper_pool:
            return False, (
                f"❌ 【{self._tier_name(tier + 1)}】品阶图鉴你已集齐，"
                f"再无可熔炼出的新称号，天机不予感应。"
            )

        if random.random() < self.SUCCESS_RATE:
            # ===== 成功：移除三个材料，授予随机一个高阶称号 =====
            for n in names:
                owned.pop(n, None)
            self.title_mgr._save_owned(player, owned)
            new_name = random.choice(upper_pool)
            ok, grant_msg = self.title_mgr.grant(player, new_name)
            if not ok:
                # 图鉴池异常（理论不可达，upper_pool 已过滤）：退回三个称号
                for n in names:
                    owned[n] = owned.get(n, 0.0) or time.time()
                self.title_mgr._save_owned(player, owned)
                await self.db.update_player_fields(player.user_id, permanent_bonus=player.permanent_bonus)
                return False, "❌ 熔炼失败：高一品阶图鉴已满，材料已退回。"
            # 落库 permanent_bonus（grant 已改内存）
            await self.db.update_player_fields(player.user_id, permanent_bonus=player.permanent_bonus)
            t = self.title_mgr.titles.get(new_name, {})
            stats = t.get("stats", {}) or {}
            stats_txt = self.title_mgr._format_stats(stats) if hasattr(self.title_mgr, "_format_stats") else str(stats)
            return True, (
                f"🔥✨ 熔炼成功！三道【{self._tier_name(tier)}】称号精華汇入丹炉，"
                f"天光乍破，凝出全新称号！\n"
                f"{grant_msg}\n"
                f"└ 加成：{stats_txt}\n"
                f"💡 加成自动按最高品阶生效，/称号图鉴 可查看。"
            )
        else:
            # ===== 失败：随机损失 1 个材料，另两个保留，发安慰奖 =====
            lost = random.choice(names)
            owned.pop(lost, None)
            self.title_mgr._save_owned(player, owned)
            await self.db.update_player_fields(player.user_id, permanent_bonus=player.permanent_bonus)
            await self.db.add_player_gold(player.user_id, self.COMFORT_GOLD)
            return False, (
                f"💥 熔炼失败！丹炉轰然炸裂，气浪四溢……\n"
                f"╾ 称号【{lost}】在炸炉中化为齑粉，永久损失！\n"
                f"╾ 其余两枚材料完好无损。\n"
                f"💰 炉灰中筛出 {self.COMFORT_GOLD:,} 灵石，聊作安慰。"
            )

    # ===== 规则面板 =====

    async def handle_board(self, player: Player, event) -> str:
        """/称号熔炼 无参：展示规则与各品阶拥有数"""
        owned = self._owned_titles(player)
        count_by_tier = {}
        for name in owned:
            t = self.title_mgr.titles.get(name)
            if t:
                count_by_tier[t["tier"]] = count_by_tier.get(t["tier"], 0) + 1

        lines = [
            "🔥【称号熔炼】",
            "━━━━━━━━━━━━━━━",
            "📜 规则：",
            "  · 从【已拥有】称号中选 3 个同品阶投入丹炉",
            f"  · {int(self.SUCCESS_RATE * 100)}% 成功：随机炼出 1 个高一品阶的新称号",
            f"  · {int((1 - self.SUCCESS_RATE) * 100)}% 失败：炸炉损失 1 枚随机材料，另两枚保留",
            f"  · 失败可获得 {self.COMFORT_GOLD:,} 灵石安慰奖",
            "  · 帝品为最高品阶，不可熔炼",
            "━━━━━━━━━━━━━━━",
            "📊 我的称号库存：",
        ]
        if not count_by_tier:
            lines.append("  （暂无任何称号，先去收集吧）")
        for tier in sorted(count_by_tier):
            mark = " 🔒已至顶" if tier >= self.MAX_TIER else ""
            lines.append(f"  【{self._tier_name(tier)}】× {count_by_tier[tier]}{mark}")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("💡 /称号熔炼 <名1> <名2> <名3> 开炉！")
        lines.append("💡 /我的称号 查看持有详情")
        return "\n".join(lines)
