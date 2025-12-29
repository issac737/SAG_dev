"""
LLM客户端基类

定义LLM客户端的统一接口
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional

from dataflow.core.ai.models import ModelConfig, LLMMessage, LLMResponse, LLMRole
from dataflow.exceptions import LLMError, LLMTimeoutError
from dataflow.utils import get_logger

logger = get_logger("ai.llm")


class BaseLLMClient(ABC):
    """LLM客户端基类"""

    def __init__(self, config: ModelConfig) -> None:
        """
        初始化LLM客户端

        Args:
            config: LLM配置
        """
        self.config = config
        logger.info(
            "初始化%s客户端",
            config.provider.value,
            extra={"model": config.model},
        )

    @abstractmethod
    async def chat(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        聊天补全

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大输出token数
            **kwargs: 其他参数

        Returns:
            LLM响应

        Raises:
            LLMError: LLM调用失败
            LLMTimeoutError: 调用超时
        """
        ...

    @abstractmethod
    def chat_stream(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        include_reasoning: bool = False,
        **kwargs: Any,
    ) -> AsyncIterator[tuple[str, Optional[str]]]:
        """
        流式聊天补全

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大输出token数
            include_reasoning: 是否返回推理内容（reasoning_content）
            **kwargs: 其他参数

        Yields:
            元组 (content, reasoning) - content为内容片段，reasoning为推理片段（如果有）

        Raises:
            LLMError: LLM调用失败
            LLMTimeoutError: 调用超时
        """
        ...

    async def chat_with_schema(
        self,
        messages: List[LLMMessage],
        response_schema: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        结构化输出（JSON Schema）
        
        注意：不自动注入提示词，调用方需在 messages 中自行定义输出格式要求。
        本方法只负责：1. 调用 LLM  2. 解析 JSON  3. Schema 校验（如果提供）

        Args:
            messages: 消息列表（应包含 SYSTEM 定义的输出格式）
            response_schema: JSON Schema定义（用于校验，可选）
            temperature: 温度参数
            max_tokens: 最大输出token数
            **kwargs: 其他参数

        Returns:
            解析后的JSON对象

        Raises:
            LLMError: LLM调用失败或JSON格式无效
            ValidationError: 响应不符合Schema（仅当提供schema时）
        """
        import json

        # 直接调用 LLM，不注入额外提示词
        response = await self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        # 解析JSON响应
        try:
            import re
            
            # 提取JSON内容（可能被markdown代码块包裹）
            content = response.content.strip()
            
            # 使用正则表达式提取 ```json 或 ``` 代码块
            json_block_match = re.search(
                r'```(?:json)?\s*\n(.*?)\n```', 
                content, 
                re.DOTALL | re.IGNORECASE
            )
            
            if json_block_match:
                content = json_block_match.group(1).strip()
                logger.debug("从 markdown 代码块中提取 JSON")
            else:
                logger.debug("直接解析 JSON（无代码块）")

            # 解析JSON
            result = json.loads(content)

            # 如果提供了schema，进行验证
            if response_schema:
                # 尝试使用jsonschema进行严格验证
                try:
                    import jsonschema

                    jsonschema.validate(instance=result, schema=response_schema)
                    logger.debug("JSON schema validation passed")
                except ImportError:
                    # jsonschema未安装，使用简单验证
                    if "properties" in response_schema:
                        required = response_schema.get("required", [])
                        for field in required:
                            if field not in result:
                                raise ValueError(f"缺少必需字段: {field}")
                    logger.debug("JSON simple validation passed")
                except Exception as e:
                    # jsonschema验证失败
                    if type(e).__name__ == "ValidationError":
                        logger.error("JSON schema validation failed: %s", e)
                        raise LLMError(f"响应不符合Schema: {e}") from e
                    raise
            else:
                # 没有schema，只验证JSON格式（已通过json.loads）
                logger.debug("JSON format validation passed (no schema provided)")

            return result

        except json.JSONDecodeError as e:
            logger.error("JSON解析失败: %s\n内容: %s", e, response.content)
            raise LLMError(f"LLM返回的不是有效的JSON: {e}") from e
        except ValueError as e:
            logger.error("Schema验证失败: %s", e)
            raise LLMError(f"响应不符合Schema: {e}") from e

    def _prepare_messages(
        self,
        messages: List[LLMMessage],
    ) -> List[Dict[str, str]]:
        """
        准备消息列表（转换为API格式）

        Args:
            messages: 消息列表

        Returns:
            API格式的消息列表
        """
        return [msg.to_dict() for msg in messages]


class LLMRetryClient:
    """带重试机制的LLM客户端包装器"""

    def __init__(
        self,
        client: BaseLLMClient,
        max_retries: Optional[int] = None,
        retry_delay: float = 1.0,
        backoff_factor: float = 2.0,
    ) -> None:
        """
        初始化重试客户端

        Args:
            client: 基础LLM客户端
            max_retries: 最大重试次数（None则使用client配置）
            retry_delay: 初始重试延迟（秒）
            backoff_factor: 退避因子
        """
        self.client = client
        self.max_retries = max_retries or client.config.max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor

    def _should_retry(self, error: Exception) -> bool:
        """
        判断错误是否应该重试

        Args:
            error: 异常对象

        Returns:
            True表示应该重试，False表示不应该重试
        """
        # 超时错误不重试（网络问题，重试可能继续超时）
        if isinstance(error, LLMTimeoutError):
            return False

        # 速率限制错误应该重试
        from dataflow.exceptions import LLMRateLimitError

        if isinstance(error, LLMRateLimitError):
            return True

        # 其他LLM错误可以重试
        if isinstance(error, LLMError):
            return True

        # 未知错误默认不重试
        return False

    async def chat(
        self,
        messages: List[LLMMessage],
        **kwargs: Any,
    ) -> LLMResponse:
        """
        带重试的聊天补全

        实现指数退避重试策略：
        - 第1次失败：等待1秒
        - 第2次失败：等待2秒
        - 第3次失败：等待4秒

        根据错误类型智能决定是否重试：
        - 超时错误：不重试
        - 速率限制：重试
        - 其他LLM错误：重试
        """
        last_error: Optional[Exception] = None
        delay = self.retry_delay

        for attempt in range(self.max_retries + 1):
            try:
                return await self.client.chat(messages, **kwargs)
            except Exception as e:
                last_error = e

                # 判断是否应该重试
                if not self._should_retry(e):
                    logger.error("遇到不可重试错误: %s", e)
                    raise

                if attempt < self.max_retries:
                    logger.warning(
                        "LLM调用失败，%s秒后重试 (尝试 %d/%d)",
                        delay,
                        attempt + 1,
                        self.max_retries,
                        extra={"error": str(e), "error_type": type(e).__name__},
                    )
                    await asyncio.sleep(delay)
                    delay *= self.backoff_factor
                else:
                    logger.error(
                        "LLM调用失败，已重试%d次",
                        self.max_retries,
                        exc_info=True,
                    )

        raise LLMError(f"LLM调用失败，已重试{self.max_retries}次") from last_error

    async def chat_stream(
        self,
        messages: List[LLMMessage],
        **kwargs: Any,
    ) -> AsyncIterator[tuple[str, Optional[str]]]:
        """
        流式调用（不重试）

        流式调用失败时无法重试，直接抛出异常

        Yields:
            元组 (content, reasoning) - content为内容片段，reasoning为推理片段（如果有）
        """
        async for chunk in self.client.chat_stream(messages, **kwargs):
            yield chunk

    async def chat_with_schema(
        self,
        messages: List[LLMMessage],
        response_schema: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        带重试的结构化输出

        根据错误类型智能决定是否重试
        """
        last_error: Optional[Exception] = None
        delay = self.retry_delay

        for attempt in range(self.max_retries + 1):
            try:
                return await self.client.chat_with_schema(
                    messages,
                    response_schema,
                    **kwargs,
                )
            except Exception as e:
                last_error = e

                # 判断是否应该重试
                if not self._should_retry(e):
                    logger.error("遇到不可重试错误: %s", e)
                    raise

                if attempt < self.max_retries:
                    logger.warning(
                        "结构化输出失败，%s秒后重试 (尝试 %d/%d)",
                        delay,
                        attempt + 1,
                        self.max_retries,
                        extra={"error": str(e), "error_type": type(e).__name__},
                    )
                    await asyncio.sleep(delay)
                    delay *= self.backoff_factor

        raise LLMError(f"结构化输出失败，已重试{self.max_retries}次") from last_error
