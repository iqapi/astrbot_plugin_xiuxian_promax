# managers/samsara_manager.py
"""轮回周目 2.0 v6.18 - 基于 reincarnation_count 的周目体系与轮回宝阁"""
import json
from typing import Tuple, Optional

from astrbot.api import logger
from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["SamsaraManager"]

# 轮回玉存 system_config：samsara_jade_{uid} = JSON 整数
JADE_KEY_PREFIX = "samsara_jade_"

# 轮回宝阁商品（编号 -> 商品）
SHOP_ITEMS = {
    1: {"name": "修为大礼包", "desc": "凝聚前世感悟的修为精粹", "exp": 100000, "gold": 0, "price": 100},
    2: {"name": "灵石袋", "desc": "沉甸甸的一袋上品灵石", "exp": 0, "gold": 50000, "price": 100},
    3: {"name": "周目灵石袋", "desc": "轮回者专属的灵石补给", "exp": 0, "gold": 30000, "price": 80},
    4: {"name": "周目大礼包", "desc": "只有大轮回者才配得上的厚礼", "exp": 0, "gold": 300000, "price": 500},
}


class SamsaraManager:
    """轮回周目 2.0：周目加成 + 轮回玉 + 轮回宝阁。

    - 加成接口为纯静态函数，无副作用，主控可直接调用
    - 轮回玉按前世总修为 1% 发放，存 system_config
    """

    def __init__(self, db: DataBase):
        self.db = db

    # ================= 纯加成接口（静态，无副作用）=================

    @staticmethod
    def get_exp_bonus(player: Player) -> float:
        """周目修为加成：每周目全局修为 +5%，6 周目封顶 +30%。"""
        try:
            return min(0.30, max(0, int(player.reincarnation_count or 0)) * 0.05)
        except Exception:
            return 0.0

    @staticmethod
    def get_success_rate_bonus(player: Player) -> float:
        """周目突破成功率加成：每周目 +1%，5 周目封顶 +5%。"""
        try:
            return min(0.05, max(0, int(player.reincarnation_count or 0)) * 0.01)
        except Exception:
            return 0.0

    # ================= 轮回玉 =================

    def _jade_key(self, user_id: str) -> str:
        return f"{JADE_KEY_PREFIX}{user_id}"

    async def get_jade(self, user_id: str) -> int:
        """查询轮回玉余额（无记录返回 0）。v3.23.0 起底层为数值键（兼容旧 JSON 整数格式）。"""
        try:
            raw = await self.db.ext.get_system_config(self._jade_key(user_id))
            if not raw:
                return 0
            raw = str(raw).strip()
            if raw.startswith('"'):
                raw = json.loads(raw)
            return int(raw)
        except Exception:
            return 0

    async def _add_jade(self, user_id: str, delta: int) -> int:
        """增减轮回玉（v3.23.0 改原子数值键；负数结果钳为 0），返回更新后的余额。"""
        try:
            return await self.db.ext.syscfg_adjust_number(self._jade_key(user_id), int(delta))
        except Exception as e:
            logger.warning(f"[samsara] 轮回玉更新失败 uid={user_id}: {e}")
            return await self.get_jade(user_id)

    async def _spend_jade(self, user_id: str, amount: int) -> bool:
        """原子扣玉：仅当余额充足时扣减成功（v3.23.0）"""
        try:
            return await self.db.ext.syscfg_spend(self._jade_key(user_id), int(amount))
        except Exception:
            return False

    async def grant_jade(self, user_id: str, lifetime_exp: int) -> int:
        """转生时调用：按前世总修为 1% 发放轮回玉，返回获得数量。"""
        try:
            if not user_id or lifetime_exp <= 0:
                return 0
            jade = max(0, int(lifetime_exp * 0.01))
            if jade <= 0:
                return 0
            await self._add_jade(user_id, jade)
            return jade
        except Exception as e:
            logger.warning(f"[samsara] grant_jade 异常 uid={user_id}: {e}")
            return 0

    # ================= 轮回宝阁 =================

    async def handle_shop(self, player: Player, event):
        """/轮回宝阁 指令：展示商品列表。"""
        try:
            jade = await self.get_jade(player.user_id)
            lines = [
                "🪷【轮回宝阁】",
                "━━━━━━━━━━━━━━━",
                f"💠 你的轮回玉：{jade:,}",
                "",
            ]
            for no, item in SHOP_ITEMS.items():
                lines.append(f"  {no}号【{item['name']}】 - 💠{item['price']} 轮回玉")
                if item.get("exp"):
                    lines.append(f"     └ {item['desc']}：+{item['exp']:,} 修为")
                if item.get("gold"):
                    lines.append(f"     └ {item['desc']}：+{item['gold']:,} 灵石")
            lines.append("━━━━━━━━━━━━━━━")
            lines.append("💡 /轮回兑换 <编号> 兑换商品；轮回玉在转生时按前世总修为 1% 发放。")
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            logger.warning(f"[samsara] handle_shop 异常: {e}")
            yield event.plain_result("❌ 轮回宝阁暂时无法开启，请稍后再试。")

    async def handle_buy(self, player: Player, event, arg: str = ""):
        """/轮回兑换 <编号> 指令：arg 为编号文本（主控解析后传入）。"""
        try:
            if player.reincarnation_count == 0:
                yield event.plain_result("❌ 轮回玉仅轮回修士可获得，道友尚未经历轮回。")
                return

            no = None
            try:
                no = int(str(arg).strip())
            except (ValueError, TypeError):
                no = None
            if no is None:
                yield event.plain_result("❌ 请输入正确的商品编号，例如：/轮回兑换 1")
                return
            item = SHOP_ITEMS.get(no)
            if item is None:
                yield event.plain_result("❌ 轮回宝阁没有该编号的商品。")
                return

            # v3.23.0：原子扣玉（余额不足即失败，并发不可双兑），成功后发放
            if not await self._spend_jade(player.user_id, item["price"]):
                jade = await self.get_jade(player.user_id)
                yield event.plain_result(
                    f"❌ 轮回玉不足！兑换【{item['name']}】需要 💠{item['price']}，你只有 💠{jade:,}。"
                )
                return
            rewards = []
            try:
                if item.get("exp"):
                    await self.db.add_player_exp(player.user_id, item["exp"])
                    rewards.append(f"📖 修为 +{item['exp']:,}")
                if item.get("gold"):
                    await self.db.add_player_gold(player.user_id, item["gold"])
                    rewards.append(f"💰 灵石 +{item['gold']:,}")
            except Exception as e:
                logger.warning(f"[samsara] 兑换发放异常 uid={player.user_id}: {e}")

            yield event.plain_result(
                f"🪷 兑换成功！【{item['name']}】已入手\n"
                f"  · {'　'.join(rewards)}\n"
                f"💠 剩余轮回玉：{await self.get_jade(player.user_id):,}"
            )
        except Exception as e:
            logger.warning(f"[samsara] handle_buy 异常: {e}")
            yield event.plain_result("❌ 兑换失败，请稍后再试。")

    # ================= 查询指令 =================

    async def handle_info(self, player: Player, event):
        """/轮回信息 指令：查看周目数、当前加成、轮回玉余额。"""
        try:
            count = int(player.reincarnation_count or 0)
            exp_bonus = self.get_exp_bonus(player)
            rate_bonus = self.get_success_rate_bonus(player)
            jade = await self.get_jade(player.user_id)

            lines = [
                "🔄【轮回信息】",
                "━━━━━━━━━━━━━━━",
                f"🌀 当前周目：第 {count} 世",
            ]
            if count == 0:
                lines.append("  · 尚未轮回，无周目加成")
            else:
                lines.append(f"  · 📖 全局修为加成：+{exp_bonus:.0%}")
                lines.append(f"  · ⚡ 突破成功率加成：+{rate_bonus:.0%}")
            lines.append(f"💠 轮回玉余额：{jade:,}")
            lines.append("━━━━━━━━━━━━━━━")
            lines.append("💡 每周目全局修为 +5%（6 周目封顶 +30%），突破成功率 +1%（封顶 +5%）")
            lines.append("💡 /轮回宝阁 可用轮回玉兑换修为与灵石。")
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            logger.warning(f"[samsara] handle_info 异常: {e}")
            yield event.plain_result("❌ 轮回信息查询失败，请稍后再试。")
