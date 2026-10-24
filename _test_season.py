# 季节系统实测：py -3 -X utf8 _test_season.py
import sys, types
sys.modules.setdefault('astrbot', types.ModuleType('astrbot'))
api = types.ModuleType('astrbot.api')
api.logger = types.SimpleNamespace(info=lambda *a: None, warning=lambda *a: None, error=lambda *a: None)
sys.modules.setdefault('astrbot.api', api)
sys.path.insert(0, '..')
import os
from importlib import import_module as _im
PKG = os.path.basename(os.path.dirname(os.path.abspath(__file__)))  # 自动探测项目目录名
_sfm = _im(f"{PKG}.managers.spirit_farm_manager")
get_current_season = _sfm.get_current_season
get_current_season_index = _sfm.get_current_season_index
get_season_growth_mult = _sfm.get_season_growth_mult
get_season_yield_mult = _sfm.get_season_yield_mult

s = get_current_season()
print('当前季节索引:', get_current_season_index())
print('当前季节:', s['icon'], s['name'], '-', s['desc'])
for herb in ('灵草', '冰心草', '火焰花', '九叶灵芝', '冰火双生花'):
    print(f'  {herb} 生长倍率: x{get_season_growth_mult(herb)}')
print('产量倍率: x', get_season_yield_mult())
