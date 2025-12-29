# Alembic 迁移重置指南

## 概述

当 Alembic 迁移历史混乱时，使用此流程重置到干净状态。本指南提供了负责人重置和团队成员同步的完整流程。

## 🎯 快速开始

### 负责人操作（一次性重置）

```bash
# 1. 删除旧迁移文件
rm migrations/versions/*.py

# 2. 生成新的初始迁移
alembic revision --autogenerate -m "initial migration"

# 3. 提交到仓库
git add migrations/versions/
git commit -m "chore: reset alembic migrations to clean state"
git push origin dev
```

### 团队成员同步

```bash
# 1. 拉取最新代码
git pull origin dev

# 2. 运行重置脚本（自动化处理一切）
python scripts/reset_database.py
```

完成！✅ 你的数据库已经和团队统一。

## 📖 脚本说明

### `scripts/reset_database.py` 智能重置流程

#### 工作流程
1. **删除项目表** - 只删除项目相关的表，保护数据库中的其他表
2. **删除版本表** - 清除 `alembic_version` 表，准备重新标记
3. **检查迁移文件** - 智能判断是否需要生成迁移
   - ✅ **有迁移文件**：直接执行 `alembic upgrade head`
   - ⚠️ **无迁移文件**：自动生成初始迁移，然后执行
4. **插入默认数据** - 自动插入默认实体类型（时间、地点、人物等）

#### 设计优势
- 🔒 **安全**：保护非项目表，只操作项目相关的表
- 🤖 **智能**：自动检测环境，无需手动判断
- 🎯 **简单**：一条命令完成所有操作
- 🔄 **统一**：团队成员使用相同的迁移文件

#### 数据库时区配置
- 所有数据库连接自动设置为 **UTC 时区**（`+00:00`）
- 时间字段使用 `NOW()` 函数，返回 UTC 时间
- 确保跨时区的数据一致性

## 日常开发规范

### 创建新迁移

```bash
# 1. 同步最新代码
git pull origin dev
alembic upgrade head

# 2. 修改模型文件
# 编辑 dataflow/db/models.py

# 3. 生成迁移
alembic revision --autogenerate -m "add xxx field"

# 4. 检查生成的文件
# 打开 migrations/versions/xxxxx.py 确认正确

# 5. 测试
alembic upgrade head
alembic downgrade -1
alembic upgrade head

# 6. 提交（尽快提交避免冲突）
git add migrations/versions/*.py
git commit -m "feat: add xxx"
git push
```

### 同步他人的迁移

```bash
git pull
alembic upgrade head
```

### 避免冲突

- ✅ 每天开始工作前：`git pull && alembic upgrade head`
- ✅ 一个迁移只改一件事
- ✅ 生成迁移后立即提交推送
- ✅ 修改重要模型前在群里说一声

### 遇到冲突

如果 `git pull` 后发现有新迁移，但你也创建了迁移：

```bash
# 1. 删除你的迁移
rm migrations/versions/你的文件.py

# 2. 升级到最新
alembic upgrade head

# 3. 重新生成
alembic revision --autogenerate -m "你的描述"

# 4. 提交
git add migrations/versions/*.py
git commit -m "..."
git push
```

## 常用命令

```bash
# 查看当前版本
alembic current

# 查看迁移历史
alembic history

# 升级到最新
alembic upgrade head

# 回滚一个版本
alembic downgrade -1

# 回滚到指定版本
alembic downgrade <revision_id>
```

## 🔧 问题排查

### 提示多个 head

```bash
# 1. 查看所有 head 分支
alembic heads

# 2. 创建合并迁移
alembic merge heads -m "merge branches"

# 3. 升级到最新
alembic upgrade head
```

### 迁移和数据库不同步

```bash
# 重新同步数据库
python scripts/reset_database.py
```

### 迁移文件生成错误

```bash
# 1. 删除错误的迁移文件
rm migrations/versions/错误的文件.py

# 2. 重新生成
alembic revision --autogenerate -m "描述"
```

### 时区相关问题

数据库已配置为 UTC 时区，如需验证：

```python
# 创建测试脚本
from sqlalchemy import text
from dataflow.db import get_session_factory

async def test():
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("SELECT @@session.time_zone, NOW(), UTC_TIMESTAMP()")
        )
        print(result.fetchone())
```

应该显示：`('+00:00', 当前UTC时间, 相同的UTC时间)`

### 遇到其他问题

1. 检查日志输出，查找具体错误信息
2. 确认数据库连接配置正确（`.env` 文件）
3. 联系团队负责人协调解决

## 📝 附录

### 项目表列表

当前项目定义的表（12个）：
- `source_config` - 信息源配置
- `article` - 文章表
- `article_section` - 文章片段
- `entity_type` - 实体类型定义
- `entity` - 实体表
- `event_entity` - 事项-实体关联
- `source_event` - 源事件
- `source_chunk` - 来源片段聚合
- `model_config` - 模型配置
- `task` - 任务表
- `chat_conversation` - 聊天会话
- `chat_message` - 聊天消息

### 配置文件位置

- **数据库配置**：`dataflow/core/config/settings.py`
- **模型定义**：`dataflow/db/models.py`
- **Alembic 配置**：`alembic.ini`
- **迁移环境**：`migrations/env.py`
- **迁移文件**：`migrations/versions/*.py`
