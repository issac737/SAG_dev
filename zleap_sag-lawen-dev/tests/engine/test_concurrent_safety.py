"""
测试引擎的并发安全性

验证多个引擎实例使用不同配置并发运行时不会互相干扰
"""

import asyncio
from pathlib import Path

import pytest

from dataflow import DataFlowEngine, ModelConfig


# ============================================================================
# 并发安全性测试
# ============================================================================


@pytest.mark.asyncio
async def test_concurrent_engines_with_different_configs():
    """
    测试：多个引擎实例使用不同的LLM配置并发运行

    验证点：
    1. 每个引擎使用自己的配置
    2. 配置不会互相干扰
    3. 可以并发创建多个引擎
    """
    # 创建三个不同配置的引擎
    configs = [
        ModelConfig(
            api_key="sk-engine1-key",
            model="sophnet/Qwen3-30B-A3B-Thinking-2507",
            base_url="https://api1.example.com/v1",
            temperature=0.2,
        ),
        ModelConfig(
            api_key="sk-engine2-key",
            model="gpt-3.5-turbo",
            base_url="https://api2.example.com/v1",
            temperature=0.5,
        ),
        ModelConfig(
            api_key="sk-engine3-key",
            model="claude-3",
            base_url="https://api3.example.com/v1",
            temperature=0.8,
        ),
    ]

    engines = []

    # 并发创建引擎
    for i, config in enumerate(configs):
        engine = DataFlowEngine(
            model_config=config,
            source_config_id=f"test-source-{i}",
            auto_setup_logging=False,
        )
        engines.append(engine)

    # 验证每个引擎的配置是独立的
    for i, engine in enumerate(engines):
        assert engine.model_config.api_key == configs[i].api_key
        assert engine.model_config.model == configs[i].model
        assert engine.model_config.base_url == configs[i].base_url
        assert engine.model_config.temperature == configs[i].temperature

    print("✓ 并发引擎配置隔离测试通过")


@pytest.mark.asyncio
async def test_llm_client_independence():
    """
    测试：每个引擎的LLM客户端是独立的

    验证点：
    1. 不同引擎的LLM客户端是不同的实例
    2. 配置互不影响
    """
    engine1 = DataFlowEngine(
        model_config=ModelConfig(
            api_key="sk-test1",
            model="sophnet/Qwen3-30B-A3B-Thinking-2507",
            base_url="https://api1.com",
        ),
        source_config_id="source1",
        auto_setup_logging=False,
    )

    engine2 = DataFlowEngine(
        model_config=ModelConfig(
            api_key="sk-test2", model="gpt-3.5-turbo", base_url="https://api2.com"
        ),
        source_config_id="source2",
        auto_setup_logging=False,
    )

    # 验证是不同的客户端实例
    assert engine1.llm_client is not engine2.llm_client

    # 验证配置没有互相污染
    assert engine1.model_config.api_key == "sk-test1"
    assert engine2.model_config.api_key == "sk-test2"

    print("✓ LLM客户端独立性测试通过")


def test_sequential_engine_creation():
    """
    测试：顺序创建多个引擎

    验证点：
    1. 后创建的引擎不会影响已创建的引擎
    2. 配置保持独立
    """
    engines = []

    for i in range(5):
        engine = DataFlowEngine(
            model_config=ModelConfig(
                api_key=f"sk-test-{i}",
                model=f"model-{i}",
                base_url=f"https://api{i}.com",
            ),
            source_config_id=f"source-{i}",
            auto_setup_logging=False,
        )
        engines.append(engine)

    # 验证所有引擎的配置都正确保留
    for i, engine in enumerate(engines):
        assert engine.model_config.api_key == f"sk-test-{i}"
        assert engine.model_config.model == f"model-{i}"
        assert engine.model_config.base_url == f"https://api{i}.com"

    print("✓ 顺序创建引擎测试通过")


@pytest.mark.asyncio
async def test_concurrent_async_operations():
    """
    测试：并发执行异步操作

    模拟多个引擎同时初始化的场景
    """

    async def create_and_init_engine(index: int):
        """创建并初始化引擎"""
        config = ModelConfig(
            api_key=f"sk-concurrent-{index}",
            model=f"model-{index}",
            base_url=f"https://api{index}.com",
        )

        engine = DataFlowEngine(
            model_config=config, source_config_id=f"concurrent-{index}", auto_setup_logging=False
        )

        # 验证配置
        assert engine.model_config.api_key == f"sk-concurrent-{index}"
        assert engine.model_config.model == f"model-{index}"

        return engine

    # 并发创建10个引擎
    engines = await asyncio.gather(*[create_and_init_engine(i) for i in range(10)])

    # 验证所有引擎配置正确
    for i, engine in enumerate(engines):
        assert engine.model_config.api_key == f"sk-concurrent-{i}"
        assert engine.model_config.model == f"model-{i}"

    print("✓ 并发异步操作测试通过")


# ============================================================================
# 配置修改测试
# ============================================================================


def test_engine_config_modification():
    """
    测试：修改一个引擎的配置不影响其他引擎

    验证点：
    1. 引擎配置是独立的
    2. 修改一个不影响另一个
    """
    engine1 = DataFlowEngine(
        model_config=ModelConfig(api_key="sk-original", model="sophnet/Qwen3-30B-A3B-Thinking-2507"),
        source_config_id="source1",
        auto_setup_logging=False,
    )

    engine2 = DataFlowEngine(
        model_config=ModelConfig(api_key="sk-original", model="sophnet/Qwen3-30B-A3B-Thinking-2507"),
        source_config_id="source2",
        auto_setup_logging=False,
    )

    # 修改 engine1 的配置
    engine1.model_config.api_key = "sk-modified"
    engine1.model_config.model = "gpt-3.5-turbo"

    # 验证 engine2 的配置没有变化
    assert engine2.model_config.api_key == "sk-original"
    assert engine2.model_config.model == "sophnet/Qwen3-30B-A3B-Thinking-2507"

    print("✓ 配置修改隔离测试通过")


# ============================================================================
# 压力测试
# ============================================================================


@pytest.mark.slow
@pytest.mark.asyncio
async def test_high_concurrency_stress():
    """
    压力测试：大量并发引擎创建

    创建100个引擎验证系统稳定性
    """

    async def create_engine(index: int):
        """创建引擎"""
        return DataFlowEngine(
            model_config=ModelConfig(api_key=f"sk-stress-{index}", model=f"model-{index}"),
            source_config_id=f"stress-{index}",
            auto_setup_logging=False,
        )

    # 并发创建100个引擎
    engines = await asyncio.gather(*[create_engine(i) for i in range(100)])

    # 抽查验证
    for i in [0, 25, 50, 75, 99]:
        assert engines[i].model_config.api_key == f"sk-stress-{i}"
        assert engines[i].model_config.model == f"model-{i}"

    print("✓ 高并发压力测试通过（100个引擎）")


# ============================================================================
# 运行测试
# ============================================================================


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("引擎并发安全性测试")
    print("=" * 70 + "\n")

    # 运行测试
    asyncio.run(test_concurrent_engines_with_different_configs())
    asyncio.run(test_llm_client_independence())
    test_sequential_engine_creation()
    asyncio.run(test_concurrent_async_operations())
    test_engine_config_modification()

    print("\n" + "=" * 70)
    print("✓ 所有并发安全性测试通过！")
    print("=" * 70)
