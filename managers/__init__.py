# managers/__init__.py

# 基础系统
from .combat_manager import CombatManager, CombatStats
from .sect_manager import SectManager
from .rift_manager import RiftManager
from .ranking_manager import RankingManager
from .adventure_manager import AdventureManager
from .alchemy_manager import AlchemyManager
from .impart_manager import ImpartManager
from .bank_manager import BankManager
from .bounty_manager import BountyManager
from .impart_pk_manager import ImpartPkManager

# Phase 4 系统
from .blessed_land_manager import BlessedLandManager
from .spirit_farm_manager import SpiritFarmManager
from .dual_cultivation_manager import DualCultivationManager
from .spirit_eye_manager import SpiritEyeManager

# v6.1 系统
from .daily_task_manager import DailyTaskManager
from .world_boss_manager import WorldBossManager
from .robbery_manager import RobberyManager
from .tutorial_manager import TutorialManager
from .reincarnation_manager import ReincarnationManager

# v6.2 - v6.5 系统
from .gamble_manager import GambleManager
from .forge_manager import ForgeManager
from .demon_invasion_manager import DemonInvasionManager
from .pet_manager import PetManager

# v6.6 交易坊市
from .auction_manager import AuctionManager

# v6.8 押镖劫道
from .escort_manager import EscortManager
# v6.8 奇遇系统
from .encounter_manager import EncounterManager
# v6.10 生活职业
from .life_skill_manager import LifeSkillManager
# v6.10 魔潮天灾
from .calamity_manager import CalamityManager
# v3.26.0 镇妖塔 & 功德善堂
from .tower_manager import TowerManager
from .merit_manager import MeritManager
# v3.27.0 除妖
from .hunt_manager import HuntManager
# v3.29.0 云游商人
from .wander_merchant_manager import WanderMerchantManager
# v3.30.0 段位天梯
from .ladder_manager import LadderManager
# v3.32.0 灵潮事件
from .spirit_tide_manager import SpiritTideManager
# v3.33.0 宗门秘境
from .sect_raid_manager import SectRaidManager
# v3.34.0 仙途回忆录
from .memoir_manager import MemoirManager

__all__ = [
    "CombatManager", "CombatStats", "SectManager", "RiftManager",
    "RankingManager", "AdventureManager", "AlchemyManager", "ImpartManager",
    "BankManager", "BountyManager", "ImpartPkManager",
    "BlessedLandManager", "SpiritFarmManager", "DualCultivationManager", "SpiritEyeManager",
    "DailyTaskManager", "WorldBossManager", "RobberyManager", "TutorialManager", "ReincarnationManager",
    "GambleManager", "ForgeManager", "DemonInvasionManager", "PetManager",
    "AuctionManager", "EscortManager", "EncounterManager", "LifeSkillManager", "CalamityManager",
    "TowerManager", "MeritManager", "HuntManager", "WanderMerchantManager", "LadderManager",
    "SpiritTideManager", "SectRaidManager", "MemoirManager"
]