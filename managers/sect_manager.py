# managers/sect_manager.py
"""
宗门系统管理器 - 处理宗门创建、管理、捐献、任务等逻辑
"""

import json
import random
import time
from typing import Tuple, List, Optional, Dict
from ..data.data_manager import DataBase
from ..models_extended import Sect, UserStatus
from ..models import Player

SECT_NAME_MIN_LENGTH = 2
SECT_NAME_MAX_LENGTH = 12
SECT_NAME_FORBIDDEN = ["管理员", "系统", "官方", "GM", "admin"]

# 宗门建筑配置：消耗宗门资金升级，给全宗提供被动
SECT_BUILDINGS: Dict[str, dict] = {
    "藏经阁": {"max_level": 5, "base_cost": 5000, "desc": "全宗闭关收益+3%/级"},
    "演武场": {"max_level": 5, "base_cost": 5000, "desc": "宗门任务奖励+10%/级"},
    "炼丹房": {"max_level": 5, "base_cost": 8000, "desc": "全宗炼丹成功率+2%/级"},
}


class SectManager:
    """宗门系统管理器"""
    
    POSITIONS = {
        0: "宗主", 1: "长老", 2: "亲传弟子", 3: "内门弟子", 4: "外门弟子"
    }
    
    POSITION_PERMISSIONS = {
        0: ["manage_all", "kick", "position_change", "build", "search_skill"],
        1: ["kick_outer", "build"],
        2: ["learn_skill"],
        3: ["learn_skill"],
        4: []
    }
    
    def __init__(self, db: DataBase, config_manager=None):
        self.db = db
        self.config = config_manager.sect_config if config_manager else {}
    
    def _validate_sect_name(self, name: str) -> Tuple[bool, str]:
        """验证宗门名称"""
        if len(name) < SECT_NAME_MIN_LENGTH or len(name) > SECT_NAME_MAX_LENGTH:
            return False, f"❌ 宗门名称长度需在{SECT_NAME_MIN_LENGTH}-{SECT_NAME_MAX_LENGTH}字之间！"
        for forbidden in SECT_NAME_FORBIDDEN:
            if forbidden.lower() in name.lower():
                return False, f"❌ 宗门名称包含禁用词汇！"
        return True, ""
    
    def get_buildings(self, sect: Sect) -> Dict[str, int]:
        """读取宗门建筑等级"""
        try:
            data = json.loads(sect.buildings) if getattr(sect, "buildings", None) else {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get_building_level(self, sect: Sect, name: str) -> int:
        return int(self.get_buildings(sect).get(name, 0))

    async def get_sect_building_bonus(self, user_id: str, name: str) -> int:
        """获取某玩家所在宗门指定建筑的等级（无宗门返回0）"""
        player = await self.db.get_player_by_id(user_id)
        if not player or player.sect_id == 0:
            return 0
        sect = await self.db.ext.get_sect_by_id(player.sect_id)
        if not sect:
            return 0
        return self.get_building_level(sect, name)

    async def show_buildings(self, user_id: str) -> Tuple[bool, str]:
        """查看宗门建筑面板"""
        player = await self.db.get_player_by_id(user_id)
        if not player or player.sect_id == 0:
            return False, "❌ 你还未加入宗门！"
        sect = await self.db.ext.get_sect_by_id(player.sect_id)
        if not sect:
            return False, "❌ 宗门信息异常！"

        levels = self.get_buildings(sect)
        lines = [
            f"🏛️ 【{sect.sect_name}】宗门建筑",
            f"宗门资金：{sect.sect_used_stone:,} 灵石",
            "━━━━━━━━━━━━━━━",
        ]
        for name, cfg in SECT_BUILDINGS.items():
            lv = levels.get(name, 0)
            next_cost = cfg["base_cost"] * (lv + 1)
            status = "满级" if lv >= cfg["max_level"] else f"升级需 {next_cost:,} 资金"
            lines.append(f"【{name}】Lv.{lv}/{cfg['max_level']} - {cfg['desc']}")
            lines.append(f"  └ {status}")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("💡 宗主/长老发送 /升级建筑 <名称>（消耗宗门资金）")
        return True, "\n".join(lines)

    async def upgrade_building(self, operator_id: str, name: str) -> Tuple[bool, str]:
        """升级宗门建筑（宗主/长老操作，消耗宗门资金）"""
        cfg = SECT_BUILDINGS.get(name)
        if not cfg:
            listing = "\n".join(
                f"  · {n}（{c['desc']}，满级{c['max_level']}级）" for n, c in SECT_BUILDINGS.items()
            )
            return False, (
                f"❌ 未知建筑【{name}】。\n可升级的建筑：\n{listing}\n"
                "💡 用法：/升级建筑 <建筑名>"
            )

        operator = await self.db.get_player_by_id(operator_id)
        if not operator or operator.sect_id == 0:
            return False, "❌ 你还未加入宗门！"
        if operator.sect_position not in (0, 1):
            return False, "❌ 只有宗主和长老才能升级建筑！"

        sect = await self.db.ext.get_sect_by_id(operator.sect_id)
        if not sect:
            return False, "❌ 宗门信息异常！"

        levels = self.get_buildings(sect)
        lv = levels.get(name, 0)
        if lv >= cfg["max_level"]:
            return False, f"❌ 【{name}】已达最高等级。"

        cost = cfg["base_cost"] * (lv + 1)
        if sect.sect_used_stone < cost:
            return False, f"❌ 宗门资金不足！升级【{name}】需要 {cost:,} 灵石（当前 {sect.sect_used_stone:,}），请号召成员 /宗门捐献。"

        sect.sect_used_stone -= cost
        levels[name] = lv + 1
        sect.buildings = json.dumps(levels, ensure_ascii=False)
        await self.db.ext.update_sect(sect)
        return True, (
            f"🏗️ 宗门建筑升级成功！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"【{name}】Lv.{lv} → Lv.{lv + 1}\n"
            f"效果：{cfg['desc']}\n"
            f"消耗宗门资金：{cost:,} 灵石"
        )

    async def create_sect(self, user_id: str, sect_name: str, required_stone: int = None, required_level: int = None) -> Tuple[bool, str]:
        """创建宗门"""
        if required_stone is None: required_stone = self.config.get("create_cost", 10000)
        if required_level is None: required_level = self.config.get("create_level_required", 3)
            
        player = await self.db.get_player_by_id(user_id)
        if not player: return False, "❌ 你还未踏入修仙之路！"
        if player.sect_id != 0: return False, "❌ 你已经加入了宗门，无法创建新宗门！"
        if player.level_index < required_level: return False, f"❌ 创建宗门需要达到境界等级 {required_level}！"
        if player.gold < required_stone: return False, f"❌ 创建宗门需要 {required_stone} 灵石！"
        
        valid, error = self._validate_sect_name(sect_name)
        if not valid: return False, error
        if await self.db.ext.get_sect_by_name(sect_name): return False, f"❌ 宗门名称『{sect_name}』已被使用！"
        
        player.gold -= required_stone
        await self.db.update_player(player)
        
        new_sect = Sect(
            sect_id=0, sect_name=sect_name, sect_owner=user_id, sect_scale=100, sect_used_stone=0,
            sect_fairyland=0, sect_materials=100, mainbuff="0", secbuff="0", elixir_room_level=0
        )
        sect_id = await self.db.ext.create_sect(new_sect)
        await self.db.ext.update_player_sect_info(user_id, sect_id, 0)
        
        buff_info = await self.db.ext.get_buff_info(user_id)
        if not buff_info: await self.db.ext.create_buff_info(user_id)
        
        return True, f"✨ 恭喜！你成功创建了宗门『{sect_name}』，成为一代宗主！"
    
    async def join_sect(self, user_id: str, sect_name: str) -> Tuple[bool, str]:
        """加入宗门"""
        player = await self.db.get_player_by_id(user_id)
        if not player: return False, "❌ 你还未踏入修仙之路！"
        if player.sect_id != 0: return False, "❌ 你已经加入了宗门！请先退出当前宗门。"
        
        sect = await self.db.ext.get_sect_by_name(sect_name)
        if not sect: return False, f"❌ 未找到宗门『{sect_name}』！"
        
        await self.db.ext.update_player_sect_info(user_id, sect.sect_id, 4)
        buff_info = await self.db.ext.get_buff_info(user_id)
        if not buff_info: await self.db.ext.create_buff_info(user_id)
        return True, f"✨ 你成功加入了宗门『{sect_name}』，成为外门弟子！"
    
    async def leave_sect(self, user_id: str) -> Tuple[bool, str]:
        """退出宗门"""
        player = await self.db.get_player_by_id(user_id)
        if not player: return False, "❌ 你还未踏入修仙之路！"
        if player.sect_id == 0: return False, "❌ 你还未加入任何宗门！"
        
        sect = await self.db.ext.get_sect_by_id(player.sect_id)
        if sect and sect.sect_owner == user_id: return False, "❌ 宗主无法直接退出宗门！请先传位或解散宗门。"
        sect_name = sect.sect_name if sect else "未知宗门"
        
        await self.db.ext.update_player_sect_info(user_id, 0, 0)
        player.sect_id = 0
        player.sect_position = 0
        player.sect_contribution = 0
        await self.db.update_player(player)
        return True, f"✨ 你已退出宗门『{sect_name}』！贡献度已清零。"
    
    async def donate_to_sect(self, user_id: str, stone_amount: int) -> Tuple[bool, str]:
        """宗门捐献"""
        player = await self.db.get_player_by_id(user_id)
        if not player or player.sect_id == 0: return False, "❌ 你还未加入宗门！"
        if stone_amount <= 0: return False, "❌ 捐献数量必须大于0！"
        if player.gold < stone_amount: return False, f"❌ 你的灵石不足！当前拥有 {player.gold} 灵石。"
        
        # 原子增减：避免全字段覆盖回滚其他并发修改
        await self.db.conn.execute(
            "UPDATE players SET gold = MAX(0, gold - ?), sect_contribution = sect_contribution + ? WHERE user_id = ?",
            (stone_amount, stone_amount, user_id)
        )
        await self.db.conn.commit()
        # 同步内存对象，供后续消息展示
        player.gold -= stone_amount
        player.sect_contribution += stone_amount
        await self.db.ext.donate_to_sect(player.sect_id, stone_amount)
        
        return True, f"✨ 捐献成功！消耗 {stone_amount} 灵石，宗门获得 {stone_amount * 10} 建设度！\n你的宗门贡献度：{player.sect_contribution}"

    async def get_sect_info(self, user_id: str) -> Tuple[bool, str, Optional[Dict]]:
        """获取宗门信息"""
        player = await self.db.get_player_by_id(user_id)
        if not player: return False, "❌ 你还未踏入修仙之路！", None
        if player.sect_id == 0: return False, "❌ 你还未加入宗门！", None
        
        sect = await self.db.ext.get_sect_by_id(player.sect_id)
        if not sect: return False, "❌ 宗门信息异常！", None
        
        owner = await self.db.get_player_by_id(sect.sect_owner)
        owner_name = owner.user_name if owner and owner.user_name else sect.sect_owner
        members = await self.db.ext.get_sect_members(sect.sect_id)
        
        info_msg = (
            f"🏛️ 宗门信息\n━━━━━━━━━━━━━━━\n"
            f"宗门名称：{sect.sect_name}\n宗主：{owner_name}\n建设度：{sect.sect_scale}\n"
            f"宗门灵石：{sect.sect_used_stone}\n宗门资材：{sect.sect_materials}\n丹房等级：{sect.elixir_room_level}\n"
            f"成员数量：{len(members)}人\n"
            f"\n你的职位：{self.POSITIONS.get(player.sect_position, '未知')}\n你的贡献：{player.sect_contribution}"
        )
        return True, info_msg, {"sect": sect, "player_position": player.sect_position, "player_contribution": player.sect_contribution, "member_count": len(members)}
    
    async def list_all_sects(self) -> Tuple[bool, str]:
        """获取所有宗门列表"""
        sects = await self.db.ext.get_all_sects()
        if not sects: return False, "❌ 当前还没有任何宗门！"
        
        msg = "🏛️ 宗门列表\n━━━━━━━━━━━━━━━\n"
        for idx, sect in enumerate(sects[:10], 1):
            owner = await self.db.get_player_by_id(sect.sect_owner)
            owner_name = owner.user_name if owner and owner.user_name else "未知"
            members = await self.db.ext.get_sect_members(sect.sect_id)
            msg += f"{idx}. 【{sect.sect_name}】\n   宗主：{owner_name}\n   建设度：{sect.sect_scale} | 成员：{len(members)}人\n\n"
        return True, msg
    
    async def change_position(self, operator_id: str, target_id: str, new_position: int) -> Tuple[bool, str]:
        """变更宗门职位"""
        operator = await self.db.get_player_by_id(operator_id)
        if not operator or operator.sect_id == 0: return False, "❌ 你还未加入宗门！"
        if operator.sect_position != 0: return False, "❌ 只有宗主才能变更职位！"
        
        target = await self.db.get_player_by_id(target_id)
        if not target or target.sect_id != operator.sect_id: return False, "❌ 目标用户不在你的宗门！"
        if target_id == operator_id: return False, "❌ 无法变更自己的职位！"
        if new_position not in self.POSITIONS: return False, "❌ 无效的职位！"
        if new_position == 0: return False, "❌ 无法直接任命宗主！请使用传位功能。"
        
        await self.db.ext.update_player_sect_info(target_id, target.sect_id, new_position)
        return True, f"✨ 已将 {target.user_name or target_id} 的职位变更为：{self.POSITIONS[new_position]}"
    
    async def transfer_ownership(self, current_owner_id: str, new_owner_id: str) -> Tuple[bool, str]:
        """宗主传位"""
        current_owner = await self.db.get_player_by_id(current_owner_id)
        if not current_owner or current_owner.sect_id == 0: return False, "❌ 你还未加入宗门！"
        
        sect = await self.db.ext.get_sect_by_id(current_owner.sect_id)
        if not sect or sect.sect_owner != current_owner_id: return False, "❌ 你不是宗主！"
        
        new_owner = await self.db.get_player_by_id(new_owner_id)
        if not new_owner or new_owner.sect_id != current_owner.sect_id: return False, "❌ 目标用户不在你的宗门！"
        if new_owner_id == current_owner_id: return False, "❌ 无法传位给自己！"
        
        sect.sect_owner = new_owner_id
        await self.db.ext.update_sect(sect)
        await self.db.ext.update_player_sect_info(new_owner_id, sect.sect_id, 0)
        await self.db.ext.update_player_sect_info(current_owner_id, sect.sect_id, 1)
        
        return True, f"✨ 宗主之位已传给 {new_owner.user_name or new_owner_id}！你现在是长老。"
    
    async def kick_member(self, operator_id: str, target_id: str) -> Tuple[bool, str]:
        """踢出宗门成员"""
        operator = await self.db.get_player_by_id(operator_id)
        if not operator or operator.sect_id == 0: return False, "❌ 你还未加入宗门！"
        if operator.sect_position not in [0, 1]: return False, "❌ 只有宗主和长老才能踢出成员！"
        
        target = await self.db.get_player_by_id(target_id)
        if not target or target.sect_id != operator.sect_id: return False, "❌ 目标用户不在你的宗门！"
        if target_id == operator_id: return False, "❌ 无法踢出自己！"
        if operator.sect_position == 1 and target.sect_position <= 3: return False, "❌ 长老只能踢出外门弟子！"
        if target.sect_position == 0: return False, "❌ 无法踢出宗主！"
        
        await self.db.ext.update_player_sect_info(target_id, 0, 0)  # 与主动退宗保持一致：无宗门时职位归零
        target.sect_contribution = 0
        await self.db.update_player(target)
        return True, f"✨ 已将 {target.user_name or target_id} 踢出宗门！"

    async def perform_sect_task(self, user_id: str) -> Tuple[bool, str]:
        """执行宗门任务"""
        player = await self.db.get_player_by_id(user_id)
        if not player or player.sect_id == 0: return False, "❌ 你还未加入宗门！"
        
        user_cd = await self.db.ext.get_user_cd(user_id)
        if not user_cd:
            await self.db.ext.create_user_cd(user_id)
            user_cd = await self.db.ext.get_user_cd(user_id)
            
        current_time = int(time.time())
        if user_cd.type == UserStatus.SECT_TASK and user_cd.scheduled_time and current_time < user_cd.scheduled_time:
            return False, f"❌ 宗门任务冷却中！还需 {(user_cd.scheduled_time - current_time)//60} 分钟。"
        elif user_cd.type == UserStatus.SECT_TASK:
            await self.db.ext.set_user_free(user_id)

        await self.db.ext.set_user_busy(user_id, UserStatus.SECT_TASK, current_time + 3600)
        return True, "✨ 你开始执行宗门任务！任务需要1小时完成，请在完成后使用 /完成宗门任务 领取奖励。"

    async def finish_sect_task(self, user_id: str) -> Tuple[bool, str]:
        """完成宗门任务"""
        player = await self.db.get_player_by_id(user_id)
        if not player or player.sect_id == 0: return False, "❌ 你还未加入宗门！"

        user_cd = await self.db.ext.get_user_cd(user_id)
        if not user_cd: return False, "❌ 你当前不在宗门任务中！"

        if user_cd.type == UserStatus.SECT_TASK:
            now = int(time.time())
            if user_cd.scheduled_time and now < user_cd.scheduled_time:
                return False, f"❌ 宗门任务尚未完成！还需 {(user_cd.scheduled_time - now)//60} 分。"

            contribution_gain = random.randint(10, 30)

            # 演武场：宗门建筑，宗门任务奖励+10%/级
            arena_note = ""
            try:
                levels = self.get_buildings(sect) if (sect := await self.db.ext.get_sect_by_id(player.sect_id)) else {}
                arena_lv = int(levels.get("演武场", 0))
                if arena_lv > 0:
                    contribution_gain = int(contribution_gain * (1 + 0.10 * arena_lv))
                    arena_note = f"\n🏟️ 演武场 Lv.{arena_lv} 生效：奖励+{10 * arena_lv}%"
            except Exception:
                pass

            player.sect_contribution += contribution_gain
            await self.db.update_player(player)

            if sect:
                sect.sect_materials += contribution_gain * 10
                await self.db.ext.update_sect(sect)

            await self.db.ext.set_user_free(user_id)
            return True, f"✨ 宗门任务完成！\n获得贡献：{contribution_gain}\n宗门资材：+{contribution_gain * 10}{arena_note}"
        else:
            await self.db.ext.set_user_free(user_id)
            return True, "✅ 状态异常已修复！你的状态已恢复正常。"

    async def handle_owner_death(self, sect_id: int, dead_owner_id: str) -> Tuple[bool, str]:
        """处理宗主死亡，自动传位或解散宗门"""
        members = await self.db.ext.get_sect_members(sect_id)
        remaining = [m for m in members if m.user_id != dead_owner_id]
        
        if not remaining:
            await self.db.ext.delete_sect(sect_id)
            return True, "宗门已解散"
        
        remaining.sort(key=lambda m: (m.sect_position, -m.sect_contribution))
        new_owner = remaining[0]
        
        sect = await self.db.ext.get_sect_by_id(sect_id)
        if sect:
            sect.sect_owner = new_owner.user_id
            await self.db.ext.update_sect(sect)
            await self.db.ext.update_player_sect_info(new_owner.user_id, sect_id, 0)
        
        return True, f"宗主之位已传给{new_owner.user_name or new_owner.user_id}"

    # ===== v6.6 宗门大比 =====
    async def start_sect_battle(self) -> Tuple[bool, str]:
        """开启宗门大比"""
        is_active = await self.db.ext.get_system_config("sect_battle_active")
        if is_active == "1":
            return False, "❌ 宗门大比正在进行中。"
        await self.db.ext.set_system_config("sect_battle_active", "1")
        return True, "⚔️ 宗门大比正式开启！所有修士可通过 /大比切磋 @某人 争夺荣誉！"

    async def end_sect_battle(self) -> Tuple[bool, str]:
        """结束宗门大比并结算"""
        is_active = await self.db.ext.get_system_config("sect_battle_active")
        if is_active != "1":
            return False, "❌ 当前没有进行中的大比。"
        await self.db.ext.set_system_config("sect_battle_active", "0")
        return True, "🏁 宗门大比结束！天道压制解除，全服已恢复正常状态。"

    async def record_battle_result(self, user_id: str, is_winner: bool = True) -> str:
        """记录大比结果，胜利者发称号，失败/平局发保底"""
        player = await self.db.get_player_by_id(user_id)
        if not player or player.sect_id == 0:
            return ""
        
        title_msg = ""
        
        if is_winner:
            # ===== 胜者逻辑 =====
            win_key = f"sect_battle_wins_{user_id}"
            current_wins_str = await self.db.ext.get_system_config(win_key)
            current_wins = int(current_wins_str) if current_wins_str and current_wins_str.isdigit() else 0
            current_wins += 1
            await self.db.ext.set_system_config(win_key, str(current_wins))

            if current_wins == 1 and not player.title:
                player.title = "初露锋芒"
                title_msg = "\n👑 恭喜你！赢得大比首胜，获得荣誉称号【初露锋芒】！"
            elif current_wins >= 3 and player.title not in ["一代宗师", "灭世魔神"]:
                player.title = "一代宗师"
                title_msg = "\n👑 恭喜你！累计胜场达到 3 场，获得荣誉称号【一代宗师】！"

            player.sect_contribution += 100
            # 给宗门加积分
            score_key = f"sect_score_{player.sect_id}"
            current_score = await self.db.ext.get_system_config(score_key)
            new_score = int(current_score) + 10 if current_score else 10
            await self.db.ext.set_system_config(score_key, str(new_score))
            
            await self.db.update_player(player)
            return f"\n🏅 你为大比赢得一场胜利！宗门贡献+100，宗门积分+10。{title_msg}"
            
        else:
            # ===== 败者/平局保底逻辑 =====
            player.sect_contribution += 20
            score_key = f"sect_score_{player.sect_id}"
            current_score = await self.db.ext.get_system_config(score_key)
            new_score = int(current_score) + 2 if current_score else 2
            await self.db.ext.set_system_config(score_key, str(new_score))
            
            await self.db.update_player(player)
            return "" # 败者不弹额外提示，避免刷屏