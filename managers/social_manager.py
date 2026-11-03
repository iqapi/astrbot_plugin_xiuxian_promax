# managers/social_manager.py
"""社交系统 v6.16 - NPC道侣（仙灵结缘）+ 师徒系统"""
import json
import time
from typing import Tuple, Optional, Dict

from astrbot.api import logger

from ..data.data_manager import DataBase
from ..models import Player

__all__ = ["SocialManager", "SPIRIT_COMPANIONS"]


# ===== 五位仙灵（NPC道侣）=====
SPIRIT_COMPANIONS = {
    "青璃": {
        "title": "丹谷仙子",
        "desc": "青丘丹谷传人，温婉聪慧，精于丹道。",
        "perk": "炼丹成功率 +5%",
        "perk_type": "alchemy",       # 炼丹
    },
    "白芷": {
        "title": "剑冢侍剑",
        "desc": "剑冢守剑人，冷若冰霜，剑意冲霄。",
        "perk": "历练修为收益 +8%",
        "perk_type": "adventure",     # 历练
    },
    "绯烟": {
        "title": "镖行大小姐",
        "desc": "天下镖行独女，飒爽仗义，交游广阔。",
        "perk": "押镖镖银 +12%",
        "perk_type": "escort",        # 押镖
    },
    "玄霜": {
        "title": "北冥散人",
        "desc": "北冥之滨的神秘散修，闭关千年，道行深不可测。",
        "perk": "闭关修为 +6%",
        "perk_type": "cultivate",     # 闭关
    },
    "灵汐": {
        "title": "灵兽谷少主",
        "desc": "灵兽谷少主，通兽语，怀中总趴着一只雪貂。",
        "perk": "灵兽协战概率 +5%",
        "perk_type": "pet",           # 灵兽
    },
}

COMPANION_COST = 50000        # 结缘费用
COMPANION_MIN_LEVEL = 3       # 结缘最低境界
DAILY_BOND_EXP = 1500         # 每日共修修为（基于双方）
BOND_PER_DAY = 8              # 每日共修情缘值
BOND_PER_LEVEL = 100          # 每级情缘所需（NPC等级 = bond // 100 + 1）
MAX_COMPANION_LEVEL = 10


class SocialManager:
    """NPC道侣 + 师徒管理器"""

    def __init__(self, db: DataBase):
        self.db = db

    # ================= NPC 道侣 =================

    async def get_companion(self, user_id: str) -> Optional[Dict]:
        async with self.db.conn.execute(
            "SELECT * FROM npc_partners WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def list_companions(self) -> str:
        lines = ["💍 仙灵结缘", "━━━━━━━━━━━━━━━"]
        for name, c in SPIRIT_COMPANIONS.items():
            lines.append(f"【{name}】· {c['title']}")
            lines.append(f"  {c['desc']}")
            lines.append(f"  缘加成：{c['perk']}")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append(
            f"结缘条件：境界≥{COMPANION_MIN_LEVEL}，{COMPANION_COST:,} 灵石，且无真人双修请求进行中\n"
            "💡 /仙灵结缘 <名字> 结缘 · /仙灵共修 每日培养 · /仙灵解除 解缘"
        )
        return "\n".join(lines)

    async def bond_companion(self, player: Player, name: str) -> Tuple[bool, str]:
        """结缘仙灵"""
        cfg = SPIRIT_COMPANIONS.get(name)
        if not cfg:
            return False, f"❌ 没有名为【{name}】的仙灵。发送 /仙灵结缘 查看全部仙灵。"
        if player.level_index < COMPANION_MIN_LEVEL:
            return False, f"❌ 结缘仙灵需要达到境界等级 {COMPANION_MIN_LEVEL}（当前 {player.level_index}）。"
        existing = await self.get_companion(player.user_id)
        if existing:
            old_name = SPIRIT_COMPANIONS.get(existing["npc_id"], {}).get("title", existing["npc_id"])
            return False, f"❌ 你已与【{existing['npc_id']}】（{old_name}）结缘。先 /仙灵解除 再结新缘。"
        # 与真人双修互斥：有待处理的双修请求（作为发起者）时不可结缘
        async with self.db.conn.execute(
            "SELECT COUNT(*) FROM dual_cultivation_requests WHERE from_id = ?", (player.user_id,)
        ) as cursor:
            cnt = (await cursor.fetchone())[0]
        if cnt > 0:
            return False, "❌ 你有未处理的双修请求，请先 /拒绝双修 或等对方回应，再考虑仙灵结缘。"
        if player.gold < COMPANION_COST:
            return False, f"❌ 结缘需要 {COMPANION_COST:,} 灵石（三书六礼总要有的）。"

        # v3.25.5：条件原子扣款（防快照过期透支），不再整行覆写玩家快照
        cursor = await self.db.conn.execute(
            "UPDATE players SET gold = gold - ? WHERE user_id = ? AND gold >= ?",
            (COMPANION_COST, player.user_id, COMPANION_COST)
        )
        await self.db.conn.commit()
        if cursor.rowcount == 0:
            return False, f"❌ 结缘需要 {COMPANION_COST:,} 灵石（三书六礼总要有的）。"
        now = int(time.time())
        await self.db.conn.execute(
            "INSERT OR REPLACE INTO npc_partners (user_id, npc_id, bond, daily_time, created_at) VALUES (?, ?, 0, 0, ?)",
            (player.user_id, name, now)
        )
        await self.db.conn.commit()
        return True, (
            f"💍 结缘成功！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"你与【{name}】（{cfg['title']}）结为道侣！\n"
            f"「{cfg['desc']}」\n"
            f"缘加成：{cfg['perk']}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 每日 /仙灵共修 培养情缘，情缘等级提升加成（最高 Lv.{MAX_COMPANION_LEVEL}）"
        )

    async def daily_commune(self, player: Player) -> Tuple[bool, str]:
        """仙灵共修（每日一次，得修为+情缘）"""
        comp = await self.get_companion(player.user_id)
        if not comp:
            return False, "❌ 你还没有仙灵道侣。发送 /仙灵结缘 查看名单。"
        now = int(time.time())
        last = comp["daily_time"]
        if now - last < 86400 and time.strftime("%Y-%m-%d", time.localtime(last)) == time.strftime("%Y-%m-%d"):
            return False, "❌ 今日已与仙灵共修过了，明日再来（一日不见如隔三秋）。"

        cfg = SPIRIT_COMPANIONS.get(comp["npc_id"], {})
        level = min(MAX_COMPANION_LEVEL, comp["bond"] // BOND_PER_LEVEL + 1)
        exp_gain = DAILY_BOND_EXP * (1 + player.level_index // 5) * (1 + level * 0.1)
        exp_gain = int(exp_gain)
        new_bond = comp["bond"] + BOND_PER_DAY
        new_level = min(MAX_COMPANION_LEVEL, new_bond // BOND_PER_LEVEL + 1)

        # v3.25.5：单条原子语句同时占用"今日共修资格"并累加情缘（原先查后写可
        # 并发双吃修为）；修为改原子累加，不再整行覆写玩家快照
        today_start = int(time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d")))
        cursor = await self.db.conn.execute(
            "UPDATE npc_partners SET daily_time = ?, bond = bond + ? WHERE user_id = ? AND daily_time < ?",
            (now, BOND_PER_DAY, player.user_id, today_start)
        )
        if cursor.rowcount == 0:
            return False, "❌ 今日已与仙灵共修过了，明日再来（一日不见如隔三秋）。"
        await self.db.add_player_exp(player.user_id, exp_gain)
        await self.db.conn.commit()

        up_note = ""
        if new_level > level:
            up_note = f"\n🌸 情缘升温！{comp['npc_id']} 的缘等级提升至 Lv.{new_level}（{cfg.get('perk', '加成')}更强了）"
        return True, (
            f"💞 仙灵共修\n"
            f"━━━━━━━━━━━━━━━\n"
            f"你与【{comp['npc_id']}】（Lv.{level}）静坐通宵，双修一夜。\n"
            f"获得修为：+{exp_gain:,}\n"
            f"情缘：{comp['bond']} → {new_bond}"
            f"{up_note}"
        )

    async def break_companion(self, player: Player) -> Tuple[bool, str]:
        comp = await self.get_companion(player.user_id)
        if not comp:
            return False, "❌ 你没有仙灵道侣。"
        await self.db.conn.execute("DELETE FROM npc_partners WHERE user_id = ?", (player.user_id,))
        await self.db.conn.commit()
        return True, (
            f"💔 你与【{comp['npc_id']}】的缘分散了。\n"
            f"情缘值已清零，结缘礼金不退。\n"
            f"（仙灵不语，转身化作青烟散去……）"
        )

    # ===== v6.17 道侣洞天共享（仙灵代收）=====

    async def companion_collect_land(self, player: Player) -> Tuple[bool, str]:
        """仙灵代收洞天产出：道侣共享洞天，仙灵替你收取闲置产出。
        情谊分成：代收灵石的 20% 留给仙灵（消耗情缘值 1 点/次），其余归玩家。"""
        comp = await self.get_companion(player.user_id)
        if not comp:
            return False, "❌ 你没有仙灵道侣，无法代收。发送 /仙灵结缘 结缘一位仙灵。"
        if comp["bond"] <= 0:
            return False, "❌ 情缘值不足（需 ≥1），先 /仙灵共修 培养情缘。"

        land = None
        async with self.db.conn.execute(
            "SELECT * FROM blessed_lands WHERE user_id = ?", (player.user_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return False, "❌ 你还没有洞天！先 /购买洞天 1。"
        land = dict(row)

        now = int(time.time())
        hours_passed = (now - land["last_collect_time"]) / 3600
        if hours_passed < 1:
            remaining = int(3600 - (now - land["last_collect_time"]))
            return False, f"❌ 洞天暂无余粮（收取冷却 {remaining // 60} 分钟）。仙灵说：刚收过啦，无物可代收～"

        hours = min(24, int(hours_passed))
        gold_income = land["gold_per_hour"] * hours
        # 灵泉假山加成
        try:
            furniture = json.loads(land.get("furniture") or "[]")
            if "灵泉假山" in furniture:
                gold_income = int(gold_income * 1.10)
        except Exception:
            pass

        spirit_cut = int(gold_income * 0.20)
        player_cut = gold_income - spirit_cut

        # v3.25.5：先 CAS 占用收取权（原"读时间戳→加钱→写回"并发双触发双份产出），
        # 成功后才动钱；情缘扣减加 MAX(0,..) 钳制（防并发扣成负数）
        cursor = await self.db.conn.execute(
            "UPDATE blessed_lands SET last_collect_time = ? WHERE user_id = ? AND last_collect_time = ?",
            (now, player.user_id, land["last_collect_time"])
        )
        if cursor.rowcount == 0:
            return False, "❌ 代收失败：产出可能刚被收取过，请稍后再试。仙灵耸耸肩飞走了～"
        await self.db.conn.execute(
            "UPDATE npc_partners SET bond = MAX(0, bond - 1) WHERE user_id = ?",
            (player.user_id,)
        )
        await self.db.conn.commit()

        # 洞天产出进洞天主人账上（v3.25.5：原子记账）
        await self.db.add_player_gold(player.user_id, player_cut)

        cfg = SPIRIT_COMPANIONS.get(comp["npc_id"], {})
        return True, (
            f"🏔️【仙灵代收】\n"
            f"━━━━━━━━━━━━━━━\n"
            f"道侣【{comp['npc_id']}】（{cfg.get('title', '')}）代你巡视洞天，\n"
            f"收得闲置产出 {hours} 小时：\n"
            f"💰 灵石：+{player_cut:,}（仙灵情谊分成 {spirit_cut:,}）\n"
            f"💞 消耗情缘 1 点（剩余 {max(0, comp['bond'] - 1)}）\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 洞天已重新计时，/洞天收取 正常收取不受影响"
        )

    def companion_bonus(self, user_id: str, perk_type: str) -> float:
        """获取玩家仙灵的某类加成倍率（如 0.05 = +5%）。无仙灵或类型不符返回 0"""
        # 同步版本不查库：由调用方在有 comp 时传入；这里简化为查内存缓存的上层接口
        return 0.0

    async def companion_bonus_async(self, user_id: str, perk_type: str) -> float:
        comp = await self.get_companion(user_id)
        if not comp:
            return 0.0
        cfg = SPIRIT_COMPANIONS.get(comp["npc_id"], {})
        if cfg.get("perk_type") != perk_type:
            return 0.0
        level = min(MAX_COMPANION_LEVEL, comp["bond"] // BOND_PER_LEVEL + 1)
        # 基础 5%，每级 +0.5%
        return 0.05 + (level - 1) * 0.005

    # ================= 师徒系统 =================

    MAX_DISCIPLES = 2  # 每位师父同门在学弟子上限（防小号）

    async def get_master_of(self, disciple_id: str) -> Optional[Dict]:
        async with self.db.conn.execute(
            "SELECT * FROM master_relations WHERE disciple_id = ? AND graduated = 0", (disciple_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_disciples(self, master_id: str) -> list:
        async with self.db.conn.execute(
            "SELECT * FROM master_relations WHERE master_id = ? AND graduated = 0", (master_id,)
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]

    async def take_as_disciple(self, disciple: Player, master_id: str) -> Tuple[bool, str]:
        """拜师"""
        if disciple.user_id == master_id:
            return False, "❌ 不能拜自己为师。"
        if disciple.level_index >= 10:
            return False, "❌ 境界已过高（≥10级），无缘再拜师学艺。"
        master = await self.db.get_player_by_id(master_id)
        if not master:
            return False, "❌ 对方还未踏入修仙之路。"
        if master.level_index < disciple.level_index + 5:
            return False, f"❌ 拜师需对方境界高于你 5 级以上（对方 {master.level_index} 级，你 {disciple.level_index} 级）。"
        existing = await self.get_master_of(disciple.user_id)
        if existing:
            m = await self.db.get_player_by_id(existing["master_id"])
            mname = m.user_name if m and m.user_name else existing["master_id"][:8]
            return False, f"❌ 你已有师父【{mname}】。"
        count = len(await self.get_disciples(master_id))
        if count >= self.MAX_DISCIPLES:
            return False, f"❌ 对方门下弟子已满（{self.MAX_DISCIPLES} 人），暂时不再收徒。"

        now = int(time.time())
        # v3.25.5 修复：表有 UNIQUE(disciple_id)，出师记录(graduated=1)保留会让再次拜师
        # 的 INSERT 抛 IntegrityError——出师弟子永远无法再拜师。该表仅作在学关系使用
        # （历史行无展示入口），拜师前清理已出师的历史记录
        await self.db.conn.execute(
            "DELETE FROM master_relations WHERE disciple_id = ? AND graduated = 1",
            (disciple.user_id,)
        )
        await self.db.conn.execute(
            "INSERT INTO master_relations (master_id, disciple_id, created_at, graduated) VALUES (?, ?, ?, 0)",
            (master_id, disciple.user_id, now)
        )
        await self.db.conn.commit()
        return True, (
            f"🍚 拜师成功！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"你跪奉茶盏，正式拜【{master.user_name or master_id[:8]}】为师！\n"
            f"💡 师父在你每次突破时获得师德点（可在 /师德商店 兑换奖励）\n"
            f"💡 当你达到筑基期（境界3）后，师父可用 /出师 为你出师，双方获大礼"
        )

    async def on_disciple_breakthrough(self, disciple_id: str) -> Tuple[bool, str]:
        """徒弟突破时调用：师父获得师德点。返回提示（供拼入突破消息）"""
        rel = await self.get_master_of(disciple_id)
        if not rel:
            return False, ""
        gain = 5
        await self.db.conn.execute(
            "UPDATE players SET virtue_points = virtue_points + ? WHERE user_id = ?",
            (gain, rel["master_id"])
        )
        await self.db.conn.commit()
        master = await self.db.get_player_by_id(rel["master_id"])
        if not master:
            return False, ""
        mname = master.user_name or rel["master_id"][:8]
        # v3.25.5 修复：master 是加成后重新读取的，这里不能再 +gain（原显示双计）
        return True, f"\n🎓 你的突破令师父【{mname}】欣喜，师德 +{gain}（当前 {master.virtue_points}）"

    # ===== v3.41.0 心魔试炼（出师考）=====

    @staticmethod
    def _chukao_pass_key(uid: str) -> str:
        return f"chukao_pass_{uid}"

    @staticmethod
    def _chukao_cnt_key(uid: str) -> str:
        import time
        return f"chukao_cnt_{uid}_{time.strftime('%Y%m%d')}"

    async def graduation_trial(self, disciple: Player) -> Tuple[bool, str]:
        """心魔试炼（出师考）：弟子每日 1 次挑战自身心魔，
        通过后获得出师考通过标记——出师时师徒奖励翻倍。"""
        uid = disciple.user_id
        rel = await self.get_master_of(uid)
        if not rel:
            return False, "❌ 你尚未拜师，无需出师考。先 /拜师 @高境界道友。"
        if disciple.level_index < 2:
            return False, "❌ 心魔试炼需至少达到境界 2（练气后期）——根基太浅，心魔难防。"
        if not await self.db.ext.syscfg_claim_slot(self._chukao_cnt_key(uid), 1):
            return False, "❌ 今日心魔试炼已挑战过（每日 1 次），心魔也需要喘息。"
        if await self.db.ext.get_system_config(self._chukao_pass_key(uid)) == "1":
            await self.db.ext.syscfg_adjust_number(self._chukao_cnt_key(uid), -1)
            return False, "✅ 你已通过出师考！请师父直接 /出师 @你 领取翻倍大礼。"

        # 心魔 = 弟子自身的镜像（攻 ×1.15 / 血 ×1.25）——战胜自己方能出师
        from .combat_manager import CombatManager, CombatStats
        cm = CombatManager()
        hp, mp = cm.calculate_hp_mp(disciple.experience)
        atk = cm.calculate_atk(
            disciple.experience, disciple.atkpractice, 0,
            disciple.physical_damage, disciple.magic_damage, disciple.cultivation_type
        )
        p_stats = CombatStats(
            user_id=uid, name=disciple.user_name or f"道友{uid[:6]}",
            hp=hp, max_hp=hp, mp=mp, max_mp=mp, atk=atk,
            exp=disciple.experience,
            element=cm.get_element_from_name(disciple.main_technique) or cm.get_element_from_name(disciple.weapon),
        )
        mirror = CombatStats(
            user_id="inner_demon", name="心魔·另一个自己",
            hp=int(hp * 1.25), max_hp=int(hp * 1.25), mp=mp, max_mp=mp,
            atk=int(atk * 1.15), defense=10, crit_rate=10,
        )
        result = cm.player_vs_boss(p_stats, mirror)
        win = result.get("winner") == uid
        if win:
            await self.db.ext.set_system_config(self._chukao_pass_key(uid), "1")
            return True, (
                "🪞【心魔试炼】通过！\n"
                "━━━━━━━━━━━━━━━\n"
                f"你直面心魔·另一个自己，{result.get('rounds', '?')} 回合后将其斩落！\n"
                "✅ 出师考通过标记已点亮\n"
                "🎁 师父执行 /出师 @你 时，师徒双方奖励【翻倍】\n"
                "💡 已通过者重复挑战不再消耗次数"
            )
        return True, (
            "🪞【心魔试炼】失败……\n"
            "━━━━━━━━━━━━━━━\n"
            f"心魔借你之力反噬，{result.get('rounds', '?')} 回合后你败下阵来。\n"
            "💫 试炼不损分毫，明日再来——战胜自己，方能出师。\n"
            "💡 提示：心魔是你的镜像（攻+15%/血+25%），先把自己变强"
        )

    async def graduate_disciple(self, master: Player, disciple_id: str) -> Tuple[bool, str]:
        """出师（师父操作，徒弟需境界≥3）"""
        rel = await self.get_master_of(disciple_id)
        if not rel or rel["master_id"] != master.user_id:
            return False, "❌ 对方不是你的在学弟子。"
        d = await self.db.get_player_by_id(disciple_id)
        if not d:
            return False, "❌ 弟子数据异常。"
        if d.level_index < 3:
            dn = d.user_name or disciple_id[:8]
            return False, f"❌ 弟子【{dn}】尚未达到筑基期（境界3），尚需打磨。"
        # v3.41.0：出师考通过 → 奖励翻倍并消费标记
        passed = await self.db.ext.get_system_config(self._chukao_pass_key(disciple_id)) == "1"
        mult = 2 if passed else 1
        # 奖励双方（v3.25.5：改原子记账，不再整行覆写快照）
        d_reward_gold, d_reward_exp = 30000 * mult, 20000 * mult
        m_reward_gold = 20000 * mult
        d_fate = 20 * mult
        await self.db.add_player_gold(d.user_id, d_reward_gold)
        await self.db.add_player_exp(d.user_id, d_reward_exp)
        await self.db.conn.execute(
            "UPDATE players SET fate_points = fate_points + ? WHERE user_id = ?", (d_fate, d.user_id)
        )
        await self.db.add_player_gold(master.user_id, m_reward_gold)
        await self.db.conn.execute(
            "UPDATE master_relations SET graduated = 1 WHERE id = ?", (rel["id"],)
        )
        await self.db.conn.commit()
        if passed:
            await self.db.ext.delete_system_config(self._chukao_pass_key(disciple_id))
        # v3.44.0：出师反哺师父威望 +10
        prestige = await self.db.ext.syscfg_adjust_number(self._prestige_key(master.user_id), 10)
        dn = d.user_name or disciple_id[:8]
        bonus_note = "\n🪞 心魔试炼加成：全部奖励翻倍！" if passed else "\n💡 通过 /出师考 可让出师奖励翻倍（弟子每日可挑战）"
        prestige_note = f"\n🏛️ 师门威望 +10（当前 {prestige}）—— /师门威望 查看里程碑"
        return True, (
            f"🎓 出师礼成！\n"
            f"━━━━━━━━━━━━━━━\n"
            f"弟子【{dn}】已至筑基，学有所成！\n"
            f"弟子获得：{d_reward_gold:,} 灵石 + {d_reward_exp:,} 修为 + {d_fate} 仙缘点\n"
            f"你获得：{m_reward_gold:,} 灵石（传道之酬）\n"
            f"师徒缘分长存，自此江湖再见亦是故人。{bonus_note}{prestige_note}"
        )

    # ===== v3.44.0 师门威望 =====

    # 威望门槛 -> (灵石奖励, 称号)
    PRESTIGE_TIERS = {
        10: (10000, None),
        30: (30000, None),
        60: (80000, "一代名师"),
    }

    @staticmethod
    def _prestige_key(uid: str) -> str:
        return f"shimen_prestige_{uid}"

    async def get_prestige(self, master_id: str) -> int:
        return await self.db.ext.syscfg_get_number(self._prestige_key(master_id))

    def _prestige_tier(self, points: int) -> Tuple[int, str]:
        idx = 0
        names = ["初为人师", "小有名气", "桃李满门", "万世师表"]
        for i, (th, _) in enumerate(sorted(self.PRESTIGE_TIERS.items())):
            if points >= th:
                idx = i + 1
        return idx, names[idx]

    async def get_prestige_panel(self, master: Player) -> str:
        uid = master.user_id
        pts = await self.get_prestige(uid)
        idx, tname = self._prestige_tier(pts)
        async with self.db.conn.execute(
            "SELECT COUNT(*) FROM master_relations WHERE master_id = ? AND graduated = 1", (uid,)
        ) as cursor:
            graduated = (await cursor.fetchone())[0]
        lines = [
            "🏛️【师门威望】",
            "━━━━━━━━━━━━━━━",
            f"📜 名师称号：{tname}",
            f"⭐ 威望：{pts}（每名弟子出师 +10）",
            f"🎓 已出师弟子：{graduated} 名",
        ]
        unclaimed = []
        for th, (gold, _) in sorted(self.PRESTIGE_TIERS.items()):
            if pts >= th and not await self.db.ext.get_system_config(f"prestige_claim_{uid}_{th}"):
                unclaimed.append(f"{th} 威望（{gold:,} 灵石）")
        if unclaimed:
            lines.append(f"🎁 可领取里程碑奖励：{'、'.join(unclaimed)} → /师门威望领取")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("💡 收徒→弟子出师即得威望，威望里程碑可领取丰厚奖励")
        return "\n".join(lines)

    async def claim_prestige_milestone(self, master: Player) -> Tuple[bool, str]:
        """领取已达威望里程碑（从高到低找第一个未领的）"""
        uid = master.user_id
        pts = await self.get_prestige(uid)
        for th in sorted(self.PRESTIGE_TIERS.keys(), reverse=True):
            if pts < th:
                continue
            if await self.db.ext.get_system_config(f"prestige_claim_{uid}_{th}"):
                continue
            if not await self.db.ext.syscfg_claim_slot(f"prestige_claim_{uid}_{th}", 1):
                continue
            gold, title = self.PRESTIGE_TIERS[th]
            await self.db.add_player_gold(uid, gold)
            title_note = ""
            if title:
                try:
                    from .title_hooks import TitleHooks
                    msg = await TitleHooks(self.db).grant_manual(master, title)
                    if msg:
                        title_note = f"\n{msg.strip()}"
                except Exception as e:
                    logger.warning(f"[师门威望] 称号授予失败: {e}")
            return True, f"🏛️ 威望里程碑（{th} 点）奖励已领取！\n💰 灵石 +{gold:,}{title_note}"
        return False, "❌ 暂无可领取的威望里程碑奖励。"

    async def dismiss_disciple(self, master: Player, disciple_id: str) -> Tuple[bool, str]:
        """逐出师门"""
        rel = await self.get_master_of(disciple_id)
        if not rel or rel["master_id"] != master.user_id:
            return False, "❌ 对方不是你的在学弟子。"
        await self.db.conn.execute("DELETE FROM master_relations WHERE id = ?", (rel["id"],))
        await self.db.conn.commit()
        d = await self.db.get_player_by_id(disciple_id)
        dn = d.user_name if d and d.user_name else disciple_id[:8]
        return True, f"✂️ 你已将【{dn}】逐出师门。师徒恩断义绝。"

    async def my_master_info(self, player: Player) -> str:
        """我的师徒关系面板"""
        lines = ["🎓 师徒缘法", "━━━━━━━━━━━━━━━"]
        rel = await self.get_master_of(player.user_id)
        if rel:
            m = await self.db.get_player_by_id(rel["master_id"])
            mname = m.user_name if m and m.user_name else rel["master_id"][:8]
            lines.append(f"你的师父：【{mname}】")
        else:
            if player.level_index >= 10:
                lines.append("你的境界已高，无缘拜师。")
            else:
                lines.append("你尚未拜师。💡 /拜师 @高境界道友")
        disciples = await self.get_disciples(player.user_id)
        if disciples:
            lines.append(f"你的在学弟子（{len(disciples)}/{self.MAX_DISCIPLES}）：")
            for drel in disciples:
                d = await self.db.get_player_by_id(drel["disciple_id"])
                dn = d.user_name if d and d.user_name else drel["disciple_id"][:8]
                lines.append(f"  · 【{dn}】(境界{d.level_index if d else '?'})")
        else:
            lines.append("你门下暂无弟子。💡 等后辈 /拜师 @你")
        vp = getattr(player, "virtue_points", 0)
        lines.append(f"师德点：{vp}")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("师德商店：/师德兑换 1 引雷符(80) · /师德兑换 2 空间石x2(150) · /师德兑换 3 称号【传道真人】(300)")
        return "\n".join(lines)

    async def redeem_virtue(self, player: Player, item_id: int) -> Tuple[bool, str]:
        """师德商店兑换"""
        shop = {
            1: {"name": "引雷符", "cost": 80, "type": "item", "item": "引雷符", "count": 1},
            2: {"name": "空间石 x2", "cost": 150, "type": "item", "item": "空间石", "count": 2},
            3: {"name": "称号【传道真人】", "cost": 300, "type": "title", "title": "传道真人"},
        }
        goods = shop.get(item_id)
        if not goods:
            return False, "❌ 无效的兑换编号。可选：1 引雷符(80) / 2 空间石x2(150) / 3 称号传道真人(300)"
        vp = getattr(player, "virtue_points", 0)
        if vp < goods["cost"]:
            return False, f"❌ 师德点不足！需要 {goods['cost']}，当前 {vp}。\n💡 收徒并等弟子 /突破 即可累积师德。"
        # v3.25.5 修复：原代码从未扣减师德点，且 handler 失败路径"退还"反而凭空加点，
        # 可无限白嫖兑换。改为条件原子扣点（余额不足时 rowcount=0），失败路径由 handler 退还。
        cursor = await self.db.conn.execute(
            "UPDATE players SET virtue_points = virtue_points - ? WHERE user_id = ? AND virtue_points >= ?",
            (goods["cost"], player.user_id, goods["cost"])
        )
        if cursor.rowcount == 0:
            return False, f"❌ 师德点不足！需要 {goods['cost']}，当前 {vp}。\n💡 收徒并等弟子 /突破 即可累积师德。"
        await self.db.conn.commit()
        player.virtue_points = vp - goods["cost"]
        # 扣点（handler 层存储失败时会退还）
        if goods["type"] == "title":
            if player.title and "传道真人" in player.title:
                return False, "❌ 你已拥有该称号。"
            if player.title and player.title != "传道真人":
                player.title = f"{player.title}·传道真人"  # 追加而非覆盖，保留原称号
            else:
                player.title = "传道真人"
            # v3.25.5：只落 title 字段（师德点已原子扣减），不再整行覆写
            await self.db.update_player_fields(player.user_id, title=player.title)
            return True, f"🏅 兑换成功！获得称号【传道真人】（消耗师德 {goods['cost']}，剩余 {player.virtue_points}）"
        return True, f"__NEED_STORE__{goods['item']}|{goods['count']}|兑换【{goods['name']}】成功（消耗师德 {goods['cost']}，剩余 {player.virtue_points}）"
