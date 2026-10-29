# managers/season_manager.py
"""天骄榜赛季系统 v6.18 - 90 天一届，按赛季内修为增量排名发奖"""
import json
import time
from typing import Optional, List, Tuple

from astrbot.api import logger
from ..data.data_manager import DataBase
from ..models import Player
from .title_manager import TitleManager

__all__ = ["SeasonManager"]

# 状态存 system_config：
#   season_state        = JSON {season_no, start_ts, end_ts}
#   season_exp_{no}     = JSON {user_id: 赛季内修为增量}
SEASON_STATE_KEY = "season_state"
SEASON_DURATION = 90 * 24 * 3600  # 赛季周期 90 天


class SeasonManager:
    """天骄榜赛季：全服按自然周期开届，统计修为增量并周期结算。

    - record_exp_gain 设计为可高频调用，内部完全 try/except 无副作用
    - 赛季数据按 season_no 隔离，结算后清空旧 key
    """

    def __init__(self, db: DataBase):
        self.db = db
        self.title_manager = TitleManager(db)

    # ================= 内部工具 =================

    def _exp_key(self, season_no: int) -> str:
        return f"season_exp_{season_no}"

    async def _load_state(self) -> Optional[dict]:
        try:
            raw = await self.db.ext.get_system_config(SEASON_STATE_KEY)
            data = json.loads(raw) if raw else None
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    async def _save_state(self, state: dict):
        await self.db.ext.set_system_config(SEASON_STATE_KEY, json.dumps(state, ensure_ascii=False))

    async def _load_exp(self, season_no: int) -> dict:
        try:
            raw = await self.db.ext.get_system_config(self._exp_key(season_no))
            data = json.loads(raw) if raw else None
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    async def _save_exp(self, season_no: int, data: dict):
        await self.db.ext.set_system_config(self._exp_key(season_no), json.dumps(data, ensure_ascii=False))

    # ================= 核心逻辑 =================

    async def ensure_season(self) -> Optional[str]:
        """读取赛季状态，过期则结算旧赛季并开新赛季。

        返回：结算摘要文本（供主控广播）；未结算返回 None。
        """
        try:
            now = time.time()
            state = await self._load_state()
            summary = None

            # 首次启动：直接开第 1 届
            if not state or not isinstance(state.get("season_no"), int):
                state = {"season_no": 1, "start_ts": now, "end_ts": now + SEASON_DURATION}
                await self._save_state(state)
                return None

            # 未到期：维持当前赛季
            if now < float(state.get("end_ts", 0)):
                return None

            # 到期：结算旧赛季
            old_no = state["season_no"]
            # v3.23.0 幂等标记：CAS 抢占结算权（先标记后发奖），防并发/异常后重发
            settled_key = f"season_settled_{old_no}"
            if not await self.db.ext.syscfg_cas(settled_key, "1", None):
                # 已被其他路径结算：仅推进赛季
                state = {"season_no": old_no + 1, "start_ts": now, "end_ts": now + SEASON_DURATION}
                await self._save_state(state)
                return None
            summary = await self._settle(old_no)

            # 开新赛季
            state = {"season_no": old_no + 1, "start_ts": now, "end_ts": now + SEASON_DURATION}
            await self._save_state(state)
            return summary
        except Exception as e:
            logger.warning(f"[season] ensure_season 异常: {e}")
            return None

    async def _settle(self, season_no: int) -> str:
        """结算第 season_no 届：按修为增量前 10 名发放奖励。"""
        exp_data = await self._load_exp_scanned(season_no)
        ranked: List[Tuple[str, int]] = sorted(
            ((uid, int(v)) for uid, v in exp_data.items() if isinstance(v, (int, float)) and v > 0),
            key=lambda x: x[1], reverse=True,
        )[:10]

        lines = [
            f"🏆【第 {season_no} 届天骄榜结算】",
            "━━━━━━━━━━━━━━━",
        ]
        if not ranked:
            lines.append("本届无人登榜，天地寂寥……")
            lines.append("━━━━━━━━━━━━━━━")
            lines.append(f"🌅 第 {season_no + 1} 届天骄榜已开启，各路道友再争高下！")
            await self._clear_season_data(season_no)
            return "\n".join(lines)

        rank_names = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, 11)]
        for idx, (uid, gain) in enumerate(ranked):
            player = await self.db.get_player_by_id(uid)
            name = player.user_name if player else "无名散修"
            reward = await self._grant_reward(uid, player, idx + 1)
            lines.append(f"  {rank_names[idx]} {name}：+{gain:,} 修为 {reward}")

        lines.append("━━━━━━━━━━━━━━━")
        lines.append(f"🌅 第 {season_no + 1} 届天骄榜已开启，各路道友再争高下！")

        await self._clear_season_data(season_no)
        return "\n".join(lines)

    async def _grant_reward(self, uid: str, player: Optional[Player], rank: int) -> str:
        """按名次发奖，返回该名次的奖励说明文本。"""
        try:
            if rank == 1:
                gold_reward = 50000
                extra_note = ""
                # 尝试授予【当代天骄】称号；title_data 中若无该称号定义，
                # grant 返回 (False, "")，此时改为发放 30000 额外灵石代替
                if player is not None:
                    ok, _msg = self.title_manager.grant(player, "当代天骄")
                    if ok:
                        # grant 只改内存对象，此处将 permanent_bonus 落库
                        await self.db.update_player_fields(uid, permanent_bonus=player.permanent_bonus)
                        extra_note = "🏅获称号【当代天骄】"
                    else:
                        await self.db.add_player_gold(uid, 30000)
                        extra_note = "（称号缺失，追加 30000 灵石）"
                else:
                    # 玩家已不存在（删号），称号无法落库，按替补规则补灵石
                    await self.db.add_player_gold(uid, 30000)
                await self.db.add_player_gold(uid, gold_reward)
                return f"奖励 50000 灵石{extra_note}"
            elif rank in (2, 3):
                await self.db.add_player_gold(uid, 20000)
                return "奖励 20000 灵石"
            else:
                await self.db.add_player_gold(uid, 8000)
                return "奖励 8000 灵石"
        except Exception as e:
            logger.warning(f"[season] 发奖失败 uid={uid} rank={rank}: {e}")
            return "（奖励发放异常，请联系管理员）"

    async def _clear_season_data(self, season_no: int):
        """结算后清空旧赛季增量 key（兼容旧 JSON key 与 per-uid 数值键）。"""
        try:
            await self.db.ext.set_system_config(self._exp_key(season_no), "")
            await self.db.conn.execute("DELETE FROM system_config WHERE key LIKE ?", (f"season_exp_{season_no}_%",))
            await self.db.conn.commit()
        except Exception:
            pass

    async def _load_exp_scanned(self, season_no: int) -> dict:
        """v3.23.0 统一读取：合并旧 JSON 快照与 per-uid 数值键（record_exp_gain 的新格式）。"""
        merged: dict = {}
        try:
            legacy = await self._load_exp(season_no)
            merged.update({k: int(v) for k, v in legacy.items()})
            async with self.db.conn.execute(
                "SELECT key, value FROM system_config WHERE key LIKE ?",
                (f"season_exp_{season_no}_%",)
            ) as cursor:
                rows = await cursor.fetchall()
            prefix_len = len(f"season_exp_{season_no}_")
            for key, val in rows:
                uid = key[prefix_len:]
                if uid and str(val).lstrip('-').isdigit():
                    merged[uid] = merged.get(uid, 0) + int(val)
        except Exception:
            pass
        return merged

    # ================= 高频记录接口 =================

    async def record_exp_gain(self, user_id: str, amount: int):
        """累加当前赛季修为增量（v3.23.0 改为 per-uid 原子数值键：高频调用零竞态、无整本覆写）。"""
        try:
            if not user_id or not amount or amount <= 0:
                return
            state = await self._load_state()
            if not state:
                return
            season_no = state.get("season_no")
            if not isinstance(season_no, int):
                return
            await self.db.ext.syscfg_adjust_number(f"season_exp_{season_no}_{user_id}", int(amount))
        except Exception:
            pass  # 赛季记录绝不影响主流程

    # ================= 查询指令 =================

    async def handle_board(self, player: Player, event):
        """/天骄榜 指令：输出赛季编号、剩余天数、修为增量前 10。"""
        try:
            state = await self._load_state()
            if not state:
                yield event.plain_result("❌ 赛季数据尚未初始化，请稍后再试。")
                return

            season_no = state.get("season_no", 1)
            remain_days = max(0, int((float(state.get("end_ts", 0)) - time.time()) // 86400))

            lines = [
                f"🏆【天骄榜 · 第 {season_no} 届】",
                f"⏳ 距赛季结束还有 {remain_days} 天",
                "━━━━━━━━━━━━━━━",
            ]

            exp_data = await self._load_exp_scanned(season_no)
            ranked = sorted(
                ((uid, int(v)) for uid, v in exp_data.items() if isinstance(v, (int, float)) and v > 0),
                key=lambda x: x[1], reverse=True,
            )[:10]

            if not ranked:
                lines.append("虚位以待，尚无天骄登榜！")
            else:
                rank_names = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, 11)]
                for idx, (uid, gain) in enumerate(ranked):
                    target = await self.db.get_player_by_id(uid)
                    name = target.user_name if target else "无名散修"
                    mark = " ← 你" if player and uid == player.user_id else ""
                    lines.append(f"  {rank_names[idx]} {name}：+{gain:,}{mark}")

            lines.append("━━━━━━━━━━━━━━━")
            lines.append("💡 赛季内修为增量实时累计，90 天一届；榜一可得 50000 灵石与称号【当代天骄】！")
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            logger.warning(f"[season] handle_board 异常: {e}")
            yield event.plain_result("❌ 天骄榜查询失败，请稍后再试。")
