# SummarizerAgent 使用指南

> 专注于文档事项总结和分析的智能 Agent

## 🎯 特点

SummarizerAgent 是一个专门用于总结文档事项的 Agent，具有以下特性：

1. **自动序号标注** - 为每个事项添加 order 序号
2. **默认流式输出** - stream=True
3. **自动待办任务** - 自动添加"引用序号"的任务要求
4. **固定分区结构** - data_type="文档事项"

---

## 🚀 快速开始

### 基础使用

```python
from dataflow.core.agent import SummarizerAgent

# 1. 创建 Agent（默认流式输出）
agent = SummarizerAgent()

# 2. 加载文档事项
events = [
    {"id": "doc-001", "summary": "2024年Q3财报", "content": "总收入1.2亿元..."},
    {"id": "doc-002", "summary": "市场分析报告", "content": "市场份额提升..."},
    {"id": "doc-003", "summary": "用户反馈汇总", "content": "用户满意度90%..."},
]

agent.load_events(events)

# 3. 运行查询（流式输出）
async for chunk in agent.run("总结这些文档的关键信息"):
    print(chunk["content"], end="")
```

### 自动特性

**加载事项后，Agent 会自动：**

1. **添加序号**
```python
# 输入
events = [
    {"id": "doc-001", "summary": "Q3财报", "content": "..."},
    {"id": "doc-002", "summary": "市场分析", "content": "..."},
]

# 自动转换为
{
    "type": "文档事项",
    "description": "从文档中提取的事项",
    "list": [
        {"id": "doc-001", "order": 1, "summary": "Q3财报", "content": "..."},
        {"id": "doc-002", "order": 2, "summary": "市场分析", "content": "..."},
    ]
}
```

2. **添加待办任务**
```python
{
    "id": "summarize-events",
    "description": "根据 2 条文档事项输出回答，回答中需要引用事项序号（如：[1]、[2]）以标明信息来源",
    "status": "pending",
    "priority": 10
}
```

**LLM 会在回答中自动引用序号，如：**
```
根据文档分析：

1. Q3财报显示收入增长15% [1]
2. 市场份额提升至30% [2]
3. 用户满意度达到90% [3]
```

---

## 📖 API 参考

### 初始化

```python
agent = SummarizerAgent(
    events=None,          # 可选：初始文档事项
    timezone=None,        # 可选：时区
    language=None,        # 可选：语言
    output=None,          # 可选：输出配置（默认 stream=True）
    **kwargs              # 其他参数传递给 BaseAgent
)
```

**特殊默认值：**
- `output.stream` = `True`（流式输出）

**示例：**

```python
# 最简单
agent = SummarizerAgent()

# 带初始事项
agent = SummarizerAgent(
    events=[
        {"id": "1", "summary": "...", "content": "..."},
        {"id": "2", "summary": "...", "content": "..."},
    ]
)

# 覆盖为非流式
agent = SummarizerAgent(
    output={"stream": False}
)
```

---

### run() - 执行总结

```python
result = await agent.run(
    query: str,                # 用户查询
    events: List[Dict] = None, # 可选：事项列表
    **overrides                # 覆盖配置
)
```

**自动行为：**
- 如果提供 `events`，自动调用 `load_events()`
- 自动添加序号和待办任务
- 根据配置自动流转（默认流式）

**示例：**

```python
# 基础用法
result = await agent.run("总结这些事项", events=events)

# 流式输出（默认）
async for chunk in agent.run("详细分析财报"):
    print(chunk["content"], end="")

# 临时关闭流式
result = await agent.run("快速总结", stream=False)

# 指定输出格式
result = await agent.run("生成JSON报告", output_format="json")
```

---

### load_events() - 加载事项

```python
agent.load_events(events: List[Dict])
```

**自动处理：**
1. 清空现有的"文档事项"分区
2. 为每个事项添加 `order` 字段（1, 2, 3...）
3. 使用固定的分区类型和描述
4. 自动添加待办任务

**事项格式：**
```python
{
    "id": "唯一标识",
    "summary": "摘要",
    "content": "内容",
    # ... 任意其他字段
}
```

**转换后：**
```python
{
    "id": "唯一标识",
    "order": 1,           # 自动添加
    "summary": "摘要",
    "content": "内容",
    # ... 保留其他字段
}
```

---

## 💡 使用场景

### 场景 1：文档总结

```python
agent = SummarizerAgent()

# 加载多个文档
events = [
    {"id": "doc1", "summary": "产品手册", "content": "..."},
    {"id": "doc2", "summary": "用户指南", "content": "..."},
    {"id": "doc3", "summary": "FAQ", "content": "..."},
]

# 流式总结（默认）
async for chunk in agent.run("总结这些文档的核心内容", events=events):
    print(chunk["content"], end="")
```

### 场景 2：数据分析

```python
agent = SummarizerAgent()

# 加载分析数据
events = [
    {"id": "q1", "summary": "Q1数据", "content": "收入8000万..."},
    {"id": "q2", "summary": "Q2数据", "content": "收入1.0亿..."},
    {"id": "q3", "summary": "Q3数据", "content": "收入1.2亿..."},
]

agent.load_events(events)

# 分析趋势（LLM 会自动引用序号）
result = await agent.run("分析收入增长趋势")

# 输出示例：
# "从数据分析：
#  - Q1收入8000万 [1]
#  - Q2收入1.0亿，环比增长25% [2]
#  - Q3收入1.2亿，环比增长20% [3]
#  整体呈现稳定增长趋势。"
```

### 场景 3：带初始数据

```python
# 初始化时直接注入
agent = SummarizerAgent(
    events=[
        {"id": "1", "summary": "财报", "content": "..."},
        {"id": "2", "summary": "分析", "content": "..."},
    ],
    timezone="Asia/Shanghai"
)

# 直接使用
async for chunk in agent.run("总结要点"):
    print(chunk["content"], end="")
```

---

## 🎨 最佳实践

### 1. 事项格式

```python
# ✅ 推荐：提供完整字段
events = [
    {
        "id": "doc-001",           # 必需
        "summary": "文档摘要",      # 必需
        "content": "完整内容",      # 必需
        "source": "财务部",         # 可选
        "date": "2024-10-31",      # 可选
        "category": "financial"    # 可选
    }
]

# ✅ 也可以：最简格式
events = [
    {"id": "1", "summary": "...", "content": "..."}
]
```

### 2. 序号引用

**Agent 会自动在回答中引用序号：**
- 使用 `[1]`, `[2]` 等标注信息来源
- 方便追溯和验证
- 提高回答的可信度

### 3. 流式输出

```python
# ✅ 推荐：流式输出（默认）
async for chunk in agent.run("查询"):
    print(chunk["content"], end="")

# ⚠️  可以：关闭流式
result = await agent.run("查询", stream=False)
print(result["content"])
```

---

## 📊 完整示例

```python
from dataflow.core.agent import SummarizerAgent

async def summarize_documents():
    # 创建 Agent
    agent = SummarizerAgent()
    
    # 准备文档事项
    events = [
        {
            "id": "doc-001",
            "summary": "2024年Q3财报",
            "content": "总收入1.2亿元，同比增长15%；净利润2千万元，同比增长20%。",
            "date": "2024-10-31",
            "category": "financial"
        },
        {
            "id": "doc-002",
            "summary": "市场分析报告",
            "content": "市场份额提升至30%，同比增长5个百分点。",
            "date": "2024-10-30",
            "category": "market"
        },
        {
            "id": "doc-003",
            "summary": "用户满意度调查",
            "content": "用户满意度达到90%，较上季度提升3%。",
            "date": "2024-10-29",
            "category": "user"
        }
    ]
    
    # 加载事项（自动添加序号、待办任务）
    agent.load_events(events)
    
    # 查看状态
    print("数据库摘要:", agent.get_database_summary())
    print("待办任务:", agent.get_todo_summary())
    
    # 流式总结（默认）
    print("\n开始总结...\n")
    async for chunk in agent.run("综合这些文档，总结Q3的业务亮点"):
        if chunk["reasoning"]:
            print(f"💭 {chunk['reasoning']}\n")
        print(chunk["content"], end="", flush=True)
    
    print("\n\n总结完成！")
    
    # 更新任务状态
    agent.update_todo_status("summarize-events", "completed")


if __name__ == "__main__":
    import asyncio
    asyncio.run(summarize_documents())
```

---

## ✅ 总结

**SummarizerAgent v2.0 特性：**

✅ **专注** - 专门用于文档事项总结
✅ **智能** - 自动添加序号和待办
✅ **流式** - 默认流式输出
✅ **规范** - 固定的分区结构
✅ **可信** - 回答带序号引用

**与 BaseAgent 的区别：**

| 特性 | BaseAgent | SummarizerAgent |
|------|-----------|-----------------|
| 默认 stream | False | True |
| events 支持 | ❌ | ✅ |
| 自动序号 | ❌ | ✅ |
| 自动待办 | ❌ | ✅ |
| 固定分区 | ❌ | ✅（文档事项） |

开始使用 SummarizerAgent 处理文档吧！🚀

