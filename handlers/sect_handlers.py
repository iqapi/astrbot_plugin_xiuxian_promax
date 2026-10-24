# handlers/sect_handlers.py
import time
from astrbot.api.event import AstrMessageEvent
from astrbot.api.all import At
from ..managers.sect_manager import SectManager
from ..data.data_manager import DataBase
from ..models_extended import UserStatus

class SectHandlers:
    def __init__(self, db: DataBase, sect_mgr: SectManager):
        self.db = db
        self.sect_mgr = sect_mgr

    async def handle_create_sect(self, event: AstrMessageEvent, name: str):
        """创建宗门"""
        user_id = event.get_sender_id()
        user_cd = await self.db.ext.get_user_cd(user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            current_status = UserStatus.get_name(user_cd.type)
            yield event.plain_result(f"❌ 你当前正{current_status}，无法进行此操作！")
            return
        success, msg = await self.sect_mgr.create_sect(user_id, name)
        yield event.plain_result(msg)

    async def handle_join_sect(self, event: AstrMessageEvent, name: str):
        """加入宗门"""
        user_id = event.get_sender_id()
        user_cd = await self.db.ext.get_user_cd(user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            current_status = UserStatus.get_name(user_cd.type)
            yield event.plain_result(f"❌ 你当前正{current_status}，无法进行此操作！")
            return
        success, msg = await self.sect_mgr.join_sect(user_id, name)
        yield event.plain_result(msg)
    
    async def handle_leave_sect(self, event: AstrMessageEvent):
        """退出宗门"""
        user_id = event.get_sender_id()
        user_cd = await self.db.ext.get_user_cd(user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            current_status = UserStatus.get_name(user_cd.type)
            yield event.plain_result(f"❌ 你当前正{current_status}，无法进行此操作！")
            return
        success, msg = await self.sect_mgr.leave_sect(user_id)
        yield event.plain_result(msg)

    async def handle_my_sect(self, event: AstrMessageEvent):
        """我的宗门"""
        user_id = event.get_sender_id()
        success, msg, _ = await self.sect_mgr.get_sect_info(user_id)
        yield event.plain_result(msg)
    
    async def handle_sect_list(self, event: AstrMessageEvent):
        """宗门列表"""
        success, msg = await self.sect_mgr.list_all_sects()
        yield event.plain_result(msg)
    
    async def handle_donate(self, event: AstrMessageEvent, amount: int):
        """宗门捐献"""
        user_id = event.get_sender_id()
        user_cd = await self.db.ext.get_user_cd(user_id)
        if user_cd and user_cd.type != UserStatus.IDLE:
            current_status = UserStatus.get_name(user_cd.type)
            yield event.plain_result(f"❌ 你当前正{current_status}，无法进行此操作！")
            return
        success, msg = await self.sect_mgr.donate_to_sect(user_id, amount)
        yield event.plain_result(msg)
        
    async def handle_kick_member(self, event: AstrMessageEvent, target: str):
        """踢出宗门成员"""
        user_id = event.get_sender_id()
        target_id = None
        for component in event.message_obj.message:
            if isinstance(component, At):
                target_id = str(component.qq)
                break
        
        if not target_id:
            if target.isdigit(): target_id = target
        
        if not target_id:
            yield event.plain_result("❌ 请指定要踢出的成员（At或输入ID）")
            return

        success, msg = await self.sect_mgr.kick_member(user_id, target_id)
        yield event.plain_result(msg)

    async def handle_transfer(self, event: AstrMessageEvent, target: str):
        """宗主传位"""
        user_id = event.get_sender_id()
        target_id = None
        for component in event.message_obj.message:
            if isinstance(component, At):
                target_id = str(component.qq)
                break
        
        if not target_id and target.isdigit():
             target_id = target
             
        if not target_id:
            yield event.plain_result("❌ 请指定传位目标（At或输入ID）")
            return

        success, msg = await self.sect_mgr.transfer_ownership(user_id, target_id)
        yield event.plain_result(msg)

    async def handle_position_change(self, event: AstrMessageEvent, target: str, position: int):
        """职位变更"""
        user_id = event.get_sender_id()
        target_id = None
        for component in event.message_obj.message:
            if isinstance(component, At):
                target_id = str(component.qq)
                break
        
        if not target_id and target.isdigit():
             target_id = target
             
        if not target_id:
            yield event.plain_result("❌ 请指定目标（At或输入ID）")
            return

        success, msg = await self.sect_mgr.change_position(user_id, target_id, position)
        yield event.plain_result(msg)

    async def handle_sect_task(self, event: AstrMessageEvent):
        """执行宗门任务"""
        user_id = event.get_sender_id()
        success, msg = await self.sect_mgr.perform_sect_task(user_id)
        yield event.plain_result(msg)

    async def handle_finish_sect_task(self, event: AstrMessageEvent):
        """完成宗门任务（解决卡住的情况）"""
        user_id = event.get_sender_id()
        success, msg = await self.sect_mgr.finish_sect_task(user_id)
        yield event.plain_result(msg)

    async def handle_sect_battle(self, event: AstrMessageEvent, target: str = ""):
        """宗门大比切磋（受天道压制 + 限制次数与冷却）"""
        user_id = event.get_sender_id()
        is_active = await self.db.ext.get_system_config("sect_battle_active")
        if is_active != "1":
            yield event.plain_result("❌ 当前没有宗门大比活动。")
            return
            
        target_id = None
        for component in event.message_obj.message:
            if isinstance(component, At):
                target_id = str(component.qq)
                break
        if not target_id and target.strip().lstrip("@").isdigit():
            target_id = target.strip().lstrip("@")

        if not target_id or target_id == user_id:
            yield event.plain_result("❌ 请使用 @某人 指定你的对手，且不能挑战自己。")
            return

        # ===== 核心修复 1：检查冷却时间 (5分钟) =====
        now = int(time.time())
        cooldown_key = f"sect_battle_cd_{user_id}"
        last_time_str = await self.db.ext.get_system_config(cooldown_key)
        if last_time_str and last_time_str.isdigit():
            last_time = int(last_time_str)
            if now - last_time < 300:
                remain = 300 - (now - last_time)
                yield event.plain_result(f"❌ 大比调息中，请 {remain // 60} 分 {remain % 60} 秒后再战。")
                return
        
        # ===== 核心修复 2：检查每日挑战次数上限 (3次) =====
        today_str = time.strftime('%Y-%m-%d')
        daily_key = f"sect_battle_daily_{user_id}_{today_str}"
        count_str = await self.db.ext.get_system_config(daily_key)
        count = int(count_str) if count_str and count_str.isdigit() else 0
        if count >= 3:
            yield event.plain_result("❌ 你今日的大比切磋次数已达上限（3次），请明日再来。")
            return

        # 动态导入，防止循环依赖
        from ..managers.combat_manager import CombatManager, CombatStats
        from ..core import EquipmentManager
        from ..managers.pet_manager import PetManager
        
        cm = CombatManager()
        em = EquipmentManager(self.db, self.sect_mgr.config)
        pet_mgr = PetManager(self.db)
        
        async def get_stats(uid):
            p = await self.db.get_player_by_id(uid)
            if not p: return None
            hp, mp = cm.calculate_hp_mp(p.experience)
            atk = cm.calculate_atk(p.experience, p.atkpractice, 0, p.physical_damage, p.magic_damage, p.cultivation_type)
            effects = em.get_combat_effects(p)
            pet = await pet_mgr.get_pet(uid)
            if pet:
                pet_eff = pet_mgr.get_pet_combat_effects(pet)
                for k, v in pet_eff.items(): effects[k] = effects.get(k, 0) + v
            return CombatStats(user_id=uid, name=p.user_name or uid, hp=hp, max_hp=hp, mp=mp, max_mp=mp, atk=atk, effects=effects,
                               element=(cm.get_element_from_name(p.main_technique) or cm.get_element_from_name(p.weapon)))

        p1_stats = await get_stats(user_id)
        p2_stats = await get_stats(target_id)
        
        if not p1_stats or not p2_stats:
            yield event.plain_result("❌ 双方都必须是已踏入仙途的修士。")
            return

        # 扣除次数与记录冷却（进入战斗才扣除）
        await self.db.ext.set_system_config(cooldown_key, str(now))
        await self.db.ext.set_system_config(daily_key, str(count + 1))

        # 进行天道压制战斗
        result = cm.player_vs_player_balanced(p1_stats, p2_stats)
        log = "\n".join(result['combat_log'])
        
         # ===== 核心修复：参与即有奖 =====
        if result["winner"] == user_id:
            # 挑战者胜
            extra_msg = await self.sect_mgr.record_battle_result(user_id, is_winner=True)
            await self.sect_mgr.record_battle_result(target_id, is_winner=False) # 败者保底
            yield event.plain_result(f"{log}\n\n🏆 你赢下了这场大比！{extra_msg}\n(今日剩余次数：{3 - (count + 1)})")
            
        elif result["winner"] == target_id:
            # 被挑战者胜
            extra_msg = await self.sect_mgr.record_battle_result(target_id, is_winner=True)
            await self.sect_mgr.record_battle_result(user_id, is_winner=False) # 败者保底
            yield event.plain_result(f"{log}\n\n💀 你输掉了这场大比...对方获得了荣誉。\n(今日剩余次数：{3 - (count + 1)})")
            
        else:
            # 平局
            await self.sect_mgr.record_battle_result(user_id, is_winner=False)
            await self.sect_mgr.record_battle_result(target_id, is_winner=False)
            yield event.plain_result(f"{log}\n\n⚖️ 平局！双方各获得一份参与奖。\n(今日剩余次数：{3 - (count + 1)})")