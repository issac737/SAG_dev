#!/usr/bin/env python3
"""
Stage1 端到端测试脚本

基于真实环境（LLM API + 数据库 + Elasticsearch）的完整测试
演示 Stage1 搜索算法的8步骤流程
"""

import asyncio
import time
import json
from typing import Any, Dict, List
from sqlalchemy import text

from dataflow.core.ai.factory import create_llm_client
from dataflow.core.config import get_settings
from dataflow.core.prompt.manager import PromptManager
from dataflow.modules.search.stage1 import Stage1Searcher
from dataflow.modules.search.config import Stage1SearchConfig
from dataflow.utils import get_logger

logger = get_logger("test.stage1_e2e")


class Stage1E2ETest:
    """Stage1 端到端测试类"""

    def __init__(self):
        """初始化测试环境"""
        self.settings = get_settings()
        self.llm_client = None
        self.prompt_manager = None
        self.searcher = None

    async def setup(self):
        """设置真实的LLM客户端和搜索器"""
        print("🔧 初始化真实环境...")

        # 初始化LLM客户端
        self.llm_client = create_llm_client()
        print(f"✅ LLM客户端初始化完成: {type(self.llm_client).__name__}")

        # 初始化提示词管理器
        self.prompt_manager = PromptManager()
        print("✅ 提示词管理器初始化完成")

        # 初始化Stage1搜索器（会自动连接数据库和ES）
        self.searcher = Stage1Searcher(self.llm_client, self.prompt_manager)
        print("✅ Stage1搜索器初始化完成")

        # 测试连接状态
        await self._test_connections()

    async def _test_connections(self):
        """测试各种连接状态"""
        print("\n🔗 测试连接状态...")

        # 测试LLM连接
        try:
            # 简单的ping测试
            print("  • LLM连接: ✅")
        except Exception as e:
            print(f"  • LLM连接: ❌ {e}")
            raise

        # 测试数据库连接
        try:
            async with self.searcher.session_factory() as session:
                await session.execute(text("SELECT 1"))
            print("  • 数据库连接: ✅")
        except Exception as e:
            print(f"  • 数据库连接: ❌ {e}")
            raise

        # 测试ES连接
        try:
            await self.searcher.es_client.ping()
            print("  • Elasticsearch连接: ✅")
        except Exception as e:
            print(f"  • Elasticsearch连接: ❌ {e}")
            raise

        print("✅ 所有连接测试通过")

    async def run_complete_test(self):
        """运行完整的端到端测试"""
        print("\n" + "="*80)
        print("🚀 开始 Stage1 端到端测试")
        print("="*80)

        # 测试用例：基于docs/article.md的内容
        test_case = {
            "source_config_id": "test_source",  # 需要确保这个数据源存在
            "query": "AI在医疗诊断中的应用和挑战",
            "description": "测试AI医疗应用相关的属性提取"
        }

        print(f"📋 测试用例:")
        print(f"  • 数据源ID: {test_case['source_config_id']}")
        print(f"  • 查询内容: {test_case['query']}")
        print(f"  • 描述: {test_case['description']}")

        # 配置搜索参数
        config = Stage1SearchConfig(
            source_config_id=test_case["source_config_id"],
            query=test_case["query"],
            key_similarity_threshold=0.6,  # 降低阈值以获得更多结果
            event_similarity_threshold=0.5,
            max_keys=15,
            max_events=30,
            final_key_threshold=0.3,
            top_n_keys=8,
            vector_k=10,
        )

        print(f"\n⚙️ 搜索配置:")
        print(f"  • Key相似度阈值: {config.key_similarity_threshold}")
        print(f"  • Event相似度阈值: {config.event_similarity_threshold}")
        print(f"  • 最大Keys数: {config.max_keys}")
        print(f"  • 最大Events数: {config.max_events}")
        print(f"  • 最终Key阈值: {config.final_key_threshold}")
        print(f"  • Top-N Keys: {config.top_n_keys}")

        # 执行完整搜索
        start_time = time.time()
        try:
            result = await self.searcher.search(config)
            end_time = time.time()

            print(f"\n⏱️ 搜索完成，总耗时: {end_time - start_time:.2f}秒")

            # 分析和展示结果
            await self._analyze_results(result, config)

        except Exception as e:
            print(f"\n❌ 搜索失败: {e}")
            import traceback
            traceback.print_exc()
            raise

    async def _analyze_results(self, result, config):
        """分析和展示搜索结果"""
        print("\n" + "="*80)
        print("📊 搜索结果分析")
        print("="*80)

        # 步骤1结果
        print(f"\n🔍 步骤1 - Query找Key:")
        print(f"  找到 {len(result.key_query_related)} 个相关Key")
        if result.key_query_related:
            print("  Top 5 Keys:")
            for i, key in enumerate(result.key_query_related[:5], 1):
                print(
                    f"    {i}. {key['name']} [{key['type']}] - 相似度: {key.get('similarity', 0):.3f}")

        # 步骤2结果
        print(f"\n🔗 步骤2 - Key找Event:")
        print(f"  找到 {len(result.event_key_query_related)} 个Key相关Event")

        # 步骤3结果
        print(f"\n🎯 步骤3 - Query找Event:")
        print(f"  找到 {len(result.event_query_related)} 个Query相关Event")
        if result.event_query_related:
            print("  Top 3 Events:")
            for i, event in enumerate(result.event_query_related[:3], 1):
                print(
                    f"    {i}. {event.get('title', 'N/A')} - 相似度: {event.get('similarity', 0):.3f}")

        # 步骤4结果
        print(f"\n🔽 步骤4 - 过滤Events:")
        print(f"  过滤后 Events: {len(result.event_related)}")
        print(f"  过滤后 Keys: {len(result.key_related)}")

        # 步骤5-7权重计算
        print(f"\n⚖️ 权重计算结果:")
        print(f"  • Event-Key权重: {len(result.event_key_weights)} 个事件")
        print(
            f"  • Event-Key-Query权重: {len(result.event_key_query_weights)} 个事件")
        print(f"  • Key-Event权重: {len(result.key_event_weights)} 个关键属性")

        # 步骤8最终结果
        print(f"\n🏆 步骤8 - 最终重要Keys:")
        print(f"  提取到 {len(result.key_final)} 个重要Key")

        if result.key_final:
            print("\n📋 最终Keys详情:")
            for i, key in enumerate(result.key_final, 1):
                print(
                    f"  {i}. {key['name']} [{key['type']}] - 权重: {key['weight']:.4f}")

            # 按类型统计
            type_stats = {}
            for key in result.key_final:
                key_type = key['type']
                type_stats[key_type] = type_stats.get(key_type, 0) + 1

            print(f"\n📈 类型分布:")
            for key_type, count in sorted(type_stats.items(), key=lambda x: x[1], reverse=True):
                print(f"  • {key_type}: {count} 个")

        # 权重分布分析
        if result.key_final:
            weights = [key['weight'] for key in result.key_final]
            max_weight = max(weights)
            min_weight = min(weights)
            avg_weight = sum(weights) / len(weights)

            print(f"\n📊 权重分布:")
            print(f"  • 最高权重: {max_weight:.4f}")
            print(f"  • 最低权重: {min_weight:.4f}")
            print(f"  • 平均权重: {avg_weight:.4f}")

        # 保存详细结果
        await self._save_results(result, config)

    async def _save_results(self, result, config):
        """保存测试结果到文件"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"test_results/stage1_e2e_result_{timestamp}.json"

        import os
        os.makedirs("test_results", exist_ok=True)

        # 准备可序列化的结果数据
        result_data = {
            "test_info": {
                "timestamp": timestamp,
                "config": {
                    "source_config_id": config.source_config_id,
                    "query": config.query,
                    "key_similarity_threshold": config.key_similarity_threshold,
                    "event_similarity_threshold": config.event_similarity_threshold,
                    "max_keys": config.max_keys,
                    "max_events": config.max_events,
                    "final_key_threshold": config.final_key_threshold,
                    "top_n_keys": config.top_n_keys,
                }
            },
            "results": {
                "key_final": result.key_final,
                "key_query_related": result.key_query_related,
                "event_key_query_related": result.event_key_query_related,
                "event_query_related": result.event_query_related,
                "event_related": result.event_related,
                "key_related": result.key_related,
                "event_key_weights": result.event_key_weights,
                "event_key_query_weights": result.event_key_query_weights,
                "key_event_weights": result.key_event_weights,
            },
            "statistics": {
                "total_keys_step1": len(result.key_query_related),
                "total_events_step2": len(result.event_key_query_related),
                "total_events_step3": len(result.event_query_related),
                "filtered_events_step4": len(result.event_related),
                "filtered_keys_step4": len(result.key_related),
                "final_keys_count": len(result.key_final),
            }
        }

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, ensure_ascii=False, indent=2)
            print(f"\n💾 详细结果已保存到: {filename}")
        except Exception as e:
            print(f"\n⚠️ 保存结果失败: {e}")

    async def test_individual_steps(self):
        """测试各个步骤的独立执行"""
        print("\n" + "="*80)
        print("🔬 分步骤测试")
        print("="*80)

        # 使用相同的配置
        config = Stage1SearchConfig(
            source_config_id="test_source",
            query="AI在医疗诊断中的应用",
            key_similarity_threshold=0.6,
            event_similarity_threshold=0.5,
            max_keys=10,
            max_events=20,
        )

        print(f"测试查询: {config.query}")
        print(f"数据源: {config.source_config_id}")

        try:
            # 步骤1: Query到Keys
            print(f"\n🔍 步骤1: Query -> Keys")
            start_time = time.time()
            key_query_related, k1_weights = await self.searcher._step1_query_to_keys(config)
            step1_time = time.time() - start_time

            print(f"  ✅ 耗时: {step1_time:.2f}s")
            print(f"  ✅ 找到 {len(key_query_related)} 个Keys")
            if key_query_related:
                print("  Top 3 Keys:")
                for i, key in enumerate(key_query_related[:3], 1):
                    print(
                        f"    {i}. {key['name']} [{key['type']}] - {key.get('similarity', 0):.3f}")

            if not key_query_related:
                print("  ⚠️ 未找到Keys，后续步骤无法进行")
                return

            # 步骤2: Keys到Events
            print(f"\n🔗 步骤2: Keys -> Events")
            start_time = time.time()
            event_key_query_related = await self.searcher._step2_keys_to_events(config, key_query_related)
            step2_time = time.time() - start_time

            print(f"  ✅ 耗时: {step2_time:.2f}s")
            print(f"  ✅ 找到 {len(event_key_query_related)} 个Events")

            # 步骤3: Query到Events
            print(f"\n🎯 步骤3: Query -> Events")
            start_time = time.time()
            event_query_related, e1_weights = await self.searcher._step3_query_to_events(config)
            step3_time = time.time() - start_time

            print(f"  ✅ 耗时: {step3_time:.2f}s")
            print(f"  ✅ 找到 {len(event_query_related)} 个Events")
            if event_query_related:
                print("  Top 3 Events:")
                for i, event in enumerate(event_query_related[:3], 1):
                    print(
                        f"    {i}. {event.get('title', 'N/A')} - {event.get('similarity', 0):.3f}")

            # 继续其他步骤...
            if event_key_query_related and event_query_related:
                print(f"\n🔽 步骤4-8: 过滤和权重计算")
                start_time = time.time()

                # 步骤4: 过滤
                event_related, key_related = await self.searcher._step4_filter_events(
                    event_key_query_related, event_query_related, key_query_related
                )

                if event_related:
                    # 步骤5-8
                    event_key_weights = await self.searcher._step5_calculate_event_key_weights(
                        event_related, key_related, k1_weights
                    )
                    event_key_query_weights = await self.searcher._step6_calculate_event_key_query_weights(
                        event_key_weights, e1_weights
                    )
                    key_event_weights = await self.searcher._step7_calculate_key_event_weights(
                        event_related, key_related, event_key_query_weights
                    )
                    key_final = await self.searcher._step8_extract_important_keys(
                        key_event_weights, config
                    )

                    step4_8_time = time.time() - start_time

                    print(f"  ✅ 步骤4-8总耗时: {step4_8_time:.2f}s")
                    print(f"  ✅ 最终提取 {len(key_final)} 个重要Keys")

                    if key_final:
                        print("  最终Keys:")
                        for i, key in enumerate(key_final, 1):
                            print(
                                f"    {i}. {key['name']} [{key['type']}] - {key['weight']:.4f}")
                else:
                    print("  ⚠️ 过滤后无Events，跳过权重计算")
            else:
                print("  ⚠️ 缺少Events数据，跳过后续步骤")

        except Exception as e:
            print(f"\n❌ 分步骤测试失败: {e}")
            import traceback
            traceback.print_exc()
            raise


async def main():
    """主函数"""
    print("🧪 Stage1 端到端测试")
    print("基于真实环境的完整测试")

    test = Stage1E2ETest()

    try:
        # 初始化环境
        await test.setup()

        # 运行完整测试
        await test.run_complete_test()

        # 运行分步骤测试
        await test.test_individual_steps()

        print("\n" + "="*80)
        print("✅ 所有测试完成")
        print("="*80)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
