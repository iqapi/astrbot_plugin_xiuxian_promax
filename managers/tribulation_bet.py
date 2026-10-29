# managers/tribulation_bet.py
"""渡劫观礼系统 v6.18 - 渡劫期及以上突破时开启全服观礼下注奖池"""
import json
import time
from typing import Tuple, Optional, Dict

from astrbot.api import logger
from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["TribulationBetManager"]

# 观礼门槛：渡劫期（level_index >= 31）及以上境界的突破才开奖池
TRIB_LEVEL = 31
MIN_BET = 100
MAX_BET = 100000

# 状态存 system_config：
#   tribbet_{user_id} = JSON {
#       "open": bool, "success_rate": float, "open_ts": float,
#       "bets": {better_id: {"amount": int, "side": "success"|"fail"}}
#   }
# 兼容旧格式：bets 值若为纯数字，视为押成功


class TribulationBetManager:
    """渡劫观礼：突破执行前开池托管下注，突破结算后按比例瓜分。

    - 下注者的灵石在 open/place_bet 阶段已扣款托管（add_player_gold(-amount)）
    - settle 只发放不扣款；押对者按 (总奖池/押对总额) 比例瓜分（含本金）
    """

    def __init__(self, db: DataBase):
        self.db = db

    # ================= 内部工具 =================

    def _pool_key(self, user_id: str) -> str:
        return f"tribbet_{user_id}"

    async def _load_pool(self, user_id: str) -> Optional[dict]:
        try:
            raw = await self.db.ext.get_system_config(self._pool_key(user_id))
            data = json.loads(raw) if raw else None
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    async def _save_pool(self, user_id: str, pool: dict):
        await self.db.ext.set_system_config(self._pool_key(user_id), json.dumps(pool, ensure_ascii=False))

    @staticmethod
    def _normalize_bets(bets) -> Dict[str, dict]:
        """把 bets 归一化为 {better_id: {"amount": int, "side": str}}"""
        result = {}
        if not isinstance(bets, dict):
            return result
        for uid, val in bets.items():
            if isinstance(val, dict):
                amount = int(val.get("amount", 0))
                side = val.get("side", "success")
            elif isinstance(val, (int, float)):
                amount = int(val)
                side = "success"
            else:
                continue
            if amount > 0:
                result[uid] = {"amount": amount, "side": side if side in ("success", "fail") else "success"}
        return result

    @staticmethod
    def _side_name(side: str) -> str:
        return "✅押突破成功" if side == "success" else "❌押突破失败"

    # ================= 核心逻辑 =================

    async def open_pool(self, player: Player, success_rate: float, actual_success: bool = None) -> bool:
        """突破执行前调用：渡劫期及以上开启全服观礼奖池。

        v3.23.0 重设计（密封信封模型）：突破结果在开池时**封存**进奖池（不下发给任何玩家），
        下注窗口 5 分钟，到期由主控定时 tick() 揭晓开奖——保证玩家下注时结果未公开。
        返回 True 表示奖池已开启；境界不足或已开池返回 False。
        """
        try:
            if player is None or player.level_index < TRIB_LEVEL:
                return False
            key = self._pool_key(player.user_id)
            existing = await self._load_pool(player.user_id)
            if existing and existing.get("open"):
                return False
            pool = {
                "open": True,
                "success_rate": float(success_rate),
                "open_ts": time.time(),
                "end_ts": time.time() + 300,   # 5 分钟下注窗口
                "sealed_success": bool(actual_success) if actual_success is not None else None,
                "target_name": player.user_name or player.user_id[:8],
                "bets": {},
            }
            await self._save_pool(player.user_id, pool)
            return True
        except Exception as e:
            logger.warning(f"[tribbet] open_pool 异常: {e}")
            return False

    async def tick(self) -> str:
        """主控定时调用：开奖到期奖池（密封揭晓）。返回广播文本（空=无事发生）。
        同时兜底清理超过 10 分钟仍未开奖的遗留旧池（退还全部托管款）。"""
        try:
            now = time.time()
            rows = []
            async with self.db.conn.execute(
                "SELECT key, value FROM system_config WHERE key LIKE 'tribbet_%'"
            ) as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                key, raw = row[0], row[1]
                try:
                    pool = json.loads(raw) if raw else None
                except Exception:
                    continue
                if not isinstance(pool, dict) or not pool.get("open"):
                    continue
                uid = key[len("tribbet_"):]
                end_ts = float(pool.get("end_ts", 0) or 0)
                if end_ts and now >= end_ts and pool.get("sealed_success") is not None:
                    return await self._settle_pool(uid, pool)
                if not end_ts or now - float(pool.get("open_ts", now)) > 600:
                    # 遗留旧池/异常池：退还托管款并作废
                    await self._refund_pool(uid, pool)
            return ""
        except Exception as e:
            logger.warning(f"[tribbet] tick 异常: {e}")
            return ""

    async def _refund_pool(self, uid: str, pool: dict):
        """退还奖池全部托管款并关闭（异常池兜底）"""
        try:
            for better_id, bet in self._normalize_bets(pool.get("bets")).items():
                await self.db.add_player_gold(better_id, bet["amount"])
            await self.db.ext.set_system_config(self._pool_key(uid), "")
            logger.info(f"[tribbet] 遗留奖池已作废退款: {uid}")
        except Exception as e:
            logger.warning(f"[tribbet] 遗留奖池退款失败: {e}")

    async def place_bet(self, better: Player, amount: int, side: str = "success") -> Tuple[bool, str]:
        """/观礼下注 <金额>：托管扣款并记入当前开启的奖池。

        - 每人限一次，金额 100-100000
        - side: "success"（默认，押渡劫成功）或 "fail"（押渡劫失败）
        - 先查余额再 add_player_gold(-amount) 扣款，settle 只发不扣
        """
        try:
            if better is None:
                return False, "❌ 道友尚未踏入仙途。"

            # 找到当前全服开启中的奖池（遍历方式：观礼奖池以突破者维度存储，
            # 主控在突破开池广播后，观礼下注统一走最近开启的奖池）
            pool_uid, pool = await self._find_open_pool()
            if pool is None:
                return False, "❌ 当前没有进行中的渡劫观礼。"
            if pool_uid == better.user_id:
                return False, "❌ 天劫加身还分心下注？专心渡劫！"
            if float(pool.get("end_ts", 0) or 0) < time.time():
                return False, "❌ 本场观礼下注窗口已关闭，静候开奖。"

            side = "fail" if side in ("fail", "败", "失败") else "success"

            amount = int(amount)
            if amount < MIN_BET or amount > MAX_BET:
                return False, f"❌ 下注金额需在 {MIN_BET} - {MAX_BET} 灵石之间。"

            if better.gold < amount:
                return False, f"❌ 灵石不足！你只有 {better.gold:,} 灵石。"

            bets = self._normalize_bets(pool.get("bets"))
            if better.user_id in bets:
                return False, "❌ 本场观礼你已下注，每人限押一次。"

            # 托管扣款（先查后扣，扣款即托管）
            await self.db.add_player_gold(better.user_id, -amount)
            bets[better.user_id] = {"amount": amount, "side": side}
            pool["bets"] = bets
            await self._save_pool(pool_uid, pool)

            total = sum(v["amount"] for v in bets.values())
            same_side = sum(v["amount"] for v in bets.values() if v["side"] == side)
            return True, (
                f"✅ 下注成功！你押了 {self._side_name(side)}，投入 {amount:,} 灵石。\n"
                f"💰 本奖池总额 {total:,} 灵石（{self._side_name(side)}侧 {same_side:,}）\n"
                f"💡 突破结算后押对者将按比例瓜分总奖池（含本金）！"
            )
        except Exception as e:
            logger.warning(f"[tribbet] place_bet 异常: {e}")
            return False, "❌ 下注失败，请稍后再试。"

    async def _find_open_pool(self) -> Tuple[Optional[str], Optional[dict]]:
        """查找全服开启中的观礼奖池（同一时间至多一场渡劫观礼）。

        通过 system_config 扫描 tribbet_ 前缀键；数量有限，直接全扫。
        """
        try:
            async with self.db.conn.execute(
                "SELECT key, value FROM system_config WHERE key LIKE 'tribbet_%'"
            ) as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                try:
                    data = json.loads(row[1]) if row[1] else None
                except Exception:
                    continue
                if isinstance(data, dict) and data.get("open"):
                    return row[0][len("tribbet_"):], data
            return None, None
        except Exception as e:
            logger.warning(f"[tribbet] _find_open_pool 异常: {e}")
            return None, None

    async def settle(self, player: Player, success: bool) -> str:
        """（兼容保留）立即结算指定玩家奖池。常规流程走 tick() 密封揭晓。"""
        if player is None:
            return ""
        pool = await self._load_pool(player.user_id)
        if not pool or not pool.get("open"):
            return ""
        return await self._settle_pool(player.user_id, pool)

    async def _settle_pool(self, pool_uid: str, pool: dict) -> str:
        """开奖：押对者瓜分奖池（含本金），返回摘要文本供主控广播。"""
        try:
            # CAS 抢占关闭：防止定时与手动并发双开奖
            closed = await self.db.ext.syscfg_cas(self._pool_key(pool_uid), "", json.dumps(pool, ensure_ascii=False))
            if not closed:
                return ""
            player = await self.db.get_player_by_id(pool_uid)
            target_name = pool.get("target_name") or (player.user_name if player else "神秘修士")
            success = bool(pool.get("sealed_success"))
            win_side = "success" if success else "fail"

            bets = self._normalize_bets(pool.get("bets"))
            total_pool = sum(v["amount"] for v in bets.values())
            win_total = sum(v["amount"] for v in bets.values() if v["side"] == win_side)

            lines = [
                "🗡️【渡劫观礼 · 开奖】",
                "━━━━━━━━━━━━━━━",
            ]

            if success:
                lines.append(f"🎉 {target_name} 渡劫成功，天地同贺！")
            else:
                lines.append(f"💀 {target_name} 渡劫失败……观礼众修哗然。")

            if total_pool <= 0:
                lines.append("（本届观礼无人下注）")
            elif win_total <= 0:
                lines.append("❌ 无人押中，奖池灵石散入天地，充作天道灵机。")
            else:
                lines.append(f"💰 总奖池 {total_pool:,} 灵石，押对总额 {win_total:,} 灵石")
                for uid, bet in bets.items():
                    if bet["side"] != win_side:
                        continue
                    payout = int(total_pool * bet["amount"] / win_total)
                    try:
                        await self.db.add_player_gold(uid, payout)
                        winner = await self.db.get_player_by_id(uid)
                        name = winner.user_name if winner else "神秘修士"
                        lines.append(f"  🏅 {name}：押对 {bet['amount']:,} → 获得 {payout:,} 灵石")
                    except Exception as e:
                        logger.warning(f"[tribbet] 派奖失败 uid={uid}: {e}")

            lines.append("━━━━━━━━━━━━━━━")
            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"[tribbet] settle 异常: {e}")
            return ""

    # ================= 查询指令 =================

    async def handle_pool(self, player: Player, event):
        """/观礼 指令：查看当前奖池与赔率。"""
        try:
            pool_uid, pool = await self._find_open_pool()
            if pool is None:
                yield event.plain_result(
                    "🌫️ 当前没有进行中的渡劫观礼。\n"
                    "💡 渡劫期及以上的道友突破时将开启全服观礼下注。"
                )
                return

            target = await self.db.get_player_by_id(pool_uid)
            name = target.user_name if target else "神秘修士"
            success_rate = float(pool.get("success_rate", 0.5))
            bets = self._normalize_bets(pool.get("bets"))

            success_total = sum(v["amount"] for v in bets.values() if v["side"] == "success")
            fail_total = sum(v["amount"] for v in bets.values() if v["side"] == "fail")
            total_pool = success_total + fail_total

            lines = [
                "🗡️【渡劫观礼】",
                "━━━━━━━━━━━━━━━",
                f"⚡ 天劫目标：{name}",
                f"📊 突破成功率：{success_rate:.0%}",
                f"💰 总奖池：{total_pool:,} 灵石",
                f"  · 押成功：{success_total:,} 灵石（{len([1 for v in bets.values() if v['side'] == 'success'])} 人）",
                f"  · 押失败：{fail_total:,} 灵石（{len([1 for v in bets.values() if v['side'] == 'fail'])} 人）",
            ]
            if success_total > 0:
                lines.append(f"📈 押成功预计赔率：{total_pool / success_total:.2f} 倍")
            if fail_total > 0:
                lines.append(f"📉 押失败预计赔率：{total_pool / fail_total:.2f} 倍")

            if player and player.user_id in bets:
                mine = bets[player.user_id]
                lines.append(f"✅ 你已下注：{mine['amount']:,} 灵石 · {self._side_name(mine['side'])}")
            else:
                lines.append("💡 /观礼下注 <金额> 押成功，/观礼下注 <金额> 败 押失败（每人限一次）")

            lines.append("━━━━━━━━━━━━━━━")
            lines.append("💡 奖池开奖后押对者按比例瓜分总奖池（含本金），押错者灵石归入天道！")
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            logger.warning(f"[tribbet] handle_pool 异常: {e}")
            yield event.plain_result("❌ 观礼信息查询失败，请稍后再试。")
