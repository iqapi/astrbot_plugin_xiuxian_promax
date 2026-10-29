# managers/group_chronicle_manager.py
"""修仙群史：每日生成"昨日修仙界大事记"（v3.22.0 新玩法）

- 主控定时循环每日调用 build_daily() + mark_broadcast()，广播一次昨日大事记
- /修仙群史 手动查看昨日大事记
- 数据全部从现成的 system_config 键 / world_boss 表尽力读取，读不到的条目静默跳过
- 不建新表，状态（广播去重位）存 system_config（chronicle_bc_{date}）
"""

import json
import time
from typing import Optional

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["GroupChronicleManager"]


class GroupChronicleManager:
    """修仙群史：昨日修仙界大事记"""

    def __init__(self, db: DataBase):
        self.db = db

    # ===== 小工具 =====

    def _date_str(self, offset_days: int = 0) -> str:
        """按本地时间返回 YYYYMMDD（offset 为负即往前推）"""
        return time.strftime("%Y%m%d", time.localtime(time.time() + offset_days * 86400))

    def _date_cn(self, offset_days: int = 0) -> str:
        """返回 M月D日 中文日期"""
        t = time.localtime(time.time() + offset_days * 86400)
        return f"{t.tm_mon}月{t.tm_mday}日"

    async def _get_json(self, key: str) -> Optional[dict]:
        """读取 system_config 中的 JSON，读不到/解析失败返回 None"""
        try:
            raw = await self.db.ext.get_system_config(key)
            if not raw:
                return None
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _uid_name(self, uid) -> str:
        """uid 转名字（同步查缓存不现实，直接给兜底由调用方尽量转）"""
        return str(uid) if uid else ""

    async def _uid_to_name(self, uid) -> str:
        if not uid:
            return ""
        try:
            p = await self.db.get_player_by_id(str(uid))
            if p is not None and getattr(p, "user_name", ""):
                return p.user_name
        except Exception:
            pass
        return str(uid)

    # ===== 各条目采集（全部异常安全，失败返回 None） =====

    async def _entry_weather(self) -> Optional[str]:
        data = await self._get_json(f"weather_today_{self._date_str(-1)}")
        if not data:
            return None
        name = str(data.get("name", "")).strip()
        desc = str(data.get("desc", "")).strip()
        if not name:
            return None
        return f"🌈 昨日天象「{name}」{'：' + desc if desc else ''}笼罩修仙界。"

    async def _entry_rift(self) -> Optional[str]:
        data = await self._get_json(f"rift_affix_{self._date_str(-1)}")
        if not data:
            return None
        name = str(data.get("name", "")).strip()
        if not name:
            return None
        return f"🌀 昨日秘境显世，天降词缀「{name}」，引群修争相探秘。"

    async def _entry_treasure(self) -> Optional[str]:
        data = await self._get_json("treasure_active")
        if not data:
            return None
        name = str(data.get("name", "")).strip()
        if not name:
            return None
        if data.get("claimed"):
            who = await self._uid_to_name(data.get("claimed_by"))
            return f"💎 天材地宝「{name}」已被 {who or '神秘修士'} 摘取，机缘已定。"
        return f"💎 天材地宝「{name}」现世，尚未有主，静待有缘人。"

    async def _entry_world_boss(self) -> Optional[str]:
        try:
            async with self.db.conn.execute(
                "SELECT boss_name, status, current_hp FROM world_boss ORDER BY boss_id DESC LIMIT 1"
            ) as cursor:
                row = await cursor.fetchone()
        except Exception:
            return None
        if not row:
            return None
        name = row[0] or "世界Boss"
        status = row[1]
        hp = row[2]
        if status == 1:
            return f"👹 世界Boss「{name}」肆虐人间（剩余气血 {hp}），众修仍在讨伐中。"
        return f"👹 世界Boss「{name}」已被群修讨平，妖氛暂清。"

    async def _entry_tide(self) -> Optional[str]:
        try:
            raw = await self.db.ext.get_system_config("tide_active")
        except Exception:
            return None
        if raw == "1":
            return "🌊 魔潮肆虐，妖氛冲天，各路散修严阵以守。"
        return None

    async def _entry_tournament(self) -> Optional[str]:
        try:
            async with self.db.conn.execute(
                "SELECT key FROM system_config WHERE key LIKE 'tnm_week_%' ORDER BY key DESC LIMIT 1"
            ) as cursor:
                row = await cursor.fetchone()
        except Exception:
            return None
        if not row:
            return None
        state = await self._get_json(row[0])
        if not state:
            return None
        champ = state.get("champion")
        if not champ:
            return None
        name = await self._uid_to_name(champ)
        return f"⚔️ 斗法台锦标赛落幕，{name or '神秘修士'} 技压群雄，问鼎冠军！"

    async def _entry_ascension(self) -> Optional[str]:
        data = await self._get_json("ascension_project")
        if not data:
            return None
        stage = data.get("stage")
        funds = data.get("funds")
        if stage is None and funds is None:
            return None
        return f"🗼 登仙台修建进度：阶段「{stage}」，已募集灵石 {funds}。"

    async def _entry_records(self) -> Optional[str]:
        """全服之最：修为最高 + 境界最高（兜底条目）"""
        try:
            players = await self.db.get_all_players()
        except Exception as e:
            logger.error(f"修仙群史读取玩家失败: {e}")
            return None
        if not players:
            return None
        lines = []
        try:
            top_exp = max(players, key=lambda p: getattr(p, "experience", 0) or 0)
            if getattr(top_exp, "experience", 0):
                lines.append(f"🏆 修为之最：{top_exp.user_name}（修为 {top_exp.experience:,}）")
            top_lv = max(players, key=lambda p: getattr(p, "level_index", 0) or 0)
            if getattr(top_lv, "level_index", 0):
                lines.append(f"🏔️ 境界之最：{top_lv.user_name}（境界第 {top_lv.level_index + 1} 阶）")
        except Exception:
            pass
        return "\n".join(lines) if lines else None

    # ===== 对外接口 =====

    async def build_daily(self) -> str:
        """生成昨日修仙界大事记文本；读取失败的条目静默跳过，至少输出全服之最兜底"""
        try:
            entries = []
            for fetch in (
                self._entry_weather,
                self._entry_rift,
                self._entry_treasure,
                self._entry_world_boss,
                self._entry_tide,
                self._entry_tournament,
                self._entry_ascension,
            ):
                try:
                    line = await fetch()
                    if line:
                        entries.append(line)
                except Exception as e:
                    logger.debug(f"修仙群史条目 {fetch.__name__} 跳过: {e}")

            records = None
            try:
                records = await self._entry_records()
            except Exception as e:
                logger.debug(f"修仙群史全服之最跳过: {e}")

            header = f"📜【修仙群史 · {self._date_cn(-1)}】\n━━━━━━━━━━━━━━━"
            body = "\n".join(entries) if entries else "☁️ 昨日修仙界风平浪静，无大事记载。"
            tail = "\n━━━━━━━━━━━━━━━"
            if records:
                tail += f"\n⭐ 全服之最 ⭐\n{records}"
            tail += "\n🌙 昨日已成史，今日犹可期。"
            return f"{header}\n{body}{tail}"
        except Exception as e:
            logger.error(f"修仙群史生成异常: {e}")
            return f"📜【修仙群史 · {self._date_cn(-1)}】\n☁️ 史官今日偷懒，大事记暂缺。"

    async def mark_broadcast(self) -> bool:
        """主控每日只广播一次：返回 True=今天尚未广播（应立即 build_daily 并广播），并置位"""
        try:
            key = f"chronicle_bc_{self._date_str()}"
            raw = await self.db.ext.get_system_config(key)
            if raw == "1":
                return False
            await self.db.ext.set_system_config(key, "1")
            return True
        except Exception as e:
            logger.error(f"修仙群史广播置位异常: {e}")
            return False

    async def handle_history(self, event) -> str:
        """/修仙群史 手动查看昨日大事记"""
        try:
            return await self.build_daily()
        except Exception as e:
            logger.error(f"/修仙群史 查询异常: {e}")
            return "❌ 查询修仙群史失败，请稍后再试。"
