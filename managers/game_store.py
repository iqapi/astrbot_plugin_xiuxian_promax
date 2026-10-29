# managers/game_store.py
"""GameStore：玩法状态存储统一门面（v3.25.1 精简为真实在用的部分）

KEY 前缀注册表是本文件的核心价值：新玩法接入前必须在此登记前缀，
集中review防止键名冲突/笔误（历史上出过 mentor_relations 表名笔误）。
埋点（note_call）为 require_whitelist 层的真实调用方；
类型化访问方法在 v3.25.1 移除——请直接使用 db.ext 的原子原语
（syscfg_cas / syscfg_adjust_number / syscfg_spend / syscfg_claim_slot），
避免出现两套等价 API 漂移。
"""

import time

__all__ = ["GameStore", "FEATURE_KEYS"]

# 玩法状态 key 前缀注册表（feature -> 前缀说明）
FEATURE_KEYS = {
    "weather": "weather_ 每日天象",
    "collection": "collect_ 图鉴收集领取记录",
    "checkin_milestone": "ckms_ 月度签到里程碑",
    "season": "season_ 天骄榜赛季",
    "tribbet": "tribbet_ 渡劫观礼奖池",
    "samsara": "samsara_jade_ 轮回玉",
    "garden": "garden_ 群聊灵植园",
    "couple_quest": "couple_week_ 道侣周任务",
    "stronghold": "stronghold_week_ 灵脉据点战",
    "rift_affix": "rift_affix_ 秘境词缀",
    "rift_sweep": "sweep_ 秘境扫荡限次",
    "player_bounty": "pblty_ 玩家悬赏",
    "quiz": "quiz_ 科举",
    "wheel": "wheel_ 幸运罗盘",
    "marriage": "marriage_ 玩家结契",
    "achievement": "ach_ 成就",
    "pet_battle": "battle_pet_ 灵宠出战",
    "treasure": "treasure_ 天材地宝",
    "sect_tech": "secttech_ 宗门科技",
    "tournament": "tnm_week_ 斗法台锦标赛",
    "loot_auction": "loot_auction_ Boss拍卖行",
    "ascension": "ascension_ 登仙台世界工程",
    "chronicle": "chronicle_bc_ 修仙群史",
    "title_forge": "(复用 title 体系) 称号熔炼",
    "fortune": "fortune_ 每日求签",
    "stats": "stats_ 指令参与度埋点",
    "admin": "admin_ban_ 封禁",
}


class GameStore:
    """玩法埋点与统计（唯一在用的职责）"""

    def __init__(self, db):
        self.db = db

    def note_call(self, feature: str) -> int:
        """记录某玩法/指令今日调用次数（stats_{feature}_{YYYYMMDD}，日键自动清理）"""
        try:
            key = f"stats_{feature}_{time.strftime('%Y%m%d')}"
            return self.db.ext.syscfg_adjust_number(key, 1)
        except Exception:
            return 0

    async def get_stats(self, feature: str, days: int = 7):
        """读取某玩法/指令最近 N 天的每日调用次数 [(date, count)]"""
        result = []
        try:
            now = time.time()
            for i in range(days):
                day = time.strftime("%Y%m%d", time.localtime(now - i * 86400))
                raw = await self.db.ext.get_system_config(f"stats_{feature}_{day}")
                result.append((day, int(raw) if raw and raw.isdigit() else 0))
        except Exception:
            pass
        return result
