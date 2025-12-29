# DataFlow 数据库设计

**数据流智能引擎 - 数据库设计**

*by Zleap Team（智跃团队）*

---

## 1. 存储架构

### 1.1 存储策略

| 数据类型                     | 存储位置      | 原因                   |
| ---------------------------- | ------------- | ---------------------- |
| **信息源/文章/事项**       | MySQL         | 结构化、事务性强       |
| **文章片段**               | MySQL         | 结构化、顺序关联       |
| **实体信息**               | MySQL         | 需要精确匹配、关联查询 |
| **实体向量/片段向量**      | Elasticsearch | 向量检索、全文检索     |
| **LLM缓存**                | Redis         | 临时缓存、高频访问     |

---

## 2. MySQL 表结构

> 完整的实体维度说明请参考 [README.md](./README.md#灵活的实体维度)

### 2.1 信息源(source_config)

```sql
CREATE TABLE `source_config` (
  `id` CHAR(36) NOT NULL COMMENT '信息源ID (UUID)',
  `name` VARCHAR(100) NOT NULL COMMENT '信息源名',
  `description` VARCHAR(255) DEFAULT NULL COMMENT '信息源描述',
  `config` JSON DEFAULT NULL COMMENT '偏好设置，格式：{"focus": ["AI"], "language": "zh"}',
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 2.2 文章表（article）

```sql
CREATE TABLE `article` (
  `id` CHAR(36) NOT NULL COMMENT '文章ID (UUID)',
  `source_config_id` CHAR(36) NOT NULL COMMENT '信息源ID',
  `title` VARCHAR(500) NOT NULL COMMENT '文章标题',
  `summary` TEXT COMMENT '文章摘要（LLM生成）',
  `content` LONGTEXT COMMENT '文章正文',
  `category` VARCHAR(50) DEFAULT NULL COMMENT '分类',
  `tags` JSON DEFAULT NULL COMMENT '标签列表',
  `status` VARCHAR(20) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING-待处理, COMPLETED-已完成, FAILED-失败',
  `extra_data` JSON DEFAULT NULL COMMENT '其他元数据：{"url": "", "headings": []}',
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_source_config_id` (`source_config_id`),
  KEY `idx_source_status` (`source_config_id`, `status`),
  KEY `idx_category` (`category`),
  CONSTRAINT `fk_article_source_config` FOREIGN KEY (`source_config_id`) REFERENCES `source_config`(`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 2.3 文章片段表（article_section）

```sql
CREATE TABLE `article_section` (
  `id` CHAR(36) NOT NULL COMMENT '片段ID (UUID)',
  `article_id` CHAR(36) NOT NULL COMMENT '文章ID',
  `rank` INT NOT NULL COMMENT '片段序号（从0开始）',
  `heading` VARCHAR(500) NOT NULL COMMENT '标题/小标题',
  `content` LONGTEXT NOT NULL COMMENT '内容（纯文本）',
  `extra_data` JSON DEFAULT NULL COMMENT '元数据：{"type": "TEXT|IMAGE|CODE", "length": 0}',
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_article_id` (`article_id`),
  KEY `idx_article_rank` (`article_id`, `rank`),
  CONSTRAINT `fk_section_article` FOREIGN KEY (`article_id`) REFERENCES `article`(`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 2.5 源事件表（source_event）

**核心表，存储提取的事项信息**

```sql
CREATE TABLE `source_event` (
  `id` CHAR(36) NOT NULL COMMENT '事件ID (UUID)',
  `source_config_id` CHAR(36) NOT NULL COMMENT '信息源ID',
  `article_id` CHAR(36) NOT NULL COMMENT '文章ID',
  `title` VARCHAR(255) NOT NULL COMMENT '标题',
  `summary` TEXT NOT NULL COMMENT '摘要',
  `content` TEXT NOT NULL COMMENT '内容（事项正文）',
  `rank` INT NOT NULL DEFAULT 0 COMMENT '事项序号（同一来源内排序，从0开始）',
  `start_time` DATETIME DEFAULT NULL COMMENT '开始时间',
  `end_time` DATETIME DEFAULT NULL COMMENT '结束时间',
  `extra_data` JSON DEFAULT NULL COMMENT '元数据：{"keywords": [], "category": "", "priority": "", "status": ""}',
  `references` JSON DEFAULT NULL COMMENT '原始片段引用：[]',
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_source_config_id` (`source_config_id`),
  KEY `idx_article_id` (`article_id`),
  KEY `idx_article_rank` (`article_id`, `rank`),
  KEY `idx_start_time` (`start_time`),
  KEY `idx_end_time` (`end_time`),
  CONSTRAINT `fk_event_source_config` FOREIGN KEY (`source_config_id`) REFERENCES `source_config`(`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_event_article` FOREIGN KEY (`article_id`) REFERENCES `article`(`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```


### 2.6 实体类型表（entity_type）

**定义默认和自定义的实体类型**

```sql
CREATE TABLE `entity_type` (
  `id` CHAR(36) NOT NULL COMMENT '实体类型ID (UUID)',
  `source_config_id` CHAR(36) DEFAULT NULL COMMENT '信息源ID（NULL表示系统默认类型）',
  `type` VARCHAR(50) NOT NULL COMMENT '实体类型标识符（如：time, location, person, custom_xxx）',
  `name` VARCHAR(100) NOT NULL COMMENT '类型名称',
  `description` TEXT DEFAULT NULL COMMENT '类型描述说明',
  `weight` DECIMAL(3,2) NOT NULL DEFAULT 1.00 COMMENT '默认权重（0.00-9.99）',
  `similarity_threshold` DECIMAL(4,3) NOT NULL DEFAULT 0.800 COMMENT '相似度匹配阈值（0.000-1.000）- 用于实体向量搜索和去重时的最低相似度要求',
  `extra_data` JSON DEFAULT NULL COMMENT '元数据：{"extraction_prompt": "", "validation_rule": {}}',
  `is_active` BOOLEAN NOT NULL DEFAULT TRUE COMMENT '是否启用',
  `is_default` BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否系统默认类型',
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_source_type` (`source_config_id`, `type`),
  KEY `idx_default_active` (`is_default`, `is_active`),
  CONSTRAINT `fk_entity_type_source_config` FOREIGN KEY (`source_config_id`) REFERENCES `source_config`(`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**默认实体类型数据**：

```sql
-- 插入系统默认实体类型（6种）
INSERT INTO entity_type (id, source_config_id, type, name, is_default, description, weight, similarity_threshold) VALUES
(UUID(), NULL, 'time', '时间', TRUE, '<When> 时间节点或范围', 0.90, 0.900),
(UUID(), NULL, 'location', '地点', TRUE, '<Where> 地点位置', 1.00, 0.750),
(UUID(), NULL, 'person', '人员', TRUE, '<Who> 人物角色', 1.10, 1.000),
(UUID(), NULL, 'topic', '话题', TRUE, '<About> 核心话题', 1.50, 0.600),
(UUID(), NULL, 'action', '行为', TRUE, '<How> 行为动作', 1.20, 0.800),
(UUID(), NULL, 'tags', '标签', TRUE, '<Tag> 分类标签', 1.00, 0.700);
```

### 2.7 实体表（entity）

**存储提取的实体实例信息（多对多关系：通过 event_entity 关联表与事项关联）**

```sql
CREATE TABLE `entity` (
  `id` CHAR(36) NOT NULL COMMENT '实体ID (UUID)',
  `source_config_id` CHAR(36) NOT NULL COMMENT '信息源ID',
  `entity_type_id` CHAR(36) NOT NULL COMMENT '实体类型ID（引用entity_type.id）',
  `type` VARCHAR(50) NOT NULL COMMENT '实体类型标识符（冗余字段，便于查询）',
  `name` VARCHAR(500) NOT NULL COMMENT '实体名称',
  `normalized_name` VARCHAR(500) NOT NULL COMMENT '标准化名称（用于匹配，小写+去空格）',
  `description` TEXT DEFAULT NULL COMMENT '实体描述（可由LLM生成）',
  `extra_data` JSON DEFAULT NULL COMMENT '元数据：{"synonyms": [], "weight": 1.0, "confidence": 1.0}',
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_source_type_name` (`source_config_id`, `type`, `normalized_name`),
  KEY `idx_source_config_id` (`source_config_id`),
  KEY `idx_entity_type_id` (`entity_type_id`),
  KEY `idx_normalized_name` (`normalized_name`),
  KEY `idx_source_type` (`source_config_id`, `type`),
  CONSTRAINT `fk_entity_source_config` FOREIGN KEY (`source_config_id`) REFERENCES `source_config`(`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_entity_entity_type` FOREIGN KEY (`entity_type_id`) REFERENCES `entity_type`(`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**设计说明**：

- **entity_type_id**：实体类型ID，建立外键约束保证引用完整性
- **type**：实体类型标识符（冗余字段），避免每次查询都需要 JOIN entity_type 表
- **normalized_name**：添加索引以支持实体匹配查询
- **similarity_threshold**：每个实体类型定义了相似度匹配阈值（0.000-1.000），用于：
  - 实体向量检索时的最低相似度要求
  - 实体去重时判断是否为同一实体
  - 不同类型的阈值反映了其匹配精度需求（如人名1.0要求精确匹配，地点0.75允许表达多样性）
- **uk_source_type_name**：唯一约束，同一信息源内相同类型和标准化名称的实体应该唯一，实现实体复用
- **外键级联策略**：
  - `fk_entity_source`: CASCADE（删除信息源时级联删除实体）
  - `fk_entity_entity_type`: RESTRICT（防止删除正在使用的实体类型）

### 2.8 事项-实体关联表（event_entity）

**实现事项与实体的多对多关系**

```sql
CREATE TABLE `event_entity` (
  `id` CHAR(36) NOT NULL COMMENT '关联ID (UUID)',
  `event_id` CHAR(36) NOT NULL COMMENT '事项ID',
  `entity_id` CHAR(36) NOT NULL COMMENT '实体ID',
  `weight` DECIMAL(3,2) DEFAULT 1.00 COMMENT '该实体在此事项中的权重（0.00-9.99）',
  `extra_data` JSON DEFAULT NULL COMMENT '元数据：{"confidence": 0.95, "context": ""}',
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_event_entity` (`event_id`, `entity_id`),
  KEY `idx_event_id` (`event_id`),
  KEY `idx_entity_id` (`entity_id`),
  CONSTRAINT `fk_event_entity_event` FOREIGN KEY (`event_id`) REFERENCES `source_event`(`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_event_entity_entity` FOREIGN KEY (`entity_id`) REFERENCES `entity`(`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**设计说明**：

- **多对多关系**：一个事项可以关联多个实体，一个实体也可以被多个事项引用
- **唯一约束**：`uk_event_entity` 确保同一事项不会重复关联同一个实体
- **weight 字段**：允许为同一个实体在不同事项中设置不同的权重
- **级联删除**：删除事项或实体时，自动删除关联记录
- **实体复用优势**：同一个实体（如"曹操"）可以被多个事项引用，避免数据冗余

### 2.9 外键约束与数据完整性

**为什么需要外键约束？**

外键约束是保证数据库引用完整性的重要机制，它可以：
1. 防止插入无效的外键值（引用不存在的记录）
2. 自动处理级联删除/更新操作
3. 在数据库层面保证数据一致性
4. 减少应用层的逻辑复杂度

**外键约束汇总**：

| 约束名称                    | 子表         | 字段           | 父表         | 字段 | ON DELETE | ON UPDATE |
| --------------------------- | ------------ | -------------- | ------------ | ---- | --------- | --------- |
| `fk_article_source_config`         | article      | source_config_id      | source_config       | id   | CASCADE   | CASCADE   |
| `fk_section_article`        | article_section | article_id  | article      | id   | CASCADE   | CASCADE   |
| `fk_event_source_config`           | source_event | source_config_id      | source_config       | id   | CASCADE   | CASCADE   |
| `fk_event_article`          | source_event | article_id     | article      | id   | RESTRICT  | CASCADE   |
| `fk_entity_type_source_config`     | entity_type  | source_config_id      | source_config       | id   | CASCADE   | CASCADE   |
| `fk_entity_source_config`          | entity       | source_config_id      | source_config       | id   | CASCADE   | CASCADE   |
| `fk_entity_entity_type`     | entity       | entity_type_id | entity_type  | id   | RESTRICT  | CASCADE   |
| `fk_event_entity_event`     | event_entity | event_id       | source_event | id   | CASCADE   | CASCADE   |
| `fk_event_entity_entity`    | event_entity | entity_id      | entity       | id   | CASCADE   | CASCADE   |

**级联策略说明**：

1. **CASCADE（级联）**
   - 删除父记录时，自动删除所有子记录
   - 更新父记录主键时，自动更新所有子记录外键
   - 适用于：父子强依赖关系

2. **RESTRICT（限制）**
   - 如果存在子记录，则阻止删除/更新父记录
   - 适用于：需要先处理子记录的场景
   - 示例：删除 article 前必须先删除关联的 source_event

3. **SET NULL（设置为空）**
   - 删除父记录时，将子记录的外键设置为 NULL
   - 适用于：外键允许为空的可选关联

**数据删除影响链路**：

```
删除 source_config (信息源)
  ↓ CASCADE
  ├─ 删除所有 article (文章)
  │    ↓ CASCADE
  │    └─ 删除所有 article_section (文章片段)
  ├─ 删除所有 source_event (事项)
  │    ↓ CASCADE
  │    └─ 删除所有 event_entity (事项-实体关联)
  ├─ 删除所有 entity_type (自定义实体类型)
  └─ 删除所有 entity (实体)
       ↓ CASCADE
       └─ 删除所有 event_entity (事项-实体关联)

删除 article (文章)
  ↓ 检查是否有关联的 source_event
  ├─ 如果有 → RESTRICT 阻止删除
  └─ 如果没有 → 允许删除
       ↓ CASCADE
       └─ 删除所有 article_section (文章片段)

删除 source_event (事项)
  ↓ CASCADE
  └─ 删除所有 event_entity (事项-实体关联)

删除 entity (实体)
  ↓ CASCADE
  └─ 删除所有 event_entity (事项-实体关联)

删除 entity_type (实体类型)
  ↓ 检查是否有关联的 entity
  ├─ 如果有 → RESTRICT 阻止删除
  └─ 如果没有 → 允许删除
```

**最佳实践**：

1. **删除信息源前**：确认是否需要保留相关数据，CASCADE 会删除所有关联数据
2. **删除文章前**：先检查并处理关联的 source_event
3. **删除实体类型前**：先将使用该类型的实体改为其他类型或删除
4. **批量删除**：使用事务包裹，确保数据一致性

**迁移现有数据**：

如果数据库中已有数据，需要先确保数据完整性再添加外键：

```sql
-- 1. 检查孤儿记录
SELECT * FROM article WHERE source_config_id NOT IN (SELECT id FROM source_config);
SELECT * FROM entity WHERE entity_type_id NOT IN (SELECT id FROM entity_type);

-- 2. 清理孤儿记录或补充缺失数据

-- 3. 添加外键约束
ALTER TABLE article ADD CONSTRAINT fk_article_source_config
  FOREIGN KEY (source_config_id) REFERENCES source_config(id) ON DELETE CASCADE ON UPDATE CASCADE;
```

---

## 3. Elasticsearch 索引设计

> **向量维度说明**：Elasticsearch 8.0+ 支持在文档索引时自动推断 `dense_vector` 的维度，因此索引映射中不再需要硬编码 `dims` 字段。向量维度由实际使用的 Embedding 模型决定（如 Qwen/Qwen3-Embedding-0.6B 默认 1536 维，text-embedding-3-large 默认 3072 维）。

### 3.1 实体向量索引（entity_vectors）

```json
{
  "mappings": {
    "properties": {
      "entity_id": {"type": "keyword"},
      "source_config_id": {"type": "keyword"},
      "type": {"type": "keyword"},
      "name": {
        "type": "text",
        "fields": {"keyword": {"type": "keyword"}}
      },
      "vector": {
        "type": "dense_vector",
        "index": true,
        "similarity": "cosine"
      },
      "created_time": {"type": "date"}
    }
  },
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1
  }
}
```

### 3.2 事项向量索引（event_vectors）

```json
{
  "mappings": {
    "properties": {
      "event_id": {"type": "keyword"},
      "source_config_id": {"type": "keyword"},
      "article_id": {"type": "keyword"},
      "title": {
        "type": "text",
        "fields": {"keyword": {"type": "keyword"}}
      },
      "summary": {
        "type": "text"
      },
      "content": {
        "type": "text"
      },
      "title_vector": {
        "type": "dense_vector",
        "index": true,
        "similarity": "cosine"
      },
      "content_vector": {
        "type": "dense_vector",
        "index": true,
        "similarity": "cosine"
      },
      "category": {"type": "keyword"},
      "tags": {"type": "keyword"},
      "entity_ids": {"type": "keyword"},
      "start_time": {"type": "date"},
      "end_time": {"type": "date"},
      "created_time": {"type": "date"}
    }
  },
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1
  }
}
```

### 3.3 文章片段向量索引（article_sections）

```json
{
  "mappings": {
    "properties": {
      "section_id": {"type": "keyword"},
      "article_id": {"type": "keyword"},
      "source_config_id": {"type": "keyword"},
      "rank": {"type": "integer"},
      "heading": {
        "type": "text",
        "fields": {"keyword": {"type": "keyword"}}
      },
      "content": {
        "type": "text"
      },
      "heading_vector": {
        "type": "dense_vector",
        "index": true,
        "similarity": "cosine"
      },
      "content_vector": {
        "type": "dense_vector",
        "index": true,
        "similarity": "cosine"
      },
      "section_type": {"type": "keyword"},
      "content_length": {"type": "integer"},
      "created_time": {"type": "date"},
      "updated_time": {"type": "date"}
    }
  },
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1
  }
}
```

---

## 4. 关键查询示例

### 4.1 通过实体查询相关事项

```sql
-- 使用实体标准化名称查询事项（多对多关联）
SELECT DISTINCT se.*
FROM source_event se
JOIN event_entity ee ON se.id = ee.event_id
JOIN entity e ON ee.entity_id = e.id
WHERE e.normalized_name IN ('大模型', 'llm', '微调')
  AND se.source_config_id = ?
  AND e.source_config_id = ?;
```

**注意**：查询前需在应用层对实体名称进行标准化处理（如转小写、去空格等），然后使用 `normalized_name` 字段进行匹配，以提高匹配准确率。

### 4.2 获取信息源所有实体类型

```sql
-- 获取系统默认 + 信息源自定义实体类型
SELECT * FROM entity_type
WHERE (source_config_id IS NULL OR source_config_id = ?)
  AND is_active = TRUE
ORDER BY is_default DESC, weight DESC;
```

### 4.3 事项聚合查询

```sql
-- 获取事项及其所有实体（多对多关联）
SELECT
    se.*,
    GROUP_CONCAT(CONCAT(e.type, ':', e.name) SEPARATOR '|') as entity_list
FROM source_event se
LEFT JOIN event_entity ee ON se.id = ee.event_id
LEFT JOIN entity e ON ee.entity_id = e.id
WHERE se.source_config_id = ?
GROUP BY se.id
ORDER BY se.created_time DESC
LIMIT 10;
```

---

## 5. 索引策略

### 5.1 MySQL 索引优化

| 表名            | 索引类型  | 索引字段                          | 目的                 |
| --------------- | --------- | --------------------------------- | -------------------- |
| source_config          | UNIQUE    | name                              | 信息源唯一性         |
| article         | INDEX     | (source_config_id, status)               | 文章列表查询         |
| article_section | COMPOSITE | (article_id, rank)                | 按顺序获取片段       |
| source_event    | INDEX     | source_config_id, (article_id, rank), start_time | 多条件筛选   |
| entity_type     | UNIQUE    | (source_config_id, type)                 | 类型唯一性           |
| entity          | UNIQUE    | (source_config_id, type, normalized_name) | 实体唯一性           |
| entity          | INDEX     | source_config_id, entity_type_id, normalized_name, (source_config_id, type) | 实体查询     |
| event_entity    | UNIQUE    | (event_id, entity_id)             | 关联唯一性           |
| event_entity    | INDEX     | event_id, entity_id               | 双向查询优化         |

**外键约束汇总**：

| 子表         | 外键字段       | 父表         | 父表字段 | 级联删除 | 级联更新 | 说明                       |
| ------------ | -------------- | ------------ | -------- | -------- | -------- | -------------------------- |
| article      | source_config_id      | source_config       | id       | CASCADE  | CASCADE  | 删除信息源时删除所有文章   |
| article_section | article_id  | article      | id       | CASCADE  | CASCADE  | 删除文章时删除所有片段     |
| source_event | source_config_id      | source_config       | id       | CASCADE  | CASCADE  | 删除信息源时删除所有事项   |
| source_event | article_id     | article      | id       | RESTRICT | CASCADE  | 防止删除有关联事项的文章   |
| entity_type  | source_config_id      | source_config       | id       | CASCADE  | CASCADE  | 删除信息源时删除自定义类型 |
| entity       | source_config_id      | source_config       | id       | CASCADE  | CASCADE  | 删除信息源时删除所有实体   |
| entity       | entity_type_id | entity_type  | id       | RESTRICT | CASCADE  | 防止删除正在使用的实体类型 |
| event_entity | event_id       | source_event | id       | CASCADE  | CASCADE  | 删除事项时删除关联记录     |
| event_entity | entity_id      | entity       | id       | CASCADE  | CASCADE  | 删除实体时删除关联记录     |

### 5.2 性能优化建议

**连接池配置**：
```python
engine = create_async_engine(
    database_url,
    pool_size=20,          # 连接池大小
    max_overflow=40,       # 最大溢出连接数
    pool_pre_ping=True,    # 连接前测试
    pool_recycle=3600      # 连接回收时间（秒）
)
```

**缓存策略**：

| 数据类型    | 缓存时间 | Redis Key格式                |
| ----------- | -------- | ---------------------------- |
| 实体向量    | 24小时   | `entity:vector:{entity_id}`  |
| LLM摘要结果 | 7天      | `llm:summary:{content_hash}` |
| 检索结果    | 1小时    | `search:{query_hash}`        |

---

## 6. 数据初始化

### 6.1 初始化脚本

```sql
-- 创建数据库
CREATE DATABASE IF NOT EXISTS dataflow
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE dataflow;

-- 按顺序执行表创建（无外键依赖，但建议按此顺序）
-- 1. source_config, entity_type
-- 2. article, source_event
-- 3. article_section, entity
```

### 6.2 测试数据

```sql
-- 插入测试信息源
INSERT INTO source_config (id, name, description, config) VALUES
('test-source-001', 'AI技术博客', '专注于人工智能和机器学习的技术博客', '{"focus": ["AI", "ML", "Python"], "language": "zh"}');

-- 插入系统默认实体类型
INSERT INTO entity_type (id, source_config_id, type, name, is_default, description, weight) VALUES
('default-type-time', NULL, 'time', '时间', TRUE, '<When> 时间节点或范围', 0.90),
('default-type-location', NULL, 'location', '地点', TRUE, '<Where> 地点位置', 1.00),
('default-type-person', NULL, 'person', '人员', TRUE, '<Who> 人物角色', 1.10),
('default-type-topic', NULL, 'topic', '话题', TRUE, '<About> 核心话题', 1.50),
('default-type-action', NULL, 'action', '行为', TRUE, '<How> 行为动作', 1.20),
('default-type-tags', NULL, 'tags', '标签', TRUE, '<Tag> 分类标签', 1.00);

-- 插入测试文章
INSERT INTO article (id, source_config_id, title, summary, content, status) VALUES
('test-article-001', 'test-source-001', '深度学习入门指南',
 '本文介绍深度学习的基础概念，包括神经网络、反向传播等核心技术',
 '深度学习是机器学习的一个分支...', 'COMPLETED');

-- 插入测试文章片段
INSERT INTO article_section (id, article_id, rank, heading, content) VALUES
('test-section-001', 'test-article-001', 0, '什么是深度学习', '深度学习是一种基于人工神经网络的机器学习方法...'),
('test-section-002', 'test-article-001', 1, '神经网络基础', '神经网络由多个层组成，包括输入层、隐藏层和输出层...');

-- 插入测试事项
INSERT INTO source_event (id, source_config_id, article_id, title, summary, content, rank) VALUES
('test-event-001', 'test-source-001', 'test-article-001',
 '学习深度学习基础', '了解神经网络和反向传播算法',
 '需要学习深度学习的基础知识，包括神经网络结构、激活函数、反向传播等', 0);

-- 插入测试实体（多对多关系，不包含 event_id）
INSERT INTO entity (id, source_config_id, entity_type_id, type, name, normalized_name) VALUES
('test-entity-001', 'test-source-001', 'default-type-topic', 'topic', '深度学习', '深度学习'),
('test-entity-002', 'test-source-001', 'default-type-topic', 'topic', '神经网络', '神经网络'),
('test-entity-003', 'test-source-001', 'default-type-action', 'action', '学习', '学习');

-- 插入事项-实体关联
INSERT INTO event_entity (id, event_id, entity_id, weight) VALUES
('test-ee-001', 'test-event-001', 'test-entity-001', 1.50),
('test-ee-002', 'test-event-001', 'test-entity-002', 1.20),
('test-ee-003', 'test-event-001', 'test-entity-003', 1.00);
```

---

## 7. 相关文档

- [系统架构设计](./architecture.md) - 分层架构与模块职责
- [模块详细设计](./module.md) - 接口设计与数据模型
- [核心算法设计](./algorithm.md) - 动态权重与多跳召回
