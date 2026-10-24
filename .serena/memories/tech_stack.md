# 技术栈

## 编程语言
- Python 3.8+

## 框架与依赖
- **AstrBot**：消息处理框架，提供插件系统
- **aiosqlite**：异步 SQLite 数据库操作
- **dataclasses**：数据模型定义
- **typing**：类型提示支持

## 核心技术特性
1. ✅ 全异步架构（async/await）
2. ✅ 异步生成器模式（async for yield）
3. ✅ 装饰器驱动的数据库迁移
4. ✅ 数据类模型（@dataclass）
5. ✅ 配置化的游戏数值
6. ✅ 类型提示（Type Hints）

## 数据存储
- SQLite 数据库文件：xiuxian_data_lite.db
- JSON 配置文件：存储在 config/ 目录

## 配置文件
```
config/
├── level_config.json          # 灵修境界配置（增量模式）
├── body_level_config.json     # 体修境界配置
├── weapons.json               # 武器库
├── pills.json                 # 破境丹配置
├── exp_pills.json             # 修为丹药配置
├── utility_pills.json         # 功能丹药配置
└── items.json                 # 其他物品
```
