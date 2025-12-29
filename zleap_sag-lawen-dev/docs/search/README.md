# 搜索模块文档目录

## 📚 文档列表

### 核心文档

1. **[usage.md](./usage.md)** - 使用指南 ⭐ 推荐阅读
   - 快速开始
   - 三种搜索模式详解（LLM/RAG/SAG）
   - 高级用法和最佳实践
   - 故障排查

2. **[rag.md](./rag.md)** - RAG 三路向量检索详解 ⭐ 新增
   - 架构设计和流程图
   - 三路检索详细说明
   - 融合策略和公式
   - 性能分析和调优
   - 最佳实践

3. **[base.md](./base.md)** - SAG 算法实现原理
   - 数据处理流程（Summary → Event → Key）
   - 检索过程（三阶段详解）
   - 查询过程（三种模式对比）
   - 聚类过程（Louvain算法）
   - IDF计算完整代码

4. **[stage1.md](./stage1.md)** - Stage1 搜索器文档
   - 8步骤复合搜索算法
   - 使用指南和配置说明
   - 实现细节

5. **[CHANGELOG.md](./CHANGELOG.md)** - 更新日志
   - v1.1 版本更新内容（RAG实现）
   - v1.0 版本更新内容（架构搭建）
   - 功能变更记录
   - 向后兼容性说明

## 🚀 快速开始

### 基本使用

```python
from dataflow.modules.search import EventSearcher, SearchConfig, SearchMode

# 初始化搜索器
searcher = EventSearcher(llm_client, prompt_manager)

# LLM模式（默认）
config = SearchConfig(
    query="查找关于AI的事项",
    source_config_id="source_123",
    mode=SearchMode.LLM,  # 可省略
)
results = await searcher.search(config)
```

### 三种搜索模式

| 模式 | 状态 | 特点 | 适用场景 |
|------|------|------|----------|
| **LLM** | ✅ 可用 | 智能理解、深度筛选 | 复杂查询、语义理解 |
| **RAG** | ✅ 可用 | 快速、高召回、三路检索 | 延迟敏感、大规模检索 |
| **SAG** | 🔄 开发中 | 精准、可解释 | 属性驱动、多跳推理 |

## 📖 详细文档

### [使用指南 (usage.md)](./usage.md)

完整的使用教程，包含：
- 三种搜索模式的详细说明
- 代码示例和最佳实践
- 配置参数说明
- 错误处理和故障排查

**适合人群**：开发者、使用者

### [SAG 算法原理 (base.md)](./base.md)

深入的算法实现文档，包含：
- 数据处理的完整流程
- 检索的三阶段算法
- 数学公式和伪代码
- Python实现示例

**适合人群**：算法研究者、核心开发者

### [Stage1 文档 (stage1.md)](./stage1.md)

Stage1搜索器的专项文档，包含：
- 8步骤搜索算法详解
- 配置参数说明
- 使用示例
- 调试技巧

**适合人群**：使用Stage1的开发者

## 🎯 开发路线图

### 当前版本 (v1.1) ✅

- ✅ 多搜索模式架构
- ✅ LLM智能检索
- ✅ RAG三路向量检索
- ✅ Stage1搜索器（SAG第一阶段）
- ✅ 完整文档体系

### 下一版本 (v1.2) 🔄

- 🔄 RAG增强功能
  - BM25混合检索
  - Rerank重排序
  - 自适应权重调整

### 未来版本 (v2.0) 📅

- 📅 SAG完整实现（三阶段）
- 📅 多跳推理
- 📅 PageRank排序
- 📅 查询改写
- 📅 DAG子查询

## 🔗 相关链接

- **示例代码**: [examples/search_modes_demo.py](../../examples/search_modes_demo.py)
- **引擎配置**: [dataflow/engine/config.py](../../dataflow/engine/config.py)
- **主项目文档**: [docs/README.md](../README.md)

## 💡 常见问题

### Q: 如何选择搜索模式？

| 需求 | 推荐模式 |
|------|----------|
| 复杂语义理解 | LLM |
| 快速响应 | RAG（开发中） |
| 属性精准查询 | SAG（开发中） |
| 探索性搜索 | LLM |

### Q: RAG和SAG何时可用？

- **RAG**: ✅ v1.1 版本已实现（三路向量检索）
- **SAG**: 计划在 v2.0 版本完整实现（Stage1已可用）

### Q: 向后兼容性如何？

✅ **完全向后兼容**！所有现有代码无需修改：

```python
# 旧代码依然有效
config = SearchConfig(query="...", source_config_id="...")
# mode 自动默认为 SearchMode.LLM
```

### Q: 如何参与开发？

1. 阅读 [base.md](./base.md) 了解算法原理
2. 查看 `TODO` 注释定位待实现功能
3. 参考 Stage1 的实现风格
4. 提交 PR 贡献代码

## 📊 性能参考

### LLM模式

- **响应时间**: 2-5秒
- **Token消耗**: 与事项数量成正比
- **适用规模**: < 1000个事项

### RAG模式

- **响应时间**: < 500ms
- **召回率**: 90%+
- **精准度**: 85%+
- **适用规模**: 任意规模

### SAG模式（预期）

- **响应时间**: 1-3秒
- **适用规模**: < 10000个事项

## 🤝 贡献指南

欢迎贡献代码、文档或建议！

**改进方向**：
1. 实现RAG搜索功能
2. 完善SAG多跳推理
3. 优化搜索性能
4. 补充使用案例
5. 改进文档质量

---

**最后更新**: 2025-10-20  
**版本**: v1.0  
**维护者**: DataFlow Team

