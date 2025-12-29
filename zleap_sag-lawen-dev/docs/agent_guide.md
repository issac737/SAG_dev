# Agent 模块最佳实践指南 v2.0

> 极简、灵活、强大的智能数据处理 Agent

## 🎯 设计理念

**三大核心：**
1. **极简初始化** - 所有参数可选，默认值合理
2. **统一执行** - `run()` 方法，自动流转
3. **完全灵活** - 基于字典，支持任意字段

---

## 📁 文件结构（最终版）

```
dataflow/core/agent/
├── __init__.py       (17行)  导出
├── base.py          (498行)  BaseAgent 核心
├── builder.py       (115行)  提示词构建器
└── summarizer.py    (148行)  SummarizerAgent

prompts/
└── agent.json       (45行)   系统提示词配置

总计: 778 行
精简: 51.9%（删除了 factory.py 和 models.py）
```

---

## 🚀 快速开始

### 最简单的使用

```python
from dataflow.core.agent import SummarizerAgent

# 创建（全部使用默认值）
agent = SummarizerAgent()

# 添加数据
agent.add_database(
    data_type="reports",
    items=[
        {"id": "1", "summary": "Q3财报", "content": "总收入1.2亿元..."}
    ]
)

# 运行
result = await agent.run("总结财报")
print(result["content"])
```

---

## 📖 API 参考

### BaseAgent 初始化

```python
agent = BaseAgent(
    timezone=None,        # 可选，默认从 agent.json
    language=None,        # 可选，默认从 agent.json
    database=None,        # 可选，初始数据库分区
    memory=None,          # 可选，初始记忆分区
    todo=None,            # 可选，初始待办任务
    output=None,          # 可选，输出配置覆盖
    model_config=None,      # 可选，LLM 配置
)
```

**示例：**

```python
# 1. 最简单
agent = BaseAgent()

# 2. 覆盖时区和语言
agent = BaseAgent(timezone="America/New_York", language="en-US")

# 3. 带初始数据
agent = BaseAgent(
    database=[
        {
            "type": "financial_reports",
            "description": "财务报告",
            "list": [
                {"id": "q3", "summary": "Q3财报", "content": "..."}
            ]
        }
    ],
    output={"stream": True, "think": False}
)

# 4. 完整配置
agent = BaseAgent(
    timezone="Asia/Shanghai",
    language="zh-CN",
    database=[...],
    memory=[...],
    todo=[...],
    output={"stream": False, "format": "json"}
)
```

---

### run() - 统一执行入口

```python
result = await agent.run(
    query: str,          # 用户查询
    **overrides          # 覆盖配置
)
```

**自动流转：**
- 如果 `stream=False` → 返回 `Dict[str, Any]`
- 如果 `stream=True` → 返回 `AsyncIterator[Dict[str, str]]`

**示例：**

```python
# 基础执行（使用默认配置）
result = await agent.run("总结财报")

# 流式输出
async for chunk in agent.run("详细分析", stream=True):
    if chunk["reasoning"]:
        print(f"💭 {chunk['reasoning']}")
    print(chunk["content"], end="")

# 覆盖多个配置
result = await agent.run(
    "提取关键数据",
    stream=False,
    think=True,
    output_format="json"
)

# 结构化输出
result = await agent.run(
    "提取指标",
    schema={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "metrics": {"type": "array"}
        }
    }
)
```

---

### 数据管理

#### add_database()

```python
agent.add_database(
    data_type: str,           # 分区类型（注意：不是 type）
    items: List[Dict],        # 数据列表
    description: str = None,  # 分区描述
)
```

**智能管理：**
- 分区不存在 → 自动创建
- 分区已存在 → 自动追加
- 提供新描述 → 自动更新

```python
agent.add_database(
    data_type="financial_reports",
    items=[
        {"id": "doc1", "summary": "Q3财报", "content": "...", "date": "2024-10-31"}
    ],
    description="财务报告专区"
)
```

#### add_memory()

```python
agent.add_memory(
    data_type: str,           # 记忆类型
    items: List[Dict],        # 记忆列表
    description: str = None,  # 分区描述
)
```

```python
agent.add_memory(
    data_type="user_preferences",
    items=[
        {
            "id": "pref1",
            "summary": "用户偏好表格",
            "content": "用户喜欢 Markdown 表格",
            "timestamp": "2025-10-31T10:00:00Z"
        }
    ]
)
```

#### add_todo()

```python
agent.add_todo(
    task_id: str,             # 任务ID（注意：不是 id）
    description: str,         # 任务描述
    status: str = "pending",  # 状态
    priority: int = 5,        # 优先级
    **kwargs                  # 其他字段
)
```

```python
agent.add_todo(
    task_id="task-001",
    description="分析Q3财报并生成报告",
    status="in_progress",
    priority=8,
    deadline="2025-11-01",
    assigned_to="data_team"
)
```

---

## 💡 完整示例

```python
from dataflow.core.agent import SummarizerAgent

async def analyze_financial_report():
    # 1. 创建 Agent（极简）
    agent = SummarizerAgent()
    
    # 2. 添加财报数据
    agent.add_database(
        data_type="financial_reports",
        items=[
            {
                "id": "q3-2024",
                "summary": "2024年Q3财报",
                "content": "总收入1.2亿元，同比增长15%；净利润2千万元，同比增长20%。",
                "quarter": "Q3",
                "year": 2024
            },
            {
                "id": "q2-2024",
                "summary": "2024年Q2财报",
                "content": "总收入1.0亿元，净利润1.5千万元。",
                "quarter": "Q2",
                "year": 2024
            }
        ],
        description="2024年季度财报"
    )
    
    # 3. 添加用户偏好
    agent.add_memory(
        data_type="user_preferences",
        items=[{
            "id": "pref-001",
            "summary": "用户偏好表格输出",
            "content": "用户喜欢用 Markdown 表格展示关键数据",
            "timestamp": "2025-10-31T09:00:00Z"
        }]
    )
    
    # 4. 添加待办任务
    agent.add_todo(
        task_id="task-001",
        description="生成Q3财报分析PPT",
        status="pending",
        priority=8,
        deadline="2025-11-05"
    )
    
    # 5. 执行分析
    result = await agent.run("用表格对比Q2和Q3的关键财务指标")
    
    print(result["content"])
    
    # 6. 更新任务状态
    agent.update_todo_status("task-001", "completed")
    
    return result
```

---

## 🎨 高级用法

### 1. 初始化时注入数据

```python
# 一次性配置所有数据
agent = SummarizerAgent(
    timezone="Asia/Shanghai",
    database=[
        {
            "type": "financial_reports",
            "description": "财务报告",
            "list": [
                {"id": "q3", "summary": "Q3财报", "content": "..."}
            ]
        },
        {
            "type": "market_analysis",
            "description": "市场分析",
            "list": [
                {"id": "m1", "summary": "市场报告", "content": "..."}
            ]
        }
    ],
    memory=[
        {
            "type": "user_preferences",
            "description": "用户偏好",
            "list": [
                {"id": "pref1", "content": "偏好表格"}
            ]
        }
    ],
    output={"stream": True, "format": "json"}
)

# 直接使用，无需再添加数据
result = await agent.run("综合分析财报和市场数据")
```

### 2. 配置覆盖

```python
# 初始化时设置默认为流式
agent = SummarizerAgent(output={"stream": True})

# 运行时可以临时覆盖
result = await agent.run("快速总结", stream=False)  # 临时关闭流式
```

### 3. 多分区联合查询

```python
# 添加多个数据源
agent.add_database(data_type="sales", items=[...])
agent.add_database(data_type="users", items=[...])
agent.add_database(data_type="feedback", items=[...])

# Agent 会自动在所有分区中查找相关数据
result = await agent.run("结合销售、用户和反馈数据，分析产品表现")
```

---

## ⚡ 最佳实践

### 1. 极简创建

```python
# ✅ 推荐：使用默认值
agent = SummarizerAgent()

# ❌ 不推荐：指定默认值（冗余）
agent = SummarizerAgent(
    timezone="Asia/Shanghai",  # agent.json 已有
    language="zh-CN"           # agent.json 已有
)
```

### 2. 统一使用 run()

```python
# ✅ 推荐：使用 run()
result = await agent.run("查询")

# ⚠️  可以：使用 execute()（内部方法）
result = await agent.execute("查询")

# ⚠️  可以：使用 summarize()（SummarizerAgent 的别名）
result = await agent.summarize("查询")
```

### 3. 字典格式灵活

```python
# ✅ 推荐：字段灵活，随需添加
items = [
    {
        "id": "1",
        "summary": "摘要",
        "content": "内容",
        "自定义字段1": "值1",
        "自定义字段2": "值2",
        # ... 任意字段
    }
]
agent.add_database(data_type="my_data", items=items)
```

---

## 📊 完整对比

### 初始化对比

| 特性 | v1.x | v2.0 |
|------|------|------|
| **参数数量** | 5个 | 7个（但都可选） |
| **必需参数** | 2个 | 0个 |
| **支持注入** | ❌ | ✅ |
| **配置路径** | 可配 | 固定（更简单） |

### API 对比

| 操作 | v1.x | v2.0 |
|------|------|------|
| **执行** | `execute()` | `run()` |
| **添加数据** | `add_database(type=...)` | `add_database(data_type=...)` |
| **添加任务** | `add_todo(id=...)` | `add_todo(task_id=...)` |
| **输出格式** | `format=` | `output_format=` |

---

## ✅ 总结

**Agent v2.0 特性：**

✅ **极简** - 初始化零参数，`agent = SummarizerAgent()`
✅ **灵活** - 完全基于字典，任意字段
✅ **统一** - `run()` 方法，自动流转
✅ **规范** - 参数名清晰，避免关键字
✅ **强大** - 支持三种执行模式
✅ **可扩展** - JSON 配置驱动

**代码量：**
- 删除 838 行（51.9%）
- 保留 778 行核心功能

开始使用最佳实践的 Agent 吧！🚀

