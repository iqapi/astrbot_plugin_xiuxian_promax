# 探测 noto-emoji 仓库的真实 tag/路径
import urllib.request, json

req = urllib.request.Request(
    'https://api.github.com/repos/googlefonts/noto-emoji/tags?per_page=10',
    headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=60) as r:
    tags = json.load(r)
for t in tags[:8]:
    print(t['name'])
