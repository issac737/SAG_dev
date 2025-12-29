"""
并发引擎演示

展示如何安全地并发运行多个 DataFlow 引擎实例
"""

import asyncio
import time

from dataflow import DataFlowEngine, ModelConfig


# ============================================================================
# 示例 1: 基础并发
# ============================================================================


def example_basic_concurrent():
    """基础并发：创建多个使用不同配置的引擎"""
    print("\n=== 示例 1: 基础并发 ===\n")

    # 引擎1：使用 OpenAI sophnet/Qwen3-30B-A3B-Thinking-2507
    engine1 = DataFlowEngine(
        model_config=ModelConfig(
            api_key="sk-openai-key-1",
            model="sophnet/Qwen3-30B-A3B-Thinking-2507",
            base_url="https://api.openai.com/v1",
        ),
        source_config_id="source-gpt4",
        auto_setup_logging=False,
    )

    # 引擎2：使用 GPT-3.5 Turbo
    engine2 = DataFlowEngine(
        model_config=ModelConfig(
            api_key="sk-openai-key-2",
            model="gpt-3.5-turbo",
            base_url="https://api.openai.com/v1",
        ),
        source_config_id="source-gpt35",
        auto_setup_logging=False,
    )

    # 引擎3：使用自定义中转API
    engine3 = DataFlowEngine(
        model_config=ModelConfig(
            api_key="sk-custom-key",
            model="custom-model",
            base_url="https://custom-api.example.com/v1",
        ),
        source_config_id="source-custom",
        auto_setup_logging=False,
    )

    # 验证配置独立
    print(f"✓ 引擎1 使用: {engine1.model_config.model} @ {engine1.model_config.base_url}")
    print(f"✓ 引擎2 使用: {engine2.model_config.model} @ {engine2.model_config.base_url}")
    print(f"✓ 引擎3 使用: {engine3.model_config.model} @ {engine3.model_config.base_url}")
    print("\n所有引擎配置独立，互不干扰！")


# ============================================================================
# 示例 2: 异步并发执行
# ============================================================================


async def example_async_concurrent():
    """异步并发：同时运行多个引擎任务"""
    print("\n=== 示例 2: 异步并发执行 ===\n")

    async def run_engine_task(engine_id: int):
        """模拟引擎任务"""
        config = ModelConfig(
            api_key=f"sk-task-{engine_id}",
            model=f"model-{engine_id}",
            base_url=f"https://api{engine_id}.example.com",
        )

        engine = DataFlowEngine(
            model_config=config, source_config_id=f"task-{engine_id}", auto_setup_logging=False
        )

        print(f"引擎 {engine_id} 启动: {engine.model_config.model}")

        # 模拟任务执行
        await asyncio.sleep(0.1)

        print(f"引擎 {engine_id} 完成: {engine.model_config.model}")

        return engine.model_config.model

    # 并发运行5个引擎
    start_time = time.time()
    results = await asyncio.gather(*[run_engine_task(i) for i in range(5)])
    duration = time.time() - start_time

    print(f"\n✓ 并发完成 {len(results)} 个任务，耗时: {duration:.2f}秒")
    print(f"使用的模型: {results}")


# ============================================================================
# 示例 3: 批量处理不同来源
# ============================================================================


async def example_batch_processing():
    """批量处理：为不同数据源创建独立引擎"""
    print("\n=== 示例 3: 批量处理不同来源 ===\n")

    # 模拟不同的数据源和配置需求
    sources = [
        {
            "name": "技术文档",
            "source_id": "tech-docs",
            "config": ModelConfig(
                api_key="sk-tech",
                model="sophnet/Qwen3-30B-A3B-Thinking-2507",
                temperature=0.2,  # 低温度，更精确
            ),
        },
        {
            "name": "营销内容",
            "source_id": "marketing",
            "config": ModelConfig(
                api_key="sk-marketing",
                model="gpt-3.5-turbo",
                temperature=0.7,  # 高温度，更有创意
            ),
        },
        {
            "name": "客户反馈",
            "source_id": "feedback",
            "config": ModelConfig(
                api_key="sk-feedback",
                model="sophnet/Qwen3-30B-A3B-Thinking-2507",
                temperature=0.3,
            ),
        },
    ]

    async def process_source(source_info):
        """处理单个数据源"""
        engine = DataFlowEngine(
            model_config=source_info["config"],
            source_config_id=source_info["source_id"],
            auto_setup_logging=False,
        )

        print(
            f"处理 {source_info['name']}: "
            f"模型={engine.model_config.model}, "
            f"温度={engine.model_config.temperature}"
        )

        # 模拟处理
        await asyncio.sleep(0.1)

        return {
            "name": source_info["name"],
            "model": engine.model_config.model,
            "temperature": engine.model_config.temperature,
        }

    # 并发处理所有来源
    results = await asyncio.gather(*[process_source(s) for s in sources])

    print("\n✓ 批量处理完成:")
    for result in results:
        print(f"  {result['name']}: {result['model']} (temperature={result['temperature']})")


# ============================================================================
# 示例 4: 多租户场景
# ============================================================================


async def example_multi_tenant():
    """多租户：不同租户使用不同的API配置"""
    print("\n=== 示例 4: 多租户场景 ===\n")

    # 模拟不同租户的配置
    tenants = {
        "tenant_a": {
            "api_key": "sk-tenant-a-key",
            "base_url": "https://tenant-a-api.example.com",
            "model": "sophnet/Qwen3-30B-A3B-Thinking-2507",
        },
        "tenant_b": {
            "api_key": "sk-tenant-b-key",
            "base_url": "https://tenant-b-api.example.com",
            "model": "gpt-3.5-turbo",
        },
        "tenant_c": {
            "api_key": "sk-tenant-c-key",
            "base_url": "https://tenant-c-api.example.com",
            "model": "claude-3",
        },
    }

    async def serve_tenant(tenant_id: str, tenant_config: dict):
        """为租户服务"""
        config = ModelConfig(
            api_key=tenant_config["api_key"],
            model=tenant_config["model"],
            base_url=tenant_config["base_url"],
        )

        engine = DataFlowEngine(
            model_config=config, source_config_id=f"tenant-{tenant_id}", auto_setup_logging=False
        )

        print(f"租户 {tenant_id}: {engine.model_config.model} @ {engine.model_config.base_url}")

        # 模拟服务
        await asyncio.sleep(0.1)

        return tenant_id

    # 并发服务所有租户
    results = await asyncio.gather(
        *[serve_tenant(tid, tconfig) for tid, tconfig in tenants.items()]
    )

    print(f"\n✓ 同时服务 {len(results)} 个租户，配置完全隔离")


# ============================================================================
# 示例 5: 负载均衡
# ============================================================================


async def example_load_balancing():
    """负载均衡：使用多个API端点分散负载"""
    print("\n=== 示例 5: 负载均衡 ===\n")

    # 多个API端点
    api_endpoints = [
        "https://api1.example.com/v1",
        "https://api2.example.com/v1",
        "https://api3.example.com/v1",
    ]

    async def process_with_endpoint(task_id: int, endpoint: str):
        """使用特定端点处理任务"""
        config = ModelConfig(
            api_key=f"sk-lb-{task_id}",
            model="sophnet/Qwen3-30B-A3B-Thinking-2507",
            base_url=endpoint,
        )

        engine = DataFlowEngine(
            model_config=config, source_config_id=f"lb-task-{task_id}", auto_setup_logging=False
        )

        print(f"任务 {task_id} 使用端点: {endpoint}")

        # 模拟处理
        await asyncio.sleep(0.1)

        return task_id

    # 将任务分配到不同端点
    tasks = []
    for i in range(9):
        endpoint = api_endpoints[i % len(api_endpoints)]  # 轮询分配
        tasks.append(process_with_endpoint(i, endpoint))

    results = await asyncio.gather(*tasks)

    print(f"\n✓ 完成 {len(results)} 个任务，负载均衡到 {len(api_endpoints)} 个端点")


# ============================================================================
# 示例 6: 高并发压力测试
# ============================================================================


async def example_stress_test():
    """压力测试：创建大量并发引擎"""
    print("\n=== 示例 6: 高并发压力测试 ===\n")

    async def create_engine(index: int):
        """创建引擎"""
        config = ModelConfig(api_key=f"sk-stress-{index}", model=f"model-{index}")

        engine = DataFlowEngine(
            model_config=config, source_config_id=f"stress-{index}", auto_setup_logging=False
        )

        # 快速验证
        assert engine.model_config.api_key == f"sk-stress-{index}"

        return index

    # 并发创建100个引擎
    print("创建 100 个并发引擎...")
    start_time = time.time()

    results = await asyncio.gather(*[create_engine(i) for i in range(100)])

    duration = time.time() - start_time

    print(f"✓ 成功创建 {len(results)} 个引擎，耗时: {duration:.2f}秒")
    print(f"平均每个引擎: {duration/len(results)*1000:.2f}ms")


# ============================================================================
# 主函数
# ============================================================================


async def main():
    """运行所有示例"""
    print("\n" + "=" * 70)
    print("DataFlow 引擎并发安全演示")
    print("=" * 70)

    # 运行示例
    example_basic_concurrent()
    await example_async_concurrent()
    await example_batch_processing()
    await example_multi_tenant()
    await example_load_balancing()
    await example_stress_test()

    print("\n" + "=" * 70)
    print("✓ 所有并发示例运行完成！")
    print("=" * 70)
    print("\n关键要点：")
    print("  1. 每个引擎实例有独立的配置")
    print("  2. 配置不会互相干扰")
    print("  3. 支持大规模并发")
    print("  4. 线程安全，可靠稳定")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n演示被中断")
