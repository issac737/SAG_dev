-- ================================================================
-- 主系统数据库迁移脚本：source_event 表
-- ================================================================
-- 目的：添加 MVP 新架构字段，支持统一的事项管理
-- 执行数据库：zleap_test (主系统)
-- 创建时间：2025-11-13
-- 相关功能：DataFlow 事项提取和管理
-- ================================================================

USE zleap_test;

-- ================================================================
-- 迁移前检查
-- ================================================================

-- 1. 查看当前表结构
SHOW CREATE TABLE `source_event`\G

-- 2. 统计当前数据
SELECT 
    COUNT(*) as total_events,
    COUNT(DISTINCT article_id) as articles_with_events,
    COUNT(DISTINCT conversation_id) as conversations_with_events,
    MIN(created_time) as earliest_event,
    MAX(created_time) as latest_event
FROM `source_event`;

-- 3. 检查是否有无效数据（article_id 和 conversation_id 都为空）
SELECT COUNT(*) as invalid_count
FROM `source_event` 
WHERE article_id IS NULL AND conversation_id IS NULL;
-- 预期：0（如果>0，需要先清理）

-- ================================================================
-- 开始迁移
-- ================================================================

-- ----------------------------------------------------------------
-- 1. 添加 rank 字段（事项排序序号）
-- ----------------------------------------------------------------
-- 说明：用于控制事项在列表中的显示顺序，与 sort 字段功能类似但更语义化
-- 位置：在 category 字段之后
-- ----------------------------------------------------------------
ALTER TABLE `source_event` 
ADD COLUMN `rank` INT NOT NULL DEFAULT 0 COMMENT '事项排序序号' AFTER `category`;

-- 添加索引（优化排序查询）
CREATE INDEX `idx_rank` ON `source_event` (`rank`);

-- 可选：从现有 sort 字段迁移数据（如果需要保持顺序）
-- UPDATE `source_event` SET `rank` = `sort` WHERE `sort` IS NOT NULL;

-- ----------------------------------------------------------------
-- 2. 添加 chunk_id 字段（来源片段ID）
-- ----------------------------------------------------------------
-- 说明：关联到 source_chunk 表，标识事项来源的具体片段
-- 位置：在 references 字段之后
-- ----------------------------------------------------------------
ALTER TABLE `source_event` 
ADD COLUMN `chunk_id` CHAR(36) NULL COMMENT '来源片段ID（关联 source_chunk 表）' AFTER `references`;

-- 添加索引（优化根据chunk查询事项）
CREATE INDEX `idx_chunk_id` ON `source_event` (`chunk_id`);

-- ----------------------------------------------------------------
-- 3. 添加层级结构字段（支持父子关系）
-- ----------------------------------------------------------------
-- 说明：支持事项的层级嵌套，实现父子关联
-- 场景：大事项拆分为子任务、项目结构化管理
-- ----------------------------------------------------------------

-- 添加 level 字段（层级深度）
ALTER TABLE `source_event` 
ADD COLUMN `level` INT NOT NULL DEFAULT 0 COMMENT '层级深度（0=顶层，1=一级子项，以此类推）' AFTER `rank`;

-- 添加 parent_id 字段（父事项ID，自引用）
ALTER TABLE `source_event` 
ADD COLUMN `parent_id` CHAR(36) NULL COMMENT '父事项ID（自引用，顶层事项为NULL）' AFTER `level`;

-- 添加外键约束（自引用）
ALTER TABLE `source_event`
ADD CONSTRAINT `fk_source_event_parent`
FOREIGN KEY (`parent_id`) REFERENCES `source_event`(`id`)
ON DELETE CASCADE ON UPDATE CASCADE;

-- 添加索引（优化层级查询）
CREATE INDEX `idx_parent_id` ON `source_event` (`parent_id`);
CREATE INDEX `idx_level` ON `source_event` (`level`);
CREATE INDEX `idx_parent_level` ON `source_event` (`parent_id`, `level`);

-- ----------------------------------------------------------------
-- 4. 添加多态来源字段（统一接口）
-- ----------------------------------------------------------------
-- 说明：添加 source_type 和 source_id 字段，统一 chunk 和 event 的接口
-- 目的：与 SourceChunk 表保持一致，方便统一查询和处理
-- ----------------------------------------------------------------

-- 添加 source_type 字段
ALTER TABLE `source_event` 
ADD COLUMN `source_type` VARCHAR(20) NOT NULL DEFAULT 'ARTICLE' COMMENT '来源类型：ARTICLE/CHAT' AFTER `source_config_id`;

-- 添加 source_id 字段
ALTER TABLE `source_event` 
ADD COLUMN `source_id` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '来源ID（article_id或conversation_id）' AFTER `source_type`;

-- 数据迁移：从 article_id/conversation_id 填充到 source_type/source_id
UPDATE `source_event` 
SET source_type = 'ARTICLE', source_id = article_id 
WHERE article_id IS NOT NULL;

UPDATE `source_event` 
SET source_type = 'CHAT', source_id = conversation_id 
WHERE conversation_id IS NOT NULL;

-- 添加索引（优化多态查询）
CREATE INDEX `idx_source` ON `source_event` (`source_type`, `source_id`);
CREATE INDEX `idx_source_rank` ON `source_event` (`source_type`, `source_id`, `rank`);

-- ----------------------------------------------------------------
-- 5. 数据完整性说明
-- ----------------------------------------------------------------
-- 注意：MySQL 8.0.23+ 不允许在有外键动作的列上使用 CHECK 约束
-- article_id 和 conversation_id 都有外键的 ON DELETE/ON UPDATE 动作
-- 因此不能添加 CHECK 约束
-- 
-- 数据完整性保证：
-- - 应用层：创建事项时必须设置 article_id 或 conversation_id
-- - 可选：使用 TRIGGER 实现验证（如果必要）
-- ----------------------------------------------------------------

-- ================================================================
-- 迁移后验证
-- ================================================================

-- 1. 查看更新后的表结构
DESCRIBE `source_event`;

-- 2. 验证新字段
SELECT 
    COUNT(*) as total,
    COUNT(`rank`) as has_rank,
    COUNT(`chunk_id`) as has_chunk_id,
    AVG(`rank`) as avg_rank
FROM `source_event`;

-- 3. 检查约束是否生效
SELECT 
    COUNT(*) as total_events,
    SUM(CASE WHEN article_id IS NOT NULL THEN 1 ELSE 0 END) as article_events,
    SUM(CASE WHEN conversation_id IS NOT NULL THEN 1 ELSE 0 END) as conversation_events,
    SUM(CASE WHEN article_id IS NULL AND conversation_id IS NULL THEN 1 ELSE 0 END) as invalid_events
FROM `source_event`;
-- 预期：invalid_events = 0

-- 4. 性能测试（可选）
-- 测试新索引的效果
EXPLAIN SELECT * FROM `source_event` WHERE `rank` > 0 ORDER BY `rank`;
EXPLAIN SELECT * FROM `source_event` WHERE `chunk_id` = 'some-uuid';

-- ================================================================
-- 回滚脚本（如果需要）
-- ================================================================
/*
-- 删除层级结构
DROP INDEX `idx_parent_level` ON `source_event`;
DROP INDEX `idx_level` ON `source_event`;
DROP INDEX `idx_parent_id` ON `source_event`;
ALTER TABLE `source_event` DROP FOREIGN KEY `fk_source_event_parent`;
ALTER TABLE `source_event` DROP COLUMN `parent_id`;
ALTER TABLE `source_event` DROP COLUMN `level`;

-- 删除其他新增字段
DROP INDEX `idx_chunk_id` ON `source_event`;
DROP INDEX `idx_rank` ON `source_event`;
ALTER TABLE `source_event` DROP COLUMN `chunk_id`;
ALTER TABLE `source_event` DROP COLUMN `rank`;
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

