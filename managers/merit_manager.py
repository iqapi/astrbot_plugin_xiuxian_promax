# managers/merit_manager.py
"""功德善堂（v3.26.0 新玩法）：功德/业力的消费闭环

背景：/行善 积功德、劫镖偷窃积业力，但功德此前只有"突破加成/奇遇概率"的被动收益，
没有消费出口。善堂让功德成为软货币（消耗功德会降低突破加成——善行取舍，天道自衡）。

- /功德善堂 查看面板与货架
- /功德兑换 <编号> 原子扣功德兑换
  1 引雷符x1（3功德）  2 空间石x1（5功德）  3 天道庇佑24h（2功德）  4 称号【济世善人】（10功德）
"""

import time
from typing import Tuple

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["MeritManager"]


class MeritManager:
    """功德善堂：以功德兑换珍宝，善行终有回响"""

    # 编号 -> (名称, 所需功德, 类型, 附加数据)
    SHOP = {
        1: {"name": "引雷符 x1", "cost": 3, "type": "item", "item": "引雷符", "count": 1},
        2: {"name": "空间石 x1", "cost": 5, "type": "item", "item": "空间石", "count": 1},
        3: {"name": "天道庇佑 24时（闭关收益+10%）", "cost": 2, "type": "bless"},
        4: {"name": "称号【济世善人】", "cost": 10, "type": "title", "title": "济世善人", "require": 10},
    }

    def __init__(self, db: DataBase, storage_ring_mgr=None):
        self.db = db
        self.storage_ring_mgr = storage_ring_mgr

    async def get_panel(self, player: Player) -> str:
        karma = int(getattr(player, "karma", 0) or 0)
        bless_until = 0
        try:
            raw = await self.db.ext.get_system_config(f"tide_bless_{player.user_id}")
            bless_until = int(raw) if raw and raw.isdigit() else 0
        except Exception:
            pass
        bless_left = max(0, bless_until - int(time.time())) // 3600

        lines = [
            "🪷【功德善堂】",
            "━━━━━━━━━━━━━━━",
            f"☯ 你的功德：{karma:+d}" + ("（业力缠身，多行善可消解）" if karma < 0 else ""),
            f"🌟 天道庇佑：{'剩余 ' + str(bless_left) + ' 小时' if bless_left > 0 else '未生效'}",
            "━━━━━━━━━━━━━━━",
            "【货架】（消耗功德，功德降低会影响突破加成）",
        ]
        for idx, g in self.SHOP.items():
            note = f"（需当前功德≥{g['require']}）" if g.get("require") else ""
            lines.append(f"  [{idx}] {g['name']} —— {g['cost']} 功德{note}")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("💡 /功德兑换 <编号> · /行善 每日积德（+1功德）")
        lines.append("💡 天道庇佑与魔潮抵御奖励同源，可续时叠加")
        return "\n".join(lines)

    async def redeem(self, player: Player, item_id: int) -> Tuple[bool, str]:
        """功德兑换（功德条件原子扣减，防并发双花）"""
        goods = self.SHOP.get(item_id)
        if not goods:
            ids = " / ".join(str(k) for k in self.SHOP)
            return False, f"❌ 无效的兑换编号。可选：{ids}"

        karma = int(getattr(player, "karma", 0) or 0)
        if goods.get("require") and karma < goods["require"]:
            return False, f"❌ 兑换【{goods['name']}】需当前功德 ≥ {goods['require']}（你 {karma}）。\n💡 /行善 积德后再来。"

        # 原子扣功德（不可透支为负——善堂只收善功）
        cursor = await self.db.conn.execute(
            "UPDATE players SET karma = karma - ? WHERE user_id = ? AND karma >= ?",
            (goods["cost"], player.user_id, goods["cost"])
        )
        await self.db.conn.commit()
        if cursor.rowcount == 0:
            return False, f"❌ 功德不足！需要 {goods['cost']}，你当前 {karma}。\n💡 /行善 每日积德（+1功德）。"
        player.karma = karma - goods["cost"]

        if goods["type"] == "item":
            if not self.storage_ring_mgr:
                # 退款
                await self.db.conn.execute(
                    "UPDATE players SET karma = karma + ? WHERE user_id = ?", (goods["cost"], player.user_id)
                )
                await self.db.conn.commit()
                return False, "❌ 储物戒系统未加载，兑换取消。"
            ok, msg = await self.storage_ring_mgr.store_item(player, goods["item"], goods["count"], silent=True)
            if not ok:
                # 退款
                await self.db.conn.execute(
                    "UPDATE players SET karma = karma + ? WHERE user_id = ?", (goods["cost"], player.user_id)
                )
                await self.db.conn.commit()
                player.karma = karma
                return False, f"❌ 兑换失败：储物戒已满（{msg}）\n💰 功德已退还。"
            return True, (
                f"🪷 兑换成功！【{goods['item']}】x{goods['count']} 已存入储物戒\n"
                f"☯ 消耗功德 {goods['cost']}（剩余 {player.karma}）"
            )

        if goods["type"] == "bless":
            now = int(time.time())
            base = now
            try:
                raw = await self.db.ext.get_system_config(f"tide_bless_{player.user_id}")
                old = int(raw) if raw and raw.isdigit() else 0
                base = max(now, old)  # 未过期的庇佑顺延（可叠加续时）
            except Exception:
                pass
            await self.db.ext.set_system_config(f"tide_bless_{player.user_id}", str(base + 86400))
            return True, (
                f"🌟 天道庇佑降临！24 小时内闭关收益 +10%\n"
                f"☯ 消耗功德 {goods['cost']}（剩余 {player.karma}）\n"
                f"💡 若已有庇佑，将顺延 24 小时"
            )

        if goods["type"] == "title":
            try:
                from .title_hooks import TitleHooks
                msg = await TitleHooks(self.db).grant_manual(player, goods["title"])
                if msg:
                    return True, f"🪷 {msg.strip()}\n☯ 消耗功德 {goods['cost']}（剩余 {player.karma}）"
                # 已拥有 → 退款
                await self.db.conn.execute(
                    "UPDATE players SET karma = karma + ? WHERE user_id = ?", (goods["cost"], player.user_id)
                )
                await self.db.conn.commit()
                player.karma = karma
                return False, "❌ 你已拥有该称号，功德已退还。"
            except Exception as e:
                logger.error(f"[功德善堂] 称号兑换异常: {e}")
                await self.db.conn.execute(
                    "UPDATE players SET karma = karma + ? WHERE user_id = ?", (goods["cost"], player.user_id)
                )
                await self.db.conn.commit()
                player.karma = karma
                return False, "❌ 兑换异常，功德已退还。"

        return False, "❌ 未知兑换类型。"
