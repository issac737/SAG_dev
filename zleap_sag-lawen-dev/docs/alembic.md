# Alembic 数据库迁移指南

Alembic 是 SQLAlchemy 的数据库迁移工具，用于管理数据库 schema 的版本变更。

## 常用命令

```bash
# 查看当前版本
alembic current

# 查看迁移历史
alembic history

# 自动生成迁移脚本（推荐）
alembic revision --autogenerate -m "描述修改内容"

# 执行迁移到最新版本
alembic upgrade head

# 回滚一个版本
alembic downgrade -1
```

## 典型工作流

### 1. 修改数据库模型

编辑 `dataflow/db/models.py`，添加或修改字段：

```python
class Article(Base):
    # ... 现有字段
    new_field = Column(String(255), nullable=True)  # 新增字段
```

### 2. 生成迁移脚本

```bash
alembic revision --autogenerate -m "add new_field to article"
```

### 3. 检查生成的脚本

查看 `migrations/versions/` 目录下新生成的文件，确认迁移逻辑正确。

### 4. 执行迁移

```bash
alembic upgrade head
```

### 5. 验证修改

检查数据库 schema 是否正确更新。

## 常用命令详解

| 命令 | 说明 |
|------|------|
| `alembic current` | 查看当前数据库版本 |
| `alembic history` | 查看所有迁移历史 |
| `alembic upgrade head` | 升级到最新版本 |
| `alembic upgrade +1` | 升级一个版本 |
| `alembic downgrade -1` | 回滚一个版本 |
| `alembic downgrade base` | 回滚到初始状态 |
| `alembic revision -m "描述"` | 手动创建空白迁移 |
| `alembic revision --autogenerate -m "描述"` | 自动生成迁移 |

## 项目配置

### 配置文件

- **alembic.ini** - Alembic 主配置文件
- **migrations/env.py** - 迁移环境配置
- **migrations/versions/** - 迁移脚本存放目录

### 数据库连接

项目使用 `dataflow.core.config.get_settings()` 自动获取数据库连接：
- 从项目配置读取 MySQL URL
- 自动将异步驱动（aiomysql）转换为同步驱动（pymysql）

## 迁移文件示例

当前项目中的迁移示例（`migrations/versions/e1cfcabde2f6_*.py`）：

```python
"""add status and error fields to article

Revision ID: e1cfcabde2f6
Revises: 
Create Date: 2025-10-28 20:04:18
"""
from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    """升级 schema"""
    op.add_column('article', sa.Column('error', sa.Text(), nullable=True))

def downgrade() -> None:
    """回滚 schema"""
    op.drop_column('article', 'error')
```

## 注意事项

### ⚠️ 生产环境

1. **执行前备份**
   ```bash
   # 先备份数据库
   mysqldump -u user -p database > backup.sql
   
   # 再执行迁移
   alembic upgrade head
   ```

2. **先在测试环境验证**
   - 在开发/测试环境先执行迁移
   - 确认无误后再在生产环境执行

### ⚠️ 自动生成的局限

`autogenerate` 不能检测：
- 表名变更
- 列名变更（会识别为删除+新增）
- 某些约束变更

**建议**：生成后检查并手动调整脚本。

### ⚠️ 团队协作

1. **提交迁移脚本**
   - 迁移脚本要一起提交到 git
   - 确保团队成员能同步 schema 变更

2. **避免冲突**
   - 多人同时创建迁移时可能冲突
   - 沟通协调，避免并行修改同一表

3. **部署流程**
   ```bash
   git pull
   alembic upgrade head  # 先执行迁移
   # 再启动应用
   ```

## 高级操作

### 合并迁移分支

如果出现迁移分支：

```bash
alembic merge <revision1> <revision2> -m "merge migrations"
```

### 标记版本（不执行SQL）

```bash
# 将数据库标记为指定版本（谨慎使用）
alembic stamp head
```

### 查看SQL预览

```bash
# 查看升级SQL但不执行
alembic upgrade head --sql

# 查看回滚SQL
alembic downgrade -1 --sql
```

## 故障排除

### 问题：迁移失败

```bash
# 查看当前状态
alembic current

# 如果部分执行失败，手动修复数据库后
alembic stamp <target_revision>
```

### 问题：需要重新生成

```bash
# 删除错误的迁移文件
rm migrations/versions/<revision_id>_*.py

# 重新生成
alembic revision --autogenerate -m "新描述"
```

## 相关资源

- [Alembic 官方文档](https://alembic.sqlalchemy.org/)
- 项目模型定义：`dataflow/db/models.py`
- 项目迁移脚本：`migrations/versions/`
- 数据库配置：`dataflow/core/config/settings.py`

