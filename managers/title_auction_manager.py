# managers/title_auction_manager.py
"""天道封号台（v3.50.0 新玩法）：灵石竞拍专属封号

- 每月轮换 3 个专属封号（确定性时间种子），每号全服仅 1 人可得
- /封号台 查看本期封号与价格 · /竞拍封号 <编号> 条件原子扣灵石 + CAS 占坑
- 封号写入 permanent_bonus["auction_title"]，由称号系统展示
"""

import json
import time
from typing import Tuple


from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["TitleAuctionManager"]


class TitleAuctionManager:
    """天道封号台：一个封号，万人仰望"""

    def __init__(self, db: DataBase):
        self.db = db

    # 月度封号池（固定 9 个轮换，每月取 3 个）
    TITLE_POOL = [
        {"name": "万剑之主", "price": 200000, "desc": "万剑臣服，剑意冲霄"},
        {"name": "丹道至尊", "price": 180000, "desc": "丹火不熄，炉中乾坤"},
        {"name": "天机神算", "price": 150000, "desc": "算尽天机，未卜先知"},
        {"name": "玄武霸主", "price": 220000, "desc": "玄武护体，不坏金身"},
        {"name": "御兽仙尊", "price": 160000, "desc": "万兽听令，群灵俯首"},
        {"name": "幽冥鬼帝", "price": 200000, "desc": "幽冥之主，鬼神辟易"},
        {"name": "佛光普照", "price": 180000, "desc": "佛光万丈，渡尽众生"},
        {"name": "雷罚天君", "price": 250000, "desc": "雷罚降世，天威难测"},
        {"name": "第一大道", "price": 300000, "desc": "大道第一，众生之上"},
    ]

    @staticmethod
    def _month() -> str:
        return time.strftime("%Y-%m")

    def _goods(self) -> list:
        """当月 3 个封号（确定性）"""
        seed = int(self._month().replace("-", "")) * 31
        rng = __import__("random").Random(seed)
        picks = rng.sample(self.TITLE_POOL, 3)
        return [{"idx": i + 1, **t} for i, t in enumerate(picks)]

    def _owner_key(self, month: str, idx: int) -> str:
        return f"title_auction_{month}_{idx}"

    async def get_board(self, player: Player) -> str:
        month = self._month()
        goods = self._goods()
        lines = [
            f"🏛️【天道封号台】{month}",
            "━━━━━━━━━━━━━━━",
        ]
        for g in goods:
            owner_raw = await self.db.ext.get_system_config(self._owner_key(month, g["idx"]))
            if owner_raw:
                try:
                    owner = json.loads(owner_raw)
                    owner_name = owner.get("buyer_name", "?")
                    status = f"已被【{owner_name}】竞得"
                except (json.JSONDecodeError, TypeError):
                    status = "已被竞得"
            else:
                status = f"💰 {g['price']:,} 灵石"
            lines.append(f"[{g['idx']}] 「{g['name']}」 —— {status}")
            lines.append(f"     {g['desc']}")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("💡 /竞拍封号 <编号> 灵石扣款即得（每号全服限 1 人/月）")
        lines.append("💡 封号永久生效，/我的称号 佩戴展示")
        return "\n".join(lines)

    async def bid(self, player: Player, idx: int) -> Tuple[bool, str]:
        """/竞拍封号 <编号>：条件原子扣款 + CAS 占坑"""
        month = self._month()
        goods = self._goods()
        target = next((g for g in goods if g["idx"] == idx), None)
        if not target:
            return False, "❌ 无效编号。可选 1-3，/封号台 查看。"

        owner_key = self._owner_key(month, idx)
        # 检查是否已被竞得
        existing = await self.db.ext.get_system_config(owner_key)
        if existing:
            try:
                prev = json.loads(existing)
                return False, f"❌ 「{target['name']}」本月已被【{prev.get('buyer_name', '?')}】竞得。"
            except (json.JSONDecodeError, TypeError):
                return False, f"❌ 「{target['name']}」已被竞得。"

        # 条件原子扣款
        cursor = await self.db.conn.execute(
            "UPDATE players SET gold = gold - ? WHERE user_id = ? AND gold >= ?",
            (target["price"], player.user_id, target["price"])
        )
        await self.db.conn.commit()
        if cursor.rowcount == 0:
            return False, f"❌ 灵石不足！「{target['name']}」需 {target['price']:,} 灵石。"

        # CAS 占坑
        record = json.dumps({
            "buyer": player.user_id,
            "buyer_name": player.user_name or player.user_id[:8],
            "title": target["name"],
            "month": month,
        }, ensure_ascii=False)
        claimed = await self.db.ext.syscfg_cas(owner_key, record, None)
        if not claimed:
            # 退款（并发竞争失败）
            await self.db.add_player_gold(player.user_id, target["price"])
            return False, f"❌ 「{target['name']}」刚刚被他人抢先竞得，灵石已退还。"

        # 写入封号（permanent_bonus）
        try:
            data = json.loads(player.permanent_bonus) if player.permanent_bonus else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        data["auction_title"] = target["name"]
        player.permanent_bonus = json.dumps(data, ensure_ascii=False)
        await self.db.update_player_fields(player.user_id, permanent_bonus=player.permanent_bonus)

        return True, (
            f"🏛️ 恭喜！你竞得封号「{target['name']}」！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💰 消耗 {target['price']:,} 灵石\n"
            f"✨ {target['desc']}\n"
            f"📌 封号已写入称号栏，/我的称号 查看\n"
            f"⏳ 本月独占，下月重新竞拍"
        )
