import glob, re, sys
NEW = "astrbot_plugin_xiuxian_promax"
issues = []
for f in glob.glob('**/*', recursive=True):
    if f.startswith(('_', 'tests', '.serena', 'resources')):
        continue
    if not f.endswith(('.py', '.json', '.yaml', '.md')):
        continue
    try:
        t = open(f, encoding='utf-8').read()
    except Exception:
        continue
    # 先剔除合法引用：新名、迁移代码行、Zspor 仓库链接、README 升级说明
    t2 = t.replace(NEW, '@@NEW@@')
    t2 = re.sub(r'for old_name in \([^)]*\)', '', t2)
    t2 = t2.replace('https://github.com/Zspor/astrbot_plugin_monixiuxian2', '@@ZSPOR@@')
    for old in ('astrbot_plugin_monixiuxian2', 'astrbot_plugin_xiuxian'):
        for m in re.finditer(re.escape(old), t2):
            ctx = t2[max(0, m.start()-50):m.end()+50].replace('\n', ' ')
            if '从旧版' in ctx or '升级' in ctx:
                continue  # README 升级说明中的合法引用
            issues.append(f"[残留] {f}: ...{ctx[:100]}...")
if issues:
    print("发现残留：")
    for i in issues:
        print(" -", i)
    sys.exit(1)
print("无旧名残留 ✅")
