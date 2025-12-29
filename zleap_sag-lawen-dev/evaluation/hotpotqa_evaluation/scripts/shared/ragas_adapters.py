"""
RAGAs 模型适配器
将项目的 LLM 和 Embedding 配置适配到 RAGAs 评估框架
"""
from typing import Optional
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from dataflow.core.config import get_settings


def create_ragas_llm(
    model: Optional[str] = None,
    temperature: float = 0.0,
    timeout: Optional[int] = None,
    verbose: bool = True
) -> ChatOpenAI:
    """
    创建用于 RAGAs 评估的 LLM 客户端

    使用项目配置的 LLM API，支持中转 API 和 OpenAI 官方 API

    Args:
        model: 模型名称（默认从配置读取）
        temperature: 温度参数（默认 0.0，评估时需要确定性）
        timeout: 超时时间（默认从配置读取）
        verbose: 是否打印配置信息

    Returns:
        LangChain ChatOpenAI 实例

    Example:
        >>> from shared.ragas_adapters import create_ragas_llm, create_ragas_embeddings
        >>>
        >>> # 创建模型实例
        >>> llm = create_ragas_llm()
        >>> embeddings = create_ragas_embeddings()
        >>>
        >>> # 传递给 RAGAs evaluate()
        >>> results = evaluate(
        ...     dataset,
        ...     metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        ...     llm=llm,
        ...     embeddings=embeddings
        ... )
    """
    settings = get_settings()

    # 使用项目配置
    model = model or settings.llm_model
    base_url = settings.llm_base_url
    api_key = settings.llm_api_key
    timeout = timeout or settings.llm_timeout

    if verbose:
        print("=" * 60)
        print("🤖 RAGAs LLM 配置")
        print("=" * 60)
        print(f"  模型:      {model}")
        print(f"  API 地址:  {base_url or 'OpenAI 官方 API'}")
        print(f"  温度:      {temperature}")
        print(f"  超时:      {timeout}s")
        print("=" * 60)
        print()

    # 创建 LangChain ChatOpenAI 客户端
    # 注意：langchain-openai 使用不同的参数名
    client_kwargs = {
        "model": model,
        "api_key": api_key,
        "temperature": temperature,
        "timeout": timeout,
        "max_retries": settings.llm_max_retries,
    }

    # 如果有自定义 base_url，添加配置
    if base_url:
        client_kwargs["base_url"] = base_url

    llm = ChatOpenAI(**client_kwargs)

    return llm


def create_ragas_embeddings(
    model: Optional[str] = None,
    dimensions: Optional[int] = None,
    verbose: bool = True
) -> OpenAIEmbeddings:
    """
    创建用于 RAGAs 评估的 Embedding 客户端

    使用项目配置的 Embedding API，支持中转 API 和 OpenAI 官方 API

    Args:
        model: 模型名称（默认从配置读取）
        dimensions: 向量维度（可选，某些模型支持自定义维度）
        verbose: 是否打印配置信息

    Returns:
        LangChain OpenAIEmbeddings 实例

    Example:
        >>> embeddings = create_ragas_embeddings()
        >>> # 传递给 RAGAs evaluate()
        >>> results = evaluate(dataset, metrics=[...], embeddings=embeddings)
    """
    settings = get_settings()

    # 使用项目配置
    model = model or settings.embedding_model_name
    dimensions = dimensions or settings.embedding_dimensions
    base_url = settings.embedding_base_url or settings.llm_base_url
    api_key = settings.embedding_api_key or settings.llm_api_key

    if verbose:
        print("=" * 60)
        print("🎯 RAGAs Embeddings 配置")
        print("=" * 60)
        print(f"  模型:      {model}")
        print(f"  API 地址:  {base_url or 'OpenAI 官方 API'}")
        if dimensions:
            print(f"  向量维度:  {dimensions}")
        else:
            # 根据模型提示默认维度
            default_dims = {
                "Qwen/Qwen3-Embedding-0.6B": 1536,
                "text-embedding-3-large": 3072,
                "text-embedding-ada-002": 1536,
            }
            print(f"  向量维度:  {default_dims.get(model, '模型默认')}")
        print("=" * 60)
        print()

    # 创建 LangChain OpenAIEmbeddings 客户端
    client_kwargs = {
        "model": model,
        "api_key": api_key,
    }

    # 如果有自定义 base_url，添加配置
    if base_url:
        client_kwargs["base_url"] = base_url

    # 如果指定了维度，添加配置（仅 text-embedding-3-* 系列支持）
    if dimensions:
        client_kwargs["dimensions"] = dimensions

    embeddings = OpenAIEmbeddings(**client_kwargs)

    return embeddings


def print_model_config():
    """
    打印当前项目的模型配置（用于调试）
    """
    settings = get_settings()

    print("\n" + "=" * 60)
    print("📋 当前项目模型配置")
    print("=" * 60)
    print("\n[LLM 配置]")
    print(f"  模型:        {settings.llm_model}")
    print(f"  API Key:     {settings.llm_api_key[:20]}..." if settings.llm_api_key else "  API Key:     未配置")
    print(f"  Base URL:    {settings.llm_base_url or 'OpenAI 官方 API'}")
    print(f"  超时:        {settings.llm_timeout}s")
    print(f"  最大重试:    {settings.llm_max_retries}")

    print("\n[Embedding 配置]")
    print(f"  模型:        {settings.embedding_model_name}")
    print(f"  API Key:     {settings.embedding_api_key[:20] + '...' if settings.embedding_api_key else '(使用 LLM API Key)'}")
    print(f"  Base URL:    {settings.embedding_base_url or settings.llm_base_url or 'OpenAI 官方 API'}")
    if settings.embedding_dimensions:
        print(f"  向量维度:    {settings.embedding_dimensions}")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    # 测试脚本
    print_model_config()

    # 创建实例
    llm = create_ragas_llm()
    embeddings = create_ragas_embeddings()

    print("✅ 模型实例创建成功！")
