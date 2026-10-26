# managers/title_hooks.py
"""称号颁发钩子：各玩法计数 + 统一检查授予。
计数存 system_config: title_cnt_<key>_<uid>"""
from typing import Optional
from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player


class TitleHooks:
    def __init__(self, db: DataBase):
        self.db = db
        self.tm = None  # 懒加载 TitleManager

    def _tm(self):
        if self.tm is None:
            from .title_manager import TitleManager
            self.tm = TitleManager(self.db)
        return self.tm

    async def bump(self, player: Player, key: str, count: int = 1) -> str:
        """行为计数 +1 并检查颁发。返回提示文本"""
        try:
            ck = f"title_cnt_{key}_{player.user_id}"
            raw = await self.db.ext.get_system_config(ck)
            val = (int(raw) if raw and raw.isdigit() else 0) + count
            await self.db.ext.set_system_config(ck, str(val))
            tm = self._tm()
            # 累进型条件：直接传计数值
            msg = tm.grant_by_key(player, key, val)
            
            # ★ 新增：如果有新获得的称号，必须立即落库，否则图鉴读不到
            if msg:
                await self.db.update_player(player)
                
            # 特殊映射：win_pvp 由决斗专用 key 计数
            return msg
        except Exception as e:
            # ★ 新增：记录异常日志，不再静默吞掉报错
            logger.exception(f"称号 bump 异常 key={key} uid={player.user_id}: {e}")
            return ""

    async def bump_value(self, player: Player, key: str, value) -> str:
        """值型颁发（如 karma/reincarnation/gold_reach/pet_level/land_level/breakthrough）"""
        try:
            tm = self._tm()
            msg = tm.grant_by_key(player, key, value)
            
            # ★ 新增：如果有新获得的称号，必须立即落库
            if msg:
                await self.db.update_player(player)
                
            return msg
        except Exception as e:
            # ★ 新增：记录异常日志
            logger.exception(f"称号 bump_value 异常 key={key} uid={player.user_id}: {e}")
            return ""

    async def grant_manual(self, player: Player, title_name: str) -> str:
        """手动授予（管理员/商店等途径），同理需要落库"""
        try:
            is_new, msg = self._tm().grant(player, title_name)
            if is_new:
                await self.db.update_player(player)
            return msg
        except Exception as e:
            logger.exception(f"称号手动授予异常 title={title_name} uid={player.user_id}: {e}")
            return ""