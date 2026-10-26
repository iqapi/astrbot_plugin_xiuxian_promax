# 图生成器 v3：英文ID（修复 Mermaid 中文ID解析失败）+ 独立文档 + README 折叠引用
import json
import re

clusters = json.load(open('_clusters.json', encoding='utf-8'))
others = clusters.pop("其他", [])
reassign = {
    "仙灵": ["仙灵结缘", "仙灵共修", "仙灵解除", "仙灵代收"],
    "师徒": ["拜师", "出师", "逐出师门", "师徒", "师德兑换"],
    "称号图鉴": ["称号图鉴", "佩戴称号", "我的称号"],
    "魔潮天灾": ["开启魔潮", "魔潮状态", "抵御魔潮", "仙界日历"],
    "化身托管": ["激活化身"],
    "押镖劫道": ["押镖", "完成押镖", "放弃押镖", "劫镖"],
    "功德因果": ["行善"],
    "管理工具": ["仙界管理"],
    "生活职业": ["选择生活职业", "制符"],
    "奇遇": ["奇遇选择"],
    "洞天装修": ["洞天装修"],
    "宗门建筑": ["宗门建筑", "升级建筑"],
}
for target, names in reassign.items():
    got = [n for n in others if n in names]
    if got:
        clusters.setdefault(target, []).extend(got)
        for n in got:
            others.remove(n)
if others:
    clusters.setdefault("其他扩展", []).extend(others)

SYSTEM_NODES = ["称号图鉴", "奇遇系统", "智能提示引擎", "功德因果", "师徒系统", "仙灵道侣", "日常任务", "悬赏系统"]
LINKS = [
    ("修炼突破", "称号图鉴", "境界称号"),
    ("修炼突破", "师徒系统", "师德+5"),
    ("修炼突破", "智能提示引擎", "下一步指引"),
    ("闭关", "智能提示引擎", None),
    ("签到", "智能提示引擎", None),
    ("开始历练", "奇遇系统", "20%触发"),
    ("完成历练", "悬赏系统", None),
    ("完成历练", "称号图鉴", None),
    ("完成探索", "奇遇系统", "25%触发"),
    ("完成探索", "日常任务", None),
    ("购买", "储物戒", None),
    ("购买", "丹药", None),
    ("完成押镖", "悬赏系统", None),
    ("完成押镖", "功德因果", None),
    ("劫镖", "功德因果", "业力"),
    ("挑战世界Boss", "日常任务", None),
    ("挑战世界Boss", "称号图鉴", None),
    ("抵御魔潮", "功德因果", None),
    ("查验天魔", "称号图鉴", None),
    ("仙灵结缘", "仙灵道侣", None),
    ("仙灵结缘", "双修", "互斥"),
    ("仙灵代收", "仙灵道侣", None),
    ("大比切磋", "称号图鉴", None),
    ("飞升", "称号图鉴", None),
    ("行善", "功德因果", None),
    ("炼丹", "称号图鉴", None),
    ("炼丹", "智能提示引擎", None),
]

# ===== 英文 ID 映射（中文 label 保留）=====
pinyin = {
    "帮助工具": "help", "玩家基础": "player", "装备": "equip", "修炼突破": "breakthrough",
    "丹药": "pill", "商店": "shop", "储物戒": "ring", "宗门": "sect",
    "旧Boss": "oldboss", "战斗PVP": "pvp", "排行榜": "ranking", "秘境": "rift",
    "历练": "adventure", "炼丹": "alchemy", "传承": "impart", "道号": "nickname",
    "银行": "bank", "悬赏": "bounty", "传承PK": "impartpk", "洞天": "land",
    "灵田": "farm", "双修": "dual", "灵眼": "eye", "日常任务": "dailytask",
    "世界Boss": "worldboss", "掠夺": "robbery", "飞升转生": "reinc",
    "赌石黑市": "gamble", "炼器": "forge", "天魔入侵": "demon", "灵兽": "pet",
    "坊市": "auction", "其他扩展": "misc2", "管理工具": "admintool",
    "称号图鉴": "title", "奇遇": "encounter", "仙灵": "spirit", "师徒": "mentor",
    "魔潮天灾": "tide", "化身托管": "avatar", "押镖劫道": "escort",
    "功德因果": "karma", "生活职业": "lifeskill", "洞天装修": "furnish",
    "宗门建筑": "sectbuild",
}
sys_ids = {"称号图鉴": "sys_title", "奇遇系统": "sys_encounter", "智能提示引擎": "sys_advisor",
           "功德因果": "sys_karma", "师徒系统": "sys_mentor", "仙灵道侣": "sys_spirit",
           "日常任务": "sys_daily", "悬赏系统": "sys_bounty"}

node_ids = {}   # 中文名 -> 英文ID
for c, names in clusters.items():
    cbase = pinyin.get(c, 'g' + str(len(node_ids)))
    for n in names:
        node_ids[n] = f'{cbase}_{len(node_ids)}'
for s in SYSTEM_NODES:
    node_ids[s] = sys_ids[s]

def nid(name):
    return node_ids[name]

# ===== Mermaid（英文ID + 中文label）=====
mm = ['graph LR',
      '  classDef sys fill:#6a5520,stroke:#ffd700,stroke-width:2px,color:#fff,font-weight:bold;']
for c, names in clusters.items():
    cid = pinyin.get(c, 'g' + str(abs(hash(c)) % 1000))
    mm.append(f'  subgraph {cid}["{c}"]')
    for n in names:
        mm.append(f'    {nid(n)}["{n}"]')
    mm.append('  end')
for s in SYSTEM_NODES:
    mm.append(f'  {nid(s)}{{"⚙ {s}"}}:::sys')
for a, b, label in LINKS:
    lbl = f'|{label}|' if label else ''
    mm.append(f'  {nid(a)} -->{lbl} {nid(b)}')
mermaid_body = '\n'.join(mm)

# ===== 独立文档 docs/command_graph.md（GitHub 渲染）=====
import os
os.makedirs('docs', exist_ok=True)
md = f'''# 🗺️ 指令逻辑有向图

> **167 指令 · {len(clusters)} 系统 · 7 个联动引擎**  
> 金色 3D 节点为联动引擎：它们不对应具体指令，而是被各玩法调用、驱动长线成长的中枢系统。  
> 边上的标签表示联动语义（如"境界称号"表示突破会触发称号颁发）。

```mermaid
{mermaid_body}
```

## 联动关系速查

| 源玩法 | 联动引擎 | 语义 |
|--------|---------|------|
| 修炼突破 | 称号图鉴 | 按境界颁发称号 |
| 修炼突破 | 师徒系统 | 弟子突破，师父+师德 |
| 修炼突破 | 智能提示引擎 | 突破后推荐下一步 |
| 开始历练 / 完成探索 | 奇遇系统 | 概率触发三选一事件 |
| 完成历练 / 完成押镖 / 挑战世界Boss / 炼丹 / 切磋 | 悬赏系统 | 推进对应悬赏进度 |
| 劫镖 / 潜入洞府 | 功德因果 | 增加业力 |
| 行善 / 抵御魔潮 | 功德因果 | 增加功德 |
| 仙灵结缘 | 双修 | 互斥约束（防止收益叠加）|
| 仙灵代收 | 仙灵道侣 | 消耗情缘代收洞天 |
| 大比切磋 / 飞升 / 查验天魔 | 称号图鉴 | 专属称号路径 |
| 闭关 / 签到 | 智能提示引擎 | 日常清单指引 |
'''
open('docs/command_graph.md', 'w', encoding='utf-8').write(md)

# ===== 修复 HTML（英文ID）=====
html = f'''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>修仙插件 · 指令逻辑有向图</title>
<style>
  body {{ background:#1a1a2e; color:#eee; font-family:"Microsoft YaHei",sans-serif; margin:0; padding:20px; }}
  h1 {{ color:#ffd700; text-align:center; }}
  .meta {{ text-align:center; color:#aaa; margin-bottom:20px; }}
  .graph {{ background:#12121f; border-radius:12px; padding:24px; overflow:auto; border:1px solid #c6a15b44; }}
</style>
</head>
<body>
<h1>🗺️ 修仙插件 · 指令逻辑有向图</h1>
<div class="meta">167 指令 · {len(clusters)} 系统 · 金色3D框为联动引擎 · v6.18</div>
<div class="graph">
<pre class="mermaid">
{mermaid_body}
</pre>
</div>
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
  mermaid.initialize({{ startOnLoad: true, theme: 'dark', securityLevel: 'loose' }});
</script>
</body>
</html>'''
open('docs_command_graph.html', 'w', encoding='utf-8').write(html)

# ===== DOT 同步（英文ID）=====
dot = ['digraph Xiuxian {',
       '  rankdir=LR; splines=true; overlap=false;',
       '  graph [fontname="Microsoft YaHei", bgcolor="#1a1a2e", fontcolor="#eee", label="修仙插件 · 指令逻辑有向图 (167指令)", labelloc=t, fontsize=22];',
       '  node [fontname="Microsoft YaHei", style="rounded,filled", color="#c6a15b", fontcolor="#eee"];',
       '  edge [color="#c6a15b88", fontcolor="#aaa"];']
for c, names in clusters.items():
    dot.append(f'  subgraph cluster_{pinyin.get(c, "g" + str(abs(hash(c)) % 1000))} {{')
    dot.append(f'    label="{c}"; style="rounded,filled"; fillcolor="#ffffff10"; color="#c6a15b88";')
    for n in names:
        dot.append(f'    {nid(n)} [label="{n}"];')
    dot.append('  }')
for s in SYSTEM_NODES:
    dot.append(f'  {nid(s)} [label="⚙ {s}", shape=box3d, fillcolor="#6a5520", color="#ffd700"];')
for a, b, label in LINKS:
    lbl = f' [label="{label}"]' if label else ''
    dot.append(f'  {nid(a)} -> {nid(b)}{lbl};')
dot.append('}')
open('docs_command_graph.dot', 'w', encoding='utf-8').write(dot and '\n'.join(dot))

# ===== README 折叠引用 =====
r = open('README.md', encoding='utf-8').read()
marker = '## 📜 许可证'
graph_section = '''## 🗺️ 指令逻辑有向图

整个项目的指令因果网：**167 条指令 · 32 个系统 · 7 个联动引擎**。

<details>
<summary><b>📍 点击展开完整逻辑图（GitHub 原生渲染 Mermaid）</b></summary>

```mermaid
{mermaid_body}
```

</details>

> 📖 也可以查看 [docs/command_graph.md](docs/command_graph.md)（含联动关系速查表）  
> 🖼️ 交互版：下载 [docs_command_graph.html](docs_command_graph.html) 用浏览器打开

---

'''
assert marker in r
r = r.replace(marker, graph_section + marker, 1)
open('README.md', 'w', encoding='utf-8').write(r)

print(f'完成: 英文ID图（{len(clusters)}系统）+ docs/command_graph.md + README折叠引用 + HTML修复')
