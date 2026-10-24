# managers/daily_task_manager.py
import random
import time
import json
from typing import Tuple, List, Dict
from ..data import DataBase
from ..models import Player

class DailyTaskManager:
    """日常任务管理器"""
    
    LEVEL_LIMITS = {
        "黄": {"max": 5, "base_exp": 500, "base_gold": 200},
        "玄": {"max": 3, "base_exp": 2000, "base_gold": 1000},
        "地": {"max": 2, "base_exp": 8000, "base_gold": 4000},
        "天": {"max": 1, "base_exp": 30000, "base_gold": 15000}
    }

    TASK_POOL = {
        "黄": [
            {"title": "洞府巡游", "type": "visit_dongfu", "count": 1, "desc": "参观一次任意玩家的洞府"},
            {"title": "宗门劳作", "type": "donate_material", "count": 10, "desc": "给宗门捐献10份材料"},
            {"title": "每日签到", "type": "check_in", "count": 1, "desc": "完成一次每日签到"}
        ],
        "玄": [
            {"title": "闭关苦修", "type": "cultivate", "count": 1, "desc": "完成一次闭关并出关"},
            {"title": "历练闯荡", "type": "adventure", "count": 1, "desc": "完成一次历练路线"},
            {"title": "秘境探索", "type": "explore_rift", "count": 1, "desc": "完成一次秘境探索"}
        ],
        "地": [
            {"title": "切磋斗法", "type": "spar", "count": 1, "desc": "参与一次玩家切磋"},
            {"title": "炼丹大师", "type": "craft_pill", "count": 1, "desc": "成功炼制一次丹药"},
            {"title": "灵田丰收", "type": "harvest", "count": 3, "desc": "收获3次灵田作物"}
        ],
        "天": [
            {"title": "弑神之战", "type": "boss_damage", "count": 2, "desc": "对世界Boss造成至少2%伤害"},
            {"title": "越级挑战", "type": "win_pvp", "count": 1, "desc": "在决斗中击败一名玩家"}
        ]
    }

    def __init__(self, db: DataBase):
        self.db = db

    def _scale_reward(self, player: Player, level: str) -> dict:
        """根据玩家境界动态缩放奖励，并附加防膨胀材料"""
        config = self.LEVEL_LIMITS[level]
        level_bonus = 1 + (player.level_index * 0.15) 
        
        exp = int(config["base_exp"] * level_bonus)
        gold = int(config["base_gold"] * level_bonus)
        
        materials = []
        if level == "黄": materials = [{"name": "灵草", "count": 3}]
        elif level == "玄": materials = [{"name": "玄铁", "count": 2}]
        elif level == "地": materials = [{"name": "洗练石", "count": 1}]
        elif level == "天": materials = [{"name": "极品洗练石", "count": 1}]

        return {"exp": exp, "gold": gold, "materials": materials}

    async def get_task_board(self, player: Player) -> str:
        """查看今日任务面板"""
        active_tasks = await self.db.ext.get_user_active_tasks(player.user_id)
        
        msg = ["📋 天道任务榜（当前进行中）", "━━━━━━━━━━━━━━━"]
        if not active_tasks:
            msg.append("你当前没有接取任何任务。")
        else:
            for t in active_tasks:
                status_str = "✅ 已完成待领取" if t["status"] == 2 else f"进度：{t['current_progress']}/{t['target_count']}"
                msg.append(f"[{t['task_level']}阶] {t['title']} - {status_str}")
                
        msg.append("\n💡 使用 /接取任务 <黄/玄/地/天> 获取新任务")
        msg.append("💡 使用 /领取任务奖励 结算已完成的日常")
        return "\n".join(msg)

    async def generate_task(self, player: Player, level: str) -> Tuple[bool, str]:
        """接取一个随机任务"""
        if level not in self.LEVEL_LIMITS:
            return False, "❌ 无效的任务品阶，请选择 黄/玄/地/天。"

        # 检查同类任务上限
        active_tasks = await self.db.ext.get_user_active_tasks(player.user_id)
        current_level_count = sum(1 for t in active_tasks if t["task_level"] == level)
        max_limit = self.LEVEL_LIMITS[level]["max"]
        
        if current_level_count >= max_limit:
            return False, f"❌ 你今日的【{level}阶】任务接取次数已用尽（上限 {max_limit} 次）。"

        # 随机抽取模板
        template = random.choice(self.TASK_POOL[level])
        
        # 动态计算奖励
        rewards = self._scale_reward(player, level)
        rewards_json = json.dumps(rewards, ensure_ascii=False)
        
        # 计算过期时间（今天 23:59:59）
        now = int(time.time())
        today_end = int(time.mktime(time.localtime(now)[:3] + (23, 59, 59, 0, 0, 0)))
        
        await self.db.ext.create_daily_task(
            user_id=player.user_id,
            task_level=level,
            title=template["title"],
            target_type=template["type"],
            target_count=template["count"],
            rewards_json=rewards_json,
            expire_time=today_end
        )
        
        return True, f"✅ 已接取【{level}阶】任务：{template['title']}\n目标：{template['desc']}"

    async def claim_rewards(self, player: Player) -> Tuple[bool, str, list]:
        """结算所有已完成的任务（加入事务防并发卡双倍奖励）"""
        # 开启事务锁
        await self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            # 事务内重新查询任务状态，确保是最新的
            async with self.db.conn.execute(
                "SELECT * FROM daily_tasks WHERE user_id = ? AND status = 2", 
                (player.user_id,)
            ) as cursor:
                completed_tasks = [dict(r) for r in await cursor.fetchall()]
            
            if not completed_tasks:
                await self.db.conn.rollback()
                return False, "❌ 当前没有已完成待领取的任务。", []
                
            total_exp = 0
            total_gold = 0
            total_items = []
            
            for task in completed_tasks:
                # 更新任务状态，并校验是否真的更新成功（防止其他协程抢先修改）
                cursor_update = await self.db.conn.execute(
                    "UPDATE daily_tasks SET status = 3 WHERE id = ? AND status = 2", 
                    (task["id"],)
                )
                if cursor_update.rowcount == 0:
                    # 如果受影响行数为0，说明在事务期间状态被改了（极端并发情况）
                    await self.db.conn.rollback()
                    return False, "❌ 领取失败，任务状态已变更，请重试。", []
                    
                rewards = json.loads(task["rewards_json"])
                total_exp += rewards.get("exp", 0)
                total_gold += rewards.get("gold", 0)
                total_items.extend(rewards.get("materials", []))
                
            # 事务内重新获取玩家数据，防止并发覆盖
            fresh_player = await self.db.get_player_by_id(player.user_id)
            if not fresh_player:
                await self.db.conn.rollback()
                return False, "❌ 玩家不存在。", []
                
            # 发放基础奖励
            fresh_player.experience += total_exp
            fresh_player.gold += total_gold
            await self.db.update_player(fresh_player, commit=False)
            
            await self.db.conn.commit()
            
            msg = [
                "🎁 任务奖励结算成功！",
                f"获得修为：+{total_exp:,}",
                f"获得灵石：+{total_gold:,}"
            ]
            if total_items:
                msg.append(f"获得材料：{total_items}")
                
            return True, "\n".join(msg), total_items
            
        except Exception as e:
            await self.db.conn.rollback()
            raise