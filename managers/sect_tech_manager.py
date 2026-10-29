# managers/sect_tech_manager.py
"""宗门科技树 v1.0 - 宗门捐资研习阵法，全宗共享加成

约定：
- 状态全部存 system_config（JSON，key 前缀 secttech_），不建新表
- 宗主(sect_position=0)/副宗主(sect_position=1) 花自己的灵石为全宗研科技
- 一次捐足下一级费用即升一级（amount < 费用拒绝，取 min，多付不收）
- 三大科技各 5 级：
  · 聚灵阵：全宗成员修炼/历练修为 +1%/级（满 5%）
  · 生财阵：全宗成员灵石收益 +1%/级（满 5%）
  · 玄壁阵：宗门成员 PVP 防御 +2%/级（展示性，暂只在面板显示，不接战斗——
    战斗结算尚未接入宗门科技钩子，后续可在 PVP 计算处按 get_defense_bonus 挂点）
"""

import json
from typing import Optional, Tuple, Dict

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["SectTechManager", "TECHS", "MAX_LEVEL", "KEY_PREFIX"]

# ===== 科技定义 =====
# cost_base: 1 级费用，每级 ×2（费用 = cost_base × 2^(lv-1)，lv 为要升到的等级）
# per_level: 每级加成（聚灵/生财为修为或灵石百分比 0.01；玄壁为防御 0.02）
TECHS: Dict[str, dict] = {
    "聚灵阵": {"cost_base": 20000, "per_level": 0.01, "desc": "全宗修炼/历练修为 +{pct}/级"},
    "生财阵": {"cost_base": 25000, "per_level": 0.01, "desc": "全宗灵石收益 +{pct}/级"},
    "玄壁阵": {"cost_base": 15000, "per_level": 0.02, "desc": "宗门成员 PVP 防御 +{pct}/级（展示性）"},
}

MAX_LEVEL = 5
KEY_PREFIX = "secttech_"


class SectTechManager:
    """宗门科技树：宗主/副宗主捐灵石研习阵法，全宗共享修为/灵石加成"""

    def __init__(self, db: DataBase):
        self.db = db

    # ===== 存取 =====

    @staticmethod
    def _data_key(sect_id: int) -> str:
        return f"{KEY_PREFIX}{int(sect_id)}"

    async def _load_levels(self, sect_id: int) -> Dict[str, int]:
        raw = await self.db.ext.get_system_config(self._data_key(sect_id))
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}

    async def _save_levels(self, sect_id: int, levels: Dict[str, int]):
        await self.db.ext.set_system_config(
            self._data_key(sect_id), json.dumps(levels, ensure_ascii=False)
        )

    @staticmethod
    def _next_cost(tech_name: str, cur_lv: int) -> int:
        """升到 cur_lv+1 级所需灵石"""
        return int(TECHS[tech_name]["cost_base"] * (2 ** cur_lv))

    async def _sect_name(self, sect_id: int) -> str:
        try:
            sect = await self.db.ext.get_sect_by_id(int(sect_id))
            return sect.sect_name if sect else f"宗门#{sect_id}"
        except Exception:
            return f"宗门#{sect_id}"

    # ===== 公开方法 =====

    async def research(self, player: Player, tech_name: str, amount: int) -> Tuple[bool, str]:
        """/宗门研科技 <名称> <灵石>：一次捐足下一级费用即升一级（amount 取 min，不足拒绝）"""
        try:
            tech_name = (tech_name or "").strip()
            if tech_name not in TECHS:
                names = " / ".join(TECHS)
                return False, f"❌ 未知科技「{tech_name or '???'}」。可选：{names}。"
            try:
                amount = int(amount)
            except (TypeError, ValueError):
                return False, "❌ 捐资灵石须为整数。"
            if amount <= 0:
                return False, "❌ 捐资灵石须为正整数。"

            sect_id = getattr(player, "sect_id", 0) or 0
            if sect_id <= 0:
                return False, "🚫 散修无宗可研科技。先 /创建宗门 或 /加入宗门 吧！"
            position = getattr(player, "sect_position", 99)
            if position not in (0, 1):
                return False, "⚖️ 只有宗主或副宗主可为宗门研习科技。"

            levels = await self._load_levels(sect_id)
            cur_lv = int(levels.get(tech_name, 0))
            if cur_lv >= MAX_LEVEL:
                return False, f"✨【{tech_name}】已臻大成（{MAX_LEVEL} 级），无需再研。"

            cost = self._next_cost(tech_name, cur_lv)
            if amount < cost:
                return False, (
                    f"❌ 灵石不足。【{tech_name}】升至 {cur_lv + 1} 级需一次捐足 "
                    f"{cost:,} 灵石（你欲捐 {amount:,}）。"
                )
            if player.gold < cost:
                return False, f"❌ 灵石不足（持有 {player.gold:,}，需 {cost:,}）。"

            # 校验全部通过后才扣灵石并升级
            await self.db.add_player_gold(player.user_id, -cost)
            levels[tech_name] = cur_lv + 1
            await self._save_levels(sect_id, levels)

            sect_name = await self._sect_name(sect_id)
            per = TECHS[tech_name]["per_level"]
            new_lv = cur_lv + 1
            bonus = per * new_lv
            bonus_txt = f"{bonus * 100:.0f}%"
            return True, (
                f"🔭 【{sect_name}】科技研习成功！\n"
                f"━━━━━━━━━━━━━━━\n"
                f"⭐ {tech_name} 升至 {new_lv}/{MAX_LEVEL} 级\n"
                f"💰 捐资 {cost:,} 灵石（由 {player.user_name or player.user_id[:8]} 慷慨解囊）\n"
                f"🎁 当前全宗加成：+{bonus_txt}\n"
                f"💡 /宗门科技 查看科技总览"
            )
        except Exception as e:
            logger.error(f"[宗门科技] 研习失败: {e}")
            return False, "❌ 研习失败，请稍后再试。"

    async def get_cultivate_bonus(self, sect_id: int) -> float:
        """聚灵阵修为加成（0~0.05），供主控挂闭关/历练修为结算；异常安全返回 0.0"""
        try:
            if not sect_id:
                return 0.0
            levels = await self._load_levels(int(sect_id))
            lv = int(levels.get("聚灵阵", 0))
            return min(max(0, lv), MAX_LEVEL) * TECHS["聚灵阵"]["per_level"]
        except Exception as e:
            logger.error(f"[宗门科技] 读取聚灵阵加成失败: {e}")
            return 0.0

    async def get_gold_bonus(self, sect_id: int) -> float:
        """生财阵灵石加成（0~0.05），供主控挂历练/押镖灵石结算；异常安全返回 0.0"""
        try:
            if not sect_id:
                return 0.0
            levels = await self._load_levels(int(sect_id))
            lv = int(levels.get("生财阵", 0))
            return min(max(0, lv), MAX_LEVEL) * TECHS["生财阵"]["per_level"]
        except Exception as e:
            logger.error(f"[宗门科技] 读取生财阵加成失败: {e}")
            return 0.0

    async def get_defense_bonus(self, sect_id: int) -> float:
        """玄壁阵 PVP 防御加成（0~0.10，展示性，暂不接战斗）；异常安全返回 0.0"""
        try:
            if not sect_id:
                return 0.0
            levels = await self._load_levels(int(sect_id))
            lv = int(levels.get("玄壁阵", 0))
            return min(max(0, lv), MAX_LEVEL) * TECHS["玄壁阵"]["per_level"]
        except Exception as e:
            logger.error(f"[宗门科技] 读取玄壁阵加成失败: {e}")
            return 0.0

    async def handle_board(self, event) -> str:
        """/宗门科技 查看本宗科技等级与下一级费用"""
        try:
            sect_id = getattr(event, "sect_id", 0) or 0
            if sect_id <= 0:
                player = getattr(event, "player", None)
                if player is None:
                    # 兜底：按发送者 ID 查玩家
                    try:
                        uid = event.get_sender_id()
                        player = await self.db.get_player_by_id(str(uid))
                    except Exception:
                        player = None
                if player is not None:
                    sect_id = getattr(player, "sect_id", 0) or 0
            if sect_id <= 0:
                return "🚫 未检测到宗门身份。先 /创建宗门 或 /加入宗门 吧！"

            levels = await self._load_levels(sect_id)
            sect_name = await self._sect_name(sect_id)
            lines = [
                f"🔭 【{sect_name}】宗门科技",
                "━━━━━━━━━━━━━━━",
            ]
            for name, info in TECHS.items():
                lv = int(levels.get(name, 0))
                if lv >= MAX_LEVEL:
                    cost_txt = "已臻大成 ✨"
                else:
                    cost_txt = f"下一级需 {self._next_cost(name, lv):,} 灵石"
                pct = info["per_level"] * 100
                desc = info["desc"].format(pct=f"{pct:.0f}%")
                bar = "★" * lv + "☆" * (MAX_LEVEL - lv)
                lines.append(f"⭐ {name} {bar}（{lv}/{MAX_LEVEL}）")
                lines.append(f"   📖 {desc}")
                lines.append(f"   💰 {cost_txt}")
            lines.append("━━━━━━━━━━━━━━━")
            lines.append("💡 /宗门研科技 <科技名> <灵石> 由宗主/副宗主一次捐足下一级费用即升级")
            lines.append("⚠️ 玄壁阵为展示性科技（PVP 防御），暂未接入战斗结算")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"[宗门科技] 查看面板失败: {e}")
            return "❌ 查询失败，请稍后再试。"

    async def cleanup_all(self):
        """宗门解散残留清理：遍历 system_config 中 secttech_ 前缀的键，宗门已不存在的删除。
        主控可低频（如每日）调用，也可不接。"""
        try:
            # 直接查 system_config 表枚举前缀键（不建新表、不动现有代码）
            async with self.db.ext.conn.execute(
                "SELECT key FROM system_config WHERE key LIKE ?", (f"{KEY_PREFIX}%",)
            ) as cursor:
                rows = await cursor.fetchall()
        except Exception as e:
            logger.error(f"[宗门科技] 清理时枚举科技键失败: {e}")
            return

        removed = 0
        for row in rows:
            key = row[0] if not isinstance(row, dict) else row.get("key")
            try:
                sect_id = int(str(key)[len(KEY_PREFIX):])
            except (TypeError, ValueError):
                continue
            try:
                sect = await self.db.ext.get_sect_by_id(sect_id)
            except Exception as e:
                logger.error(f"[宗门科技] 清理时查询宗门 {sect_id} 失败: {e}")
                continue
            if sect is None:
                await self.db.ext.set_system_config(key, "")
                removed += 1
        if removed:
            logger.info(f"[宗门科技] 已清理 {removed} 个解散宗门的残留科技数据")
