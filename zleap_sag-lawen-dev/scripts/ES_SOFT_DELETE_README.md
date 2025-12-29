# ES 软删除功能脚本说明

本目录包含三个用于实现 Elasticsearch 软删除功能的脚本，需要按顺序执行。

## 脚本执行顺序

### 1. 添加软删除字段映射（每个服务器此脚本只需要执行一次）
**文件**: `es_version/es_add_soft_delete_mapping20251203.py`

为 ES 索引添加 `is_delete` 字段映射：
- `entity_vectors`
- `event_vectors`
- `source_chunks`

**作用**: 在 ES 索引中添加 `is_delete` 布尔类型字段，用于标记软删除状态。

**执行前确认**:
- ES 地址是否正确
- 目标索引列表

---

### 2. 标记孤立文档
**文件**: `es_mark_orphan_documents.py`

扫描 ES 中的孤立文档并标记为软删除：
1. 从 MySQL 获取所有有效的 `source_config_id`
2. 扫描三个 ES 索引，找出 `source_config_id` 不在 MySQL 中的文档
3. 输出 CSV 审计文件到 `output/` 目录
4. 将孤立文档的 `is_delete` 字段标记为 `true`

**作用**: 识别并软删除那些关联的 MySQL 配置已不存在的 ES 文档。

**安全措施**:
- 打印 ES 和 MySQL 地址供确认
- 输出 CSV 文件供审计
- 随机抽样显示待删除的 `source_config_id`
- 执行前二次确认

**输出文件**: `output/orphan_source_configs_YYYYMMDD_HHMMSS.csv`

---

### 3. 物理删除软删除文档
**文件**: `es_delete_soft_deleted.py`

物理删除标记为软删除的文档：
1. 统计三个索引中 `is_delete=true` 的文档数量
2. 执行物理删除操作

**作用**: 彻底删除已标记为软删除的文档，释放存储空间。

**安全措施**:
- 打印 ES 地址供确认
- 显示待删除文档数量
- 执行前确认
- 显示删除结果统计

**注意**: 此操作不可逆，删除后文档无法恢复。

---

## 使用场景

### 场景 1: 完整清理流程
当需要清理 ES 中的孤立文档时，按顺序执行三个脚本：

```bash
# 1. 添加字段映射（如果还未添加）
python es_version/es_add_soft_delete_mapping20251203.py

# 2. 标记孤立文档
python es_mark_orphan_documents.py

# 3. 物理删除
python es_delete_soft_deleted.py
```

### 场景 2: 定期清理
如果已经添加过字段映射，只需执行后两个脚本：

```bash
# 标记孤立文档
python es_mark_orphan_documents.py

# 物理删除
python es_delete_soft_deleted.py
```

### 场景 3: 安全验证
在执行物理删除前，可以只执行标记脚本，检查 CSV 输出文件，确认无误后再执行删除。

---

## 配置要求

所有脚本都需要正确的配置文件，确保以下连接信息正确：
- Elasticsearch 地址、用户名、密码
- MySQL 地址、数据库、用户名、密码（仅标记脚本需要）

---

## 注意事项

1. **执行顺序很重要**: 必须按 1→2→3 的顺序执行，否则会导致失败
2. **确认环境**: 每个脚本执行前都会显示连接信息，请仔细确认
3. **备份重要数据**: 建议在执行前备份重要数据
4. **观察输出**: 脚本会显示详细的执行进度和结果
5. **CSV 审计**: 标记脚本生成的 CSV 文件建议保留作为审计记录
