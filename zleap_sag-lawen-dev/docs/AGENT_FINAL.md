# Agent 模块最终指南 v2.0

## 🎯 核心 API

### BaseAgent

```python
# 非流式执行
result = await agent.run("查询")

# 流式执行
async for chunk in agent.run_stream("查询"):
    print(chunk["content"], end="")
```

### SummarizerAgent

```python
# 默认流式输出
async for chunk in agent.run("总结", events=[...]):
    print(chunk["content"], end="")

# 非流式输出
result = await agent.run_normal("总结", events=[...])
```

---

## 📚 完整示例

```python
from dataflow.core.agent import SummarizerAgent

# 虚拟事项
events = [
    {"id": "1", "summary": "Q3财报", "content": "总收入1.2亿元，增长15%..."},
    {"id": "2", "summary": "市场分析", "content": "市场份额30%，提升5pp..."},
    {"id": "3", "summary": "用户调查", "content": "满意度90%，提升3%..."},
]

# 创建并运行
agent = SummarizerAgent(events=events)

async for chunk in agent.run("总结Q3业务亮点"):
    if chunk["reasoning"]:
        print(f"💭 {chunk['reasoning']}")
    print(chunk["content"], end="")
```

**输出示例：**
```
- 财务业绩稳健增长：收入1.2亿（+15%），净利润2000万（+20%）[1]
- 市场份额显著提升：达30%，提升5pp，领先竞争对手 [2]
- 用户满意度创新高：90%，智能推荐95%、界面92% [3]
```

---

## ✅ 核心特性

| 特性 | BaseAgent | SummarizerAgent |
|------|-----------|-----------------|
| **run()** | 非流式 | 流式（默认） |
| **run_stream()** | 流式 | - |
| **run_normal()** | - | 非流式 |
| **自动序号** | ❌ | ✅ |
| **自动待办** | ❌ | ✅ |
| **序号引用** | ❌ | ✅ [1], [2], [3] |

---

## 🚀 快速开始

```python
from dataflow.core.agent import SummarizerAgent

agent = SummarizerAgent(events=[...])
async for chunk in agent.run("总结"):
    print(chunk["content"], end="")
```

**就这么简单！** 🎉

