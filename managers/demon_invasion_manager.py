# managers/demon_invasion_manager.py
import json
import random
import time
from typing import Tuple
from ..data import DataBase
from ..models import Player

class DemonInvasionManager:
    """天魔入侵管理器"""
    
    def __init__(self, db: DataBase):
        self.db = db

    async def start_invasion(self, duration_hours: int = 24) -> Tuple[bool, str]:
        """开启天魔入侵"""
        is_active = await self.db.ext.get_system_config("demon_invasion_active")
        if is_active == "1":
            return False, "❌ 当前已有天魔入侵正在进行中。"
            
        # 获取全服所有玩家
        players = await self.db.get_all_players()
        
        # 核心判定：参与人数必须达到 10 人及以上
        if len(players) < 10:
            return False, f"❌ 开启失败！当前全服修仙者仅有 {len(players)} 人。\n(天魔入侵至少需要 10 名修士参与才能开启)"
            
        # 随机抽取 1~2 名天魔 (10-15人抽1个，16人以上抽2个)
        demon_count = 1 if len(players) < 16 else 2
        demons = random.sample(players, demon_count)
        demon_ids = [p.user_id for p in demons]
        
        now = int(time.time())
        end_time = now + duration_hours * 3600
        
        await self.db.ext.set_system_config("demon_invasion_active", "1")
        await self.db.ext.set_system_config("demon_invasion_end_time", str(end_time))
        await self.db.ext.set_system_config("demon_invasion_list", json.dumps(demon_ids))
        
        return True, f"天魔已降临！{demon_count}名修士被附体。活动时长：{duration_hours}小时。"

    async def end_invasion(self) -> Tuple[bool, str]:
        """结束天魔入侵（结算）"""
        is_active = await self.db.ext.get_system_config("demon_invasion_active")
        if is_active != "1":
            return False, "❌ 当前没有正在进行的活动。"
            
        demon_list_str = await self.db.ext.get_system_config("demon_invasion_list")
        demon_ids = json.loads(demon_list_str) if demon_list_str else []
        
        await self.db.ext.set_system_config("demon_invasion_active", "0")
        await self.db.ext.set_system_config("demon_invasion_list", "[]")
        
        if not demon_ids:
            return True, "天魔入侵已结束。"
            
        # 给天魔发奖
        for uid in demon_ids:
            p = await self.db.get_player_by_id(uid)
            if p:
                p.gold += 50000
                await self.db.update_player(p)
                
        # ===== 修复点：给予所有参与过活动的普通玩家安慰奖 =====
        all_players = await self.db.get_all_players()
        for p in all_players:
            if p.user_id not in demon_ids:
                p.gold += 5000
                await self.db.update_player(p)
        # =========================================================
                
        return True, f"🌑 天魔入侵结束！天魔潜伏成功（共 {len(demon_ids)} 人），每人获得丰厚奖励。\n全服正道修士获得 5000 灵石安慰奖。"

    async def catch_demon(self, player: Player, target_id: str, storage_ring_mgr) -> Tuple[bool, str]:
        """查验并捉拿天魔"""
        is_active = await self.db.ext.get_system_config("demon_invasion_active")
        if is_active != "1":
            return False, "❌ 当前没有进行天魔入侵。"
            
        if not storage_ring_mgr.has_item(player, "照妖镜", 1):
            return False, "❌ 你没有【照妖镜】，无法查验。"
            
        await storage_ring_mgr.retrieve_item(player, "照妖镜", 1)
        
        demon_list_str = await self.db.ext.get_system_config("demon_invasion_list")
        demon_ids = json.loads(demon_list_str) if demon_list_str else []
        
        if target_id in demon_ids:
            # 抓到了！
            demon_ids.remove(target_id)
            
            # 给抓妖人发奖
            player.gold += 30000
            await self.db.update_player(player)
            
            # 给被捉的天魔惩罚（扣修为）
            target_p = await self.db.get_player_by_id(target_id)
            if target_p:
                target_p.experience = int(target_p.experience * 0.8)
                await self.db.update_player(target_p)
                
            if not demon_ids:
                await self.db.ext.set_system_config("demon_invasion_active", "0")
                await self.db.ext.set_system_config("demon_invasion_list", "[]")
                return True, "🎉 天地震动！你一语道破天机，【最后一名天魔】被你成功揪出！天魔入侵彻底结束！你获得了 30,000 灵石奖励。"
                
            await self.db.ext.set_system_config("demon_invasion_list", json.dumps(demon_ids))
            return True, "🔔 降妖除魔！你成功查验出对方是【天魔】！对方修为受损，你获得了 30,000 灵石奖励。但似乎还有天魔潜伏..."
        else:
            # 抓错了，被反噬
            player.hp = max(1, int(player.hp * 0.5))
            await self.db.update_player(player)
            return False, "💥 查验失败！对方是清清白白的正道修士。你遭到天道反噬，气血减半，照妖镜碎裂。"