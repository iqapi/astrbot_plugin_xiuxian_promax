# 项目结构

## 四层架构

```
1. 入口层 (main.py)
   └─ 插件注册、命令路由、访问控制

2. 处理器层 (handlers/)
   ├─ player_handler.py         # 玩家操作（创建角色、信息查看、闭关、签到）
   ├─ equipment_handler.py      # 装备系统（装备、卸下、查看装备）
   ├─ breakthrough_handler.py   # 突破系统（突破信息、突破操作）
   ├─ pill_handler.py           # 丹药系统（服用、查看背包、丹药信息）
   ├─ shop_handler.py           # 商店系统（丹阁、器阁、百宝阁、购买）
   ├─ misc_handler.py           # 帮助信息
   └─ utils.py                  # 通用工具函数

3. 业务逻辑层 (core/)
   ├─ cultivation_manager.py    # 修炼系统（闭关、修为计算）
   ├─ equipment_manager.py      # 装备管理（装备逻辑、属性计算）
   ├─ breakthrough_manager.py   # 突破管理（突破逻辑、成功率计算）
   ├─ pill_manager.py           # 丹药管理（丹药效果、背包管理）
   └─ shop_manager.py           # 商店管理（商品生成、刷新、购买）

4. 数据层 (data/)
   ├─ data_manager.py           # 数据库操作（CRUD）
   └─ migration.py              # 数据库迁移系统
```

## 目录结构

```
astrbot_plugin_monixiuxian/
├── main.py                     # 插件入口点
├── models.py                   # 数据模型（Player, Item）
├── config_manager.py           # 配置管理器
├── _conf_schema.json           # 配置 Schema（AstrBot 配置界面）
├── metadata.yaml               # 插件元数据
├── AGENTS.md                   # 代码指南
├── README.md                   # 项目文档
├── LICENSE                     # 许可证文件
├── logo.png                    # 插件 Logo
│
├── handlers/                   # 命令处理器层
│   ├── __init__.py
│   ├── player_handler.py
│   ├── equipment_handler.py
│   ├── breakthrough_handler.py
│   ├── pill_handler.py
│   ├── shop_handler.py
│   ├── misc_handler.py
│   └── utils.py
│
├── core/                       # 业务逻辑层
│   ├── __init__.py
│   ├── cultivation_manager.py
│   ├── equipment_manager.py
│   ├── breakthrough_manager.py
│   ├── pill_manager.py
│   └── shop_manager.py
│
├── data/                       # 数据访问层
│   ├── __init__.py
│   ├── data_manager.py
│   └── migration.py
│
└── config/                     # 游戏配置文件
    ├── level_config.json       # 灵修境界配置
    ├── body_level_config.json  # 体修境界配置
    ├── weapons.json            # 武器配置
    ├── pills.json              # 破境丹配置
    ├── exp_pills.json          # 修为丹药配置
    ├── utility_pills.json      # 功能丹药配置
    └── items.json              # 其他物品配置
```

## 数据流

1. **消息接收**：AstrBot → main.py → 命令过滤器
2. **权限检查**：main.py → `_check_access()`
3. **命令处理**：main.py → handlers/
4. **业务逻辑**：handlers/ → core/
5. **数据操作**：core/ → data/ → SQLite
6. **配置读取**：所有层 → config_manager → config/
7. **消息返回**：使用异步生成器逐步返回结果

## 关键文件说明

- **main.py**：插件入口，定义所有命令及其处理流程
- **models.py**：定义 Player 和 Item 数据模型
- **config_manager.py**：统一管理所有 JSON 配置文件的读取
- **_conf_schema.json**：AstrBot Web 界面的配置表单定义
