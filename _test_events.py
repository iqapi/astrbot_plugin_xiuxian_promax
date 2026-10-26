# 事件池结构校验：py -3 -X utf8 _test_events.py
import ast, sys, types
ast.parse(open('managers/encounter_events.py', encoding='utf-8').read())
sys.modules.setdefault('astrbot', types.ModuleType('astrbot'))
api = types.ModuleType('astrbot.api')
api.logger = types.SimpleNamespace(info=lambda *a: None, warning=lambda *a: None, error=lambda *a: None)
sys.modules.setdefault('astrbot.api', api)
sys.path.insert(0, '..')
import os
from importlib import import_module as _im
PKG = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
EVENTS = _im(f"{PKG}.managers.encounter_events").EVENTS
print('events:', len(EVENTS))
assert len(EVENTS) >= 100, '事件数不足100'
keys = set()
for ev in EVENTS:
    assert len(ev['options']) == 3, ev['title']
    assert ev['key'] not in keys, f'重复key: {ev["key"]}'
    keys.add(ev['key'])
    for o in ev['options']:
        assert o['weight'] in ('risk', 'safe', 'good', 'evil', 'leave'), (ev['title'], o)
print('all events valid')
