# managers/gamble_manager.py
import random
import time
from typing import Tuple
from ..data import DataBase
from ..models import Player

class GambleManager:
    """赌石与黑市管理器"""
    def __init__(self, db: DataBase, config_manager, storage_ring_mgr):
        self.db = db
        self.config_manager = config_manager
        self.storage_ring_mgr = storage_ring_mgr

    async def cut_stone(self, player: Player, count: int) -> Tuple[bool, str]:
        """切原石"""
        if count <= 0 or count > 10:
            return False, "❌ 一次最多切 10 块原石。"
            
        total_cost = 10000 * count
        if player.gold < total_cost:
            return False, f"❌ 灵石不足！切 {count} 块原石需要 {total_cost:,} 灵石。"

        player.gold -= total_cost
        
        # ===== 修复点：动态获取可用物品池，防止出现配置里没有的“幽灵物品” =====
        all_items = list(self.config_manager.items_data.values())
        
        def get_random_by_rank(rank):
            pool = [i for i in all_items if i.get("rank") == rank]
            return random.choice(pool)["name"] if pool else "精铁"

        results = []
        for _ in range(count):
            roll = random.random()
            if roll < 0.80:
                # 80% 废料 (黄阶)
                item_name = get_random_by_rank("黄阶")
                results.append(f"切出了【{item_name}】（废料）")
                await self.storage_ring_mgr.store_item(player, item_name, 5, silent=True)
            elif roll < 0.95:
                # 15% 稀有材料 (玄阶)
                item_name = get_random_by_rank("玄阶")
                results.append(f"✨ 切出了【{item_name}】！")
                await self.storage_ring_mgr.store_item(player, item_name, 1, silent=True)
            elif roll < 0.999:
                # 4.9% 地阶/天阶法宝
                rank_pool = "天阶" if random.random() < 0.2 else "地阶"
                item_name = get_random_by_rank(rank_pool)
                results.append(f"🎉 金光四射！切出了【{item_name}】！")
                await self.storage_ring_mgr.store_item(player, item_name, 1, silent=True)
            else:
                # 0.1% 极其稀有的彩蛋
                results.append("🌌 天地异象！你切出了传说中的【护府令】x3！")
                await self.storage_ring_mgr.store_item(player, "护府令", 3, silent=True)

        await self.db.update_player(player)
        
        msg = [
            f"⛏️ 你花费了 {total_cost:,} 灵石，切开了 {count} 块原石：",
            "━━━━━━━━━━━━━━━",
            "\n".join(results),
            "━━━━━━━━━━━━━━━",
            f"💰 剩余灵石：{player.gold:,}"
        ]
        return True, "\n".join(msg)

    def get_black_market(self) -> Tuple[bool, str]:
        """获取今日黑市"""
        today_seed = int(time.strftime("%Y%m%d"))
        rng = random.Random(today_seed)
        
        pool = [
            {"name": "天阶·混元道果", "price": 100000, "desc": "吃了直接修为暴增。", "fake": False},
            {"name": "地阶·洗髓丹", "price": 1000, "desc": "永久加属性。", "fake": False},
            {"name": "神秘的葫芦", "price": 5000, "desc": "不知道装了什么。", "fake": True},
            {"name": "天阶·诛仙剑", "price": 50000, "desc": "绝世神兵。", "fake": False},
            {"name": "劣质回气散", "price": 200, "desc": "闻起来有点刺鼻。", "fake": True},
            {"name": "引雷符", "price": 1500, "desc": "雷纹隐现，炼丹保命必备。", "fake": False},
            {"name": "空间石", "price": 4200, "desc": "触手冰凉，蕴着空间之力。", "fake": False},
            {"name": "化身傀儡", "price": 180000, "desc": "眉心有一道灵光缓缓流转。", "fake": False},
            {"name": "护府令", "price": 30000, "desc": "真正的护府大阵符令。", "fake": False},
            {"name": "来路不明的傀儡", "price": 20000, "desc": "看起来像化身傀儡……真的吗？", "fake": True}
        ]
        items = rng.sample(pool, 3)
        
        msg = ["🕶️ 今日黑市（每天0点刷新）", "━━━━━━━━━━━━━━━"]
        for i, item in enumerate(items, 1):
            msg.append(f"[{i}] {item['name']} - {item['price']:,} 灵石")
            msg.append(f"    {item['desc']}")
        
        msg.append("━━━━━━━━━━━━━━━")
        msg.append("💡 使用 `/黑市购买 <编号>` 盲盒交易，一经售出概不负责！")
        return True, "\n".join(msg)

    async def buy_black_market(self, player: Player, index: int) -> Tuple[bool, str]:
        """购买黑市商品"""
        today_seed = int(time.strftime("%Y%m%d"))
        rng = random.Random(today_seed)
        
        pool = [
            {"name": "天阶·混元道果", "price": 100000, "desc": "吃了直接修为暴增。", "fake": False},
            {"name": "地阶·洗髓丹", "price": 1000, "desc": "永久加属性。", "fake": False},
            {"name": "神秘的葫芦", "price": 5000, "desc": "不知道装了什么。", "fake": True},
            {"name": "天阶·诛仙剑", "price": 50000, "desc": "绝世神兵。", "fake": False},
            {"name": "劣质回气散", "price": 200, "desc": "闻起来有点刺鼻。", "fake": True},
            {"name": "引雷符", "price": 1500, "desc": "雷纹隐现，炼丹保命必备。", "fake": False},
            {"name": "空间石", "price": 4200, "desc": "触手冰凉，蕴着空间之力。", "fake": False},
            {"name": "化身傀儡", "price": 180000, "desc": "眉心有一道灵光缓缓流转。", "fake": False},
            {"name": "护府令", "price": 30000, "desc": "真正的护府大阵符令。", "fake": False},
            {"name": "来路不明的傀儡", "price": 20000, "desc": "看起来像化身傀儡……真的吗？", "fake": True}
        ]
        items = rng.sample(pool, 3)

        if index < 1 or index > len(items):
            return False, "❌ 无效的商品编号。"
            
        target = items[index - 1]
        if player.gold < target["price"]:
            return False, f"❌ 灵石不足！需要 {target['price']}。"

        player.gold -= target["price"]
        
        if target["fake"]:
            penalty_hp = int(player.hp * 0.2) if player.hp > 0 else 0
            player.hp = max(1, player.hp - penalty_hp)
            await self.db.update_player(player)
            return True, f"🤢 你买下了【{target['name']}】，结果发现是个假货！你被毒气所伤，损失了 {penalty_hp} 点气血。"
        else:
            await self.storage_ring_mgr.store_item(player, target["name"], 1, silent=True)
            await self.db.update_player(player)
            return True, f"✅ 交易成功！你获得了【{target['name']}】，已存入储物戒。"