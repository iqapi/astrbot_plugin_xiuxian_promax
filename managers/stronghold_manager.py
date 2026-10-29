# managers/stronghold_manager.py
"""仙盟争霸·灵脉据点战 v1.0 - 每周一届，宗门竞逐五大灵脉据点

约定：
- 状态全部存 system_config（JSON），不建新表
- 玩家花自己的灵石转化为据点积分（1 灵石 = 1 分），积分反超即易主
- 每周一届结算：占领宗门全宗每人 5000 灵石 + 2 万修为，由主控定时调用 weekly_settle
"""

import json
import time
from typing import Optional, Tuple, Dict, List

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["StrongholdManager", "STRONGHOLD_SPOTS", "ATTACK_MIN", "ATTACK_MAX", "SETTLE_GOLD", "SETTLE_EXP"]

# ===== 五大灵脉据点 =====
STRONGHOLD_SPOTS = {
    1: "青云灵脉",
    2: "赤霄火脉",
    3: "玄冥水脉",
    4: "厚土灵脉",
    5: "紫电雷脉",
}

ATTACK_MIN = 100       # 单次投入下限
ATTACK_MAX = 50000     # 单次投入上限
MAX_SPOTS_PER_SECT = 2  # 每周同一宗门最多占据据点数
SETTLE_GOLD = 5000     # 结算：占领宗门每人灵石
SETTLE_EXP = 20000     # 结算：占领宗门每人修为


def current_week() -> str:
    """当前周标识（YYYYWW）"""
    return time.strftime("%Y%W")


class StrongholdManager:
    """灵脉据点战：宗门成员投入灵石抬升本宗积分，积分反超即占领，每周一届结算"""

    def __init__(self, db: DataBase):
        self.db = db

    # ===== 存取 =====

    def _data_key(self, week: str) -> str:
        return f"stronghold_week_{week}"

    def _fresh_data(self, week: str) -> Dict:
        return {
            "week": week,
            "spots": {str(sid): {"occupant": 0, "score": 0, "scores": {}} for sid in STRONGHOLD_SPOTS},
        }

    async def _load_data(self) -> Optional[Dict]:
        raw = await self.db.ext.get_system_config(self._data_key(current_week()))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    async def _save_data(self, data: Optional[Dict]):
        await self.db.ext.set_system_config(
            self._data_key(current_week()), json.dumps(data, ensure_ascii=False) if data else ""
        )

    async def _ensure_data(self) -> Dict:
        data = await self._load_data()
        if not data:
            data = self._fresh_data(current_week())
            await self._save_data(data)
        return data

    async def _sect_name(self, sect_id: int) -> str:
        if not sect_id:
            return "无主之地"
        try:
            sect = await self.db.ext.get_sect_by_id(int(sect_id))
            return sect.sect_name if sect else f"宗门#{sect_id}"
        except Exception:
            return f"宗门#{sect_id}"

    async def _sect_spot_count(self, data: Dict, sect_id: int, exclude_spot: int = 0) -> int:
        """统计某宗门当前占据的据点数（可排除某个据点）"""
        return sum(
            1 for sid, spot in data["spots"].items()
            if spot.get("occupant") == sect_id and int(sid) != exclude_spot
        )

    # ===== 公开方法 =====

    async def attack(self, player: Player, spot_id: int, amount: int) -> Tuple[bool, str]:
        """/进攻灵脉 <编号> <灵石>：花自己灵石转化为据点积分，反超即易主"""
        try:
            if int(spot_id) not in STRONGHOLD_SPOTS:
                ids = " / ".join(str(i) for i in STRONGHOLD_SPOTS)
                return False, f"❌ 据点编号须为 1-5（{ids}）。发送 /灵脉战 查看战况。"
            spot_id = int(spot_id)
            try:
                amount = int(amount)
            except (TypeError, ValueError):
                return False, "❌ 投入灵石须为整数。"

            if amount < ATTACK_MIN or amount > ATTACK_MAX:
                return False, f"❌ 单次投入须在 {ATTACK_MIN:,} ~ {ATTACK_MAX:,} 灵石之间。"

            sect_id = getattr(player, "sect_id", 0) or 0
            if sect_id <= 0:
                return False, "🚫 散修无法参与灵脉之争。先 /创建宗门 或 /加入宗门，为本宗而战！"
            if player.gold < amount:
                return False, f"❌ 灵石不足（持有 {player.gold:,}，需 {amount:,}）。"

            data = await self._ensure_data()
            spot = data["spots"][str(spot_id)]
            scores: Dict[str, int] = spot.setdefault("scores", {})
            key = str(sect_id)
            scores[key] = scores.get(key, 0) + amount
            spot["score"] = scores[key]  # 展示用：本宗当前累计投入

            # 每周同一宗门最多占 MAX_SPOTS_PER_SECT 个据点（若本宗已占此据点则不受限）
            old_occupant = spot.get("occupant", 0)
            changed = False
            if old_occupant != sect_id:
                held = await self._sect_spot_count(data, sect_id)
                if held >= MAX_SPOTS_PER_SECT:
                    return False, f"⚖️ 一周之内，一宗至多据守 {MAX_SPOTS_PER_SECT} 条灵脉。本宗已占 {held} 处。"

            # 扣灵石（通过所有校验后才扣，避免先扣后拒）
            await self.db.add_player_gold(player.user_id, -amount)

            # 积分反超现任占领宗门即易主（无主之地直接占领）
            occ_key = str(old_occupant) if old_occupant else ""
            occ_score = scores.get(occ_key, 0) if occ_key else 0
            if not old_occupant:
                spot["occupant"] = sect_id
                changed = True
            elif scores[key] > occ_score:
                spot["occupant"] = sect_id
                changed = True

            await self._save_data(data)

            old_name = await self._sect_name(old_occupant)
            my_name = await self._sect_name(sect_id)
            lines = [
                f"⚔️ {player.user_name} 代表【{my_name}】进攻【{STRONGHOLD_SPOTS[spot_id]}】！",
                f"💰 投入 {amount:,} 灵石 → 本宗积分 {spot['score']:,}",
            ]
            if changed:
                if old_occupant:
                    lines.append(f"🌀 灵脉易主！积分反超【{old_name}】，【{my_name}】夺下据点！")
                else:
                    lines.append(f"🚩 【{my_name}】率先插旗，占领此灵脉！")
            else:
                lines.append(f"🛡️ 当前守方：【{await self._sect_name(spot.get('occupant', 0))}】")
            return True, "\n".join(lines)
        except Exception as e:
            logger.error(f"[灵脉据点战] 进攻失败: {e}")
            return False, "❌ 进攻失败，请稍后再试。"

    async def weekly_settle(self) -> str:
        """每周一届结算（主控定时调用，week key 变化时触发）。
        返回结算摘要文本供广播；无新周切换时返回空串"""
        try:
            week = current_week()
            raw = await self.db.ext.get_system_config(self._data_key(week))
            if raw:
                return ""  # 本周已初始化，无需结算

            # 读取上一届数据（逐周回查最近 2 周，防漏结）
            last_data = None
            year, wk = int(week[:4]), int(week[4:])
            for back in (1, 2):
                prev_wk = wk - back
                prev_year = year
                if prev_wk < 0:
                    prev_wk += 52
                    prev_year -= 1
                prev_raw = await self.db.ext.get_system_config(self._data_key(f"{prev_year}{prev_wk:02d}"))
                if prev_raw:
                    try:
                        last_data = json.loads(prev_raw)
                        break
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue

            lines = ["🏆 仙盟争霸·灵脉据点战 本届结算", "━━━━━━━━━━━━━━━"]
            # v3.23.0：先落库新一届数据（结算标记），再发奖——中途异常不会重发
            await self._save_data(self._fresh_data(week))
            if not last_data:
                lines.append("上一届风平浪静，无据点归属。")
            else:
                for sid_str, spot in last_data.get("spots", {}).items():
                    occupant = spot.get("occupant", 0)
                    spot_name = STRONGHOLD_SPOTS.get(int(sid_str), f"据点#{sid_str}")
                    if not occupant:
                        lines.append(f"⛰️ {spot_name}：无宗门占领")
                        continue
                    sect_name = await self._sect_name(occupant)
                    try:
                        member_count = len(await self.db.ext.get_sect_members(int(occupant)))
                    except Exception as e:
                        logger.error(f"[灵脉据点战] 获取宗门成员失败: {e}")
                        member_count = 0
                    # v3.24.0 批量 SQL 发放（不再逐成员 UPDATE）
                    await self.db.conn.execute(
                        "UPDATE players SET gold = gold + ?, experience = experience + ? WHERE sect_id = ?",
                        (SETTLE_GOLD, SETTLE_EXP, int(occupant))
                    )
                    await self.db.conn.commit()
                    shown_score = (spot.get("scores") or {}).get(str(occupant), spot.get("score", 0))
                    lines.append(
                        f"⛰️ {spot_name}：【{sect_name}】守土成功"
                        f"（{shown_score:,} 分）→ 全宗 {member_count} 人各得 {SETTLE_GOLD:,} 灵石 + {SETTLE_EXP:,} 修为"
                    )
                occupied = sum(1 for s in last_data.get("spots", {}).values() if s.get("occupant"))
                if not occupied:
                    lines.append("上一届五脉皆无主。")

            lines.append("━━━━━━━━━━━━━━━")
            lines.append("🌅 新一届灵脉战开启，发送 /灵脉战 查看战况，/进攻灵脉 <编号> <灵石> 投入灵石争夺！")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"[灵脉据点战] 周结算失败: {e}")
            return ""

    async def handle_board(self, event) -> str:
        """/灵脉战 查看五据点当前占领与积分"""
        try:
            data = await self._ensure_data()
            lines = [
                "🏔️ 仙盟争霸·灵脉据点战",
                f"🗓️ 本届：第 {current_week()} 周（周一届结算）",
                "━━━━━━━━━━━━━━━",
            ]
            for sid, spot_name in STRONGHOLD_SPOTS.items():
                spot = data["spots"].get(str(sid), {"occupant": 0, "score": 0})
                occ = spot.get("occupant", 0)
                occ_name = await self._sect_name(occ)
                lines.append(f"【{sid}】{spot_name}")
                if occ:
                    shown = (spot.get("scores") or {}).get(str(spot.get("occupant", 0)), spot.get("score", 0))
                    lines.append(f"   🚩 {occ_name} · 积分 {shown:,}")
                else:
                    lines.append(f"   ⚪ 无主之地 · 积分 {spot.get('score', 0):,}")
            lines.append("━━━━━━━━━━━━━━━")
            lines.append(
                f"⚔️ /进攻灵脉 <编号> <灵石>（单次 {ATTACK_MIN:,}~{ATTACK_MAX:,}，1 灵石=1 分）\n"
                "📜 积分反超守方即易主；每宗每周至多据守 2 脉\n"
                f"🎁 周一结算：占领宗门全宗每人 {SETTLE_GOLD:,} 灵石 + {SETTLE_EXP:,} 修为"
            )
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"[灵脉据点战] 查看战况失败: {e}")
            return "❌ 查询失败，请稍后再试。"
