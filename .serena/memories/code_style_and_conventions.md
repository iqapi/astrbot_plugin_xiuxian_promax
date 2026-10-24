# 代码风格与规范

## 命名约定

### 常量命名
- 使用全大写字母 + 下划线分隔
- 例如：`CMD_HELP`, `CMD_START_XIUXIAN`, `BASE_EXP_PER_MINUTE`

### 类命名
- 使用驼峰命名法（PascalCase）
- 例如：`XiuXianPlugin`, `PlayerHandler`, `CultivationManager`

### 函数和变量命名
- 使用小写字母 + 下划线分隔（snake_case）
- 例如：`handle_help()`, `get_level()`, `cultivation_start_time`

### 私有方法
- 使用单下划线前缀
- 例如：`_check_access()`, `_send_access_denied_message()`

## 代码结构

### 数据模型
- 使用 `@dataclass` 装饰器定义数据类
- 为所有字段提供类型提示
- 示例：
```python
@dataclass
class Player:
    user_id: str
    level_index: int = 0
    spiritual_root: str = "未知"
```

### 异步编程
- 所有涉及 I/O 操作的函数都使用 async/await
- 消息处理器使用异步生成器模式：
```python
async def handle_xxx(self, event: AstrMessageEvent):
    async for r in self.handler.some_method(event):
        yield r
```

### 类型提示
- 导入类型时使用 TYPE_CHECKING 避免循环导入
- 为函数参数和返回值提供类型提示
- 使用 Optional、List 等泛型类型

### 装饰器模式
- 使用 `@register()` 注册插件
- 使用 `@filter.command()` 注册命令处理器
- 使用 `@migration()` 注册数据库迁移

## 文档字符串
- 类和复杂函数应提供简洁的文档字符串
- 使用中文描述
- 示例：`"""修仙插件 - 文字修仙游戏"""`

## 错误处理
- 使用 try-except 处理可能的错误
- 适当时静默处理错误（如发送消息失败）

## 代码组织
- 常量定义在文件顶部
- 导入语句按标准库、第三方库、本地模块顺序组织
- 相关功能按逻辑分组
