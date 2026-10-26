# managers/sect_coop.py —— 宗门协作榜 + 悬赏助力
import time
import json
from typing import Tuple

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["SectCoopManager"]


class SectCoopManager:
    """v6.20 宗门协作：成员每日任务进度聚合周榜 + 悬赏助力"""

    def __init__(self, db: DataBase):
        self.db = db

    # ===== 宗门周协作榜 =====
    async def bump_sect_progress(self, player: Player, points: int = 1):
        """成员完成日常行为时为宗门+协作分（按周存）"""
        if not player.sect_id:
            return
        week = time.strftime("%G-W%V")
        key = f"sect_coop_{player.sect_id}_{week}"
        old = await self.db.ext.get_system_config(key)
        val = (int(old) if old and old.isdigit() else 0) + points
        await self.db.ext.set_system_config(key, str(val))
        # 个人贡献（用于宗门内展示）
        pkey = f"sect_coop_p_{player.sect_id}_{week}_{player.user_id}"
        pold = await self.db.ext.get_system_config(pkey)
        pval = (int(pold) if pold and pold.isdigit() else 0) + points
        await self.db.ext.set_system_config(pkey, str(pval))

    async def weekly_board(self, player: Player) -> str:
        """宗门协作周榜（全服宗门排名 + 本宗成员贡献）"""
        week = time.strftime("%G-W%V")
        sects = await self.db.ext.get_all_sects()
        if not sects:
            return "🏛️ 宗门协作榜：暂无宗门数据。"

        board = []
        for sect in sects:
            key = f"sect_coop_{sect.sect_id}_{week}"
            val = await self.db.ext.get_system_config(key)
            board.append((sect, int(val) if val and val.isdigit() else 0))
        board.sort(key=lambda x: x[1], reverse=True)

        lines = [f"🏛️【宗门协作周榜】（{week}）", "━━━━━━━━━━━━━━━"]
        medals = ["🥇", "🥈", "🥉"]
        my_rank = None
        for idx, (sect, val) in enumerate(board, 1):
            mark = medals[idx - 1] if idx <= 3 else f"{idx}."
            if sect.sect_id == player.sect_id:
                my_rank = idx
                mark = f"➡{mark}"
            lines.append(f"{mark} 【{sect.sect_name}】协作分 {val:,}")
        lines.append("━━━━━━━━━━━━━━━")

        if player.sect_id:
            lines.append(f"你的宗门排名：第 {my_rank if my_rank else '—'} 名")
            # 本宗成员贡献
            my_sect = next((s for s, _ in board if s.sect_id == player.sect_id), None)
            if my_sect:
                members = await self.db.ext.get_sect_members(player.sect_id)
                rows = []
                for mem in members:
                    pkey = f"sect_coop_p_{player.sect_id}_{week}_{mem.user_id}"
                    pv = await self.db.ext.get_system_config(pkey)
                    rows.append((mem, int(pv) if pv and pv.isdigit() else 0))
                rows.sort(key=lambda x: x[1], reverse=True)
                top = rows[:5]
                if top and top[0][1] > 0:
                    lines.append("本宗贡献前5：")
                    for mem, val in top:
                        lines.append(f"  · {mem.user_name or mem.user_id[:8]} — {val}")
            lines.append("💡 成员完成日常任务即可为宗门+协作分（周一重置）")
        else:
            lines.append("💡 加入宗门后即可为本宗贡献协作分！")
        return "\n".join(lines)


# ===== 悬赏助力（挂在 bounty_manager 或独立；独立实现）=====
class BountyAssist:
    """悬赏助力：玩家可对他人进行中的悬赏助力一次，得该悬赏 10% 奖励"""

    def __init__(self, db: DataBase):
        self.db = db

    async def assist(self, player: Player, target_id: str) -> Tuple[bool, str]:
        # 不能助自己
        if player.user_id == target_id:
            return False, "❌ 不能给自己的悬赏助力。"
        # 目标有进行中的悬赏？
        raw = await self.db.ext.get_active_bounty(target_id)
        if not raw:
            return False, "❌ 对方当前没有进行中的悬赏。"
        bounty = dict(raw)
        target = await self.db.get_player_by_id(target_id)
        tname = (target.user_name if target and target.user_name else target_id[:8])

        # 每个悬赏最多3人助力（每人限1次）
        week_id = f"bounty_{bounty['id']}" if "id" in bounty else f"bounty_{target_id}_{bounty.get('start_time', 0)}"
        aid_key = f"bounty_assist_{week_id}"
        helpers = []
        raw_helpers = await self.db.ext.get_system_config(aid_key)
        if raw_helpers:
            try:
                helpers = json.loads(raw_helpers)
            except Exception:
                helpers = []
        if player.user_id in helpers:
            return False, "❌ 你已助力过这次悬赏。"
        if len(helpers) >= 3:
            return False, "❌ 该悬赏助力已满（3人）。"

        # 助力奖励：该悬赏奖励的10%
        try:
            rewards = json.loads(bounty.get("rewards", "{}"))
        except Exception:
            rewards = {}
        stone = int(rewards.get("stone", 0) * 0.10)
        exp = int(rewards.get("exp", 0) * 0.10)

        player.gold += stone
        player.experience += exp
        player.karma = (getattr(player, "karma", 0) or 0) + 1  # 助人为乐，功德+1
        await self.db.update_player(player)

        helpers.append(player.user_id)
        await self.db.ext.set_system_config(aid_key, json.dumps(helpers))

        # 信箱：通知悬赏主人
        try:
            from .enhance_systems import MailboxManager
            await MailboxManager(self.db).send(
                target_id, "悬赏助力",
                f"【{player.user_name or player.user_id[:8]}】为你的悬赏助力，为你加油打气！"
            )
        except Exception:
            pass

        return True, (
            f"🤝 悬赏助力成功！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"你为【{tname}】的悬赏「{bounty.get('bounty_name', '任务')}」助力。\n"
            f"获得：{stone:,} 灵石 + {exp:,} 修为\n"
            f"✨ 助人为乐，功德 +1\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 每个悬赏最多 3 人助力，每人限 1 次"
        )
