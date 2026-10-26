# 迁移真实验证：py -3 -X utf8 _test_migration.py
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
    'players': ['karma', 'life_skill', 'virtue_points'],
    'spirit_farms': ['fertility'],
    'blessed_lands': ['furniture'],
    'sects': ['buildings'],
}
REQUIRED_TABLES = ['npc_partners', 'master_relations']


def check(db_path):
    ok = True
    conn = sqlite3.connect(db_path)
    for tbl, cols in REQUIRED_COLUMNS.items():
        existing = {r[1] for r in conn.execute(f'PRAGMA table_info({tbl})')}
        for c in cols:
            present = c in existing
            if not present:
                ok = False
            print(f'  {tbl}.{c}: {"OK" if present else "MISSING"}')
    for tbl in REQUIRED_TABLES:
        exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tbl,)).fetchone()
        if not exists:
            ok = False
        print(f'  表 {tbl}: {"OK" if exists else "MISSING"}')
    conn.close()
    return ok


async def main():
    import aiosqlite
    tmp = tempfile.mkdtemp(prefix='xiuxian_mig_')

    db1 = os.path.join(tmp, 'fresh.db')
    conn = await aiosqlite.connect(db1)
    await mig.MigrationManager(conn, None).migrate()
    await conn.close()
    print('路径1 全新建库:')
    ok1 = check(db1)

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
    await mig.MigrationManager(conn2, None).migrate()
    await conn2.close()
    print('路径2 坏库修复:')
    ok2 = check(db2)

    print('=' * 40)
    print('迁移验证 ' + ('全部通过 ✅' if (ok1 and ok2) else 'FAILED ❌'))
    sys.exit(0 if (ok1 and ok2) else 1)

asyncio.run(main())
