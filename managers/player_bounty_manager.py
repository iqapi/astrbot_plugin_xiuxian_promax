# managers/player_bounty_manager.py
"""悬赏行会：玩家发布/接取的真实玩家悬赏（v3.19.0 新玩法）

与系统悬赏（bounty_manager）完全独立：
- 发布者预扣赏金托管进 system_config
- 接单者提交后领取托管赏金
- 发布者可在未被接单前取消取回；已被接单则取消需支付 50% 违约金给接单者
- 悬赏 72 小时未完成自动退回发布者
"""

import json
import time
from typing import Tuple

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["PlayerBountyManager"]


class PlayerBountyManager:
    """玩家悬赏行会"""

    MAX_ACTIVE = 20          # 悬赏池上限
    MAX_PER_POSTER = 3       # 每人同时在池上限
    MIN_REWARD = 1000
    MAX_REWARD = 500000
    EXPIRE_SECONDS = 72 * 3600
    MIN_RUN_MINUTES = 10     # 接单 10 分钟后才可提交
    CANCEL_PENALTY = 0.5     # 接单后取消的违约金比例

    def __init__(self, db: DataBase):
        self.db = db

    def _pool_key(self) -> str:
        return "pblty_pool"

    async def _load_pool(self) -> list:
        raw = await self.db.ext.get_system_config(self._pool_key())
        if not raw:
            return []
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    async def _save_pool(self, pool: list):
        await self.db.ext.set_system_config(self._pool_key(), json.dumps(pool, ensure_ascii=False))

    async def _cleanup_expired(self, pool: list) -> Tuple[list, int]:
        """过期悬赏退回发布者，返回 (新池, 退还人数)
        v3.24.0：被接单但 24h 未提交的悬赏也自动退回发布者（此前赏金会被无限期锁死）"""
        now = int(time.time())
        kept = []
        returned = 0
        for b in pool:
            expired_unposted = now - b["created_at"] > self.EXPIRE_SECONDS and not b.get("taken_by")
            taken_stale = b.get("taken_by") and now - b.get("taken_at", 0) > 24 * 3600
            if expired_unposted or taken_stale:
                await self.db.add_player_gold(b["poster_id"], b["reward"])
                if taken_stale:
                    try:
                        from .enhance_systems import MailboxManager
                        await MailboxManager(self.db).send(
                            b["poster_id"], "悬赏行会通知",
                            f"你的悬赏（#{b['id']}「{b['desc']}」）被接单后 24 小时未完成，赏金 {b['reward']:,} 灵石已退回。"
                        )
                    except Exception:
                        pass
                returned += 1
            else:
                kept.append(b)
        return kept, returned

    async def post(self, player: Player, desc: str, reward: int) -> Tuple[bool, str]:
        """/发布悬赏 <描述> <赏金>"""
        desc = (desc or "").strip()
        if not (2 <= len(desc) <= 30):
            return False, "❌ 悬赏描述需为 2-30 个字。"
        if not (self.MIN_REWARD <= reward <= self.MAX_REWARD):
            return False, f"❌ 赏金需在 {self.MIN_REWARD:,} - {self.MAX_REWARD:,} 灵石之间。"

        pool = await self._load_pool()
        pool, returned = await self._cleanup_expired(pool)
        if returned:
            await self._save_pool(pool)

        if len(pool) >= self.MAX_ACTIVE:
            return False, f"❌ 悬赏行会已满（上限 {self.MAX_ACTIVE} 条），稍后再试。"
        mine = [b for b in pool if b["poster_id"] == player.user_id and not b.get("taken_by")]
        if len(mine) >= self.MAX_PER_POSTER:
            return False, f"❌ 你已发布 {self.MAX_PER_POSTER} 条未完成悬赏，先等它们完成或取消。"
        if player.gold < reward:
            return False, f"❌ 灵石不足！赏金 {reward:,} 需预扣托管（当前持有 {player.gold:,}）。"

        await self.db.add_player_gold(player.user_id, -reward)
        next_id = max([b["id"] for b in pool], default=0) + 1
        pool.append({
            "id": next_id,
            "poster_id": player.user_id,
            "poster_name": player.user_name or player.user_id[:8],
            "desc": desc,
            "reward": reward,
            "taken_by": None,
            "taken_name": None,
            "taken_at": 0,
            "created_at": int(time.time()),
        })
        await self._save_pool(pool)
        return True, (
            f"📜 悬赏已发布！（编号 {next_id}）\n"
            f"━━━━━━━━━━━━━━━\n"
            f"「{desc}」\n"
            f"赏金：{reward:,} 灵石（已托管）\n"
            f"72 小时内无人接单将自动退回赏金\n"
            f"💡 其他道友可用 /悬赏行会 查看、/接玩家悬赏 <编号> 接单"
        )

    async def take(self, player: Player, bounty_id: int) -> Tuple[bool, str]:
        """/接玩家悬赏 <编号>"""
        pool = await self._load_pool()
        for b in pool:
            if b["id"] == bounty_id:
                if b["poster_id"] == player.user_id:
                    return False, "❌ 不能接自己发布的悬赏。"
                if b.get("taken_by"):
                    return False, f"❌ 该悬赏已被【{b.get('taken_name', '他人')}】接下。"
                # 弱并发防护：写入前二次确认（同连接串行下足够）
                b["taken_by"] = player.user_id
                b["taken_name"] = player.user_name or player.user_id[:8]
                b["taken_at"] = int(time.time())
                await self._save_pool(pool)
                return True, (
                    f"⚔️ 你接下了悬赏（编号 {bounty_id}）：{b['desc']}\n"
                    f"完成 /玩家悬赏完成 {bounty_id} 提交，赏金 {b['reward']:,} 灵石到手！\n"
                    f"💡 接单 {self.MIN_RUN_MINUTES} 分钟后才能提交。"
                )
        return False, "❌ 未找到该编号的悬赏（可能已被完成或过期）。"

    async def verify_and_pay(self, taker: Player, bounty_id: int) -> Tuple[bool, str]:
        """/玩家悬赏完成 <编号>：提交并领取托管赏金"""
        pool = await self._load_pool()
        for idx, b in enumerate(pool):
            if b["id"] == bounty_id:
                if b.get("taken_by") != taker.user_id:
                    return False, "❌ 该悬赏不是由你接下的。"
                if int(time.time()) - b["taken_at"] < self.MIN_RUN_MINUTES * 60:
                    remain = self.MIN_RUN_MINUTES * 60 - (int(time.time()) - b["taken_at"])
                    return False, f"❌ 接单尚未满 {self.MIN_RUN_MINUTES} 分钟（还需 {remain // 60} 分），再等等。"
                await self.db.add_player_gold(taker.user_id, b["reward"])
                pool.pop(idx)
                await self._save_pool(pool)
                return True, (
                    f"✅ 悬赏（编号 {bounty_id}）完成！\n"
                    f"获得托管赏金：{b['reward']:,} 灵石\n"
                    f"发布者【{b['poster_name']}】感谢你的效劳。"
                )
        return False, "❌ 未找到该编号的悬赏。"

    async def cancel(self, player: Player, bounty_id: int) -> Tuple[bool, str]:
        """/玩家悬赏取消 <编号>：未接单全额退；已接单付 50% 违约金"""
        pool = await self._load_pool()
        for idx, b in enumerate(pool):
            if b["id"] == bounty_id:
                if b["poster_id"] != player.user_id:
                    return False, "❌ 只能取消自己发布的悬赏。"
                if b.get("taken_by"):
                    penalty = int(b["reward"] * self.CANCEL_PENALTY)
                    await self.db.add_player_gold(player.user_id, b["reward"] - penalty)
                    await self.db.add_player_gold(b["taken_by"], penalty)
                    pool.pop(idx)
                    await self._save_pool(pool)
                    return True, (
                        f"📄 悬赏（编号 {bounty_id}）已取消。\n"
                        f"因已被【{b.get('taken_name', '他人')}】接单，支付违约金 {penalty:,} 灵石，"
                        f"退回 {b['reward'] - penalty:,} 灵石。"
                    )
                await self.db.add_player_gold(player.user_id, b["reward"])
                pool.pop(idx)
                await self._save_pool(pool)
                return True, f"📄 悬赏（编号 {bounty_id}）已取消，托管赏金 {b['reward']:,} 灵石已退回。"
        return False, "❌ 未找到该编号的悬赏。"

    async def handle_board(self, event):
        """/悬赏行会 查看悬赏池"""
        pool = await self._load_pool()
        pool, returned = await self._cleanup_expired(pool)
        if returned:
            await self._save_pool(pool)

        if not pool:
            yield event.plain_result(
                "📜【悬赏行会】\n━━━━━━━━━━━━━━━\n悬赏池空空如也。\n"
                "💡 /发布悬赏 <描述> <赏金> 悬赏天下道友为你办事"
            )
            return

        lines = ["📜【悬赏行会】", "━━━━━━━━━━━━━━━"]
        now = int(time.time())
        for b in pool:
            remain_h = max(0, (b["created_at"] + self.EXPIRE_SECONDS - now) // 3600)
            if b.get("taken_by"):
                status = f"⚔️已被接单（{b.get('taken_name', '?')}）"
            else:
                status = "🟢待接单"
            lines.append(f"#{b['id']} 「{b['desc']}」")
            lines.append(f"   💰{b['reward']:,} 灵石 · 发布:{b['poster_name']} · {status} · 剩{remain_h}h")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("💡 /接玩家悬赏 <编号> 接单 · /玩家悬赏完成 <编号> 提交")
        yield event.plain_result("\n".join(lines))
