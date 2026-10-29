# managers/marriage_manager.py
"""玩家结契系统 v1.0 - 玩家之间结为道侣（v3.20.0 新玩法）

与仙灵结缘（social_manager 的 npc 道侣）完全独立，是真实玩家之间的道侣关系：
- /结契 @人 发起（发起者耗 5000 灵石礼金），对方 300 秒内 /接受结契
- 结契关系存 system_config：marriage_{uid}（JSON），双向各一条
- 羁绊值 bond 随双修/共同历练增长（主控调用 add_bond），提供修为加成
- /解除结契 需 10000 灵石分手费

约定：
- 状态全存 system_config（JSON），不建新表
- 全中文 + emoji
- 主控负责指令注册与 @ 解析（解析出 target: Player 后调用 propose）
"""

import json
import time
from datetime import datetime
from typing import Optional, Tuple, Dict

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["MarriageManager"]

# 数值水位
PROPOSAL_COST = 5000        # 结契礼金（发起者支付）
GIFT_EXP = 20000            # 结契成功双方各得修为贺礼
DIVORCE_COST = 10000        # 解除结契分手费
REQUEST_EXPIRE = 300        # 结契请求有效期（秒）
BOND_PER = 0.001            # 每 1 点羁绊的加成系数
BOND_BONUS_CAP = 0.05       # 加成上限 5%


class MarriageManager:
    """玩家结契（玩家间道侣）"""

    def __init__(self, db: DataBase):
        self.db = db

    # ===== 存取 =====

    def _marriage_key(self, uid: str) -> str:
        return f"marriage_{uid}"

    def _req_key(self, uid: str) -> str:
        return f"marriage_req_{uid}"

    async def _load_marriage(self, uid: str) -> Optional[Dict]:
        raw = await self.db.ext.get_system_config(self._marriage_key(uid))
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    async def _save_marriage(self, uid: str, partner_id: str, since: int, bond: int = 0):
        await self.db.ext.set_system_config(
            self._marriage_key(uid),
            json.dumps(
                {"partner_id": partner_id, "since": since, "bond": bond},
                ensure_ascii=False,
            ),
        )

    async def _load_req(self, uid: str) -> Optional[Dict]:
        raw = await self.db.ext.get_system_config(self._req_key(uid))
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    async def _save_req(self, uid: str, req: Optional[Dict]):
        await self.db.ext.set_system_config(
            self._req_key(uid), json.dumps(req, ensure_ascii=False) if req else ""
        )

    # ===== 公开方法 =====

    async def propose(self, player: Player, target: Player) -> Tuple[bool, str]:
        """/结契 @人：发起结契请求（发起者耗 5000 灵石礼金）"""
        try:
            me = player.user_id
            other = target.user_id
            if me == other:
                return False, "❌ 不能与自己结契，道侣岂能是另一个自己？"

            my_marriage = await self._load_marriage(me)
            if my_marriage:
                return False, "❌ 你已与一位道侣结契，道途不可三心二意。"
            other_marriage = await self._load_marriage(other)
            if other_marriage:
                return False, (
                    f"❌ 【{target.user_name or other[:8]}】已与一位道侣结契，姻缘已被斩断。"
                )

            # v3.23.0：对方已有未过期请求时拒绝（此前直接覆盖会吞掉前一位提案人的礼金）
            pending = await self._load_req(other)
            if pending and int(time.time()) - pending.get("ts", 0) <= REQUEST_EXPIRE:
                return False, (
                    f"❌ 【{target.user_name or other[:8]}】已有待确认的结契请求，"
                    f"请稍后再试（请求 5 分钟内有效）。"
                )

            if player.gold < PROPOSAL_COST:
                return False, f"❌ 结契需 {PROPOSAL_COST:,} 灵石礼金，你当前持有 {player.gold:,}，灵石不足。"
            await self.db.add_player_gold(me, -PROPOSAL_COST)

            req = {
                "proposer_id": me,
                "proposer_name": player.user_name or me[:8],
                "target_id": other,
                "ts": int(time.time()),
            }
            await self._save_req(other, req)
            remain_min = REQUEST_EXPIRE // 60
            return True, (
                f"💌 结契请求已送达！\n"
                f"━━━━━━━━━━━━━━━\n"
                f"【{player.user_name or me[:8]}】愿与【{target.user_name or other[:8]}】"
                f"结为道侣，同证长生！\n"
                f"💰 发起者已支付礼金 {PROPOSAL_COST:,} 灵石\n"
                f"⏳ 有效期 {remain_min} 分钟\n"
                f"💡 请对方发送 /接受结契 应允（双方各得 {GIFT_EXP:,} 修为贺礼）"
            )
        except Exception as e:
            logger.error(f"[玩家结契] 发起失败: {e}")
            return False, "❌ 结契失败，请稍后再试。"

    async def accept(self, player: Player) -> Tuple[bool, str]:
        """/接受结契：接受待确认请求，双向写入并双方各得 2 万修为贺礼"""
        try:
            me = player.user_id
            req = await self._load_req(me)
            if not req:
                return False, "❌ 你没有待确认的结契请求。"
            if int(time.time()) - req.get("ts", 0) > REQUEST_EXPIRE:
                await self._save_req(me, None)
                return False, "⌛ 结契请求已过期（300 秒内未应允）。"

            proposer_id = req.get("proposer_id", "")
            # 再次校验双方均未结契（防止请求期间另有结契）
            if await self._load_marriage(me) or await self._load_marriage(proposer_id):
                await self._save_req(me, None)
                return False, "❌ 双方中已有人另结道侣，此段姻缘作罢。"

            # v3.23.0：CAS 抢占清空请求（成功者才发贺礼），并发双发已封堵
            req_raw = json.dumps(req, ensure_ascii=False)
            cleared = await self.db.ext.syscfg_cas(self._req_key(me), "", req_raw)
            if not cleared:
                return False, "❌ 该请求已被处理。"

            now = int(time.time())
            await self._save_marriage(me, proposer_id, now)
            await self._save_marriage(proposer_id, me, now)

            # 双方各得 2 万修为贺礼
            await self.db.add_player_exp(me, GIFT_EXP)
            await self.db.add_player_exp(proposer_id, GIFT_EXP)

            since_str = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M")
            return True, (
                f"💞 结契礼成！\n"
                f"━━━━━━━━━━━━━━━\n"
                f"【{req.get('proposer_name', proposer_id[:8])}】与"
                f"【{player.user_name or me[:8]}】于 {since_str} 结为道侣！\n"
                f"天地为证，日月为鉴，愿二位同证大道。\n"
                f"🎁 双方各获得 {GIFT_EXP:,} 修为贺礼\n"
                f"💗 羁绊值随双修/共同历练增长（每 100 羁绊 +1% 修为，上限 5%）\n"
                f"💡 /结契信息 查看道侣羁绊 · /解除结契 需 {DIVORCE_COST:,} 灵石分手费"
            )
        except Exception as e:
            logger.error(f"[玩家结契] 接受失败: {e}")
            return False, "❌ 接受失败，请稍后再试。"

    async def divorce(self, player: Player) -> Tuple[bool, str]:
        """/解除结契：支付 10000 灵石分手费，双向删除"""
        try:
            me = player.user_id
            marriage = await self._load_marriage(me)
            if not marriage:
                return False, "❌ 你尚未与任何道侣结契。"
            if player.gold < DIVORCE_COST:
                return False, (
                    f"❌ 解除结契需 {DIVORCE_COST:,} 灵石分手费，"
                    f"你当前持有 {player.gold:,}，灵石不足。"
                )

            partner_id = marriage.get("partner_id", "")
            await self.db.add_player_gold(me, -DIVORCE_COST)
            await self.db.ext.set_system_config(self._marriage_key(me), "")
            await self.db.ext.set_system_config(self._marriage_key(partner_id), "")

            # 同步清除可能残留的未过期请求（对方再发来的）
            await self._save_req(me, None)

            return True, (
                f"💔 缘尽情断，结契已解除。\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💸 你支付了 {DIVORCE_COST:,} 灵石分手费\n"
                f"🕊️ 往后各自修行，道途珍重。\n"
                f"💡 不必难过，天涯何处无芳草。"
            )
        except Exception as e:
            logger.error(f"[玩家结契] 解除失败: {e}")
            return False, "❌ 解除失败，请稍后再试。"

    async def get_partner_id(self, uid: str) -> Optional[str]:
        """查询结契对象 uid（供主控挂加成，无副作用）"""
        try:
            marriage = await self._load_marriage(uid)
            return marriage.get("partner_id") if marriage else None
        except Exception as e:
            logger.error(f"[玩家结契] 查询伴侣失败: {e}")
            return None

    async def bond_bonus(self, player: Player) -> float:
        """修为加成 = min(0.05, 羁绊 * 0.001)，每 100 羁绊 +1%，上限 5%"""
        try:
            marriage = await self._load_marriage(player.user_id)
            if not marriage:
                return 0.0
            bond = marriage.get("bond", 0)
            try:
                bond = int(bond)
            except (TypeError, ValueError):
                bond = 0
            return min(BOND_BONUS_CAP, max(0, bond) * BOND_PER)
        except Exception as e:
            logger.error(f"[玩家结契] 计算加成失败: {e}")
            return 0.0

    async def add_bond(self, uid_a: str, uid_b: str, n: int = 1):
        """羁绊值增长接口：主控在双修/共同历练后调用（无副作用、异常安全）"""
        try:
            if n <= 0 or uid_a == uid_b:
                return
            for uid, other in ((uid_a, uid_b), (uid_b, uid_a)):
                marriage = await self._load_marriage(uid)
                if not marriage or marriage.get("partner_id") != other:
                    continue
                try:
                    bond = int(marriage.get("bond", 0)) + n
                except (TypeError, ValueError):
                    bond = n
                marriage["bond"] = bond
                await self.db.ext.set_system_config(
                    self._marriage_key(uid), json.dumps(marriage, ensure_ascii=False)
                )
        except Exception as e:
            logger.error(f"[玩家结契] 增加羁绊失败: {e}")

    async def handle_info(self, player: Player, event) -> str:
        """/结契信息：查看伴侣、结契天数、羁绊与加成"""
        try:
            me = player.user_id
            marriage = await self._load_marriage(me)
            if not marriage:
                return (
                    "💔 你尚未与任何道侣结契。\n"
                    "💡 /结契 @道友 向心仪之人发起结契（礼金 5000 灵石）"
                )

            partner_id = marriage.get("partner_id", "")
            since = marriage.get("since", 0)
            days = max(0, (int(time.time()) - since) // 86400) if since else 0
            try:
                bond = int(marriage.get("bond", 0))
            except (TypeError, ValueError):
                bond = 0
            bonus = min(BOND_BONUS_CAP, bond * BOND_PER)

            # 查道号（容错：查不到就显示 uid 前 8 位）
            partner_name = partner_id[:8] if partner_id else "???"
            if partner_id:
                try:
                    partner = await self.db.get_player_by_id(partner_id)
                    if partner:
                        partner_name = partner.user_name or partner_name
                except Exception:
                    pass

            since_str = (
                datetime.fromtimestamp(since).strftime("%Y-%m-%d %H:%M")
                if since else "未知"
            )
            return (
                f"💞 结契信息\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💑 道侣：【{partner_name}】\n"
                f"📅 结契于：{since_str}（已相伴 {days} 天）\n"
                f"💗 羁绊值：{bond}（每 100 羁绊 +1% 修为）\n"
                f"✨ 修为加成：+{bonus * 100:.1f}%\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💡 多与道侣双修/共同历练可提升羁绊"
            )
        except Exception as e:
            logger.error(f"[玩家结契] 信息查询失败: {e}")
            return "❌ 查询失败，请稍后再试。"

    async def handle_pending(self, player: Player, event) -> str:
        """/接受结契 的入口：如有待确认请求直接走 accept 完成展示"""
        try:
            ok, text = await self.accept(player)
            return text
        except Exception as e:
            logger.error(f"[玩家结契] 处理接受失败: {e}")
            return "❌ 处理失败，请稍后再试。"
