# managers/title_manager.py
"""称号系统 v6.17 - 110 称号六品阶，最高品阶生效加成"""
import json
import time
from typing import Tuple, Optional, Dict

from ..data.data_manager import DataBase
from ..models import Player
from .title_data import TITLES, TIERS

__all__ = ["TitleManager"]

# 称号档案存于 permanent_bonus["titles"]: {称号名: 获得时间戳}
# 当前佩戴称号存于 player.title（展示用）；加成按图鉴内最高品阶自动生效


class TitleManager:
    def __init__(self, db: DataBase):
        self.db = db
        self.titles: Dict[str, dict] = {t["name"]: t for t in TITLES}

    def _load_owned(self, player: Player) -> Dict[str, float]:
        try:
            data = json.loads(player.permanent_bonus) if player.permanent_bonus else {}
            if not isinstance(data, dict):  # 防御数据异常（如 null, []）
                return {}
            owned = data.get("titles", {})
            return owned if isinstance(owned, dict) else {}
        except Exception:
            return {}

    def _save_owned(self, player: Player, owned: Dict[str, float]):
        try:
            data = json.loads(player.permanent_bonus) if player.permanent_bonus else {}
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        data["titles"] = owned
        player.permanent_bonus = json.dumps(data, ensure_ascii=False)

    def grant(self, player: Player, title_name: str) -> Tuple[bool, str]:
        """授予称号（幂等：已拥有则跳过）。返回 (是否新获得, 消息)"""
        t = self.titles.get(title_name)
        if not t:
            return False, ""
        owned = self._load_owned(player)
        if title_name in owned:
            return False, ""
        owned[title_name] = float(time.time())
        self._save_owned(player, owned)
        tier_name = TIERS[t["tier"]][0]
        return True, f"\n🏅 获得称号【{title_name}】（{tier_name}）！已录入称号图鉴。"

    def grant_by_key(self, player: Player, key: str, value) -> str:
        """按获取路径 key 批量检查并授予。返回提示文本（可能为空）"""
        msgs = []
        owned = self._load_owned(player)
        for t in TITLES:
            if t["how"] != key or t["name"] in owned:
                continue
            cond = t.get("condition")
            if cond is None:
                continue
            try:
                if key == "karma_neg":
                    met = (player.karma or 0) <= cond
                elif isinstance(value, (int, float)):
                    met = value >= cond
                else:
                    met = False
            except Exception:
                met = False
            if met:
                ok, msg = self.grant(player, t["name"])
                if ok:
                    msgs.append(msg)
        return "".join(msgs)

    def get_active_bonus(self, player: Player) -> Dict:
        """计算当前生效的加成（最高品阶的一个称号）"""
        owned = self._load_owned(player)
        best = None
        for name in owned:
            t = self.titles.get(name)
            if t and (best is None or t["tier"] > best["tier"]):
                best = t
        return best["stats"] if best else {}

    def get_active_title(self, player: Player) -> Optional[dict]:
        """当前提供加成的称号（最高品阶）"""
        owned = self._load_owned(player)
        best = None
        for name in owned:
            t = self.titles.get(name)
            if t and (best is None or t["tier"] >= best["tier"]):
                best = t
        return best

    def equip_display(self, player: Player, title_name: str) -> Tuple[bool, str]:
        """佩戴称号（仅改展示名，加成始终按最高品阶自动生效）"""
        owned = self._load_owned(player)
        if title_name == "" or title_name == "无":
            player.title = ""
            return True, "已摘下称号。"
        if title_name not in owned:
            return False, f"❌ 你尚未拥有称号【{title_name}】。查看 /称号图鉴"
        player.title = title_name
        return True, f"已佩戴称号【{title_name}】。"

    def collection_view(self, player: Player) -> str:
        """称号图鉴"""
        owned = self._load_owned(player)
        active = self.get_active_title(player)
        
        # ★ C2 修复：过滤掉不在当前版本 TITLES 中的残留称号，防止统计出错
        valid_owned_count = len([n for n in owned if n in self.titles])
        lines = [f"📜 称号图鉴（已收集 {valid_owned_count}/{len(TITLES)}）", "━━━━━━━━━━━━━━━"]
        
        by_tier = {}
        for t in TITLES:
            by_tier.setdefault(t["tier"], []).append(t)
            
        for tier in sorted(by_tier):
            # ★ C1 修复：增加 get 防御，未来若加新品阶忘记改 TIERS 也不会崩溃
            tier_name = TIERS.get(tier, (f"未知({tier})",))[0]
            lines.append(f"【{tier_name}】")
            for t in by_tier[tier]:
                mark = "✅" if t["name"] in owned else "🔒"
                active_mark = " ⭐生效中" if active and active["name"] == t["name"] else ""
                how_txt = self._how_text(t)
                lines.append(f"  {mark}【{t['name']}】{how_txt}{active_mark}")
                
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("💡 加成自动按已拥有的最高品阶称号生效；/佩戴称号 <名> 更换展示")
        return "\n".join(lines)

    def _how_text(self, t: dict) -> str:
        key = t["how"]
        cond = t.get("condition")
        texts = {
            "breakthrough": f"突破至境界{cond}",
            "win_pvp": f"决斗获胜{cond}场",
            "spar_count": f"切磋{cond}次",
            "checkin_count": f"累计签到{cond}天",
            "boss_damage": f"讨伐世界Boss {cond}次",
            "boss_kill_old": f"击杀旧Boss {cond}次",
            "escort_count": f"完成押镖{cond}次",
            "karma": f"功德达到{cond}",
            "karma_neg": f"业力达到{cond}",
            "craft_perfect": f"炼出极品丹{cond}枚",
            "craft_count": f"炼丹{cond}次",
            "enhance_count": f"强化{cond}次",
            "wash_count": f"洗练{cond}次",
            "gamble_count": f"切原石{cond}次",
            "harvest_count": f"收获灵田{cond}次",
            "cultivate_count": f"闭关{cond}次",
            "adventure_count": f"历练{cond}次",
            "rift_count": f"探索秘境{cond}次",
            "buy_count": f"购买{cond}次",
            "market_sell": f"坊市上架{cond}次",
            "blackmarket_buy": f"黑市购物{cond}次",
            "shield_count": f"开启护府{cond}次",
            "forge_count": f"强化/洗练共{cond}次",
            "pet_level": f"灵兽达到Lv.{cond}",
            "land_level": f"洞天达到Lv.{cond}",
            # ★ A2 修复：配合 title_data 加入 condition=5
            "furnace_max": (f"丹炉达到Lv.{cond}" if cond is not None else "丹炉升至满级"),
            "reincarnation": f"飞升转生{cond}次",
            "rebirth": (f"弃道重修{cond}次" if cond is not None else "弃道重修"),
            "luck_event": f"触发奇遇{cond}次",
            "sect_battle_win": f"大比获胜{cond}场",
            "demon_catch": f"揪出天魔{cond}次",
            "tide_resist": f"参与抵御魔潮{cond}次",
            # ★ 根因修复：防止 cond 为 None 时触发 {None:,} 格式化异常崩溃
            "gold_reach": (f"灵石达到{cond:,}" if isinstance(cond, int) else "灵石达到一定数额"),
            "manual": "特殊途径获得",
        }
        return texts.get(key, f"途径：{key} {cond if cond is not None else ''}")

    def bonus_summary(self, player: Player) -> str:
        stats = self.get_active_bonus(player)
        if not stats:
            return "当前无称号加成"
        parts = []
        cn = {"atk": "物伤", "magic": "法伤", "phys_def": "物防", "magic_def": "法防",
              "crit": "会心", "lifesteal": "吸血", "exp": "修为%", "luck": "气运",
              "gold_pct": "灵石%"}
        for k, v in stats.items():
            if k in ("exp", "gold_pct", "lifesteal"):
                parts.append(f"{cn.get(k, k)}+{v:.0%}" if isinstance(v, float) else f"{cn.get(k, k)}+{v}")
            else:
                parts.append(f"{cn.get(k, k)}+{v}")
        active = self.get_active_title(player)
        tier_name = TIERS[active["tier"]][0] if active else ""
        return f"【{active['name']}】({tier_name})：{' '.join(parts)}" if active else "无"