# managers/ladder_manager.py
"""段位天梯（v3.30.0 新玩法）：PVP 积分段位体系

- 积分：决斗胜 +3 / 负 -1 / 平 0；切磋胜 +1 / 负平 0（以发起方结算，积分钳 ≥0）
- 段位：青铜 → 白银 → 黄金 → 铂金 → 钻石 → 宗师，积分达标即晋升
- 段位里程碑一次性奖励：/天梯领取 按当前最高已达段位领取
- 状态存 system_config 数值键（ladder_pts_* / ladder_win_* / ladder_claim_*），无新表
"""

from typing import Tuple, List

from astrbot.api import logger

from ..data.data_manager import DataBase

__all__ = ["LadderManager"]


class LadderManager:
    """段位天梯：以战证道，步步登高"""

    # (积分门槛, 段位名)
    TIERS = [
        (0, "🥉 青铜剑士"),
        (30, "🥈 白银游侠"),
        (80, "🥇 黄金剑豪"),
        (160, "💠 铂金武尊"),
        (280, "💎 钻石战圣"),
        (450, "🔮 宗师·通神"),
    ]
    # 段位里程碑奖励（index -> 灵石）
    MILESTONE_GOLD = {1: 2000, 2: 5000, 3: 12000, 4: 30000, 5: 80000}
    DUEL_WIN, DUEL_LOSE = 3, -1
    SPAR_WIN = 1

    def __init__(self, db: DataBase):
        self.db = db

    @staticmethod
    def _pts_key(uid: str) -> str:
        return f"ladder_pts_{uid}"

    @staticmethod
    def _win_key(uid: str) -> str:
        return f"ladder_win_{uid}"

    @staticmethod
    def _claim_key(uid: str, tier_idx: int) -> str:
        return f"ladder_claim_{uid}_{tier_idx}"

    def tier_of(self, points: int) -> Tuple[int, str]:
        idx = 0
        for i, (th, _name) in enumerate(self.TIERS):
            if points >= th:
                idx = i
        return idx, self.TIERS[idx][1]

    async def get_points(self, uid: str) -> int:
        return await self.db.ext.syscfg_get_number(self._pts_key(uid))

    async def get_wins(self, uid: str) -> int:
        return await self.db.ext.syscfg_get_number(self._win_key(uid))

    async def record(self, uid: str, outcome: str, duel: bool) -> str:
        """记录一场 PVP 结果。返回附加提示（无变化返回空串）"""
        if outcome == "win":
            delta = self.DUEL_WIN if duel else self.SPAR_WIN
        elif outcome == "lose":
            delta = self.DUEL_LOSE if duel else 0
        else:
            delta = 0

        old_pts = await self.get_points(uid)
        new_pts = await self.db.ext.syscfg_adjust_number(self._pts_key(uid), delta)
        note = ""
        if delta:
            note = f"\n🗡️ 天梯积分 {'+' if delta > 0 else ''}{delta}（当前 {new_pts}）"

        if outcome == "win":
            await self.db.ext.syscfg_adjust_number(self._win_key(uid), 1)

        old_idx, _ = self.tier_of(old_pts)
        new_idx, new_name = self.tier_of(new_pts)
        if new_idx > old_idx:
            note += f"\n🎉 天梯晋升：{new_name}！/天梯领取 领取段位奖励"
            # 称号（初入天梯30 / 天梯战魂160 / 天梯至圣450）
            try:
                from .title_hooks import TitleHooks
                p = await self.db.get_player_by_id(uid)
                if p:
                    tmsg = await TitleHooks(self.db).bump_value(p, "ladder_points", new_pts)
                    if tmsg:
                        note += f"\n{tmsg.strip()}"
            except Exception as e:
                logger.warning(f"[天梯] 称号授予失败: {e}")
        return note

    async def get_panel(self, player) -> str:
        uid = player.user_id
        pts = await self.get_points(uid)
        wins = await self.get_wins(uid)
        idx, name = self.tier_of(pts)
        lines = [
            "⚔️【段位天梯】",
            "━━━━━━━━━━━━━━━",
            f"🏅 当前段位：{name}",
            f"⚡ 天梯积分：{pts} · 累计胜利：{wins} 场",
        ]
        if idx + 1 < len(self.TIERS):
            nxt_th, nxt_name = self.TIERS[idx + 1]
            lines.append(f"⏭️ 距 {nxt_name}：还需 {nxt_th - pts} 积分")
        else:
            lines.append("👑 已至天梯之巅！")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("💡 决斗 胜+3/负-1 · 切磋 胜+1（发起方结算）")
        unclaimed = [self.TIERS[t][1] for t in self.MILESTONE_GOLD
                     if pts >= self.TIERS[t][0]
                     and not await self.db.ext.get_system_config(self._claim_key(uid, t))]
        if unclaimed:
            lines.append(f"🎁 有可领取的段位奖励：{'、'.join(unclaimed)} → /天梯领取")
        lines.append("💡 /天梯榜 查看全服高手")
        return "\n".join(lines)

    async def claim_milestone(self, player) -> Tuple[bool, str]:
        """领取当前最高已达且未领的段位奖励（从高到低找第一个可领的）"""
        uid = player.user_id
        pts = await self.get_points(uid)
        for t in sorted(self.MILESTONE_GOLD.keys(), reverse=True):
            th, tname = self.TIERS[t]
            if pts < th:
                continue
            if await self.db.ext.get_system_config(self._claim_key(uid, t)):
                continue
            # 原子认领
            if not await self.db.ext.syscfg_claim_slot(self._claim_key(uid, t), 1):
                continue
            gold = self.MILESTONE_GOLD[t]
            await self.db.add_player_gold(uid, gold)
            return True, (
                f"🎁【{tname}】段位奖励已领取！\n💰 灵石 +{gold:,}\n"
                f"⚔️ 继续征战天梯，向更高段位进发！"
            )
        return False, "❌ 暂无可领取的段位奖励（达标段位的奖励均已领取）。"

    async def get_ranking(self, limit: int = 10) -> str:
        async with self.db.conn.execute(
            "SELECT key, value FROM system_config WHERE key LIKE 'ladder_pts_%'"
        ) as cursor:
            rows = await cursor.fetchall()
        entries: List[Tuple[str, int]] = []
        for key, value in rows:
            uid = key.replace("ladder_pts_", "")
            try:
                pts = int(value)
            except (TypeError, ValueError):
                continue
            if pts > 0:
                entries.append((uid, pts))
        entries.sort(key=lambda x: -x[1])
        if not entries:
            return "⚔️【天梯榜】\n━━━━━━━━━━━━━━━\n天梯尚未开启——发 /决斗 @道友 拿下首胜！"
        lines = ["⚔️【天梯榜】", "━━━━━━━━━━━━━━━"]
        medals = ["🥇", "🥈", "🥉"]
        for i, (uid, pts) in enumerate(entries[:limit], 1):
            p = await self.db.get_player_by_id(uid)
            name = (p.user_name if p and p.user_name else uid[:8])
            _, tname = self.tier_of(pts)
            medal = medals[i - 1] if i <= 3 else f"{i}."
            lines.append(f"{medal} {name} —— {pts} 分（{tname}）")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("💡 决斗/切磋累积积分，/天梯领取 段位奖励")
        return "\n".join(lines)
