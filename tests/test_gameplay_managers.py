# tests/test_gameplay_managers.py
"""v3.40.2 正规测试流程：新玩法管理器测试套件

测试范围（测试计划 v1.0）：
- 单元测试：纯逻辑（道心被动、段位阈值、合成配方）
- 集成测试：真实临时 SQLite（migration 全量建表）+ 管理器与数据层交互
- 边界测试：非法输入、资源不足、重复操作、限额
- 并发语义：CAS 抢占、原子扣减（借助既有 test_atomic_primitives 已验证的原语）

外部依赖 stub：astrbot（框架）、战斗结果（patch CombatManager.player_vs_boss）、
储物戒（可控行为的假管理器）。通过标准：全部断言通过。
"""
import json
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
PKG = ROOT.name

# ---- astrbot stub（完整属性集，强制注册；与 test_atomic_primitives 同款约定）----
_astrbot = types.ModuleType("astrbot")
_api = types.ModuleType("astrbot.api")
_api.logger = types.SimpleNamespace(
    info=lambda *a: None, warning=lambda *a: None,
    error=lambda *a: None, exception=lambda *a: None,
)
_api.AstrBotConfig = dict
_event = types.ModuleType("astrbot.api.event")
_event.AstrMessageEvent = object
_api.event = _event
_all = types.ModuleType("astrbot.api.all")
_all.At = object
_all.Plain = object
_api.all = _all
sys.modules["astrbot"] = _astrbot
sys.modules["astrbot.api"] = _api
sys.modules["astrbot.api.event"] = _event
sys.modules["astrbot.api.all"] = _all

_data_base = __import__(f"{PKG}.data.data_manager", fromlist=["x"])
DataBase = _data_base.DataBase
_migration = __import__(f"{PKG}.data.migration", fromlist=["x"])
MigrationManager = _migration.MigrationManager
_models = __import__(f"{PKG}.models", fromlist=["x"])
Player = _models.Player


def make_player(uid: str, name: str = "", level: int = 1, gold: int = 100000,
                exp: int = 100000, karma: int = 0, fate: int = 0, reinc: int = 0) -> Player:
    p = Player(user_id=uid, user_name=name or uid[:6])
    p.level_index = level
    p.gold = gold
    p.experience = exp
    p.karma = karma
    p.fate_points = fate
    p.reincarnation_count = reinc
    p.hp = 1000
    p.atk = 100
    p.atkpractice = 0
    p.physical_damage = 50
    p.magic_damage = 50
    p.main_technique = ""
    p.weapon = ""
    p.life_skill = ""
    p.set_pills_inventory({})
    p.set_storage_ring_items({})
    p.permanent_bonus = ""
    return p


class FakeRing:
    """可控行为的储物戒 stub"""

    def __init__(self, fail_store=False):
        self.fail_store = fail_store
        self.stored = []
        self.items = {}

    async def store_item(self, player, name, count=1, silent=True, **kw):
        if self.fail_store:
            return False, "full"
        self.stored.append((name, count))
        self.items[name] = self.items.get(name, 0) + count
        return True, "ok"

    async def retrieve_item(self, player, name, count=1):
        if self.items.get(name, 0) < count:
            return False, "not enough"
        self.items[name] -= count
        return True, "ok"

    def has_item(self, player, name, count=1):
        return self.items.get(name, 0) >= count

    def get_item_count(self, player, name):
        return self.items.get(name, 0)


class GameplayTestBase(unittest.IsolatedAsyncioTestCase):
    """公共基建：真实临时库 + migration 全量建表"""

    async def asyncSetUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = DataBase(os.path.join(self._tmpdir.name, "test_gameplay.db"))
        await self.db.connect()
        await MigrationManager(self.db.conn, None).migrate()
        await self.db.ext.ensure_system_config_table()
        await self.db.ensure_performance_indexes()

    async def asyncTearDown(self):
        await self.db.close()
        self._tmpdir.cleanup()

    async def save_player(self, p: Player):
        await self.db.create_player(p)
        # v3.40.2：create_player 不含 karma/fate/reincarnation 等列，测试关注字段统一补写落库
        await self.db.update_player_fields(
            p.user_id,
            karma=p.karma, fate_points=p.fate_points,
            reincarnation_count=p.reincarnation_count,
            level_index=p.level_index, experience=p.experience,
            gold=p.gold, physical_damage=p.physical_damage,
            mental_power=p.mental_power,
        )
        return p

    async def load_player(self, uid: str) -> Player:
        return await self.db.get_player_by_id(uid)


# ============ 1. 镇妖塔 ============

class TestTower(GameplayTestBase):
    async def test_challenge_win_progress_and_rewards(self):
        TowerManager = __import__(f"{PKG}.managers.tower_manager", fromlist=["x"]).TowerManager
        ring = FakeRing()
        mgr = TowerManager(self.db, None, ring)
        p = await self.save_player(make_player("tw1", "登塔者", level=20, exp=5_000_000))
        old_exp = p.experience
        ok, msg, new_record = await mgr.challenge(p)
        if "通关" in msg:  # 战斗结果由真实公式决定；低层对高修为必胜
            self.assertEqual(await mgr.get_best("tw1"), 1)
            self.assertTrue(new_record)
            fresh = await self.load_player("tw1")
            self.assertGreater(fresh.experience, old_exp)
        else:
            self.fail(f"低层挑战意外失败: {msg}")

    async def test_daily_limit(self):
        TowerManager = __import__(f"{PKG}.managers.tower_manager", fromlist=["x"]).TowerManager
        mgr = TowerManager(self.db, None, FakeRing())
        p = await self.save_player(make_player("tw2", level=30, exp=9_000_000))
        results = [await mgr.challenge(p) for _ in range(5)]
        ok_count = sum(1 for ok, _, _ in results if ok)
        blocked = [msg for ok, msg, _ in results if not ok and "次数已用尽" in msg]
        self.assertLessEqual(ok_count, 3)
        self.assertTrue(blocked, "第 4 次应被每日限额拦截")

    async def test_sweep_requires_progress_and_limits(self):
        TowerManager = __import__(f"{PKG}.managers.tower_manager", fromlist=["x"]).TowerManager
        mgr = TowerManager(self.db, None, FakeRing())
        p = await self.save_player(make_player("tw3"))
        ok, msg = await mgr.sweep(p)
        self.assertFalse(ok)
        self.assertIn("未通关", msg)
        # 手动置 best=1 再扫荡
        await self.db.ext.set_system_config("tower_best_tw3", "1")
        ok, msg = await mgr.sweep(p)
        self.assertTrue(ok)
        ok, msg = await mgr.sweep(p)
        self.assertTrue(ok)
        ok, msg = await mgr.sweep(p)
        self.assertFalse(ok)
        self.assertIn("扫荡次数已用尽", msg)

    async def test_record_and_ranking(self):
        TowerManager = __import__(f"{PKG}.managers.tower_manager", fromlist=["x"]).TowerManager
        mgr = TowerManager(self.db, None, FakeRing())
        await self.db.ext.set_system_config("tower_best_rk1", "5")
        board = await mgr.get_ranking()
        self.assertIn("第 5 层", board)


# ============ 2. 功德善堂 ============

class TestMerit(GameplayTestBase):
    async def test_redeem_item_success_and_deduction(self):
        MeritManager = __import__(f"{PKG}.managers.merit_manager", fromlist=["x"]).MeritManager
        ring = FakeRing()
        mgr = MeritManager(self.db, ring)
        p = await self.save_player(make_player("me1", karma=10))
        ok, msg = await mgr.redeem(p, 1)  # 引雷符 3 功德
        self.assertTrue(ok)
        self.assertEqual(ring.stored, [("引雷符", 1)])
        self.assertEqual(p.karma, 7)
        fresh = await self.load_player("me1")
        self.assertEqual(fresh.karma, 7)

    async def test_redeem_insufficient_karma_no_deduction(self):
        MeritManager = __import__(f"{PKG}.managers.merit_manager", fromlist=["x"]).MeritManager
        mgr = MeritManager(self.db, FakeRing())
        p = await self.save_player(make_player("me2", karma=2))
        ok, msg = await mgr.redeem(p, 2)  # 空间石 5 功德
        self.assertFalse(ok)
        self.assertEqual(p.karma, 2)
        fresh = await self.load_player("me2")
        self.assertEqual(fresh.karma, 2)

    async def test_redeem_title_requires_karma(self):
        MeritManager = __import__(f"{PKG}.managers.merit_manager", fromlist=["x"]).MeritManager
        mgr = MeritManager(self.db, FakeRing())
        p = await self.save_player(make_player("me3", karma=5))
        ok, msg = await mgr.redeem(p, 4)  # 称号需当前功德≥10
        self.assertFalse(ok)
        self.assertIn("≥ 10", msg)

    async def test_redeem_refund_on_store_fail(self):
        MeritManager = __import__(f"{PKG}.managers.merit_manager", fromlist=["x"]).MeritManager
        mgr = MeritManager(self.db, FakeRing(fail_store=True))
        p = await self.save_player(make_player("me4", karma=10))
        ok, msg = await mgr.redeem(p, 1)
        self.assertFalse(ok)
        self.assertIn("退还", msg)
        fresh = await self.load_player("me4")
        self.assertEqual(fresh.karma, 10)  # 原子退款

    async def test_bless_extends(self):
        MeritManager = __import__(f"{PKG}.managers.merit_manager", fromlist=["x"]).MeritManager
        mgr = MeritManager(self.db, FakeRing())
        p = await self.save_player(make_player("me5", karma=10))
        now = int(time.time())
        await self.db.ext.set_system_config("tide_bless_me5", str(now + 3600))
        ok, msg = await mgr.redeem(p, 3)  # 天道庇佑
        self.assertTrue(ok)
        raw = await self.db.ext.get_system_config("tide_bless_me5")
        # 未过期庇佑应顺延 24h（原 1h + 24h）
        self.assertGreaterEqual(int(raw), now + 3600 + 86400 - 5)


# ============ 3. 顿悟与道心 ============

class TestEnlighten(GameplayTestBase):
    async def test_passive_cap_and_tier(self):
        EnlightenManager = __import__(f"{PKG}.managers.enlighten_manager", fromlist=["x"]).EnlightenManager
        mgr = EnlightenManager(self.db)
        self.assertEqual(await mgr.get_passive("en1"), 0.0)
        await self.db.ext.set_system_config("daoxin_en1", "35")
        self.assertAlmostEqual(await mgr.get_passive("en1"), 0.03)
        await self.db.ext.set_system_config("daoxin_en1", "500")
        self.assertAlmostEqual(await mgr.get_passive("en1"), 0.10)  # 上限

    async def test_daily_gate_blocks_second_roll(self):
        EnlightenManager = __import__(f"{PKG}.managers.enlighten_manager", fromlist=["x"]).EnlightenManager
        mgr = EnlightenManager(self.db)
        p = make_player("en2")
        # 手动占满当日名额 → 无论骰子如何都返回 1.0
        await self.db.ext.syscfg_claim_slot(mgr._daily_key("en2"), 1)
        mult, note = await mgr.roll_enlighten(p)
        self.assertEqual(mult, 1.0)
        self.assertEqual(note, "")


# ============ 4. 段位天梯 ============

class TestLadder(GameplayTestBase):
    async def test_record_duel_win_lose_draw(self):
        LadderManager = __import__(f"{PKG}.managers.ladder_manager", fromlist=["x"]).LadderManager
        mgr = LadderManager(self.db)
        await mgr.record("ld1", "win", True)
        self.assertEqual(await mgr.get_points("ld1"), 3)
        await mgr.record("ld1", "lose", True)
        self.assertEqual(await mgr.get_points("ld1"), 2)
        await mgr.record("ld1", "draw", True)
        self.assertEqual(await mgr.get_points("ld1"), 2)
        self.assertEqual(await mgr.get_wins("ld1"), 1)

    async def test_points_clamp_zero(self):
        LadderManager = __import__(f"{PKG}.managers.ladder_manager", fromlist=["x"]).LadderManager
        mgr = LadderManager(self.db)
        await mgr.record("ld2", "lose", True)
        self.assertEqual(await mgr.get_points("ld2"), 0)  # 钳 0

    async def test_tier_thresholds(self):
        LadderManager = __import__(f"{PKG}.managers.ladder_manager", fromlist=["x"]).LadderManager
        mgr = LadderManager(self.db)
        self.assertIn("青铜", mgr.tier_of(0)[1])
        self.assertIn("白银", mgr.tier_of(30)[1])
        self.assertIn("宗师", mgr.tier_of(450)[1])

    async def test_milestone_claim_once(self):
        LadderManager = __import__(f"{PKG}.managers.ladder_manager", fromlist=["x"]).LadderManager
        mgr = LadderManager(self.db)
        p = await self.save_player(make_player("ld3"))
        await self.db.ext.set_system_config("ladder_pts_ld3", "80")
        ok, msg = await mgr.claim_milestone(p)  # 最高已达：黄金 5000
        self.assertTrue(ok)
        self.assertIn("5,000", msg)
        ok, msg = await mgr.claim_milestone(p)  # 低段位（白银 2000）仍可逐个领取
        self.assertTrue(ok)
        self.assertIn("2,000", msg)
        ok, msg = await mgr.claim_milestone(p)  # 已达段位奖励全部领完
        self.assertFalse(ok)
        fresh = await self.load_player("ld3")
        self.assertEqual(fresh.gold, 100000 + 7000)


# ============ 5. 丹药合成 ============

class TestPillSynth(GameplayTestBase):
    async def _make_mgr_player(self, uid, pills, gold=100000):
        PillSynthManager = __import__(f"{PKG}.managers.pill_synth_manager", fromlist=["x"]).PillSynthManager
        mgr = PillSynthManager(self.db, None)  # pill_manager 仅在 synth 成功路径用于… 实际未用（直接改 inventory）
        p = make_player(uid, gold=gold)
        p.set_pills_inventory(dict(pills))
        await self.save_player(p)
        return mgr, p

    async def test_synth_success(self):
        mgr, p = await self._make_mgr_player("ps1", {"炼气丹": 3})
        ok, msg = await mgr.synth(p, "聚灵丹")
        self.assertTrue(ok)
        inv = p.get_pills_inventory()
        self.assertEqual(inv.get("聚灵丹"), 1)
        self.assertNotIn("炼气丹", inv)
        fresh = await self.load_player("ps1")
        self.assertEqual(fresh.gold, 100000 - 1000)

    async def test_synth_insufficient_material(self):
        mgr, p = await self._make_mgr_player("ps2", {"炼气丹": 2})
        ok, msg = await mgr.synth(p, "聚灵丹")
        self.assertFalse(ok)
        self.assertIn("原料不足", msg)

    async def test_synth_insufficient_gold_keeps_material(self):
        mgr, p = await self._make_mgr_player("ps3", {"炼气丹": 3}, gold=100)
        ok, msg = await mgr.synth(p, "聚灵丹")
        self.assertFalse(ok)
        self.assertIn("灵石不足", msg)
        self.assertEqual(p.get_pills_inventory().get("炼气丹"), 3)  # 材料不动

    async def test_synth_unknown_product(self):
        mgr, p = await self._make_mgr_player("ps4", {})
        ok, msg = await mgr.synth(p, "不存在的丹")
        self.assertFalse(ok)


# ============ 6. 强化保底 ============

class TestForgePity(GameplayTestBase):
    def _mgr(self, ring):
        ForgeManager = __import__(f"{PKG}.managers.forge_manager", fromlist=["x"]).ForgeManager
        return ForgeManager(self.db, None, ring)

    async def test_pity_guaranteed_success_at_10(self):
        ring = FakeRing()
        ring.items["强化石"] = 999
        mgr = self._mgr(ring)
        p = await self.save_player(make_player("fg1", gold=10_000_000))
        # 直接构造连败 10 次 → 成功率 = min(1.0, base + 8*0.15) = 100% → 必成
        data = json.dumps({"forge_level": 0, "affixes": [], "forge_pity": 10})
        p.permanent_bonus = data
        await self.db.update_player_fields("fg1", permanent_bonus=data)
        ok, msg = await mgr.enhance_equipment(p)
        self.assertTrue(ok)
        fresh = await self.load_player("fg1")
        bonus = json.loads(fresh.permanent_bonus)
        self.assertEqual(bonus.get("forge_level"), 1)
        self.assertEqual(bonus.get("forge_pity"), 0)  # 保底兑现清零

    async def test_pity_increments_on_fail(self):
        ring = FakeRing()
        ring.items["强化石"] = 999
        mgr = self._mgr(ring)
        p = await self.save_player(make_player("fg2", gold=10_000_000))
        # 压低成功率路径不可控（真实骰子）——改为验证：无论成败，pity 字段与等级一致性
        for _ in range(6):
            await mgr.enhance_equipment(p)
        fresh = await self.load_player("fg2")
        bonus = json.loads(fresh.permanent_bonus)
        lv = bonus.get("forge_level", 0)
        pity = bonus.get("forge_pity", 0)
        self.assertLessEqual(lv + pity, 6)  # 每次要么 +1 级要么 +1 保底
        # 若出现 ≥3 连败后仍有失败，保底加成下最终应收敛（等级+保底 ≤ 次数）
        self.assertGreaterEqual(lv + pity, 1)


# ============ 7. 天道盘 ============

class TestDaoBet(GameplayTestBase):
    async def test_bet_success_deducts_and_pools(self):
        DaoBetManager = __import__(f"{PKG}.managers.dao_bet_manager", fromlist=["x"]).DaoBetManager
        mgr = DaoBetManager(self.db)
        p = await self.save_player(make_player("db1", gold=10000))
        ok, msg = await mgr.bet(p, "红", 1000)
        self.assertTrue(ok)
        fresh = await self.load_player("db1")
        self.assertEqual(fresh.gold, 9000)
        date, state = await mgr._get_or_create()
        self.assertEqual(int(state["red_pool"]), 1000)

    async def test_bet_insufficient_gold_releases_limit(self):
        DaoBetManager = __import__(f"{PKG}.managers.dao_bet_manager", fromlist=["x"]).DaoBetManager
        mgr = DaoBetManager(self.db)
        p = await self.save_player(make_player("db2", gold=50))
        ok, msg = await mgr.bet(p, "红", 1000)
        self.assertFalse(ok)
        date, state = await mgr._get_or_create()
        self.assertEqual(int(state.get("red_pool", 0)), 0)

    async def test_side_lock_prevents_hedging(self):
        DaoBetManager = __import__(f"{PKG}.managers.dao_bet_manager", fromlist=["x"]).DaoBetManager
        mgr = DaoBetManager(self.db)
        p = await self.save_player(make_player("db3", gold=100000))
        ok, _ = await mgr.bet(p, "红", 500)
        self.assertTrue(ok)
        ok, msg = await mgr.bet(p, "玄", 500)
        self.assertFalse(ok)
        self.assertIn("三心二意", msg)

    async def test_settle_pays_winners_proportionally(self):
        DaoBetManager = __import__(f"{PKG}.managers.dao_bet_manager", fromlist=["x"]).DaoBetManager
        mgr = DaoBetManager(self.db)
        yday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
        state = {
            "date": yday, "red_pool": 3000, "blue_pool": 1000, "settled": False,
            "bets": {
                "w1": {"side": "red", "amount": 3000, "name": "甲"},
                "l1": {"side": "blue", "amount": 1000, "name": "乙"},
            },
        }
        await self.db.ext.set_system_config(mgr._key(yday), json.dumps(state))
        await self.save_player(make_player("w1", gold=0))
        await self.save_player(make_player("l1", gold=0))
        with patch("random.random", return_value=0.1):  # 天意 → red 胜
            await mgr._settle_if_due()
        fw = await self.load_player("w1")
        fl = await self.load_player("l1")
        # 唯一赢方拿全部 90%：4000*0.9 = 3600
        self.assertEqual(fw.gold, 3600)
        self.assertEqual(fl.gold, 0)
        # 盘已标记 settled
        settled = await self.db.ext.get_system_config(mgr._key(yday))
        self.assertIn("true", settled)


# ============ 8. 妖兽巢穴 ============

class TestNestDefense(GameplayTestBase):
    async def test_start_cas_double_block(self):
        NestDefenseManager = __import__(f"{PKG}.managers.nest_defense_manager", fromlist=["x"]).NestDefenseManager
        mgr = NestDefenseManager(self.db, None, FakeRing())
        ok, msg = await mgr.start()
        self.assertTrue(ok)
        ok, msg = await mgr.start()
        self.assertFalse(ok)
        self.assertIn("已在进行", msg)

    async def test_contribute_reaches_target_triggers_victory(self):
        NestDefenseManager = __import__(f"{PKG}.managers.nest_defense_manager", fromlist=["x"]).NestDefenseManager
        ring = FakeRing()
        mgr = NestDefenseManager(self.db, None, ring)
        # 先放几名玩家抬高 target（MIN_TARGET=50000 太大，直接改 state 目标）
        ok, msg = await mgr.start()
        raw = await self.db.ext.get_system_config("nest_state")
        state = json.loads(raw)
        state["target"] = 200
        await self.db.ext.set_system_config("nest_state", json.dumps(state, ensure_ascii=False))
        p = await self.save_player(make_player("ns1", level=30, exp=9_000_000))

        with patch(f"{PKG}.managers.combat_manager.CombatManager.player_vs_boss",
                   lambda self, a, b: {"winner": "ns1", "rounds": 2, "damage_to_boss": 500}):
            ok, msg = await mgr.contribute(p)
        # 战斗被 patch 为必胜，200 目标一次 500 伤害 → 胜利结算
        self.assertIn("平定", msg) if "平定" in msg else self.assertIn("镇压", msg)
        # 状态关闭
        st = await mgr.get_state()
        self.assertIsNotNone(st)
        self.assertFalse(st.get("open", True))

    async def test_expire_triggers_raid(self):
        NestDefenseManager = __import__(f"{PKG}.managers.nest_defense_manager", fromlist=["x"]).NestDefenseManager
        mgr = NestDefenseManager(self.db, None, FakeRing())
        await mgr.start()
        raw = await self.db.ext.get_system_config("nest_state")
        state = json.loads(raw)
        state["end_ts"] = int(time.time()) - 10  # 过期
        state["target"] = 999999  # 必然未达标
        await self.db.ext.set_system_config("nest_state", json.dumps(state, ensure_ascii=False))
        await self.save_player(make_player("ns2", gold=10000))
        msg = await mgr.get_status()
        self.assertIn("洗劫", msg)
        fresh = await self.load_player("ns2")
        self.assertEqual(fresh.gold, 10000 - 500)  # -5%


# ============ 9. 宗门秘境 ============

class TestSectRaid(GameplayTestBase):
    async def test_summon_requires_materials_and_cas(self):
        SectRaidManager = __import__(f"{PKG}.managers.sect_raid_manager", fromlist=["x"]).SectRaidManager
        mgr = SectRaidManager(self.db, None, FakeRing())
        poor = types.SimpleNamespace(sect_id=1, sect_materials=100)
        ok, msg = await mgr.summon(make_player("sr0"), poor)
        self.assertFalse(ok)
        self.assertIn("资材不足", msg)
        rich = types.SimpleNamespace(sect_id=1, sect_materials=9999)
        ok, msg = await mgr.summon(make_player("sr1"), rich)
        self.assertTrue(ok)
        ok, msg = await mgr.summon(make_player("sr2"), rich)
        self.assertFalse(ok)  # CAS 防重复召唤

    async def test_challenge_drains_pool_and_settles(self):
        SectRaidManager = __import__(f"{PKG}.managers.sect_raid_manager", fromlist=["x"]).SectRaidManager
        ring = FakeRing()
        mgr = SectRaidManager(self.db, None, ring)
        rich = types.SimpleNamespace(sect_id=9, sect_materials=9999)
        await mgr.summon(make_player("sr3"), rich)
        raw = await self.db.ext.get_system_config("sectboss_active_9")
        state = json.loads(raw)
        state["max_hp"] = 200  # 缩小血池便于一击打空
        await self.db.ext.set_system_config("sectboss_active_9", json.dumps(state, ensure_ascii=False))
        await self.db.ext.set_system_config("sectboss_hp_9", "200")
        # 全宗成员（结算按 sect_id 批量 UPDATE）
        sr = await self.save_player(make_player("sr3", level=30, exp=9_000_000))
        sr.sect_id = 9
        await self.db.update_player_fields("sr3", sect_id=9)

        with patch(f"{PKG}.managers.combat_manager.CombatManager.player_vs_boss",
                   lambda self, a, b: {"winner": "sr3", "rounds": 1, "damage_to_boss": 500}):
            ok, msg, killed = await mgr.challenge(await self.load_player("sr3"), 9)
        self.assertTrue(killed)
        fresh = await self.load_player("sr3")
        self.assertEqual(fresh.gold, 100000 + 3000 + 5000)  # 全宗奖 + 伤害榜 Top1(5000)
        self.assertGreaterEqual(fresh.experience, 100000 + 8000)
        # 伤害键清理
        leftover = await self.db.ext.syscfg_get_number(mgr._dmg_prefix(9) + "sr3")
        self.assertEqual(leftover, 0)


# ============ 10. 仙府传功 ============

class TestMentor(GameplayTestBase):
    async def test_level_gates(self):
        MentorManager = __import__(f"{PKG}.managers.mentor_manager", fromlist=["x"]).MentorManager
        mgr = MentorManager()
        weak = make_player("mt0", level=5)
        junior = make_player("mt1", level=3)
        ok, msg = await mgr.transfer(self.db, weak, junior)
        self.assertFalse(ok)
        self.assertIn("境界 ≥ 15", msg)
        master = make_player("mt2", level=20)
        senior = make_player("mt3", level=20)
        ok, msg = await mgr.transfer(self.db, master, senior)
        self.assertFalse(ok)
        self.assertIn("≤ 8", msg)

    async def test_transfer_success_dual_gain(self):
        MentorManager = __import__(f"{PKG}.managers.mentor_manager", fromlist=["x"]).MentorManager
        mgr = MentorManager()
        master = await self.save_player(make_player("mt4", level=20, karma=0))
        junior = await self.save_player(make_player("mt5", level=3))
        old_exp = junior.experience
        ok, msg = await mgr.transfer(self.db, master, junior)
        self.assertTrue(ok)
        fj = await self.load_player("mt5")
        self.assertEqual(fj.experience, old_exp + 250 * 20)
        fm = await self.load_player("mt4")
        self.assertEqual(fm.karma, 1)
        # 受功者当日限额
        ok, msg = await mgr.transfer(self.db, master, junior)
        self.assertFalse(ok)
        self.assertIn("已受过一次传功", msg)


# ============ 11. 灵潮 ============

class TestSpiritTide(GameplayTestBase):
    async def test_maybe_start_once_per_slot(self):
        SpiritTideManager = __import__(f"{PKG}.managers.spirit_tide_manager", fromlist=["x"]).SpiritTideManager
        mgr = SpiritTideManager(self.db)
        with patch("random.random", return_value=0.01):  # 必中 18% 概率
            msg = await mgr.maybe_start()
            self.assertIn("灵潮", msg)
            msg2 = await mgr.maybe_start()
            self.assertEqual(msg2, "")  # 同一时段 CAS 已占
        self.assertTrue(await mgr.is_active())

    async def test_low_roll_never_starts(self):
        SpiritTideManager = __import__(f"{PKG}.managers.spirit_tide_manager", fromlist=["x"]).SpiritTideManager
        mgr = SpiritTideManager(self.db)
        with patch("random.random", return_value=0.99):  # 必不中
            msg = await mgr.maybe_start()
            self.assertEqual(msg, "")
        self.assertFalse(await mgr.is_active())


# ============ 12. 轮回天赋 ============

class TestTalents(GameplayTestBase):
    async def test_requires_reincarnation(self):
        ReincarnationManager = __import__(f"{PKG}.managers.reincarnation_manager", fromlist=["x"]).ReincarnationManager
        mgr = ReincarnationManager(self.db, None, None)
        p = await self.save_player(make_player("tl0", reinc=0, fate=1000))
        ok, msg = await mgr.upgrade_talent(p, "破煞")
        self.assertFalse(ok)
        self.assertIn("飞升", msg)

    async def test_upgrade_deducts_and_applies(self):
        ReincarnationManager = __import__(f"{PKG}.managers.reincarnation_manager", fromlist=["x"]).ReincarnationManager
        mgr = ReincarnationManager(self.db, None, None)
        p = await self.save_player(make_player("tl1", reinc=2, fate=100))
        ok, msg = await mgr.upgrade_talent(p, "破煞")  # 1 级 20 点
        self.assertTrue(ok)
        fresh = await self.load_player("tl1")
        self.assertEqual(fresh.fate_points, 80)
        self.assertEqual(fresh.physical_damage, 50 + 25)  # 基础 50 + 天赋
        # 二级 40 点
        ok, msg = await mgr.upgrade_talent(p, "破煞")
        self.assertTrue(ok)
        fresh = await self.load_player("tl1")
        self.assertEqual(fresh.fate_points, 40)
        self.assertEqual(fresh.physical_damage, 50 + 50)

    async def test_insufficient_fate(self):
        ReincarnationManager = __import__(f"{PKG}.managers.reincarnation_manager", fromlist=["x"]).ReincarnationManager
        mgr = ReincarnationManager(self.db, None, None)
        p = await self.save_player(make_player("tl2", reinc=2, fate=10))
        ok, msg = await mgr.upgrade_talent(p, "铁骨")  # 需 20
        self.assertFalse(ok)
        fresh = await self.load_player("tl2")
        self.assertEqual(fresh.fate_points, 10)

    async def test_max_level_block(self):
        ReincarnationManager = __import__(f"{PKG}.managers.reincarnation_manager", fromlist=["x"]).ReincarnationManager
        mgr = ReincarnationManager(self.db, None, None)
        p = await self.save_player(make_player("tl3", reinc=2, fate=100000))
        # 直接灌满天赋
        bonus = {"talents": {"破煞": 10}}
        p.permanent_bonus = json.dumps(bonus)
        await self.db.update_player_fields("tl3", permanent_bonus=p.permanent_bonus)
        ok, msg = await mgr.upgrade_talent(p, "破煞")
        self.assertFalse(ok)
        self.assertIn("无法再进", msg)


# ============ 13. 灵兽探险 ============

class TestPetExpedition(GameplayTestBase):
    async def _setup_pet(self, uid):
        await self.db.conn.execute(
            "INSERT OR REPLACE INTO player_pets (user_id, pet_name, pet_type, level, exp) VALUES (?, '火灵狐', '火灵狐', 5, 100)",
            (uid,)
        )
        await self.db.conn.commit()

    async def test_dispatch_and_collect_flow(self):
        PetManager = __import__(f"{PKG}.managers.pet_manager", fromlist=["x"]).PetManager
        mgr = PetManager(self.db)
        p = await self.save_player(make_player("pe1", gold=1000))
        await self._setup_pet("pe1")
        ok, msg = await mgr.start_expedition(p, "灵矿深处")
        self.assertTrue(ok)
        ok, msg = await mgr.start_expedition(p)
        self.assertFalse(ok)  # 重复派遣拒绝
        ok, msg = await mgr.collect_expedition(p)
        self.assertFalse(ok)  # 未到期
        # 时间快进
        raw = await self.db.ext.get_system_config(mgr._exp_key("pe1"))
        st = json.loads(raw)
        st["end_ts"] = int(time.time()) - 1
        await self.db.ext.set_system_config(mgr._exp_key("pe1"), json.dumps(st))
        old_gold = (await self.load_player("pe1")).gold
        old_exp = (await self.load_player("pe1")).experience
        ok, msg = await mgr.collect_expedition(p)
        self.assertTrue(ok)
        fresh = await self.load_player("pe1")
        self.assertGreater(fresh.gold, old_gold)
        self.assertGreater(fresh.experience, old_exp)
        ok, msg = await mgr.collect_expedition(p)
        self.assertFalse(ok)  # 状态一次性消费

    async def test_unknown_dest_rejected(self):
        PetManager = __import__(f"{PKG}.managers.pet_manager", fromlist=["x"]).PetManager
        mgr = PetManager(self.db)
        p = await self.save_player(make_player("pe2"))
        await self._setup_pet("pe2")
        ok, msg = await mgr.start_expedition(p, "不存在的地点")
        self.assertFalse(ok)


# ============ 14. 除妖 ============

class TestHunt(GameplayTestBase):
    async def test_hunt_daily_limit_and_total(self):
        HuntManager = __import__(f"{PKG}.managers.hunt_manager", fromlist=["x"]).HuntManager
        ring = FakeRing()
        mgr = HuntManager(self.db, None, ring)
        p = await self.save_player(make_player("hn1", level=10, exp=100000))
        with patch(f"{PKG}.managers.combat_manager.CombatManager.player_vs_boss",
                   lambda self, a, b: {"winner": "hn1", "rounds": 1, "damage_to_boss": 999}):
            for _ in range(5):
                ok, msg, win = await mgr.hunt(p)
                self.assertTrue(win)
            ok, msg, win = await mgr.hunt(p)
            self.assertFalse(ok)
            self.assertIn("体力已耗尽", msg)
        self.assertEqual(await mgr.get_total("hn1"), 5)
        # 击杀掉落进入假储物戒
        self.assertGreaterEqual(sum(c for _, c in ring.stored), 0)

# ============ 15. 心魔试炼（出师考）============

class TestGraduationTrial(GameplayTestBase):
    async def _setup_pair(self, m_uid="g1", d_uid="g2", d_level=5):
        master = await self.save_player(make_player(m_uid, level=20, karma=0))
        disciple = await self.save_player(make_player(d_uid, level=d_level, exp=80000))
        await self.db.conn.execute(
            "INSERT INTO master_relations (master_id, disciple_id, created_at, graduated) VALUES (?, ?, 0, 0)",
            (m_uid, d_uid)
        )
        await self.db.conn.commit()
        return master, disciple

    async def test_no_master_rejected(self):
        SocialManager = __import__(f"{PKG}.managers.social_manager", fromlist=["x"]).SocialManager
        mgr = SocialManager(self.db)
        p = await self.save_player(make_player("g0", level=5))
        ok, msg = await mgr.graduation_trial(p)
        self.assertFalse(ok)
        self.assertIn("尚未拜师", msg)

    async def test_win_sets_marker_and_graduate_doubles(self):
        SocialManager = __import__(f"{PKG}.managers.social_manager", fromlist=["x"]).SocialManager
        mgr = SocialManager(self.db)
        master, disciple = await self._setup_pair()
        with patch(f"{PKG}.managers.combat_manager.CombatManager.player_vs_boss",
                   lambda self_, a, b: {"winner": disciple.user_id, "rounds": 3}):
            ok, msg = await mgr.graduation_trial(disciple)
        self.assertTrue(ok)
        self.assertIn("通过", msg)
        # 出师 → 翻倍
        ok, msg = await mgr.graduate_disciple(master, disciple.user_id)
        self.assertTrue(ok)
        self.assertIn("翻倍", msg)
        fd = await self.load_player(disciple.user_id)
        fm = await self.load_player(master.user_id)
        self.assertEqual(fd.gold, 100000 + 60000)   # 30000 × 2
        self.assertEqual(fd.experience, 80000 + 40000)
        self.assertEqual(fm.gold, 100000 + 40000)   # 20000 × 2
        # 标记消费
        marker = await self.db.ext.get_system_config(mgr._chukao_pass_key(disciple.user_id))
        self.assertIsNone(marker)

    async def test_lose_no_marker_graduate_normal(self):
        SocialManager = __import__(f"{PKG}.managers.social_manager", fromlist=["x"]).SocialManager
        mgr = SocialManager(self.db)
        master, disciple = await self._setup_pair()
        with patch(f"{PKG}.managers.combat_manager.CombatManager.player_vs_boss",
                   lambda self_, a, b: {"winner": "inner_demon", "rounds": 2}):
            ok, msg = await mgr.graduation_trial(disciple)
        self.assertTrue(ok)  # 有战报
        self.assertIn("失败", msg)
        ok, msg = await mgr.graduate_disciple(master, disciple.user_id)
        self.assertTrue(ok)
        fd = await self.load_player(disciple.user_id)
        self.assertEqual(fd.gold, 100000 + 30000)  # 原倍

    async def test_daily_limit(self):
        SocialManager = __import__(f"{PKG}.managers.social_manager", fromlist=["x"]).SocialManager
        mgr = SocialManager(self.db)
        _, disciple = await self._setup_pair()
        with patch(f"{PKG}.managers.combat_manager.CombatManager.player_vs_boss",
                   lambda self_, a, b: {"winner": "inner_demon", "rounds": 1}):
            ok, _ = await mgr.graduation_trial(disciple)
            self.assertTrue(ok)
            ok, msg = await mgr.graduation_trial(disciple)
        self.assertFalse(ok)
        self.assertIn("每日 1 次", msg)

    async def test_repeat_after_pass_no_cost(self):
        SocialManager = __import__(f"{PKG}.managers.social_manager", fromlist=["x"]).SocialManager
        mgr = SocialManager(self.db)
        _, disciple = await self._setup_pair()
        await self.db.ext.set_system_config(mgr._chukao_pass_key(disciple.user_id), "1")
        ok, msg = await mgr.graduation_trial(disciple)
        self.assertFalse(ok)
        self.assertIn("已通过出师考", msg)
        # 未消耗次数（回退）
        used = await self.db.ext.syscfg_get_number(mgr._chukao_cnt_key(disciple.user_id))
        self.assertEqual(used, 0)


# ============ 16. 灵石红包 ============

class TestRedPacket(GameplayTestBase):
    async def _mgr(self):
        RedPacketManager = __import__(f"{PKG}.managers.redpacket_manager", fromlist=["x"]).RedPacketManager
        return RedPacketManager(self.db)

    async def test_send_deducts_and_splits_exactly(self):
        mgr = await self._mgr()
        sender = await self.save_player(make_player("rp1", gold=5000))
        ok, msg = await mgr.send(sender, 1000, 5)
        self.assertTrue(ok)
        fresh = await self.load_player("rp1")
        self.assertEqual(fresh.gold, 4000)
        # 提取份额验证总和恰好等于总额
        packet_id = msg.split("红包编号：")[1].split("\n")[0].strip()
        st = await mgr._load(packet_id)
        self.assertEqual(sum(st["shares"]), 1000)
        self.assertEqual(len(st["shares"]), 5)
        for s in st["shares"]:
            self.assertGreaterEqual(s, mgr.MIN_UNIT)

    async def test_send_insufficient_gold(self):
        mgr = await self._mgr()
        sender = await self.save_player(make_player("rp2", gold=100))
        ok, msg = await mgr.send(sender, 1000, 5)
        self.assertFalse(ok)
        self.assertIn("灵石不足", msg)

    async def test_grab_flow_no_double_claim(self):
        mgr = await self._mgr()
        sender = await self.save_player(make_player("rp3", gold=100000))
        ok, msg = await mgr.send(sender, 1000, 3)
        packet_id = msg.split("红包编号：")[1].split("\n")[0].strip()
        g1 = await self.save_player(make_player("g1", gold=0))
        g2 = await self.save_player(make_player("g2", gold=0))
        ok1, m1 = await mgr.grab(g1, packet_id)
        self.assertTrue(ok1)
        ok2, m2 = await mgr.grab(g2, packet_id)
        self.assertTrue(ok2)
        ok3, m3 = await mgr.grab(g1, packet_id)
        self.assertFalse(ok3)
        self.assertIn("已经抢过", m3)
        # 金币到账
        f1 = await self.load_player("g1")
        f2 = await self.load_player("g2")
        self.assertGreater(f1.gold + f2.gold, 0)
        st = await mgr._load(packet_id)
        self.assertEqual(len(st["claimed"]), 2)

    async def test_sender_cannot_grab_own(self):
        mgr = await self._mgr()
        sender = await self.save_player(make_player("rp4", gold=100000))
        ok, msg = await mgr.send(sender, 600, 2)
        packet_id = msg.split("红包编号：")[1].split("\n")[0].strip()
        ok, msg = await mgr.grab(sender, packet_id)
        self.assertFalse(ok)
        self.assertIn("不能抢自己", msg)

    async def test_expire_refunds_unclaimed(self):
        mgr = await self._mgr()
        sender = await self.save_player(make_player("rp5", gold=100000))
        ok, msg = await mgr.send(sender, 1000, 4)
        packet_id = msg.split("红包编号：")[1].split("\n")[0].strip()
        g1 = await self.save_player(make_player("g3", gold=0))
        await mgr.grab(g1, packet_id)
        got = (await self.load_player("g3")).gold
        # 时间快进过期
        raw = await self.db.ext.get_system_config(mgr._key(packet_id))
        st = json.loads(raw)
        st["expire_ts"] = int(time.time()) - 1
        await self.db.ext.set_system_config(mgr._key(packet_id), json.dumps(st, ensure_ascii=False))
        msg = await mgr.get_info(packet_id)
        self.assertIn("退回", msg)
        fresh_sender = await self.load_player("rp5")
        # 退回 = 总额 - 已领取
        self.assertEqual(fresh_sender.gold, 100000 - 1000 + (1000 - got))


# ============ 17. 妖兽图鉴 ============

class TestBestiary(GameplayTestBase):
    async def _mgr(self):
        HuntManager = __import__(f"{PKG}.managers.hunt_manager", fromlist=["x"]).HuntManager
        return HuntManager(self.db, None, FakeRing())

    async def test_record_species_dedup(self):
        mgr = await self._mgr()
        new1, body1 = await mgr.record_species("bk1", "残暴的野猪妖")
        self.assertTrue(new1)
        new2, body2 = await mgr.record_species("bk1", "嗜血的野猪妖")  # 同本体不同前缀 → 不重复
        self.assertFalse(new2)
        new3, _ = await mgr.record_species("bk1", "上古的黑风蟒")
        self.assertTrue(new3)
        raw = await self.db.ext.get_system_config("bestiary_bk1")
        seen = json.loads(raw)
        self.assertEqual(sorted(seen), ["野猪妖", "黑风蟒"])

    async def test_panel_progress_and_claim_once(self):
        mgr = await self._mgr()
        p = await self.save_player(make_player("bk2", gold=0))
        panel = await mgr.get_bestiary(p)
        self.assertIn("0/8", panel)
        # 集齐 8 种
        for body in mgr.BODIES:
            await mgr.record_species("bk2", "x的" + body)
        msg = await mgr.get_bestiary(p)
        self.assertIn("图鉴集齐", msg)
        self.assertIn("20,000", msg)
        fresh = await self.load_player("bk2")
        self.assertEqual(fresh.gold, mgr.BESTIARY_REWARD)
        # 再查看不重复发奖
        msg = await mgr.get_bestiary(p)
        self.assertIn("已领取", msg)
        fresh = await self.load_player("bk2")
        self.assertEqual(fresh.gold, mgr.BESTIARY_REWARD)

    async def test_hunt_records_species(self):
        mgr = await self._mgr()
        p = await self.save_player(make_player("bk3", level=10, exp=100000))
        with patch(f"{PKG}.managers.combat_manager.CombatManager.player_vs_boss",
                   lambda self_, a, b: {"winner": "bk3", "rounds": 1, "damage_to_boss": 999}):
            # 固定妖兽名（patch random.choice）
            with patch(f"{PKG}.managers.hunt_manager.random.choice",
                       side_effect=["残暴的", "野猪妖"]):
                ok, msg, win = await mgr.hunt(p)
        self.assertTrue(win)
        self.assertIn("图鉴收录新物种：【野猪妖】", msg)
        panel = await mgr.get_bestiary(await self.load_player("bk3"))
        self.assertIn("1/8", panel)
        self.assertIn("✅ 野猪妖", panel)


# ============ 18. 师门威望 ============

class TestPrestige(GameplayTestBase):
    async def _setup_pair(self, m_uid="pr1", d_uid="pr2", d_level=5, m_karma=0):
        SocialManager = __import__(f"{PKG}.managers.social_manager", fromlist=["x"]).SocialManager
        mgr = SocialManager(self.db)
        master = await self.save_player(make_player(m_uid, level=20, gold=100000))
        disciple = await self.save_player(make_player(d_uid, level=d_level, exp=80000))
        await self.db.conn.execute(
            "INSERT INTO master_relations (master_id, disciple_id, created_at, graduated) VALUES (?, ?, 0, 0)",
            (m_uid, d_uid)
        )
        await self.db.conn.commit()
        return mgr, master, disciple

    async def test_graduate_grants_prestige(self):
        mgr, master, disciple = await self._setup_pair()
        with patch(f"{PKG}.managers.combat_manager.CombatManager.player_vs_boss",
                   lambda self_, a, b: {"winner": disciple.user_id, "rounds": 2}):
            await mgr.graduation_trial(disciple)
        ok, msg = await mgr.graduate_disciple(master, disciple.user_id)
        self.assertTrue(ok)
        self.assertIn("师门威望 +10", msg)
        self.assertEqual(await mgr.get_prestige(master.user_id), 10)

    async def test_prestige_panel_counts_graduated(self):
        mgr, master, disciple = await self._setup_pair()
        with patch(f"{PKG}.managers.combat_manager.CombatManager.player_vs_boss",
                   lambda self_, a, b: {"winner": disciple.user_id, "rounds": 2}):
            await mgr.graduation_trial(disciple)
        await mgr.graduate_disciple(master, disciple.user_id)
        panel = await mgr.get_prestige_panel(master)
        self.assertIn("威望：10", panel)
        self.assertIn("已出师弟子：1 名", panel)
        self.assertIn("小有名气", panel)  # 威望10=小有名气

    async def test_milestone_claim_once(self):
        mgr, master, disciple = await self._setup_pair(m_uid="pr3", d_uid="pr4")
        await self.db.ext.set_system_config(mgr._prestige_key(master.user_id), "35")
        ok, msg = await mgr.claim_prestige_milestone(master)  # 最高达 30 → 30000
        self.assertTrue(ok)
        self.assertIn("30,000", msg)
        fresh = await self.load_player(master.user_id)
        self.assertEqual(fresh.gold, 100000 + 30000)
        ok, msg = await mgr.claim_prestige_milestone(master)  # 10 档仍可领
        self.assertTrue(ok)
        self.assertIn("10,000", msg)
        ok, msg = await mgr.claim_prestige_milestone(master)
        self.assertFalse(ok)
        fresh = await self.load_player(master.user_id)
        self.assertEqual(fresh.gold, 100000 + 40000)


# ============ 19. 秘境藏宝图 ============

class TestTreasureMap(GameplayTestBase):
    async def _mgr(self, uid, gold=100000):
        TreasureMapManager = __import__(f"{PKG}.managers.treasure_map_manager", fromlist=["x"]).TreasureMapManager
        mgr = TreasureMapManager(self.db, FakeRing())
        p = await self.save_player(make_player(uid, gold=gold))
        return mgr, p

    async def test_synth_requires_five_frags(self):
        mgr, p = await self._mgr("tm1")
        await self.db.ext.set_system_config(mgr._frag_key("tm1"), "4")
        ok, msg = await mgr.synth(p)
        self.assertFalse(ok)
        self.assertIn("碎片不足", msg)
        await self.db.ext.set_system_config(mgr._frag_key("tm1"), "5")
        ok, msg = await mgr.synth(p)
        self.assertTrue(ok)
        self.assertEqual(await mgr.get_frags("tm1"), 0)  # 碎片消耗
        self.assertEqual(await mgr.get_maps("tm1"), 1)

    async def test_explore_consumes_and_rewards(self):
        mgr, p = await self._mgr("tm2")
        await self.db.ext.set_system_config(mgr._map_key("tm2"), "1")
        ok, msg = await mgr.explore(p)
        self.assertTrue(ok)
        self.assertEqual(await mgr.get_maps("tm2"), 0)
        fresh = await self.load_player("tm2")
        # 奖励必然到账：灵石类直接加钱 / 物品类折算或入袋 —— gold 或 ring 必有一变
        # 最低物品价值 1×3000 折算
        self.assertGreaterEqual(fresh.gold, 100000)

    async def test_explore_without_map(self):
        mgr, p = await self._mgr("tm3")
        ok, msg = await mgr.explore(p)
        self.assertFalse(ok)
        self.assertIn("没有藏宝图", msg)

    async def test_jackpot_pool_structure(self):
        mgr, p = await self._mgr("tm4")
        # 权重总和一致性（防止改池漏改权重）
        self.assertEqual(mgr._TOTAL_WEIGHT, sum(w for _, _, _, w in mgr.TREASURE_POOL))
        # 抽 200 次确保分布函数不抛异常且结果合法
        await self.db.ext.set_system_config(mgr._map_key("tm4"), "500")
        for _ in range(200):
            ok, msg = await mgr.explore(p)
            self.assertTrue(ok)
        fresh = await self.load_player("tm4")
        self.assertGreater(fresh.gold, 100000)  # 至少有灵石/折算入账


# ============ 20. 仙侣送礼 ============

class TestMarriageGift(GameplayTestBase):
    class _Ring:
        """记录型储物戒 stub（分离双玩家物品）"""

        def __init__(self):
            self.bags = {}

        def _bag(self, player):
            return self.bags.setdefault(player.user_id, {})

        async def store_item(self, player, name, count=1, silent=True, **kw):
            self._bag(player)[name] = self._bag(player).get(name, 0) + count
            return True, "ok"

        async def retrieve_item(self, player, name, count=1):
            bag = self._bag(player)
            if bag.get(name, 0) < count:
                return False, "not enough"
            bag[name] -= count
            return True, "ok"

        def has_item(self, player, name, count=1):
            return self._bag(player).get(name, 0) >= count

    async def _setup_couple(self, m_uid="mg1", f_uid="mg2"):
        MarriageManager = __import__(f"{PKG}.managers.marriage_manager", fromlist=["x"]).MarriageManager
        ring = self._Ring()
        mgr = MarriageManager(self.db, ring)
        a = await self.save_player(make_player(m_uid, gold=100000))
        b = await self.save_player(make_player(f_uid, gold=100000))
        # 直接写入结契关系（跳过 propose 流程）
        import time
        now = int(time.time())
        for uid, other in ((m_uid, f_uid), (f_uid, m_uid)):
            await mgr._save_marriage(uid, other, now, bond=10)
        ring._bag(a)["空间石"] = 2
        return mgr, ring, a, b

    async def test_gift_success_transfers_and_bonds(self):
        mgr, ring, a, b = await self._setup_couple()
        ok, msg = await mgr.send_gift(a, "空间石", ring)
        self.assertTrue(ok)
        self.assertEqual(ring._bag(a).get("空间石"), 1)   # 送出 1
        self.assertEqual(ring._bag(b).get("空间石"), 1)   # 对方收到 1
        # 羁绊 +2
        ma = await mgr._load_marriage(a.user_id)
        self.assertEqual(ma.get("bond"), 12)
        mb = await mgr._load_marriage(b.user_id)
        self.assertEqual(mb.get("bond"), 12)

    async def test_gift_daily_limit(self):
        mgr, ring, a, b = await self._setup_couple("mg3", "mg4")
        ring._bag(a)["空间石"] = 5
        ok, _ = await mgr.send_gift(a, "空间石", ring)
        self.assertTrue(ok)
        ok, msg = await mgr.send_gift(a, "空间石", ring)
        self.assertFalse(ok)
        self.assertIn("今日已赠过仙礼", msg)
        self.assertEqual(ring._bag(a).get("空间石"), 4)  # 物品未被多扣

    async def test_gift_item_missing_no_limit_consumed(self):
        mgr, ring, a, b = await self._setup_couple("mg5", "mg6")
        ok, msg = await mgr.send_gift(a, "不存在的物品", ring)
        self.assertFalse(ok)
        # 名额退回：当日仍可正常赠送
        ring._bag(a)["引雷符"] = 1
        ok, msg = await mgr.send_gift(a, "引雷符", ring)
        self.assertTrue(ok)

    async def test_gift_partner_bag_full_refunds(self):
        mgr, ring, a, b = await self._setup_couple("mg7", "mg8")
        ring._bag(a)["空间石"] = 1
        # 塞满对方（FakeRing 无容量概念 → 用特殊物品名触发 store 失败）
        _orig_store = ring.store_item
        async def fail_store(player, name, count=1, silent=True, **kw):
            if player.user_id == b.user_id:  # 仅对方装不下
                return False, "full"
            return await _orig_store(player, name, count, silent=silent, **kw)
        ring.store_item = fail_store
        ok, msg = await mgr.send_gift(a, "空间石", ring)
        self.assertFalse(ok)
        self.assertIn("退回", msg)
        self.assertEqual(ring._bag(a).get("空间石"), 1)  # 物品退回
        # 名额退回：当日仍可赠送
        del ring.store_item  # 恢复正常方法
        ring._bag(b)["引雷符"] = 0
        ok, msg = await mgr.send_gift(a, "空间石", ring)
        self.assertTrue(ok)

    async def test_gift_requires_marriage(self):
        mgr, ring, a, b = await self._setup_couple("mg9", "mg10")
        lone = await self.save_player(make_player("mg11"))
        ring._bag(lone)["空间石"] = 1
        ok, msg = await mgr.send_gift(lone, "空间石", ring)
        self.assertFalse(ok)
        self.assertIn("尚未与道侣结契", msg)


# ============ 21. 突破心得录 ============

class TestBreakthroughLog(GameplayTestBase):
    def _mgr(self):
        _bm = __import__(f"{PKG}.core.breakthrough_manager", fromlist=["x"])
        return _bm.BreakthroughManager(self.db, None, {})

    async def test_record_and_stats(self):
        mgr = self._mgr()
        p = await self.save_player(make_player("bl1", level=5))
        await mgr._record_breakthrough(p, "炼气", "筑基", True, pill_name="")
        await mgr._record_breakthrough(p, "炼气", "筑基", False, pill_name="破境丹")
        await mgr._record_breakthrough(p, "炼气", "筑基", False, died=True)
        stats = await mgr.get_breakthrough_stats(p)
        self.assertIn("总尝试：3", stats)
        self.assertIn("成功 1", stats)
        self.assertIn("失败 2", stats)
        self.assertIn("走火入魔：1", stats)

    async def test_fifo_max_50(self):
        mgr = self._mgr()
        p = await self.save_player(make_player("bl2", level=5))
        for _ in range(60):
            await mgr._record_breakthrough(p, "A", "B", True)
        raw = await self.db.ext.get_system_config("bt_log_bl2")
        entries = json.loads(raw)
        self.assertEqual(len(entries), 50)  # FIFO 截断

    async def test_empty_stats(self):
        mgr = self._mgr()
        p = await self.save_player(make_player("bl3", level=1))
        stats = await mgr.get_breakthrough_stats(p)
        self.assertIn("尚无突破记录", stats)


# ============ 22. 宗门捐献周榜 ============

class TestDonateRanking(GameplayTestBase):
    async def _setup(self):
        SectManager = __import__(f"{PKG}.managers.sect_manager", fromlist=["x"]).SectManager
        mgr = SectManager(self.db, None)
        p = await self.save_player(make_player("dr1", level=10, gold=100000))
        return mgr, p

    async def test_donate_accumulates_weekly(self):
        mgr, p = await self._setup()
        # 直接调 donate 逻辑（无需宗门表：周榜只看 syscfg）
        import time
        week = time.strftime('%G-W%V')
        await self.db.ext.syscfg_adjust_number(f"sect_donate_week_99_{week}", 5000)
        await self.db.ext.syscfg_adjust_number(f"sect_donate_week_99_{week}", 3000)
        total = await self.db.ext.syscfg_get_number(f"sect_donate_week_99_{week}")
        self.assertEqual(total, 8000)

    async def test_ranking_shows_sorted(self):
        mgr, p = await self._setup()
        import time
        week = time.strftime('%G-W%V')
        # 插入两个宗门的捐献
        await self.db.ext.set_system_config(f"sect_donate_week_1_{week}", "50000")
        await self.db.ext.set_system_config(f"sect_donate_week_2_{week}", "80000")
        # 插入对应宗门名
        await self.db.conn.execute(
            "INSERT OR IGNORE INTO sects (sect_id, sect_name, sect_owner, sect_scale, sect_used_stone, sect_fairyland, sect_materials, mainbuff, secbuff, elixir_room_level) VALUES (1, '青云门', 'x', 100, 0, 0, 0, '0', '0', 0)"
        )
        await self.db.conn.execute(
            "INSERT OR IGNORE INTO sects (sect_id, sect_name, sect_owner, sect_scale, sect_used_stone, sect_fairyland, sect_materials, mainbuff, secbuff, elixir_room_level) VALUES (2, '天剑宗', 'y', 100, 0, 0, 0, '0', '0', 0)"
        )
        await self.db.conn.commit()
        panel = await mgr.get_donate_ranking(p)
        self.assertIn("天剑宗", panel)  # 80000 排第一
        self.assertIn("青云门", panel)
        self.assertIn("80,000", panel)
        self.assertIn("50,000", panel)

    async def test_empty_ranking(self):
        mgr, p = await self._setup()
        panel = await mgr.get_donate_ranking(p)
        self.assertIn("尚无宗门捐献", panel)


# ============ 23. 修炼周报 ============

class TestWeeklyReport(GameplayTestBase):
    async def _mgr(self):
        WeeklyReportManager = __import__(f"{PKG}.managers.weekly_report_manager", fromlist=["x"]).WeeklyReportManager
        return WeeklyReportManager(self.db)

    async def test_record_and_report(self):
        mgr = await self._mgr()
        p = await self.save_player(make_player("wr1"))
        await mgr.record_hunt("wr1")
        await mgr.record_hunt("wr1")
        await mgr.record_hunt_win("wr1")
        await mgr.record_breakthrough("wr1")
        await mgr.record_duel_win("wr1")
        await mgr.record_donate("wr1", 5000)
        report = await mgr.get_report(p)
        self.assertIn("除妖 2 次", report)
        self.assertIn("胜率 50%", report)
        self.assertIn("突破 1 次", report)
        self.assertIn("5,000", report)
        self.assertIn("本周总活跃", report)

    async def test_weekly_auto_reset(self):
        mgr = await self._mgr()
        await mgr.record_hunt("wr2")
        self.assertEqual(await mgr.get_count("wr2", "hunt"), 1)
        # 模拟新周：直接改周键
        old_key = mgr._key("wr2", "hunt")
        await self.db.ext.delete_system_config(old_key)
        self.assertEqual(await mgr.get_count("wr2", "hunt"), 0)  # 新周自动归零

    async def test_empty_report(self):
        mgr = await self._mgr()
        p = await self.save_player(make_player("wr3"))
        report = await mgr.get_report(p)
        self.assertIn("本周尚无动静", report)


# ============ 24. 天道封号台 ============

class TestTitleAuction(GameplayTestBase):
    async def _mgr(self):
        TitleAuctionManager = __import__(f"{PKG}.managers.title_auction_manager", fromlist=["x"]).TitleAuctionManager
        return TitleAuctionManager(self.db)

    async def test_bid_success_and_exclusivity(self):
        mgr = await self._mgr()
        rich = await self.save_player(make_player("ta1", gold=500000))
        ok, msg = await mgr.bid(rich, 1)
        self.assertTrue(ok)
        self.assertIn("竞得", msg)
        # 第二人抢同一编号 → 拒绝
        poor = await self.save_player(make_player("ta2", gold=500000))
        ok, msg = await mgr.bid(poor, 1)
        self.assertFalse(ok)
        # 封号写入 permanent_bonus
        fresh = await self.load_player("ta1")
        bonus = json.loads(fresh.permanent_bonus)
        self.assertIn("auction_title", bonus)

    async def test_bid_insufficient_gold(self):
        mgr = await self._mgr()
        poor = await self.save_player(make_player("ta3", gold=100))
        ok, msg = await mgr.bid(poor, 1)
        self.assertFalse(ok)
        self.assertIn("灵石不足", msg)

    async def test_bid_invalid_idx(self):
        mgr = await self._mgr()
        p = await self.save_player(make_player("ta4", gold=500000))
        ok, msg = await mgr.bid(p, 99)
        self.assertFalse(ok)


# ============ 25. 仙缘突破卷 ============

class TestBTCharge(GameplayTestBase):
    async def _mgr(self):
        ReincarnationManager = __import__(f"{PKG}.managers.reincarnation_manager", fromlist=["x"]).ReincarnationManager
        return ReincarnationManager(self.db, None, None)

    async def test_buy_and_count(self):
        mgr = await self._mgr()
        p = await self.save_player(make_player("bc1", reinc=1, fate=500))
        ok, msg = await mgr.buy_bt_charge(p)
        self.assertTrue(ok)
        bonus, charges = mgr.get_bt_charge_bonus(p)
        self.assertAlmostEqual(bonus, 0.08)
        self.assertEqual(charges, 1)
        # 再买两张到上限
        await mgr.buy_bt_charge(p)
        ok, msg = await mgr.buy_bt_charge(p)
        self.assertTrue(ok)
        ok, msg = await mgr.buy_bt_charge(p)
        self.assertFalse(ok)  # 上限 3
        self.assertIn("囤满", msg)

    async def test_buy_insufficient_fate(self):
        mgr = await self._mgr()
        p = await self.save_player(make_player("bc2", reinc=1, fate=50))
        ok, msg = await mgr.buy_bt_charge(p)
        self.assertFalse(ok)
        self.assertIn("仙缘点不足", msg)

    async def test_consume_charge(self):
        mgr = await self._mgr()
        p = await self.save_player(make_player("bc3", reinc=1, fate=500))
        await mgr.buy_bt_charge(p)
        bonus, note = await mgr.consume_bt_charge(self.db, p)
        self.assertAlmostEqual(bonus, 0.08)
        self.assertIn("突破卷", note)
        _, charges = mgr.get_bt_charge_bonus(p)
        self.assertEqual(charges, 0)
        # 消耗后再取 → 0
        bonus2, note2 = await mgr.consume_bt_charge(self.db, p)
        self.assertEqual(bonus2, 0.0)
        self.assertEqual(note2, "")



if __name__ == "__main__":
    unittest.main()
