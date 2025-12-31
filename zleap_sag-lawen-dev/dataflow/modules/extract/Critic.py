"""
实体提取评估器 - Multi-Agent 机制

使用 LLM 智能评估提取的事件和实体质量
"""

from typing import Any, Dict, List
from dataflow.core.ai.models import LLMMessage, LLMRole
from dataflow.core.prompt.manager import get_prompt_manager
from dataflow.utils import get_logger

logger = get_logger("extract.critic")


class EventCritic:
    """
    LLM 评估器 (Critic 层)

    逐条评估提取的事件和实体是否合规，给出 yes/no + 理由
    不做修改和删除，只负��评估
    """

    def __init__(self, llm_client, entity_types: List[Any]):
        """
        初始化评估器

        Args:
            llm_client: LLM 客户端
            entity_types: 实体类型配置列表
        """
        self.llm_client = llm_client
        self.entity_types = entity_types
        self.logger = logger
        self.prompt_manager = get_prompt_manager()

    async def evaluate_events(
        self,
        events: List[Any],
        original_content: str,
        batch_index: int,
    ) -> List[Dict[str, Any]]:
        """
        逐条评估事件和实体

        Args:
            events: 待评估的事件列表
            original_content: 原文内容
            batch_index: 批次索引

        Returns:
            评估结果列表:
            [
              {
                "event_id": "...",
                "event_title": "...",
                "is_valid": true/false,
                "issues": [...],
                "reason": "..."
              }
            ]
        """
        if not events:
            return []

        self.logger.info(
            f"🔍 批次 {batch_index}: 开始 Critic 评估 - "
            f"共 {len(events)} 个事件"
        )

        # 格式化事件和实体
        events_text = self._format_events_for_evaluation(events)

        # 格式化实体类型定义
        entity_types_text = self._format_entity_types()

        # 截取原文摘要
        content_summary = original_content[:1000] if len(original_content) > 1000 else original_content

        # 使用 PromptManager 加载模板
        prompt = self.prompt_manager.render(
            "critic_evaluation",
            entity_types=entity_types_text,
            events_data=events_text,
            original_content=content_summary
        )

        # 定义 schema
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "event_title": {"type": "string"},
                    "is_invalid": {"type": "boolean"},
                    "issues": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "description": {"type": "string"},
                                "entity_info": {"type": "object"},
                                "duplicate_with": {"type": "string"},
                            },
                            "required": ["type", "description"],
                        },
                    },
                    "reason": {"type": "string"},
                },
                "required": ["event_id", "event_title", "is_invalid", "issues", "reason"],
            },
        }

        try:
            # 调用 LLM 评估
            result = await self.llm_client.chat_with_schema(
                [LLMMessage(role=LLMRole.USER, content=prompt)],
                response_schema=schema,
                temperature=0.1,
                max_tokens=2000,
            )

            evaluations = result if isinstance(result, list) else []

            # 统计评估结果
            valid_count = sum(1 for e in evaluations if not e.get("is_invalid", True))
            invalid_count = len(evaluations) - valid_count

            self.logger.info(
                f"✅ 批次 {batch_index}: Critic 评估完成 - "
                f"有效 {valid_count} 个, 有问题 {invalid_count} 个"
            )

            return evaluations

        except Exception as e:
            self.logger.error(
                f"❌ 批次 {batch_index}: Critic 评估失败 - {e}",
                exc_info=True,
            )
            # 失败时返回空列表，不影响后续流程
            return []

    def _format_events_for_evaluation(self, events: List[Any]) -> str:
        """
        格式化事件为可读文本用于评估

        Returns:
            格式化的文本
        """
        lines = []

        for idx, event in enumerate(events, 1):
            lines.append(f"\n## 事件 {idx}: {event.title}")
            lines.append(f"**ID**: {event.id}")
            lines.append(f"**摘要**: {event.summary}")
            lines.append(f"**内容**: {event.content[:200]}...")

            # 提取实体
            raw_entities = event.extra_data.get("raw_entities", {})
            if raw_entities:
                lines.append(f"**实体**:")
                for entity_type, entity_list in raw_entities.items():
                    if entity_list:
                        lines.append(f"  - {entity_type}:")
                        for entity in entity_list[:5]:  # 限制显示数量
                            name = entity.get("name", "")
                            desc = entity.get("description", "")
                            lines.append(f"    * {name}: {desc}")
                        if len(entity_list) > 5:
                            lines.append(f"    ... (还有 {len(entity_list) - 5} 个)")

            lines.append("")  # 空行分隔

        return "\n".join(lines)

    def _format_entity_types(self) -> str:
        """
        格式化实体类型定义

        Returns:
            格式化的文本
        """
        lines = []

        for entity_type in self.entity_types:
            lines.append(f"\n## {entity_type.name}")
            lines.append(f"**描述**: {entity_type.description}")
            if hasattr(entity_type, "examples") and entity_type.examples:
                lines.append(f"**示例**: {', '.join(entity_type.examples)}")

        return "\n".join(lines)
