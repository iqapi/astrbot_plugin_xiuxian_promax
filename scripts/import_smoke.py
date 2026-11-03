"""导入烟测：验证 20 个核心管理器模块可正常导入"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
PKG = ROOT.name

_a = types.ModuleType("astrbot")
_api = types.ModuleType("astrbot.api")
_api.logger = types.SimpleNamespace(info=lambda *a: None, warning=lambda *a: None,
                                    error=lambda *a: None, exception=lambda *a: None)
_api.AstrBotConfig = dict
_ev = types.ModuleType("astrbot.api.event")
_ev.AstrMessageEvent = object
_ev.MessageChain = object
_api.event = _ev
_al = types.ModuleType("astrbot.api.all")
_al.At = object
_al.Plain = object
_api.all = _al
_st = types.ModuleType("astrbot.api.star")
_st.Star = object
_st.Context = object
_st.StarTools = object
_api.star = _st
_fi = types.ModuleType("astrbot.api.filter")
_fi.filter = types.SimpleNamespace(command=lambda *a: lambda f: f)
_api.filter = _fi
sys.modules["astrbot"] = _a
sys.modules["astrbot.api"] = _api
sys.modules["astrbot.api.event"] = _ev
sys.modules["astrbot.api.all"] = _al
sys.modules["astrbot.api.star"] = _st
sys.modules["astrbot.api.filter"] = _fi

mods = [
    "managers.tower_manager", "managers.merit_manager", "managers.hunt_manager",
    "managers.enlighten_manager", "managers.wander_merchant_manager", "managers.ladder_manager",
    "managers.spirit_tide_manager", "managers.sect_raid_manager", "managers.memoir_manager",
    "managers.nest_defense_manager", "managers.dao_bet_manager", "managers.mentor_manager",
    "managers.pill_synth_manager", "managers.treasure_map_manager", "managers.redpacket_manager",
    "managers.title_auction_manager", "managers.weekly_report_manager",
    "managers.player_bounty_manager", "managers.loot_auction_manager", "managers.combat_manager",
]
ok = fail = 0
for m in mods:
    try:
        __import__(f"{PKG}.{m}", fromlist=["x"])
        ok += 1
    except Exception as e:
        print(f"FAIL: {m}: {e}")
        fail += 1
print(f"IMPORT_SMOKE: ok={ok} fail={fail}")
