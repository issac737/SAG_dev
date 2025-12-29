# Elasticsearch Repositories 测试

## 📝 测试内容

本测试脚本全面测试 Elasticsearch 存储层的三个 Repository：

1. **EntityVectorRepository** - 实体向量存储
2. **EventVectorRepository** - 事件向量存储
3. **ArticleSectionRepository** - 文章片段存储

### 测试覆盖

- ✅ **增删查改 (CRUD)**：基础数据操作
- ✅ **向量检索 (KNN)**：向量相似度搜索（核心功能）
- ✅ **全文检索**：多字段文本搜索
- ✅ **过滤查询**：组合条件查询

## 🚀 运行方式

### 前置条件

1. **激活虚拟环境**
   ```bash
   source /Users/mac/dev/data_flow/.venv/bin/activate
   ```

2. **初始化 ES 索引**（首次运行）
   ```bash
   python scripts/init_es_indices.py
   ```

### 测试模式

#### 模式 1：随机向量测试（推荐，快速）

```bash
python tests/storage/test_es_repositories.py
```

**特点：**
- ⚡ 执行速度快（不调用 API）
- 💰 不消耗 Embedding API 配额
- 🔧 适合开发和 CI/CD 自动化测试
- 📊 向量维度：1024维（随机生成）

#### 模式 2：真实 Embedding API 测试

```bash
python tests/storage/test_es_repositories.py --use-real-embedding
```

**特点：**
- 🎯 使用真实 Embedding API 生成向量
- 🧠 验证语义相似度（如"人工智能" vs "机器学习"）
- 💸 消耗 API 配额
- ✅ 适合功能验证和演示
- 📊 向量维度：1024维（从 `.env` 配置读取）

## ⚙️ 配置

### Embedding API 配置

在 `.env` 文件中配置：

```env
# Embedding API 配置
EMBEDDING_API_KEY=your-api-key
EMBEDDING_MODEL_NAME=Qwen/Qwen3-Embedding-0.6B
EMBEDDING_DIMENSIONS=1024
EMBEDDING_BASE_URL=http://your-embedding-service/v1
```

### 向量维度说明

当前配置：**1024 维**

- 与 `.env` 中的 `EMBEDDING_DIMENSIONS` 保持一致
- 确保 ES 索引支持 1024 维向量
- 如果需要修改，同步更新以下位置：
  - `tests/storage/test_es_repositories.py` 中的 `VECTOR_DIM`
  - `scripts/init_es_indices.py` 中的索引 mapping
  - `.env` 中的 `EMBEDDING_DIMENSIONS`

## 📊 测试输出示例

### 随机向量模式

```
============================================================
  Elasticsearch Repositories 完整功能测试 - 随机向量 (1024维)
============================================================
  前置条件：ES索引已通过 scripts/init_es_indices.py 初始化

📝 初始化 Elasticsearch 客户端...
  ✅ ES 客户端已初始化
  ✅ Repositories 已创建

============================================================
  EntityVectorRepository 增删查改测试
============================================================
...
```

### 真实 Embedding 模式

```
============================================================
  Elasticsearch Repositories 完整功能测试 - 真实Embedding API (1024维)
============================================================
  前置条件：ES索引已通过 scripts/init_es_indices.py 初始化
  ⚠️  注意：使用真实Embedding API会消耗API配额

📝 测试 Embedding API 连接...
  ✅ Embedding API 连接成功！向量维度: 1024
...
```

## 🐛 常见问题

### 1. 向量维度不匹配

**错误信息**：
```
Error: [dense_vector] field requires an array of floats of size [1536] but was [1024]
```

**解决方案**：
```bash
# 重建索引（⚠️ 会清空数据）
python scripts/init_es_indices.py
```

### 2. Embedding API 连接失败

**错误信息**：
```
❌ Embedding API 连接失败: ...
```

**检查项**：
1. `.env` 文件中的 `EMBEDDING_API_KEY` 是否正确
2. `EMBEDDING_BASE_URL` 是否可访问
3. 网络连接是否正常
4. API 配额是否充足

### 3. ES 连接失败

**错误信息**：
```
❌ ES 初始化失败: Connection refused
```

**解决方案**：
```bash
# 检查 ES 服务是否运行
curl http://localhost:9200

# 或启动 ES 服务
docker-compose up -d elasticsearch
```

## 📁 文件说明

- `test_es_repositories.py` - 主测试脚本
- `__init__.py` - 包标识文件
- `README.md` - 本说明文档

## 🔗 相关文档

- [存储模块文档](../../docs/module.md#22-存储模块corestorage)
- [Elasticsearch 索引配置](../../scripts/init_es_indices.py)
- [项目配置说明](../../docs/README.md)
