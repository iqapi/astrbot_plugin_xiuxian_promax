# managers/adventure_manager.py
"""
历练系统管理器 - 可配置路线、风险与奖励
"""

import json
import random
import time
from pathlib import Path
from typing import Tuple, Dict, Optional, List, TYPE_CHECKING

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player
from ..models_extended import UserStatus

if TYPE_CHECKING:
    from ..core import StorageRingManager


class AdventureManager:
    """历练系统管理器"""

    CONFIG_FILE = Path(__file__).resolve().parents[1] / "config" / "adventure_config.json"
    DEFAULT_CONFIG = {
        "routes": [
            {
                "key": "scout",
                "name": "巡山问道",
                "aliases": ["短途", "巡山"],
                "description": "巡视宗门周边，风险较低，适合积累经验。",
                "risk": "低",
                "duration": 1800,
                "min_level": 0,
                "fatigue_cooldown": 300,
                "base_exp_per_min": 45,
                "base_gold_per_min": 10,
                "level_bonus_exp": 12,
                "level_bonus_gold": 3,
                "completion_bonus": {"exp": 300, "gold": 120},
                "event_weights": {"safe": 60, "standard": 30, "risky": 10},
                "drop_tier": "low",
                "bounty_tag": "adventure_scout",
                "bounty_progress": 1
            }
        ],
        "event_groups": {
            "safe": [
                {
                    "key": "steady_path",
                    "name": "平稳推进",
                    "desc": "历练过程顺风顺水，按部就班地完成目标。",
                    "exp_mult": 1.1,
                    "gold_mult": 1.1,
                    "item_chance": 60,
                    "bonus_progress": 0
                }
            ],
            "standard": [
                {
                    "key": "minor_skirmish",
                    "name": "遭遇小型冲突",
                    "desc": "击退拦路妖兽，实战经验有所增长。",
                    "exp_mult": 1.2,
                    "gold_mult": 1.2,
                    "item_chance": 50,
                    "bonus_progress": 1
                }
            ],
            "risky": [
                {
                    "key": "ambush",
                    "name": "埋伏受创",
                    "desc": "遭遇伏击，受了点伤但仍坚持完成任务。",
                    "exp_mult": 0.7,
                    "gold_mult": 0.7,
                    "item_chance": 15,
                    "bonus_progress": 0,
                    "injury": True
                }
            ]
        },
        "drop_tables": {
            "low": [
                {"name": "灵草", "weight": 50, "min": 1, "max": 3},
                {"name": "精铁", "weight": 30, "min": 1, "max": 2},
                {"name": "灵石碎片", "weight": 20, "min": 2, "max": 5}
            ]
        }
    }

    def __init__(self, db: DataBase, storage_ring_manager: "StorageRingManager" = None):
        self.db = db
        self.storage_ring_manager = storage_ring_manager
        self._social = None  # 懒加载 SocialManager（避免循环导入）
        self._route_cooldowns: Dict[str, Dict[str, int]] = {}
        self.routes: Dict[str, dict] = {}
        self.route_alias_index: Dict[str, str] = {}
        self.event_groups: Dict[str, List[dict]] = {}
        self.drop_tables: Dict[str, List[dict]] = {}
        self.default_route_key: str = "scout"
        self.reload_config()

    # -------- 配置加载 --------

    def reload_config(self):
        """重新加载配置文件"""
        config = self._load_config_file()
        self.routes = {route["key"]: route for route in config.get("routes", [])}
        self.default_route_key = next(iter(self.routes.keys()), "scout")

        self.route_alias_index = {}
        for key, route in self.routes.items():
            aliases = set(route.get("aliases", []))
            aliases.add(route["key"])
            aliases.add(route["name"])
            # 兼容旧指令
            if route["key"] == "scout":
                aliases.update({"short", "短途"})
            elif route["key"] == "journey":
                aliases.update({"medium", "中途"})
            elif route["key"] == "peril":
                aliases.update({"long", "长途"})
            for alias in aliases:
                self.route_alias_index[alias.lower()] = key

        self.event_groups = config.get("event_groups", self.DEFAULT_CONFIG["event_groups"])
        self.drop_tables = config.get("drop_tables", self.DEFAULT_CONFIG["drop_tables"])

    def _load_config_file(self) -> dict:
        """加载配置文件并在失败时回退到默认配置"""
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.info("已加载 adventure_config.json")
                    return data
            except Exception as exc:
                logger.error(f"加载 adventure_config.json 失败，将使用默认配置: {exc}")
        return self.DEFAULT_CONFIG

    def get_route_overview(self) -> List[dict]:
        """暴露给指令层的路线概览"""
        overview = []
        for route in self.routes.values():
            overview.append(
                {
                    "key": route["key"],
                    "name": route["name"],
                    "risk": route.get("risk", "未知"),
                    "duration": route.get("duration", 0),
                    "min_level": route.get("min_level", 0),
                    "description": route.get("description", "")
                }
            )
        return overview

    # -------- 核心流程 --------

    async def start_adventure(self, user_id: str, route_token: str = "") -> Tuple[bool, str]:
        """开始指定路线的历练"""
        player = await self.db.get_player_by_id(user_id)
        if not player:
            return False, "❌ 你还未踏入修仙之路！"

        user_cd = await self.db.ext.get_user_cd(user_id)
        if not user_cd:
            await self.db.ext.create_user_cd(user_id)
            user_cd = await self.db.ext.get_user_cd(user_id)

        if user_cd.type != UserStatus.IDLE:
            return False, f"❌ 你当前正{UserStatus.get_name(user_cd.type)}，无法开始历练！"

        # ===== v6.18 空参必须明选路线（不再静默进默认路线）=====
        # 60+ 路线按境界过滤：只显示当前可走的 + 最近的 2 个待解锁预告
        if not route_token or not route_token.strip():
            lines = [
                "🗺️ 请选择历练路线",
                "━━━━━━━━━━━━━━━",
            ]
            available = sorted(
                [r for r in self.routes.values() if player.level_index >= r.get("min_level", 0)],
                key=lambda r: r.get("min_level", 0)
            )
            locked = sorted(
                [r for r in self.routes.values() if player.level_index < r.get("min_level", 0)],
                key=lambda r: r.get("min_level", 0)
            )
            for route in available:
                lines.append(
                    f"  · {route['name']}\n"
                    f"      {route.get('description', '')}\n"
                    f"      风险：{route.get('risk', '?')} | 时长：{route.get('duration', 0) // 60} 分钟"
                    + (f" | 需境界{route.get('min_level')}" if route.get('min_level') else " | 无境界要求")
                )
            if not available:
                lines.append("  （暂无可用路线，异常！）")
            if locked:
                lines.append("━━━━━━━━━━━━━━━")
                lines.append("【即将解锁】再升几级就能去：")
                for route in locked[:3]:
                    lines.append(
                        f"  🔒 {route['name']}（需境界{route.get('min_level')}，还差 {route.get('min_level', 0) - player.level_index} 级）"
                        f" | 时长 {route.get('duration', 0) // 60} 分钟"
                    )
            lines.append("━━━━━━━━━━━━━━━")
            lines.append(f"💡 共 {len(available)} 条路线可用（全服共 {len(self.routes)} 条）")
            lines.append("💡 使用 /开始历练 <路线名> 出发（如 /开始历练 云游四方）")
            return False, "\n".join(lines)

        route_key = self._resolve_route(route_token)
        route = self.routes.get(route_key)
        if not route:
            valid = "、".join(r["name"] for r in self.routes.values())
            return False, (
                f"❌ 未找到路线【{route_token}】。\n"
                f"可选路线：{valid}\n"
                f"💡 也可发送 /开始历练 查看路线详情"
            )

        if player.level_index < route.get("min_level", 0):
            return False, (
                f"❌ 境界不足，无法踏上【{route['name']}】！\n"
                f"━━━━━━━━━━━━━━━\n"
                f"该路线需要境界等级 {route.get('min_level')}\n"
                f"你当前境界等级：{player.level_index}（还差 {route.get('min_level', 0) - player.level_index} 级）\n"
                f"💡 先在低风险路线积累修为，或 /闭关 提升"
            )

        cooldown_key = f"adv_cd_{user_id}_{route_key}"
        cooldown_end = 0
        cooldown_str = await self.db.ext.get_system_config(cooldown_key)
        if cooldown_str and cooldown_str.isdigit():
            cooldown_end = int(cooldown_str)
        now = int(time.time())
        if cooldown_end > now:
            remaining = cooldown_end - now
            minutes = remaining // 60 or 1
            return False, f"⚠️ 该路线尚在休整中，请 {minutes} 分钟后再试。"

        duration = route.get("duration", 3600)
        scheduled_time = now + duration
        extra = {"route_key": route_key}
        await self.db.ext.set_user_busy(user_id, UserStatus.ADVENTURING, scheduled_time, extra_data=extra)

        fatigue = route.get("fatigue_cooldown", 0)
        hint = [
            f"✨ 你选择了「{route['name']}」——{route.get('description', '未知冒险')}",
            f"路线风险：{route.get('risk', '未知')} | 历练时长：{duration // 60} 分钟"
        ]
        if route.get("min_level", 0):
            hint.append(f"建议境界：{route['min_level']} 阶以上")
        if fatigue:
            hint.append(f"（该路线完成后需要休整 {fatigue // 60} 分钟）")

        return True, "\n".join(hint)

    async def finish_adventure(self, user_id: str) -> Tuple[bool, str, Optional[Dict]]:
        """结算历练"""
        player = await self.db.get_player_by_id(user_id)
        if not player:
            return False, "❌ 你还未踏入修仙之路！", None

        user_cd = await self.db.ext.get_user_cd(user_id)
        if not user_cd or user_cd.type != UserStatus.ADVENTURING:
            return False, "❌ 你当前不在历练中！", None

        now = int(time.time())
        if now < user_cd.scheduled_time:
            remaining = user_cd.scheduled_time - now
            minutes = remaining // 60
            seconds = remaining % 60
            return False, f"❌ 历练尚未完成！还需 {minutes}分{seconds}秒。", None

        extra = {}
        if hasattr(user_cd, "get_extra_data"):
            extra = user_cd.get_extra_data()
        else:
            try:
                extra = json.loads(getattr(user_cd, "extra_data", "{}") or "{}")
            except Exception:
                extra = {}

        route = self.routes.get(extra.get("route_key", self.default_route_key)) or self.routes.get(self.default_route_key)
        if not route:
            return False, "❌ 未找到历练路线配置，请联系管理员。", None

        adventure_duration = now - user_cd.create_time
        scheduled_duration = max(1, user_cd.scheduled_time - user_cd.create_time)
        effective_duration = min(adventure_duration, scheduled_duration)
        event = self._trigger_route_event(route)

        rewards = self._calculate_rewards(player, route, effective_duration, event)
        
        # 开始事务
        await self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            # 重新获取玩家对象，确保在事务中
            player = await self.db.get_player_by_id(user_id)
            if not player:
                await self.db.conn.rollback()
                return False, "❌ 你还未踏入修仙之路！", None

            # 事务内重查历练状态：并发双开 /完成历练 时，第二个会因状态已被置回 IDLE 而被拦下
            recheck_cd = await self.db.ext.get_user_cd(user_id)
            if not recheck_cd or recheck_cd.type != UserStatus.ADVENTURING:
                await self.db.conn.rollback()
                return False, "❌ 你当前不在历练中！", None

            # 事务内把状态置回空闲（先占位防并发）。同连接可见未提交数据，并发方重查即被拦下；
            # 用裸 SQL 而非 ext.set_user_free()，后者内部 commit 会击穿本事务的原子性
            await self.db.conn.execute(
                "UPDATE user_cd SET type = 0, scheduled_time = 0, extra_data = '{}' WHERE user_id = ?",
                (user_id,)
            )

            # 处理物品掉落，传递 external_transaction=True
            dropped_items, item_msg = await self._handle_drops(player, route, event, external_transaction=True)

            # 修改玩家属性
            # v6.21 境界压制衰减：超出路线需求10级以上，每级-5%（下限40%）
            try:
                from .enhance_systems import apply_level_suppression
                sup = apply_level_suppression(player, route.get("min_level", 0))
                if sup < 1.0:
                    rewards["exp"] = int(rewards["exp"] * sup)
                    rewards["gold"] = int(rewards["gold"] * sup)
            except Exception:
                pass
            comp_bonus = 0.0
            try:
                if self._social is None:
                    from .social_manager import SocialManager
                    self._social = SocialManager(self.db)
                comp_bonus = await self._social.companion_bonus_async(user_id, "adventure")
            except Exception:
                comp_bonus = 0.0
            if comp_bonus > 0:
                rewards["exp"] = int(rewards["exp"] * (1 + comp_bonus))
            # v3.19.0 新玩法：天象（历练）/ 轮回周目 / 图鉴收集 / 天骄榜赛季
            try:
                from .weather_manager import WeatherManager
                wm = await WeatherManager(self.db).get_multiplier("adventure")
                if wm != 1.0:
                    rewards["exp"] = int(rewards["exp"] * wm)
            except Exception:
                pass
            try:
                from .samsara_manager import SamsaraManager
                from .collection_manager import CollectionManager
                sams_bonus = SamsaraManager.get_exp_bonus(player)
                coll_bonus = CollectionManager.get_exp_bonus(player)
                if sams_bonus > 0:
                    rewards["exp"] = int(rewards["exp"] * (1 + sams_bonus))
                if coll_bonus > 0:
                    rewards["exp"] = int(rewards["exp"] * (1 + coll_bonus))
            except Exception:
                pass
            # v3.20.0 新玩法：结契羁绊 / 灵宠出战（异常安全）
            try:
                from .marriage_manager import MarriageManager
                bond = await MarriageManager(self.db).bond_bonus(player)
                if bond > 0:
                    rewards["exp"] = int(rewards["exp"] * (1 + bond))
            except Exception:
                pass
            try:
                from .pet_battle_manager import PetBattleManager
                petb = await PetBattleManager(self.db).get_exp_bonus(player.user_id)
                if petb > 0:
                    rewards["exp"] = int(rewards["exp"] * (1 + petb))
            except Exception:
                pass
            # v3.21.0 宗门科技：聚灵阵（修为）+ 生财阵（灵石）（异常安全）
            try:
                if player.sect_id:
                    from .sect_tech_manager import SectTechManager
                    stm = SectTechManager(self.db)
                    tech_exp = await stm.get_cultivate_bonus(player.sect_id)
                    tech_gold = await stm.get_gold_bonus(player.sect_id)
                    if tech_exp > 0:
                        rewards["exp"] = int(rewards["exp"] * (1 + tech_exp))
                    if tech_gold > 0:
                        rewards["gold"] = int(rewards["gold"] * (1 + tech_gold))
            except Exception:
                pass
            # v3.22.0 每日求签修为倍率（异常安全）
            try:
                from .fortune_stick_manager import FortuneStickManager
                fm = await FortuneStickManager(self.db).get_exp_mult(player)
                if fm != 1.0:
                    rewards["exp"] = int(rewards["exp"] * fm)
                # v3.23.0 补接财签灵石倍率（此前定义未接入，财签等于白抽）
                gm = await FortuneStickManager(self.db).get_gold_mult(player)
                if gm != 1.0:
                    rewards["gold"] = int(rewards["gold"] * gm)
            except Exception:
                pass
            # 结契羁绊值：共同历练积累（已婚者 +1）
            try:
                from .marriage_manager import MarriageManager
                mm = MarriageManager(self.db)
                partner_id = await mm.get_partner_id(player.user_id)
                if partner_id:
                    await mm.add_bond(player.user_id, partner_id, 1)
            except Exception:
                pass
            player.experience += rewards["exp"]
            player.gold += rewards["gold"]

            # 道侣周任务：历练计数（异常安全）
            try:
                from .couple_quest_manager import CoupleQuestManager
                await CoupleQuestManager(self.db).record_action(player, "adventure")
            except Exception:
                pass
            # 天骄榜：赛季修为增量
            try:
                from .season_manager import SeasonManager
                if rewards["exp"] > 0:
                    await SeasonManager(self.db).record_exp_gain(user_id, rewards["exp"])
            except Exception:
                pass
            
            # 一次更新玩家对象
            await self.db.update_player(player)
            await self.db.conn.commit()
        except Exception:
            await self.db.conn.rollback()
            raise

        fatigue = route.get("fatigue_cooldown", 0)
        if event.get("injury"):
            # 受伤时增加额外休整时间
            fatigue += 600
        if fatigue:
            # 冷却持久化到数据库，重启不失效
            await self.db.ext.set_system_config(
                f"adv_cd_{user_id}_{route['key']}", str(int(time.time()) + fatigue)
            )
            # 内存冷却缓存：清理已过期条目，防止 dict 无界增长
            user_cds = self._route_cooldowns.setdefault(user_id, {})
            now_ts = int(time.time())
            for k in [k for k, v in user_cds.items() if v < now_ts]:
                del user_cds[k]
            user_cds[route["key"]] = now_ts + fatigue

        fatigue_hint = f"\n⏳ 该路线休整：{fatigue // 60} 分钟" if fatigue else ""
        display_minutes = effective_duration // 60
        msg = (
            f"🚶 历练归来 · {route['name']}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"{event['desc']}\n\n"
            f"本次历练：{display_minutes} 分钟\n"
            f"获得修为：+{rewards['exp']:,}\n"
            f"获得灵石：+{rewards['gold']:,}"
            f"{item_msg}"
            f"\n━━━━━━━━━━━━━━━\n"
            f"当前修为：{player.experience:,}\n"
            f"当前灵石：{player.gold:,}"
            f"{fatigue_hint}"
        )

        reward_data = {
            "route_key": route["key"],
            "route_name": route["name"],
            "event_key": event.get("key"),
            "event_desc": event["desc"],
            "exp_reward": rewards["exp"],
            "gold_reward": rewards["gold"],
            "items": dropped_items,
            "duration": effective_duration,
            "bounty_tag": route.get("bounty_tag", "adventure"),
            "bounty_progress": max(1, route.get("bounty_progress", 1) + event.get("bonus_progress", 0))
        }
        return True, msg, reward_data

    async def check_adventure_status(self, user_id: str) -> Tuple[bool, str]:
        """查看历练状态"""
        user_cd = await self.db.ext.get_user_cd(user_id)
        if not user_cd or user_cd.type != UserStatus.ADVENTURING:
            return False, "❌ 你当前不在历练中！"

        now = int(time.time())
        route_name = "未知路线"
        extra = {}
        if hasattr(user_cd, "get_extra_data"):
            extra = user_cd.get_extra_data()
        else:
            try:
                extra = json.loads(getattr(user_cd, "extra_data", "{}") or "{}")
            except Exception:
                extra = {}
        route = self.routes.get(extra.get("route_key", self.default_route_key))
        if route:
            route_name = route["name"]

        if now >= user_cd.scheduled_time:
            return True, f"✅ {route_name} 已完成！使用 /完成历练 领取奖励。"

        remaining = user_cd.scheduled_time - now
        elapsed = now - user_cd.create_time
        minutes = remaining // 60
        seconds = remaining % 60
        elapsed_minutes = elapsed // 60

        msg = (
            f"📍 历练进度 · {route_name}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"已历练：{elapsed_minutes} 分钟\n"
            f"剩余时间：{minutes}分{seconds}秒\n"
            f"请耐心等待历练完成..."
        )
        return True, msg

    # -------- 内部工具 --------

    def _resolve_route(self, token: str) -> Optional[str]:
        """解析路线 token：精确key → 别名 → 模糊包含。找不到返回 None（由调用方报错，不再静默回退默认路线）"""
        if not token:
            return None
        token = token.strip()
        if not token:
            return None
        if token in self.routes:
            return token
        if token in self.route_alias_index:
            return self.route_alias_index[token]
        normalized = token.lower()
        if normalized in self.route_alias_index:
            return self.route_alias_index[normalized]
        # 模糊包含匹配（如"云游"匹配"云游四方"）
        for key, route in self.routes.items():
            if token in route.get("name", "") or normalized in route.get("name", "").lower():
                return key
        return None

    def _trigger_route_event(self, route: dict) -> dict:
        weights = route.get("event_weights", {})
        if not weights:
            group_key = "standard"
        else:
            total_weight = sum(max(0, w) for w in weights.values()) or 1
            roll = random.randint(1, total_weight)
            upto = 0
            group_key = "standard"
            for key, weight in weights.items():
                upto += max(0, weight)
                if roll <= upto:
                    group_key = key
                    break

        group = self.event_groups.get(group_key) or self.event_groups.get("standard") or self.DEFAULT_CONFIG["event_groups"]["standard"]
        return random.choice(group)

    def _calculate_rewards(self, player: Player, route: dict, duration: int, event: dict) -> Dict[str, int]:
        duration_minutes = max(1, duration // 60)
        base_exp = duration_minutes * route.get("base_exp_per_min", 40)
        base_gold = duration_minutes * route.get("base_gold_per_min", 10)

        level_bonus_exp = player.level_index * route.get("level_bonus_exp", 10)
        level_bonus_gold = player.level_index * route.get("level_bonus_gold", 2)

        completion_bonus = route.get("completion_bonus", {})
        exp_total = base_exp + level_bonus_exp + completion_bonus.get("exp", 0)
        gold_total = base_gold + level_bonus_gold + completion_bonus.get("gold", 0)

        final_exp = max(0, int(exp_total * event.get("exp_mult", 1.0)))
        final_gold = max(0, int(gold_total * event.get("gold_mult", 1.0)))
        return {"exp": final_exp, "gold": final_gold}

    async def _companion_adventure_bonus(self, user_id: str) -> float:
        """仙灵道侣历练加成（白芷：修为+8%起）"""
        try:
            return await self._social.companion_bonus_async(user_id, "adventure")
        except Exception:
            return 0.0

    async def _handle_drops(self, player: Player, route: dict, event: dict, external_transaction: bool = False) -> Tuple[List[Tuple[str, int]], str]:
        dropped_items: List[Tuple[str, int]] = []
        if not self.storage_ring_manager:
            return dropped_items, ""

        item_chance = event.get("item_chance", 40)
        if random.randint(1, 100) > item_chance:
            return dropped_items, ""

        tier = event.get("drop_tier") or route.get("drop_tier") or "low"
        drop_table = self.drop_tables.get(tier, self.DEFAULT_CONFIG["drop_tables"]["low"])
        total_weight = sum(item["weight"] for item in drop_table)
        roll = random.randint(1, total_weight)
        upto = 0
        chosen = drop_table[0]
        for item in drop_table:
            upto += item["weight"]
            if roll <= upto:
                chosen = item
                break

        count = random.randint(chosen["min"], chosen["max"])
        dropped_items.append((chosen["name"], count))

        item_lines = []
        for item_name, qty in dropped_items:
            success, _ = await self.storage_ring_manager.store_item(player, item_name, qty, silent=True, external_transaction=external_transaction)
            if success:
                item_lines.append(f"  · {item_name} x{qty}")
            else:
                item_lines.append(f"  · {item_name} x{qty}（储物戒已满，丢失）")

        if item_lines:
            return dropped_items, "\n\n📦 获得物品：\n" + "\n".join(item_lines)
        return dropped_items, ""
