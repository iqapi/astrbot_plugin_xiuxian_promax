# 开发常用命令

## 系统信息
本项目运行在 **Windows** 系统上。

## Windows 系统命令

### 文件和目录操作
```powershell
# 列出目录内容
dir
dir /s          # 递归列出子目录

# 查看文件内容
type <filename>

# 创建目录
mkdir <dirname>

# 删除文件
del <filename>

# 删除目录
rmdir /s <dirname>

# 复制文件
copy <source> <dest>

# 移动文件
move <source> <dest>
```

### 文本搜索
```powershell
# 在文件中搜索文本
findstr /s /i "pattern" *.py

# 查找文件
dir /s /b *pattern*
```

### Git 操作
```bash
# 查看状态
git status

# 查看差异
git diff

# 添加文件
git add .

# 提交
git commit -m "message"

# 推送
git push

# 拉取
git pull

# 查看日志
git log --oneline
```

## Python 相关

### 运行 Python 脚本
```bash
python <script.py>
python -m <module>
```

### 包管理
```bash
# 安装依赖（如果有 requirements.txt）
pip install -r requirements.txt

# 安装特定包
pip install <package>

# 查看已安装包
pip list
```

## 插件开发

### 测试插件
由于这是 AstrBot 插件，需要通过 AstrBot 框架加载测试：
1. 将插件目录放置在 AstrBot 的插件目录中
2. 启动 AstrBot
3. 在聊天界面测试命令

### 数据库操作
```bash
# 查看数据库（需要 SQLite 工具）
sqlite3 xiuxian_data_lite.db

# SQLite 常用命令
.tables          # 查看所有表
.schema <table>  # 查看表结构
SELECT * FROM players;  # 查询数据
.quit           # 退出
```

## 代码检查与格式化

目前项目没有配置自动化的 linting 或格式化工具，但可以手动安装：

```bash
# 安装代码检查工具
pip install pylint
pip install flake8

# 运行检查
pylint main.py
flake8 .

# 安装格式化工具
pip install black

# 格式化代码
black .
```

## 日常开发流程

1. **修改代码**：使用代码编辑器编辑文件
2. **检查语法**：确保 Python 语法正确
3. **测试功能**：在 AstrBot 中加载插件测试
4. **提交代码**：使用 git 提交更改
5. **更新版本**：修改 metadata.yaml 和 README.md 中的版本号

## 注意事项

- 修改配置文件后，需要重启 AstrBot 才能生效
- 数据库迁移会在插件初始化时自动执行
- 配置 schema 的修改需要重启 AstrBot Web 界面
- Windows 路径使用反斜杠 `\` 或双反斜杠 `\\`
