"""
事项处理器

负责从文章片段中提取事项和实体的核心逻辑
"""

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import or_, select

from sqlalchemy.orm import selectinload

from dataflow.core.ai.base import BaseLLMClient
from dataflow.core.ai.models import LLMMessage, LLMRole
from dataflow.core.prompt.manager import PromptManager
from dataflow.core.storage.elasticsearch import get_es_client
from dataflow.core.storage.repositories.event_repository import EventVectorRepository
from dataflow.db import get_session_factory
from dataflow.db.models import (
    SourceChunk,
    Entity,
    EntityType as DBEntityType,
    EventEntity,
    SourceEvent,
)
from dataflow.exceptions import ExtractError
from dataflow.modules.extract.config import ExtractConfig
from dataflow.modules.extract.parser import EntityValueParser
from dataflow.utils import get_logger

logger = get_logger("extract.processor")


class EventProcessor:
    """事项处理器（核心提取逻辑）"""

    def __init__(
        self,
        llm_client: BaseLLMClient,
        prompt_manager: PromptManager,
        config: ExtractConfig,
    ):
        """
        初始化事项处理器

        Args:
            llm_client: LLM客户端
            prompt_manager: 提示词管理器
            config: 提取配置
        """
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager
        self.config = config
        self.session_factory = get_session_factory()
        
        # 历史事项召回相关（延迟初始化）
        self._es_client = None
        self._event_repo = None
        self._embedding_client = None
        self.entity_types: List[DBEntityType] = []
        self.logger = get_logger("extract.processor")
        self.parser = EntityValueParser()

    async def extract(
        self,
        items: List,
        metadata: Dict,
        source_type: str,
    ) -> List[SourceEvent]:
        """
        从内容列表提取事项（chunk级提取入口）
        
        Args:
            items: ArticleSection 或 ChatMessage 列表
            metadata: {document_title, chunk_title, previous_context}
            source_type: "ARTICLE" 或 "CHAT"
        
        Returns:
            SourceEvent 列表
        """
        import json
        
        if not items:
            self.logger.warning("items 为空，跳过提取")
            return []
        
        try:
            is_article = source_type == "ARTICLE"
            
            # 1. 构建 SYSTEM 提示词（包含背景、实体类型、候选关键词、输出schema）
            system_prompt = await self._build_system_prompt(items, metadata, is_article)
            self.logger.debug(f"SYSTEM: {system_prompt[:500]}...")
            
            # 2. 构建 USER 输入（纯数据）
            user_input = self._build_user_input(items, is_article)
            self.logger.debug(f"USER: {json.dumps(user_input, ensure_ascii=False)[:300]}...")
            
            # 3. 构建消息列表
            messages = [
                LLMMessage(role=LLMRole.SYSTEM, content=system_prompt),
                LLMMessage(role=LLMRole.USER, content=json.dumps(user_input, ensure_ascii=False))
            ]
            self.logger.info(f"开始提取: items={len(items)}, type={source_type}")
            
            # 4. 调用 LLM（传入 schema 用于校验）
            schema = self._build_extraction_schema()
            result = await self.llm_client.chat_with_schema(
                messages,
                response_schema=schema,
                temperature=0.3
            )
            
            # 5. 解析结果
            events = self._parse_result(result, items, source_type)
            
            self.logger.info(f"提取完成: {len(events)} 个事项")
            return events
            
        except Exception as e:
            self.logger.error(f"提取失败: {e}", exc_info=True)
            raise ExtractError(f"提取失败: {e}") from e
    
    def _parse_result(self, result: Dict, items: List, source_type: str) -> List[SourceEvent]:
        """解析结果为 SourceEvent"""
        from datetime import datetime
        
        events = []
        id_map = {item.id: item for item in items}
        
        # 获取 source_id（从第一个 item 获取）
        first_item = items[0] if items else None
        source_id = None
        article_id = None
        conversation_id = None
        
        if first_item:
            if source_type == "ARTICLE":
                # ArticleSection 有 article_id 属性
                article_id = getattr(first_item, "article_id", None)
                source_id = article_id
            elif source_type == "CHAT":
                # ChatMessage 有 conversation_id 属性
                conversation_id = getattr(first_item, "conversation_id", None)
                source_id = conversation_id
        
        for event_data in result.get("items", []):
            references = event_data.get("references", [])
            valid_refs = [ref for ref in references if ref in id_map]
            
            if not valid_refs and references:
                self.logger.warning(f"事项引用无效: {references}")
                continue
            
            # 转换实体格式：从列表 -> 字典
            # LLM返回: [{"type": "person", "name": "张三", "description": "CEO"}, ...]
            # 期望格式: {"person": [{"name": "张三", "description": "CEO"}], ...}
            raw_entities_list = event_data.get("entities", [])
            raw_entities_dict = {}
            if isinstance(raw_entities_list, list):
                for entity in raw_entities_list:
                    if isinstance(entity, dict):
                        entity_type = entity.get("type", "")
                        if entity_type:
                            if entity_type not in raw_entities_dict:
                                raw_entities_dict[entity_type] = []
                            raw_entities_dict[entity_type].append({
                                "name": entity.get("name", ""),
                                "description": entity.get("description", "")
                            })
            elif isinstance(raw_entities_list, dict):
                # 已经是字典格式，直接使用
                raw_entities_dict = raw_entities_list
            
            # 根据来源类型设置时间
            start_time = None
            end_time = None
            
            if source_type == "ARTICLE":
                # 文档类型：使用当前时间
                current_time = datetime.now()
                start_time = current_time
                end_time = current_time
            elif source_type == "CHAT":
                # 会话类型：从引用的消息中获取时间范围
                ref_items = [id_map[ref] for ref in valid_refs if ref in id_map]
                if ref_items:
                    timestamps = [getattr(item, 'timestamp', None) for item in ref_items]
                    timestamps = [t for t in timestamps if t is not None]
                    if timestamps:
                        start_time = min(timestamps)
                        end_time = max(timestamps)
            
            event = SourceEvent(
                id=str(uuid.uuid4()),
                source_config_id=self.config.source_config_id,
                source_type=source_type,
                source_id=source_id or "",
                article_id=article_id,
                conversation_id=conversation_id,
                title=event_data.get("title", ""),
                summary=event_data.get("summary", ""),
                content=event_data.get("content", ""),
                category=event_data.get("category", ""),
                type=source_type,  # 业务字段，与 source_type 保持一致
                references=valid_refs or references,  # 直接设置到 references 字段
                start_time=start_time,
                end_time=end_time,
                extra_data={
                    "raw_entities": raw_entities_dict,
                    "is_valid": event_data.get("is_valid", True)
                }
            )
            events.append(event)
        
        return events

    async def extract_from_sections(
        self, sections: List[SourceChunk], batch_index: int
    ) -> List[SourceEvent]:
        """
        从来源片段提取事项（核心方法）

        这是最底层的提取逻辑，单次LLM调用

        Args:
            sections: 来源片段列表
            batch_index: 批次索引（用于日志）

        Returns:
            提取的事项列表

        Raises:
            ExtractError: 提取失败
        """
        import json
        
        # 输入验证
        if not sections:
            self.logger.warning(f"批次 {batch_index}: sections 列表为空，跳过提取")
            return []

        try:
            # 1. 构建 SYSTEM 提示词
            metadata = {"document_title": "", "chunk_title": f"批次{batch_index}", "previous_context": ""}
            system_prompt = await self._build_system_prompt(sections, metadata, is_article=True)

            # 2. 构建 USER 输入
            user_input = self._build_user_input(sections, is_article=True)

            # 3. 构建消息列表
            messages = [
                LLMMessage(role=LLMRole.SYSTEM, content=system_prompt),
                LLMMessage(role=LLMRole.USER, content=json.dumps(user_input, ensure_ascii=False))
            ]

            # 4. 构建JSON Schema
            schema = self._build_extraction_schema()

            # 5. 调用LLM
            result = await self.llm_client.chat_with_schema(
                messages, response_schema=schema, temperature=0.3
            )

            # 6. 解析结果 -> SourceEvent 对象（不含实体，统一由 process_entity_associations 处理）
            events = await self._parse_extraction_result_without_entities(result, sections)

            self.logger.info(
                f"批次 {batch_index}: 提取了 {len(events)} 个事项（不含实体）",
                extra={"batch_index": batch_index, "event_count": len(events)},
            )

            return events

        except Exception as e:
            self.logger.error(f"批次 {batch_index} 提取失败: {e}", exc_info=True)
            raise ExtractError(f"批次 {batch_index} 提取失败: {e}") from e

    async def extract_events_without_entities(
        self, sections: List[SourceChunk], batch_index: int
    ) -> List[SourceEvent]:
        """
        阶段1：提取事项（不含实体关联）

        Args:
            sections: 来源片段列表
            batch_index: 批次索引

        Returns:
            不含实体关联的事项列表
        """
        import json
        
        try:
            # 1. 构建 SYSTEM 提示词
            metadata = {"document_title": "", "chunk_title": f"批次{batch_index}", "previous_context": ""}
            system_prompt = await self._build_system_prompt(sections, metadata, is_article=True)

            # 2. 构建 USER 输入
            user_input = self._build_user_input(sections, is_article=True)

            # 3. 构建消息列表
            messages = [
                LLMMessage(role=LLMRole.SYSTEM, content=system_prompt),
                LLMMessage(role=LLMRole.USER, content=json.dumps(user_input, ensure_ascii=False))
            ]

            # 4. 构建JSON Schema
            schema = self._build_extraction_schema()

            self.logger.info(
                f"📦 批次 {batch_index}: 开始提取事项 - 片段数={len(sections)}, "
                f"LLM模型={self.llm_client.client.config.model}"
            )

            # 5. 调用LLM
            result = await self.llm_client.chat_with_schema(
                messages, response_schema=schema, temperature=0.3
            )

            # 6. 解析结果（不处理实体关联）
            events = await self._parse_extraction_result_without_entities(result, sections)

            self.logger.info(
                f"批次 {batch_index}: 提取了 {len(events)} 个事项（不含实体）",
                extra={"batch_index": batch_index, "event_count": len(events)},
            )

            return events

        except Exception as e:
            self.logger.error(
                f"❌ 批次 {batch_index} 提取失败 - 模型: {self.llm_client.client.config.model}, "
                f"片段数: {len(sections)}, 错误: {e}",
                exc_info=True
            )
            raise ExtractError(f"批次 {batch_index} 提取失败: {e}") from e

    async def process_entity_associations(
        self, events: List[SourceEvent], session=None  # noqa: ARG002
    ) -> List[SourceEvent]:
        """
        阶段2：统一处理所有事项的实体关联（两阶段处理优化版）
        
        优化策略：
        1. 批量查询已存在的实体（减少 SELECT 次数）
        2. 逐个创建新实体（独立事务，冲突隔离）
        3. 建立关联
        
        注意：session 参数保留是为了向后兼容，但当前实现使用独立事务创建实体

        Args:
            events: 所有事项列表（不含实体关联）
            session: 数据库 session（保留参数，当前未使用）

        Returns:
            包含实体关联的事项列表
        """
        try:
            self.logger.info(f"开始统一处理 {len(events)} 个事项的实体关联")

            # ========== 阶段1：收集所有需要的实体 ==========
            # 自动注入时间实体（基于 start_time/end_time 字段）
            for event in events:
                self._inject_time_entities_for_event(event)

            # 收集所有实体数据：{entity_type: {name: description}}
            all_entities_data = {}

            # 1️⃣ 收集 LLM 提取的实体
            for event in events:
                entities_data = event.extra_data.get("raw_entities", {})
                for entity_type, entity_names in entities_data.items():
                    if entity_type not in all_entities_data:
                        all_entities_data[entity_type] = {}

                    for entity_data in entity_names:
                        if isinstance(entity_data, dict):
                            name = entity_data.get("name")
                            description = entity_data.get("description", "")
                        else:
                            name = entity_data
                            description = ""

                        if name:
                            if name not in all_entities_data[entity_type]:
                                all_entities_data[entity_type][name] = description
                            elif description and not all_entities_data[entity_type][name]:
                                all_entities_data[entity_type][name] = description

            # 2️⃣ 添加配置的默认值实体到收集池
            for entity_type_config in self.entity_types:
                constraints = entity_type_config.value_constraints or {}
                default_value = constraints.get('default')
                if default_value:
                    entity_type = entity_type_config.type
                    if entity_type not in all_entities_data:
                        all_entities_data[entity_type] = {}
                    if default_value not in all_entities_data[entity_type]:
                        all_entities_data[entity_type][default_value] = "系统默认值"
                        self.logger.debug(f"📌 添加默认值实体: {entity_type}={default_value}")

            # ========== 阶段2：批量查询已存在的实体 ==========
            entity_id_map = await self._batch_query_existing_entities(all_entities_data)

            # ========== 阶段3：逐个创建新实体（独立事务） ==========
            entities_to_create = []
            for entity_type, entities_dict in all_entities_data.items():
                entity_type_obj = self._get_entity_type_by_type(entity_type)
                if not entity_type_obj:
                    continue
                
                for name, description in entities_dict.items():
                    normalized_name = self._normalize_entity_name(name)
                    key = (entity_type, normalized_name)
                    
                    if key not in entity_id_map:
                        entities_to_create.append((entity_type, name, description, entity_type_obj))

            if entities_to_create:
                self.logger.info(f"需要创建 {len(entities_to_create)} 个新实体")
                
                for entity_type, name, description, entity_type_obj in entities_to_create:
                    try:
                        entity_id = await self._create_entity_with_retry(
                            entity_type, name, entity_type_obj
                        )
                        normalized_name = self._normalize_entity_name(name)
                        entity_id_map[(entity_type, normalized_name)] = (entity_id, description)
                    except Exception as e:
                        self.logger.error(f"❌ 创建实体失败: {name}, error={e}")
                        # 继续处理其他实体，不中断

            # ========== 阶段4：建立实体关联 ==========
            # 预先收集所有强制模式的默认值
            forced_defaults = {}
            for entity_type_config in self.entity_types:
                constraints = entity_type_config.value_constraints or {}
                default_value = constraints.get('default')
                override_mode = constraints.get('override', False)
                if default_value and override_mode:
                    forced_defaults[entity_type_config.type] = default_value

            # 为所有事项建立实体关联
            for event in events:
                entities_data = event.extra_data.get("raw_entities", {})
                event_associations = []
                entity_map = {}  # 用于去重和合并描述

                # 建立 LLM 提取的实体关联
                for entity_type, entity_names in entities_data.items():
                    entity_type_obj = self._get_entity_type_by_type(entity_type)
                    if not entity_type_obj:
                        continue

                    for entity_data in entity_names:
                        if isinstance(entity_data, dict):
                            name = entity_data.get("name")
                            description = entity_data.get("description", "")
                        else:
                            name = entity_data
                            description = ""

                        if not name:
                            continue

                        normalized_name = self._normalize_entity_name(name)
                        key = (entity_type, normalized_name)
                        
                        if key in entity_id_map:
                            entity_id, cached_description = entity_id_map[key]
                            
                            if entity_id not in entity_map:
                                entity_map[entity_id] = {
                                    "name": name,
                                    "type": entity_type,
                                    "descriptions": [],
                                    "weight": float(entity_type_obj.weight),
                                    "is_forced_default": False
                                }
                            
                            if description and description not in entity_map[entity_id]["descriptions"]:
                                entity_map[entity_id]["descriptions"].append(description)
                            if cached_description and cached_description not in entity_map[entity_id]["descriptions"]:
                                entity_map[entity_id]["descriptions"].append(cached_description)
                            
                            if entity_type in forced_defaults and name == forced_defaults[entity_type]:
                                entity_map[entity_id]["is_forced_default"] = True

                # 应用默认值实体关联逻辑
                extracted_by_type = {}
                for entity_type, entity_names in entities_data.items():
                    names = [e.get('name') if isinstance(e, dict) else e for e in entity_names]
                    extracted_by_type[entity_type] = [n for n in names if n]

                for entity_type_config in self.entity_types:
                    constraints = entity_type_config.value_constraints or {}
                    default_value = constraints.get('default')
                    override_mode = constraints.get('override', False)

                    if not default_value:
                        continue

                    entity_type = entity_type_config.type
                    entity_names_of_type = extracted_by_type.get(entity_type, [])
                    has_default = default_value in entity_names_of_type

                    should_add_default = (
                        (override_mode and not has_default) or
                        (not override_mode and len(entity_names_of_type) == 0)
                    )

                    if should_add_default:
                        normalized_name = self._normalize_entity_name(default_value)
                        key = (entity_type, normalized_name)
                        if key in entity_id_map:
                            entity_id, _ = entity_id_map[key]
                            
                            if entity_id not in entity_map:
                                mode_desc = "强制追加" if override_mode else "自动补充"
                                entity_map[entity_id] = {
                                    "name": default_value,
                                    "type": entity_type,
                                    "descriptions": [f"系统默认值（{mode_desc}）"],
                                    "weight": float(entity_type_config.weight),
                                    "is_forced_default": False,
                                    "is_default": True,
                                    "mode": mode_desc
                                }

                # 为每个唯一的 entity_id 创建关联
                for entity_id, info in entity_map.items():
                    if info.get("is_forced_default"):
                        final_description = "系统默认值（强制写入）"
                    elif info.get("is_default"):
                        final_description = info["descriptions"][0] if info["descriptions"] else None
                    elif info["descriptions"]:
                        final_description = "、".join(info["descriptions"])
                    else:
                        final_description = None
                    
                    extra_data = {"confidence": event.extra_data.get("quality_score", 0.8)}
                    if info.get("is_forced_default"):
                        extra_data["is_forced_default"] = True
                    if info.get("is_default"):
                        extra_data["is_default"] = True
                        extra_data["mode"] = info.get("mode")
                    if len(info["descriptions"]) > 1:
                        extra_data["description_count"] = len(info["descriptions"])
                    
                    assoc = EventEntity(
                        id=str(uuid.uuid4()),
                        event_id=event.id,
                        entity_id=entity_id,
                        weight=info["weight"],
                        description=final_description,
                        extra_data=extra_data,
                    )
                    event_associations.append(assoc)

                event.event_associations = event_associations

                # 清理临时数据
                if "raw_entities" in event.extra_data:
                    del event.extra_data["raw_entities"]

            self.logger.info(f"✅ 完成 {len(events)} 个事项的实体关联处理")
            return events

        except Exception as e:
            self.logger.error(f"实体关联处理失败: {e}", exc_info=True)
            raise ExtractError(f"实体关联处理失败: {e}") from e

    async def _parse_extraction_result_without_entities(
        self, result: Dict[str, Any], sections: List[SourceChunk]
    ) -> List[SourceEvent]:
        """
        解析LLM提取结果为SourceEvent对象（不处理实体关联）

        Args:
            result: LLM返回的JSON结果
            sections: 原始片段列表（用于生成引用）

        Returns:
            不含实体关联的SourceEvent对象列表
        """
        events = []
        for event_data in result.get("items", []):
            # 解析 LLM 标注的引用（片段编号，从1开始）
            referenced_indices = event_data.get("references", [])
            # 将片段编号转换为实际的 section_id
            referenced_section_ids = []
            invalid_indices = []
            for idx in referenced_indices:
                if isinstance(idx, int) and 1 <= idx <= len(sections):  # 验证索引有效性
                    section = sections[idx - 1]  # 编号从1开始，索引从0开始
                    referenced_section_ids.append(section.id)
                else:
                    # 记录无效索引
                    invalid_indices.append(idx)

            # 记录警告（如果有无效索引）
            if invalid_indices:
                self.logger.warning(
                    f"事项 '{event_data.get('title', '未知')}' 包含无效的片段引用索引: {invalid_indices}",
                    extra={
                        "event_title": event_data.get("title"),
                        "invalid_indices": invalid_indices,
                        "total_sections": len(sections),
                    },
                )

            # 🆕 ==================== 实体转换、去重与合并逻辑（源头处理）====================
            # 1. 将 LLM 返回的数组格式转换为按 type 分组的字典格式
            entities_from_llm = event_data.get("entities", [])
            entities_raw = {}

            # 如果 LLM 返回的是数组（schema 定义的格式）
            if isinstance(entities_from_llm, list):
                for entity_item in entities_from_llm:
                    if not isinstance(entity_item, dict):
                        continue
                    
                    entity_type = entity_item.get("type")
                    if not entity_type:
                        continue
                    
                    # 按类型分组
                    if entity_type not in entities_raw:
                        entities_raw[entity_type] = []
                    
                    entities_raw[entity_type].append({
                        "name": entity_item.get("name", ""),
                        "description": entity_item.get("description", "")  # 保留 description
                    })
            # 兼容旧的字典格式（如果存在）
            elif isinstance(entities_from_llm, dict):
                entities_raw = entities_from_llm

            # 2. 对每个类型内的实体去重，并智能合并 description
            entities_deduped = {}

            for entity_type, entity_list in entities_raw.items():
                if not entity_list:
                    entities_deduped[entity_type] = []
                    continue
                
                # 使用字典收集：key=normalized_name, value={"name": str, "descriptions": [str]}
                merged_entities = {}
                
                for entity_data in entity_list:
                    # 兼容格式：字典或字符串
                    if isinstance(entity_data, dict):
                        name = entity_data.get("name", "").strip()
                        description = entity_data.get("description", "").strip()
                    else:
                        name = str(entity_data).strip()
                        description = ""
                    
                    if not name:
                        continue
                    
                    # 规范化名称用于去重
                    normalized_name = name.lower().strip()
                    
                    # 第一次遇到这个实体
                    if normalized_name not in merged_entities:
                        merged_entities[normalized_name] = {
                            "name": name,  # 保留原始名称（第一次出现的）
                            "descriptions": []
                        }
                    
                    # 收集描述（去重、去空）
                    if description:
                        existing_descs = merged_entities[normalized_name]["descriptions"]
                        if description not in existing_descs:
                            existing_descs.append(description)
                
                # 转换回列表格式，合并描述
                deduped_list = []
                for entity_info in merged_entities.values():
                    # 用中文顿号连接多个描述
                    final_desc = "、".join(entity_info["descriptions"]) if entity_info["descriptions"] else ""
                    
                    deduped_list.append({
                        "name": entity_info["name"],
                        "description": final_desc  # 合并后的描述
                    })
                    
                    if len(entity_info["descriptions"]) > 1:
                        self.logger.debug(
                            f"✅ 合并重复实体描述 [{entity_type}] {entity_info['name']}: "
                            f"{len(entity_info['descriptions'])}个 -> {final_desc}"
                        )
                
                entities_deduped[entity_type] = deduped_list
            # =================================================================

            # 确定主要引用的 chunk（取第一个被引用的 chunk）
            primary_chunk = None
            if referenced_section_ids:
                # 查找第一个被引用的 section 对应的 chunk
                for section in sections:
                    if section.id == referenced_section_ids[0]:
                        primary_chunk = section
                        break
                if not primary_chunk:
                    primary_chunk = sections[0]  # 如果没找到，默认使用第一个 chunk
            else:
                primary_chunk = sections[0] if sections else None

            # 🆕 根据来源类型设置时间
            # 注意：在 processor 中，事项的 references 直接继承自 primary_chunk.references
            # 所以用 primary_chunk.references 来查询时间是正确的
            from datetime import datetime
            from dataflow.db import ChatMessage
            from sqlalchemy import select
            
            start_time = None
            end_time = None
            event_references = primary_chunk.references if primary_chunk else None
            
            if primary_chunk:
                if primary_chunk.source_type == "ARTICLE":
                    # 文档类型：使用当前时间
                    current_time = datetime.now()
                    start_time = current_time
                    end_time = current_time
                    
                elif primary_chunk.source_type == "CHAT":
                    # 会话类型：从引用的消息中获取时间范围
                    # 使用 primary_chunk.references（因为事项会继承这个）
                    if event_references and isinstance(event_references, list):
                        async with self.session_factory() as session:
                            result_msgs = await session.execute(
                                select(ChatMessage)
                                .where(ChatMessage.id.in_(event_references))
                                .order_by(ChatMessage.timestamp)
                            )
                            messages = list(result_msgs.scalars().all())
                            
                            if messages:
                                start_time = messages[0].timestamp  # 最早时间
                                end_time = messages[-1].timestamp  # 最晚时间
                                self.logger.debug(
                                    f"会话事项时间: {start_time} ~ {end_time} "
                                    f"(共{len(messages)}条消息)"
                                )

            # 创建事项对象
            source_type_value = primary_chunk.source_type if primary_chunk else "ARTICLE"
            event = SourceEvent(
                id=str(uuid.uuid4()),
                source_config_id=self.config.source_config_id,
                source_type=source_type_value,
                source_id=primary_chunk.source_id if primary_chunk else sections[0].source_id,
                article_id=sections[0].article_id if primary_chunk and primary_chunk.source_type == "ARTICLE" else None,
                conversation_id=primary_chunk.conversation_id if primary_chunk and primary_chunk.source_type == "CHAT" else None,
                title=event_data["title"],
                summary=event_data.get("summary") or "",
                content=event_data["content"],
                category=event_data.get("category") or "",  # 独立字段，确保None转为空字符串
                # 业务字段（兼容主系统）- type与source_type保持一致
                type=source_type_value,
                priority="UNKNOWN",  # 默认值
                status="UNKNOWN",  # 默认值
                rank=None,  # 由上层 EventExtractor 统一分配全局 rank
                start_time=start_time,
                end_time=end_time,
                references=referenced_section_ids,  # ✅ 修复：使用LLM精确标注的引用
                chunk_id=primary_chunk.id if primary_chunk else None,
                extra_data={
                    "quality_score": event_data.get("quality_score", 0.8),
                    "batch_size": len(sections),
                    # 保存去重后的实体数据，用于第二阶段处理
                    "raw_entities": entities_deduped,
                },
            )

            events.append(event)

        return events

    async def initialize(self) -> None:
        """
        初始化处理器（加载实体类型配置）

        必须在使用处理器之前调用此方法
        """
        await self._load_entity_types()

    async def _load_entity_types(self) -> None:
        """
        从数据库加载实体类型配置

        加载规则（按优先级从高到低）：
        1. 文档级别（scope='article', article_id=当前文档）
        2. 信息源级别（scope='source', source_config_id=当前信息源）
        3. 全局自定义（scope='global', source_config_id IS NULL, is_default=FALSE）
        4. 系统默认（source_config_id IS NULL, is_default=TRUE）

        注意：同一个 type 只取优先级最高的配置
        """
        async with self.session_factory() as session:
            # 查询条件列表（按优先级排序）
            conditions = []

            # 1. 文档级别（优先级最高）
            if self.config.article_id:
                conditions.append(
                    (DBEntityType.scope == 'article')
                    & (DBEntityType.article_id == self.config.article_id)
                    & DBEntityType.is_active
                )

            # 2. 信息源级别
            if self.config.source_config_id:
                conditions.append(
                    (DBEntityType.scope == 'source')
                    & (DBEntityType.source_config_id == self.config.source_config_id)
                    & DBEntityType.is_active
                )

            # 3. 全局自定义类型
            conditions.append(
                (DBEntityType.scope == 'global')
                & DBEntityType.source_config_id.is_(None)
                & (DBEntityType.is_default == False)
                & DBEntityType.is_active
            )

            # 4. 系统默认类型
            conditions.append(
                DBEntityType.source_config_id.is_(None)
                & DBEntityType.is_default
                & DBEntityType.is_active
                    )

            # 查询所有匹配的实体类型
            result = await session.execute(
                select(DBEntityType)
                .where(or_(*conditions))
                .order_by(DBEntityType.weight.desc())
            )
            all_entity_types = list(result.scalars().all())

            # 去重：同一个 type 只保留优先级最高的
            # 优先级：文档 > 信息源 > 全局 > 默认
            type_priority_map = {}
            for et in all_entity_types:
                if et.type not in type_priority_map:
                    # 第一次出现该类型，记录下来
                    type_priority_map[et.type] = et
                else:
                    # 该类型已存在，比较优先级
                    existing = type_priority_map[et.type]

                    # 确定优先级得分（数值越小优先级越高）
                    def get_priority_score(entity_type):
                        if entity_type.scope == 'article' and entity_type.article_id == self.config.article_id:
                            return 1  # 文档级别
                        elif entity_type.scope == 'source' and entity_type.source_config_id == self.config.source_config_id:
                            return 2  # 信息源级别
                        elif entity_type.scope == 'global' and not entity_type.is_default:
                            return 3  # 全局自定义
                        elif entity_type.is_default:
                            return 4  # 系统默认
                        else:
                            return 5  # 其他（不应该出现）

                    if get_priority_score(et) < get_priority_score(existing):
                        type_priority_map[et.type] = et

            self.entity_types = list(type_priority_map.values())

        self.logger.info(
            f"加载了 {len(self.entity_types)} 个实体类型配置",
            extra={
                "article_id": self.config.article_id,
                "source_config_id": self.config.source_config_id,
                "entity_types": [et.type for et in self.entity_types],
            },
        )

        # 🔍 调试：输出每个实体类型的详细信息
        # for et in self.entity_types:
        #     scope_desc = f"{et.scope}"
        #     if et.scope == 'article':
        #         scope_desc += f"(article_id={et.article_id[:8]}...)"
        #     elif et.scope == 'source':
        #         scope_desc += f"(source_config_id={et.source_config_id[:8] if et.source_config_id else 'None'}...)"
        #     elif et.is_default:
        #         scope_desc += "(default)"

        #     self.logger.info(
        #         f"🔍 实体类型 [{et.type}]: "
        #         f"name={et.name}, scope={scope_desc}, "
        #         f"is_active={et.is_active}, is_default={et.is_default}, "
        #         f"value_constraints={et.value_constraints}"
        #     )

    async def _build_system_prompt(self, items: List, metadata: Dict, is_article: bool) -> str:
        """
        构建 SYSTEM 提示词（异步：支持历史事项召回）
        
        Args:
            items: 内容列表
            metadata: 元数据 {document_title, chunk_title, previous_context}
            is_article: 是否为文章类型
        
        Returns:
            SYSTEM 提示词
        """
        import json
        from dataflow.core.ai.tokensize import extract_keywords
        
        # 1. 提取原文内容
        raw_text = "\n".join([item.content for item in items if hasattr(item, 'content')])
        
        # 2. 召回相关历史事项（分类和实体命名参考）
        related_events = await self._recall_related_events(raw_text)
        
        # 3. 构建背景信息（包含历史事项参考）
        background = self._build_background(metadata, is_article, related_events)
        
        # 4. 获取实体类型说明
        entity_types = self._get_entity_types_description()
        
        # 5. 提取候选关键词（分词器预提取）
        keywords = extract_keywords(raw_text, top_k=50) if raw_text else []
        candidate_keywords = "、".join(keywords) if keywords else "（无）"
        
        # 6. 构建输出 schema 示例（单个事项的结构）
        output_schema = json.dumps({
            "title": "简洁标题",
            "summary": "一句话摘要",
            "content": "完整事件内容",
            "category": "分类标签",
            "references": ["item.id"],
            "entities": [{"type": "类型", "name": "名称", "description": "描述"}],
            "is_valid": True
        }, ensure_ascii=False, indent=2)
        
        # 7. 渲染模板
        return self.prompt_manager.render(
            "event_extraction",
            background=background,
            entity_types=entity_types,
            candidate_keywords=candidate_keywords,
            output_schema=output_schema
        )
    
    def _build_background(self, metadata: Dict, is_article: bool, related_events: List[Dict] = None) -> str:
        """
        构建背景信息
        
        Args:
            metadata: 元数据
            is_article: 是否为文章类型
            related_events: 相关历史事项列表
        
        Returns:
            背景信息文本
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        tz = ZoneInfo("Asia/Shanghai")
        parts = [f"时间: {datetime.now(tz).strftime('%Y-%m-%d %H:%M')}"]
        
        # 文档/会话标题
        if metadata.get("document_title"):
            label = "文档" if is_article else "会话"
            parts.append(f"{label}: {metadata['document_title']}")
        
        # 当前片段标题
        if metadata.get("chunk_title"):
            parts.append(f"当前片段: {metadata['chunk_title']}")
        
        # 前文参考
        if metadata.get("previous_context"):
            parts.append(f"\n前文参考:\n{metadata['previous_context']}")
        
        # 相关历史事项（仅供参考分类标签和实体命名风格）
        if related_events:
            parts.append("\n### 相关历史事项")
            parts.append("以下是同信息源的历史事项，供你参考：")
            parts.append("- 参考其「分类」标签的命名风格")
            parts.append("- 参考其「实体」的提取粒度和命名方式")
            
            for i, event in enumerate(related_events, 1):
                title = event.get('title', '')
                category = event.get('category', '')
                entities = event.get('entities', [])
                # 实体带上类型：name(type)
                entities_str = "、".join([f"{e['name']}({e['type']})" for e in entities[:5]])
                
                parts.append(f"事项{i}:")
                parts.append(f"  标题: {title}")
                if category:
                    parts.append(f"  分类: {category}")
                if entities_str:
                    parts.append(f"  实体: {entities_str}")
        
        return "\n".join(parts)
    
    async def _ensure_recall_deps(self):
        """确保召回依赖可用（延迟初始化，参考 search 模块）"""
        if self._event_repo is None:
            from dataflow.modules.load.processor import DocumentProcessor
            
            # 初始化 ES 客户端和仓库
            self._es_client = get_es_client()
            self._event_repo = EventVectorRepository(self._es_client)
            
            # 初始化向量生成器（使用 DocumentProcessor，与 search 模块一致）
            self._embedding_client = DocumentProcessor(llm_client=self.llm_client)
    
    async def _recall_related_events(self, content: str) -> List[Dict]:
        """
        召回同信息源的相关历史事项（用于分类和实体命名参考）
        
        Args:
            content: 当前处理的内容文本
        
        Returns:
            历史事项列表 [{title, category, entities: [{type, name}]}]
        """
        if not self.config.enable_related_events:
            return []
        
        try:
            # 确保依赖可用
            await self._ensure_recall_deps()
            
            # 1. 生成当前内容的向量（使用 DocumentProcessor）
            content_vector = await self._embedding_client.generate_embedding(content[:2000])
            
            # 2. 从 ES 召回同信息源的历史事项
            results = await self._event_repo.search_similar_by_content(
                query_vector=content_vector,
                k=self.config.related_events_top_k,
                source_config_id=self.config.source_config_id
            )
            
            # 3. 过滤低相似度结果
            results = [r for r in results if r.get("_score", 0) >= self.config.related_events_threshold]
            
            if not results:
                return []
            
            # 4. 从数据库加载事项详情和实体
            event_ids = [r["event_id"] for r in results]
            related_events = []
            
            async with self.session_factory() as session:
                stmt = (
                    select(SourceEvent)
                    .options(selectinload(SourceEvent.event_associations).selectinload(EventEntity.entity))
                    .where(SourceEvent.id.in_(event_ids))
                )
                db_events = (await session.execute(stmt)).scalars().all()
                
                for event in db_events:
                    entities = [
                        {"type": ee.entity.type, "name": ee.entity.name}
                        for ee in event.event_associations if ee.entity
                    ]
                    related_events.append({
                        "title": event.title,
                        "category": event.category or "",
                        "entities": entities[:10]  # 限制实体数量
                    })
            
            self.logger.info(f"召回 {len(related_events)} 个相关历史事项作为参考")
            return related_events
            
        except Exception as e:
            self.logger.warning(f"历史事项召回失败: {e}")
            return []
    
    def _build_user_input(self, items: List, is_article: bool) -> Dict:
        """
        构建 USER 输入（统一结构：type + name + description + items）
        
        Args:
            items: 内容列表
            is_article: 是否为文章类型
        
        Returns:
            {"type": "input", "name": "...", "description": "...", "items": [...]}
        """
        if is_article:
            # ArticleSection: heading + content
            items_data = [
                {
                    "id": item.id,
                    "content": f"{getattr(item, 'heading', '') or ''}\n{item.content}".strip()
                }
                for item in items
            ]
            name = "文档片段"
            description = "来源于文档的片段内容，每个 item 包含标题和正文，id 用于事项引用"
        else:
            # ChatMessage: [time] sender: content
            items_data = [
                {
                    "id": item.id,
                    "content": f"[{item.timestamp.strftime('%H:%M') if hasattr(item, 'timestamp') and item.timestamp else ''}] {getattr(item, 'sender_name', '未知')}: {item.content}"
                }
                for item in items
            ]
            name = "聊天消息"
            description = "来源于会话的消息记录，每个 item 包含时间、发送者和内容，id 用于事项引用"
        
        return {
            "type": "input",
            "name": name,
            "description": description,
            "items": items_data
        }

    def _get_entity_types_description(self) -> str:
        """获取实体类型说明（简化版，只取第一行描述）"""
        lines = []

        for entity_type in self.entity_types:
            # 只取描述的第一行，避免太长
            desc = entity_type.description or ""
            first_line = desc.split('\n')[0].strip() if desc else f"提取{entity_type.name}相关实体"
            lines.append(f"- **{entity_type.type}** ({entity_type.name}): {first_line}")

        return "\n".join(lines)

    def _build_extraction_schema(self) -> Dict[str, Any]:
        """
        构建动态JSON Schema（统一结构：type + name + description + items）

        Returns:
            JSON Schema字典
        """
        valid_types = [et.type for et in self.entity_types]
        
        return {
            "type": "object",
            "properties": {
                "type": {"type": "string", "const": "output"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "summary": {"type": "string"},
                            "content": {"type": "string"},
                            "category": {"type": "string"},
                            "references": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 1
                            },
                            "entities": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "enum": valid_types},
                                        "name": {"type": "string"},
                                        "description": {"type": "string"}
                                    },
                                    "required": ["type", "name", "description"]
                                }
                            },
                            "is_valid": {"type": "boolean"}
                        },
                        "required": ["title", "summary", "content", "category", "references", "entities", "is_valid"]
                    }
                }
            },
            "required": ["type", "name", "description", "items"]
        }

    async def _parse_extraction_result(
        self, result: Dict[str, Any], sections: List[SourceChunk]
    ) -> List[SourceEvent]:
        """
        解析LLM提取结果为SourceEvent对象

        Args:
            result: LLM返回的JSON结果
            sections: 原始片段列表（用于生成引用）

        Returns:
            SourceEvent对象列表
        """
        events = []

        for event_data in result.get("items", []):
            # 解析 LLM 标注的引用（片段编号，从1开始）
            referenced_indices = event_data.get("references", [])

            # 将片段编号转换为实际的 section_id
            referenced_section_ids = []
            invalid_indices = []

            for idx in referenced_indices:
                if isinstance(idx, int) and 1 <= idx <= len(sections):  # 验证索引有效性
                    section = sections[idx - 1]  # 编号从1开始，索引从0开始
                    referenced_section_ids.append(section.id)
                else:
                    # 记录无效索引
                    invalid_indices.append(idx)

            # 记录警告（如果有无效索引）
            if invalid_indices:
                self.logger.warning(
                    f"事项 '{event_data.get('title', '未知')}' 包含无效的片段引用索引: {invalid_indices}",
                    extra={
                        "event_title": event_data.get("title"),
                        "invalid_indices": invalid_indices,
                        "total_sections": len(sections),
                    },
                )

            # 确定主要引用的 chunk（取第一个被引用的 chunk）
            primary_chunk = None
            if referenced_section_ids:
                # 查找第一个被引用的 section 对应的 chunk
                for section in sections:
                    if section.id == referenced_section_ids[0]:
                        primary_chunk = section
                        break
                if not primary_chunk:
                    primary_chunk = sections[0]  # 如果没找到，默认使用第一个 chunk
            else:
                primary_chunk = sections[0] if sections else None

            # 🆕 根据来源类型设置时间
            from datetime import datetime
            from dataflow.db import ChatMessage
            from sqlalchemy import select
            
            start_time = None
            end_time = None
            event_references = primary_chunk.references if primary_chunk else None
            
            if primary_chunk:
                if primary_chunk.source_type == "ARTICLE":
                    # 文档类型：使用当前时间
                    current_time = datetime.now()
                    start_time = current_time
                    end_time = current_time
                    
                elif primary_chunk.source_type == "CHAT":
                    # 会话类型：从引用的消息中获取时间范围
                    # 使用 primary_chunk.references（因为事项会继承这个）
                    if event_references and isinstance(event_references, list):
                        async with self.session_factory() as session:
                            result_msgs = await session.execute(
                                select(ChatMessage)
                                .where(ChatMessage.id.in_(event_references))
                                .order_by(ChatMessage.timestamp)
                            )
                            messages = list(result_msgs.scalars().all())
                            
                            if messages:
                                start_time = messages[0].timestamp
                                end_time = messages[-1].timestamp
            
            # 创建事项对象
            # 注意：sections 列表已在方法开始时验证为非空
            source_type_value = primary_chunk.source_type if primary_chunk else "ARTICLE"
            event = SourceEvent(
                id=str(uuid.uuid4()),
                source_config_id=self.config.source_config_id,
                source_type=source_type_value,  # 🆕
                source_id=primary_chunk.source_id if primary_chunk else sections[0].source_id,  # 🆕
                article_id=sections[0].article_id if primary_chunk and primary_chunk.source_type == "ARTICLE" else None,  # 🆕 修改
                conversation_id=primary_chunk.conversation_id if primary_chunk and primary_chunk.source_type == "CHAT" else None,  # 🆕
                title=event_data["title"],
                summary=event_data.get("summary") or "",
                content=event_data["content"],
                category=event_data.get("category") or "",  # 独立字段，确保None转为空字符串
                # 业务字段（兼容主系统）- type与source_type保持一致
                type=source_type_value,
                priority="UNKNOWN",  # 默认值
                status="UNKNOWN",  # 默认值
                rank=None,  # 由上层 EventExtractor 统一分配全局 rank，确保同一文章内事项按顺序排列
                start_time=start_time,  # 🆕
                end_time=end_time,  # 🆕
                # 使用 references 字段存储 AI 标注的引用片段（精确引用）
                references=referenced_section_ids,  # ✅ 修复：使用LLM精确标注的引用
                chunk_id=primary_chunk.id if primary_chunk else None,
                extra_data={
                    "quality_score": event_data.get("quality_score", 0.8),
                    "batch_size": len(sections),
                    # category不再存储在extra_data中
                },
            )

            # 解析实体
            entities_data = event_data.get("entities", {})
            event_associations = []

            # 处理每种类型的实体
            for entity_type, entity_names in entities_data.items():
                if not entity_names:
                    continue

                # 查找对应的实体类型定义
                entity_type_obj = self._get_entity_type_by_type(entity_type)
                if not entity_type_obj:
                    self.logger.warning(
                        f"未找到实体类型 '{entity_type}'，跳过该类型的实体提取",
                        extra={"entity_type": entity_type,
                               "event_title": event_data.get("title")},
                    )
                    continue

                for entity_data in entity_names:
                    # 兼容新旧格式：字符串或对象
                    if isinstance(entity_data, dict):
                        name = entity_data.get("name")
                        description = entity_data.get("description", "")
                    else:
                        # 旧格式：直接是字符串
                        name = entity_data
                        description = ""

                    if not name:
                        continue

                    # 获取或创建实体ID（不再传递description）
                    entity_id = await self._get_or_create_entity(
                        entity_type, name, entity_type_obj
                    )

                    # 创建关联对象（description保存到中间表）
                    assoc = EventEntity(
                        id=str(uuid.uuid4()),
                        event_id=event.id,
                        entity_id=entity_id,
                        weight=float(entity_type_obj.weight),
                        description=description or None,  # 保存到中间表
                        extra_data={"confidence": event_data.get(
                            "quality_score", 0.8)},
                    )

                    # 绑定关系
                    event_associations.append(assoc)

            event.event_associations = event_associations
            events.append(event)

        return events

    async def _get_or_create_entity(
        self, entity_type: str, entity_name: str, entity_type_obj: DBEntityType
    ) -> str:
        """
        获取或创建实体的ID（使用新 session）

        先查询数据库是否存在相同 (source_config_id, type, normalized_name) 的实体，
        如果存在则返回其ID，否则创建新实体并返回新ID。

        Args:
            entity_type: 实体类型标识符
            entity_name: 实体原始名称
            entity_type_obj: 实体类型对象

        Returns:
            实体ID
        """
        normalized_name = self._normalize_entity_name(entity_name)

        async with self.session_factory() as session:
            return await self._get_or_create_entity_with_session(
                session, entity_type, entity_name, normalized_name, entity_type_obj
            )

    async def _get_or_create_entity_with_session(
        self,
        session,
        entity_type: str,
        entity_name: str,
        normalized_name: str,
        entity_type_obj: DBEntityType,
    ) -> str:
        """
        获取或创建实体的ID（使用已有 session）

        先查询数据库是否存在相同 (source_config_id, type, normalized_name) 的实体，
        如果存在则返回其ID，否则创建新实体并返回新ID。

        Args:
            session: 数据库 session
            entity_type: 实体类型标识符
            entity_name: 实体原始名称
            normalized_name: 标准化的实体名称
            entity_type_obj: 实体类型对象

        Returns:
            实体ID
        """
        # 查询已存在的实体
        result = await session.execute(
            select(Entity)
            .where(Entity.source_config_id == self.config.source_config_id)
            .where(Entity.type == entity_type)
            .where(Entity.normalized_name == normalized_name)
        )
        existing_entity = result.scalar_one_or_none()

        if existing_entity:
            self.logger.debug(
                f"实体已存在：{entity_name} -> {existing_entity.name} (ID: {existing_entity.id})"
            )
            return existing_entity.id

        # 创建新实体（不保存description）
        new_entity = Entity(
            id=str(uuid.uuid4()),
            source_config_id=self.config.source_config_id,
            entity_type_id=entity_type_obj.id,
            type=entity_type,
            name=entity_name,
            normalized_name=normalized_name,
            description=None,  # 不再保存description到Entity表
            extra_data={},
        )

        # 🆕 解析类型化值
        try:
            value_constraints = entity_type_obj.value_constraints if hasattr(
                entity_type_obj, 'value_constraints') else None
            entity_type_category = entity_type_obj.type if hasattr(
                entity_type_obj, 'type') else None
            typed_fields = self.parser.parse_to_typed_fields(
                entity_name,
                entity_type=entity_type,
                entity_type_category=entity_type_category,  # 🆕 传递属性类型（time/person/location等）
                value_constraints=value_constraints
            )

            # 填充类型化字段
            if typed_fields:
                new_entity.value_type = typed_fields.get("value_type")
                new_entity.value_raw = typed_fields.get("value_raw")
                new_entity.int_value = typed_fields.get("int_value")
                new_entity.float_value = typed_fields.get("float_value")
                new_entity.datetime_value = typed_fields.get("datetime_value")
                new_entity.bool_value = typed_fields.get("bool_value")
                new_entity.enum_value = typed_fields.get("enum_value")
                new_entity.value_unit = typed_fields.get("value_unit")
                new_entity.value_confidence = typed_fields.get(
                    "value_confidence")

                self.logger.debug(
                    f"✅ 解析实体值: {entity_name} -> {typed_fields.get('value_type')} = {typed_fields.get('int_value') or typed_fields.get('float_value') or typed_fields.get('datetime_value') or typed_fields.get('bool_value') or typed_fields.get('enum_value')}"
                )
        except Exception as e:
            # 解析失败不影响实体创建
            self.logger.warning(f"⚠️ 实体值解析失败: {entity_name}, error={e}")

        # 添加到 session（但不立即提交）
        # 🆕 不在内层处理异常，让异常传播到外层由重试机制统一处理
        # 原因：内层 rollback 会回滚同一 session 中所有已 flush 但未 commit 的实体
        session.add(new_entity)
        await session.flush()  # flush 以获取 ID，但不提交事务
        self.logger.debug(f"创建新实体：{entity_name} (ID: {new_entity.id})")
        return new_entity.id

    async def _batch_query_existing_entities(
        self, all_entities_data: Dict[str, Dict[str, str]]
    ) -> Dict[tuple, tuple]:
        """
        批量查询已存在的实体（优化：减少数据库查询次数）
        
        Args:
            all_entities_data: {entity_type: {name: description}}
        
        Returns:
            {(entity_type, normalized_name): (entity_id, description)}
        """
        entity_id_map = {}
        
        # 收集所有 (type, normalized_name, name, description) 元组
        all_keys = []
        for entity_type, entities_dict in all_entities_data.items():
            for name, description in entities_dict.items():
                normalized = self._normalize_entity_name(name)
                all_keys.append((entity_type, normalized, name, description))
        
        if not all_keys:
            return entity_id_map
        
        # 批量查询（分批避免 SQL 过长）
        batch_size = 100
        async with self.session_factory() as session:
            for i in range(0, len(all_keys), batch_size):
                batch = all_keys[i:i + batch_size]
                
                # 构建 OR 条件
                conditions = [
                    (Entity.type == etype) & (Entity.normalized_name == norm)
                    for etype, norm, _, _ in batch
                ]
                
                result = await session.execute(
                    select(Entity)
                    .where(Entity.source_config_id == self.config.source_config_id)
                    .where(or_(*conditions))
                )
                
                # 建立已存在实体的映射
                for entity in result.scalars().all():
                    key = (entity.type, entity.normalized_name)
                    # 找到对应的 description
                    for etype, norm, name, desc in batch:
                        if (etype, norm) == key:
                            entity_id_map[key] = (entity.id, desc)
                            break
        
        self.logger.info(f"批量查询: 需要 {len(all_keys)} 个实体，已存在 {len(entity_id_map)} 个")
        return entity_id_map

    async def _create_entity_with_retry(
        self,
        entity_type: str,
        entity_name: str,
        entity_type_obj: DBEntityType,
    ) -> str:
        """
        独立事务创建实体，冲突时重新查询
        
        每个实体使用独立的数据库事务，冲突不会影响其他实体。
        处理的错误类型：
        - IntegrityError: 唯一约束冲突（并发创建相同实体）
        - OperationalError: 死锁(1213)、锁等待超时(1205)
        
        Args:
            entity_type: 实体类型标识符
            entity_name: 实体原始名称
            entity_type_obj: 实体类型对象
        
        Returns:
            实体ID
        """
        import asyncio
        from sqlalchemy.exc import IntegrityError, OperationalError
        
        normalized_name = self._normalize_entity_name(entity_name)
        max_retries = 3
        base_delay = 0.05  # 50ms 基础延迟
        
        for attempt in range(max_retries):
            async with self.session_factory() as session:
                try:
                    # 再次查询（可能已被其他任务创建）
                    result = await session.execute(
                        select(Entity)
                        .where(Entity.source_config_id == self.config.source_config_id)
                        .where(Entity.type == entity_type)
                        .where(Entity.normalized_name == normalized_name)
                    )
                    existing = result.scalar_one_or_none()
                    if existing:
                        self.logger.debug(f"🔄 实体已被其他任务创建: {entity_name}")
                        return existing.id
                    
                    # 创建新实体
                    new_entity = Entity(
                        id=str(uuid.uuid4()),
                        source_config_id=self.config.source_config_id,
                        entity_type_id=entity_type_obj.id,
                        type=entity_type,
                        name=entity_name,
                        normalized_name=normalized_name,
                        description=None,
                        extra_data={},
                    )
                    
                    # 解析类型化值
                    try:
                        value_constraints = getattr(entity_type_obj, 'value_constraints', None)
                        typed_fields = self.parser.parse_to_typed_fields(
                            entity_name,
                            entity_type=entity_type,
                            entity_type_category=entity_type_obj.type,
                            value_constraints=value_constraints
                        )
                        if typed_fields:
                            new_entity.value_type = typed_fields.get("value_type")
                            new_entity.value_raw = typed_fields.get("value_raw")
                            new_entity.int_value = typed_fields.get("int_value")
                            new_entity.float_value = typed_fields.get("float_value")
                            new_entity.datetime_value = typed_fields.get("datetime_value")
                            new_entity.bool_value = typed_fields.get("bool_value")
                            new_entity.enum_value = typed_fields.get("enum_value")
                            new_entity.value_unit = typed_fields.get("value_unit")
                            new_entity.value_confidence = typed_fields.get("value_confidence")
                    except Exception as e:
                        self.logger.warning(f"⚠️ 实体值解析失败: {entity_name}, error={e}")
                    
                    session.add(new_entity)
                    await session.commit()
                    self.logger.debug(f"✅ 创建新实体: {entity_name} (ID: {new_entity.id})")
                    return new_entity.id
                    
                except IntegrityError as exc:
                    # 并发冲突（唯一约束），回滚并重试
                    await session.rollback()
                    self.logger.debug(f"🔄 实体创建冲突，重试 ({attempt + 1}/{max_retries}): {entity_name}")
                    
                    if attempt == max_retries - 1:
                        # 最后一次重试：查询已存在的实体
                        async with self.session_factory() as retry_session:
                            result = await retry_session.execute(
                                select(Entity)
                                .where(Entity.source_config_id == self.config.source_config_id)
                                .where(Entity.type == entity_type)
                                .where(Entity.normalized_name == normalized_name)
                            )
                            existing = result.scalar_one_or_none()
                            if existing:
                                self.logger.debug(f"✅ 冲突后查询到已存在实体: {entity_name}")
                                return existing.id
                        raise ExtractError(f"实体创建失败（重试{max_retries}次）: {entity_name}") from exc
                    
                    await asyncio.sleep(base_delay * (2 ** attempt))
                    
                except OperationalError as exc:
                    # 死锁(1213)或锁等待超时(1205)
                    error_str = str(exc)
                    is_deadlock = "1213" in error_str or "Deadlock" in error_str
                    is_lock_timeout = "1205" in error_str or "Lock wait timeout" in error_str
                    
                    if is_deadlock or is_lock_timeout:
                        await session.rollback()
                        error_type = "死锁" if is_deadlock else "锁超时"
                        self.logger.warning(
                            f"🔄 实体创建{error_type}，重试 ({attempt + 1}/{max_retries}): {entity_name}"
                        )
                        
                        if attempt == max_retries - 1:
                            raise ExtractError(
                                f"实体创建失败（{error_type}，重试{max_retries}次）: {entity_name}"
                            ) from exc
                        
                        # 死锁使用更长的退避时间
                        delay = base_delay * (2 ** (attempt + 1)) if is_deadlock else base_delay * (2 ** attempt)
                        await asyncio.sleep(delay)
                    else:
                        # 非死锁/锁超时的 OperationalError，直接抛出
                        raise
        
        raise ExtractError(f"实体创建失败: {entity_name}")

    def _normalize_entity_name(self, name: str) -> str:
        """
        标准化实体名称

        Args:
            name: 原始名称（可能是字符串或其他类型，如整数）

        Returns:
            标准化后的名称
        """
        import re

        # 先转为字符串，确保能处理非字符串输入（如 LLM 提取的数字实体）
        name_str = str(name)

        # 去除首尾空格并转小写
        normalized = name_str.strip().lower()

        # 去除多余的空格（多个空格合并为一个）
        normalized = re.sub(r"\s+", " ", normalized)

        # 去除常见的标点符号（保留中文标点）
        normalized = re.sub(r"[^\w\s\u4e00-\u9fff]", "", normalized)

        return normalized.strip()

    def _get_entity_type_by_type(self, entity_type: str) -> Optional[DBEntityType]:
        """
        根据类型标识符查找实体类型

        Args:
            entity_type: 实体类型标识符

        Returns:
            实体类型对象，如果未找到返回 None
        """
        for et in self.entity_types:
            if et.type == entity_type:
                return et
        return None

    def _get_entity_type_weight(self, entity_type: str) -> float:
        """
        获取实体类型权重

        Args:
            entity_type: 实体类型

        Returns:
            权重值
        """
        # 从加载的实体类型中查找
        entity_type_obj = self._get_entity_type_by_type(entity_type)
        if entity_type_obj:
            return float(entity_type_obj.weight)

        # 默认权重
        return 1.0

    def _cross_fill_entities(self, events: List[SourceEvent]) -> List[SourceEvent]:
        """
        实体交叉补充（兜底策略）
        
        收集本次提取的所有实体，检查每个事项的标题+正文是否包含其他事项的实体但未提取，
        如果包含则自动补充。
        
        注意：权重小于1的实体类型不参与交叉，以减少噪音。
        
        Args:
            events: 本次提取的事项列表（extra_data["raw_entities"] 存储实体）
        
        Returns:
            补充后的事项列表
        """
        if len(events) <= 1:
            return events
        
        # 批量获取实体类型权重
        type_weights = {et.type: float(et.weight) for et in self.entity_types}
        
        # 收集所有实体，过滤低权重类型
        # key: (type, name_lower), value: {type, name, description}
        all_entities = {}
        filtered_count = 0
        
        for event in events:
            raw_entities = event.extra_data.get("raw_entities", {})
            for entity_type, entity_list in raw_entities.items():
                # 权重 < 1 的实体类型不参与交叉
                if type_weights.get(entity_type, 1.0) < 1.0:
                    filtered_count += len(entity_list) if entity_list else 0
                    continue
                
                for entity_data in entity_list:
                    if isinstance(entity_data, dict):
                        name = entity_data.get('name', '')
                        description = entity_data.get('description', '')
                    else:
                        name = str(entity_data)
                        description = ''
                    
                    if not name:
                        continue
                    
                    key = (entity_type, name.lower())
                    if key not in all_entities:
                        all_entities[key] = {
                            'type': entity_type,
                            'name': name,
                            'description': description
                        }
        
        if not all_entities:
            if filtered_count > 0:
                self.logger.debug(f"实体交叉补充: 过滤了 {filtered_count} 个低权重类型实体")
            return events
        
        self.logger.info(
            f"实体交叉补充: {len(all_entities)} 个实体待检查，过滤 {filtered_count} 个低权重类型"
        )
        
        # 交叉补充
        total_added = 0
        for event in events:
            text = f"{event.title} {event.content}".lower()
            raw_entities = event.extra_data.get("raw_entities", {})
            
            # 收集当前事项已有的实体名称（按类型）
            existing_by_type = {}  # {type: set(name_lower)}
            for entity_type, entity_list in raw_entities.items():
                existing_by_type[entity_type] = set()
                for entity_data in entity_list:
                    if isinstance(entity_data, dict):
                        name = entity_data.get('name', '').lower()
                    else:
                        name = str(entity_data).lower()
                    if name:
                        existing_by_type[entity_type].add(name)
            
            # 检查并补充缺失的实体
            added = []
            for (entity_type, name_lower), entity in all_entities.items():
                # 检查文本是否包含该实体名称
                if name_lower not in text:
                    continue
                
                # 检查该类型是否已有该实体
                if entity_type in existing_by_type and name_lower in existing_by_type[entity_type]:
                    continue
                
                # 补充实体
                if entity_type not in raw_entities:
                    raw_entities[entity_type] = []
                
                raw_entities[entity_type].append({
                    'name': entity['name'],
                    'description': entity.get('description', '')
                })
                
                # 更新已存在集合
                if entity_type not in existing_by_type:
                    existing_by_type[entity_type] = set()
                existing_by_type[entity_type].add(name_lower)
                
                added.append(f"{entity['name']}({entity_type})")
            
            if added:
                total_added += len(added)
                event.extra_data["raw_entities"] = raw_entities
                self.logger.debug(f"事项 '{event.title[:30]}' 补充实体: {', '.join(added)}")
        
        if total_added > 0:
            self.logger.info(f"实体交叉补充完成: 共补充 {total_added} 个实体")
        
        return events

    def _inject_time_entities_for_event(self, event: SourceEvent) -> None:
        """
        自动注入时间实体（基于事项的 start_time/end_time 字段）

        规则：
        - 如果配置了 start_time 类型且事项有 start_time → 注入
        - 如果配置了 end_time 类型且事项有 end_time → 注入
        - 没有配置对应类型 → 跳过

        Args:
            event: 事项对象
        """
        # 确保有 raw_entities 字段
        if "raw_entities" not in event.extra_data:
            event.extra_data["raw_entities"] = {}

        raw_entities = event.extra_data["raw_entities"]

        # 检查是否配置了 start_time 类型
        has_start_time_type = any(et.type == "start_time" for et in self.entity_types)

        # 检查是否配置了 end_time 类型
        has_end_time_type = any(et.type == "end_time" for et in self.entity_types)

        # 注入开始时间
        if has_start_time_type and event.start_time:
            time_str = event.start_time.strftime("%Y年%m月%d日 %H:%M:%S")
            if "start_time" not in raw_entities:
                raw_entities["start_time"] = []
            raw_entities["start_time"].append({
                "name": time_str,
                "description": "事项开始时间"
            })
            self.logger.debug(f"✅ 注入开始时间: {time_str}, event_id={event.id[:8]}...")

        # 注入结束时间
        if has_end_time_type and event.end_time:
            time_str = event.end_time.strftime("%Y年%m月%d日 %H:%M:%S")
            if "end_time" not in raw_entities:
                raw_entities["end_time"] = []
            raw_entities["end_time"].append({
                "name": time_str,
                "description": "事项结束时间"
            })
            self.logger.debug(f"✅ 注入结束时间: {time_str}, event_id={event.id[:8]}...")
