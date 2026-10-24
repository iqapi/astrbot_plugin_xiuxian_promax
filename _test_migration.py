# 迁移真实验证：py -3 -X utf8 _test_migration.py
# 覆盖两条路径：1) 全新建库（v2建表+补列） 2) 模拟用户坏库（version=28但缺新列）
import asyncio
import sys
import types
import os
import tempfile
import sqlite3

sys.modules.setdefault('astrbot', types.ModuleType('astrbot'))
api = types.ModuleType('astrbot.api')
api.logger = types.SimpleNamespace(info=lambda *a: print('[info]', *a), warning=lambda *a: print('[warn]', *a), error=lambda *a: print('[error]', *a))
sys.modules.setdefault('astrbot.api', api)
sys.path.insert(0, '..')
import os as _os
PKG = _os.path.basename(_os.path.dirname(_os.path.abspath(__file__)))
from importlib import import_module as _im
mig = _im(f'{PKG}.data.migration')

REQUIRED_COLUMNS = {
    'players': ['karma', 'life_skill'],
    'spirit_farms': ['fertility'],
    'blessed_lands': ['furniture'],
    'sects': ['buildings'],
}


def check_columns(db_path):
    ok = True
    conn = sqlite3.connect(db_path)
    for tbl, cols in REQUIRED_COLUMNS.items():
        existing = {r[1] for r in conn.execute(f'PRAGMA table_info({tbl})')}
        for c in cols:
            present = c in existing
            if not present:
                ok = False
            print(f'  {tbl}.{c}: {"OK" if present else "MISSING"}')
    conn.close()
    return ok


async def main():
    tmp = tempfile.mkdtemp(prefix='xiuxian_mig_')

    # 路径1：全新建库
    db1 = os.path.join(tmp, 'fresh.db')
    conn = await mig.__dict__['aiosqlite'].connect(db1) if 'aiosqlite' in mig.__dict__ else None
    # migration.py 导入了哪些取决于顶部 import——直接用 aiosqlite
    import aiosqlite
    conn = await aiosqlite.connect(db1)
    mm = mig.MigrationManager(conn, None)
    await mm.migrate()
    await conn.close()
    print('路径1 全新建库:')
    ok1 = check_columns(db1)

    # 路径2：模拟用户坏库（表结构缺新列，但 version 已是 28）
    db2 = os.path.join(tmp, 'broken.db')
    raw = sqlite3.connect(db2)
    raw.execute("CREATE TABLE db_info (version INTEGER NOT NULL)")
    raw.execute("INSERT INTO db_info VALUES (28)")
    raw.execute("CREATE TABLE players (user_id TEXT PRIMARY KEY, experience INTEGER DEFAULT 0)")
    raw.execute("CREATE TABLE spirit_farms (id INTEGER PRIMARY KEY, user_id TEXT, crops TEXT)")
    raw.execute("CREATE TABLE blessed_lands (id INTEGER PRIMARY KEY, user_id TEXT)")
    raw.execute("CREATE TABLE sects (sect_id INTEGER PRIMARY KEY, sect_name TEXT)")
    raw.commit(); raw.close()

    conn2 = await aiosqlite.connect(db2)
    mm2 = mig.MigrationManager(conn2, None)
    await mm2.migrate()
    await conn2.close()
    print('路径2 坏库修复:')
    ok2 = check_columns(db2)

    print('=' * 40)
    print('迁移验证 ' + ('全部通过 ✅' if (ok1 and ok2) else 'FAILED ❌'))
    sys.exit(0 if (ok1 and ok2) else 1)

asyncio.run(main())
