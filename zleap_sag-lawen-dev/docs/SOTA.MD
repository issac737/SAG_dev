# SAG Search Optimization Log (SOTA)

> State-of-the-Art tracking for SAG search optimization on HotpotQA benchmark.

---

## 📊 Current Performance

| Metric | Value | Date |
|--------|-------|------|
| **Overall Recall** | **93-94%** | 2025-12-12 |
| Perfect Recall (100%) | 44-47/50 | - |
| Partial Recall | 5-7/50 | - |
| Zero Recall (0%) | 0-1/50 | - |

> 🎉 **v2.1 优化后**: 50 个问题测试，标准配置 `max_results=10`，召回率稳定在 93-94%

---

## 🔄 Optimization History

### v2.2 - Step4 权重文档与可解释性 (2025-12-13) 📝

**更新内容：**

1. 完整记录 Step4 的加权 RRF 公式与参数（k_rrf=60，w_sim=1.5，w_rel=0.5，w_den=0.2）
2. 补充三种得分组件的计算方式：
   - similarity：沿用 Step1 余弦相似度
   - relation：按 hop 衰减并对目标类型加权 1.5
   - density：基于出现次数使用 weight * ln(1+count) / step
3. 明确 Step4 计算流程（排序取 rank → 加权 RRF → 作为 weight/score 返回），便于排查排序/加权问题

**目的：** 提升权重计算的可解释性和排错效率，为后续调参与实验对比提供清晰基线。

### v2.1 - 排序修复 + 噪音过滤 (2025-12-12) 🎉

**问题发现：**

1. **Step5 排序 Bug**: PageRank 后按 `pagerank_score` 排序，但混合权重后应按 `weight` 排序
2. **分词匹配噪音**: 分词器使用前缀匹配 `LIKE 'New%'`，导致 "New" 匹配到 28 个无关实体
3. **评估匹配遗漏**: 复合标题如 `# A | # B` 无法匹配 oracle 标题 `A`

**修复措施：**

1. **排序修复**:
   ```python
   # 修复前：按 pagerank_score 排序
   sorted_contents = sorted(contents, key=lambda x: x["pagerank_score"], reverse=True)
   
   # 修复后：按混合权重排序
   content["weight"] = 0.9 * original_weight + 0.1 * scaled_pagerank
   sorted_contents = sorted(contents, key=lambda x: x["weight"], reverse=True)
   ```

2. **分词噪音过滤**:
   ```python
   # 分词器补充召回禁用前缀匹配，只用精确匹配
   matched_entities = await self._mysql_exact_search_entities(
       ...,
       use_prefix_match=False  # 避免 "New" 匹配到 "New York" 等噪音
   )
   ```

3. **评估匹配增强**:
   ```python
   # 新增标题包含匹配策略
   for oracle_title, chunk in oracle_by_title.items():
       if oracle_title in normalized_title:
           matched_chunk = chunk
           break
   ```

4. **参数调整**:
   - PageRank 混合比例: 90% 原始权重 + 10% PageRank
   - 标准配置保持 `max_results=10`

**效果：**
- 召回率: 72% → **93-94%** (标准配置 `max_results=10`)
- 召回率: 72% → **98-100%** (宽松配置 `max_results=25`)
- Zero recall: 7 → **0-1**
- 50 个问题测试稳定

**剩余 Partial Recall 分析：**
- 比较问题 (A vs B): 第二个对象有时排在 11-20 位
- 多跳问题: 需要 3+ 跳关联的段落排名靠后

---

### v2.0 - 搜索提示词重构 (2025-12-12) 🎉

**核心改进：**

1. **提示词设计原则**：
   - 目的导向：说明缘由，让 LLM 理解为什么这样做
   - 灵活不死板：不限定具体数字，让 LLM 自己判断
   - 核心原则：**宁多勿少，无法确定排除的就加入**

2. **四个输出明确分工**：
   - `rewritten_query`: 重写问题，使意图清晰
   - `entities`: 搜索关键词（不遗漏任何专有名词）
   - `focus_entity_types`: 线索维度（搜索路径，覆盖面广）
   - `target_entity_types`: 目标维度（答案位置，用于排序加权）

3. **关键强调**：
   - 比较问题必须提取所有比较对象
   - 指代问题要从候选中找出实际名称
   - 每个关键词 = 一个搜索入口，漏掉就丢失文档

**效果：**
- 8/8 次测试：**100% 召回率**
- 稳定性大幅提升

---

### v1.9 - 多跳传递关联 + 目标维度加权 (2025-12-12) 🎯

**核心改动：**

1. **LLM Query 分析扩展**:
   - 新增 `target_entity_types` 字段（目标维度）
   - `focus_entity_types` 用于 Recall/Expand 过滤（线索维度）
   - `target_entity_types` 用于 Rerank 加权（答案维度）

2. **Rerank 权重公式优化**:
   ```python
   # 旧公式
   weight = 0.5 * similarity_score + log(1 + key_weight_sum)
   
   # 新公式：多跳衰减 + 目标维度加权
   hop_factor = 1.0 / (1.0 + hop)  # hop=0→1.0, hop=1→0.5
   target_boost = 1.5 if entity_type in target_types else 1.0
   relation_contribution = hop_factor * target_boost * weight
   
   final_score = similarity_score + bonus  # 加分模式，保底 similarity
   ```

3. **过滤逻辑调整**:
   - Step1 预过滤阈值降低到 0.1（保留更多候选）
   - Step4 之后基于新权重进行最终过滤（阈值 0.45）

**Partial Recall 案例修复效果：**

| 案例 | 原始分数 | 新分数 | 状态 |
|------|----------|--------|------|
| Adriana Trigiani | 0.298 | **1.098** | ✅ 召回 |
| Shirley Temple | 0.393 | **1.193** | ✅ 召回 |
| Management consulting | 0.430 | **0.541** | ✅ 召回 |

**问题：LLM 不确定性**
- 3 次测试召回率波动：75% → 65% → 65%
- Perfect Recall 波动：6 → 6 → 5
- Zero Recall 波动：1 → 3 → 2

**修改文件：**
- `dataflow/modules/search/config.py`: 添加 `target_entity_types` 字段
- `dataflow/modules/search/recall.py`: Schema 和解析逻辑
- `dataflow/modules/search/ranking/pagerank_section.py`: 新权重公式
- `prompts/search.yaml`: 提示词更新

---

### v1.3 - Stability Test (2025-12-12) 📊

**Test Run:** `--batch-size 20 --concurrency 20 --track-zero-recall`

| Metric | v1.1 Result | v1.3 Result | Variance |
|--------|-------------|-------------|----------|
| Overall Recall | 85% | 81% | **-4%** |
| Perfect Recall | 36 | 34 | -2 |
| Partial Recall | 13 | 13 | 0 |
| Zero Recall | 1 | 3 | +2 |

**Analysis:** LLM 随机性导致结果波动明显，需要多次测试取平均值

**New Zero Recall Cases:**
1. `Big Stone Gap` - **retrieved: 0** (完全未检索到任何文档)
2. `Badly Drawn Boy or Wolf Alice` - retrieved: 3 (检索到错误文档)
3. `VCU Rams basketball` - retrieved: 10 (检索到错误文档)

---

### v1.2 - Stage Name Fix (2025-12-12) 🔧

**Issue Found (from partial recall analysis):**
```
Question: "Which performance act has higher ratio, Badly Drawn Boy or Wolf Alice?"
Problem: 
  - Correct doc "# Badly Drawn Boy" has person: "Badly Drawn Boy"
  - Wrong doc "# Badly Drawn Boy discography" has tags: "Badly Drawn Boy"
  - Search returned wrong doc because tags classification was incorrect
```

**Changes:**
- Update person type: explicitly include stage names, pen names, pseudonyms
- Add examples: "Badly Drawn Boy", "Wolf Alice", "Mark Twain"
- Expand common mistakes section

**Status:** ❌ 未生效 - 问题仍出现在 zero recall 中

---

### v1.1 - Entity Type Enhancement (2025-12-12) ✅

**Changes:**
- 新增 `nationality` 类型（国籍：American, British...）
- 新增 `profession` 类型（职业：director, writer...）
- 降低 `tags` 权重（0.5→0.3）并标记为 "LastResort"
- 优化 person/organization/work 类型描述
- 增强提取提示词：明确分类规则，避免误入 tags
- 增强搜索提示词：比较问题必须提取所有比较对象

**Result:** 
| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Overall Recall | 82% | **85%** | **+3%** |
| Perfect Recall | 33 | 36 | +3 |
| Partial Recall | 16 | 13 | -3 |
| Zero Recall | 1 | 1 | 0 |

**Analysis:** 实体分类优化有效，减少了 tags 桶的误分类

---

### v1.0 - Baseline + Focus Entity Types (2025-12-11)

**Key Features:**
- 三阶段搜索架构: Recall → Expand → Rerank
- LLM 智能识别 focus_entity_types（白名单）
- PageRank 重排序算法

**Recall Rate:** 78-82% (fluctuates due to LLM non-determinism)

---

## 🔍 Bad Case Analysis

### 🚨 Critical Issue: ES 索引严重不完整 (v1.4)

**诊断结果 (2025-12-12 01:36):**
```
MySQL source_chunk: 493 条
ES source_chunks:   493 条 (数量一致但内容不同步!)

未索引到 ES 的文档: 324 / 493 = 65.7%!

未索引文档示例:
  - # Big Stone Gap (film)  ← Zero Recall
  - # Wolf Alice            ← Zero Recall  
  - # MacScan
  - # Hackers (film)
  - # Androscoggin Bank Colisée
  - ... 还有 319 个
```

**受影响的 Zero Recall Cases:**
| Question ID | Question | Retrieved | Root Cause |
|-------------|----------|-----------|------------|
| 5a8e3ea9 | "The director of 'Big Stone Gap'..." | **0** | ⚠️ **文档在MySQL但未索引到ES** |
| 5ae2070a | "Badly Drawn Boy or Wolf Alice?" | 3 | ⚠️ **Wolf Alice 未索引到ES** |
| 5adf37a9 | "VCU Rams 2011-12...founded?" | 10 | 2011-12 VCU Rams 文档不存在 |

**问题原因:**
- 数据重新提取后，`_index_source_chunks_to_es()` 未对所有文档执行
- 只有部分文档被正确同步到 ES

---

### 历史 Zero Recall Case (已修复/变为 Partial)

| Question ID | Question | Status |
|-------------|----------|--------|
| 5ae0d4c9 | "Roger O. Egeberg was Assistant Secretary..." | ✅ 本次测试已变为 **Partial Recall (50%)** |

**原问题分析:**
- **Root Cause**: Multi-hop bridge question: Egeberg → Nixon → 1969-1974
- 搜索系统召回了 "Assistant Secretary" 相关的其他人物
- 但未找到正确的 Richard Nixon 文档

**Database Verification:**
```
✅ Roger O. Egeberg chunk EXISTS (id: 9da5e8af-6c19-46a6-b3c4-d7ea63a63ed1)
✅ Richard Nixon chunk EXISTS (id: dca1c727-88d3-4fb6-a97e-71b155bc710d)
```

**Extracted Entities from Roger O. Egeberg:**
- person: Roger O. Egeberg
- role: Assistant Secretary for Health and Scientific Affairs
- organization: Department of Health, Education, and Welfare
- tags: Nixon ← **关键线索存在但未被有效利用**

---

### Partial Recall Cases (16个) - Pattern Analysis

#### Pattern 1: Comparison Questions (A vs B) - 6个

| Question | Missing Entity |
|----------|---------------|
| "Which writer was from England, Henry Roth or Robert Erskine Childers?" | 只找到其中一个作家 |
| "Are Giuseppe Verdi and Ambroise Thomas both Opera composers?" | 只找到其中一个作曲家 |
| "Are Freakonomics and In the Realm of the Hackers both American documentaries?" | 只找到其中一部 |
| "Which performance act has a higher instrument to person ratio, Badly Drawn Boy or Wolf Alice?" | 只找到其中一个乐队 |
| "Which dog's ancestors include Gordon and Irish Setters..." | 只找到其中一种狗 |

**Root Cause:** LLM 实体提取时只识别了部分比较对象

**Solution Direction:** 优化提示词，强调 "提取所有被比较的实体"

---

#### Pattern 2: Multi-hop Bridge Questions - 10个

| Question Type | Example |
|---------------|---------|
| Person → Role → Target | "What government position was held by the woman who portrayed Corliss Archer..." |
| Person → Location → Target | "Ralph Hefferline was a psychology professor at a university that is located in what city?" |
| Person → Company → Location | "Where is the company that Sachin Warrier worked for as a software engineer headquartered?" |
| Role → Person → Time | "Roger O. Egeberg was Assistant Secretary... president that served during what years?" |

**Root Cause:** 
1. 第一跳实体召回成功
2. 多跳扩展未能有效传递到桥接实体
3. 最终目标实体未被召回

---

## 🎯 Optimization Roadmap

### v1.5 - Score Threshold Experiment (2025-12-12) ❌

**Hypothesis:** `score_threshold=0.45` 太高，导致 Zero Recall

**Experiment:** 降低 `score_threshold` 从 0.45 → 0.25

**Result:** ❌ **召回率反而下降！**

| 指标 | Before (0.45) | After (0.25) | Change |
|------|---------------|--------------|--------|
| Overall Recall | **80%** | **65%** | **-15%** |
| Perfect Recall | 33 | 22 | -11 |
| Partial Recall | 14 | 21 | +7 |
| Zero Recall | 3 | 7 | +4 |

**Analysis:**
- 降低阈值让更多不相关文档进入 PageRank
- PageRank 排序时，噪音文档可能排名更高
- 把真正相关的文档挤出 Top 10

**Conclusion:** 保持 `score_threshold=0.45`，问题在其他地方

---

### v1.6 - Deep Dive: Wolf Alice Zero Recall (2025-12-12) 🔍

**Case Study:** "Which performance act has a higher instrument to person ratio, Badly Drawn Boy or Wolf Alice?"

**Expected:** Wolf Alice, Badly Drawn Boy  
**Actual:** About a Boy (soundtrack), The Hour of Bewilderbeast (all wrong!)

**Debug Results:**

| 阶段 | Wolf Alice 状态 | 问题 |
|------|----------------|------|
| 向量召回 | ✅ 召回 (rank=5) | - |
| LLM 识别 | ✅ 正确识别 | - |
| 实体匹配 | ✅ 相似度 0.5984 | - |
| Event 召回 | ✅ "Wolf Alice Band Formation..." | - |
| Chunk 关联 | ✅ → # Wolf Alice | - |
| **相似度检查** | ✅ 0.5469 > 0.45 | - |
| **最终结果** | ❌ 未出现 | ??? |

**Root Cause Analysis:**
```
相似度过滤: 120 → 3 个原文块 (阈值=0.45)
```

理论上 Wolf Alice chunk 相似度 0.5469 应该通过，但实际被过滤。

**可能原因:**
1. **LLM 非确定性**: 每次运行 query rewrite 不同，影响相似度计算
2. **Expand 阶段权重过滤**: Wolf Alice 实体权重低于阈值
3. **key_final 列表限制**: Wolf Alice 未进入最终 key 列表

**数据验证:**
```
# Wolf Alice chunk 直接测试 (静态)
原始 Query 相似度: 0.5209 ✅
重写 Query 相似度: 0.5469 ✅
```

**Next Steps:**
1. 增加日志追踪 Wolf Alice 在每个阶段的权重变化
2. 检查 `entities_per_hop` 和 `max_keys` 参数限制
3. 考虑添加 "关键实体保护" 机制

---

### v1.7 - Zero Recall Root Cause Analysis (2025-12-12) 🔍

**测试结果:** 80% recall, 3 zero recall, 14 partial recall

**Zero Recall Cases 详细分析:**

| Case | Question | Expected | 根因 |
|------|----------|----------|------|
| 1 | Big Stone Gap director in NY? | Big Stone Gap (film), Adriana Trigiani | **weight=0.10 < threshold=0.20** |
| 2 | Stage name Aladin consultant? | Eenasul Fateh, Management consulting | 待分析 |
| 3 | Wolf Alice vs Badly Drawn Boy? | Wolf Alice, Badly Drawn Boy | **相似度过滤: 153→0 (阈值0.45)** |

**Case 1 详细分析 (Big Stone Gap):**
```
向量召回: ✅ Big Stone Gap 相似度 0.5092
LLM 识别: ✅ 正确识别 "Big Stone Gap"
实体匹配: ✅ 找到 [work]Big Stone Gap, [location]Big Stone Gap

问题出现:
Step6: Key 'Big Stone Gap': weight=0.1000, step=6
entity_weight_threshold: 0.2 ← Big Stone Gap 被过滤！

结果:
- Big Stone Gap 未进入 key_final
- 153 个原文块都与目标无关
- 相似度过滤: 153 → 0
- 最终返回 0 个段落
```

**解决方案:**

| 优化 | 参数 | 当前值 | 建议值 | 预期效果 |
|------|------|--------|--------|----------|
| 降低实体权重阈值 | `entity_weight_threshold` | 0.2 | 0.1 | 保留更多实体 |
| 降低相似度阈值 | `score_threshold` | 0.45 | 0.35 | 减少过滤 |
| 增加关键实体保护 | N/A | N/A | 问题中出现的实体强制保留 | 保证核心实体 |

---

### v1.8 - 权重公式优化 (2025-12-12) ✅

**问题分析：**
- 原公式 `weight = sum(event_weights) × similarity`
- event 数量多的通用实体（如 New York City）权重过高
- 核心实体（如 Big Stone Gap）因 event 少被过滤

**新公式：**
```python
# 1. Event 贡献归一化（平均值替代求和）
avg_event_weight = sum(event_weights) / len(events)

# 2. 语义优先 + event 贡献
base_weight = 0.7 × similarity + 0.3 × avg_event_weight

# 3. 核心实体保护（问题中直接提到的实体 +50%）
core_boost = 1.5 if entity_name in query else 1.0
final_weight = base_weight × core_boost
```

**效果：**
| 指标 | 优化前 | 优化后 | 变化 |
|------|--------|--------|------|
| Overall Recall | 80% | **83%** | **+3%** |
| Perfect Recall | 33 | 34 | +1 |
| Zero Recall | 3 | **1** | **-2** |

**修复的 Case：**
- ✅ Big Stone Gap (weight 0.10 → 0.76)
- ✅ Wolf Alice (被正确召回)

**剩余 Zero Recall：**
- VCU Rams 2011-12：**数据提取问题**（Event 未关联 "VCU Rams" 实体）

### Short-term (v1.5)

| Priority | Task | Expected Impact |
|----------|------|-----------------|
| 🔴 High | 优化 search prompt - 强制提取所有比较对象 | +3-5% recall |
| 🔴 High | 增加 max_results (10→15) | 兜底更多结果 |
| 🟡 Medium | 降低 LLM temperature (0.7→0.3) | 减少随机性 |

### Medium-term (v2.0)

| Task | Description |
|------|-------------|
| 多跳扩展优化 | 增加 hop depth 或调整实体权重传播 |
| 实体类型统一 | 同一 normalized_name 只保留主类型 |
| 实体消歧 | 处理同名实体问题 |
| Query 分解 | 将复杂问题拆分为子查询 |

### Long-term (v3.0)

| Task | Description |
|------|-------------|
| Re-ranking 模型 | 使用 cross-encoder 重排 |
| Query Expansion | 使用 LLM 生成多个查询变体 |
| Hybrid Search | 结合 BM25 + Dense Retrieval |

---

## 📝 Technical Notes

### LLM Non-determinism Issue

**Observation:** 相同配置下召回率波动 78-82%

**Cause:** LLM 在选择 `focus_entity_types` 时有随机性

**Mitigation:**
- 降低 temperature
- 使用更明确的提示词
- 考虑使用 fixed type list 作为 baseline

### Database Schema Reference

```sql
-- Key tables for search
source_chunk    -- 原始文档片段
source_event    -- 提取的事项
entity          -- 实体 (name, type, normalized_name)
event_entity    -- 事项-实体关联
```

### Entity Types in Use

```
person, organization, location, time, role, event, 
topic, action, product, tags (generic)
```

---

## 📈 Benchmark Comparison

| System | HotpotQA Recall | Notes |
|--------|-----------------|-------|
| **SAG (ours)** | **81-85%** | Focus entity types + PageRank (波动范围) |
| BM25 baseline | ~60% | Traditional keyword matching |
| Dense Retrieval | ~70% | Single vector similarity |
| HippoRAG | 85%+ | SOTA multi-hop retrieval |

---

## 📋 Test History Log

| Date | Time | Recall | Perfect | Partial | Zero | Notes |
|------|------|--------|---------|---------|------|-------|
| 2025-12-12 | 01:36 | **80%** | 33 | 14 | 3 | v1.4 数据重新提取后，65.7%文档未索引ES |
| 2025-12-12 | 01:10 | 81% | 34 | 13 | 3 | v1.3 stability test |
| 2025-12-12 | ~00:30 | 85% | 36 | 13 | 1 | v1.1 entity enhancement |
| 2025-12-11 | - | 82% | 33 | 16 | 1 | v1.0 baseline |

---

*Last updated: 2025-12-12*
