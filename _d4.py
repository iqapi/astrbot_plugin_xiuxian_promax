import json
sr = json.load(open('config/storage_rings.json', encoding='utf-8'))
print('储物戒配置条数:', len(sr))
for k, v in list(sr.items())[:12]:
    print(k, v.get('name'), '| 容量', v.get('capacity'), '| 品阶', v.get('rank'), '| 价格', v.get('price'), '| 需境界', v.get('required_level_index'))
