# Load 模块测试

测试 `dataflow/modules/load/` 模块的功能。

## 📁 目录结构

```
tests/load/
├── __init__.py
├── fixtures/                      # 测试数据文件
│   ├── sample_article_1.md       # 测试文章1：AI医疗应用
│   └── sample_article_2.md       # 测试文章2：量子计算
└── test_document_loader.py       # DocumentLoader 完整流程测试
```

## 🧪 测试说明

### test_document_loader.py

测试 DocumentLoader 的完整加载流程：
1. Markdown 解析（MarkdownParser）
2. 元数据生成（DocumentProcessor + LLM）
3. 向量生成（DocumentProcessor + Embedding API）
4. MySQL 存储（Article + ArticleSection）
5. Elasticsearch 索引（article_sections）
6. 向量相似度搜索（KNN）
7. 全文检索

**运行方式：**
```bash
# 快速测试（使用随机向量）
python tests/load/test_document_loader.py

# 真实API测试（消耗API配额）
python tests/load/test_document_loader.py --use-real-embedding
```

**前置条件：**
1. 激活虚拟环境
2. MySQL 数据库已启动并初始化
3. Elasticsearch 已启动
4. ES 索引已初始化：`python scripts/init_es_indices.py`

## 📝 测试数据

### sample_article_1.md
- **主题**：人工智能技术在医疗领域的应用与展望
- **长度**：约1800字
- **章节**：9个主要章节
- **内容**：AI诊断、精准医疗、药物研发、智能健康管理等

### sample_article_2.md
- **主题**：量子计算：下一代计算革命
- **长度**：约1500字
- **章节**：7个主要章节
- **内容**：量子原理、应用领域、技术挑战、发展现状等

## 🔗 相关模块

- `dataflow/modules/load/loader.py` - DocumentLoader 主类
- `dataflow/modules/load/parser.py` - MarkdownParser 解析器
- `dataflow/modules/load/processor.py` - DocumentProcessor 处理器
