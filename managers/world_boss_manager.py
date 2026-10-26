# managers/world_boss_manager.py
import time
import random
from typing import Tuple, List, Dict
from astrbot.api import logger
from ..data import DataBase
from ..models import Player

class WorldBossManager:
    """全服世界Boss管理器 - 动态水位与防膨胀机制"""

    BOSS_NAMES = ["深渊魔龙", "远古天魔", "九幽冥王", "吞天巨兽", "血海老祖"]

    def __init__(self, db: DataBase, config_manager, storage_ring_mgr):
        self.db = db
        self.config_manager = config_manager
        self.storage_ring_mgr = storage_ring_mgr
        self.last_milestone_msg = None

    HP_RATIO = 0.60  # v6.19：Boss血量 = 全服玩家战力总和的 60%

    async def calculate_total_power(self) -> Tuple[int, int]:
        """计算全服玩家战力总和（含装备/称号加成的综合战力口径）
        返回 (总战力, 参与人数)"""
        players = await self.db.get_all_players()
        if not players:
            return 500_000, 0

        total = 0
        count = 0
        for p in players:
            # 战力口径与排行榜一致：物伤+法伤+双防+精神力/10，再叠加修为基数
            power = (p.experience + p.physical_damage + p.magic_damage +
                     p.physical_defense + p.magic_defense + p.mental_power // 10)
            total += power
            count += 1
        if total <= 0:
            total, count = 500_000, 0
        return total, count

    async def calculate_dynamic_hp(self) -> Tuple[int, int]:
        """v6.19：Boss 血量 = 全服玩家战力总和的 60%（一周三刷，玩家合围可破）"""
        total_power, player_count = await self.calculate_total_power()
        target_hp = int(total_power * self.HP_RATIO)
        target_hp = max(500_000, min(target_hp, 10_000_000_000))
        return target_hp, player_count

    async def preannounce(self) -> str:
        """Boss 降临预告（提前 15 分钟广播）"""
        total_power, count = await self.calculate_total_power()
        hp = int(total_power * self.HP_RATIO)
        hp = max(500_000, min(hp, 10_000_000_000))
        name = random.choice(self.BOSS_NAMES)
        return (
            f"📣【天道预警】15 分钟后，【{name}】将降临人间！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"❤️ 预估血量：约 {hp:,}（全服战力总和的 60%）\n"
            f"👥 当前可战修士：{count} 位\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 各位道友抓紧准备：修理法器（/强化）、备好丹药（/丹药背包）、\n"
            f"   检查五行克制（功法/武器名带金木水火土）\n"
            f"💡 15 分钟后发送 /挑战世界Boss 参与讨伐，排名奖励丰厚！"
        )

    async def spawn_boss(self) -> Tuple[bool, str]:
        """生成世界Boss"""
        async with self.db.conn.execute("SELECT * FROM world_boss WHERE status = 1") as cursor:
            if await cursor.fetchone():
                return False, "❌ 当前已有世界Boss存活！"

        max_hp, p_count = await self.calculate_dynamic_hp()
        boss_name = random.choice(self.BOSS_NAMES)
        now = int(time.time())
        expire_time = now + 86400 # 存活 24 小时

        await self.db.conn.execute(
            """INSERT INTO world_boss (boss_name, boss_level, max_hp, current_hp, atk, defense, spawn_time, expire_time)
               VALUES (?, 2, ?, ?, ?, 50, ?, ?)""",
            (boss_name, max_hp, max_hp, int(max_hp * 0.001), now, expire_time)
        )
        await self.db.conn.commit()

        return True, (
            f"🌪️ 【天道警示】世界Boss降临！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👹 名称：{boss_name}\n"
            f"💀 境界：灭世级\n"
            f"❤️ 血量：{max_hp:,}（全服战力总和的 60%，{p_count} 位修士合力可破）\n"
            f"⏳ 存活时间：24小时\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 发送 /挑战世界Boss 参与讨伐！"
        )

    async def challenge_boss(self, player: Player) -> Tuple[bool, str]:
        """挑战世界Boss"""
        now = int(time.time())

        # 0. 境界门槛：境界3（炼气四层）以上才能参与，防小号白嫖全服奖励
        MIN_BOSS_LEVEL = 3
        if player.level_index < MIN_BOSS_LEVEL:
            return False, (
                f"❌ 境界不足，无法参与讨伐！\n"
                f"━━━━━━━━━━━━━━━\n"
                f"挑战世界Boss需要达到境界等级 {MIN_BOSS_LEVEL}\n"
                f"你当前境界等级：{player.level_index}（还差 {MIN_BOSS_LEVEL - player.level_index} 级）\n"
                f"💡 通过 /闭关 /历练 提升修为后 /突破 提高境界"
            )

        # 1. 检查Boss状态
        async with self.db.conn.execute("SELECT * FROM world_boss WHERE status = 1") as cursor:
            row = await cursor.fetchone()
            if not row:
                return False, "❌ 当前没有存活的世界Boss。"
            boss = dict(row)

        if now > boss["expire_time"]:
            return False, "❌ Boss已逃遁，请等待下次降临。"

        # 2. 检查个人挑战次数与冷却（次数按自然日重置：跨日后当日次数清零）
        today_str = time.strftime("%Y%m%d")
        async with self.db.conn.execute(
            "SELECT * FROM world_boss_damage WHERE boss_id = ? AND user_id = ?",
            (boss["boss_id"], player.user_id)
        ) as cursor:
            record = await cursor.fetchone()
            if record:
                rec = dict(record)
                # 上次攻击不是今天 → 今日次数视为 0（重置）
                last_day = time.strftime("%Y%m%d", time.localtime(rec["last_attack_time"])) if rec["last_attack_time"] else ""
                if last_day != today_str:
                    rec["attack_count"] = 0
                if rec["attack_count"] >= 3:
                    return False, "❌ 你今日的挑战次数已用尽（每日限3次，次日刷新）。"
                if now - rec["last_attack_time"] < 300: # 5分钟CD
                    return False, f"❌ 调息中，请 {300 - (now - rec['last_attack_time'])} 秒后再来。"
            else:
                rec = {"total_damage": 0, "attack_count": 0, "id": 0}

        # 3. 核心修复：实时计算攻击力，防止面板未刷新导致的伤害异常
        from .combat_manager import CombatManager
        cm = CombatManager()
        realtime_atk = cm.calculate_atk(
            player.experience, player.atkpractice, 0, 
            player.physical_damage, player.magic_damage, player.cultivation_type
        )
        base_damage = int(realtime_atk * 100 + player.experience * 0.1)
        
        damage_percent = (base_damage / boss["max_hp"]) * 100

        # 强制限制在 0.5% ~ 3.0% 之间
        damage_percent = max(0.5, min(3.0, damage_percent))
        final_damage = int(boss["max_hp"] * (damage_percent / 100))
        
        if final_damage > boss["current_hp"]:
            final_damage = boss["current_hp"]

        # 4. 开启事务进行并发扣血与记录
        await self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            new_hp = boss["current_hp"] - final_damage
            is_kill = False
            if new_hp <= 0:
                new_hp = 0
                is_kill = True
                await self.db.conn.execute("UPDATE world_boss SET current_hp = ?, status = 2 WHERE boss_id = ?", (new_hp, boss["boss_id"]))
            else:
                await self.db.conn.execute("UPDATE world_boss SET current_hp = ? WHERE boss_id = ?", (new_hp, boss["boss_id"]))

            # 记录伤害
            if record:
                await self.db.conn.execute(
                    "UPDATE world_boss_damage SET total_damage = total_damage + ?, attack_count = attack_count + 1, last_attack_time = ? WHERE id = ?",
                    (final_damage, now, rec.get("id", 0))
                )
            else:
                await self.db.conn.execute(
                    "INSERT INTO world_boss_damage (boss_id, user_id, total_damage, attack_count, last_attack_time) VALUES (?, ?, ?, 1, ?)",
                    (boss["boss_id"], player.user_id, final_damage, now)
                )
            
            await self.db.conn.commit()
        except Exception as e:
            await self.db.conn.rollback()
            logger.error(f"世界Boss战斗异常: {e}")
            return False, "❌ 战斗异常，请稍后再试。"

        self.last_challenge_ok = True  # 真正打出伤害，供任务进度判定

        # v6.20 血量里程碑全服播报（25%/50%/75%，每档只播一次）
        try:
            new_pct = new_hp / max(1, boss["max_hp"])
            for threshold, label in ((0.75, "75%"), (0.50, "50%"), (0.25, "25%")):
                if new_pct <= threshold:
                    key = f"boss_hp_ann_{boss['boss_id']}_{label.replace('%','')}"
                    announced = await self.db.ext.get_system_config(key)
                    if not announced:
                        await self.db.ext.set_system_config(key, "1")
                        self.last_milestone_msg = (
                            f"📢【战况播报】【{boss['boss_name']}】血量已跌破 {label}！\n"
                            f"❤️ 剩余 {new_hp:,} / {boss['max_hp']:,}\n"
                            f"⚔️ 各位道友一鼓作气，尾刀奖励丰厚！"
                        )
                    break
        except Exception:
            pass

        # 5. 构造战报
        msg = [
            f"⚔️ 你对【{boss['boss_name']}】造成了 {final_damage:,} 点伤害！",
            f"━━━━━━━━━━━━━━━",
            f"📊 伤害占比：{damage_percent:.2f}%",
            f"❤️ Boss剩余血量：{new_hp:,} / {boss['max_hp']:,}",
        ]

        # 6. 击杀结算
        if is_kill:
            settle_msg = await self.settle_boss_kill(boss["boss_id"], player.user_id)
            msg.append("\n" + settle_msg)
        else:
            msg.append("\n💡 使用 /世界Boss状态 查看当前状态")

        return True, "\n".join(msg)

    async def settle_boss_kill(self, boss_id: int, killer_id: str) -> str:
        """结算Boss击杀奖励（真实发奖 + 尾刀称号）"""
        async with self.db.conn.execute(
            "SELECT * FROM world_boss_damage WHERE boss_id = ? ORDER BY total_damage DESC",
            (boss_id,)
        ) as cursor:
            damages = [dict(r) for r in await cursor.fetchall()]

        msg = [
            f"🎉 世界Boss已被成功击杀！",
            f"━━━━━━━━━━━━━━━",
        ]
        
        for i, dmg in enumerate(damages):
            rank = i + 1
            target_player = await self.db.get_player_by_id(dmg["user_id"])
            if not target_player: continue

            # 默认显示名字
            display_name = target_player.user_name or dmg['user_id']

            if dmg["user_id"] == killer_id:
                # 发尾刀奖励
                await self.storage_ring_mgr.store_item(target_player, "洗练石", 2, silent=True)
                await self.db.add_player_gold(target_player.user_id, 50000)
                target_player.gold += 50000

                # ===== 核心修复：实装尾刀称号 =====
                if not target_player.title or target_player.title != "灭世魔神":
                    await self.db.update_player_fields(target_player.user_id, title="灭世魔神")
                    target_player.title = "灭世魔神"
                    msg.append(f"👑 恭喜【{display_name}】斩杀世界Boss，获得唯一称号：【灭世魔神】！")
                # 更新显示名（加上称号前缀）
                display_name = f"【灭世魔神】{display_name}"
                # ==================================

                msg.append(f"🏆 {rank}. {display_name} - 尾刀大奖(洗练石x2, 5万灵石)")

            elif rank <= 3:
                await self.storage_ring_mgr.store_item(target_player, "洗练石", 1, silent=True)
                await self.db.add_player_gold(target_player.user_id, 20000)
                target_player.gold += 20000
                # 显示带有称号的名字
                if target_player.title:
                    display_name = f"【{target_player.title}】{display_name}"
                msg.append(f"🥇 {rank}. {display_name} - 主力输出(洗练石x1, 2万灵石)")

            else:
                await self.db.add_player_gold(target_player.user_id, 5000)
                target_player.gold += 5000
                # 显示带有称号的名字
                if target_player.title:
                    display_name = f"【{target_player.title}】{display_name}"
                msg.append(f"🥉 {rank}. {display_name} - 参与奖(5千灵石)")

        msg.append("━━━━━━━━━━━━━━━")
        msg.append("💡 奖励已发放至各位修士的储物戒/账户！")

        # 缓存结算文本，由指令层负责全服广播
        self.last_settle_msg = "\n".join(msg)

        return "\n".join(msg)