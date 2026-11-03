# managers/redpacket_manager.py
"""灵石红包（v3.42.0 新玩法）：拼手气红包，仙缘共享

- /发红包 <总额> <份数>：预扣总额（条件原子），按"拼手气"算法预切份额
- /抢红包 <编号>：原子认领一份（syscfg_claim_slot 逐份占坑，天然防重复抢/超抢）
- 5 分钟未领完 → 惰性退还剩余份额给发红包者
- 状态：每个红包一个 JSON 键（redpacket_{id}），无新表
"""

import json
import random
import time
import uuid
from typing import Tuple


from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["RedPacketManager"]


class RedPacketManager:
    """灵石红包：手气最好的道友，请客吃丹"""

    MAX_TOTAL = 100000
    MAX_COUNT = 20
    EXPIRE_SECONDS = 300
    MIN_UNIT = 10  # 每份最低 10 灵石

    def __init__(self, db: DataBase):
        self.db = db

    @staticmethod
    def _key(packet_id: str) -> str:
        return f"redpacket_{packet_id}"

    async def _load(self, packet_id: str):
        raw = await self.db.ext.get_system_config(self._key(packet_id))
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None

    async def send(self, player: Player, total: int, count: int) -> Tuple[bool, str]:
        """/发红包 <总额> <份数>"""
        try:
            total = int(str(total).strip().translate(str.maketrans("０１２３４５６７８９", "0123456789")))
            count = int(str(count).strip())
        except (TypeError, ValueError):
            return False, "❌ 用法：/发红包 <总额> <份数>（如 /发红包 1000 5）"
        if total < count * self.MIN_UNIT:
            return False, f"❌ 总额过低！每份至少 {self.MIN_UNIT} 灵石（{count} 份需 ≥ {count * self.MIN_UNIT:,}）。"
        if total > self.MAX_TOTAL:
            return False, f"❌ 单个红包上限 {self.MAX_TOTAL:,} 灵石——仙界反洗钱条例。"
        if not (1 <= count <= self.MAX_COUNT):
            return False, f"❌ 份数需在 1 - {self.MAX_COUNT} 之间。"

        # 条件原子预扣总额
        cursor = await self.db.conn.execute(
            "UPDATE players SET gold = gold - ? WHERE user_id = ? AND gold >= ?",
            (total, player.user_id, total)
        )
        await self.db.conn.commit()
        if cursor.rowcount == 0:
            return False, f"❌ 灵石不足！红包总额 {total:,}（你持有 {player.gold:,}）。"

        # 拼手气切分：二倍均值法，保证每份 ≥ MIN_UNIT 且恰好分完
        shares = []
        remain, remain_cnt = total, count
        for _i in range(count - 1):
            avg = remain / remain_cnt
            upper = int(avg * 2)
            share = random.randint(self.MIN_UNIT, max(self.MIN_UNIT, upper))
            # 保证剩余份额都可达 MIN_UNIT
            share = min(share, remain - self.MIN_UNIT * (remain_cnt - 1))
            share = max(share, self.MIN_UNIT)
            shares.append(share)
            remain -= share
            remain_cnt -= 1
        shares.append(remain)

        packet_id = uuid.uuid4().hex[:8]
        state = {
            "sender": player.user_id,
            "sender_name": player.user_name or player.user_id[:8],
            "total": total,
            "count": count,
            "shares": shares,
            "claimed": {},
            "created_at": int(time.time()),
            "expire_ts": int(time.time()) + self.EXPIRE_SECONDS,
        }
        await self.db.ext.set_system_config(
            self._key(packet_id), json.dumps(state, ensure_ascii=False)
        )
        return True, (
            f"🧧 {player.user_name or player.user_id[:8]} 发出了拼手气红包！\n"
            "━━━━━━━━━━━━━━━\n"
            f"💰 总额 {total:,} 灵石 · {count} 份\n"
            f"🪪 红包编号：{packet_id}\n"
            f"⏳ 5 分钟内 /抢红包 {packet_id}，手慢无！"
        )

    async def _refund_if_expired(self, packet_id: str, state: dict) -> Tuple[bool, str]:
        """过期惰性结算：未领份额退回发送者。返回 (已过期, 展示消息)"""
        if time.time() <= int(state.get("expire_ts", 0)):
            return False, ""
        # CAS 抢占退款权：以"已过期"标记覆盖
        refunded = {**state, "expired": True}
        claimed = await self.db.ext.syscfg_cas(
            self._key(packet_id), json.dumps(refunded, ensure_ascii=False),
            json.dumps(state, ensure_ascii=False),
        )
        if not claimed:
            return True, "🧧 该红包已过期。"
        unclaimed_idx = [i for i in range(state["count"]) if str(i) not in (state.get("claimed") or {})]
        refund = sum(state["shares"][i] for i in unclaimed_idx)
        if refund > 0:
            await self.db.add_player_gold(state["sender"], refund)
        # 保留展示（领取记录），标记 expired
        return True, (
            f"🧧 红包（{state.get('sender_name', '?')}发出）已过期，"
            f"未领的 {len(unclaimed_idx)} 份（{refund:,} 灵石）已退回发送者。"
        )

    async def grab(self, player: Player, packet_id: str) -> Tuple[bool, str]:
        """/抢红包 <编号>"""
        packet_id = (packet_id or "").strip()
        state = await self._load(packet_id)
        if not state:
            return False, "❌ 红包不存在（编号有误或已被系统清理）。"
        if state.get("expired"):
            return False, "🧧 该红包已过期，手慢了……"
        expired, expire_msg = await self._refund_if_expired(packet_id, state)
        if expired:
            return False, expire_msg
        if player.user_id == state.get("sender"):
            return False, "❌ 不能抢自己的红包（天道看着呢）。"
        if player.user_id in (state.get("claimed") or {}).values():
            return False, "❌ 你已经抢过这个红包了！"

        # 原子占坑：逐份 claim_slot（未被认领的份额才可占）
        claimed = state.get("claimed") or {}
        idx = None
        for i in range(state["count"]):
            if str(i) in claimed:
                continue
            if await self.db.ext.syscfg_claim_slot(f"rp_{packet_id}_{i}", 1):
                idx = i
                break
        if idx is None:
            return False, "🧧 手慢了！红包已被抢完。"

        # CAS 把认领记录写回（失败=他人同时抢走该份 → 尝试下一份由下次调用处理）
        for _ in range(3):
            fresh = await self._load(packet_id)
            if not fresh or fresh.get("expired"):
                return False, "🧧 红包状态已变化。"
            fresh_claimed = dict(fresh.get("claimed") or {})
            if str(idx) in fresh_claimed:
                break  # 该份被抢，下次再试
            fresh_claimed[str(idx)] = player.user_id
            # v3.40.2 修复：必须写入含新认领人的完整状态（原实现 dumps(fresh) 丢失 claimed，
            # 认领记录永远为空 → 同一人可抢光整包）
            if await self.db.ext.syscfg_cas(
                self._key(packet_id), json.dumps({**fresh, "claimed": fresh_claimed}, ensure_ascii=False),
                json.dumps(state, ensure_ascii=False),
            ):
                amount = state["shares"][idx]
                await self.db.add_player_gold(player.user_id, amount)
                lucky = ""
                if amount == max(state["shares"]) and state["count"] > 1:
                    lucky = "（手气最佳！）"
                return True, (
                    f"🧧 你抢到 {amount:,} 灵石{lucky}！\n"
                    f"来自 {state.get('sender_name', '?')} 的红包（{idx + 1}/{state['count']} 份）"
                )
            state = fresh
        return False, "🧧 手慢了！红包已被抢完。"

    async def get_info(self, packet_id: str) -> str:
        packet_id = (packet_id or "").strip()
        state = await self._load(packet_id)
        if not state:
            return "❌ 红包不存在。"
        expired, expire_msg = await self._refund_if_expired(packet_id, state)
        claimed = state.get("claimed") or {}
        lines = [
            f"🧧【红包详情】{packet_id}",
            "━━━━━━━━━━━━━━━",
            f"发起人：{state.get('sender_name', '?')} · 总额 {state['total']:,} / {state['count']} 份",
        ]
        if claimed:
            lines.append("—— 领取记录 ——")
            for idx_str, uid in claimed.items():
                amount = state["shares"][int(idx_str)]
                p = await self.db.get_player_by_id(uid)
                name = (p.user_name if p and p.user_name else uid[:8])
                lines.append(f"  {int(idx_str) + 1}. {name}：{amount:,} 灵石")
        else:
            lines.append("（尚无人领取）")
        left = state["count"] - len(claimed)
        lines.append(f"剩余 {left} 份 · /抢红包 {packet_id}")
        if expired:
            lines.insert(1, expire_msg)
        return "\n".join(lines)
