# managers/combat_manager.py
"""
战斗系统管理器 - 处理HP/MP/ATK系统和战斗逻辑
"""

import random
from typing import Tuple, Dict, Optional, List
from dataclasses import dataclass

@dataclass
class CombatStats:
    """战斗属性"""
    user_id: str
    name: str  # 道号
    hp: int  # 当前气血
    max_hp: int  # 最大气血
    mp: int  # 当前真元值
    max_mp: int  # 最大真元值
    atk: int  # 攻击力
    defense: int = 0  # 防御力
    crit_rate: int = 0  # 会心率（百分比）
    exp: int = 0  # 修为（用于计算攻击力）
    effects: dict = None # 战斗特效（功法/词条/灵兽）
    element: str = ""  # 五行属性（金木水火土，空为无属性）


class CombatManager:
    """战斗系统管理器"""

    # 五行相生相克：key 克 value（金克木、木克土、土克水、水克火、火克金）
    ELEMENT_OVERCOMES = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}
    ELEMENT_ADVANTAGE_MULT = 1.3   # 克制方伤害 +30%
    ELEMENT_DISADVANTAGE_MULT = 0.8 # 被克制方伤害 -20%

    @staticmethod
    def get_element_from_name(name: str) -> str:
        """从功法/心法/武器名称中推断五行属性（金木水火土）"""
        if not name:
            return ""
        for e in ("金", "木", "水", "火", "土"):
            if e in name:
                return e
        return ""

    @classmethod
    def element_multiplier(cls, attacker_element: str, defender_element: str) -> float:
        """计算五行克制伤害倍率"""
        if not attacker_element or not defender_element:
            return 1.0
        if cls.ELEMENT_OVERCOMES.get(attacker_element) == defender_element:
            return cls.ELEMENT_ADVANTAGE_MULT
        if cls.ELEMENT_OVERCOMES.get(defender_element) == attacker_element:
            return cls.ELEMENT_DISADVANTAGE_MULT
        return 1.0
    
    @staticmethod
    def calculate_hp_mp(experience: int, hp_buff: float = 0.0, mp_buff: float = 0.0) -> Tuple[int, int]:
        """根据修为计算HP和MP"""
        base_hp = experience // 2
        base_mp = experience
        
        hp = int(base_hp * (1 + hp_buff))
        mp = int(base_mp * (1 + mp_buff))
        
        return hp, mp
    
    @staticmethod
    def calculate_atk(experience: int, atkpractice: int = 0, atk_buff: float = 0.0, physical_damage: int = 0, magic_damage: int = 0, cultivation_type: str = "灵修") -> int:
        """根据修为、攻击修炼等级和物伤/法伤计算攻击力（加入了职业分化）"""
        base_atk = experience // 10
        practice_bonus = atkpractice * 0.04  # 每级4%加成
        
        # 职业专属攻击加成
        class_multiplier = 1.0
        if cultivation_type == "剑修":
            class_multiplier = 1.5 # 剑修伤害提升 50%
        elif cultivation_type == "魔修":
            class_multiplier = 1.3 # 魔修伤害提升 30%
        elif cultivation_type == "佛修":
            class_multiplier = 0.6 # 佛修伤害降低 40%
            
        total_atk = int(base_atk * (1 + practice_bonus + atk_buff) * class_multiplier) + physical_damage + magic_damage
        
        return max(total_atk, 1)  # 至少为1
    
    @staticmethod
    def apply_damage_reduction(damage: int, defense: int = 0) -> int:
        """应用伤害减免（使用递减公式）"""
        if defense <= 0:
            return damage
        reduction_rate = defense / (defense + 100)
        final_damage = int(damage * (1 - reduction_rate))
        return max(1, final_damage)
    
    @classmethod
    def _execute_attack(cls, attacker: CombatStats, defender: CombatStats) -> Tuple[int, List[str], int]:
        """执行一次攻击，返回 (最终伤害, 战斗日志列表, 吸血量)"""
        logs = []
        effects = attacker.effects or {}
        
        # 1. 基础伤害
        damage = int(round(random.uniform(0.95, 1.05), 2) * attacker.atk)

        # 1.5 五行克制倍率（克制+30%，被克-20%）
        elem_mult = cls.element_multiplier(attacker.element, defender.element)
        if elem_mult != 1.0:
            damage = int(damage * elem_mult)
        
        # 2. 暴击判定
        base_crit = attacker.crit_rate
        bonus_crit = effects.get("crit_rate", 0)
        is_crit = random.randint(0, 100) <= (base_crit + bonus_crit)
        
        if is_crit:
            crit_mult = effects.get("crit_damage", 1.5)
            damage = int(damage * crit_mult)
            logs.append(f"💥 {attacker.name} 触发会心一击！")
            
        # 3. 连击/追加伤害判定
        combo_rate = effects.get("combo_rate", 0)
        if random.randint(0, 100) <= combo_rate:
            extra_dmg = int(damage * 0.5)
            damage += extra_dmg
            logs.append(f"⚡ {attacker.name} 触发功法连击，追加 {extra_dmg} 伤害！")
            
        # 4. 防御减伤
        final_damage = cls.apply_damage_reduction(damage, defender.defense)
        
        # 5. 吸血计算
        lifesteal_percent = effects.get("lifesteal", 0)
        heal_amount = 0
        if lifesteal_percent > 0:
            heal_amount = int(final_damage * (lifesteal_percent / 100))
            if heal_amount > 0:
                logs.append(f"🩸 {attacker.name} 吸取了 {heal_amount} 点气血！")
                
        logs.append(f"🗡️ {attacker.name} 造成 {final_damage} 点伤害")
        
        # 6. ===== 灵兽协战判定 =====
        pet_damage_mult = effects.get("pet_damage_mult", 0)
        if pet_damage_mult > 0:
            pet_damage = int(attacker.atk * pet_damage_mult)
            pet_damage = cls.apply_damage_reduction(pet_damage, defender.defense)
            final_damage += pet_damage
            logs.append(f"🐾 {attacker.name} 的灵兽发起协同攻击，造成额外 {pet_damage} 点伤害！")
        # ==========================

        return final_damage, logs, heal_amount

    @classmethod
    def player_vs_player(cls, player1: CombatStats, player2: CombatStats, combat_type: int = 1) -> Dict:
        """玩家vs玩家战斗"""
        combat_log = [f"☆━━━━ 战斗开始 ━━━━☆", f"{player1.name} VS {player2.name}"]
        round_num = 0
        max_rounds = 100
        
        while player1.hp > 0 and player2.hp > 0 and round_num < max_rounds:
            round_num += 1
            combat_log.append(f"-- 第 {round_num} 回合 --")
            
            # 玩家1攻击
            dmg1, logs1, heal1 = cls._execute_attack(player1, player2)
            player2.hp -= dmg1
            player1.hp = min(player1.max_hp, player1.hp + heal1)
            combat_log.extend(logs1)
            combat_log.append(f"{player2.name} 剩余 HP: {max(0, player2.hp)}")
            
            # 反伤判定（针对玩家2的功法）
            counter = (player2.effects or {}).get("counter_damage", 0)
            if counter > 0:
                reflect_dmg = int(dmg1 * (counter / 100))
                player1.hp -= reflect_dmg
                combat_log.append(f"🛡️ {player2.name} 触发反伤，反弹 {reflect_dmg} 点伤害！")
                combat_log.append(f"{player1.name} 剩余 HP: {max(0, player1.hp)}")
            
            if player2.hp <= 0 or player1.hp <= 0: break
            
            # 玩家2攻击
            dmg2, logs2, heal2 = cls._execute_attack(player2, player1)
            player1.hp -= dmg2
            player2.hp = min(player2.max_hp, player2.hp + heal2)
            combat_log.extend(logs2)
            combat_log.append(f"{player1.name} 剩余 HP: {max(0, player1.hp)}")
            
            # 反伤判定（针对玩家1的功法）
            counter1 = (player1.effects or {}).get("counter_damage", 0)
            if counter1 > 0:
                reflect_dmg = int(dmg2 * (counter1 / 100))
                player2.hp -= reflect_dmg
                combat_log.append(f"🛡️ {player1.name} 触发反伤，反弹 {reflect_dmg} 点伤害！")
                combat_log.append(f"{player2.name} 剩余 HP: {max(0, player2.hp)}")
                
            combat_log.append("")
        
        if player1.hp > 0: winner = player1.user_id
        elif player2.hp > 0: winner = player2.user_id
        else: winner = "平局"
        
        if combat_type == 1:
            p1_hp, p2_hp = player1.max_hp, player2.max_hp
        else:
            p1_hp = max(1, player1.hp) if player1.hp > 0 else 1
            p2_hp = max(1, player2.hp) if player2.hp > 0 else 1
            
        return {
            "winner": winner, "combat_log": combat_log, "rounds": round_num,
            "player1_final_hp": p1_hp, "player1_final_mp": player1.mp,
            "player2_final_hp": p2_hp, "player2_final_mp": player2.mp
        }

    @classmethod
    def player_vs_player_balanced(cls, player1: CombatStats, player2: CombatStats) -> Dict:
        """天道压制 PVP（强制拉平基础属性）"""
        p1_orig_hp, p1_orig_atk = player1.hp, player1.atk
        p2_orig_hp, p2_orig_atk = player2.hp, player2.atk
        
        # 强制拉平基础属性 (HP 锁定 10000)
        player1.hp = player1.max_hp = 10000
        player2.hp = player2.max_hp = 10000
        
        # 攻击力压制 (基础500，并且只保留原装备/词条 20% 的纯附加值优势)
        p1_atk_bonus = max(0, p1_orig_atk - (p1_orig_hp * 0.1))
        player1.atk = 500 + int(p1_atk_bonus * 0.2)
        
        p2_atk_bonus = max(0, p2_orig_atk - (p2_orig_hp * 0.1))
        player2.atk = 500 + int(p2_atk_bonus * 0.2)
        
        # 双方防御力也拉平
        player1.defense = 100
        player2.defense = 100
        
        combat_log = [
            f"⚖️ 【天道压制】双方基础属性已被强制拉平！",
            f"（但保留了功法、装备、灵兽的特殊加成）",
            f"{player1.name} (ATK {player1.atk}) VS {player2.name} (ATK {player2.atk})",
            ""
        ]
        
        round_num = 0
        while player1.hp > 0 and player2.hp > 0 and round_num < 100:
            round_num += 1
            combat_log.append(f"-- 第 {round_num} 回合 --")
            
            # 玩家1攻击
            dmg1, logs1, heal1 = cls._execute_attack(player1, player2)
            player2.hp -= dmg1
            player1.hp = min(player1.max_hp, player1.hp + heal1)
            combat_log.extend(logs1)
            combat_log.append(f"{player2.name} 剩余 HP: {max(0, player2.hp)}")
            
            # 反伤
            counter = (player2.effects or {}).get("counter_damage", 0)
            if counter > 0:
                reflect_dmg = int(dmg1 * (counter / 100))
                player1.hp -= reflect_dmg
                combat_log.append(f"🛡️ {player2.name} 触发反伤，反弹 {reflect_dmg} 点伤害！")
            
            if player2.hp <= 0: break
            
            # 玩家2攻击
            dmg2, logs2, heal2 = cls._execute_attack(player2, player1)
            player1.hp -= dmg2
            player2.hp = min(player2.max_hp, player2.hp + heal2)
            combat_log.extend(logs2)
            combat_log.append(f"{player1.name} 剩余 HP: {max(0, player1.hp)}")
            
            # 反伤
            counter1 = (player1.effects or {}).get("counter_damage", 0)
            if counter1 > 0:
                reflect_dmg = int(dmg2 * (counter1 / 100))
                player2.hp -= reflect_dmg
                combat_log.append(f"🛡️ {player1.name} 触发反伤，反弹 {reflect_dmg} 点伤害！")
                
            combat_log.append("")
        
        winner = player1.user_id if player1.hp > 0 else (player2.user_id if player2.hp > 0 else "平局")
        
        return {
            "winner": winner, 
            "combat_log": combat_log, 
            "rounds": round_num,
            "player1_final_hp": 1, "player1_final_mp": 1,
            "player2_final_hp": 1, "player2_final_mp": 1
        }
    
    @classmethod
    def player_vs_boss(cls, player: CombatStats, boss: CombatStats) -> Dict:
        """玩家vs Boss战斗"""
        combat_log = [f"☆━━━━ Boss战开始 ━━━━☆", f"{player.name} 挑战 {boss.name}"]
        round_num = 0
        total_damage_dealt = 0
        
        while player.hp > 0 and boss.hp > 0 and round_num < 100:
            round_num += 1
            combat_log.append(f"-- 第 {round_num} 回合 --")
            
            dmg, logs, heal = cls._execute_attack(player, boss)
            boss.hp -= dmg
            total_damage_dealt += dmg
            player.hp = min(player.max_hp, player.hp + heal)
            combat_log.extend(logs)
            combat_log.append(f"{boss.name} 剩余 HP: {max(0, boss.hp)}")
            
            if boss.hp <= 0: break
            
            b_dmg, b_logs, b_heal = cls._execute_attack(boss, player)
            player.hp -= b_dmg
            combat_log.extend(b_logs)
            combat_log.append(f"{player.name} 剩余 HP: {max(0, player.hp)}")
            combat_log.append("")
            
        if boss.hp <= 0:
            winner = player.user_id
            reward = boss.exp
        elif player.hp <= 0:
            winner = boss.user_id
            reward = int(boss.exp * (total_damage_dealt / boss.max_hp))
        else:
            winner = "平局"
            reward = 0
            
        return {
            "winner": winner, "combat_log": combat_log, "rounds": round_num,
            "player_final_hp": max(1, player.hp), "player_final_mp": player.mp,
            "boss_final_hp": max(0, boss.hp), "reward": reward
        }