# tests/test_atomic_primitives.py
"""原子 system_config 原语单测（v3.24.0）：真实临时 SQLite 数据库，防并发语义回退。

覆盖：CAS 抢占/比较交换、数值键原子增减、原子扣减（余额不足失败）、
限次认领（不可越限）、过期日键清理、竞态交错语义（顺序交错模拟）。
"""
import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
PKG = ROOT.name

# stub astrbot（与 test_core_logic.py 同款约定）
import types
_astrbot = types.ModuleType("astrbot")
_api = types.ModuleType("astrbot.api")
_api.logger = types.SimpleNamespace(
    info=lambda *a: None, warning=lambda *a: None,
    error=lambda *a: None, exception=lambda *a: None,
)
sys.modules.setdefault("astrbot", _astrbot)
sys.modules["astrbot.api"] = _api

_data_base = __import__(f"{PKG}.data.data_manager", fromlist=["x"])
DataBase = _data_base.DataBase


class TestAtomicPrimitives(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = DataBase(os.path.join(self._tmpdir.name, "test_atomic.db"))
        await self.db.connect()
        await self.db.ext.ensure_system_config_table()

    async def asyncTearDown(self):
        # 确保连接线程退出，否则 aiosqlite 的非守护线程会让解释器挂起
        try:
            await self.db.close()
        except Exception:
            pass
        self._tmpdir.cleanup()

    # ---- CAS ----

    async def test_cas_claim_only_once(self):
        """抢占语义（expect_old=None）：两个协程只有一个抢占成功"""
        ok1 = await self.db.ext.syscfg_cas("t_cas_claim", "1", None)
        ok2 = await self.db.ext.syscfg_cas("t_cas_claim", "2", None)
        self.assertTrue(ok1)
        self.assertFalse(ok2, "第二次抢占必须失败（值已非空）")

    async def test_cas_compare_and_swap(self):
        await self.db.ext.set_system_config("t_cas_swap", "A")
        ok = await self.db.ext.syscfg_cas("t_cas_swap", "B", "A")
        self.assertTrue(ok)
        self.assertEqual(await self.db.ext.get_system_config("t_cas_swap"), "B")
        # 旧值不匹配则失败
        ok2 = await self.db.ext.syscfg_cas("t_cas_swap", "C", "A")
        self.assertFalse(ok2)
        self.assertEqual(await self.db.ext.get_system_config("t_cas_swap"), "B")

    async def test_cas_new_key_equals_empty_claim(self):
        """key 不存在时 expect_old=None 视为抢占空值成功"""
        ok = await self.db.ext.syscfg_cas("t_cas_new", "v", None)
        self.assertTrue(ok)

    # ---- 数值键 ----

    async def test_adjust_number_from_missing_key(self):
        self.assertEqual(await self.db.ext.syscfg_adjust_number("t_num", 5), 5)
        self.assertEqual(await self.db.ext.syscfg_adjust_number("t_num", 3), 8)

    async def test_adjust_number_clamp_zero(self):
        self.assertEqual(await self.db.ext.syscfg_adjust_number("t_num_clamp", 2), 2)
        self.assertEqual(await self.db.ext.syscfg_adjust_number("t_num_clamp", -10), 0, "负数结果钳为 0")

    async def test_spend_insufficient_fails_atomically(self):
        await self.db.ext.syscfg_adjust_number("t_spend", 100)
        ok = await self.db.ext.syscfg_spend("t_spend", 60)
        self.assertTrue(ok)
        self.assertEqual(await self.db.ext.syscfg_get_number("t_spend"), 40)
        ok2 = await self.db.ext.syscfg_spend("t_spend", 60)
        self.assertFalse(ok2, "余额不足必须失败且不扣款")
        self.assertEqual(await self.db.ext.syscfg_get_number("t_spend"), 40, "失败扣款不得改动余额")

    async def test_spend_missing_key_fails(self):
        ok = await self.db.ext.syscfg_spend("t_spend_missing", 1)
        self.assertFalse(ok, "不存在的键视为余额 0，扣减必须失败")

    # ---- 限次认领 ----

    async def test_claim_slot_respects_limit(self):
        results = [await self.db.ext.syscfg_claim_slot("t_claim", 3) for _ in range(5)]
        self.assertEqual(results, [True, True, True, False, False], "第 4 次起必须失败")
        self.assertEqual(await self.db.ext.syscfg_get_number("t_claim"), 3, "失败认领不得增加计数")

    # ---- 过期日键清理 ----

    async def test_purge_dated_keys(self):
        import time
        old_day = time.strftime("%Y%m%d", time.localtime(time.time() - 30 * 86400))
        await self.db.ext.set_system_config(f"stats_cmd_x_{old_day}", "7")
        await self.db.ext.set_system_config("not_dated_key", "keep")
        n = await self.db.ext.purge_dated_config_keys(8)
        self.assertGreaterEqual(n, 1)
        self.assertIsNone(await self.db.ext.get_system_config(f"stats_cmd_x_{old_day}"))
        self.assertEqual(await self.db.ext.get_system_config("not_dated_key"), "keep", "无日期后缀的键不得误删")

    # ---- 竞态交错语义（顺序模拟并发交错）----

    async def test_interleaved_double_claim(self):
        """模拟两个协程交错执行"检查+发奖"：CAS 保证只有一个赢家"""
        raw_key = "t_interleave"
        await self.db.ext.set_system_config(raw_key, "state_v1")
        # 协程 A 与 B 都基于同一旧值准备新值
        old = await self.db.ext.get_system_config(raw_key)
        cas_a = await self.db.ext.syscfg_cas(raw_key, "A_done", old)
        cas_b = await self.db.ext.syscfg_cas(raw_key, "B_done", old)
        winners = [w for w, ok in (("A", cas_a), ("B", cas_b)) if ok]
        self.assertEqual(len(winners), 1, f"交错下必须恰好一个赢家，实际 {winners}")
        self.assertEqual(await self.db.ext.get_system_config(raw_key), f"{winners[0]}_done")

    async def test_interleaved_spend_no_double_spend(self):
        """模拟双花：两笔 60 扣款对 100 余额只有一笔成功"""
        await self.db.ext.syscfg_adjust_number("t_doublespend", 100)
        r1 = await self.db.ext.syscfg_spend("t_doublespend", 60)
        r2 = await self.db.ext.syscfg_spend("t_doublespend", 60)
        self.assertTrue(r1)
        self.assertFalse(r2, "双花必须被拒绝")
        self.assertEqual(await self.db.ext.syscfg_get_number("t_doublespend"), 40)


if __name__ == "__main__":
    import faulthandler
    faulthandler.dump_traceback_later(45, exit=True)  # 防挂死：45 秒自动转储栈并退出
    unittest.main()
