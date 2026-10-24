# managers/impart_pk_manager.py
"""传承PK系统管理器"""
import random
from typing import Tuple
from ..data import DataBase
from ..models import Player
from .combat_manager import CombatManager
from .combat_manager import CombatStats

__all__ = ["ImpartPkManager"]


class ImpartPkManager:
    """传承PK管理器 - 玩家间争夺传承的战斗"""
    
    def __init__(self, db: DataBase, combat_mgr: CombatManager):
        self.db = db
        self.combat_mgr = combat_mgr
    
    async def challenge_impart(self, attacker: Player, defender: Player) -> Tuple[bool, str, dict]:
        """发起传承挑战
        
        Args:
            attacker: 挑战者
            defender: 被挑战者
            
        Returns:
            (attacker_wins, battle_log, rewards)
        """
        # 获取双方传承等级
        attacker_impart = await self.db.ext.get_impart_info(attacker.user_id)
        defender_impart = await self.db.ext.get_impart_info(defender.user_id)
        
        # 准备战斗属性
        atk_hp, atk_mp = self.combat_mgr.calculate_hp_mp(attacker.experience)
        atk_atk = self.combat_mgr.calculate_atk(attacker.experience, attacker.atkpractice)
        atk_stats = CombatStats(
            user_id=attacker.user_id, name=attacker.user_name or "挑战者",
            hp=atk_hp, max_hp=atk_hp, mp=atk_mp, max_mp=atk_mp, atk=atk_atk
        )
        
        def_hp, def_mp = self.combat_mgr.calculate_hp_mp(defender.experience)
        def_atk = self.combat_mgr.calculate_atk(defender.experience, defender.atkpractice)
        def_stats = CombatStats(
            user_id=defender.user_id, name=defender.user_name or "防守者",
            hp=def_hp, max_hp=def_hp, mp=def_mp, max_mp=def_mp, atk=def_atk
        )
        
        # 战斗模拟
        atk_hp = atk_stats.hp
        def_hp = def_stats.hp
        
        rounds = 0
        max_rounds = 20
        battle_log = []
        
        while atk_hp > 0 and def_hp > 0 and rounds < max_rounds:
            rounds += 1
            
            # 攻击者出手
            damage = max(1, atk_stats.atk - def_stats.defense // 2)
            damage = int(damage * random.uniform(0.8, 1.2))
            def_hp -= damage
            battle_log.append(f"第{rounds}回合: {attacker.user_name or attacker.user_id} 造成 {damage} 伤害")
            
            if def_hp <= 0:
                break
            
            # 防守者反击
            counter_damage = max(1, def_stats.atk - atk_stats.defense // 2)
            counter_damage = int(counter_damage * random.uniform(0.8, 1.2))
            atk_hp -= counter_damage
            battle_log.append(f"第{rounds}回合: {defender.user_name or defender.user_id} 反击 {counter_damage}")
        
        # 判定胜负
        attacker_wins = def_hp <= 0 or (atk_hp > 0 and atk_hp >= def_hp)
        
        rewards = {}
        if attacker_wins:
            # 胜利奖励：获得传承加成
            impart_gain = random.uniform(0.01, 0.05)  # 1%-5%
            if attacker_impart:
                new_atk_per = min(1.0, attacker_impart.impart_atk_per + impart_gain)
                attacker_impart.impart_atk_per = new_atk_per
                await self.db.ext.update_impart_info(attacker_impart)
                rewards["impart_atk_gain"] = impart_gain
            
            # 失败惩罚
            if defender_impart and defender_impart.impart_atk_per > 0:
                loss = min(impart_gain / 2, defender_impart.impart_atk_per)
                defender_impart.impart_atk_per -= loss
                await self.db.ext.update_impart_info(defender_impart)
                rewards["defender_loss"] = loss
        else:
            # 失败惩罚：损失修为
            exp_loss = int(attacker.experience * 0.01)  # 1%
            attacker.experience = max(0, attacker.experience - exp_loss)
            await self.db.update_player(attacker)
            rewards["exp_loss"] = exp_loss
        
        return attacker_wins, "\n".join(battle_log[-6:]), rewards  # 只返回最后6条log
    
    async def get_impart_ranking(self, limit: int = 10) -> list:
        """获取传承排行榜"""
        # 查询所有传承数据，按攻击加成排序
        async with self.db.conn.execute(
            """
            SELECT user_id, impart_hp_per, impart_mp_per, impart_atk_per, 
                   impart_know_per, impart_burst_per
            FROM impart_info 
            ORDER BY impart_atk_per DESC 
            LIMIT ?
            """,
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                user_id = row[0]
                player = await self.db.get_player_by_id(user_id)
                if player:
                    total_per = row[1] + row[2] + row[3] + row[4] + row[5]
                    results.append({
                        "user_id": user_id,
                        "user_name": player.user_name or user_id[:8],
                        "atk_per": row[3],
                        "total_per": total_per
                    })
            return results
