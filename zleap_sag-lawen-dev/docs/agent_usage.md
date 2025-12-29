# Agent系统使用指南

## 概述

Agent系统是DataFlow的智能数据处理模块，专门用于对搜索结果进行总结和回答用户查询。

## 核心设计

### 统一数据格式

记忆(memory)和数据库(database)使用统一的数据格式：

```python
{
    "id": "唯一标识",
    "type": "数据类型",
    "summary": "摘要",
    "content": "完整内容",
    "extra_data": {}  # 额外数据
}
```

### Agent架构

- **角色(role)**: Agent的身份定义，默认是Zleap.AI的智能数据助手
- **记忆(memory)**: Agent自身的记忆，包括历史输出、用户反馈、偏好等
- **数据库(database)**: 用户数据，默认为空数组`[]`，直接注入
- **任务(task)**: 用户的查询和要求
- **输出(output)**: 支持流式、思考过程、多种格式(json/text/markdown)

## 快速开始

###  1. 最简单的使用

```python
from dataflow.core.agent import create_summarizer_agent, DataItem

# 创建Agent（使用空数据库）
agent = await create_summarizer_agent()

# 准备数据
events = [
    DataItem(
        id="evt1",
        type="event",
        summary="GPT-4发布",
        content="OpenAI于2023年3月14日发布了GPT-4模型，在多项基准测试中超越了前代模型。",
        extra_data={"date": "2023-03-14", "category": "AI"}
    ),
    DataItem(
        id="evt2",
        type="event",
        summary="Claude 3发布",
        content="Anthropic发布了Claude 3系列模型，包括Opus、Sonnet和Haiku三个版本。",
        extra_data={"date": "2024-03-04", "category": "AI"}
    )
]

# 执行总结（流式输出）
async for chunk in agent.summarize_stream(
    query="帮我总结2023-2024年重要的AI模型发布事件",
    events=events
):
    if chunk.content:
        print(chunk.content, end="", flush=True)
    if chunk.reasoning:
        print(f"\n[思考: {chunk.reasoning}]")
```

### 2. 自定义输出配置

```python
from dataflow.core.agent import create_summarizer_agent, create_default_output_config

# 创建自定义输出配置
output_config = create_default_output_config(
    stream=True,         # 启用流式输出
    think=True,          # 显示思考过程
    format="markdown",   # Markdown格式
    retry=3              # 失败重试3次
)

# 创建Agent
agent = await create_summarizer_agent(
    events=events,
    output_config=output_config
)

# 执行总结
async for chunk in agent.summarize_stream(
    query="总结AI发展趋势",
    events=events
):
    print(chunk.content, end="")
```

### 3. 添加记忆功能

```python
from dataflow.core.agent import create_summarizer_agent, MemoryItem

# 创建记忆
memory = [
    MemoryItem(
        id="mem1",
        type="user_feedback",
        summary="用户偏好简洁回答",
        content="用户在上次交互中表示希望得到更简洁的答案，避免过多细节",
        extra_data={"timestamp": "2024-01-15T10:30:00Z"}
    ),
    MemoryItem(
        id="mem2",
        type="preference",
        summary="关注技术细节",
        content="用户对技术实现细节特别感兴趣",
        extra_data={}
    )
]

# 创建带记忆的Agent
agent = await create_summarizer_agent(
    events=events,
    memory=memory,
    output_config=output_config
)
```

### 4. 自定义角色

```python
custom_role = """
你是一位资深的AI研究分析师，拥有10年以上的AI行业经验。
你擅长从技术、商业和社会影响等多个维度分析AI发展趋势。
你的回答深入浅出，既有专业深度，又容易理解。
"""

agent = await create_summarizer_agent(
    events=events,
    role=custom_role
)
```

### 5. 从搜索结果直接创建

```python
from dataflow.core.agent import create_agent_from_search_results

# 假设这是从search模块获取的结果
search_results = [
    {
        "id": "evt1",
        "type": "event",
        "summary": "摘要",
        "content": "内容",
        "extra_data": {"date": "2024-01-01"}
    }
]

# 直接从搜索结果创建Agent
agent = await create_agent_from_search_results(
    query="用户的查询",
    search_results=search_results
)
```

### 6. 非流式输出

```python
# 获取完整响应
response = await agent.summarize(
    query="总结这些事件",
    events=events
)

print(f"内容: {response.content}")
print(f"格式: {response.format}")
print(f"元数据: {response.metadata}")
```

### 7. JSON格式输出

```python
from dataflow.core.agent import create_default_output_config

# 配置JSON输出
json_config = create_default_output_config(
    stream=False,
    think=False,
    format="json",
    example='{"summary": "总结内容", "key_points": ["要点1", "要点2"]}'
)

agent = await create_summarizer_agent(
    events=events,
    output_config=json_config
)

response = await agent.summarize(
    query="以JSON格式总结",
    events=events
)

import json
result = json.loads(response.content)
print(result)
```

## 完整示例：集成到Search模块

```python
from dataflow.core.agent import create_summarizer_agent, DataItem
from dataflow.modules.search import EventSearcher

# 1. 执行搜索
searcher = EventSearcher()
search_results = await searcher.search(
    query="AI大模型发展",
    source_config_id="my-source"
)

# 2. 转换为DataItem格式
events = [
    DataItem(
        id=event.id,
        type="event",
        summary=event.summary or "",
        content=event.content or "",
        extra_data=event.extra_data or {}
    )
    for event in search_results.events
]

# 3. 创建Agent并总结
agent = await create_summarizer_agent(events=events)

# 4. 流式输出总结
print("AI助手回答：\n")
async for chunk in agent.summarize_stream(
    query="AI大模型发展",
    events=events
):
    if chunk.content:
        print(chunk.content, end="", flush=True)

    if chunk.is_final:
        print("\n\n[总结完成]")
```

## 高级功能

### 动态更新数据库

```python
agent = await create_summarizer_agent()

# 后续动态添加数据
new_events = [...]
agent.update_database(new_events)
```

### 添加/清空记忆

```python
# 添加新记忆
agent.add_memory(MemoryItem(
    id="mem3",
    type="conversation",
    summary="上次对话摘要",
    content="详细对话内容"
))

# 清空所有记忆
agent.clear_memory()
```

### 查询意图分析

```python
# 分析用户查询意图
analysis = await agent.analyze_query("帮我找最近的AI新闻")

print(analysis)
# {
#     "intent": "信息查询",
#     "key_elements": {
#         "time_range": "最近",
#         "entities": ["AI", "新闻"],
#         "data_types": ["event"]
#     },
#     "expected_output": {
#         "format": "markdown",
#         "detail_level": "detailed",
#         "structure": "列表"
#     }
# }
```

## 最佳实践

1. **数据准备**: 确保events包含充分的信息，summary和content要清晰
2. **合理分批**: 如果数据量很大（>100条），考虑先筛选最相关的
3. **记忆管理**: 定期清理过期的记忆，保持记忆的相关性
4. **输出格式**: 根据使用场景选择合适的格式（UI展示用markdown，API返回用json）
5. **思考过程**: 在调试时启用think=True，生产环境可以关闭以提升速度
6. **错误处理**: 设置合理的retry次数，捕获并处理异常

## 架构图

```
┌─────────────────────────────────────────────┐
│         SummarizerAgent                     │
│                                             │
│  ┌────────────┐  ┌──────────┐  ┌─────────┐ │
│  │   Role     │  │  Memory  │  │Database │ │
│  │  (身份)    │  │  (记忆)  │  │ (数据)  │ │
│  └────────────┘  └──────────┘  └─────────┘ │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │        Task (用户查询)               │   │
│  └─────────────────────────────────────┘   │
│                   ↓                         │
│  ┌─────────────────────────────────────┐   │
│  │     LLM Client (reasoning_content)   │   │
│  └─────────────────────────────────────┘   │
│                   ↓                         │
│  ┌─────────────────────────────────────┐   │
│  │   Output (stream/think/format)       │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

## 技术细节

- **LLM支持**: 通过OpenAI Client支持reasoning_content字段（Qwen等思考模型）
- **流式输出**: 返回`(content, reasoning)`元组，支持实时展示思考过程
- **Prompt管理**: 使用PromptManager统一管理提示词模板
- **类型安全**: 使用Pydantic进行数据验证
- **日志记录**: 完整的日志体系，便于调试和监控
