# SAG 搜索引擎 API 文档

## 📋 概述

SAG (SQL-Algorithm-Graph) 是一个三阶段混合搜索引擎，结合SQL查询、算法计算和图遍历技术，实现高效的知识图谱搜索。

## 🔄 三阶段搜索流程

### 1. Recall（实体召回）
- **功能**：从查询中召回相关实体
- **算法**：8步骤复合搜索算法
- **输出**：带权重的实体列表 + 召回线索

### 2. Expand（实体扩展）
- **功能**：通过多跳关系扩展发现更多实体
- **算法**：基于共现关系的图遍历
- **输出**：扩展后的实体网络 + 扩展线索

### 3. Rerank（重排序）
- **功能**：基于实体对事项/段落进行排序
- **算法**：PageRank或RRF融合排序
- **输出**：排序后的事项/段落列表 + 最终线索

## 📡 API 接口

### 主要接口：POST /api/v1/search

#### 请求参数

```json
{
  "query": "人工智能技术发展",           // 必需：查询文本
  "source_config_ids": ["source_001"],   // 必需：数据源ID列表
  "return_type": "event",                // 可选：返回类型（event/paragraph）

  // Recall 配置
  "recall": {
    "max_entities": 25,                  // 最大实体数量
    "entity_similarity_threshold": 0.4,  // 实体相似度阈值
    "vector_top_k": 15,                  // 向量搜索返回数量
    "use_fast_mode": true                // 是否使用快速模式
  },

  // Expand 配置
  "expand": {
    "enabled": true,                     // 是否启用扩展
    "max_hops": 3,                       // 最大跳数
    "entities_per_hop": 10,              // 每跳新增实体数
    "weight_change_threshold": 0.1       // 权重变化阈值（收敛判断）
  },

  // Rerank 配置
  "rerank": {
    "strategy": "pagerank",              // 排序策略（pagerank/rrf）
    "max_results": 10,                   // 最大返回数量
    "score_threshold": 0.5               // 分数阈值
  }
}
```

#### 响应格式

**EVENT模式（返回事项）:**
```json
{
  "success": true,
  "data": {
    "events": [
      {
        "id": "event_123",
        "title": "GPT模型发布",
        "content": "OpenAI发布了GPT-3模型...",
        "category": "technology",
        "created_at": "2023-01-01T00:00:00Z",
        "source_config_id": "source_001"
      }
    ],
    "clues": [
      {
        "stage": "recall",
        "from": {
          "id": "query_ai_tech",
          "type": "query",
          "content": "人工智能技术发展"
        },
        "to": {
          "id": "entity_gpt",
          "type": "entity",
          "content": "GPT模型",
          "category": "technology"
        },
        "confidence": 0.85,
        "relation": "语义相似",
        "metadata": {
          "method": "vector_search",
          "similarity": 0.85,
          "weight": 0.82,        // to节点权重（仅当to是实体时存在）
          "step": "step1"
        },
        "display_level": "final"
      }
    ],
    "stats": {
      "total_events": 15,
      "total_clues": 45,
      "recall_entities": 25,
      "expand_entities": 32,
      "execution_time": 2.34,
      "stages": {
        "recall": {
          "entities_found": 25,
          "entities_passed": 18,
          "execution_time": 0.8
        },
        "expand": {
          "total_jumps": 3,
          "entities_discovered": 32,
          "execution_time": 1.2
        },
        "rerank": {
          "events_ranked": 15,
          "strategy": "pagerank",
          "execution_time": 0.34
        }
      }
    },
    "query": {
      "original": "人工智能技术发展",
      "rewritten": "人工智能技术发展现状与趋势",
      "embedding_generated": true
    }
  }
}
```

**PARAGRAPH模式（返回段落）:**
```json
{
  "success": true,
  "data": {
    "sections": [
      {
        "id": "section_456",
        "title": "GPT技术原理",
        "content": "GPT模型基于Transformer架构，通过大规模预训练...",
        "event_id": "event_123",
        "order_index": 1,
        "source_config_id": "source_001"
      }
    ],
    "clues": [...],  // 同EVENT模式
    "stats": {...},  // 同EVENT模式
    "query": {...}   // 同EVENT模式
  }
}
```

## 📊 数据类型定义

### 基本类型

| 类型 | 描述 | 示例 |
|-----|------|------|
| `string` | 文本字符串 | `"人工智能"` |
| `number` | 数字（整数或浮点） | `0.85`, `25` |
| `boolean` | 布尔值 | `true`, `false` |
| `array` | 数组 | `["source_001", "source_002"]` |
| `object` | 对象 | `{"key": "value"}` |

### 枚举类型

#### ReturnType 枚举
```typescript
enum ReturnType {
  EVENT = "event",      // 返回事项（默认）
  PARAGRAPH = "paragraph"  // 返回段落
}
```

#### RerankStrategy 枚举
```typescript
enum RerankStrategy {
  PAGERANK = "pagerank",  // PageRank排序
  RRF = "rrf"            // 倒数排名融合排序
}
```

#### DisplayLevel 枚举
```typescript
enum DisplayLevel {
  FINAL = "final",        // 最终结果（前端显示）
  INTERMEDIATE = "intermediate",  // 中间结果（调试用）
  DEBUG = "debug"         // 调试信息
}
```

### 核心对象类型

#### SearchConfig 对象
```typescript
interface SearchConfig {
  query: string;                    // 查询文本
  source_config_ids: string[];      // 数据源ID列表
  original_query?: string;          // 原始查询（用于重写对比）
  enable_query_rewrite?: boolean;   // 是否启用查询重写
  return_type?: ReturnType;         // 返回类型

  // 三阶段配置
  recall?: RecallConfig;            // 召回配置
  expand?: ExpandConfig;            // 扩展配置
  rerank?: RerankConfig;            // 重排配置

  // 运行时缓存
  query_embedding?: number[];       // 查询向量缓存
  has_query_embedding?: boolean;    // 是否已生成查询向量
  all_clues?: Clue[];               // 所有线索（统一追踪）
  entity_node_cache?: EntityNodeCache;  // 实体节点缓存
}
```

#### RecallConfig 对象
```typescript
interface RecallConfig {
  enabled?: boolean;                // 是否启用（默认true）
  max_entities?: number;            // 最大实体数量（默认25）
  entity_similarity_threshold?: number; // 实体相似度阈值（默认0.4）
  vector_top_k?: number;            // 向量搜索返回数量（默认15）
  vector_candidates?: number;       // 向量搜索候选池大小（默认20）
  use_fast_mode?: boolean;          // 是否使用快速模式（默认true）
  fallback_to_single_query?: boolean; // 失败时降级为单查询（默认true）
}
```

#### ExpandConfig 对象
```typescript
interface ExpandConfig {
  enabled?: boolean;                // 是否启用（默认true）
  max_hops?: number;                // 最大跳数（默认3）
  entities_per_hop?: number;        // 每跳新增实体数（默认10）
  weight_change_threshold?: number; // 权重变化阈值（默认0.1）
  event_similarity_threshold?: number; // 事项相似度阈值（默认0.3）
  min_events_per_hop?: number;      // 每跳最少事项数（默认5）
  max_events_per_hop?: number;      // 每跳最多事项数（默认100）
}
```

#### RerankConfig 对象
```typescript
interface RerankConfig {
  strategy?: RerankStrategy;        // 排序策略（默认"rrf"）
  score_threshold?: number;         // 分数阈值（默认0.5）
  max_results?: number;             // 最大返回数量（默认10）
  max_key_recall_results?: number;  // Key召回最大结果数（默认30）
  max_query_recall_results?: number; // Query召回最大结果数（默认30）

  // PageRank参数
  pagerank_damping_factor?: number; // 阻尼系数（默认0.85）
  pagerank_max_iterations?: number; // 最大迭代次数（默认100）

  // RRF参数
  rrf_k?: number;                   // RRF融合参数K（默认60）
}
```

#### Clue 对象（线索）
```typescript
interface Clue {
  stage: "recall" | "expand" | "rerank" | "prepare";  // 阶段标识
  from_node: Node;                  // 起点节点
  to_node: Node;                    // 终点节点
  confidence: number;               // 置信度（0.0-1.0）
  relation: string;                 // 关系类型
  metadata: Metadata;               // 元数据
  display_level: DisplayLevel;      // 显示级别
}

interface Node {
  id: string;                       // 节点ID
  type: "query" | "entity" | "event";  // 节点类型
  category?: string;               // 节点分类（如实体类型）
  content: string;                 // 节点内容
  description?: string;            // 节点描述
  hop?: number;                    // 跳数（用于图遍历）
}

interface Metadata {
  method?: string;                  // 方法（如"vector_search"）
  step?: string;                    // 步骤标识
  similarity?: number;              // 相似度分数
  weight?: number;                  // 权重（仅当to_node是实体时存在）
  steps?: number[];                 // 步骤列表
  source_attribute?: string;        // 来源属性
  pagerank_score?: number;          // PageRank分数
  rrf_score?: number;               // RRF分数
  rank?: number;                    // 排名
  [key: string]: any;               // 其他自定义字段
}
```

#### SourceEvent 对象
```typescript
interface SourceEvent {
  id: string;                       // 事项ID
  title: string;                    // 事项标题
  content: string;                  // 事项内容
  summary?: string;                 // 事项摘要
  category: string;                 // 事项分类
  tags?: string[];                  // 标签列表
  created_at: string;               // 创建时间（ISO 8601）
  updated_at: string;               // 更新时间（ISO 8601）
  source_config_id: string;         // 数据源配置ID
  metadata?: Record<string, any>;   // 元数据
}
```

#### Section 对象（段落）
```typescript
interface Section {
  id: string;                       // 段落ID
  title: string;                    // 段落标题
  content: string;                  // 段落内容
  event_id: string;                 // 所属事项ID
  order_index: number;              // 排序索引
  source_config_id: string;         // 数据源配置ID
  metadata?: Record<string, any>;   // 元数据
}
```

## 🔗 线索追踪系统

### 线索类型

1. **召回线索 (recall)**
   - 来源：query → entity
   - 方法：向量搜索、SQL关联
   - metadata：包含相似度和实体权重

2. **扩展线索 (expand)**
   - 来源：entity → event → entity
   - 方法：共现关系分析
   - metadata：包含跳数和权重信息

3. **重排线索 (rerank)**
   - 来源：entity → event 或 query → event
   - 方法：PageRank或RRF排序
   - metadata：包含排序分数和排名

4. **准备线索 (prepare)**
   - 来源：query → query（重写）或 query → 提取属性
   - 方法：LLM处理
   - metadata：包含处理方法和属性信息

### 权重信息规范

- **confidence**：表示from节点和to节点之间的关系强度，主要来源于相似度计算
- **metadata.weight**：表示to节点的权重（仅当to节点是实体时存在），来源于key权重计算
- **显示规则**：前端可以根据`display_level`决定显示哪些线索

## 📈 性能指标

### 响应时间
- 简单查询：< 2秒
- 复杂查询：< 5秒
- 包含扩展：< 10秒

### 准确率指标
- 实体召回率：> 85%
- 事项相关性：> 80%
- 用户满意度：> 75%

## 🚨 错误处理

### 错误响应格式
```json
{
  "success": false,
  "error": {
    "code": "SEARCH_ERROR",
    "message": "搜索失败：数据库连接超时",
    "details": {
      "stage": "recall",
      "retryable": true
    }
  }
}
```

### 常见错误码
- `SEARCH_ERROR`：搜索通用错误
- `CONFIG_ERROR`：配置错误
- `DATABASE_ERROR`：数据库错误
- `LLM_ERROR`：LLM服务错误
- `TIMEOUT_ERROR`：超时错误

## 💡 使用示例

### 基本搜索
```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "人工智能技术发展",
    "source_config_ids": ["tech_source"]
  }'
```

### 高级搜索
```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Transformer架构原理",
    "source_config_ids": ["ai_papers", "tech_blogs"],
    "return_type": "paragraph",
    "recall": {
      "max_entities": 30,
      "entity_similarity_threshold": 0.3,
      "use_fast_mode": false
    },
    "expand": {
      "max_hops": 2,
      "entities_per_hop": 15
    },
    "rerank": {
      "strategy": "pagerank",
      "max_results": 20
    }
  }'
```

## 📚 相关文档

- [搜索模块README](./README.md) - 模块详细介绍
- [配置文档](./config.md) - 配置参数详解
- [线索追踪文档](./tracker.md) - 线索系统说明
- [API路由文档](../api/routers/) - 具体路由实现