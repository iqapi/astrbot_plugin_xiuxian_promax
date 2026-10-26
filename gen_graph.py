# docs_command_graph 生成器 v2（完整独立版）
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

def safe(s):
    return re.sub(r'\W', '_', s)

# ===== DOT =====
dot = ['digraph Xiuxian {',
       '  rankdir=LR; splines=true; overlap=false;',
       '  graph [fontname="Microsoft YaHei", bgcolor="#1a1a2e", fontcolor="#eee", label="修仙插件 · 指令逻辑有向图 (167指令/32系统)", labelloc=t, fontsize=22];',
       '  node [fontname="Microsoft YaHei", style="rounded,filled", color="#c6a15b", fontcolor="#eee"];',
       '  edge [color="#c6a15b88", fontcolor="#aaa"];']
for c, names in clusters.items():
    dot.append(f'  subgraph cluster_{safe(c)} {{')
    dot.append(f'    label="{c}"; style="rounded,filled"; fillcolor="#ffffff10"; color="#c6a15b88";')
    for n in names:
        dot.append(f'    n_{safe(n)} [label="{n}"];')
    dot.append('  }')
for s in SYSTEM_NODES:
    dot.append(f'  s_{safe(s)} [label="⚙ {s}", shape=box3d, fillcolor="#6a5520", color="#ffd700"];')
for a, b, label in LINKS:
    na = 's_' + safe(a) if a in SYSTEM_NODES else 'n_' + safe(a)
    nb = 's_' + safe(b) if b in SYSTEM_NODES else 's_' + safe(b)
    lbl = f' [label="{label}"]' if label else ''
    dot.append(f'  {na} -> {nb}{lbl};')
dot.append('}')
open('docs_command_graph.dot', 'w', encoding='utf-8').write('\n'.join(dot))

# ===== Mermaid =====
mm = ['graph LR', '  classDef sys fill:#6a5520,stroke:#ffd700,stroke-width:2px,color:#fff;']
for c, names in clusters.items():
    cid = safe(c)
    mm.append(f'  subgraph {cid}["{c}"]')
    for n in names:
        mm.append(f'    {safe(n)}["{n}"]')
    mm.append('  end')
for s in SYSTEM_NODES:
    mm.append(f'  {safe(s)}{{"⚙ {s}"}}:::sys')
for a, b, label in LINKS:
    lbl = f'|{label}|' if label else ''
    mm.append(f'  {safe(a)} -->{lbl} {safe(b)}')
open('docs_command_graph.mmd', 'w', encoding='utf-8').write('\n'.join(mm))

# ===== HTML =====
mermaid_body = '\n'.join(mm[1:])
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

print(f'三格式完成: .dot / .mmd / .html | {len(clusters)} 系统 {sum(len(v) for v in clusters.values())} 指令')
