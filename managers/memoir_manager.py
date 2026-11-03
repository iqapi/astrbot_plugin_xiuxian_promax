# managers/memoir_manager.py
"""仙途回忆录（v3.34.0 新玩法）：个人修行生涯年报

纯聚合读取既有数据（system_config 数值键 + 玩家字段），零写入零风险：
修炼 / 战斗 / 积累 / 生活四大篇章，一目了然的仙途足迹。
"""

from ..data.data_manager import DataBase

__all__ = ["MemoirManager"]


class MemoirManager:
    """仙途回忆录：你走过的每一步，天道都记着"""

    def __init__(self, db: DataBase):
        self.db = db

    async def get_memoir(self, player) -> str:
        uid = player.user_id
        g = self.db.ext.syscfg_get_number

        # ===== 修炼篇 =====
        level_name = "未知"
        try:
            level_name = player.get_level(self.config_manager) if self.config_manager else f"境界{player.level_index}"
        except Exception:
            level_name = f"境界{player.level_index}"

        # ===== 战斗篇 =====
        tower_best = await g(f"tower_best_{uid}")
        hunt_total = await g("hunt_total_" + uid)
        ladder_pts = await g(f"ladder_pts_{uid}")
        ladder_wins = await g(f"ladder_win_{uid}")
        _, tier_name = self._ladder_tier(ladder_pts)

        # ===== 积累篇 =====
        daoxin = await g(f"daoxin_{uid}")
        jade = await g(f"samsara_jade_{uid}")
        karma = int(getattr(player, "karma", 0) or 0)
        virtue = int(getattr(player, "virtue_points", 0) or 0)
        fate = int(getattr(player, "fate_points", 0) or 0)

        # ===== 生活篇 =====
        bank_balance = 0
        try:
            account = await self.db.ext.get_bank_account(uid)
            if account:
                bank_balance = int(account.get("balance", 0) or 0)
        except Exception:
            pass
        sect_contrib = int(getattr(player, "sect_contribution", 0) or 0)
        ring_level = 0
        land_level = 0
        try:
            row = None
            async with self.db.conn.execute(
                "SELECT level FROM blessed_lands WHERE user_id = ?", (uid,)
            ) as cur:
                row = await cur.fetchone()
            if row:
                land_level = int(row[0])
        except Exception:
            pass

        reinc = int(getattr(player, "reincarnation_count", 0) or 0)

        lines = [
            "📖【仙途回忆录】",
            "━━━━━━━━━━━━━━━",
            f"📜 道号：{player.user_name or uid[:8]}" + (f" · 第 {reinc} 世" if reinc else " · 初入仙途"),
            f"🧘 境界：{level_name} · 修为 {player.experience:,}",
            "━━━━━━━━━━━━━━━",
            "【⚔️ 战斗篇】",
            f"  · 镇妖塔最高：第 {tower_best} 层",
            f"  · 累计除妖：{hunt_total} 只",
            f"  · 天梯：{ladder_pts} 分（{tier_name}）· {ladder_wins} 胜",
            "【🧧 积累篇】",
            f"  · 道心 {daoxin} · 功德 {karma:+d} · 师德 {virtue}",
            f"  · 仙缘点 {fate} · 轮回玉 {jade:,}",
            "【🏮 生活篇】",
            f"  · 灵石 {player.gold:,} · 银行存款 {bank_balance:,}",
            f"  · 宗门贡献 {sect_contrib:,} · 洞天 Lv.{land_level}",
            "━━━━━━━━━━━━━━━",
            "💡 仙途漫漫，每一步都算数。",
        ]
        return "\n".join(lines)

    @staticmethod
    def _ladder_tier(points: int):
        tiers = [
            (0, "🥉 青铜剑士"), (30, "🥈 白银游侠"), (80, "🥇 黄金剑豪"),
            (160, "💠 铂金武尊"), (280, "💎 钻石战圣"), (450, "🔮 宗师·通神"),
        ]
        idx = 0
        for i, (th, name) in enumerate(tiers):
            if points >= th:
                idx = i
        return idx, tiers[idx][1]
