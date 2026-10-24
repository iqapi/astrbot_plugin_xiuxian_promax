# 渲染器冒烟测试（脱离 astrbot 依赖，直接测纯渲染部分）
import sys, types, os

# stub astrbot.api.logger，使 image_generator 可脱离框架导入
stub = types.ModuleType('astrbot')
api = types.ModuleType('astrbot.api')
class _L:
    def info(self, *a): print('[info]', *a)
    def warning(self, *a): print('[warn]', *a)
    def error(self, *a): print('[error]', *a)
api.logger = _L()
sys.modules['astrbot'] = stub
sys.modules['astrbot.api'] = api

from utils.image_generator import render_card

path = render_card(
    "info",
    "测试道友的信息",
    "ID: 10000 · 筑基期",
    sections=[
        {"name": "基础", "rows": [
            ("职业", "剑修"), ("境界", "筑基期"),
            ("修为", "123,456/200,000"), ("灵石", "88,888"),
            ("功德/业力", "+3"), ("生活职业", "符箓师"),
        ]},
        {"name": "属性", "rows": [
            ("气血", "5,000/5,000"), ("物伤/法伤", "800/120"),
            ("精神力", "300"),
        ]},
        {"name": "一段很长的整行文本测试截断逻辑", "lines": [
            "金克木、木克土、土克水、水克火、火克金 —— 五行流转，相生相克。",
            "测试第二行。",
        ]},
    ],
    footer="模拟修仙 · 冒烟测试",
)
if path and os.path.exists(path):
    print("RENDER OK ->", path, os.path.getsize(path), "bytes")
else:
    print("RENDER FAILED")
