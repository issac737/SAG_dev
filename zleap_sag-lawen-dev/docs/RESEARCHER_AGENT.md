# Researcher Agent - 智能对话研究员

## 📖 概述

ResearcherAgent 是一个具有完整认知能力的对话 Agent，能够：
- 🧠 **深度理解**：分析问题意图、提取关键概念
- 🔍 **主动搜索**：基于 SAG 引擎智能搜索相关事项
- 💭 **推理链路**：展示完整的思考过程（CoT）
- 📊 **自我评估**：判断知识是否充分
- 🔄 **迭代优化**：深度模式支持多轮搜索
- 📝 **记忆管理**：维护对话上下文

---

## 🚀 快速开始

### 基础用法

```python
from dataflow.core.agent import ResearcherAgent

# 创建研究员
agent = ResearcherAgent(
    source_config_ids=["source_123", "source_456"],
    mode="quick"
)

# 对话（流式输出）
async for chunk in agent.chat("人工智能的最新进展是什么？"):
    if chunk["type"] == "thinking":
        print(f"💭 {chunk['content']}")
    elif chunk["type"] == "content":
        print(chunk["content"], end="")
    elif chunk["type"] == "done":
        print(f"\n📊 统计: {chunk['stats']}")
```

---

## 🎯 两种模式

### 快速模式（Quick）

**适用场景**：简单事实查询、快速获取答案

**流程**：
1. 理解问题（提取关键词）
2. 执行搜索（单次，多源）
3. 评估知识（是否充分）
4. 生成回答（简洁直接）

**特点**：
- ⚡ 响应快速（~2-5秒）
- 📝 回答简洁
- 💰 成本较低

**示例**：
```python
agent = ResearcherAgent(
    source_config_ids=["tech_news"],
    mode="quick"
)

async for chunk in agent.chat("什么是 GPT-4？"):
    print(chunk["content"], end="")

# 输出：
# GPT-4 是 OpenAI 开发的大型语言模型... [#1][#2]
```

### 深度模式（Deep）

**适用场景**：复杂分析、对比研究、深度理解

**流程**：
1. 深度理解（问题分解）
2. 制定计划（搜索策略）
3. 多轮搜索（3-5轮迭代）
4. 持续评估（知识缺口）
5. 深度综合（完整答案）
6. 质量验证（自我检查）

**特点**：
- 🧠 分析深入（多角度）
- 📚 信息全面（多轮搜索）
- 🎯 回答详细（结构化）
- ⏱️ 耗时较长（~10-30秒）

**示例**：
```python
agent = ResearcherAgent(
    source_config_ids=["tech_reports", "market_analysis"],
    mode="deep"
)

async for chunk in agent.chat("对比分析 GPT-4 和 Claude 的优劣"):
    if chunk["type"] == "stage":
        print(f"\n🎯 {chunk['stage']}")
    elif chunk["type"] == "thinking":
        print(f"  💭 {chunk['content']}")
    elif chunk["type"] == "content":
        print(chunk["content"], end="")

# 输出：
# 🎯 理解问题
#   💭 问题类型：对比分析
#   💭 核心概念：GPT-4, Claude
# 🎯 制定计划
#   💭 搜索计划：3 轮搜索
# 🎯 搜索研究
#   💭 第 1 轮搜索：["GPT-4", "Claude"]
#   💭 找到 8 个事项
# ...
# 根据搜索到的信息，GPT-4 和 Claude 的对比如下：
# 
# **1. 技术架构**
# - GPT-4：... [#1][#3]
# - Claude：... [#2][#4]
# ...
```

---

## 📊 认知流程详解

### 阶段1：Understanding（理解）

**目标**：深入理解用户问题

**快速模式**：
- 提取用户意图
- 提取关键词（2-5个）
- 识别实体类型

**深度模式**：
- 判断问题类型（事实/对比/趋势/原因/建议）
- 提取核心概念（2-5个）
- 分解子问题（2-4个）
- 识别时间范围
- 确定关注实体

### 阶段2：Planning（规划）

**仅深度模式**

**目标**：制定搜索策略

**输出**：
- 搜索轮数（1-5轮）
- 每轮查询列表
- 搜索策略说明

**示例**：
```json
{
  "rounds": 3,
  "queries": [
    ["人工智能", "发展趋势"],      // 第1轮：主关键词
    ["AI应用", "技术突破"],         // 第2轮：补充概念
    ["行业影响", "未来展望"]        // 第3轮：关联信息
  ],
  "strategy": "从技术本身到应用实践，再到未来影响"
}
```

### 阶段3：Researching（研究）

**目标**：主动搜索相关知识

**快速模式**：
- 单次搜索
- 使用主关键词
- Top 10 结果

**深度模式**：
- 多轮迭代（最多5轮）
- 每轮1-2个查询
- 累积结果并去重

**核心优化**：
- ✅ 多源一次调用（`source_config_ids`）
- ✅ 自动去重（基于事项ID）
- ✅ 结果累积（跨轮次）

### 阶段4：Evaluating（评估）

**目标**：判断知识是否充分

**评估维度**：
- 事项数量
- 内容相关性
- 置信度计算

**判断标准**：
```
0 个事项   → 不充分（confidence: 0.0）
1-2 个事项 → 部分充分（confidence: 0.4-0.6）
3-5 个事项 → 基本充分（confidence: 0.65）
5+ 个事项  → 完全充分（confidence: 0.85）
```

**深度模式特殊处理**：
- 第2轮后降低标准（≥3个即可）
- 考虑搜索轮次
- 识别知识缺口

### 阶段5：Synthesizing（综合）

**目标**：生成高质量回答

**回答要求**：
- ✅ 逻辑清晰
- ✅ 重点突出（用**加粗**）
- ✅ 结构化（列表、标题）
- ✅ 标注来源（[#1][#2]）
- ✅ 诚实表达（不编造）

**快速模式回答结构**：
```
直接回答 + 关键点（带引用）
```

**深度模式回答结构**：
```
背景介绍
  ↓
现状分析（多个维度）
  ↓
深入探讨（细节展开）
  ↓
总结结论
```

### 阶段6：Verifying（验证）

**仅深度模式**

**目标**：质量把关

**检查项**：
- 准确性（是否有依据）
- 完整性（是否回答了问题）
- 一致性（逻辑是否连贯）
- 引用完整（来源标注）

---

## 💾 记忆机制

### 记忆分区

| 分区类型 | 内容 | 用途 |
|---------|------|------|
| 对话历史 | 最近10条消息 | 维护上下文 |
| 当前问题 | 本次问题详情 | 问题聚焦 |
| 问题理解 | 理解分析结果 | 指导搜索 |
| 搜索计划 | 搜索策略 | 执行指导 |
| 搜索历史 | 每次搜索记录 | 避免重复 |
| 知识评估 | 评估结果 | 决策依据 |

### 记忆更新时机

```python
# 对话开始时
self._record_user_query(query)

# 理解完成后
self._record_understanding(understanding)

# 规划完成后（深度模式）
self._record_search_plan(plan)

# 每次搜索后
self._record_search(query, result)

# 每次评估后
self._record_evaluation(evaluation)
```

---

## 📋 TODO 任务机制

### 快速模式 TODO

```python
[
    {
        "task_id": "analyze-relevance",
        "description": "分析事项与问题的相关性",
        "priority": 10
    },
    {
        "task_id": "extract-key-info",
        "description": "提取关键信息",
        "priority": 9
    },
    {
        "task_id": "synthesize-answer",
        "description": "生成简洁回答，引用序号",
        "priority": 8
    }
]
```

### 深度模式 TODO

```python
[
    {
        "task_id": "deep-understanding",
        "description": "深度理解问题本质",
        "priority": 10
    },
    {
        "task_id": "cross-reference",
        "description": "交叉验证信息",
        "priority": 9
    },
    {
        "task_id": "build-narrative",
        "description": "构建完整叙事",
        "priority": 8
    },
    {
        "task_id": "cite-sources",
        "description": "准确引用来源",
        "priority": 7
    },
    {
        "task_id": "add-insights",
        "description": "添加深度洞察",
        "priority": 6
    }
]
```

---

## 🌐 API 使用

### 流式对话

```bash
curl -X POST http://localhost:8000/api/v1/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "query": "人工智能的发展趋势",
    "source_config_ids": ["source_123"],
    "mode": "quick",
    "params": {"top_k": 10}
  }'

# SSE 流式响应：
data: {"type": "stage", "stage": "understanding"}
data: {"type": "thinking", "content": "理解问题：趋势分析"}
data: {"type": "thinking", "content": "搜索完成：找到 8 个事项"}
data: {"type": "content", "content": "根据搜索..."}
data: {"type": "content", "content": "人工智能的发展..."}
data: {"type": "done", "stats": {"events_found": 8, "confidence": 0.85}}
```

### 提交反馈

```bash
curl -X POST http://localhost:8000/api/v1/chat/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "msg_123",
    "rating": 5,
    "feedback_type": "helpful",
    "comment": "回答很准确"
  }'
```

---

## 💻 前端集成

### 流式接收

```typescript
// 调用流式对话
for await (const chunk of apiClient.chatStream({
  query: "人工智能的发展",
  source_config_ids: ["src1", "src2"],
  mode: "quick",
  context: messages.slice(-10),
  params: { top_k: 10 }
})) {
  switch (chunk.type) {
    case 'stage':
      console.log(`阶段: ${chunk.stage}`)
      break
    case 'thinking':
      console.log(`思考: ${chunk.content}`)
      break
    case 'content':
      console.log(chunk.content, { end: '' })
      break
    case 'done':
      console.log(`\n完成: ${chunk.stats}`)
      break
  }
}
```

### UI 展示

```tsx
<div className="message">
  {/* 思考过程（可折叠） */}
  {message.thinking && (
    <Collapsible>
      <CollapsibleTrigger>
        💭 思考过程 ({message.thinking.length} 步)
      </CollapsibleTrigger>
      <CollapsibleContent>
        {message.thinking.map(thought => (
          <div className="text-xs text-gray-600">{thought}</div>
        ))}
      </CollapsibleContent>
    </Collapsible>
  )}

  {/* 回答内容 */}
  <div className="content">
    {message.content}
    {message.isStreaming && <Loader2 className="animate-spin" />}
  </div>

  {/* 统计信息 */}
  {message.stats && (
    <div className="stats">
      📊 {message.stats.events_found} 个事项
      · 置信度 {(message.stats.confidence * 100).toFixed(0)}%
    </div>
  )}
</div>
```

---

## 🔧 高级配置

### 自定义参数

```python
agent = ResearcherAgent(
    source_config_ids=["s1", "s2"],
    mode="deep",
    max_iterations=5,  # 深度模式最大搜索轮数
    output={
        "stream": True,
        "think": True,
        "format": "text"
    }
)
```

### 对话历史

```python
# 带上下文对话
history = [
    {"role": "user", "content": "什么是AI？"},
    {"role": "assistant", "content": "AI是..."},
]

agent = ResearcherAgent(
    source_config_ids=["tech"],
    conversation_history=history
)

# 新问题会参考历史上下文
async for chunk in agent.chat("它有什么应用？"):
    ...
```

---

## 📈 性能优化

### 多源搜索

✅ **一次调用**（推荐）
```python
result = await searcher.search(
    SearchConfig(
        query="人工智能",
        source_config_ids=["s1", "s2", "s3"]  # 多源一次调用
    )
)
```

❌ **循环调用**（不推荐）
```python
for source_id in source_config_ids:
    result = await searcher.search(
        SearchConfig(query="人工智能", source_id=source_id)
    )
```

### 事项去重

```python
def _deduplicate_events(self, events: List) -> List:
    """基于ID去重"""
    seen_ids = set()
    unique = []
    for e in events:
        if e.id not in seen_ids:
            seen_ids.add(e.id)
            unique.append(e)
    return unique
```

---

## 🎨 最佳实践

### 1. 信息源选择

- 单源：精准查询
- 多源：全面覆盖
- 建议：2-5个相关源

### 2. 模式选择

| 问题类型 | 推荐模式 | 原因 |
|---------|---------|------|
| 简单事实 | Quick | 快速直接 |
| 概念解释 | Quick | 单次搜索足够 |
| 对比分析 | Deep | 需要多角度 |
| 趋势分析 | Deep | 需要综合信息 |
| 原因探究 | Deep | 需要深入挖掘 |

### 3. 对话历史

- 保留最近10条
- 包含用户+助手消息
- 维护上下文连贯性

### 4. 错误处理

```python
try:
    async for chunk in agent.chat(query):
        yield chunk
except Exception as e:
    yield {
        "type": "error",
        "content": f"执行失败：{str(e)}"
    }
```

---

## 🔍 调试技巧

### 查看思考过程

```python
agent = ResearcherAgent(
    source_config_ids=["tech"],
    output={"think": True}  # 开启思考展示
)

async for chunk in agent.chat("什么是AI？"):
    if chunk["type"] == "thinking":
        print(f"💭 {chunk['content']}")  # 查看思考
```

### 查看搜索统计

```python
async for chunk in agent.chat("什么是AI？"):
    if chunk["type"] == "done":
        print(f"统计: {chunk['stats']}")
        # {
        #   "mode": "quick",
        #   "events_found": 8,
        #   "confidence": 0.85,
        #   "sources": 2
        # }
```

---

## 📝 TODO

### 未来增强

- [ ] LLM 评估知识充分性（更智能）
- [ ] 问题重写优化（生成更好的搜索词）
- [ ] 引用追溯（点击序号跳转到事项）
- [ ] 对话持久化（保存会话）
- [ ] 反馈学习（基于用户反馈优化）

---

## 🎉 总结

ResearcherAgent 是一个：
- ✅ 具有完整认知能力的对话 Agent
- ✅ 支持两种模式（快速/深度）
- ✅ 完整的思考过程展示
- ✅ 基于证据的准确回答
- ✅ 优雅的前后端集成

立即体验智能对话！🚀

