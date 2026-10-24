# tests/test_core_logic.py
# 核心纯函数逻辑测试：可 pytest 运行，也可直接 `py -3 tests/test_core_logic.py`
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))  # 以包名导入，保持包内相对导入有效
PKG = ROOT.name  # 自动探测项目目录名，兼容插件改名

# ---- stub astrbot 依赖，使模块可脱离框架导入 ----
astrbot = types.ModuleType("astrbot")
api_mod = types.ModuleType("astrbot.api")


class _StubLogger:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


api_mod.logger = _StubLogger()
sys.modules.setdefault("astrbot", astrbot)
sys.modules.setdefault("astrbot.api", api_mod)


def _imp(module_path: str):
    return __import__(f"{PKG}.{module_path}", fromlist=["x"])


class TestCombat(unittest.TestCase):
    def setUp(self):
        CombatManager = _imp("managers.combat_manager").CombatManager
        self.cm = CombatManager

    def test_element_overcomes_cycle(self):
        """五行相克闭环：金克木木克土土克水水克火火克金"""
        expect = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}
        self.assertEqual(self.cm.ELEMENT_OVERCOMES, expect)

    def test_element_multiplier(self):
        self.assertAlmostEqual(self.cm.element_multiplier("水", "火"), 1.3)
        self.assertAlmostEqual(self.cm.element_multiplier("火", "水"), 0.8)
        self.assertAlmostEqual(self.cm.element_multiplier("金", "金"), 1.0)
        self.assertAlmostEqual(self.cm.element_multiplier("", "火"), 1.0)  # 无属性不参与

    def test_element_from_name(self):
        self.assertEqual(self.cm.get_element_from_name("离火真诀"), "火")
        self.assertEqual(self.cm.get_element_from_name("玄冰剑"), "")  # 冰的映射在 ConfigManager 层，基础推断只认单字
        # 基础推断只认单字
        self.assertEqual(self.cm.get_element_from_name("庚金剑"), "金")
        self.assertEqual(self.cm.get_element_from_name("无属性"), "")

    def test_calculate_hp_mp(self):
        hp, mp = self.cm.calculate_hp_mp(1000, 0.5, 0.0)
        self.assertEqual((hp, mp), (750, 1000))

    def test_calculate_atk_class_bonus(self):
        base = dict(experience=10000, atkpractice=0, atk_buff=0.0,
                    physical_damage=0, magic_damage=0)
        sword = self.cm.calculate_atk(cultivation_type="剑修", **base)
        buddha = self.cm.calculate_atk(cultivation_type="佛修", **base)
        normal = self.cm.calculate_atk(cultivation_type="灵修", **base)
        self.assertEqual(sword, int(1000 * 1.5))
        self.assertEqual(buddha, int(1000 * 0.6))
        self.assertEqual(normal, 1000)

    def test_damage_reduction_floor(self):
        self.assertEqual(self.cm.apply_damage_reduction(1000, 0), 1000)
        self.assertLess(self.cm.apply_damage_reduction(1000, 900), 1000)
        self.assertGreaterEqual(self.cm.apply_damage_reduction(1, 9999), 1)  # 保底1点


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
        # 1天前存入10000，0.1%日息 → 利息应 <= 10
        interest = self.bank._calculate_interest(10_000, now - 86400)
        self.assertGreater(interest, 0)
        self.assertLessEqual(interest, 10)

    def test_zero_balance_no_interest(self):
        self.assertEqual(self.bank._calculate_interest(0, 0), 0)


class TestConfigElements(unittest.TestCase):
    def test_keyword_inference(self):
        ConfigManager = _imp("config_manager").ConfigManager
        cm = ConfigManager.__new__(ConfigManager)  # 跳过 __init__ 的文件加载
        self.assertEqual(cm._infer_element("烈焰刀"), "火")
        self.assertEqual(cm._infer_element("寒冰甲"), "水")
        self.assertEqual(cm._infer_element("青木令"), "木")
        self.assertEqual(cm._infer_element("厚土盾"), "土")
        self.assertEqual(cm._infer_element("庚金剑"), "金")
        self.assertEqual(cm._infer_element("闪电豹"), "木")  # 雷→木
        self.assertEqual(cm._infer_element("普通物品"), "")


class TestEncounterOutcomes(unittest.TestCase):
    def test_event_pool_structure(self):
        em = _imp("managers.encounter_events")
        events = em.EVENTS
        self.assertGreaterEqual(len(events), 100, "事件池应不少于100个")
        weights = {"risk", "safe", "good", "evil", "leave"}
        for ev in events:
            self.assertEqual(len(ev["options"]), 3, ev["title"])
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
        # 索引合法且四季齐备
        self.assertIn(sfm.get_current_season_index(), (0, 1, 2, 3))
        self.assertEqual(len(sfm.SEASON_EFFECTS), 4)
        # 每季倍率都为正、生长倍率>0
        for idx, eff in sfm.SEASON_EFFECTS.items():
            self.assertGreater(eff["growth_mult"], 0)
            self.assertGreater(eff["yield_mult"], 0)
        # 任意灵草任意季节的生长倍率均为正
        for herb in sfm.SPIRIT_HERBS:
            self.assertGreater(sfm.get_season_growth_mult(herb), 0)
        # 春季全体加速、冬季整体放缓但冰心草豁免
        spring = sfm.SEASON_EFFECTS[0]
        self.assertLess(spring["growth_mult"], 1.0)
        winter = sfm.SEASON_EFFECTS[3]
        self.assertGreater(winter["growth_mult"], 1.0)
        self.assertEqual(winter["boost_growth"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
