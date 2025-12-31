"""
事项过滤器 - Filter 层

基于 Critic 的评估结果进行实际的修改和过滤操作
"""

from typing import Any, Dict, List
from dataflow.utils import get_logger

logger = get_logger("extract.filter")


class EventFilter:
    """
    事项过滤器 (Filter 层)

    根据 Critic 的评估结果进行过滤和修正
    - 删除无效事项
    - 删除无效实体
    - 修正实体类型
    - 合并重复事项
    """

    def __init__(self):
        """初始化过滤器"""
        self.logger = logger

    def filter_events(
        self,
        events: List[Any],
        evaluations: List[Dict[str, Any]],
        batch_index: int,
    ) -> List[Any]:
        """
        根据 Critic 评估结果过滤和修正事项

        Args:
            events: 原始事项列表
            evaluations: Critic 评估结果列表
            batch_index: 批次索引

        Returns:
            过滤和修正后的事项列表
        """
        if not events:
            return events

        if not evaluations:
            self.logger.warning(
                f"批次 {batch_index}: 无评估结果，跳过过滤"
            )
            return events

        self.logger.info(
            f"🔧 批次 {batch_index}: 开始过滤 - "
            f"共 {len(events)} 个事项，{len(evaluations)} 条评估"
        )

        # 创建评估结果映射
        eval_map = {eval["event_id"]: eval for eval in evaluations}

        # 第一步：删除无效事项
        filtered_events = self._remove_invalid_events(
            events, eval_map, batch_index
        )

        # 第二步：删除无效实体
        filtered_events = self._remove_invalid_entities(
            filtered_events, eval_map, batch_index
        )

        # 第三步：修正实体类型
        filtered_events = self._fix_entity_types(
            filtered_events, eval_map, batch_index
        )

        # 第四步：合并重复事项
        final_events = self._merge_duplicate_events(
            filtered_events, eval_map, batch_index
        )

        self.logger.info(
            f"✅ 批次 {batch_index}: 过滤完成 - "
            f"保留 {len(final_events)}/{len(events)} 个事项"
        )

        return final_events

    def _remove_invalid_events(
        self,
        events: List[Any],
        eval_map: Dict[str, Dict[str, Any]],
        batch_index: int,
    ) -> List[Any]:
        """
        删除无效事项

        Args:
            events: 原始事项列表
            eval_map: 评估结果映射 {event_id: evaluation}
            batch_index: 批次索引

        Returns:
            过滤后的事项列表
        """
        filtered = []
        removed_count = 0

        for event in events:
            evaluation = eval_map.get(event.id)

            if not evaluation:
                # 无评估结果，保留
                filtered.append(event)
                continue

            is_invalid = evaluation.get("is_invalid", False)

            # 检查是否有 invalid_event 问题
            has_invalid_issue = any(
                issue.get("type") == "invalid_event"
                for issue in evaluation.get("issues", [])
            )

            if is_invalid and has_invalid_issue:
                removed_count += 1
                self.logger.debug(
                    f"🗑️ 批次 {batch_index}: 删除无效事项 '{event.title[:50]}' - "
                    f"理由: {evaluation.get('reason', '')[:100]}"
                )
            else:
                filtered.append(event)

        if removed_count > 0:
            self.logger.info(
                f"🗑️ 批次 {batch_index}: 删除 {removed_count} 个无效事项"
            )

        return filtered

    def _remove_invalid_entities(
        self,
        events: List[Any],
        eval_map: Dict[str, Dict[str, Any]],
        batch_index: int,
    ) -> List[Any]:
        """
        删除事项中的无效实体

        Args:
            events: 事项列表
            eval_map: 评估结果映射
            batch_index: 批次索引

        Returns:
            修正后的事项列表
        """
        removed_entities = 0

        for event in events:
            evaluation = eval_map.get(event.id)

            if not evaluation:
                continue

            raw_entities = event.extra_data.get("raw_entities", {})
            issues = evaluation.get("issues", [])

            # 找出需要删除的实体
            entities_to_remove = set()

            for issue in issues:
                if issue.get("type") == "invalid_entity":
                    # 从 entity_info 中提取实体信息
                    entity_info = issue.get("entity_info", {})
                    entity_name = entity_info.get("name", "")
                    entity_type = entity_info.get("type", "")

                    if entity_name and entity_type:
                        entities_to_remove.add((entity_type, entity_name.lower()))

            # 删除实体
            if entities_to_remove:
                for entity_type, entity_list in raw_entities.items():
                    filtered_list = []
                    for entity in entity_list:
                        name = entity.get("name", "")
                        key = (entity_type, name.lower())

                        if key in entities_to_remove:
                            removed_entities += 1
                            self.logger.debug(
                                f"🗑️ 批次 {batch_index}: 删除无效实体 "
                                f"[{entity_type}]: {name} "
                                f"(事项: {event.title[:30]})"
                            )
                        else:
                            filtered_list.append(entity)

                    raw_entities[entity_type] = filtered_list

                event.extra_data["raw_entities"] = raw_entities

        if removed_entities > 0:
            self.logger.info(
                f"🗑️ 批次 {batch_index}: 删除 {removed_entities} 个无效实体"
            )

        return events

    def _fix_entity_types(
        self,
        events: List[Any],
        eval_map: Dict[str, Dict[str, Any]],
        batch_index: int,
    ) -> List[Any]:
        """
        修正实体类型错误

        Args:
            events: 事项列表
            eval_map: 评估结果映射
            batch_index: 批次索引

        Returns:
            修正后的事项列表
        """
        fixed_count = 0

        for event in events:
            evaluation = eval_map.get(event.id)

            if not evaluation:
                continue

            raw_entities = event.extra_data.get("raw_entities", {})
            issues = evaluation.get("issues", [])

            # 找出需要修正的实体
            entities_to_fix = {}

            for issue in issues:
                if issue.get("type") == "entity_mismatch":
                    # 从 entity_info 中提取实体信息和正确类型
                    entity_info = issue.get("entity_info", {})
                    name = entity_info.get("name", "")
                    current_type = entity_info.get("type", "")
                    correct_type = entity_info.get("correct_type", "")

                    if current_type and name and correct_type:
                        entities_to_fix[(current_type, name)] = correct_type

            # 修正实体类型
            if entities_to_fix:
                for entity_type, entity_list in raw_entities.items():
                    new_list = []

                    for entity in entity_list:
                        name = entity.get("name", "")
                        key = (entity_type, name)

                        if key in entities_to_fix:
                            correct_type = entities_to_fix[key]
                            # 修改实体类型
                            entity["type"] = correct_type
                            fixed_count += 1
                            self.logger.debug(
                                f"🔧 批次 {batch_index}: 修正实体类型 "
                                f"'{name}' {entity_type} -> {correct_type} "
                                f"(事项: {event.title[:30]})"
                            )

                        new_list.append(entity)

                    raw_entities[entity_type] = new_list

                # 需要重新组织实体到正确的类型下
                raw_entities = self._reorganize_entities(raw_entities)
                event.extra_data["raw_entities"] = raw_entities

        if fixed_count > 0:
            self.logger.info(
                f"🔧 批次 {batch_index}: 修正 {fixed_count} 个实体的类型"
            )

        return events

    def _merge_duplicate_events(
        self,
        events: List[Any],
        eval_map: Dict[str, Dict[str, Any]],
        batch_index: int,
    ) -> List[Any]:
        """
        合并重复事项

        Args:
            events: 事项列表
            eval_map: 评估结果映射
            batch_index: 批次索引

        Returns:
            合并后的事项列表
        """
        # 找出需要合并的事项组
        merge_groups = []
        processed_ids = set()

        for event in events:
            if event.id in processed_ids:
                continue

            evaluation = eval_map.get(event.id)
            if not evaluation:
                processed_ids.add(event.id)
                continue

            issues = evaluation.get("issues", [])
            duplicate_issues = [
                issue for issue in issues
                if issue.get("type") == "duplicate"
            ]

            if duplicate_issues:
                group = [event]
                processed_ids.add(event.id)

                # 从 duplicate_with 字段中找出要合并的事项ID
                for issue in duplicate_issues:
                    duplicate_event_id = issue.get("duplicate_with", "")
                    if duplicate_event_id:
                        # 找到对应的事项
                        for other_event in events:
                            if other_event.id == duplicate_event_id:
                                group.append(other_event)
                                processed_ids.add(duplicate_event_id)
                                break

                if len(group) > 1:
                    merge_groups.append(group)

        # 合并事项组
        merged_events = []
        merged_ids = set()

        for group in merge_groups:
            if len(group) == 1:
                merged_events.append(group[0])
                continue

            # 选择最完整的事项作为基础（通常选内容最长的）
            base_event = max(group, key=lambda e: len(e.content))
            merged_ids.update(e.id for e in group)

            # 合并实体
            merged_entities = {}
            for event in group:
                raw_entities = event.extra_data.get("raw_entities", {})
                for entity_type, entity_list in raw_entities.items():
                    if entity_type not in merged_entities:
                        merged_entities[entity_type] = []

                    # 去重添加实体
                    existing_names = {
                        e.get("name", "").lower()
                        for e in merged_entities[entity_type]
                    }

                    for entity in entity_list:
                        name = entity.get("name", "")
                        if name.lower() not in existing_names:
                            merged_entities[entity_type].append(entity)
                            existing_names.add(name.lower())

            base_event.extra_data["raw_entities"] = merged_entities

            merged_events.append(base_event)

            self.logger.info(
                f"🔗 批次 {batch_index}: 合并 {len(group)} 个重复事项 - "
                f"主事项: '{base_event.title[:50]}'"
            )

        # 添加未合并的事项
        for event in events:
            if event.id not in merged_ids:
                merged_events.append(event)

        return merged_events

    def _reorganize_entities(
        self,
        raw_entities: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        重新组织实体到正确的类型下

        Args:
            raw_entities: 原始实体字典

        Returns:
            重新组织后的实体字典
        """
        reorganized = {}

        for old_type, entity_list in raw_entities.items():
            for entity in entity_list:
                new_type = entity.get("type", old_type)

                if new_type not in reorganized:
                    reorganized[new_type] = []

                reorganized[new_type].append(entity)

        return reorganized

    def _guess_entity_type_from_reason(self, reason: str) -> str:
        """
        从理由中猜测实体类型

        Args:
            reason: 问题描述

        Returns:
            实体类型或空字符串
        """
        if "新闻来源地" in reason or "发布地" in reason:
            return "location"
        elif "媒体平台" in reason:
            return "organization"
        elif "记者" in reason or "作者" in reason:
            return "person"

        return ""
