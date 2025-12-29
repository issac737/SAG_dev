-- ================================================================
-- 主系统数据库迁移脚本：source_chunk 表
-- ================================================================
-- 目的：添加外键支持，实现级联删除
-- 执行数据库：zleap_test (主系统)
-- 创建时间：2025-11-13
-- 相关功能：DataFlow 片段管理和级联删除
-- ================================================================

USE zleap_test;

-- ================================================================
-- 迁移前检查
-- ================================================================

-- 1. 查看当前表结构
SHOW CREATE TABLE `source_chunk`\G

-- 2. 统计当前数据
SELECT 
    COUNT(*) as total_chunks,
    COUNT(DISTINCT source_config_id) as unique_sources,
    SUM(CASE WHEN source_type = 'ARTICLE' THEN 1 ELSE 0 END) as article_chunks,
    SUM(CASE WHEN source_type = 'CHAT' THEN 1 ELSE 0 END) as conversation_chunks
FROM `source_chunk`;

-- 3. 检查 source_config_id 是否有 NULL 值
SELECT COUNT(*) as null_config_count
FROM `source_chunk` 
WHERE source_config_id IS NULL;
-- 预期：0（如果>0，需要先填充默认值）

-- ================================================================
-- 开始迁移
-- ================================================================

-- ----------------------------------------------------------------
-- 1. 添加外键字段
-- ----------------------------------------------------------------

-- 添加 article_id 字段
ALTER TABLE `source_chunk` 
ADD COLUMN `article_id` CHAR(36) NULL COMMENT '文章ID（外键）' AFTER `source_id`;

-- 添加 conversation_id 字段
ALTER TABLE `source_chunk` 
ADD COLUMN `conversation_id` CHAR(36) NULL COMMENT '会话ID（外键）' AFTER `article_id`;

-- ----------------------------------------------------------------
-- 2. 数据迁移：从 source_id 填充到外键字段
-- ----------------------------------------------------------------

-- 填充 article_id
UPDATE `source_chunk` 
SET article_id = source_id 
WHERE source_type = 'ARTICLE' AND article_id IS NULL;

-- 填充 conversation_id
UPDATE `source_chunk` 
SET conversation_id = source_id 
WHERE source_type = 'CHAT' AND conversation_id IS NULL;

-- ----------------------------------------------------------------
-- 3. 确保 source_config_id 完整性
-- ----------------------------------------------------------------

-- 如果有 NULL 值，需要先处理（根据实际情况）
-- 选项1：删除无效数据
-- DELETE FROM `source_chunk` WHERE source_config_id IS NULL;

-- 选项2：填充默认值（需要一个有效的 source_config_id）
-- UPDATE `source_chunk` SET source_config_id = '默认ID' WHERE source_config_id IS NULL;

-- 修改为必填
ALTER TABLE `source_chunk` 
MODIFY COLUMN `source_config_id` CHAR(36) NOT NULL COMMENT '信息源配置ID';

-- ----------------------------------------------------------------
-- 4. 添加外键约束（级联删除）
-- ----------------------------------------------------------------

-- source_config 外键
ALTER TABLE `source_chunk`
ADD CONSTRAINT `fk_source_chunk_source_config`
FOREIGN KEY (`source_config_id`) REFERENCES `source_config`(`id`)
ON DELETE CASCADE ON UPDATE CASCADE;

-- article 外键
ALTER TABLE `source_chunk`
ADD CONSTRAINT `fk_source_chunk_article`
FOREIGN KEY (`article_id`) REFERENCES `article`(`id`)
ON DELETE CASCADE ON UPDATE CASCADE;

-- conversation 外键  
ALTER TABLE `source_chunk`
ADD CONSTRAINT `fk_source_chunk_conversation`
FOREIGN KEY (`conversation_id`) REFERENCES `chat_conversation`(`id`)
ON DELETE CASCADE ON UPDATE CASCADE;

-- ----------------------------------------------------------------
-- 5. 添加索引（优化查询性能）
-- ----------------------------------------------------------------

CREATE INDEX `idx_source_config_id` ON `source_chunk` (`source_config_id`);
CREATE INDEX `idx_article_id` ON `source_chunk` (`article_id`);
CREATE INDEX `idx_conversation_id` ON `source_chunk` (`conversation_id`);

-- ================================================================
-- 迁移后验证
-- ================================================================

-- 1. 查看更新后的表结构
DESCRIBE `source_chunk`;

-- 2. 验证外键字段
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN article_id IS NOT NULL THEN 1 ELSE 0 END) as has_article,
    SUM(CASE WHEN conversation_id IS NOT NULL THEN 1 ELSE 0 END) as has_conversation,
    SUM(CASE WHEN article_id IS NOT NULL AND conversation_id IS NOT NULL THEN 1 ELSE 0 END) as both_set
FROM `source_chunk`;
-- 预期：both_set = 0（不应该同时有值）

-- 3. 验证外键约束
SELECT 
    CONSTRAINT_NAME, 
    TABLE_NAME, 
    COLUMN_NAME, 
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'zleap_test' 
  AND TABLE_NAME = 'source_chunk'
  AND REFERENCED_TABLE_NAME IS NOT NULL;

-- 4. 测试级联删除（可选，谨慎）
-- 创建测试数据验证级联是否正常工作

-- ================================================================
-- 回滚脚本（如果需要）
-- ================================================================
/*
-- 删除外键
ALTER TABLE `source_chunk` DROP FOREIGN KEY `fk_source_chunk_conversation`;
ALTER TABLE `source_chunk` DROP FOREIGN KEY `fk_source_chunk_article`;
ALTER TABLE `source_chunk` DROP FOREIGN KEY `fk_source_chunk_source_config`;

-- 删除索引
DROP INDEX `idx_conversation_id` ON `source_chunk`;
DROP INDEX `idx_article_id` ON `source_chunk`;
DROP INDEX `idx_source_config_id` ON `source_chunk`;

-- source_config_id 改回可选
ALTER TABLE `source_chunk` 
MODIFY COLUMN `source_config_id` CHAR(36) NULL;

-- 删除字段
ALTER TABLE `source_chunk` DROP COLUMN `conversation_id`;
ALTER TABLE `source_chunk` DROP COLUMN `article_id`;
*/

-- ================================================================
-- 执行记录
-- ================================================================
-- 执行时间：__________________
-- 执行人：____________________
-- 影响行数：__________________
-- 验证结果：✅ 成功 / ❌ 失败
-- 备注：______________________
-- ================================================================

