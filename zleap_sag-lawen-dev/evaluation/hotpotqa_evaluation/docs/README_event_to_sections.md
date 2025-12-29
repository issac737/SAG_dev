# 事项转段落工具使用指南

## 功能说明

该工具可以将搜索到的事项(SourceEvent)转换为对应的原始文档段落(ArticleSection)。

### 核心流程

```
事项列表 → 提取事项ID → 查询 source_event 表
    ↓
获取 references、article_id、source_config_id
    ↓
查询 article_section 表 → 返回段落列表
```

## 快速开始

### 方法 1：在 3_upload_corpus.py 中使用

修改后的 `3_upload_corpus.py` 已经集成了段落获取功能：

```bash
# 运行测试查询（会自动获取段落）
python 3_upload_corpus.py --test-queries

# 或仅运行搜索测试
python 3_upload_corpus.py --search-only
```

**输出示例**：
```
🔍 搜索问题: What is the capital of France?
✅ 找到 3 个相关事项

🔍 获取事项关联的段落...
✅ 找到 5 个段落

============================================================
段落详情
============================================================

1. 段落 #0: Introduction
   关联事项: Paris Overview
   事项得分: 0.8521
   内容预览: Paris is the capital and most populous city of France...

2. 段落 #1: Geography
   关联事项: Paris Overview
   事项得分: 0.8521
   内容预览: The city is located in northern France...
============================================================
```

### 方法 2：直接使用 EventToSectionConverter

```python
import asyncio
from event_to_sections import EventToSectionConverter

async def main():
    # 创建转换器
    converter = EventToSectionConverter()

    try:
        # 从 API 获取的事项列表
        events = [
            {'id': 'event-id-1', 'title': 'Event 1', 'score': 0.85},
            {'id': 'event-id-2', 'title': 'Event 2', 'score': 0.78}
        ]

        # 获取段落
        sections = await converter.get_sections_from_events(events)

        # 打印结果
        for section in sections:
            print(f"段落: {section['heading']}")
            print(f"关联事项: {section['event_title']}")
            print(f"内容: {section['content'][:100]}...")
            print()

    finally:
        await converter.close()

asyncio.run(main())
```

### 方法 3：使用同步包装函数

```python
from event_to_sections import EventToSectionConverter
import asyncio

# 定义同步包装函数
def get_sections_sync(events):
    async def _get_sections():
        converter = EventToSectionConverter()
        try:
            return await converter.get_sections_from_events(events)
        finally:
            await converter.close()

    return asyncio.run(_get_sections())

# 使用
events = pipeline.search_events(source_config_id, query)
sections = get_sections_sync(events)
```

## API 参考

### EventToSectionConverter

#### `__init__(db_url: Optional[str] = None)`

初始化转换器。

**参数**:
- `db_url`: 数据库连接 URL（可选，默认从配置读取）

#### `async get_sections_from_events(events, include_event_info=True)`

从事项列表获取关联的段落。

**参数**:
- `events`: 事项列表（API 返回的字典格式）
- `include_event_info`: 是否在结果中包含事项信息

**返回**:
```python
[
    {
        'section_id': 'section-uuid-1',
        'article_id': 'article-uuid-1',
        'rank': 0,
        'heading': '段落标题',
        'content': '段落内容...',
        'extra_data': {...},
        'event_id': 'event-uuid-1',      # 如果 include_event_info=True
        'event_title': '事项标题',         # 如果 include_event_info=True
        'event_summary': '事项摘要',       # 如果 include_event_info=True
        'event_score': 0.85              # 如果提供了 events_dict
    },
    ...
]
```

#### `async get_sections_by_event_ids(event_ids, include_event_info=True)`

通过事项 ID 列表获取段落。

**参数**:
- `event_ids`: 事项 ID 列表
- `include_event_info`: 是否包含事项信息

**返回**: 同上

#### `async get_event_details_with_sections(event_ids)`

获取事项的完整信息（包括关联的段落）。

**参数**:
- `event_ids`: 事项 ID 列表

**返回**:
```python
[
    {
        'event_id': 'event-uuid-1',
        'source_config_id': 'source-uuid-1',
        'article_id': 'article-uuid-1',
        'title': '事项标题',
        'summary': '事项摘要',
        'content': '事项内容',
        'rank': 0,
        'start_time': '2024-01-01T10:00:00',
        'end_time': None,
        'created_time': '2024-01-01T09:00:00',
        'sections': [
            {
                'section_id': 'section-uuid-1',
                'rank': 0,
                'heading': '段落标题',
                'content': '段落内容...',
                'extra_data': {...}
            },
            ...
        ]
    },
    ...
]
```

## 数据库查询详解

### 查询流程

```python
# 1. 查询事项，获取 references
SELECT id, references, article_id, source_config_id
FROM source_event
WHERE id IN (event_ids)

# 2. 提取所有 section_ids
section_ids = []
for event in events:
    section_ids.extend(event.references)

# 3. 查询段落
SELECT id, article_id, rank, heading, content, extra_data
FROM article_section
WHERE id IN (section_ids)
ORDER BY article_id, rank
```

### references 字段格式

`source_event.references` 字段存储为 JSON 数组：

```json
["section-uuid-1", "section-uuid-2", "section-uuid-3"]
```

表示该事项是从这三个段落中提取出来的。

## 注意事项

1. **异步操作**: 核心方法都是异步的，需要使用 `asyncio.run()` 或在 async 函数中调用

2. **数据库连接**:
   - 确保数据库配置正确（在 `dataflow/core/config/settings.py` 中）
   - 使用完毕后调用 `await converter.close()` 关闭连接

3. **references 为空**:
   - 如果事项的 `references` 字段为空，该事项不会返回任何段落
   - 这是正常现象，可能是旧数据或提取时未记录 references

4. **性能优化**:
   - 批量查询：一次性传入多个事项 ID，减少数据库查询次数
   - 预加载：使用 `selectinload` 避免 N+1 查询问题

## 典型使用场景

### 场景 1: 检索评估

```python
# 搜索事项
events = pipeline.search_events(source_config_id, query, top_k=10)

# 获取原始段落
sections = get_sections_sync(events)

# 评估段落是否包含答案
for section in sections:
    if answer in section['content']:
        print(f"✅ 找到答案！段落: {section['heading']}")
```

### 场景 2: 结果可视化

```python
# 获取完整的事项和段落信息
events = await converter.get_event_details_with_sections(event_ids)

# 在 Web 界面展示
for event in events:
    print(f"事项: {event['title']}")
    print(f"来源段落:")
    for section in event['sections']:
        print(f"  - {section['heading']} (段落 #{section['rank']})")
```

### 场景 3: 数据分析

```python
# 分析每个事项关联了多少段落
sections = await converter.get_sections_from_events(events)

event_section_count = {}
for section in sections:
    event_id = section['event_id']
    event_section_count[event_id] = event_section_count.get(event_id, 0) + 1

print(f"平均每个事项关联段落数: {sum(event_section_count.values()) / len(event_section_count):.2f}")
```

## 故障排查

### 问题 1: 返回空列表

**可能原因**:
- 事项的 `references` 字段为空
- 段落已被删除
- 事项 ID 不存在

**解决方法**:
```python
# 检查事项的 references
events_detail = await converter.get_event_details_with_sections(event_ids)
for event in events_detail:
    print(f"事项 {event['event_id']} 关联段落数: {len(event['sections'])}")
```

### 问题 2: 数据库连接失败

**可能原因**:
- 数据库配置错误
- 数据库服务未启动

**解决方法**:
- 检查 `.env` 文件中的 `DATABASE_URL`
- 确认数据库服务正常运行

### 问题 3: asyncio 错误

**可能原因**:
- 在非异步上下文中调用异步方法
- 事件循环冲突

**解决方法**:
```python
# 使用同步包装函数
sections = get_sections_sync(events)

# 或在异步函数中调用
async def main():
    converter = EventToSectionConverter()
    sections = await converter.get_sections_from_events(events)
    await converter.close()
```

## 更多示例

查看 `event_to_sections.py` 文件底部的 `demo()` 函数获取更多使用示例。

运行示例：
```bash
python event_to_sections.py
```
