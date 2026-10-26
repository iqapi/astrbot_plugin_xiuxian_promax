# managers/calamity_manager.py
"""天道天灾事件 - 魔潮降临，全服捐献抵御"""
import time
from typing import Tuple

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["CalamityManager"]


class CalamityManager:
    """魔潮事件：开启后全服修炼-20%，捐灵石填进度条抵御；超时未达标再罚24小时"""

    KEY_ACTIVE = "tide_active"
    KEY_END = "tide_end_time"
    KEY_TARGET = "tide_target"
    KEY_PROGRESS = "tide_progress"
    KEY_AFTERMATH = "tide_aftermath_until"   # 魔潮肆虐 debuff 截止时间
    DEBUFF_RATE = 0.20                        # 修炼减速 20%

    def __init__(self, db: DataBase):
        self.db = db

    async def _get(self, key: str, default: str = "") -> str:
        v = await self.db.ext.get_system_config(key)
        return v if v is not None else default

    async def is_tide_active(self) -> bool:
        return await self._get(self.KEY_ACTIVE) == "1"

    async def is_aftermath(self) -> bool:
        until = await self._get(self.KEY_AFTERMATH)
        try:
            return bool(until) and int(time.time()) < int(until)
        except ValueError:
            return False

    async def start_tide(self, hours: int = 12) -> Tuple[bool, str]:
        """管理员开启魔潮"""
        if await self.is_tide_active():
            return False, "❌ 魔潮已在肆虐中！"

        players = await self.db.get_all_players()
        if len(players) < 3:
            return False, f"❌ 全服至少需要 3 名修士才能掀起魔潮（当前 {len(players)} 人）。"

        target = max(50000, len(players) * 10000)
        now = int(time.time())
        end_time = now + hours * 3600

        await self.db.ext.set_system_config(self.KEY_ACTIVE, "1")
        await self.db.ext.set_system_config(self.KEY_END, str(end_time))
        await self.db.ext.set_system_config(self.KEY_TARGET, str(target))
        await self.db.ext.set_system_config(self.KEY_PROGRESS, "0")

        return True, (
            f"🌑【天道天灾】魔潮降临！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"域外魔气侵蚀天地灵脉，持续 {hours} 小时！\n"
            f"⚠️ 魔潮期间全服修炼效率 -20%\n"
            f"━━━━━━━━━━━━━━━\n"
            f"抵御目标：全服捐献 {target:,} 灵石\n"
            f"💡 发送 /抵御魔潮 <灵石> 参与抵御\n"
            f"若超时未达标，魔潮将再肆虐 24 小时！"
        )

    async def get_status(self) -> str:
        if not await self.is_tide_active():
            if await self.is_aftermath():
                until = int(await self._get(self.KEY_AFTERMATH, "0"))
                remain = max(0, until - int(time.time()))
                return (
                    f"🌑 魔潮虽退，魔气余毒仍在侵蚀灵脉……\n"
                    f"修炼效率 -20%，还剩 {remain // 3600} 小时{(remain % 3600) // 60}分"
                )
            return "🌤️ 当前风平浪静，天地灵脉运转如常。"

        end_time = int(await self._get(self.KEY_END, "0"))
        target = int(await self._get(self.KEY_TARGET, "0"))
        progress = int(await self._get(self.KEY_PROGRESS, "0"))
        remain = max(0, end_time - int(time.time()))
        pct = min(100.0, progress * 100.0 / max(1, target))

        filled = int(pct // 5)
        bar = "█" * filled + "░" * (20 - filled)

        return (
            f"🌑【魔潮肆虐中】\n"
            f"━━━━━━━━━━━━━━━\n"
            f"抵御进度 [{bar}] {pct:.1f}%\n"
            f"已捐献：{progress:,} / {target:,} 灵石\n"
            f"剩余时间：{remain // 3600}小时{(remain % 3600) // 60}分\n"
            f"⚠️ 魔潮期间全服修炼效率 -20%\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 发送 /抵御魔潮 <灵石> 参与抵御"
        )

    async def resist(self, player: Player, amount: int) -> Tuple[bool, str]:
        """玩家捐献灵石抵御魔潮"""
        if not await self.is_tide_active():
            return False, "❌ 当前没有魔潮，无需抵御。"
        if amount <= 0:
            return False, "❌ 请输入有效的捐献金额。"
        if amount > 500000:
            return False, "❌ 单次捐献上限 500,000 灵石，量力而行。"
        if player.gold < amount:
            return False, f"❌ 灵石不足！你当前持有 {player.gold:,}。"

        player.gold -= amount
        await self.db.update_player(player)

        progress = int(await self._get(self.KEY_PROGRESS, "0")) + amount
        target = int(await self._get(self.KEY_TARGET, "0"))
        await self.db.ext.set_system_config(self.KEY_PROGRESS, str(progress))

        # 记录个人贡献，结算时返还奖励
        contrib_key = f"tide_contrib_{player.user_id}"
        old = int(await self._get(contrib_key, "0"))
        await self.db.ext.set_system_config(contrib_key, str(old + amount))

        if progress >= target:
            return True, (await self._settle_success())[1] + f"\n\n💰 你本次捐献：{amount:,} 灵石"

        pct = min(100.0, progress * 100.0 / max(1, target))
        return True, (
            f"🛡️ 捐献成功！你向天道大阵注入 {amount:,} 灵石。\n"
            f"抵御进度：{progress:,}/{target:,}（{pct:.1f}%）\n"
            f"感谢你为天下苍生出力！"
        )

    async def _settle_success(self) -> Tuple[bool, str]:
        """抵御成功结算"""
        await self.db.ext.set_system_config(self.KEY_ACTIVE, "0")

        # 参与者返还捐献的 15% + 固定奖励
        async with self.db.conn.execute(
            "SELECT key, value FROM system_config WHERE key LIKE 'tide_contrib_%'"
        ) as cursor:
            rows = await cursor.fetchall()

        bonus_note = ""
        # 参与者返还捐献的 15% + 固定奖励 + 24小时「天道庇佑」（闭关收益+10%）
        import time as _time
        for key, value in rows:
            uid = key.replace("tide_contrib_", "")
            contributor = await self.db.get_player_by_id(uid)
            if contributor:
                refund = int(int(value) * 0.15)
                await self.db.add_player_gold(uid, refund + 3000)
            await self.db.ext.set_system_config(key, "")
            await self.db.ext.set_system_config(
                f"tide_bless_{uid}", str(int(_time.time()) + 86400)
            )

        if rows:
            bonus_note = (f"\n🧧 {len(rows)} 位义士各获 3,000 灵石 + 捐献额15%返还"
                          f"\n🌟 义士获得 24 小时【天道庇佑】：闭关收益 +10%")

        return True, (
            f"🌟【天道昭彰】魔潮被成功抵御！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"天下修士同心戮力，魔气溃散！\n"
            f"全服修炼效率恢复正常{bonus_note}"
        )

    async def check_and_expire(self) -> Tuple[bool, str]:
        """超时未达标：魔潮再肆虐24小时（由定时任务调用）"""
        if not await self.is_tide_active():
            return False, ""
        end_time = int(await self._get(self.KEY_END, "0"))
        if int(time.time()) <= end_time:
            return False, ""

        progress = int(await self._get(self.KEY_PROGRESS, "0"))
        target = int(await self._get(self.KEY_TARGET, "0"))
        if progress >= target:
            return await self._settle_success()

        await self.db.ext.set_system_config(self.KEY_ACTIVE, "0")
        await self.db.ext.set_system_config(self.KEY_AFTERMATH, str(int(time.time()) + 86400))

        # 清理贡献记录
        async with self.db.conn.execute(
            "SELECT key FROM system_config WHERE key LIKE 'tide_contrib_%'"
        ) as cursor:
            rows = await cursor.fetchall()
        for (key,) in rows:
            await self.db.ext.set_system_config(key, "")

        return True, (
            f"💀【魔潮得逞】修士们未能及时抵御！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"魔气彻底侵蚀灵脉，全服修炼效率 -20% 将持续 24 小时……\n"
            f"（最终进度：{progress:,}/{target:,}）"
        )

    # ===== v6.16 魔潮自动化 =====

    async def auto_check(self) -> Tuple[bool, str]:
        """定时任务入口：到期结算 + 按日期自动开启魔潮（周六晚 20-23 点自动小魔潮，月初自动大魔潮）
        返回 (是否产生了需要广播的消息, 消息)"""
        import time as _time
        # 1. 到期结算优先
        settled, msg = await self.check_and_expire()
        if settled:
            return True, msg

        # 2. 魔潮进行中或余波未散则不自动开
        if await self.is_tide_active() or await self.is_aftermath():
            return False, ""

        # 3. 自动开启判定（今日是否该开）
        local = _time.localtime()
        now = _time.time()
        key_today = f"tide_auto_{_time.strftime('%Y%m%d')}"
        already = await self._get(key_today)
        if already:
            return False, ""

        is_first_of_month = local.tm_mday == 1
        is_saturday = local.tm_wday == 5
        hour_ok = local.tm_hour >= 20

        if not ((is_first_of_month or is_saturday) and hour_ok):
            return False, ""

        # 标记今日已自动处理（无论成败，防重复尝试）
        await self.db.ext.set_system_config(key_today, "1")

        players = await self.db.get_all_players()
        if len(players) < 3:
            from astrbot.api import logger
            logger.warning(f"【修仙插件】今日为魔潮自动开启日，但全服仅 {len(players)} 人（需≥3），本次跳过")
            return False, ""

        hours = 8 if is_first_of_month else 5
        ok, msg = await self.start_tide(hours)
        if ok:
            scale = "大魔潮（月初·8小时）" if is_first_of_month else "魔潮（周六·5小时）"
            msg = f"🌑【天道自动警示】{scale}降临！\n" + msg
            return True, msg
        return False, ""

    async def get_calendar(self) -> str:
        """仙界日历：未来事件预告"""
        import time as _time
        local = _time.localtime()
        season_idx = get_season_index_pub()
        seasons = ["🌱 春·生发", "☀️ 夏·炎灼", "🍂 秋·丰收", "❄️ 冬·蛰藏"]
        wday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        # 下一个周六
        days_to_sat = (5 - local.tm_wday) % 7 or 7
        # 下个月初
        if local.tm_mday == 1:
            days_to_month = 0
        elif local.tm_mon == 12:
            import calendar as _cal
            days_to_month = _cal.monthrange(local.tm_year, 12)[1] - local.tm_mday + 1
        else:
            import calendar as _cal
            days_to_month = _cal.monthrange(local.tm_year, local.tm_mon)[1] - local.tm_mday + 1

        tide_active = await self.is_tide_active()
        aftermath = await self.is_aftermath()

        lines = [
            "📅 仙界日历",
            "━━━━━━━━━━━━━━━",
            f"今日：{wday_names[local.tm_wday]} · {local.tm_mon}月{local.tm_mday}日",
            f"当前季节：{seasons[season_idx]}（每约一周轮转）",
            f"魔潮状态：{'🌑 肆虐中！/抵御魔潮 参与抵御' if tide_active else ('🌫 余波未散，修炼-20%' if aftermath else '🌤 风平浪静')}",
            "━━━━━━━━━━━━━━━",
            "【事件预告】",
            f"  · 周六 20:00：周六魔潮（{'还有 ' + str(days_to_sat) + ' 天' if not tide_active else '进行中'}）",
            f"  · 每月 1 日 20:00：月初大魔潮（8小时，还有 {days_to_month} 天）",
            "  · 世界Boss：按全服周期自动降临（关注广播）",
            "  · 灵眼：每 2 小时出现一处",
            "━━━━━━━━━━━━━━━",
            "💡 魔潮来袭前囤好灵石，抵御成功者获 24 小时天道庇佑！",
        ]
        return "\n".join(lines)


def get_season_index_pub() -> int:
    """供日历使用的季节索引（避免循环导入 spirit_farm_manager）"""
    return (time.localtime().tm_yday // 7) % 4
