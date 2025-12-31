"""
事项处理器 (Multi-Agent 版本)

继承自 EventProcessor,增加 LLM 评估层
"""

from typing import List
from dataflow.core.ai.base import BaseLLMClient
from dataflow.core.prompt.manager import PromptManager
from dataflow.modules.extract.config import ExtractConfig
from dataflow.modules.extract.processor import EventProcessor
from dataflow.modules.extract.Critic import EventCritic
from dataflow.modules.extract.Filter import EventFilter
from dataflow.db.models import SourceChunk, SourceEvent
from dataflow.utils import get_logger

logger = get_logger("extract.processor_with_agent")


class EventProcessorWithAgent(EventProcessor):
    """
    事项处理器 (Multi-Agent 版本)

    在原有提取逻辑基础上，增加 Critic 评估层和 Filter 过滤层
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        prompt_manager: PromptManager,
        config: ExtractConfig,
    ):
        """
        初始化处理器

        Args:
            llm_client: LLM客户端
            prompt_manager: 提示词管理器
            config: 提取配置
        """
        # 调用父类初始化
        super().__init__(llm_client, prompt_manager, config)

        # 🆕 Multi-Agent 评估器和过滤器 (延迟加载)
        self._critic = None
        self._filter = None

        self.logger = logger

    def _get_critic(self) -> EventCritic:
        """获取 Critic 评估器 (懒加载)"""
        if self._critic is None:
            self._critic = EventCritic(
                self.llm_client,
                self.entity_types,
            )
        return self._critic

    def _get_filter(self) -> EventFilter:
        """获取 Filter 过滤器 (懒加载)"""
        if self._filter is None:
            self._filter = EventFilter()
        return self._filter

    async def extract_events_without_entities(
        self,
        sections: List[SourceChunk],
        batch_index: int,
    ) -> List[SourceEvent]:
        """
        阶段1: 提取事项 (Multi-Agent 版本)

        流程:
        1. Round 1: 粗提取 (调用父类方法)
        2. Round 2: Critic 评估
        3. Round 3: Filter 过滤和修正
        4. 返回最终事项

        Args:
            sections: 来源片段列表
            batch_index: 批次索引

        Returns:
            不含实体关联的事项列表
        """
        # ========== Round 1: 粗提取 (复用父类逻辑) ==========
        self.logger.info(f"📦 批次 {batch_index}: Round 1 - 粗提取")

        events = await super().extract_events_without_entities(sections, batch_index)

        if not events:
            return events

        # ========== Round 2: Critic 评估 ==========
        if self.config.enable_llm_evaluation:
            self.logger.info(f"🔍 批次 {batch_index}: Round 2 - Critic 评估")

            # 提取原文用于评估上下文
            content = "\n".join([s.content for s in sections])

            # Critic 评估
            critic = self._get_critic()
            evaluations = await critic.evaluate_events(events, content, batch_index)

            # ========== Round 3: Filter 过滤和修正 ==========
            self.logger.info(f"🔧 批次 {batch_index}: Round 3 - Filter 过滤")

            filter_layer = self._get_filter()
            events = filter_layer.apply_evaluations(events, evaluations, batch_index)
        else:
            self.logger.debug(
                f"批次 {batch_index}: Critic 评估已禁用 (enable_llm_evaluation=False)"
            )

        return events
