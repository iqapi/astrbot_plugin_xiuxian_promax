# tests/test_core_logic.py 恢复（14 项核心单测）
import sys, types, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
PKG = ROOT.name

astrbot = types.ModuleType("astrbot")
api_mod = types.ModuleType("astrbot.api")
event_mod = types.ModuleType("astrbot.api.event")


class _StubLogger:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


api_mod.logger = _StubLogger()
api_mod.AstrBotConfig = dict
event_mod.AstrMessageEvent = object
api_mod.event = event_mod
all_mod = types.ModuleType("astrbot.api.all")
all_mod.At = object
all_mod.Plain = object
api_mod.all = all_mod
sys.modules.setdefault("astrbot", astrbot)
sys.modules.setdefault("astrbot.api", api_mod)
sys.modules.setdefault("astrbot.api.event", event_mod)
sys.modules.setdefault("astrbot.api.all", all_mod)


def _imp(module_path: str):
    return __import__(f"{PKG}.{module_path}", fromlist=["x"])


class TestCombat(unittest.TestCase):
    def setUp(self):
        CombatManager = _imp("managers.combat_manager").CombatManager
        self.cm = CombatManager

    def test_element_overcomes_cycle(self):
        expect = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}
        self.assertEqual(self.cm.ELEMENT_OVERCOMES, expect)

    def test_element_multiplier(self):
        self.assertAlmostEqual(self.cm.element_multiplier("水", "火"), 1.3)
        self.assertAlmostEqual(self.cm.element_multiplier("火", "水"), 0.8)
        self.assertAlmostEqual(self.cm.element_multiplier("金", "金"), 1.0)
        self.assertAlmostEqual(self.cm.element_multiplier("", "火"), 1.0)

    def test_element_from_name(self):
        self.assertEqual(self.cm.get_element_from_name("离火真诀"), "火")
        self.assertEqual(self.cm.get_element_from_name("玄冰剑"), "")
        self.assertEqual(self.cm.get_element_from_name("庚金剑"), "金")
        self.assertEqual(self.cm.get_element_from_name("无属性"), "")

    def test_calculate_hp_mp(self):
        hp, mp = self.cm.calculate_hp_mp(1000, 0.5, 0.0)
        self.assertEqual((hp, mp), (750, 1000))

    def test_calculate_atk_class_bonus(self):
        base = dict(experience=10000, atkpractice=0, atk_buff=0.0, physical_damage=0, magic_damage=0)
        sword = self.cm.calculate_atk(cultivation_type="剑修", **base)
        buddha = self.cm.calculate_atk(cultivation_type="佛修", **base)
        normal = self.cm.calculate_atk(cultivation_type="灵修", **base)
        self.assertEqual(sword, int(1000 * 1.5))
        self.assertEqual(buddha, int(1000 * 0.6))
        self.assertEqual(normal, 1000)

    def test_damage_reduction_floor(self):
        self.assertEqual(self.cm.apply_damage_reduction(1000, 0), 1000)
        self.assertLess(self.cm.apply_damage_reduction(1000, 900), 1000)
        self.assertGreaterEqual(self.cm.apply_damage_reduction(1, 9999), 1)


class TestBankInterest(unittest.TestCase):
    def setUp(self):
        BankManager = _imp("managers.bank_manager").BankManager
        self.bank = BankManager(None, {})

    def test_no_interest_before_one_day(self):
        import time
        self.assertEqual(self.bank._calculate_interest(1_000_000, int(time.time())), 0)

    def test_interest_rounds_down(self):
        import time
        now = int(time.time())
        interest = self.bank._calculate_interest(10_000, now - 86400)
        self.assertGreater(interest, 0)
        self.assertLessEqual(interest, 10)

    def test_zero_balance_no_interest(self):
        self.assertEqual(self.bank._calculate_interest(0, 0), 0)


class TestConfigElements(unittest.TestCase):
    def test_keyword_inference(self):
        ConfigManager = _imp("config_manager").ConfigManager
        cm = ConfigManager.__new__(ConfigManager)
        self.assertEqual(cm._infer_element("烈焰刀"), "火")
        self.assertEqual(cm._infer_element("寒冰甲"), "水")
        self.assertEqual(cm._infer_element("青木令"), "木")
        self.assertEqual(cm._infer_element("厚土盾"), "土")
        self.assertEqual(cm._infer_element("庚金剑"), "金")
        self.assertEqual(cm._infer_element("闪电豹"), "木")
        self.assertEqual(cm._infer_element("普通物品"), "")


class TestCultivationEntry(unittest.TestCase):
    def test_cultivation_aliases(self):
        ph = _imp("handlers.player_handler")
        aliases = ph.CULTIVATION_ALIASES
        valid = set(ph.VALID_CULTIVATIONS)
        for alias, target in aliases.items():
            self.assertIn(target, valid, f"别名 {alias} 映射到未知职业 {target}")
        for short in ("灵", "体", "魔", "剑", "鬼", "佛", "兽"):
            self.assertIn(short, aliases, f"缺少单字简称 {short}")
        for name in valid:
            self.assertEqual(aliases[name], name)


class TestEncounterOutcomes(unittest.TestCase):
    def test_event_pool_structure(self):
        em = _imp("managers.encounter_events")
        events = em.EVENTS
        self.assertGreaterEqual(len(events), 100, "事件池应不少于100个")
        weights = {"risk", "safe", "good", "evil", "leave"}
        keys = set()
        for ev in events:
            self.assertEqual(len(ev["options"]), 3, ev["title"])
            self.assertNotIn(ev["key"], keys, f"重复key: {ev['key']}")
            keys.add(ev["key"])
            for opt in ev["options"]:
                self.assertIn(opt["weight"], weights, (ev["title"], opt["label"]))
                for branch in ("win", "lose"):
                    self.assertIsInstance(opt[branch], (dict, type(None)),
                                          f"{ev['title']}.{opt['label']}.{branch}")
                    if opt[branch] and "item" in opt[branch]:
                        self.assertIn("name", opt[branch]["item"], ev["title"])


class TestFarmConfigs(unittest.TestCase):
    def test_hybrid_product_plantable(self):
        _sfm = _imp("managers.spirit_farm_manager")
        SPIRIT_HERBS, HYBRID_RECIPES = _sfm.SPIRIT_HERBS, _sfm.HYBRID_RECIPES
        for materials, product in HYBRID_RECIPES.items():
            self.assertIn(product, SPIRIT_HERBS, f"杂交产物 {product} 必须可种植")
            for m in materials:
                self.assertIn(m, SPIRIT_HERBS)

    def test_season_system(self):
        sfm = _imp("managers.spirit_farm_manager")
        self.assertIn(sfm.get_current_season_index(), (0, 1, 2, 3))
        self.assertEqual(len(sfm.SEASON_EFFECTS), 4)
        for idx, eff in sfm.SEASON_EFFECTS.items():
            self.assertGreater(eff["growth_mult"], 0)
            self.assertGreater(eff["yield_mult"], 0)
        for herb in sfm.SPIRIT_HERBS:
            self.assertGreater(sfm.get_season_growth_mult(herb), 0)
        spring = sfm.SEASON_EFFECTS[0]
        self.assertLess(spring["growth_mult"], 1.0)
        winter = sfm.SEASON_EFFECTS[3]
        self.assertGreater(winter["growth_mult"], 1.0)
        self.assertEqual(winter["boost_growth"], 1.0)


class TestTitleSystem(unittest.TestCase):
    def test_title_pool(self):
        td = _imp("managers.title_data")
        self.assertGreaterEqual(len(td.TITLES), 100, "称号应不少于100个")
        names = [t["name"] for t in td.TITLES]
        self.assertEqual(len(names), len(set(names)), "称号存在重名")
        tiers = {t["tier"] for t in td.TITLES}
        self.assertTrue(tiers.issubset(set(td.TIERS.keys())))


if __name__ == "__main__":
    unittest.main(verbosity=2)
