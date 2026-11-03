# managers/player_bounty_manager.py
"""悬赏行会：玩家发布/接取的真实玩家悬赏（v3.19.0 新玩法）

与系统悬赏（bounty_manager）完全独立：
- 发布者预扣赏金托管进 system_config
- 接单者提交后领取托管赏金
- 发布者可在未被接单前取消取回；已被接单则取消需支付 50% 违约金给接单者
- 悬赏 72 小时未完成自动退回发布者

v3.25.5 并发加固：整池 JSON 读-改-写全部改走 syscfg_cas 抢占（失败重读重试），
资金操作在 CAS 成功后执行、失败自动回滚，消除并发双领托管赏金/退款双发/出价覆盖。
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
    CAS_RETRIES = 3          # 并发冲突重试次数

    def __init__(self, db: DataBase):
        self.db = db

    def _pool_key(self) -> str:
        return "pblty_pool"

    async def _load_pool_raw(self) -> Tuple[str, list]:
        """返回 (原始 JSON 串, 解析后的池)；raw 供 CAS 期望值使用"""
        raw = await self.db.ext.get_system_config(self._pool_key())
        if not raw:
            return "", []
        try:
            data = json.loads(raw)
            return raw, (data if isinstance(data, list) else [])
        except (json.JSONDecodeError, TypeError):
            return raw, []

    async def _load_pool(self) -> list:
        return (await self._load_pool_raw())[1]

    async def _save_pool_cas(self, old_raw: str, new_pool: list) -> bool:
        """CAS 覆写整池：仅当池未被并发修改时写入成功"""
        return await self.db.ext.syscfg_cas(
            self._pool_key(), json.dumps(new_pool, ensure_ascii=False), old_raw or None
        )

    async def _deduct_gold_cond(self, user_id: str, amount: int) -> bool:
        """条件原子扣款：余额不足时失败（不像 add_player_gold 会钳 0 透支）"""
        cursor = await self.db.conn.execute(
            "UPDATE players SET gold = gold - ? WHERE user_id = ? AND gold >= ?",
            (amount, user_id, amount)
        )
        await self.db.conn.commit()
        return cursor.rowcount > 0

    async def _cleanup_expired(self) -> Tuple[list, int]:
        """过期悬赏退回发布者（v3.24.0：被接单但 24h 未提交的也自动退回）
        v3.25.5：CAS 抢占整池成功后才退款，防并发双退。
        返回 (清理后的最新池, 退还人数)；重试耗尽返回当前快照与 0"""
        for _ in range(self.CAS_RETRIES):
            raw, pool = await self._load_pool_raw()
            now = int(time.time())
            kept, expired = [], []
            for b in pool:
                expired_unposted = now - b["created_at"] > self.EXPIRE_SECONDS and not b.get("taken_by")
                taken_stale = b.get("taken_by") and now - b.get("taken_at", 0) > 24 * 3600
                (expired if (expired_unposted or taken_stale) else kept).append(b)
            if not expired:
                return pool, 0
            if await self._save_pool_cas(raw, kept):
                for b in expired:
                    await self.db.add_player_gold(b["poster_id"], b["reward"])
                    if b.get("taken_by"):
                        try:
                            from .enhance_systems import MailboxManager
                            await MailboxManager(self.db).send(
                                b["poster_id"], "悬赏行会通知",
                                f"你的悬赏（#{b['id']}「{b['desc']}」）被接单后 24 小时未完成，赏金 {b['reward']:,} 灵石已退回。"
                            )
                        except Exception:
                            pass
                return kept, len(expired)
        return await self._load_pool(), 0

    async def post(self, player: Player, desc: str, reward: int) -> Tuple[bool, str]:
        """/发布悬赏 <描述> <赏金>"""
        desc = (desc or "").strip()
        if not (2 <= len(desc) <= 30):
            return False, "❌ 悬赏描述需为 2-30 个字。"
        if not (self.MIN_REWARD <= reward <= self.MAX_REWARD):
            return False, f"❌ 赏金需在 {self.MIN_REWARD:,} - {self.MAX_REWARD:,} 灵石之间。"
        if player.gold < reward:
            return False, f"❌ 灵石不足！赏金 {reward:,} 需预扣托管（当前持有 {player.gold:,}）。"

        pool, _ = await self._cleanup_expired()
        if len(pool) >= self.MAX_ACTIVE:
            return False, f"❌ 悬赏行会已满（上限 {self.MAX_ACTIVE} 条），稍后再试。"
        mine = [b for b in pool if b["poster_id"] == player.user_id and not b.get("taken_by")]
        if len(mine) >= self.MAX_PER_POSTER:
            return False, f"❌ 你已发布 {self.MAX_PER_POSTER} 条未完成悬赏，先等它们完成或取消。"

        for _ in range(self.CAS_RETRIES):
            raw, pool = await self._load_pool_raw()
            if len(pool) >= self.MAX_ACTIVE:
                return False, f"❌ 悬赏行会已满（上限 {self.MAX_ACTIVE} 条），稍后再试。"
            mine = [b for b in pool if b["poster_id"] == player.user_id and not b.get("taken_by")]
            if len(mine) >= self.MAX_PER_POSTER:
                return False, f"❌ 你已发布 {self.MAX_PER_POSTER} 条未完成悬赏，先等它们完成或取消。"
            next_id = max([b["id"] for b in pool], default=0) + 1
            new_pool = pool + [{
                "id": next_id,
                "poster_id": player.user_id,
                "poster_name": player.user_name or player.user_id[:8],
                "desc": desc,
                "reward": reward,
                "taken_by": None,
                "taken_name": None,
                "taken_at": 0,
                "created_at": int(time.time()),
            }]
            # 先条件原子扣款（防透支），CAS 失败则退款重试
            if not await self._deduct_gold_cond(player.user_id, reward):
                return False, f"❌ 灵石不足！赏金 {reward:,} 需预扣托管。"
            if await self._save_pool_cas(raw, new_pool):
                return True, (
                    f"📜 悬赏已发布！（编号 {next_id}）\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"「{desc}」\n"
                    f"赏金：{reward:,} 灵石（已托管）\n"
                    f"72 小时内无人接单将自动退回赏金\n"
                    f"💡 其他道友可用 /悬赏行会 查看、/接玩家悬赏 <编号> 接单"
                )
            await self.db.add_player_gold(player.user_id, reward)  # 回滚扣款
        return False, "⚠️ 悬赏行会当前繁忙，请稍后再试。"

    async def take(self, player: Player, bounty_id: int) -> Tuple[bool, str]:
        """/接玩家悬赏 <编号>"""
        for _ in range(self.CAS_RETRIES):
            raw, pool = await self._load_pool_raw()
            target = next((b for b in pool if b["id"] == bounty_id), None)
            if target is None:
                return False, "❌ 未找到该编号的悬赏（可能已被完成或过期）。"
            if target["poster_id"] == player.user_id:
                return False, "❌ 不能接自己发布的悬赏。"
            if target.get("taken_by"):
                return False, f"❌ 该悬赏已被【{target.get('taken_name', '他人')}】接下。"
            new_pool = []
            for b in pool:
                if b["id"] == bounty_id:
                    b = dict(b)
                    b["taken_by"] = player.user_id
                    b["taken_name"] = player.user_name or player.user_id[:8]
                    b["taken_at"] = int(time.time())
                new_pool.append(b)
            # CAS：同一时刻仅一人能抢占接单位
            if await self._save_pool_cas(raw, new_pool):
                return True, (
                    f"⚔️ 你接下了悬赏（编号 {bounty_id}）：{target['desc']}\n"
                    f"完成 /玩家悬赏完成 {bounty_id} 提交，赏金 {target['reward']:,} 灵石到手！\n"
                    f"💡 接单 {self.MIN_RUN_MINUTES} 分钟后才能提交。"
                )
        return False, "⚠️ 该悬赏正被他人抢接，请稍后再试。"

    async def verify_and_pay(self, taker: Player, bounty_id: int) -> Tuple[bool, str]:
        """/玩家悬赏完成 <编号>：提交并领取托管赏金"""
        for _ in range(self.CAS_RETRIES):
            raw, pool = await self._load_pool_raw()
            target = next((b for b in pool if b["id"] == bounty_id), None)
            if target is None:
                return False, "❌ 未找到该编号的悬赏。"
            if target.get("taken_by") != taker.user_id:
                return False, "❌ 该悬赏不是由你接下的。"
            elapsed = int(time.time()) - target["taken_at"]
            if elapsed < self.MIN_RUN_MINUTES * 60:
                remain = self.MIN_RUN_MINUTES * 60 - elapsed
                return False, f"❌ 接单尚未满 {self.MIN_RUN_MINUTES} 分钟（还需 {remain // 60} 分），再等等。"
            new_pool = [b for b in pool if b["id"] != bounty_id]
            # CAS：先摘除悬赏（防并发双领托管赏金），成功后才发钱
            if await self._save_pool_cas(raw, new_pool):
                await self.db.add_player_gold(taker.user_id, target["reward"])
                return True, (
                    f"✅ 悬赏（编号 {bounty_id}）完成！\n"
                    f"获得托管赏金：{target['reward']:,} 灵石\n"
                    f"发布者【{target['poster_name']}】感谢你的效劳。"
                )
        return False, "⚠️ 悬赏行会当前繁忙，请稍后再试。"

    async def cancel(self, player: Player, bounty_id: int) -> Tuple[bool, str]:
        """/玩家悬赏取消 <编号>：未接单全额退；已接单付 50% 违约金"""
        for _ in range(self.CAS_RETRIES):
            raw, pool = await self._load_pool_raw()
            target = next((b for b in pool if b["id"] == bounty_id), None)
            if target is None:
                return False, "❌ 未找到该编号的悬赏。"
            if target["poster_id"] != player.user_id:
                return False, "❌ 只能取消自己发布的悬赏。"
            new_pool = [b for b in pool if b["id"] != bounty_id]
            # CAS：先摘除（防并发双退/双份违约金），成功后才走资金
            if await self._save_pool_cas(raw, new_pool):
                if target.get("taken_by"):
                    penalty = int(target["reward"] * self.CANCEL_PENALTY)
                    await self.db.add_player_gold(player.user_id, target["reward"] - penalty)
                    await self.db.add_player_gold(target["taken_by"], penalty)
                    return True, (
                        f"📄 悬赏（编号 {bounty_id}）已取消。\n"
                        f"因已被【{target.get('taken_name', '他人')}】接单，支付违约金 {penalty:,} 灵石，"
                        f"退回 {target['reward'] - penalty:,} 灵石。"
                    )
                await self.db.add_player_gold(player.user_id, target["reward"])
                return True, f"📄 悬赏（编号 {bounty_id}）已取消，托管赏金 {target['reward']:,} 灵石已退回。"
        return False, "⚠️ 悬赏行会当前繁忙，请稍后再试。"

    async def handle_board(self, event):
        """/悬赏行会 查看悬赏池"""
        pool, _ = await self._cleanup_expired()

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
