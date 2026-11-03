# handlers/sect_handlers.py
import time
from astrbot.api.event import AstrMessageEvent
from astrbot.api.all import At
from ..managers.sect_manager import SectManager
from ..data.data_manager import DataBase
from ..models_extended import UserStatus

class SectHandlers:
    def __init__(self, db: DataBase, sect_mgr: SectManager, config_manager=None):
        self.db = db
        self.sect_mgr = sect_mgr
        # v3.25.5 修复：EquipmentManager 需要真正的 ConfigManager（sect_mgr.config 只是 dict，
        # 传入后会因缺少 techniques_data 等属性导致装备玩家大比切磋必崩）
        self.config_manager = config_manager

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

        # 职位范围校验（0宗主 1副宗主 2长老 3内门 4外门）
        if position < 0 or position > 4:
            yield event.plain_result("❌ 职位编号需为 0-4（0宗主 1副宗主 2长老 3内门 4外门）。")
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
        # v3.25.5：预检仅作提示（真正的原子占坑在进入战斗前执行）
        count = await self.db.ext.syscfg_get_number(daily_key)
        if count >= 3:
            yield event.plain_result("❌ 你今日的大比切磋次数已达上限（3次），请明日再来。")
            return

        # 动态导入，防止循环依赖
        from ..managers.combat_manager import CombatManager, CombatStats
        from ..core import EquipmentManager
        from ..managers.pet_manager import PetManager
        
        cm = CombatManager()
        em = EquipmentManager(self.db, self.config_manager)
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
                               exp=p.experience,
                               element=(cm.get_element_from_name(p.main_technique) or cm.get_element_from_name(p.weapon)))

        p1_stats = await get_stats(user_id)
        p2_stats = await get_stats(target_id)

        if not p1_stats or not p2_stats:
            yield event.plain_result("❌ 双方都必须是已踏入仙途的修士。")
            return

        # ===== v6.16 盲选换职业（大比特色）：发起者可带参数盲选职业，战斗以所选职业倍率计算 =====
        # 用法：/大比切磋 @人 剑 —— 双方均按盲选职业倍率重算攻击（被克方无感知，是"盲"选）
        CLASS_MULT = {"剑修": 1.5, "魔修": 1.3, "佛修": 0.6}
        note_msg = ""
        picked = (target or "").strip()
        if picked in ("剑修", "剑", "魔修", "魔", "佛修", "佛"):
            picked = {"剑": "剑修", "魔": "魔修", "佛": "佛修"}.get(picked, picked)
            base1 = cm.calculate_atk(p1_stats.exp, 0, 0, 0, 0, "灵修")
            base2 = cm.calculate_atk(p2_stats.exp, 0, 0, 0, 0, "灵修")
            p1_stats.atk = int(base1 * CLASS_MULT.get(picked, 1.0)) + 300
            p2_stats.atk = int(base2 * 1.0) + 300  # 防守方不盲选，保持常倍
            note_msg = f"\n🎯 你盲选了【{picked}】出战！（对方不知情，攻击倍率已按 {picked} 计算）"
            # 注：原此处有一段"换命符"半成品死代码（创建 StorageRingManager 后从未使用，
            # 且传入 dict 当 ConfigManager 会踩类型坑）。经查【换命符】并不存在于任何物品
            # 配置中，功能永远无法触发，已移除。若日后在 config/items.json 上架该物品，
            # 可在此实现"防守方携带换命符自动消耗、攻击倍率与盲选方持平"的反埋伏机制。

        # 扣除次数与记录冷却（进入战斗才扣除）
        # v3.25.5：次数改原子限次认领（原 read-then-write 在并发连发下可刷爆 3 次/日）
        if not await self.db.ext.syscfg_claim_slot(daily_key, 3):
            yield event.plain_result("❌ 你今日的大比切磋次数已达上限（3次），请明日再来。")
            return
        await self.db.ext.set_system_config(cooldown_key, str(now))

        # 进行天道压制战斗
        result = cm.player_vs_player_balanced(p1_stats, p2_stats)
        log = "\n".join(result['combat_log'])
        if note_msg:
            log = note_msg + "\n\n" + log
        
         # ===== 核心修复：参与即有奖 =====
        if result["winner"] == user_id:
            # 挑战者胜
            try:
                from ..managers.title_hooks import TitleHooks
                # v3.25.5 修复：bump 需要 Player 对象，原代码传入 CombatStats 导致称号永不发放
                p1_real = await self.db.get_player_by_id(user_id)
                tmsg = await TitleHooks(self.db).bump(p1_real, "sect_battle_win") if p1_real else ""
                if tmsg: extra_pre = tmsg
                else: extra_pre = ""
            except Exception:
                extra_pre = ""
            extra_msg = extra_pre + await self.sect_mgr.record_battle_result(user_id, is_winner=True)
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