import asyncio
import time
import random
import json
import re
from datetime import datetime
from functools import wraps
from pathlib import Path
from astrbot.api import logger, AstrBotConfig
from astrbot.api.star import Context, Star, StarTools
from astrbot.api.event import AstrMessageEvent, filter
from .data import DataBase, MigrationManager
from .config_manager import ConfigManager
from .handlers import (
    PlayerHandler, MiscHandler, EquipmentHandler, BreakthroughHandler,
    PillHandler, ShopHandler, StorageRingHandler,
    SectHandlers, CombatHandlers, RankingHandlers,
    RiftHandlers, AdventureHandlers, AlchemyHandlers, ImpartHandlers,
    NicknameHandler, BankHandlers, BountyHandlers, ImpartPkHandlers,
    BlessedLandHandlers, SpiritFarmHandlers, DualCultivationHandlers, SpiritEyeHandlers,
    DailyTaskHandlers, WorldBossHandlers, RobberyHandlers, ReincarnationHandlers,
    GambleHandlers, ForgeHandlers, DemonInvasionHandlers, PetHandlers,
    AuctionHandlers
)
from .managers import (
    CombatManager, SectManager, RiftManager,
    RankingManager, AdventureManager, AlchemyManager, ImpartManager,
    BankManager, BountyManager, ImpartPkManager,
    BlessedLandManager, SpiritFarmManager, DualCultivationManager, SpiritEyeManager,
    DailyTaskManager, WorldBossManager, RobberyManager, ReincarnationManager,
    TutorialManager, GambleManager, ForgeManager, DemonInvasionManager, PetManager,
    AuctionManager, EscortManager, EncounterManager, LifeSkillManager, CalamityManager
)
from .models_extended import UserStatus
# v3.24.0：指令装饰器与新玩法指令拆分至 commands/ 包
from .commands.base import require_whitelist
from .commands.feature_commands import FeatureCommandsMixin


# 指令定义
CMD_HELP = "修仙帮助"
CMD_START_XIUXIAN = "我要修仙"
CMD_PLAYER_INFO = "我的信息"
CMD_START_CULTIVATION = "闭关"
CMD_END_CULTIVATION = "出关"
CMD_CHECK_IN = "签到"
CMD_SHOW_EQUIPMENT = "我的装备"
CMD_EQUIP_ITEM = "装备"
CMD_UNEQUIP_ITEM = "卸下"
CMD_BREAKTHROUGH = "突破"
CMD_BREAKTHROUGH_INFO = "突破信息"
CMD_USE_PILL = "服用丹药"
CMD_SHOW_PILLS = "丹药背包"
CMD_PILL_INFO = "丹药信息"
CMD_PILL_PAVILION = "丹阁"
CMD_WEAPON_PAVILION = "器阁"
CMD_TREASURE_PAVILION = "百宝阁"
CMD_ITEM_INFO = "物品信息"
CMD_BUY = "购买"
CMD_STORAGE_RING = "储物戒"
CMD_RETRIEVE_ITEM = "取出"
CMD_UPGRADE_RING = "更换储物戒"
CMD_DISCARD_ITEM = "丢弃"
CMD_GIFT_ITEM = "赠予"
CMD_ACCEPT_GIFT = "接收"
CMD_REJECT_GIFT = "拒绝"
CMD_SEARCH_ITEM = "搜索物品"
CMD_RETRIEVE_ALL = "取出所有"
CMD_CREATE_SECT = "创建宗门"
CMD_JOIN_SECT = "加入宗门"
CMD_LEAVE_SECT = "退出宗门"
CMD_MY_SECT = "我的宗门"
CMD_SECT_LIST = "宗门列表"
CMD_SECT_DONATE = "宗门捐献"
CMD_SECT_KICK = "踢出成员"
CMD_SECT_TRANSFER = "宗主传位"
CMD_SECT_TASK = "宗门任务"
CMD_FINISH_SECT_TASK = "完成宗门任务"
CMD_SECT_POSITION = "职位变更"
CMD_RANK_LEVEL = "境界排行"
CMD_RANK_POWER = "战力排行"
CMD_RANK_WEALTH = "灵石排行"
CMD_RANK_SECT = "宗门排行"
CMD_RANK_DEPOSIT = "存款排行"
CMD_RANK_CONTRIBUTION = "贡献排行"
CMD_DUEL = "决斗"
CMD_SPAR = "切磋"
CMD_RIFT_LIST = "秘境列表"
CMD_RIFT_EXPLORE = "探索秘境"
CMD_RIFT_COMPLETE = "完成秘境探索"
CMD_RIFT_EXIT = "退出秘境"
CMD_ADVENTURE_START = "开始历练"
CMD_ADVENTURE_COMPLETE = "完成历练"
CMD_ADVENTURE_STATUS = "历练状态"
CMD_ADVENTURE_INFO = "历练信息"
CMD_ALCHEMY_RECIPES = "丹药配方"
CMD_ALCHEMY_CRAFT = "炼制丹药"
CMD_IMPART_INFO = "传承信息"
CMD_CHANGE_NICKNAME = "改道号"
CMD_BANK_INFO = "银行"
CMD_BANK_DEPOSIT = "存灵石"
CMD_BANK_WITHDRAW = "取灵石"
CMD_BANK_INTEREST = "领取利息"
CMD_BANK_LOAN = "贷款"
CMD_BANK_REPAY = "还款"
CMD_BANK_TRANSACTIONS = "银行流水"
CMD_BANK_BREAKTHROUGH_LOAN = "突破贷款"
CMD_BOUNTY_LIST = "悬赏令"
CMD_BOUNTY_ACCEPT = "接取悬赏"
CMD_BOUNTY_STATUS = "悬赏状态"
CMD_BOUNTY_COMPLETE = "完成悬赏"
CMD_BOUNTY_ABANDON = "放弃悬赏"
CMD_IMPART_CHALLENGE = "传承挑战"
CMD_IMPART_RANKING = "传承排行"
CMD_BLESSED_LAND_INFO = "我的洞天"
CMD_BLESSED_LAND_BUY = "购买洞天"
CMD_BLESSED_LAND_UPGRADE = "升级洞天"
CMD_BLESSED_LAND_COLLECT = "洞天收取"
CMD_BLESSED_LAND_ADVANCE = "进阶洞天"
CMD_SPIRIT_FARM_INFO = "我的灵田"
CMD_SPIRIT_FARM_CREATE = "开垦灵田"
CMD_SPIRIT_FARM_PLANT = "种植"
CMD_SPIRIT_FARM_HARVEST = "收获"
CMD_SPIRIT_FARM_UPGRADE = "升级灵田"
CMD_DUAL_CULT_REQUEST = "双修"
CMD_DUAL_CULT_ACCEPT = "接受双修"
CMD_DUAL_CULT_REJECT = "拒绝双修"
CMD_SPIRIT_EYE_INFO = "灵眼信息"
CMD_SPIRIT_EYE_CLAIM = "抢占灵眼"
CMD_SPIRIT_EYE_COLLECT = "灵眼收取"
CMD_SPIRIT_EYE_RELEASE = "释放灵眼"
CMD_REBIRTH = "弃道重修"


class XiuXianPlugin(FeatureCommandsMixin, Star):
    """修仙插件 - 文字修仙游戏"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        _current_dir = Path(__file__).parent
        self.config_manager = ConfigManager(_current_dir)

        files_config = self.config.get("FILES", {})
        db_filename = files_config.get("DATABASE_FILE", "")
        if not db_filename:
            plugin_data_path = Path(StarTools.get_data_dir("astrbot_plugin_xiuxian_promax"))
            plugin_data_path.mkdir(parents=True, exist_ok=True)
            # 未配置时向后兼容：优先沿用旧默认库名（数据目录/插件目录/cwd 任一存在即视为老库），否则用 schema 默认
            if any((d / "xiuxian_data_v2.db").exists() for d in (plugin_data_path, _current_dir, Path("."))):
                db_filename = "xiuxian_data_v2.db"
            else:
                db_filename = "xiuxian_data_lite.db"
        plugin_data_path = StarTools.get_data_dir("astrbot_plugin_xiuxian_promax")
        plugin_data_path.mkdir(parents=True, exist_ok=True)

        # 项目改名迁移：若历史旧目录有数据而新目录为空，自动整体迁移（按时间从新到旧尝试）
        try:
            import shutil as _shutil
            for old_name in ("astrbot_plugin_xiuxian", "astrbot_plugin_monixiuxian2"):
                old_data_path = plugin_data_path.parent / old_name
                if old_data_path.exists() and not any(plugin_data_path.iterdir()):
                    _shutil.copytree(old_data_path, plugin_data_path, dirs_exist_ok=True)
                    logger.info(f"【修仙插件】已将旧数据目录 {old_name} 迁移至 {plugin_data_path.name}")
                    break
        except Exception as e:
            logger.warning(f"【修仙插件】旧数据目录迁移检查失败（不影响新库使用）: {e}")

        db_path = plugin_data_path / db_filename
        self.db = DataBase(str(db_path))

        # ===== 基础管理器与处理器 =====
        self.misc_handler = MiscHandler(self.db)
        self.player_handler = PlayerHandler(self.db, self.config, self.config_manager)
        self.equipment_handler = EquipmentHandler(self.db, self.config_manager)
        self.breakthrough_handler = BreakthroughHandler(self.db, self.config_manager, self.config)
        self.pill_handler = PillHandler(self.db, self.config_manager)
        self.shop_handler = ShopHandler(self.db, self.config, self.config_manager)
        self.storage_ring_handler = StorageRingHandler(self.db, self.config_manager)

        from .core import StorageRingManager
        self.storage_ring_mgr = StorageRingManager(self.db, self.config_manager)

        self.combat_mgr = CombatManager()
        self.sect_mgr = SectManager(self.db, self.config_manager)
        self.rift_mgr = RiftManager(self.db, self.config_manager, self.storage_ring_mgr)
        self.rank_mgr = RankingManager(self.db, self.combat_mgr, self.config_manager)
        self.adventure_mgr = AdventureManager(self.db, self.storage_ring_mgr)
        self.alchemy_mgr = AlchemyManager(self.db, self.config_manager, self.storage_ring_mgr)
        self.impart_mgr = ImpartManager(self.db)

        # ===== 功能处理器 =====
        self.sect_handlers = SectHandlers(self.db, self.sect_mgr)
        self.combat_handlers = CombatHandlers(self.db, self.combat_mgr, self.config_manager)
        self.ranking_handlers = RankingHandlers(self.db, self.rank_mgr)
        self.rift_handlers = RiftHandlers(self.db, self.rift_mgr)
        self.adventure_handlers = AdventureHandlers(self.db, self.adventure_mgr)
        self.alchemy_handlers = AlchemyHandlers(self.db, self.alchemy_mgr)
        self.impart_handlers = ImpartHandlers(self.db, self.impart_mgr)
        self.nickname_handler = NicknameHandler(self.db)

        self.bank_mgr = BankManager(self.db, self.config)
        self.bounty_mgr = BountyManager(self.db, self.storage_ring_mgr)
        self.bank_handlers = BankHandlers(self.db, self.bank_mgr)
        self.bounty_handlers = BountyHandlers(self.db, self.bounty_mgr)

        self.impart_pk_mgr = ImpartPkManager(self.db, self.combat_mgr)
        self.impart_pk_handlers = ImpartPkHandlers(self.db, self.impart_pk_mgr)

        self.blessed_land_mgr = BlessedLandManager(self.db)
        self.blessed_land_handlers = BlessedLandHandlers(self.db, self.blessed_land_mgr)
        self.spirit_farm_mgr = SpiritFarmManager(self.db, self.storage_ring_mgr)
        self.spirit_farm_handlers = SpiritFarmHandlers(self.db, self.spirit_farm_mgr)
        self.dual_cult_mgr = DualCultivationManager(self.db)
        self.dual_cult_handlers = DualCultivationHandlers(self.db, self.dual_cult_mgr)
        self.spirit_eye_mgr = SpiritEyeManager(self.db)
        self.spirit_eye_handlers = SpiritEyeHandlers(self.db, self.spirit_eye_mgr)

        # v6.1 系统
        self.robbery_mgr = RobberyManager(self.db, self.storage_ring_mgr)
        self.robbery_handlers = RobberyHandlers(self.db, self.robbery_mgr)
        self.daily_task_mgr = DailyTaskManager(self.db)
        self.daily_task_handlers = DailyTaskHandlers(self.db, self.daily_task_mgr, self.storage_ring_mgr)
        self.world_boss_mgr = WorldBossManager(self.db, self.config_manager, self.storage_ring_mgr)
        self.world_boss_handlers = WorldBossHandlers(self.db, self.world_boss_mgr)
        self.reinc_mgr = ReincarnationManager(self.db, self.config_manager, self.storage_ring_mgr)
        self.reinc_handlers = ReincarnationHandlers(self.db, self.reinc_mgr)
        self.tutorial_mgr = TutorialManager(self.db)

        # v6.2 & v6.3
        self.gamble_mgr = GambleManager(self.db, self.config_manager, self.storage_ring_mgr)
        self.gamble_handlers = GambleHandlers(self.db, self.gamble_mgr)
        self.forge_mgr = ForgeManager(self.db, self.config_manager, self.storage_ring_mgr)
        self.forge_handlers = ForgeHandlers(self.db, self.forge_mgr)

        # v6.4 天魔入侵
        self.demon_mgr = DemonInvasionManager(self.db)
        self.demon_handlers = DemonInvasionHandlers(self.db, self.demon_mgr, self.storage_ring_mgr)
        self.demon_handlers.context = self.context

        # v6.5 灵兽系统
        self.pet_mgr = PetManager(self.db)
        self.pet_handlers = PetHandlers(self.db, self.pet_mgr)

        # v6.6 交易坊市
        self.auction_mgr = AuctionManager(self.db, self.storage_ring_mgr, self.config_manager)
        self.auction_handlers = AuctionHandlers(self.db, self.auction_mgr)

        # v6.8 押镖劫道 & 奇遇
        self.escort_mgr = EscortManager(self.db, self.combat_mgr, self.storage_ring_mgr)
        self.encounter_mgr = EncounterManager(self.db, self.storage_ring_mgr)

        # v6.10 生活职业 & 魔潮天灾
        self.life_skill_mgr = LifeSkillManager(self.db, self.storage_ring_mgr)
        self.calamity_mgr = CalamityManager(self.db)

        # v6.16 NPC道侣 & 师徒
        from .managers.social_manager import SocialManager
        self.social_mgr = SocialManager(self.db)
        self.player_handler.social_mgr_ref = self.social_mgr
        self.player_handler.sect_coop_ref = None

        # v6.17 称号系统
        from .managers.title_hooks import TitleHooks
        self.title_hooks = TitleHooks(self.db)
        self.title_mgr = self.title_hooks.title_manager
        self.player_handler.title_hooks = self.title_hooks

        # v6.18 提前退出
        from .managers.exit_manager import ExitManager
        self.exit_mgr = ExitManager(self.db)

        # v6.19 智能下一步提示
        from .managers.next_step import NextStepAdvisor
        self.advisor = NextStepAdvisor(self.db)

        # v6.20 新手七日仙途
        from .managers.first_week import FirstWeekManager
        self.first_week = FirstWeekManager(self.db)
        self.player_handler.first_week_ref = self.first_week

        # v6.20 宗门协作 & 悬赏助力
        from .managers.sect_coop import SectCoopManager, BountyAssist
        self.sect_coop = SectCoopManager(self.db)
        self.bounty_assist = BountyAssist(self.db)
        self.player_handler.sect_coop_ref = self.sect_coop

        # v6.21 装备套装/离线信箱
        from .managers.enhance_systems import EquipSetManager, MailboxManager
        self.equip_sets = EquipSetManager(self.db)
        self.mailbox = MailboxManager(self.db)

        # v3.19.0 十一大新玩法
        from .managers.weather_manager import WeatherManager
        from .managers.collection_manager import CollectionManager
        from .managers.checkin_milestone import CheckinMilestoneManager
        from .managers.season_manager import SeasonManager
        from .managers.tribulation_bet import TribulationBetManager
        from .managers.samsara_manager import SamsaraManager
        from .managers.group_garden_manager import GroupGardenManager
        from .managers.couple_quest_manager import CoupleQuestManager
        from .managers.stronghold_manager import StrongholdManager
        from .managers.rift_enhance import RiftEnhanceManager
        from .managers.player_bounty_manager import PlayerBountyManager
        self.weather_mgr = WeatherManager(self.db)
        self.collection_mgr = CollectionManager(self.db, self.title_mgr)
        self.ckms_mgr = CheckinMilestoneManager(self.db)
        self.season_mgr = SeasonManager(self.db)
        self.tribbet_mgr = TribulationBetManager(self.db)
        self.samsara_mgr = SamsaraManager(self.db)
        self.garden_mgr = GroupGardenManager(self.db)
        self.couple_quest_mgr = CoupleQuestManager(self.db)
        self.stronghold_mgr = StrongholdManager(self.db)
        self.rift_enhance_mgr = RiftEnhanceManager(self.db)
        self.pblty_mgr = PlayerBountyManager(self.db)
        # v3.20.0 第二批新玩法
        from .managers.quiz_manager import QuizManager
        from .managers.lucky_wheel_manager import LuckyWheelManager
        from .managers.marriage_manager import MarriageManager
        from .managers.achievement_manager import AchievementManager
        from .managers.pet_battle_manager import PetBattleManager
        from .managers.treasure_hunt_manager import TreasureHuntManager
        self.quiz_mgr = QuizManager(self.db)
        self.wheel_mgr = LuckyWheelManager(self.db)
        self.marriage_mgr = MarriageManager(self.db)
        self.achievement_mgr = AchievementManager(self.db)
        self.petbattle_mgr = PetBattleManager(self.db)
        self.treasure_mgr = TreasureHuntManager(self.db)
        # v3.21.0 第三批新玩法
        from .managers.sect_tech_manager import SectTechManager
        from .managers.tournament_manager import TournamentManager
        from .managers.loot_auction_manager import LootAuctionManager
        self.sect_tech_mgr = SectTechManager(self.db)
        self.tournament_mgr = TournamentManager(self.db)
        self.loot_auction_mgr = LootAuctionManager(self.db)
        # v3.22.0 第四批新玩法
        from .managers.ascension_project_manager import AscensionProjectManager
        self.ascension_mgr = AscensionProjectManager(self.db)
        from .managers.group_chronicle_manager import GroupChronicleManager
        self.chronicle_mgr = GroupChronicleManager(self.db)
        from .managers.title_forge_manager import TitleForgeManager
        from .managers.fortune_stick_manager import FortuneStickManager
        self.title_forge_mgr = TitleForgeManager(self.db, self.title_mgr)
        self.fortune_mgr = FortuneStickManager(self.db)
        # 挂引用给 handler 层（沿用 social_mgr_ref 模式）
        self.player_handler.weather_ref = self.weather_mgr
        self.player_handler.collection_ref = self.collection_mgr
        self.player_handler.ckms_ref = self.ckms_mgr
        self.player_handler.couple_quest_ref = self.couple_quest_mgr
        self.player_handler.samsara_ref = self.samsara_mgr
        self.player_handler.season_ref = self.season_mgr

        # 后台任务句柄
        self.boss_task = None
        self.loan_check_task = None
        self.spirit_eye_task = None
        self.bounty_check_task = None
        self.demon_check_task = None
        self.restock_task = None

        access_control_config = self.config.get("ACCESS_CONTROL", {})
        self.whitelist_groups = [str(g) for g in access_control_config.get("WHITELIST_GROUPS", [])]
        self.boss_admins = [str(a) for a in access_control_config.get("BOSS_ADMINS", [])]

        logger.info(f"【修仙插件】XiuXianPlugin 初始化完成，数据库路径: {db_path}")

    def _check_access(self, event: AstrMessageEvent) -> bool:
        if not self.whitelist_groups: return True
        group_id = event.get_group_id()
        if not group_id: return True
        if str(group_id) in self.whitelist_groups: return True
        return False

    def _check_boss_admin(self, event: AstrMessageEvent) -> bool:
        if not self.boss_admins: return False
        sender_id = str(event.get_sender_id())
        return sender_id in self.boss_admins

    async def _send_access_denied_message(self, event: AstrMessageEvent):
        try:
            await event.send("抱歉，此群聊未在修仙插件的白名单中，无法使用相关功能。")
        except:
            pass

    async def initialize(self):
        await self.db.connect()
        migration_manager = MigrationManager(self.db.conn, self.config_manager)
        await migration_manager.migrate()
        await self.db.ext.ensure_system_config_table()
        # v3.24.0：建表完成后再补性能索引（connect 阶段表尚不存在）
        await self.db.ensure_performance_indexes()

        # 接线图片卡片开关：读取 IMAGE_CARDS 配置并下发给渲染器（此前配置从未被消费）
        try:
            from .utils.image_generator import set_card_flags
            card_cfg = self.config.get("IMAGE_CARDS", {}) or {}
            flags = {"__enabled__": bool(card_cfg.get("ENABLED", True))}
            for key, val in card_cfg.items():
                if key.startswith("CARD_"):
                    flags[key] = bool(val)
            set_card_flags(flags)
        except Exception as e:
            logger.warning(f"【修仙插件】图片卡片开关初始化失败（默认全开）: {e}")

        self.boss_task = asyncio.create_task(self._schedule_boss_spawn())
        self.loan_check_task = asyncio.create_task(self._schedule_loan_check())
        self.spirit_eye_task = asyncio.create_task(self._schedule_spirit_eye_spawn())
        self.bounty_check_task = asyncio.create_task(self._schedule_bounty_check())
        self.demon_check_task = asyncio.create_task(self._schedule_demon_check())
        self.tide_check_task = asyncio.create_task(self._schedule_tide_check())
        # v6.17 商店自动上货
        self.restock_task = asyncio.create_task(self._schedule_restock())

        logger.info("【修仙插件】已加载。")

    async def terminate(self):
        tasks = [t for t in (self.boss_task, self.loan_check_task, self.spirit_eye_task,
                             self.bounty_check_task, self.demon_check_task,
                             getattr(self, "tide_check_task", None), getattr(self, "restock_task", None)) if t]
        for task in tasks:
            task.cancel()
        # 等待后台任务真正退出后再关库，避免任务停在半途事务时连接被关闭导致写入丢失
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self.db.close()
        logger.info("【修仙插件】已卸载。")

    def _warn_no_whitelist(self, event_name: str):
        """全服事件广播因未配置白名单而被丢弃时提示管理员"""
        if not hasattr(self, "_whitelist_warned"):
            self._whitelist_warned = set()
        if event_name not in self._whitelist_warned:
            self._whitelist_warned.add(event_name)
            logger.warning(f"【修仙插件】{event_name} 广播被跳过：未配置白名单 WHITELIST_GROUPS，全服事件将不会通知任何群聊！")

    async def _title_bump(self, user_id: str, key: str, count: int = 1) -> str:
        """称号计数颁发（玩法处一行调用）"""
        try:
            player = await self.db.get_player_by_id(user_id)
            if not player:
                return ""
            return await self.title_hooks.bump(player, key, count)
        except Exception:
            return ""

    def _extract_at_target(self, event, arg: str = "") -> str:
        """统一的 @目标 解析：At组件 > CQ码文本 > 纯数字，排除发送者自己"""
        from astrbot.api.all import At
        sender_id = str(event.get_sender_id())
        if hasattr(event, "message_obj") and event.message_obj:
            for comp in (event.message_obj.message or []):
                if isinstance(comp, At):
                    for attr in ("qq", "target", "uin"):
                        v = getattr(comp, attr, None)
                        if v and str(v) != sender_id:
                            return str(v)
        if arg:
            cleaned = arg.strip()
            cq = re.search(r'\[CQ:at,qq=(\d{5,})\]', cleaned)
            if cq and cq.group(1) != sender_id:
                return cq.group(1)
            c2 = cleaned.lstrip("@").strip()
            if c2.isdigit() and len(c2) >= 5 and c2 != sender_id:
                return c2
        return ""

    def _safe_int(self, val: str, default: int = 0, lo: int = None, hi: int = None) -> int:
        """安全整数解析（支持全角数字，范围钳制）"""
        try:
            v = int(str(val).strip().translate(str.maketrans("０１２３４５６７８９", "0123456789")) or default)
        except (ValueError, TypeError):
            return default
        if lo is not None and v < lo:
            return lo
        if hi is not None and v > hi:
            return hi
        return v



    async def _schedule_boss_spawn(self):
        """v6.19 世界Boss调度（全自动）：每周随机 3 次 + 15 分钟预告"""
        while True:
            try:
                await self.db.ensure_connection()
                await asyncio.sleep(60)
                now = int(time.time())

                # 清理过期未击杀的旧世界Boss
                async with self.db.conn.execute(
                    "SELECT boss_id FROM world_boss WHERE status=1 AND expire_time < ?", (now,)
                ) as cur:
                    if await cur.fetchone():
                        await self.db.conn.execute(
                            "UPDATE world_boss SET status=3 WHERE status=1 AND expire_time < ?", (now,))
                        await self.db.conn.commit()
                        logger.info("【修仙插件】清理了超时未击杀的世界Boss")

                # 已有存活 Boss 则不调度
                async with self.db.conn.execute("SELECT boss_id FROM world_boss WHERE status=1") as cur:
                    if await cur.fetchone():
                        continue

                # 本周调度计划
                plan_str = await self.db.ext.get_system_config("boss_week_plan")
                week_key = time.strftime("%G-W%V")
                plan = None
                if plan_str:
                    try:
                        plan_data = json.loads(plan_str)
                        if plan_data.get("week") == week_key:
                            plan = plan_data
                    except Exception:
                        plan = None
                if not plan:
                    days = random.sample(range(7), 3)
                    events = []
                    for d in days:
                        base = time.strptime(week_key + "-1", "%G-W%V-%u")
                        base_ts = int(time.mktime((base.tm_year, base.tm_mon, base.tm_mday, 0, 0, 0, 0, 0, -1)))
                        base_ts += d * 86400
                        spawn_at = base_ts + random.randint(10, 22) * 3600 + random.choice([0, 1800])
                        events.append(spawn_at)
                    events = sorted(e for e in events if e > now)
                    plan = {"week": week_key, "events": events}
                    await self.db.ext.set_system_config("boss_week_plan", json.dumps(plan))
                    logger.info(f"【修仙插件】本周世界Boss计划：{len(events)} 场")

                if plan["events"]:
                    next_at = plan["events"][0]
                    announced_key = f"boss_preannounced_{next_at}"
                    announced = await self.db.ext.get_system_config(announced_key)
                    if not announced and 0 < next_at - now <= 900:
                        pre_msg = await self.world_boss_mgr.preannounce()
                        await self.db.ext.set_system_config(announced_key, "1")
                        await self._broadcast_world_boss_spawn(pre_msg)
                        logger.info("【修仙插件】世界Boss 15 分钟预告已广播")
                        continue

                    if now >= next_at:
                        plan["events"].pop(0)
                        await self.db.ext.set_system_config("boss_week_plan", json.dumps(plan))
                        success, msg = await self.world_boss_mgr.spawn_boss()
                        if success:
                            logger.info("【修仙插件】世界Boss已降临")
                            await self._broadcast_world_boss_spawn(msg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Boss生成任务异常: {e}")
                await asyncio.sleep(120)

    async def _schedule_loan_check(self):
        retry_count = 0
        max_retry_delay = 3600
        while True:
            try:
                await self.db.ensure_connection()
                await asyncio.sleep(3600)
                processed = await self.bank_mgr.check_and_process_overdue_loans()
                if processed:
                    logger.info(f"【修仙插件】处理了 {len(processed)} 笔逾期贷款")
                    for loan_info in processed:
                        if loan_info.get("death"):
                            await self._broadcast_loan_death(loan_info)
                retry_count = 0
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"贷款检查任务异常: {e}")
                retry_count += 1
                delay = min(60 * (2 ** retry_count), max_retry_delay)
                await asyncio.sleep(delay)

    async def _schedule_demon_check(self):
        """定时检查天魔入侵是否超时并自动结算"""
        while True:
            try:
                await self.db.ensure_connection()
                await asyncio.sleep(300)
                is_active = await self.db.ext.get_system_config("demon_invasion_active")
                if is_active == "1":
                    end_time_str = await self.db.ext.get_system_config("demon_invasion_end_time")
                    if end_time_str and end_time_str.isdigit() and int(time.time()) > int(end_time_str):
                        success, msg = await self.demon_mgr.end_invasion()
                        if success:
                            logger.info(f"【修仙插件】天魔入侵超时自动结算：{msg}")
                            await self._broadcast_world_boss_spawn(msg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"天魔入侵检查任务异常: {e}")
                await asyncio.sleep(60)

    async def _schedule_spirit_eye_spawn(self):
        retry_count = 0
        max_retry_delay = 3600
        while True:
            try:
                await self.db.ensure_connection()
                spawn_interval = 7200
                next_spawn_str = await self.db.ext.get_system_config("spirit_eye_next_spawn_time")
                current_time = int(time.time())
                if next_spawn_str:
                    next_spawn_time = int(next_spawn_str)
                    remaining = next_spawn_time - current_time
                    if remaining > 0:
                        await asyncio.sleep(remaining)
                else:
                    next_spawn_time = current_time + spawn_interval
                    await self.db.ext.set_system_config("spirit_eye_next_spawn_time", str(next_spawn_time))
                    await asyncio.sleep(spawn_interval)
                success, msg = await self.spirit_eye_mgr.spawn_spirit_eye()
                if success:
                    logger.info(f"【修仙插件】{msg}")
                    await self._broadcast_spirit_eye_spawn(msg)
                next_spawn_time = int(time.time()) + spawn_interval
                await self.db.ext.set_system_config("spirit_eye_next_spawn_time", str(next_spawn_time))
                retry_count = 0
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"灵眼生成任务异常: {e}")
                retry_count += 1
                delay = min(60 * (2 ** retry_count), max_retry_delay)
                await asyncio.sleep(delay)

    async def _schedule_bounty_check(self):
        while True:
            try:
                await self.db.ensure_connection()
                await asyncio.sleep(1800)
                expired = await self.bounty_mgr.check_and_expire_bounties()
                if expired > 0:
                    logger.info(f"【修仙插件】处理了 {expired} 个过期悬赏任务")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"悬赏检查任务异常: {e}")
                await asyncio.sleep(60)

    async def _schedule_tide_check(self):
        """定时检查魔潮：到期结算 + 周六/月初自动开启 + 月度称号"""
        while True:
            try:
                await self.db.ensure_connection()
                await asyncio.sleep(300)
                settled, msg = await self.calamity_mgr.auto_check()
                if settled and msg:
                    logger.info(f"【修仙插件】魔潮事件：{msg.splitlines()[0]}")
                    await self._broadcast_world_boss_spawn(msg)

                # v3.19.0 新玩法定时钩子：天骄榜赛季结算 / 灵脉周结 / 每日天象首播
                try:
                    season_summary = await self.season_mgr.ensure_season()
                    if season_summary:
                        await self._broadcast_world_boss_spawn(season_summary)
                except Exception as e:
                    logger.warning(f"天骄榜赛季检查异常: {e}")
                try:
                    stronghold_summary = await self.stronghold_mgr.weekly_settle()
                    if stronghold_summary:
                        await self._broadcast_world_boss_spawn(stronghold_summary)
                except Exception as e:
                    logger.warning(f"灵脉周结异常: {e}")
                try:
                    weather_data = await self.weather_mgr.ensure_today()
                    today = time.strftime("%Y%m%d")
                    bc_key = f"weather_bc_{today}"
                    if weather_data.get("date") == today and not await self.db.ext.get_system_config(bc_key):
                        await self.db.ext.set_system_config(bc_key, "1")
                        text = await self.weather_mgr.get_weather_text()
                        if text:
                            await self._broadcast_world_boss_spawn(text)
                except Exception as e:
                    logger.warning(f"每日天象播报异常: {e}")
                # v3.20.0 天材地宝定时刷新（30% 概率，刷新即全服广播）
                try:
                    spawned, treasure_text = await self.treasure_mgr.try_spawn()
                    if spawned and treasure_text:
                        await self._broadcast_world_boss_spawn(treasure_text)
                except Exception as e:
                    logger.warning(f"天材地宝刷新异常: {e}")
                # v3.21.0 斗法台周五自动开赛 + 拍卖行到期落槌
                try:
                    tnm_text = await self.tournament_mgr.run()
                    if tnm_text:
                        await self._broadcast_world_boss_spawn(tnm_text)
                except Exception as e:
                    logger.warning(f"斗法台开赛异常: {e}")
                try:
                    auction_text = await self.loot_auction_mgr.settle()
                    if auction_text:
                        await self._broadcast_world_boss_spawn(auction_text)
                except Exception as e:
                    logger.warning(f"拍卖行落槌异常: {e}")
                # v3.23.0 渡劫观礼密封开奖 + 日键清理
                try:
                    tribbet_text = await self.tribbet_mgr.tick()
                    if tribbet_text:
                        await self._broadcast_world_boss_spawn(tribbet_text)
                except Exception as e:
                    logger.warning(f"观礼开奖异常: {e}")
                try:
                    purge_key = f"purge_done_{time.strftime('%Y%m%d')}"
                    if time.strftime("%H%M") >= "0400" and not await self.db.ext.get_system_config(purge_key):
                        n = await self.db.ext.purge_dated_config_keys(8)
                        await self.db.ext.set_system_config(purge_key, "1")
                        if n:
                            logger.info(f"【修仙插件】清理过期日键 {n} 条")
                except Exception as e:
                    logger.warning(f"日键清理异常: {e}")
                # v3.22.0 修仙群史：每日首次循环广播昨日大事记
                try:
                    if await self.chronicle_mgr.mark_broadcast():
                        chronicle_text = await self.chronicle_mgr.build_daily()
                        if chronicle_text:
                            await self._broadcast_world_boss_spawn(chronicle_text)
                except Exception as e:
                    logger.warning(f"修仙群史播报异常: {e}")

                # v6.21 月度称号：每月1日自动颁发全服之最
                try:
                    month_key = time.strftime("%Y%m")
                    month_cfg_key = f"month_title_{month_key}"
                    done = await self.db.ext.get_system_config(month_cfg_key)
                    if not done and time.localtime().tm_mday == 1:
                        players = await self.db.get_all_players()
                        if players:
                            from .managers.title_manager import TitleManager
                            tm = TitleManager(self.db)
                            top_exp = max(players, key=lambda p: p.experience)
                            top_karma = max(players, key=lambda p: (p.karma or 0))
                            granted_any = False
                            for p, title in ((top_exp, "月度人杰"), (top_karma, "月度大善")):
                                ok, _ = tm.grant(p, title)
                                if ok:
                                    # grant 只改内存对象，必须落库，否则称号随临时对象一起丢失
                                    await self.db.update_player_fields(p.user_id, permanent_bonus=p.permanent_bonus)
                                    granted_any = True
                            if granted_any:
                                broadcast = (
                                    f"🏆【月度盛典】新的一月，天道册封上月之最：\n"
                                    f"  · 修为至尊：【{top_exp.user_name or top_exp.user_id[:8]}】\n"
                                    f"  · 第一大善：【{top_karma.user_name or top_karma.user_id[:8]}】\n"
                                    f"获得月度限定称号，全服敬仰！"
                                )
                                await self._broadcast_world_boss_spawn(broadcast)
                            # 颁发成功后才写当月标记，失败时下轮可重试
                            await self.db.ext.set_system_config(month_cfg_key, "1")
                except Exception as e:
                    logger.error(f"月度称号颁发异常: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"魔潮检查任务异常: {e}")
                await asyncio.sleep(60)

    async def _schedule_restock(self):
        """v6.18 商店自动上货：每 10 分钟检查三阁"""
        while True:
            try:
                await self.db.ensure_connection()
                await asyncio.sleep(600)
                n, detail = await self.shop_handler.auto_restock()
                if n:
                    logger.info(f"【修仙插件】自动上货完成（{n} 阁）：{detail}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自动上货任务异常: {e}")
                await asyncio.sleep(120)

    async def _broadcast_world_boss_spawn(self, msg: str):
        """广播全服事件"""
        from astrbot.api.event import MessageChain
        if not self.whitelist_groups:
            self._warn_no_whitelist("世界Boss/魔潮")
            return
        message_chain = MessageChain().message(msg)
        try:
            platforms = self.context.platform_manager.get_insts()
            for platform in platforms:
                platform_name = platform.meta().name if hasattr(platform, 'meta') and callable(platform.meta) else "unknown"
                for group_id in self.whitelist_groups:
                    umo = f"{platform_name}:GroupMessage:{group_id}"
                    try:
                        await self.context.send_message(umo, message_chain)
                    except Exception as e:
                        logger.warning(f"【修仙插件】广播失败 (群{group_id}): {e}")
        except Exception as e:
            logger.error(f"【修仙插件】广播异常: {e}")

    async def _broadcast_loan_death(self, loan_info: dict):
        from astrbot.api.event import MessageChain
        if not self.whitelist_groups:
            self._warn_no_whitelist("贷款追杀")
            return
        player_name = loan_info.get("player_name", "某修士")
        principal = loan_info.get("principal", 0)
        broadcast_msg = (
            f"💀 银行追杀公告 💀\n"
            f"━━━━━━━━━━━━━━━\n"
            f"修士【{player_name}】因贷款逾期未还\n"
            f"欠款：{principal:,} 灵石\n"
            f"已被灵石银行追杀致死！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⚠️ 借贷有风险，还款需及时！"
        )
        message_chain = MessageChain().message(broadcast_msg)
        try:
            platforms = self.context.platform_manager.get_insts()
            for platform in platforms:
                platform_name = platform.meta().name if hasattr(platform, 'meta') and callable(platform.meta) else "unknown"
                for group_id in self.whitelist_groups:
                    umo = f"{platform_name}:GroupMessage:{group_id}"
                    try:
                        await self.context.send_message(umo, message_chain)
                    except Exception as e:
                        logger.warning(f"【修仙插件】贷款追杀广播失败 (群{group_id}): {e}")
        except Exception as e:
            logger.error(f"【修仙插件】贷款追杀广播异常: {e}")

    async def _broadcast_spirit_eye_spawn(self, msg: str):
        from astrbot.api.event import MessageChain
        if not self.whitelist_groups:
            self._warn_no_whitelist("灵眼降临")
            return
        broadcast_msg = f"👁️ {msg}\n💡 使用 /灵眼信息 查看详情"
        message_chain = MessageChain().message(broadcast_msg)
        try:
            platforms = self.context.platform_manager.get_insts()
            for platform in platforms:
                platform_name = platform.meta().name if hasattr(platform, 'meta') and callable(platform.meta) else "unknown"
                for group_id in self.whitelist_groups:
                    umo = f"{platform_name}:GroupMessage:{group_id}"
                    try:
                        await self.context.send_message(umo, message_chain)
                    except Exception as e:
                        logger.warning(f"【修仙插件】灵眼广播发送失败 (群{group_id}): {e}")
        except Exception as e:
            logger.error(f"【修仙插件】灵眼广播异常: {e}")

    # ================= 指令注册区 =================

    @filter.command(CMD_HELP, "显示帮助信息（可带关键字过滤：/修仙帮助 签到）")
    @require_whitelist
    async def handle_help(self, event: AstrMessageEvent, keyword: str = ""):
        async for r in self.misc_handler.handle_help(event, keyword): yield r

    @filter.command(CMD_START_XIUXIAN, "开始你的修仙之路")
    @require_whitelist
    async def handle_start_xiuxian(self, event: AstrMessageEvent, cultivation_type: str = ""):
        async for r in self.player_handler.handle_start_xiuxian(event, cultivation_type): yield r

    @filter.command(CMD_PLAYER_INFO, "查看你的角色信息")
    @require_whitelist
    async def handle_player_info(self, event: AstrMessageEvent):
        async for r in self.player_handler.handle_player_info(event): yield r

    @filter.command(CMD_REBIRTH, "弃道重修（7天一次）")
    @require_whitelist
    async def handle_rebirth(self, event: AstrMessageEvent, confirm: str = ""):
        async for r in self.player_handler.handle_rebirth(event, confirm): yield r

    @filter.command(CMD_START_CULTIVATION, "开始闭关修炼")
    @require_whitelist
    async def handle_start_cultivation(self, event: AstrMessageEvent):
        async for r in self.player_handler.handle_start_cultivation(event): yield r

    @filter.command(CMD_END_CULTIVATION, "结束闭关修炼")
    @require_whitelist
    async def handle_end_cultivation(self, event: AstrMessageEvent):
        async for r in self.player_handler.handle_end_cultivation(event):
            yield r

    @filter.command(CMD_CHECK_IN, "每日签到领取灵石")
    @require_whitelist
    async def handle_check_in(self, event: AstrMessageEvent):
        async for r in self.player_handler.handle_check_in(event):
            yield r

    @filter.command(CMD_SHOW_EQUIPMENT, "查看已装备的物品")
    @require_whitelist
    async def handle_show_equipment(self, event: AstrMessageEvent):
        async for r in self.equipment_handler.handle_show_equipment(event): yield r

    @filter.command(CMD_EQUIP_ITEM, "装备物品")
    @require_whitelist
    async def handle_equip_item(self, event: AstrMessageEvent, item_name: str = ""):
        async for r in self.equipment_handler.handle_equip_item(event, item_name): yield r

    @filter.command(CMD_UNEQUIP_ITEM, "卸下装备")
    @require_whitelist
    async def handle_unequip_item(self, event: AstrMessageEvent, slot_or_name: str = ""):
        async for r in self.equipment_handler.handle_unequip_item(event, slot_or_name): yield r

    @filter.command(CMD_BREAKTHROUGH_INFO, "查看突破信息")
    @require_whitelist
    async def handle_breakthrough_info(self, event: AstrMessageEvent):
        async for r in self.breakthrough_handler.handle_breakthrough_info(event): yield r

    @filter.command(CMD_BREAKTHROUGH, "尝试突破境界")
    @require_whitelist
    async def handle_breakthrough(self, event: AstrMessageEvent, pill_name: str = ""):
        async for r in self.breakthrough_handler.handle_breakthrough(event, pill_name):
            yield r
        player = await self.db.get_player_by_id(event.get_sender_id())
        if player:
            tutorial_msg = await self.tutorial_mgr.check_and_advance(player, "breakthrough")
            if tutorial_msg:
                yield event.plain_result(tutorial_msg)
            # 称号：境界型 + 师德联动（弟子突破）
            try:
                tmsg = await self.title_hooks.bump_value(player, "breakthrough", player.level_index)
                if tmsg: yield event.plain_result(tmsg)
            except Exception:
                pass
            # 智能下一步提示
            try:
                advise = await self.advisor.advise(player, "breakthrough")
                if advise: yield event.plain_result(advise)
            except Exception:
                pass
            # 七日任务：突破
            try:
                await self.first_week.record_action(player, "breakthrough")
            except Exception:
                pass
            try:
                from .managers.social_manager import SocialManager
                _, mentor_msg = await SocialManager(self.db).on_disciple_breakthrough(player.user_id)
                if mentor_msg: yield event.plain_result(mentor_msg)
            except Exception:
                pass

    @filter.command(CMD_USE_PILL, "服用丹药")
    @require_whitelist
    async def handle_use_pill(self, event: AstrMessageEvent, pill_name: str = ""):
        async for r in self.pill_handler.handle_use_pill(event, pill_name): yield r

    @filter.command(CMD_SHOW_PILLS, "查看丹药背包")
    @require_whitelist
    async def handle_show_pills(self, event: AstrMessageEvent):
        async for r in self.pill_handler.handle_show_pills(event): yield r

    @filter.command(CMD_PILL_INFO, "查看丹药信息")
    @require_whitelist
    async def handle_pill_info(self, event: AstrMessageEvent, pill_name: str = ""):
        async for r in self.pill_handler.handle_pill_info(event, pill_name): yield r

    @filter.command(CMD_PILL_PAVILION, "查看丹阁丹药")
    @require_whitelist
    async def handle_pill_pavilion(self, event: AstrMessageEvent):
        async for r in self.shop_handler.handle_pill_pavilion(event): yield r

    @filter.command(CMD_WEAPON_PAVILION, "查看器阁武器")
    @require_whitelist
    async def handle_weapon_pavilion(self, event: AstrMessageEvent):
        async for r in self.shop_handler.handle_weapon_pavilion(event): yield r

    @filter.command(CMD_TREASURE_PAVILION, "查看百宝阁物品")
    @require_whitelist
    async def handle_treasure_pavilion(self, event: AstrMessageEvent):
        async for r in self.shop_handler.handle_treasure_pavilion(event): yield r

    @filter.command(CMD_ITEM_INFO, "查看物品详细效果")
    @require_whitelist
    async def handle_item_info(self, event: AstrMessageEvent, item_name: str = ""):
        async for r in self.shop_handler.handle_item_info(event, item_name): yield r

    @filter.command(CMD_BUY, "购买物品")
    @require_whitelist
    async def handle_buy(self, event: AstrMessageEvent, item_name: str = ""):
        async for r in self.shop_handler.handle_buy(event, item_name): yield r

    @filter.command("购买物品", "购买物品（无空格连写形式）")
    @require_whitelist
    async def handle_buy_compact(self, event: AstrMessageEvent, item_name: str = ""):
        # 兼容 "购买物品玄铁 5" / "购买物品 玄铁"：剥离"购买物品"前缀后走同一逻辑
        try:
            raw = (event.get_message_str() or "").strip().lstrip('/').lstrip('#').strip()
        except Exception:
            raw = ""
        if raw.startswith("购买物品"):
            raw = raw[len("购买物品"):].strip()
        async for r in self.shop_handler.handle_buy(event, raw): yield r

    @filter.command(CMD_STORAGE_RING, "查看储物戒信息")
    @require_whitelist
    async def handle_storage_ring(self, event: AstrMessageEvent):
        async for r in self.storage_ring_handler.handle_storage_ring(event): yield r

    @filter.command(CMD_RETRIEVE_ITEM, "从储物戒取出物品")
    @require_whitelist
    async def handle_retrieve_item(self, event: AstrMessageEvent, args: str = ""):
        async for r in self.storage_ring_handler.handle_retrieve_item(event, args): yield r

    @filter.command(CMD_UPGRADE_RING, "升级储物戒")
    @require_whitelist
    async def handle_upgrade_ring(self, event: AstrMessageEvent, ring_name: str = ""):
        async for r in self.storage_ring_handler.handle_upgrade_ring(event, ring_name): yield r

    @filter.command(CMD_DISCARD_ITEM, "丢弃储物戒中的物品")
    @require_whitelist
    async def handle_discard_item(self, event: AstrMessageEvent, args: str = ""):
        async for r in self.storage_ring_handler.handle_discard_item(event, args): yield r

    @filter.command(CMD_GIFT_ITEM, "赠予物品给其他玩家")
    @require_whitelist
    async def handle_gift_item(self, event: AstrMessageEvent, args: str = ""):
        async for r in self.storage_ring_handler.handle_gift_item(event, args): yield r

    @filter.command(CMD_ACCEPT_GIFT, "接收赠予的物品")
    @require_whitelist
    async def handle_accept_gift(self, event: AstrMessageEvent):
        async for r in self.storage_ring_handler.handle_accept_gift(event): yield r

    @filter.command(CMD_REJECT_GIFT, "拒绝赠予的物品")
    @require_whitelist
    async def handle_reject_gift(self, event: AstrMessageEvent):
        async for r in self.storage_ring_handler.handle_reject_gift(event): yield r

    @filter.command(CMD_SEARCH_ITEM, "搜索储物戒物品")
    @require_whitelist
    async def handle_search_item(self, event: AstrMessageEvent, keyword: str = ""):
        async for r in self.storage_ring_handler.handle_search_item(event, keyword): yield r

    @filter.command(CMD_RETRIEVE_ALL, "批量取出物品")
    @require_whitelist
    async def handle_retrieve_all(self, event: AstrMessageEvent, category: str = ""):
        async for r in self.storage_ring_handler.handle_retrieve_all(event, category): yield r

    # ===== 宗门 =====
    @filter.command(CMD_CREATE_SECT, "创建宗门")
    @require_whitelist
    async def handle_create_sect(self, event: AstrMessageEvent, name: str = ""):
        if not name:
            yield event.plain_result(f"请输入宗门名称，例如：/{CMD_CREATE_SECT} 逍遥门")
            return
        async for r in self.sect_handlers.handle_create_sect(event, name): yield r

    @filter.command(CMD_JOIN_SECT, "加入宗门")
    @require_whitelist
    async def handle_join_sect(self, event: AstrMessageEvent, name: str = ""):
        if not name:
            yield event.plain_result(f"请输入要加入的宗门名称，例如：/{CMD_JOIN_SECT} 逍遥门")
            return
        async for r in self.sect_handlers.handle_join_sect(event, name): yield r

    @filter.command(CMD_LEAVE_SECT, "退出当前宗门")
    @require_whitelist
    async def handle_leave_sect(self, event: AstrMessageEvent):
        async for r in self.sect_handlers.handle_leave_sect(event): yield r

    @filter.command(CMD_MY_SECT, "查看我的宗门信息")
    @require_whitelist
    async def handle_my_sect(self, event: AstrMessageEvent):
        async for r in self.sect_handlers.handle_my_sect(event): yield r

    @filter.command(CMD_SECT_TASK, "执行宗门任务")
    @require_whitelist
    async def handle_sect_task(self, event: AstrMessageEvent):
        async for r in self.sect_handlers.handle_sect_task(event): yield r

    @filter.command(CMD_FINISH_SECT_TASK, "完成宗门任务")
    @require_whitelist
    async def handle_finish_sect_task(self, event: AstrMessageEvent):
        async for r in self.sect_handlers.handle_finish_sect_task(event): yield r

    @filter.command(CMD_SECT_LIST, "查看宗门列表")
    @require_whitelist
    async def handle_sect_list(self, event: AstrMessageEvent):
        buf = []
        async for r in self.sect_handlers.handle_sect_list(event): buf.append(str(r))
        async for r in self.send_text_card(event, "\n".join(buf), "sect", "🏯 宗门列表", "仙盟林立 · 强者为尊"): yield r

    @filter.command(CMD_SECT_DONATE, "宗门捐献")
    @require_whitelist
    async def handle_sect_donate(self, event: AstrMessageEvent, amount: str = "0"):
        try: amount_int = int(amount)
        except ValueError:
            yield event.plain_result("请输入正确的数字！")
            return
        if amount_int <= 0:
             yield event.plain_result(f"请输入捐献数量，例如：/{CMD_SECT_DONATE} 1000")
             return
        async for r in self.sect_handlers.handle_donate(event, amount_int): yield r

    @filter.command(CMD_SECT_KICK, "踢出宗门成员")
    @require_whitelist
    async def handle_sect_kick(self, event: AstrMessageEvent, target: str = ""):
        async for r in self.sect_handlers.handle_kick_member(event, target): yield r

    @filter.command(CMD_SECT_TRANSFER, "宗主传位")
    @require_whitelist
    async def handle_sect_transfer(self, event: AstrMessageEvent, target: str = ""):
        async for r in self.sect_handlers.handle_transfer(event, target): yield r

    @filter.command(CMD_SECT_POSITION, "变更成员职位")
    @require_whitelist
    async def handle_sect_position(self, event: AstrMessageEvent, target: str = "", position: str = "-1"):
        try: pos_int = int(position)
        except ValueError:
            yield event.plain_result("职位必须是数字！")
            return
        if pos_int < 0:
            yield event.plain_result(f"请输入目标和职位ID(0-4)，例如：/{CMD_SECT_POSITION} @某人 1")
            return
        async for r in self.sect_handlers.handle_position_change(event, target, pos_int): yield r

    # ===== 排行榜（v3.25.0 全部升级仙侠卡片）=====
    @filter.command(CMD_RANK_LEVEL, "境界排行")
    @require_whitelist
    async def handle_rank_level(self, event: AstrMessageEvent):
        buf = []
        async for r in self.ranking_handlers.handle_rank_level(event): buf.append(str(r))
        async for r in self.send_text_card(event, "\n".join(buf), "rank", "🏔️ 境界排行", "修行界风云榜"): yield r

    @filter.command(CMD_RANK_POWER, "战力排行")
    @require_whitelist
    async def handle_rank_power(self, event: AstrMessageEvent):
        buf = []
        async for r in self.ranking_handlers.handle_rank_power(event): buf.append(str(r))
        async for r in self.send_text_card(event, "\n".join(buf), "rank", "⚔️ 战力排行", "修行界风云榜"): yield r

    @filter.command(CMD_RANK_WEALTH, "财富排行")
    @require_whitelist
    async def handle_rank_wealth(self, event: AstrMessageEvent):
        buf = []
        async for r in self.ranking_handlers.handle_rank_wealth(event): buf.append(str(r))
        async for r in self.send_text_card(event, "\n".join(buf), "rank", "💰 灵石排行", "修行界风云榜"): yield r

    @filter.command(CMD_RANK_SECT, "宗门排行")
    @require_whitelist
    async def handle_rank_sect(self, event: AstrMessageEvent):
        buf = []
        async for r in self.ranking_handlers.handle_rank_sect(event): buf.append(str(r))
        async for r in self.send_text_card(event, "\n".join(buf), "rank", "🏯 宗门排行", "修行界风云榜"): yield r

    @filter.command(CMD_RANK_DEPOSIT, "存款排行")
    @require_whitelist
    async def handle_rank_deposit(self, event: AstrMessageEvent):
        buf = []
        async for r in self.ranking_handlers.handle_rank_deposit(event): buf.append(str(r))
        async for r in self.send_text_card(event, "\n".join(buf), "rank", "🏦 存款排行", "修行界风云榜"): yield r

    @filter.command(CMD_RANK_CONTRIBUTION, "贡献排行")
    @require_whitelist
    async def handle_rank_contribution(self, event: AstrMessageEvent):
        buf = []
        async for r in self.ranking_handlers.handle_rank_sect_contribution(event): buf.append(str(r))
        async for r in self.send_text_card(event, "\n".join(buf), "rank", "✨ 贡献排行", "修行界风云榜"): yield r

    # ===== 战斗 =====
    @filter.command(CMD_DUEL, "决斗")
    @require_whitelist
    async def handle_duel(self, event: AstrMessageEvent, target: str = ""):
        user_id = event.get_sender_id()
        async for r in self.combat_handlers.handle_duel(event, target):
            yield r
        # 只有获胜才计入 win_pvp 任务进度（结果按 user_id 隔离，取后即清）
        last_result = self.combat_handlers.last_duel_result.pop(user_id, None)
        if last_result and last_result.get("winner") == user_id:
            await self.db.ext.add_task_progress(user_id, "win_pvp", 1)

    @filter.command(CMD_SPAR, "切磋")
    @require_whitelist
    async def handle_spar(self, event: AstrMessageEvent, target: str = ""):
        user_id = event.get_sender_id()
        async for r in self.combat_handlers.handle_spar(event, target):
            yield r
        # 真正开打（非冷却被拒）才计入 spar 任务进度
        if self.combat_handlers.last_spar_fought.pop(user_id, False):
            await self.db.ext.add_task_progress(user_id, "spar", 1)
            await self._title_bump(user_id, "spar_count")
        # 悬赏联动（spar/pvp tag）
            player = await self.db.get_player_by_id(user_id)
            if player:
                await self.bounty_mgr.add_bounty_progress(player, "spar", 1)
                await self.bounty_mgr.add_bounty_progress(player, "pvp", 1)

    # ===== 秘境 =====
    @filter.command(CMD_RIFT_LIST, "秘境列表")
    @require_whitelist
    async def handle_rift_list(self, event: AstrMessageEvent):
        buf = []
        async for r in self.rift_handlers.handle_rift_list(event): buf.append(str(r))
        async for r in self.send_text_card(event, "\n".join(buf), "rift", "🌀 秘境列表", "天开异境 · 机缘所在",
                                           footer="探索秘境 <ID> · /秘境词缀 看今日天时"): yield r

    @filter.command(CMD_RIFT_EXPLORE, "探索秘境")
    @require_whitelist
    async def handle_rift_explore(self, event: AstrMessageEvent, rift_id: str = "0"):
        try: rift_id_int = int(rift_id)
        except ValueError:
            yield event.plain_result("请输入正确的秘境ID！")
            return
        async for r in self.rift_handlers.handle_rift_explore(event, rift_id_int): yield r

    @filter.command(CMD_RIFT_COMPLETE, "完成秘境探索")
    @require_whitelist
    async def handle_rift_complete(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        success, msg, reward_data = await self.rift_mgr.finish_exploration(user_id)
        if success and reward_data:
            await self.db.ext.add_task_progress(user_id, "explore_rift", 1)
            await self._title_bump(user_id, "rift_count")
            player = await self.db.get_player_by_id(user_id)
            if player:
                has_progress, bounty_msg = await self.bounty_mgr.add_bounty_progress(player, "rift", 1)
                if has_progress: msg += bounty_msg

                # 奇遇系统：秘境归来概率触发三选一事件（25%）
                try:
                    encounter_msg = await self.encounter_mgr.maybe_trigger(player, base_chance=25)
                    if encounter_msg: msg += encounter_msg
                except Exception as e:
                    logger.warning(f"秘境奇遇触发异常: {e}")

                # 七日任务：秘境
                try:
                    await self.first_week.record_action(player, "rift")
                except Exception:
                    pass

                # 智能下一步提示
                try:
                    advise = await self.advisor.advise(player, "rift")
                    if advise: msg += advise
                except Exception:
                    pass
        yield event.plain_result(msg)

    @filter.command("提前退出", "历练/秘境中途退出，按已进行时长比例结算")
    @require_whitelist
    async def handle_early_exit(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        success, msg = await self.exit_mgr.early_exit(player)
        yield event.plain_result(msg)

    @filter.command(CMD_RIFT_EXIT, "退出秘境")
    @require_whitelist
    async def handle_rift_exit(self, event: AstrMessageEvent):
        async for r in self.rift_handlers.handle_rift_exit(event): yield r

    # ===== 历练 =====
    @filter.command(CMD_ADVENTURE_START, "开始历练")
    @require_whitelist
    async def handle_adventure_start(self, event: AstrMessageEvent, route: str = ""):
        async for r in self.adventure_handlers.handle_start_adventure(event, route): yield r

    @filter.command(CMD_ADVENTURE_COMPLETE, "完成历练")
    @require_whitelist
    async def handle_adventure_complete(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        success, msg, reward_data = await self.adventure_mgr.finish_adventure(user_id)
        if success and reward_data:
            await self.db.ext.add_task_progress(user_id, "adventure", 1)
            await self._title_bump(user_id, "adventure_count")
            # 七日任务：历练
            try:
                p_adv = await self.db.get_player_by_id(user_id)
                if p_adv:
                    await self.first_week.record_action(p_adv, "adventure")
            except Exception:
                pass
            # 宗门协作分
            try:
                if p_adv:
                    await self.sect_coop.bump_sect_progress(p_adv, 1)
            except Exception:
                pass
            player = await self.db.get_player_by_id(user_id)
            if player:
                bounty_tag = reward_data.get("bounty_tag", "adventure")
                bounty_value = reward_data.get("bounty_progress", 1)
                has_progress, bounty_msg = await self.bounty_mgr.add_bounty_progress(player, bounty_tag, bounty_value)
                if has_progress: msg += bounty_msg
                
                tutorial_msg = await self.tutorial_mgr.check_and_advance(player, "adventure")
                if tutorial_msg: msg += tutorial_msg

            # 奇遇系统：历练归来概率触发三选一事件
            try:
                encounter_msg = await self.encounter_mgr.maybe_trigger(player)
                if encounter_msg:
                    msg += encounter_msg
                    await self._title_bump(user_id, "luck_event")
            except Exception as e:
                logger.warning(f"奇遇触发异常: {e}")

            # 智能下一步提示
            try:
                advise = await self.advisor.advise(player, "adventure")
                if advise: msg += advise
            except Exception:
                pass
        yield event.plain_result(msg)

    @filter.command(CMD_ADVENTURE_STATUS, "历练状态")
    @require_whitelist
    async def handle_adventure_status(self, event: AstrMessageEvent):
        async for r in self.adventure_handlers.handle_adventure_status(event): yield r

    @filter.command(CMD_ADVENTURE_INFO, "历练信息")
    @require_whitelist
    async def handle_adventure_info(self, event: AstrMessageEvent):
        async for r in self.adventure_handlers.handle_adventure_info(event): yield r

    # ===== 炼丹 =====
    @filter.command(CMD_ALCHEMY_RECIPES, "丹药配方")
    @require_whitelist
    async def handle_alchemy_recipes(self, event: AstrMessageEvent):
        async for r in self.alchemy_handlers.handle_recipes(event): yield r

    @filter.command(CMD_ALCHEMY_CRAFT, "炼制丹药")
    @require_whitelist
    async def handle_alchemy_craft(self, event: AstrMessageEvent, pill_id: str = ""):
        user_id = event.get_sender_id()
        async for r in self.alchemy_handlers.handle_craft(event, pill_id):
            yield r
        # 任务要求"成功炼制"：失败/丹劫毁丹不计进度（结果按 user_id 隔离，取后即清）
        if self.alchemy_handlers.last_craft_success.pop(user_id, False):
            await self.db.ext.add_task_progress(user_id, "craft_pill", 1)
            await self._title_bump(user_id, "craft_count")
            if self.alchemy_handlers.last_perfect.pop(user_id, False):
                await self._title_bump(user_id, "craft_perfect")
            # 悬赏联动（craft tag）
            player = await self.db.get_player_by_id(user_id)
            if player:
                await self.bounty_mgr.add_bounty_progress(player, "craft", 1)

    # ===== 传承 =====
    @filter.command(CMD_IMPART_INFO, "传承信息")
    @require_whitelist
    async def handle_impart_info(self, event: AstrMessageEvent):
        async for r in self.impart_handlers.handle_impart_info(event): yield r

    # ===== 道号 =====
    @filter.command(CMD_CHANGE_NICKNAME, "改道号")
    @require_whitelist
    async def handle_change_nickname(self, event: AstrMessageEvent, new_name: str = ""):
        async for r in self.nickname_handler.handle_change_nickname(event, new_name): yield r

    # ===== 银行 =====
    @filter.command(CMD_BANK_INFO, "查看银行信息")
    @require_whitelist
    async def handle_bank_info(self, event: AstrMessageEvent):
        buf = []
        async for r in self.bank_handlers.handle_bank_info(event): buf.append(str(r))
        async for r in self.send_text_card(event, "\n".join(buf), "bank", "🏦 灵石银行", "存取 · 复利 · 贷款",
                                           footer="贷款逾期将被追杀 · 谨慎借贷"): yield r

    @filter.command(CMD_BANK_DEPOSIT, "存入灵石")
    @require_whitelist
    async def handle_bank_deposit(self, event: AstrMessageEvent, amount: str = "0"):
        try: amount_int = int(amount)
        except ValueError:
            yield event.plain_result("❌ 请输入正确的数字！")
            return
        async for r in self.bank_handlers.handle_deposit(event, amount_int): yield r

    @filter.command(CMD_BANK_WITHDRAW, "取出灵石")
    @require_whitelist
    async def handle_bank_withdraw(self, event: AstrMessageEvent, amount: str = "0"):
        try: amount_int = int(amount)
        except ValueError:
            yield event.plain_result("❌ 请输入正确的数字！")
            return
        async for r in self.bank_handlers.handle_withdraw(event, amount_int): yield r

    @filter.command(CMD_BANK_INTEREST, "领取利息")
    @require_whitelist
    async def handle_bank_interest(self, event: AstrMessageEvent):
        async for r in self.bank_handlers.handle_claim_interest(event): yield r

    @filter.command(CMD_BANK_LOAN, "申请贷款")
    @require_whitelist
    async def handle_bank_loan(self, event: AstrMessageEvent, amount: str = "0"):
        try: amount_int = int(amount)
        except ValueError:
            yield event.plain_result("❌ 请输入正确的数字！")
            return
        async for r in self.bank_handlers.handle_loan(event, amount_int): yield r

    @filter.command(CMD_BANK_REPAY, "偿还贷款")
    @require_whitelist
    async def handle_bank_repay(self, event: AstrMessageEvent):
        async for r in self.bank_handlers.handle_repay(event): yield r

    @filter.command(CMD_BANK_TRANSACTIONS, "银行流水")
    @require_whitelist
    async def handle_bank_transactions(self, event: AstrMessageEvent):
        async for r in self.bank_handlers.handle_transactions(event): yield r

    @filter.command(CMD_BANK_BREAKTHROUGH_LOAN, "申请突破贷款")
    @require_whitelist
    async def handle_bank_breakthrough_loan(self, event: AstrMessageEvent, amount: str = "0"):
        try: amount_int = int(amount)
        except ValueError:
            yield event.plain_result("❌ 请输入正确的数字！")
            return
        async for r in self.bank_handlers.handle_breakthrough_loan(event, amount_int): yield r

    # ===== 悬赏 =====
    @filter.command(CMD_BOUNTY_LIST, "查看悬赏任务")
    @require_whitelist
    async def handle_bounty_list(self, event: AstrMessageEvent):
        buf = []
        async for r in self.bounty_handlers.handle_bounty_list(event): buf.append(str(r))
        async for r in self.send_text_card(event, "\n".join(buf), "bounty", "📜 悬赏令", "今日悬赏 · 童叟无欺",
                                           footer="接取悬赏 <编号> · 完成得灵石功德"): yield r

    @filter.command(CMD_BOUNTY_ACCEPT, "接取悬赏任务")
    @require_whitelist
    async def handle_bounty_accept(self, event: AstrMessageEvent, bounty_id: str = "0"):
        bounty_id_int = self._safe_int(bounty_id, 0, lo=0)
        if bounty_id_int <= 0:
            yield event.plain_result("❌ 请输入正确的悬赏编号！例如：/接取悬赏 1（编号见 /悬赏令）")
            return
        async for r in self.bounty_handlers.handle_accept_bounty(event, bounty_id_int): yield r

    @filter.command(CMD_BOUNTY_STATUS, "查看悬赏状态")
    @require_whitelist
    async def handle_bounty_status(self, event: AstrMessageEvent):
        async for r in self.bounty_handlers.handle_bounty_status(event): yield r

    @filter.command(CMD_BOUNTY_COMPLETE, "完成悬赏任务")
    @require_whitelist
    async def handle_bounty_complete(self, event: AstrMessageEvent):
        async for r in self.bounty_handlers.handle_complete_bounty(event): yield r

    @filter.command(CMD_BOUNTY_ABANDON, "放弃悬赏任务")
    @require_whitelist
    async def handle_bounty_abandon(self, event: AstrMessageEvent):
        async for r in self.bounty_handlers.handle_abandon_bounty(event): yield r

    # ===== 传承PK =====
    @filter.command(CMD_IMPART_CHALLENGE, "发起传承挑战")
    @require_whitelist
    async def handle_impart_challenge(self, event: AstrMessageEvent, target: str = ""):
        async for r in self.impart_pk_handlers.handle_impart_challenge(event, target): yield r

    @filter.command(CMD_IMPART_RANKING, "查看传承排行")
    @require_whitelist
    async def handle_impart_ranking(self, event: AstrMessageEvent):
        async for r in self.impart_pk_handlers.handle_impart_ranking(event): yield r

    # ===== 洞天福地 =====
    @filter.command(CMD_BLESSED_LAND_INFO, "查看洞天信息")
    @require_whitelist
    async def handle_blessed_land_info(self, event: AstrMessageEvent):
        async for r in self.blessed_land_handlers.handle_blessed_land_info(event): yield r

    @filter.command(CMD_BLESSED_LAND_BUY, "购买洞天")
    @require_whitelist
    async def handle_blessed_land_buy(self, event: AstrMessageEvent, land_type: str = "0"):
        try: land_int = int(land_type)
        except ValueError:
            yield event.plain_result("❌ 请输入正确的数字！")
            return
        async for r in self.blessed_land_handlers.handle_purchase(event, land_int): yield r

    @filter.command(CMD_BLESSED_LAND_UPGRADE, "升级洞天")
    @require_whitelist
    async def handle_blessed_land_upgrade(self, event: AstrMessageEvent):
        async for r in self.blessed_land_handlers.handle_upgrade(event): yield r
        # 称号：洞天等级
        try:
            p1 = await self.db.get_player_by_id(event.get_sender_id())
            if p1:
                land = None
                async with self.db.conn.execute("SELECT level FROM blessed_lands WHERE user_id = ?", (p1.user_id,)) as cur:
                    row = await cur.fetchone()
                if row and row[0] >= 5:
                    tmsg = await self.title_hooks.bump_value(p1, "land_level", row[0])
                    if tmsg: yield event.plain_result(tmsg)
        except Exception:
            pass

    @filter.command(CMD_BLESSED_LAND_COLLECT, "收取洞天产出")
    @require_whitelist
    async def handle_blessed_land_collect(self, event: AstrMessageEvent):
        async for r in self.blessed_land_handlers.handle_collect(event): yield r

    @filter.command(CMD_BLESSED_LAND_ADVANCE, "进阶洞天")
    @require_whitelist
    async def handle_blessed_land_advance(self, event: AstrMessageEvent, target_type: str = "0"):
        try: target_int = int(target_type)
        except ValueError:
            yield event.plain_result("❌ 请输入正确的数字！")
            return
        async for r in self.blessed_land_handlers.handle_advance(event, target_int): yield r

    # ===== 灵田 =====
    @filter.command(CMD_SPIRIT_FARM_INFO, "查看灵田")
    @require_whitelist
    async def handle_spirit_farm_info(self, event: AstrMessageEvent):
        async for r in self.spirit_farm_handlers.handle_farm_info(event): yield r

    @filter.command(CMD_SPIRIT_FARM_CREATE, "开垦灵田")
    @require_whitelist
    async def handle_spirit_farm_create(self, event: AstrMessageEvent):
        async for r in self.spirit_farm_handlers.handle_create_farm(event): yield r

    @filter.command(CMD_SPIRIT_FARM_PLANT, "种植灵草")
    @require_whitelist
    async def handle_spirit_farm_plant(self, event: AstrMessageEvent, herb_name: str = ""):
        async for r in self.spirit_farm_handlers.handle_plant(event, herb_name): yield r

    @filter.command(CMD_SPIRIT_FARM_HARVEST, "收获灵草")
    @require_whitelist
    async def handle_spirit_farm_harvest(self, event: AstrMessageEvent):
        async for r in self.spirit_farm_handlers.handle_harvest(event):
            yield r
        # 真正收获成功（有成熟作物）才计任务进度
        if self.spirit_farm_handlers.last_harvest_ok.pop(event.get_sender_id(), False):
            await self.db.ext.add_task_progress(event.get_sender_id(), "harvest", 1)
            await self._title_bump(event.get_sender_id(), "harvest_count")

    @filter.command(CMD_SPIRIT_FARM_UPGRADE, "升级灵田")
    @require_whitelist
    async def handle_spirit_farm_upgrade(self, event: AstrMessageEvent):
        async for r in self.spirit_farm_handlers.handle_upgrade_farm(event): yield r

    # ===== 双修 =====
    @filter.command(CMD_DUAL_CULT_REQUEST, "发起双修")
    @require_whitelist
    async def handle_dual_cult_request(self, event: AstrMessageEvent, target: str = ""):
        async for r in self.dual_cult_handlers.handle_dual_request(event, target): yield r

    @filter.command(CMD_DUAL_CULT_ACCEPT, "接受双修")
    @require_whitelist
    async def handle_dual_cult_accept(self, event: AstrMessageEvent):
        async for r in self.dual_cult_handlers.handle_accept(event): yield r

    @filter.command(CMD_DUAL_CULT_REJECT, "拒绝双修")
    @require_whitelist
    async def handle_dual_cult_reject(self, event: AstrMessageEvent):
        async for r in self.dual_cult_handlers.handle_reject(event): yield r

    # ===== 灵眼 =====
    @filter.command(CMD_SPIRIT_EYE_INFO, "查看灵眼")
    @require_whitelist
    async def handle_spirit_eye_info(self, event: AstrMessageEvent):
        async for r in self.spirit_eye_handlers.handle_spirit_eye_info(event): yield r

    @filter.command(CMD_SPIRIT_EYE_CLAIM, "抢占灵眼")
    @require_whitelist
    async def handle_spirit_eye_claim(self, event: AstrMessageEvent, eye_id: str = "0"):
        eye_id_int = self._safe_int(eye_id, 0, lo=0)
        if eye_id_int <= 0:
            yield event.plain_result("❌ 请输入正确的灵眼编号！例如：/抢占灵眼 1（编号见 /灵眼信息）")
            return
        async for r in self.spirit_eye_handlers.handle_claim(event, eye_id_int): yield r

    @filter.command(CMD_SPIRIT_EYE_COLLECT, "收取灵眼产出")
    @require_whitelist
    async def handle_spirit_eye_collect(self, event: AstrMessageEvent):
        async for r in self.spirit_eye_handlers.handle_collect(event): yield r

    @filter.command(CMD_SPIRIT_EYE_RELEASE, "释放灵眼")
    @require_whitelist
    async def handle_spirit_eye_release(self, event: AstrMessageEvent):
        async for r in self.spirit_eye_handlers.handle_release(event): yield r

    # ===== v6.1 日常任务 =====
    @filter.command("任务榜", "查看日常任务")
    @require_whitelist
    async def handle_task_board(self, event: AstrMessageEvent):
        buf = []
        async for r in self.daily_task_handlers.handle_task_board(event): buf.append(str(r))
        async for r in self.send_text_card(event, "\n".join(buf), "task", "📋 任务榜", "今日随机任务",
                                           footer="接取任务 <黄/玄/地/天> · 完成领奖"): yield r

    @filter.command("接取任务", "接取日常任务")
    @require_whitelist
    async def handle_accept_task(self, event: AstrMessageEvent, level: str = ""):
        async for r in self.daily_task_handlers.handle_accept_task(event, level): yield r

    @filter.command("领取任务奖励", "领取日常任务奖励")
    @require_whitelist
    async def handle_claim_reward(self, event: AstrMessageEvent):
        async for r in self.daily_task_handlers.handle_claim_reward(event): yield r

    # ===== v6.1 动态世界Boss =====
    @filter.command("挑战世界Boss", "参与全服世界Boss讨伐")
    @require_whitelist
    async def handle_challenge_world_boss(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        async for r in self.world_boss_handlers.handle_challenge(event): yield r
        # 挑战成功（真正打出伤害）计入 boss_damage 任务进度（结果按 user_id 隔离）
        if self.world_boss_mgr.last_challenge_ok.pop(user_id, False):
            await self.db.ext.add_task_progress(user_id, "boss_damage", 1)
            # 悬赏联动（boss_damage/tide tag）
            player = await self.db.get_player_by_id(user_id)
            if player:
                await self.bounty_mgr.add_bounty_progress(player, "boss_damage", 1)
                await self.bounty_mgr.add_bounty_progress(player, "tide", 1)
        # 击杀结算全服广播（排名奖励公示）
        settle_msg = self.world_boss_mgr.last_settle_msg.pop(user_id, None)
        if settle_msg:
            await self._broadcast_world_boss_spawn(settle_msg)
        # 血量里程碑播报
        milestone = self.world_boss_mgr.last_milestone_msg.pop(user_id, None)
        if milestone:
            await self._broadcast_world_boss_spawn(milestone)

    @filter.command("世界Boss状态", "查看动态世界Boss信息")
    @require_whitelist
    async def handle_query_world_boss(self, event: AstrMessageEvent):
        async for r in self.world_boss_handlers.handle_query(event): yield r
            
    # ===== v6.1 洞府掠夺 =====
    @filter.command("开启护府", "使用护府令保护洞天")
    @require_whitelist
    async def handle_use_shield(self, event: AstrMessageEvent):
        async for r in self.robbery_handlers.handle_use_shield(event): yield r

    @filter.command("潜入洞府", "潜入他人洞府偷窃")
    @require_whitelist
    async def handle_rob(self, event: AstrMessageEvent, target: str = ""):
        async for r in self.robbery_handlers.handle_rob(event, target): yield r

    # ===== v6.1 飞升转生 =====
    @filter.command("飞升", "达到最高境界后飞升转生（可附加装备名封印为传家宝）")
    @require_whitelist
    async def handle_reincarnate(self, event: AstrMessageEvent, heirloom_name: str = ""):
        before = None
        p0 = await self.db.get_player_by_id(event.get_sender_id())
        if p0: before = p0.reincarnation_count
        async for r in self.reinc_handlers.handle_reincarnate(event, heirloom_name):
            yield r
        # 称号：转生次数（飞升后 count+1）
        try:
            p1 = await self.db.get_player_by_id(event.get_sender_id())
            if p1 and before is not None and p1.reincarnation_count > before:
                tmsg = await self.title_hooks.bump_value(p1, "reincarnation", p1.reincarnation_count)
                if tmsg: yield event.plain_result(tmsg)
        except Exception:
            pass

    @filter.command("解封传家宝", "达到筑基期后解封转生前的装备")
    @require_whitelist
    async def handle_unseal_heirloom(self, event: AstrMessageEvent):
        async for r in self.reinc_handlers.handle_unseal(event):
            yield r

    @filter.command("仙缘商店", "查看转生永久加成")
    @require_whitelist
    async def handle_fate_shop(self, event: AstrMessageEvent):
        async for r in self.reinc_handlers.handle_fate_shop(event): yield r

    # ===== 新增：仙缘兑换 =====
    @filter.command("仙缘兑换", "购买仙缘商店的永久加成")
    @require_whitelist
    async def handle_fate_exchange(self, event: AstrMessageEvent, item_id: str = "0"):
        async for r in self.reinc_handlers.handle_fate_exchange(event, item_id):
            yield r

    # ===== v6.1 真·一键日常 =====
    @filter.command("一键日常", "自动完成签到/收菜等挂机操作")
    @require_whitelist
    async def handle_daily_helper(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        player = await self.db.get_player_by_id(user_id)
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途，请先发送「我要修仙」。")
            return

        # 检查是否处于忙碌状态
        user_cd = await self.db.ext.get_user_cd(user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            status_name = UserStatus.get_name(user_cd.type)
            yield event.plain_result(f"❌ 道友当前正「{status_name}」，无法分心打理日常。")
            return

        details = []
        has_any_action = False

        # 1. 签到
        today = datetime.now().strftime("%Y-%m-%d")
        if player.last_check_in_date != today:
            check_in_gold_min = self.config.get("VALUES", {}).get("CHECK_IN_GOLD_MIN", 50)
            check_in_gold_max = self.config.get("VALUES", {}).get("CHECK_IN_GOLD_MAX", 500)
            check_in_gold = random.randint(check_in_gold_min, check_in_gold_max)
            player.gold += check_in_gold
            player.last_check_in_date = today
            details.append(f"✅ 签到成功，获得 {check_in_gold} 灵石")
            
            # ===== 节日判定 =====
            festival = self.player_handler._get_today_festival()
            if festival:
                player.gold += festival["gold"]
                player.experience += festival["exp"]
                item_name = festival.get("item")
                item_count = festival.get("item_count", 1)
                if item_name:
                    await self.storage_ring_mgr.store_item(player, item_name, item_count, silent=True)
                
                details.append(f"🎊 今天是【{festival['name']}】，额外获得 {festival['gold']} 灵石、{festival['exp']} 修为及恩赐物品！")
            # ======================
            
            await self.db.ext.add_task_progress(user_id, "check_in", 1)
            has_any_action = True
            # 签到改动立即落库，防止后续子系统未触发 update_player 时被结尾覆盖丢失
            await self.db.update_player(player)

        # 2. 银行利息
        try:
            bank_data = await self.db.ext.get_bank_account(user_id)
            if bank_data and bank_data["balance"] > 0:
                success, msg = await self.bank_mgr.claim_interest(player)
                if success:
                    details.append(f"🏦 银行利息已领取")
                    has_any_action = True
        except Exception as e: logger.warning(f"一键日常-银行利息异常: {e}")

        # 3. 洞天福地
        try:
            success, msg = await self.blessed_land_mgr.collect_income(player)
            if success:
                details.append(f"🏔️ 洞天产出已收取")
                has_any_action = True
        except Exception as e: logger.warning(f"一键日常-洞天异常: {e}")

        # 4. 灵田
        try:
            success, msg = await self.spirit_farm_mgr.harvest(player)
            if success:
                details.append(f"🌾 灵田已收获")
                has_any_action = True
        except Exception as e: logger.warning(f"一键日常-灵田异常: {e}")

        # 5. 灵眼
        try:
            success, msg = await self.spirit_eye_mgr.collect_spirit_eye(player)
            if success:
                details.append(f"👁️ 灵眼产出已收取")
                has_any_action = True
        except Exception as e: logger.warning(f"一键日常-灵眼异常: {e}")

        if not has_any_action:
            yield event.plain_result("✨ 你今日的日常打理得井井有条，目前没有可以一键收取的东西。")
            return

        # 仅用于展示最新数值；各子系统已各自持久化，这里不再回写避免用陈旧对象覆盖
        player = await self.db.get_player_by_id(user_id)

        reply_msg = "🪄 【一键日常】托管完成！\n"
        reply_msg += "━━━━━━━━━━━━━━━\n"
        reply_msg += "\n".join(details)
        reply_msg += f"\n━━━━━━━━━━━━━━━\n"
        reply_msg += f"💰 当前持有灵石：{player.gold:,}\n"
        reply_msg += f"📈 当前修为：{player.experience:,}"
        
        yield event.plain_result(reply_msg)

    # ===== v6.1 解卡 =====
    @filter.command("解卡", "强制重置卡死状态")
    @require_whitelist
    async def handle_force_unlock(self, event: AstrMessageEvent):
        async for r in self.misc_handler.handle_force_unlock(event): yield r

    # ===== v6.2 赌石与黑市 =====
    @filter.command("切原石", "花费灵石赌石")
    @require_whitelist
    async def handle_cut_stone(self, event: AstrMessageEvent, count: str = "1"):
        async for r in self.gamble_handlers.handle_cut_stone(event, count): yield r

    @filter.command("黑市", "查看今日黑市")
    @require_whitelist
    async def handle_market(self, event: AstrMessageEvent):
        async for r in self.gamble_handlers.handle_market(event): yield r

    @filter.command("黑市购买", "从黑市购买商品")
    @require_whitelist
    async def handle_buy_market(self, event: AstrMessageEvent, index: str = "0"):
        async for r in self.gamble_handlers.handle_buy_market(event, index): yield r

    # ===== v6.3 炼器与洗练 =====
    @filter.command("强化", "消耗强化石提升炼器等级")
    @require_whitelist
    async def handle_enhance(self, event: AstrMessageEvent):
        async for r in self.forge_handlers.handle_enhance(event): yield r

    @filter.command("洗练", "消耗洗练石重置装备词条")
    @require_whitelist
    async def handle_wash(self, event: AstrMessageEvent):
        async for r in self.forge_handlers.handle_wash(event): yield r

    # ===== v6.4 天魔入侵 =====
    @filter.command("开启天魔入侵", "管理员开启活动")
    @require_whitelist
    async def handle_demon_start(self, event: AstrMessageEvent, hours: str = "24"):
        if not self._check_boss_admin(event):
            yield event.plain_result("❌ 你没有权限！")
            return
        async for r in self.demon_handlers.handle_start(event, hours): yield r

    @filter.command("查验天魔", "查验某人是否为天魔")
    @require_whitelist
    async def handle_demon_catch(self, event: AstrMessageEvent, target: str = ""):
        got_it = False
        async for r in self.demon_handlers.handle_catch(event, target):
            if isinstance(r, str) and ("降妖除魔" in r or "最后一名天魔" in r):
                got_it = True
            yield r
        # 称号：揪出天魔
        try:
            if got_it:
                tmsg = await self._title_bump(event.get_sender_id(), "demon_catch")
                if tmsg: yield event.plain_result(tmsg)
        except Exception:
            pass

    @filter.command("天魔状态", "查看当前活动状态")
    @require_whitelist
    async def handle_demon_status(self, event: AstrMessageEvent):
        async for r in self.demon_handlers.handle_status(event): yield r

    # ===== v6.5 灵兽系统 =====
    @filter.command("我的灵兽", "查看当前携带的灵兽")
    @require_whitelist
    async def handle_my_pet(self, event: AstrMessageEvent):
        async for r in self.pet_handlers.handle_my_pet(event): yield r

    @filter.command("孵化灵兽", "契约一只新灵兽")
    @require_whitelist
    async def handle_adopt_pet(self, event: AstrMessageEvent, pet_name: str = ""):
        async for r in self.pet_handlers.handle_adopt(event, pet_name): yield r

    @filter.command("喂养灵兽", "消耗资源提升灵兽等级")
    @require_whitelist
    async def handle_feed_pet(self, event: AstrMessageEvent):
        before = None
        p0 = await self.db.get_player_by_id(event.get_sender_id())
        if p0:
            pet0 = await self.pet_mgr.get_pet(p0.user_id)
            before = pet0["level"] if pet0 else 0
        async for r in self.pet_handlers.handle_feed(event): yield r
        # 称号：灵兽等级
        try:
            p1 = await self.db.get_player_by_id(event.get_sender_id())
            pet1 = await self.pet_mgr.get_pet(p1.user_id) if p1 else None
            if pet1 and before is not None and pet1["level"] > before:
                tmsg = await self.title_hooks.bump_value(p1, "pet_level", pet1["level"])
                if tmsg: yield event.plain_result(tmsg)
        except Exception:
            pass

    # ===== v6.5.1 新增：放生与吞噬 =====
    @filter.command("放生灵兽", "清空当前灵兽，以便契约新的")
    @require_whitelist
    async def handle_release_pet(self, event: AstrMessageEvent):
        async for r in self.pet_handlers.handle_release(event): yield r

    @filter.command("吞噬灵兽", "吞噬当前灵兽，返还部分资源")
    @require_whitelist
    async def handle_devour_pet(self, event: AstrMessageEvent):
        async for r in self.pet_handlers.handle_devour(event): yield r

    # ===== v6.6 宗门大比 =====
    @filter.command("开启宗门大比", "管理员开启活动")
    @require_whitelist
    async def handle_start_sect_battle(self, event: AstrMessageEvent):
        if not self._check_boss_admin(event):
            yield event.plain_result("❌ 你没有权限！")
            return
        success, msg = await self.sect_mgr.start_sect_battle()
        yield event.plain_result(msg)

    @filter.command("结束宗门大比", "管理员结束活动")
    @require_whitelist
    async def handle_end_sect_battle(self, event: AstrMessageEvent):
        if not self._check_boss_admin(event):
            yield event.plain_result("❌ 你没有权限！")
            return
        success, msg = await self.sect_mgr.end_sect_battle()
        yield event.plain_result(msg)

    @filter.command("大比切磋", "受天道压制的宗门PVP")
    @require_whitelist
    async def handle_sect_battle(self, event: AstrMessageEvent, target: str = ""):
        async for r in self.sect_handlers.handle_sect_battle(event, target): yield r

    # ===== v6.7 交易坊市 =====
    @filter.command("坊市", "查看玩家交易坊市")
    @require_whitelist
    async def handle_market_list(self, event: AstrMessageEvent):
        async for r in self.auction_handlers.handle_list(event): yield r

    @filter.command("坊市上架", "上架物品到坊市")
    @require_whitelist
    async def handle_market_sell(self, event: AstrMessageEvent, args: str = ""):
        async for r in self.auction_handlers.handle_list_item(event, args): yield r

    @filter.command("坊市购买", "购买坊市物品")
    @require_whitelist
    async def handle_market_buy(self, event: AstrMessageEvent, auction_id: str = "0"):
        async for r in self.auction_handlers.handle_buy(event, auction_id): yield r

    @filter.command("坊市下架", "下架坊市物品")
    @require_whitelist
    async def handle_market_cancel(self, event: AstrMessageEvent, auction_id: str = "0"):
        async for r in self.auction_handlers.handle_cancel(event, auction_id): yield r

    # ===== v6.8 灵田扩展：施肥与杂交 =====
    @filter.command("施肥", "消耗灵石恢复灵田肥力")
    @require_whitelist
    async def handle_fertilize(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途，请先发送「我要修仙」。")
            return
        success, msg = await self.spirit_farm_mgr.fertilize(player)
        yield event.plain_result(msg)

    @filter.command("杂交", "将两种灵草杂交出新品种")
    @require_whitelist
    async def handle_hybridize(self, event: AstrMessageEvent, herb_a: str = "", herb_b: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途，请先发送「我要修仙」。")
            return
        success, msg = await self.spirit_farm_mgr.hybridize(player, herb_a, herb_b)
        yield event.plain_result(msg)

    # ===== v6.8 储物戒空间附魔 =====
    @filter.command("储物戒附魔", "消耗空间石永久扩充储物戒容量")
    @require_whitelist
    async def handle_ring_enchant(self, event: AstrMessageEvent, stones: str = "1"):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途，请先发送「我要修仙」。")
            return
        try:
            stone_count = int(stones)
        except ValueError:
            yield event.plain_result("❌ 请输入有效的空间石数量，例如：/储物戒附魔 2")
            return
        success, msg = await self.storage_ring_mgr.enchant_ring(player, stone_count)
        yield event.plain_result(msg)

    # ===== v6.8 押镖与劫道 =====
    @filter.command("押镖", "接一趟灵石镖（期间可被劫镖）")
    @require_whitelist
    async def handle_start_escort(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途，请先发送「我要修仙」。")
            return
        user_cd = await self.db.ext.get_user_cd(player.user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            from .models_extended import UserStatus as _US
            yield event.plain_result(f"❌ 你当前正{_US.get_name(user_cd.type)}，无法押镖！")
            return
        success, msg, _ = await self.escort_mgr.start_escort(player)
        if success:
            player_name = player.user_name or str(player.user_id)[:8]
            await self._broadcast_world_boss_spawn(
                f"🛡️ 修士【{player_name}】接下了一趟灵石镖，正行走于官道之上...\n"
                f"💡 可消耗【迷神香】发送 /劫镖 @此人 截取镖银！"
            )
        yield event.plain_result(msg)

    @filter.command("完成押镖", "押镖时间结束后结算镖银")
    @require_whitelist
    async def handle_finish_escort(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        success, msg = await self.escort_mgr.finish_escort(player)
        if success:
            await self.db.ext.add_task_progress(player.user_id, "escort", 1)
            await self._title_bump(player.user_id, "escort_count")
            has_progress, bounty_msg = await self.bounty_mgr.add_bounty_progress(player, "escort", 1)
            if has_progress: msg += bounty_msg
        yield event.plain_result(msg)

    @filter.command("放弃押镖", "扔下镖车跑路（无收益）")
    @require_whitelist
    async def handle_quit_escort(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        success, msg = await self.escort_mgr.quit_escort(player)
        yield event.plain_result(msg)

    @filter.command("劫镖", "消耗迷神香截取他人镖银（强制PVP）")
    @require_whitelist
    async def handle_rob_escort(self, event: AstrMessageEvent, target: str = ""):
        from astrbot.api.all import At
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        target_id = self._extract_at_target(event, target)
        if not target_id:
            yield event.plain_result(
                "❌ 未识别到目标！请 @对方。\n"
                "用法：/劫镖 @道友（消耗迷神香×1，10分钟冷却）"
            )
            return
        success, msg = await self.escort_mgr.rob_escort(player, target_id)
        yield event.plain_result(msg)
        # 称号：业力（劫镖为恶）
        try:
            p2 = await self.db.get_player_by_id(event.get_sender_id())
            if p2 and (p2.karma or 0) < 0:
                tmsg = await self.title_hooks.bump_value(p2, "karma_neg", p2.karma)
                if tmsg: yield event.plain_result(tmsg)
        except Exception:
            pass

    # ===== v6.8 奇遇选择 =====
    @filter.command("奇遇选择", "对当前奇遇事件做出抉择")
    @require_whitelist
    async def handle_encounter_choice(self, event: AstrMessageEvent, choice: str = "0"):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        try:
            choice_int = int(choice)
        except ValueError:
            yield event.plain_result("❌ 请输入选项编号，例如：/奇遇选择 1")
            return
        success, msg = await self.encounter_mgr.resolve_choice(player, choice_int)
        yield event.plain_result(msg)

    # ===== v6.10 功德因果 =====
    @filter.command("行善", "捐献灵石积累功德（每日一次）")
    @require_whitelist
    async def handle_do_good(self, event: AstrMessageEvent):
        import time as _time
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        today = _time.strftime("%Y-%m-%d")
        key = f"dogood_{player.user_id}"
        last = await self.db.ext.get_system_config(key)
        if last == today:
            yield event.plain_result("❌ 你今日已经行过善了，明日再来。")
            return
        cost = 2000
        if player.gold < cost:
            yield event.plain_result(f"❌ 行善需要捐献 {cost:,} 灵石（为贫苦散修购置丹药）。")
            return
        player.gold -= cost
        player.karma = (getattr(player, "karma", 0) or 0) + 1
        await self.db.update_player(player)
        await self.db.ext.set_system_config(key, today)
        # 称号：功德
        try:
            tmsg = await self.title_hooks.bump_value(player, "karma", player.karma)
            if tmsg: yield event.plain_result(tmsg)
        except Exception:
            pass
        # 七日任务：行善
        try:
            await self.first_week.record_action(player, "good")
        except Exception:
            pass
        yield event.plain_result(
            "🪷 行善积德！\n"
            "━━━━━━━━━━━━━━━\n"
            f"你捐献 {cost:,} 灵石济困扶危。\n"
            f"功德 +1（当前功德 {player.karma}）\n"
            "✨ 功德可提升奇遇概率与突破成功率\n"
            "🌑 而偷窃、劫镖会积累业力，反向影响突破"
        )

    # ===== v6.10 丹炉系统 =====
    @filter.command("升级丹炉", "消耗灵石升级丹炉（每级炼丹成功率+3%）")
    @require_whitelist
    async def handle_upgrade_furnace(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        success, msg = await self.alchemy_mgr.upgrade_furnace(player)
        yield event.plain_result(msg)
        # 称号：五品炉神
        try:
            if success and self.alchemy_mgr.get_furnace_level(player) >= 5:
                tmsg = await self.title_hooks.bump_value(player, "furnace_max", 5)
                if tmsg: yield event.plain_result(tmsg)
        except Exception:
            pass

    # ===== v6.10 洞天装修 =====
    @filter.command("洞天装修", "购买家具布置洞天")
    @require_whitelist
    async def handle_buy_furniture(self, event: AstrMessageEvent, name: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        if not name.strip():
            name = ""  # 走底层的家具清单展示
        success, msg = await self.blessed_land_mgr.buy_furniture(player, name.strip())
        yield event.plain_result(msg)

    # ===== v6.10 宗门建筑 =====
    @filter.command("宗门建筑", "查看宗门建筑")
    @require_whitelist
    async def handle_sect_buildings(self, event: AstrMessageEvent):
        success, msg = await self.sect_mgr.show_buildings(event.get_sender_id())
        yield event.plain_result(msg)

    @filter.command("升级建筑", "升级宗门建筑（宗主/长老，消耗宗门资金）")
    @require_whitelist
    async def handle_upgrade_building(self, event: AstrMessageEvent, name: str = ""):
        if not name.strip():
            # 空参时先展示建筑面板
            success, msg = await self.sect_mgr.show_buildings(event.get_sender_id())
            if not success:
                yield event.plain_result(msg)
            else:
                yield event.plain_result(msg + "\n\n💡 升级请输入：/升级建筑 <建筑名>")
            return
        success, msg = await self.sect_mgr.upgrade_building(event.get_sender_id(), name.strip())
        yield event.plain_result(msg)

    # ===== v6.10 生活职业 =====
    @filter.command("选择生活职业", "选择专精：炼器师/符箓师/阵法师")
    @require_whitelist
    async def handle_choose_life_skill(self, event: AstrMessageEvent, skill: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        success, msg = await self.life_skill_mgr.choose_skill(player, skill.strip())
        yield event.plain_result(msg)
    @filter.command("制符", "符箓师每日免费绘制一张引雷符")
    @require_whitelist
    async def handle_draw_talisman(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        success, msg = await self.life_skill_mgr.daily_talisman(player)
        yield event.plain_result(msg)

    # ===== v6.10 魔潮天灾 =====
    @filter.command("开启魔潮", "管理员开启全服天灾事件")
    @require_whitelist
    async def handle_start_tide(self, event: AstrMessageEvent, hours: str = "12"):
        if not self._check_boss_admin(event):
            yield event.plain_result("❌ 你没有权限！")
            return
        try:
            h = max(1, min(48, int(hours)))
        except ValueError:
            h = 12
        success, msg = await self.calamity_mgr.start_tide(h)
        if success:
            await self._broadcast_world_boss_spawn(msg)
        yield event.plain_result(msg)

    @filter.command("魔潮状态", "查看魔潮抵御进度")
    @require_whitelist
    async def handle_tide_status(self, event: AstrMessageEvent):
        yield event.plain_result(await self.calamity_mgr.get_status())

    @filter.command("抵御魔潮", "捐献灵石抵御魔潮")
    @require_whitelist
    async def handle_resist_tide(self, event: AstrMessageEvent, amount: str = "0"):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        try:
            amt = int(amount)
        except ValueError:
            yield event.plain_result("❌ 请输入正确的灵石数量，例如：/抵御魔潮 5000")
            return
        success, msg = await self.calamity_mgr.resist(player, amt)
        if "成功抵御" in msg:
            await self._broadcast_world_boss_spawn(msg)
        yield event.plain_result(msg)
        # 称号：魔潮抵御次数
        try:
            if success and "捐献成功" in msg:
                tmsg = await self._title_bump(event.get_sender_id(), "tide_resist")
                if tmsg: yield event.plain_result(tmsg)
        except Exception:
            pass

    # ===== v6.11 管理员工具 =====
    # ===== v6.14 季节系统 =====
    @filter.command("季节", "查看当前灵田季节与加成")
    @require_whitelist
    async def handle_season_info(self, event: AstrMessageEvent):
        from .managers.spirit_farm_manager import SEASON_EFFECTS, get_current_season_index
        season = SEASON_EFFECTS[get_current_season_index()]
        idx = get_current_season_index()
        order = ["春", "夏", "秋", "冬"]
        lines = [
            f"{season['icon']} 当前季节：【{season['name']}】",
            "━━━━━━━━━━━━━━━",
            season["desc"],
            "━━━━━━━━━━━━━━━",
            "四季轮转表：",
            f"  🌱 春·生发：生长+33%，产量+10%",
            f"  ☀️ 夏·炎灼：阳性灵草（火焰花/血灵草）生长+33%",
            f"  🍂 秋·丰收：全灵草产量+25%",
            f"  ❄️ 冬·蛰藏：生长放缓50%，冰心草不受影响",
            "━━━━━━━━━━━━━━━",
            f"季节按现实时间每约一周自动轮转（当前：{order[idx]}季）",
            "💡 发送 /种植 <灵草名> 把握季节加成",
        ]
        yield event.plain_result("\n".join(lines))

    # ===== v6.13 化身托管 =====
    @filter.command("激活化身", "消耗化身傀儡，30天内闭关收益+20%")
    @require_whitelist
    async def handle_activate_avatar(self, event: AstrMessageEvent):
        import json as _json
        import time as _time
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return

        try:
            bonus = _json.loads(player.permanent_bonus) if player.permanent_bonus else {}
        except Exception:
            bonus = {}
        avatar_until = int(bonus.get("avatar_until", 0))
        if avatar_until > int(_time.time()):
            days = (avatar_until - int(_time.time())) // 86400
            yield event.plain_result(f"❌ 你的化身仍在行功中（剩余约 {days} 天），无需重复激活。")
            return

        if not self.storage_ring_mgr.has_item(player, "化身傀儡", 1):
            yield event.plain_result(
                "❌ 你的储物戒中没有【化身傀儡】。\n"
                "💡 化身傀儡为天阶稀有物品，可留意百宝阁刷新。"
            )
            return

        success, msg = await self.storage_ring_mgr.retrieve_item(player, "化身傀儡", 1)
        if not success:
            yield event.plain_result(f"❌ 消耗化身傀儡失败：{msg}")
            return

        # retrieve 已同步物品数据到 player；保留其他加成，写入 avatar_until
        try:
            bonus = _json.loads(player.permanent_bonus) if player.permanent_bonus else {}
        except Exception:
            bonus = {}
        bonus["avatar_until"] = int(_time.time()) + 30 * 86400
        player.permanent_bonus = _json.dumps(bonus, ensure_ascii=False)
        await self.db.update_player(player)

        yield event.plain_result(
            "🤖 化身激活成功！\n"
            "━━━━━━━━━━━━━━━\n"
            "你以秘法唤醒化身傀儡，它将替你昼夜行功。\n"
            "⏳ 有效期：30 天\n"
            "📈 效果：闭关收益 +20%（与其他加成叠加）\n"
            "消耗：化身傀儡 x1"
        )

    # ===== v6.16 炼丹火候 =====
    @filter.command("火候", "炼丹时选择火候（猛火/文火/守中）")
    @require_whitelist
    async def handle_fire_control(self, event: AstrMessageEvent, choice: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        if not choice.strip():
            yield event.plain_result(
                "🔥 火候选择\n"
                "━━━━━━━━━━━━━━━\n"
                "  [1] 猛火急攻 —— 成功率-8%，极品概率大增\n"
                "  [2] 文火慢煨 —— 成功率+6%，难出极品\n"
                "  [3] 控火守中 —— 一切如常\n"
                "━━━━━━━━━━━━━━━\n"
                "💡 先 /炼丹 <ID> 投料，再 /火候 <编号>；开炉时再 /炼丹 <同一ID>"
            )
            return
        success, msg = await self.alchemy_mgr.set_fire_choice(event.get_sender_id(), choice.strip())
        yield event.plain_result(msg)

    # ===== v6.16 仙界日历 =====
    @filter.command("仙界日历", "查看季节与全服事件预告")
    @require_whitelist
    async def handle_calendar(self, event: AstrMessageEvent):
        yield event.plain_result(await self.calamity_mgr.get_calendar())

    # ===== v6.16 NPC道侣（仙灵结缘）=====
    @filter.command("仙灵结缘", "查看仙灵名单或与仙灵结为道侣")
    @require_whitelist
    async def handle_spirit_bond(self, event: AstrMessageEvent, name: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        if not name.strip():
            yield event.plain_result(await self.social_mgr.list_companions())
            return
        success, msg = await self.social_mgr.bond_companion(player, name.strip())
        yield event.plain_result(msg)

    @filter.command("仙灵共修", "每日与仙灵道侣共修（修为+情缘）")
    @require_whitelist
    async def handle_spirit_commune(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        success, msg = await self.social_mgr.daily_commune(player)
        yield event.plain_result(msg)

    @filter.command("仙灵解除", "与仙灵解除道侣关系（情缘清零）")
    @require_whitelist
    async def handle_spirit_break(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        success, msg = await self.social_mgr.break_companion(player)
        yield event.plain_result(msg)

    @filter.command("仙灵代收", "仙灵道侣代收洞天闲置产出（消耗1情缘）")
    @require_whitelist
    async def handle_spirit_collect(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        success, msg = await self.social_mgr.companion_collect_land(player)
        yield event.plain_result(msg)

    # ===== v6.16 师徒系统 =====
    @filter.command("拜师", "拜高境界道友为师")
    @require_whitelist
    async def handle_take_master(self, event: AstrMessageEvent, target: str = ""):
        from astrbot.api.all import At
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        master_id = self._extract_at_target(event, target)
        if not master_id:
            yield event.plain_result(
                "🎓【拜师系统】\n"
                "━━━━━━━━━━━━━━━\n"
                "📌 用法：/拜师 @高境界道友\n"
                "📌 条件：对方境界须高于你 5 级，且门下未满（2人）\n"
                "💰 收益：弟子突破时师父得师德点；出师双方获大礼\n"
                "📍 出师：弟子达筑基期后，师父发 /出师 @弟子\n"
                "━━━━━━━━━━━━━━━\n"
                "💡 师父也可随时 /师徒 查看门下弟子情况"
            )
            return
        success, msg = await self.social_mgr.take_as_disciple(player, master_id)
        yield event.plain_result(msg)

    @filter.command("出师", "为达到筑基的弟子举办出师礼（师父操作）")
    @require_whitelist
    async def handle_graduate(self, event: AstrMessageEvent, target: str = ""):
        from astrbot.api.all import At
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        disciple_id = self._extract_at_target(event, target)
        if not disciple_id:
            yield event.plain_result("用法：/出师 @你的弟子（弟子需达筑基期）")
            return
        success, msg = await self.social_mgr.graduate_disciple(player, disciple_id)
        yield event.plain_result(msg)

    @filter.command("逐出师门", "将弟子逐出师门（师父操作）")
    @require_whitelist
    async def handle_dismiss(self, event: AstrMessageEvent, target: str = ""):
        from astrbot.api.all import At
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        disciple_id = self._extract_at_target(event, target)
        if not disciple_id:
            yield event.plain_result("用法：/逐出师门 @你的弟子")
            return
        success, msg = await self.social_mgr.dismiss_disciple(player, disciple_id)
        yield event.plain_result(msg)

    @filter.command("师徒", "查看我的师徒关系与师德点")
    @require_whitelist
    async def handle_master_info(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        yield event.plain_result(await self.social_mgr.my_master_info(player))

    @filter.command("师德兑换", "用师德点兑换奖励")
    @require_whitelist
    async def handle_virtue_redeem(self, event: AstrMessageEvent, item_id: str = "0"):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        try:
            idx = int(item_id)
        except ValueError:
            idx = 0
        # 记录本次兑换成本（供存储失败退还）
        from .managers.social_manager import SPIRIT_COMPANIONS  # noqa
        goods_cost_ref = 0
        try:
            _shop = {1: 80, 2: 150, 3: 300}
            goods_cost_ref = _shop.get(idx, 0)
        except Exception:
            pass
        success, msg = await self.social_mgr.redeem_virtue(player, idx)
        if success and msg.startswith("__NEED_STORE__"):
            # 物品类奖励：存入储物戒；失败退还师德
            _, payload = msg.split("__NEED_STORE__", 1)
            item_name, count, note = payload.split("|", 2)
            ok, smsg = await self.storage_ring_mgr.store_item(player, item_name, int(count), silent=True)
            if ok:
                yield event.plain_result(f"✅ {note}，【{item_name}】x{count} 已存入储物戒")
            else:
                player.virtue_points = getattr(player, "virtue_points", 0) + goods_cost_ref
                await self.db.update_player(player)
                yield event.plain_result(
                    f"❌ 兑换失败：储物戒已满（{smsg}）\n"
                    f"💰 师德点已退还 {goods_cost_ref}（当前 {player.virtue_points}）。清理储物戒后再试。"
                )
            return
        yield event.plain_result(msg)

    # ===== v6.16 排行扩展 =====
    @filter.command("功德榜", "查看功德与业力排行")
    @require_whitelist
    async def handle_karma_rank(self, event: AstrMessageEvent):
        success, msg = await self.rank_mgr.get_karma_ranking()
        yield event.plain_result(msg)

    @filter.command("气运榜", "查看全服气运之子")
    @require_whitelist
    async def handle_luck_rank(self, event: AstrMessageEvent):
        success, msg = await self.rank_mgr.get_luck_ranking()
        yield event.plain_result(msg)

    @filter.command("师德榜", "查看传道真人排行")
    @require_whitelist
    async def handle_virtue_rank(self, event: AstrMessageEvent):
        success, msg = await self.rank_mgr.get_virtue_ranking()
        yield event.plain_result(msg)

        # ===== v6.20 宗门协作 & 悬赏助力 =====
    @filter.command("仙谱", "查看你在全服修士中的位置")
    @require_whitelist
    async def handle_xianpu(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        all_players = await self.db.get_all_players()
        total = len(all_players)
        # 注册序
        reg_rank = "未知"
        pct_text = ""
        try:
            sorted_by_exp = sorted(all_players, key=lambda p: p.experience, reverse=True)
            my_idx = next((i for i, p in enumerate(sorted_by_exp, 1) if p.user_id == player.user_id), None)
            if my_idx:
                reg_rank = f"第 {my_idx} 位"
                pct = (1 - my_idx / max(1, total)) * 100
                pct_text = f"你的修为已超越全服 {pct:.0f}% 的修士"
        except Exception:
            pct_text = ""
        # 境界分布
        higher = sum(1 for p in all_players if p.level_index > player.level_index)
        lines = [
            "📖 仙谱",
            "━━━━━━━━━━━━━━━",
            f"全服在册修士：{total} 位",
            f"修为排名：{reg_rank}" + (f" / {total}" if reg_rank != "未知" else ""),
        ]
        if pct_text:
            lines.append(f"📊 {pct_text}")
        lines.append(f"⛰️ 境界高于你的修士：{higher} 位")
        lines.append(f"🧭 当前境界：{player.get_level(self.config_manager)}")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("💡 仙路漫漫，与其仰望他人，不如低头赶路")
        # v3.25.0 仙谱升级卡片
        async for r in self.send_text_card(event, "\n".join(lines), "info", "📖 仙谱", "全服修士名鉴"):
            yield r

    @filter.command("宗门丹会", "宗主开启丹会，全宗免费领丹（需炼丹房3级，每周一次）")
    @require_whitelist
    async def handle_sect_pill_party(self, event: AstrMessageEvent):
        import random as _random
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        if not player.sect_id:
            yield event.plain_result("❌ 你还未加入宗门。")
            return
        sect = await self.db.ext.get_sect_by_id(player.sect_id)
        if not sect:
            yield event.plain_result("❌ 宗门信息异常。")
            return
        # 权限：宗主开启
        if sect.sect_owner != player.user_id:
            yield event.plain_result("❌ 只有宗主才能开启丹会。")
            return
        # 炼丹房等级
        try:
            import json as _json
            lv = _json.loads(getattr(sect, "buildings", "{}") or "{}").get("炼丹房", 0)
        except Exception:
            lv = 0
        if lv < 3:
            yield event.plain_result(f"❌ 丹会需要【炼丹房】达到 3 级（当前 {lv}）。先 /升级建筑 炼丹房")
            return
        # 每周一次
        week = __import__("time").strftime("%G-W%V")
        key = f"pill_party_{player.sect_id}_{week}"
        opened = await self.db.ext.get_system_config(key)
        if opened:
            yield event.plain_result("❌ 本周丹会已开启过，下周再来。")
            return
        await self.db.ext.set_system_config(key, "1")
        # 宗主自己先领
        yield event.plain_result(
            "🍶 宗门丹会开启！\n"
            f"【{sect.sect_name}】炼丹房灯火通明，香飘十里。\n"
            f"你先领取了一枚【随机丹药】。\n"
            f"💡 全宗成员 7 天内发送 /领丹会丹 即可各领一枚"
        )

    @filter.command("领丹会丹", "领取本宗丹会丹药（每周一次）")
    @require_whitelist
    async def handle_claim_pill_party(self, event: AstrMessageEvent):
        import random as _random
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        if not player.sect_id:
            yield event.plain_result("❌ 你还未加入宗门。")
            return
        week = __import__("time").strftime("%G-W%V")
        opened = await self.db.ext.get_system_config(f"pill_party_{player.sect_id}_{week}")
        if not opened:
            yield event.plain_result("❌ 本宗本周尚未开启丹会（宗主每周可开启一次）。")
            return
        claim_key = f"pill_party_claim_{player.sect_id}_{week}_{player.user_id}"
        claimed = await self.db.ext.get_system_config(claim_key)
        if claimed:
            yield event.plain_result("❌ 本周已领过丹会丹了。")
            return
        # 随机丹药池
        pills_pool = ["回气散", "凝神丹", "小还丹", "血气丹", "清心丹"]
        pill = _random.choice(pills_pool)
        ok, smsg = await self.storage_ring_mgr.store_item(player, pill, 2, silent=True)
        if not ok:
            yield event.plain_result(f"❌ 储物戒已满，无法发放丹药：{smsg}")
            return
        await self.db.ext.set_system_config(claim_key, "1")
        yield event.plain_result(
            f"🍶 丹会领丹成功！\n"
            f"获得【{pill}】x2（已存入储物戒）\n"
            f"💡 同系列装备凑齐有套装效果，/装备图鉴 查看"
        )

    @filter.command("宗门协作榜", "查看宗门协作周榜与本宗贡献")
    @require_whitelist
    async def handle_sect_coop_board(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        yield event.plain_result(await self.sect_coop.weekly_board(player))

    @filter.command("悬赏助力", "助力他人悬赏，获得奖励分成")
    @require_whitelist
    async def handle_bounty_assist(self, event: AstrMessageEvent, target: str = ""):
        from astrbot.api.all import At
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        target_id = self._extract_at_target(event, target)
        if not target_id:
            yield event.plain_result(
                "🤝【悬赏助力】\n"
                "━━━━━━━━━━━━━━━\n"
                "用法：/悬赏助力 @正在做悬赏的道友\n"
                "收益：获得对方悬赏奖励的 10% + 功德1\n"
                "限制：每个悬赏最多 3 人助力，每人限 1 次"
            )
            return
        success, msg = await self.bounty_assist.assist(player, target_id)
        yield event.plain_result(msg)

    # ===== v6.21 装备图鉴（套装鉴识）=====
    @filter.command("信箱", "查看离线期间的事件信件")
    @require_whitelist
    async def handle_mailbox(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        yield event.plain_result(await self.mailbox.view(player))

    @filter.command("装备图鉴", "鉴识当前装备的套装效果与全部已知套装")
    @require_whitelist
    async def handle_equip_set(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        yield event.plain_result(self.equip_sets.panel(player))

    # ===== v6.17 称号系统 =====
    # ===== v6.20 新手七日仙途 =====
    @filter.command("新手七日", "查看七日任务进度并一键领取奖励")
    @require_whitelist
    async def handle_first_week(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
        # 记录创建行为（第1天）
        try:
            await self.first_week.record_action(player, "created")
        except Exception:
            pass
        # 先尝试一键领取
        try:
            ok, cmsg = await self.first_week.claim(player)
            if ok:
                yield event.plain_result(cmsg)
        except Exception:
            pass
        yield event.plain_result(await self.first_week.onboarding_panel(player))

    @filter.command("称号图鉴", "查看全部称号与收集进度")
    @require_whitelist
    async def handle_title_collection(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
            
        try:
            # 1. 触发历史称号校验补齐
            sync_msg = await self.title_mgr.sync_missing_titles(player)
            
            # 2. 渲染图鉴
            text = self.title_mgr.collection_view(player)
            
            # 3. 如果有补发，附加提示
            if sync_msg:
                text += sync_msg
        except Exception as e:
            logger.exception(f"称号图鉴渲染失败 uid={player.user_id}: {e}")
            text = "❌ 称号图鉴读取失败，请稍后再试。"
            
        # 修复了原代码这里重复调用 collection_view 导致兜底失效的 Bug
        yield event.plain_result(text)

    @filter.command("佩戴称号", "更换展示的称号（加成自动按最高品阶生效）")
    @require_whitelist
    async def handle_title_equip(self, event: AstrMessageEvent, name: str = ""):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
            
        # equip_display 内部已经做了去空格、去@符号、自动推荐最高品阶等容错处理
        success, msg = self.title_mgr.equip_display(player, name)
        if success:
            await self.db.update_player(player)
        yield event.plain_result(msg)

    @filter.command("我的称号", "查看当前拥有的所有称号")
    @require_whitelist
    async def handle_my_title(self, event: AstrMessageEvent):
        player = await self.db.get_player_by_id(event.get_sender_id())
        if not player:
            yield event.plain_result("❌ 道友尚未踏入仙途。")
            return
            
        try:
            # 1. 触发历史称号校验补齐
            sync_msg = await self.title_mgr.sync_missing_titles(player)
            
            # 2. 渲染拥有的全量称号面板
            res = self.title_mgr.my_titles_summary(player)
            
            # 3. 如果有补发，附加提示
            if sync_msg:
                res += sync_msg
        except Exception as e:
            logger.exception(f"我的称号渲染失败 uid={player.user_id}: {e}")
            res = "❌ 称号数据读取失败，请稍后再试。"
            
        yield event.plain_result(res)
    @filter.command("仙界管理", "管理员工具：查玩家/发灵石/重置状态/公告")
    @require_whitelist
    async def handle_admin_tool(self, event: AstrMessageEvent):
        if not self._check_boss_admin(event):
            yield event.plain_result("❌ 你没有管理员权限！")
            return

        # 1. 尝试获取被 @ 的玩家 ID
        at_id = None
        if hasattr(event, "message_obj") and event.message_obj:
            from astrbot.api.all import At
            for comp in event.message_obj.message:
                if isinstance(comp, At):
                    at_id = str(comp.qq)
                    break
                elif isinstance(comp, str) and "[CQ:at,qq=" in comp:
                    import re
                    m = re.search(r"\[CQ:at,qq=(\d+)\]", comp)
                    if m:
                        at_id = m.group(1)
                        break

        # 2. 暴力提取纯文本，防止 @ 组件剥离导致错位
        try:
            raw_text = event.get_plain_text()
        except AttributeError:
            raw_text = event.get_message_str() or ""

        idx = raw_text.find("仙界管理")
        if idx != -1:
            args_str = raw_text[idx + 4:].strip()
        else:
            args_str = raw_text.strip()

        parts = args_str.split()
        clean_parts = [p for p in parts if p.strip()]

        if not clean_parts:
            yield event.plain_result("❌ 请提供子指令。例如：/仙界管理 发灵石 12345 1000")
            return
            
        sub = clean_parts[0]
        arg1 = clean_parts[1] if len(clean_parts) > 1 else ""
        arg2 = clean_parts[2] if len(clean_parts) > 2 else ""

        # ================= 查玩家 =================
        if sub == "查玩家":
            target = None
            # 兼容 @查询
            if at_id and not arg1:
                target = await self.db.get_player_by_id(at_id)
            elif arg1:
                if arg1.isdigit() or (arg1.startswith("@") and arg1[1:].isdigit()):
                    target = await self.db.get_player_by_id(arg1.lstrip("@"))
                else:
                    target = await self.db.get_player_by_name(arg1)
            
            if not target:
                yield event.plain_result(f"❌ 未找到该玩家。")
                return
                
            user_cd = await self.db.ext.get_user_cd(target.user_id)
            loan = await self.db.ext.get_active_loan(target.user_id)
            status = UserStatus.get_name(user_cd.type) if user_cd else "空闲"
            yield event.plain_result(
                f"🔍 玩家数据\n"
                f"━━━━━━━━━━━━━━━\n"
                f"ID：{target.user_id}\n"
                f"道号：{target.user_name or '无'}\n"
                f"职业/境界：{target.cultivation_type} / {target.get_level(self.config_manager)}\n"
                f"修为：{target.experience:,}\n"
                f"灵石：{target.gold:,}\n"
                f"功德/业力：{getattr(target, 'karma', 0):+d}\n"
                f"生活职业：{getattr(target, 'life_skill', '') or '无'}\n"
                f"状态：{status} / {target.state}\n"
                f"转生次数：{target.reincarnation_count}\n"
                f"贷款：{('本金 ' + format(loan['principal'], ',') + ' 灵石') if loan else '无'}"
            )
            return

        # ================= 发灵石 =================
        elif sub == "发灵石":
            target_id = ""
            amount_str = ""
            
            if arg1 == "全体":
                target_id = "全体"
                amount_str = arg2
            elif at_id:
                # 如果有 @，说明是给被艾特的人发
                target_id = at_id
                # 不管 @ 有没有被文本解析吃掉，参数最后一位必然是金额
                if len(clean_parts) >= 2:
                    amount_str = clean_parts[-1]
            elif arg1.isdigit() or (arg1.startswith("@") and arg1[1:].isdigit()):
                # 纯数字 ID
                target_id = arg1.lstrip("@")
                amount_str = arg2
            elif arg1:
                # 尝试按道号查询
                target = await self.db.get_player_by_name(arg1)
                if target:
                    target_id = target.user_id
                    amount_str = arg2
                else:
                    yield event.plain_result(f"❌ 未找到玩家【{arg1}】。")
                    return
            
            if not target_id or not amount_str:
                yield event.plain_result("❌ 参数格式错误。用法：/仙界管理 发灵石 <玩家ID/道号/@玩家/全体> <数量>")
                return
                
            try:
                amount = int(amount_str)
            except ValueError:
                yield event.plain_result("❌ 灵石数量必须是整数。")
                return
            # 钳制：负数发全体会把全服灵石清零，超大数据会破坏经济；单次上限 10 亿
            if amount == 0 or abs(amount) > 1_000_000_000:
                yield event.plain_result("❌ 灵石数量需为非零且绝对值不超过 10 亿的整数。")
                return

            # --- 全体发放逻辑 ---
            if target_id == "全体":
                await self.db.conn.execute("UPDATE players SET gold = MAX(0, gold + ?)", (amount,))
                await self.db.conn.commit()
                sign = "+" if amount >= 0 else ""
                yield event.plain_result(f"✅ 已向 **全体玩家** 发放 {sign}{amount:,} 灵石。")
                return
                
            # --- 单人发放逻辑 ---
            else:
                target = await self.db.get_player_by_id(target_id)
                if not target:
                    yield event.plain_result(f"❌ 数据库中未找到该玩家（ID: {target_id}）。")
                    return
                
                await self.db.add_player_gold(target_id, amount)
                sign = "+" if amount >= 0 else ""
                yield event.plain_result(f"✅ 已向玩家 {target_id}（{target.user_name or '无名'}）{sign}{amount:,} 灵石。")
                return

        # ================= 重置状态 =================
        elif sub == "发称号":
            # /仙界管理 发称号 <ID或@> <称号名>
            target_id = self._extract_at_target(event, arg1)
            tid = target_id or (arg1 if arg1.isdigit() else "")
            title_name = arg2.strip()
            if not tid or not title_name:
                yield event.plain_result("用法：/仙界管理 发称号 <ID或@玩家> <称号名>")
                return
            target = await self.db.get_player_by_id(tid)
            if not target:
                yield event.plain_result(f"❌ 未找到玩家 {tid}。")
                return
            # grant_manual 返回提示文本（str），内部已自行落库
            tmsg = await self.title_hooks.grant_manual(target, title_name)
            if tmsg:
                yield event.plain_result(f"✅ 已授予玩家 {tid} 称号{tmsg}")
            else:
                yield event.plain_result(f"❌ 称号【{title_name}】不存在于称号库或已拥有。/称号图鉴 查看全部")
            return

        elif sub == "运营":
            # v3.24.0 参与度面板：今日指令调用 Top20（玩法调参的数据依据）
            today = time.strftime("%Y%m%d")
            async with self.db.conn.execute(
                "SELECT key, value FROM system_config WHERE key LIKE ? ORDER BY CAST(value AS INTEGER) DESC LIMIT 20",
                (f"stats_cmd_%_{today}",)
            ) as cursor:
                rows = await cursor.fetchall()
            if not rows:
                yield event.plain_result("📊 今日暂无指令调用数据。")
                return
            lines = [f"📊【今日指令热度 Top{len(rows)}】", "━━━━━━━━━━━━━━━"]
            for key, val in rows:
                name = key[len("stats_cmd_"):-len(f"_{today}")]
                lines.append(f"  {val} 次 · {name}")
            yield event.plain_result("\n".join(lines))
            return

        elif sub == "清冷却":
            # /仙界管理 清冷却 <ID> —— 清历练疲劳/决斗/押镖等玩家侧CD
            if not arg1.isdigit():
                yield event.plain_result("用法：/仙界管理 清冷却 <玩家ID>")
                return
            cleaned = 0
            async with self.db.conn.execute(
                "SELECT key FROM system_config WHERE key LIKE ? OR key LIKE ? OR key LIKE ? OR key LIKE ? "
                "OR key LIKE ? OR key LIKE ? OR key LIKE ? OR key LIKE ? OR key LIKE ?",
                (
                    f"adv_cd_{arg1}_%", f"escort_cd_{arg1}", f"duel_pair_{arg1}_%", f"duel_pair_%_{arg1}",
                    f"escort_rob_cd_{arg1}",          # 劫镖冷却
                    f"sect_battle_cd_{arg1}",         # 大比冷却
                    f"sect_battle_daily_{arg1}",      # 大比每日次数
                    f"bounty_abandon_cd_{arg1}",      # 放弃悬赏冷却
                    f"rebirth_last_{arg1}",           # 弃道重修冷却
                )
            ) as cursor:
                rows = await cursor.fetchall()
            for (k,) in rows:
                await self.db.ext.set_system_config(k, "")
                cleaned += 1
            yield event.plain_result(f"✅ 已清理玩家 {arg1} 的 {cleaned} 项冷却。")
            return

        elif sub == "重置状态":
            target_id = at_id if at_id else arg1.lstrip("@")
            if not target_id:
                yield event.plain_result("❌ 请指定要重置状态的玩家。")
                return
                
            target = await self.db.get_player_by_id(target_id)
            if not target:
                yield event.plain_result(f"❌ 未找到玩家 {target_id}。")
                return
                
            await self.db.ext.set_user_busy(target_id, UserStatus.IDLE, 0, extra_data={})
            await self.db.update_player_fields(target_id, state="空闲", cultivation_start_time=0)
            yield event.plain_result(f"✅ 已重置玩家 {target_id}（{target.user_name or '无名'}）的卡死状态。")
            return

        # ================= 公告 =================
        elif sub == "封禁":
            # /仙界管理 封禁 <ID/道号/@玩家> —— 写入 admin_ban_{uid}，player_required 全局拦截
            ban_target = at_id or (arg1.lstrip("@") if arg1 and (arg1.isdigit() or arg1.startswith("@")) else None)
            if not ban_target:
                t = await self.db.get_player_by_name(arg1) if arg1 else None
                ban_target = t.user_id if t else None
            if not ban_target:
                yield event.plain_result("用法：/仙界管理 封禁 <ID/道号/@玩家>")
                return
            await self.db.ext.set_system_config(f"admin_ban_{ban_target}", "1")
            yield event.plain_result(f"⛔ 已封禁玩家 {ban_target}（所有玩家指令将被拦截）。/仙界管理 解封 可解除。")
            return

        elif sub == "解封":
            unban_target = at_id or (arg1.lstrip("@") if arg1 and (arg1.isdigit() or arg1.startswith("@")) else None)
            if not unban_target:
                t = await self.db.get_player_by_name(arg1) if arg1 else None
                unban_target = t.user_id if t else None
            if not unban_target:
                yield event.plain_result("用法：/仙界管理 解封 <ID/道号/@玩家>")
                return
            await self.db.ext.set_system_config(f"admin_ban_{unban_target}", "")
            yield event.plain_result(f"✅ 已解除玩家 {unban_target} 的封禁。")
            return

        elif sub == "深查":
            # /仙界管理 深查 <ID/道号/@玩家> —— 跨系统深度画像
            deep_target = None
            if at_id and not arg1:
                deep_target = await self.db.get_player_by_id(at_id)
            elif arg1:
                deep_target = (
                    await self.db.get_player_by_id(arg1.lstrip("@"))
                    if (arg1.isdigit() or arg1.startswith("@"))
                    else await self.db.get_player_by_name(arg1)
                )
            if not deep_target:
                yield event.plain_result("❌ 未找到该玩家。")
                return
            uid = deep_target.user_id
            try:
                owned_titles = await self.title_mgr._load_owned(deep_target)
            except Exception:
                owned_titles = {}
            partner = await self.marriage_mgr.get_partner_id(uid)
            partner_name = ""
            if partner:
                pp = await self.db.get_player_by_id(partner)
                partner_name = (pp.user_name if pp else "") or partner[:8]
            jade = await self.samsara_mgr.get_jade(uid)
            banned = await self.db.ext.get_system_config(f"admin_ban_{uid}") == "1"
            import json as _dj
            try:
                ring = list(_dj.loads(deep_target.storage_ring_items or "{}").items())[:5]
                ring_txt = "、".join(f"{k}x{v}" for k, v in ring) or "空"
            except Exception:
                ring_txt = "?"
            yield event.plain_result(
                f"🔬 深度档案 · {deep_target.user_name or uid[:8]}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"境界/修为：{deep_target.get_level(self.config_manager)} / {deep_target.experience:,}\n"
                f"灵石/转生：{deep_target.gold:,} / {deep_target.reincarnation_count} 周\n"
                f"称号图鉴：{len(owned_titles)} 个\n"
                f"结契道侣：{partner_name or '无'}\n"
                f"轮回玉：{jade:,}\n"
                f"储物戒（前5）：{ring_txt}\n"
                f"封禁状态：{'⛔ 已封禁' if banned else '正常'}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"ID：{uid}"
            )
            return

        elif sub == "补偿":
            # /仙界管理 补偿 <灵石> <修为> [全体|ID|道号/@] —— 附信箱通知
            try:
                c_gold = int(arg1) if arg1.isdigit() else -1
                c_exp = int(arg2) if arg2.isdigit() else -1
            except ValueError:
                c_gold = c_exp = -1
            if c_gold <= 0 or c_exp < 0:
                yield event.plain_result("用法：/仙界管理 补偿 <灵石> <修为> [全体|ID/@/道号]（灵石>0）")
                return
            rest_parts = clean_parts[3:]
            tgt = rest_parts[0] if rest_parts else "全体"
            reason = " ".join(rest_parts[1:]) or "管理员补偿"
            if tgt == "全体":
                ids = await self.db.get_all_player_ids()
                await self.db.conn.execute(
                    "UPDATE players SET gold = gold + ?, experience = experience + ?",
                    (c_gold, c_exp)
                )
                await self.db.conn.commit()
                yield event.plain_result(f"✅ 已向全服 {len(ids)} 名玩家补偿：{c_gold:,} 灵石 + {c_exp:,} 修为（理由：{reason}）。")
                return
            if tgt.startswith("@"):
                tgt = tgt[1:]
            tp = await self.db.get_player_by_id(tgt) if tgt.isdigit() else await self.db.get_player_by_name(tgt)
            if not tp:
                yield event.plain_result("❌ 未找到该玩家。")
                return
            await self.db.add_player_gold(tp.user_id, c_gold)
            await self.db.add_player_exp(tp.user_id, c_exp)
            try:
                from .managers.enhance_systems import MailboxManager
                await MailboxManager(self.db).send(tp.user_id, "天道补偿", f"你收到补偿：{c_gold:,} 灵石 + {c_exp:,} 修为（{reason}）。")
            except Exception:
                pass
            yield event.plain_result(f"✅ 已补偿 {tp.user_name or tp.user_id}：{c_gold:,} 灵石 + {c_exp:,} 修为（已寄信通知）。")
            return

        elif sub == "玩法状态":
            # 一键总览全部周期玩法的关键状态（只读）
            lines = ["🎛️【玩法状态总览】", "━━━━━━━━━━━━━━━"]
            try:
                st = await self.season_mgr._load_state()
                if st:
                    remain = max(0, int((float(st.get("end_ts", 0)) - time.time()) // 86400))
                    lines.append(f"🏆 天骄榜：第 {st.get('season_no', 1)} 届 · 剩 {remain} 天")
            except Exception:
                pass
            try:
                a_stage = await self.db.ext.syscfg_get_number("ascension_stage")
                a_funds = await self.db.ext.syscfg_get_number("ascension_funds")
                lines.append(f"⛩️ 登仙台：第 {a_stage}/6 阶 · 累计 {a_funds:,} 灵石")
            except Exception:
                pass
            try:
                au = await self.db.ext.get_system_config("loot_auction_state")
                if au:
                    import json as _aj
                    aud = _aj.loads(au)
                    lines.append(f"🔨 拍卖行：{'进行中（截止 ' + time.strftime('%H:%M', time.localtime(aud.get('end_ts', 0))) + '）' if aud.get('open') else '空闲'}")
                else:
                    lines.append("🔨 拍卖行：空闲")
            except Exception:
                pass
            try:
                tr = await self.db.ext.get_system_config("treasure_active")
                if tr:
                    import json as _aj2
                    trd = _aj2.loads(tr)
                    lines.append(f"🌈 天材地宝：{trd.get('name')}（{'已被夺' if trd.get('claimed') else '现世中'}）")
                else:
                    lines.append("🌈 天材地宝：无现世")
            except Exception:
                pass
            try:
                tnm = await self.tournament_mgr._load_state()
                if tnm:
                    lines.append(f"⚔️ 斗法台：{tnm.get('phase')} · 报名 {len(tnm.get('players', []))} 人")
            except Exception:
                pass
            try:
                tide = await self.db.ext.get_system_config("tide_active")
                lines.append(f"🌑 魔潮：{'肆虐中' if tide == '1' else '平静'}")
            except Exception:
                pass
            lines.append("━━━━━━━━━━━━━━━")
            lines.append("💡 发送 /仙界管理 查看 全部管理指令")
            yield event.plain_result("\n".join(lines))
            return

        elif sub == "经济面板":
            # SQL 聚合：全服经济与活跃度一览
            async with self.db.conn.execute(
                "SELECT COUNT(*), SUM(gold), MAX(gold) FROM players"
            ) as cursor:
                total_players, total_gold, max_gold = await cursor.fetchone()
            try:
                async with self.db.conn.execute("SELECT SUM(balance) FROM bank_accounts") as cursor:
                    bank_sum = await cursor.fetchone()
                bank_sum = bank_sum[0] or 0
            except Exception:
                bank_sum = 0
            today = time.strftime("%Y%m%d")
            try:
                async with self.db.conn.execute(
                    "SELECT SUM(CAST(value AS INTEGER)) FROM system_config WHERE key LIKE ?",
                    (f"stats_cmd_%_{today}",)
                ) as cursor:
                    active_cmds = await cursor.fetchone()
                active_cmds = active_cmds[0] or 0
            except Exception:
                active_cmds = 0
            yield event.plain_result(
                f"💰【经济面板】\n"
                f"━━━━━━━━━━━━━━━\n"
                f"注册修士：{total_players or 0}\n"
                f"流通灵石：{(total_gold or 0):,}\n"
                f"首富持有：{(max_gold or 0):,}\n"
                f"银行存款：{bank_sum:,}\n"
                f"今日指令调用：{active_cmds:,} 次\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💡 通胀预警线：流通灵石接近全服日产出×30 时应收紧回收口"
            )
            return

        elif sub == "设境界":
            # /仙界管理 设境界 <ID/道号/@> <境界等级> —— 直接改写 level_index（谨慎使用）
            lv_target = at_id or (arg1.lstrip("@") if arg1 and (arg1.isdigit() or arg1.startswith("@")) else None)
            if not lv_target and arg1:
                tp = await self.db.get_player_by_name(arg1)
                lv_target = tp.user_id if tp else None
            lv_num = int(arg2) if arg2.isdigit() else -1
            level_data = self.config_manager.get_level_data("灵修")
            if not lv_target or not (0 <= lv_num < len(level_data)):
                yield event.plain_result(f"用法：/仙界管理 设境界 <ID/道号/@> <0-{len(level_data) - 1}>")
                return
            tp2 = await self.db.get_player_by_id(lv_target)
            if not tp2:
                yield event.plain_result("❌ 未找到该玩家。")
                return
            old_name = tp2.get_level(self.config_manager)
            # 修为同步到该境界门槛，避免立即被突降的判定卡住
            need_exp = level_data[lv_num].get("exp_needed", 0)
            await self.db.update_player_fields(
                lv_target, level_index=lv_num,
                experience=max(tp2.experience, need_exp),
            )
            new_name = level_data[lv_num]["level_name"]
            yield event.plain_result(f"✅ 已将 {tp2.user_name or lv_target} 从【{old_name}】改为【{new_name}】（修为已补至门槛）。")
            return

        elif sub == "公告":
            # 公告直接把后面的所有内容拼接
            text = " ".join(clean_parts[1:]).strip()
            if not text:
                yield event.plain_result("用法：/仙界管理 公告 <文本>")
                return
            await self._broadcast_world_boss_spawn(f"📜【仙界公告】\n{text}")
            yield event.plain_result("✅ 公告已广播。")
            return

        yield event.plain_result(
            "🛠️ 仙界管理工具\n"
            "━━━━━━━━━━━━━━━\n"
            "【玩家管理】\n"
            "/仙界管理 查玩家 <ID/道号/@玩家>\n"
            "/仙界管理 深查 <ID/道号/@玩家> (跨系统深度档案)\n"
            "/仙界管理 封禁 <ID/道号/@玩家> / 解封 <...>\n"
            "/仙界管理 设境界 <ID/道号/@玩家> <0-35>\n"
            "/仙界管理 清冷却 <ID>\n"
            "/仙界管理 重置状态 <ID/@玩家>\n"
            "【经济与运营】\n"
            "/仙界管理 发灵石 <ID/道号/@玩家/全体> <数量>\n"
            "/仙界管理 发称号 <ID/@玩家> <称号名>\n"
            "/仙界管理 补偿 <灵石> <修为> [全体|ID|@|道号] (附信箱通知)\n"
            "/仙界管理 运营 (今日指令热度Top20)\n"
            "/仙界管理 经济面板 (全服流通/存款/活跃)\n"
            "/仙界管理 玩法状态 (赛季/登仙台/拍卖/Boss/魔潮一览)\n"
            "【全服】\n"
            "/仙界管理 公告 <文本>"
        )
