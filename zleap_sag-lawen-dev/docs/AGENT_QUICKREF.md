# Agent 快速参考 v2.0

## 🚀 快速开始

```python
from dataflow.core.agent import SummarizerAgent

# 创建
agent = SummarizerAgent()

# 加载事项（自动添加序号）
agent.load_events([
    {"id": "1", "summary": "Q3财报", "content": "..."},
    {"id": "2", "summary": "市场分析", "content": "..."},
])

# 运行（流式输出）
async for chunk in agent.run("总结要点"):
    print(chunk["content"], end="")
```

---

## 📚 核心 API

### 初始化

```python
# 零参数
agent = SummarizerAgent()

# 带配置
agent = SummarizerAgent(
    timezone="Asia/Shanghai",   # 可选
    language="zh-CN",            # 可选
    events=[...],                # 可选
    output={"stream": True}      # 可选
)
```

### 执行

```python
# 基础
result = await agent.run("查询")

# 流式（默认）
async for chunk in agent.run("查询"):
    print(chunk["content"], end="")

# 覆盖配置
result = await agent.run("查询", stream=False, output_format="json")
```

### 数据管理

```python
# 添加数据
agent.add_database(data_type="reports", items=[...])

# 添加记忆
agent.add_memory(data_type="preferences", items=[...])

# 添加待办
agent.add_todo(task_id="task1", description="...", priority=8)
```

---

## 🎯 参数速查

| 参数 | 说明 | 示例 |
|------|------|------|
| `data_type` | 分区类型 | `"financial_reports"` |
| `task_id` | 任务ID | `"task-001"` |
| `output_format` | 输出格式 | `"markdown"`, `"json"` |
| `stream` | 流式输出 | `True`, `False` |
| `think` | 展示思考 | `True`, `False` |
| `schema` | JSON Schema | `{"type": "object", ...}` |

---

## 💡 SummarizerAgent 特性

- ✅ 默认 `stream=True`
- ✅ 自动添加 `order` 序号
- ✅ 自动待办任务（引用序号）
- ✅ 固定分区：`type="文档事项"`

---

## 📖 文档

- 完整指南: `docs/agent_guide.md`
- Summarizer: `docs/agent_summarizer.md`
- 配置文件: `prompts/agent.json`

