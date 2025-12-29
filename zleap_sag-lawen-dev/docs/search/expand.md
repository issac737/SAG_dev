# Expand 多跳循环搜索功能

## 概述

Expand是基于Stage1结果的多跳循环搜索算法，通过迭代扩展和权重计算来发现更多相关的实体和事件。

## 算法流程

### 核心思想
Expand通过多跳循环不断扩展搜索范围，每一步都使用原始query进行约束，确保搜索结果不会偏离原始意图，同时通过权重收敛机制控制搜索深度。

### 具体步骤

#### 1. SQL查询关联事件
- **输入**: Stage1最终的重要keys `[key-final]`
- **操作**: 使用SQL查询找到所有包含这些keys的事件
- **输出**: 新的事件集合 `[Event-key-related-2]`
- **特点**: 精准匹配，确保关联性

#### 2. 计算相似度向量
- **输入**: 原始query + 新事件集合
- **操作**: 计算原始query与每个新事件的语义相似度
- **输出**: 相似性向量 `(event-query-2)`
- **特点**: 使用原始query约束，保持搜索方向

#### 3. 计算事件权重向量
- **输入**: 新事件集合 + key权重
- **操作**: 根据每个事件包含的重要key情况，将对应key权重相加
- **输出**: 事件权重向量 `(event-key-2)`
- **特点**: 包含重要key越多的事件权重越高

#### 4. 计算复合权重向量
- **输入**: 事件权重向量 + 相似度向量
- **操作**: `(event-key-2) * (event-query-2)`
- **输出**: 复合权重向量 `(event-jump-2)`
- **特点**: 结合key重要性和query相关性

#### 5. 反向计算key权重
- **输入**: 复合权重向量 + 事件-key关系
- **操作**: 根据事件权重反向计算所有包含的key的重要性
- **输出**: 新的key权重向量 `(key-event)`
- **特点**: 发现新的重要key

#### 6. 多跳循环控制
- **收敛条件**: 权重变化小于阈值时停止
- **最大跳跃**: 防止无限循环
- **权重更新**: 选择权重最高的keys进入下一跳

## 配置参数

### 基础配置
```python
config = SearchConfig(
    source_config_id="your_source_config_id",
    query="your search query",
    enable_expand=True,  # 启用Expand
)
```

### Expand专用参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `enable_expand` | `False` | 是否启用Expand多跳循环搜索 |
| `max_jumps` | `3` | 最大跳跃次数 (1-10) |
| `expand_event_threshold` | `0.4` | Expand Event相似度阈值 (0.0-1.0) |
| `expand_convergence_threshold` | `0.1` | 收敛阈值，权重变化小于此值时停止 |
| `expand_min_events` | `5` | 每轮最少Event数量 |
| `expand_max_events` | `100` | 每轮最多Event数量 |

## 使用方法

### 1. 独立使用Expand
```python
from eventflow.modules.search.expand import ExpandSearcher
from eventflow.modules.search.stage1 import Stage1Searcher

# 初始化搜索器
stage1_searcher = Stage1Searcher(llm_client, prompt_manager)
expand_searcher = ExpandSearcher(llm_client, prompt_manager, stage1_searcher)

# 配置参数
config = SearchConfig(
    source_config_id="source_config_id",
    query="search query",
    enable_expand=True,
    max_jumps=3,
    # ... 其他参数
)

# 执行搜索（Expand会自动执行Stage1）
result = await expand_searcher.search(config)
```

### 2. 基于已有Stage1结果使用
```python
# 先执行Stage1
stage1_result = await stage1_searcher.search(config)

# 基于Stage1结果执行Expand
expand_result = await expand_searcher.search(config, stage1_result)
```

## 结果结构

### ExpandResult
```python
@dataclass
class ExpandResult:
    # 最终结果
    key_final: List[Dict[str, Any]]  # 最终重要keys

    # 多跳结果
    jump_results: List[Dict[str, Any]]  # 每跳的详细信息

    # 聚合统计
    total_jumps: int  # 实际跳跃次数
    convergence_reached: bool  # 是否收敛

    # 中间结果（调试用）
    all_events_by_jump: Dict[int, List[str]]  # 每跳找到的events
    all_keys_by_jump: Dict[int, List[str]]    # 每跳计算的keys
    weight_evolution: Dict[int, Dict[str, float]]  # 权重演化
```

### 最终Keys格式
```python
{
    "key_id": "entity_id",
    "name": "实体名称",
    "type": "实体类型",
    "weight": 0.85,  # 最终权重
    "steps": [1, 2]  # 经过的阶段 [1=Stage1, 2=Expand]
}
```

## 权重聚合策略

Expand采用加权平均策略聚合多跳结果：
- 越后面的跳跃权重越高
- 每跳的重要性 = 跳跃编号 / 总跳跃次数
- 最终权重 = Σ(每跳权重 × 跳跃重要性) / Σ(跳跃重要性)

## 收敛机制

### 自动收敛条件
1. **权重收敛**: 当前跳权重变化 < `expand_convergence_threshold`
2. **最大跳跃**: 达到 `max_jumps` 限制
3. **无结果**: 某跳没有找到关联事件或相似事件

### 收敛判断逻辑
```python
weight_change = abs(current_total_weight - previous_total_weight)
if weight_change < config.expand_convergence_threshold:
    # 收敛，停止跳跃
    convergence_reached = True
    break
```

## 性能优化

### 1. 批量处理
- Events按批次处理，避免单次查询过多数据
- 默认批次大小：20个events

### 2. 结果限制
- 每跳限制最大events数量：`expand_max_events`
- 限制keys数量：`max_keys`

### 3. 早期终止
- 收敛时自动停止
- 无结果时提前终止

## 调试和监控

### 日志记录
- 每个步骤的详细日志
- 权重变化追踪
- 收敛过程记录

### 测试脚本
运行测试脚本验证功能：
```bash
python test_expand.py
```

### 结果分析
- 查看 `jump_results` 了解每跳效果
- 分析 `weight_evolution` 观察权重变化
- 检查 `convergence_reached` 确认是否正常收敛

## 常见问题和解决

### 1. 跳跃次数过少
- **问题**: 只跳了1-2次就收敛
- **解决**: 降低 `expand_convergence_threshold` 或提高 `expand_event_threshold`

### 2. 找不到关联事件
- **问题**: 某跳没有找到events
- **解决**: 检查数据完整性，调整相似度阈值

### 3. 权重变化异常
- **问题**: 权重变化过大或过小
- **解决**: 调整 `expand_event_threshold` 和收敛阈值

### 4. 性能问题
- **问题**: 搜索速度过慢
- **解决**: 减少 `max_jumps` 和 `expand_max_events`

## 与Stage1的对比

| 特性 | Stage1 | Expand |
|------|--------|--------|
| 搜索深度 | 单次 | 多跳迭代 |
| 收敛机制 | 无 | 有 |
| 权重计算 | 线性 | 非线性迭代 |
| 结果精度 | 基础 | 更精确 |
| 计算成本 | 低 | 较高 |
| 适用场景 | 快速检索 | 深度挖掘 |

## 最佳实践

1. **参数调优**: 根据数据特点调整阈值参数
2. **结果验证**: 对比Stage1和Expand结果的质量
3. **性能监控**: 关注跳跃次数和收敛时间
4. **增量使用**: 先用Stage1，重要查询再使用Expand
5. **结果缓存**: 缓存常见查询的Expand结果