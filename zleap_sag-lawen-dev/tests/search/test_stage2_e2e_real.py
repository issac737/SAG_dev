#!/usr/bin/env python3
"""
Stage2 搜索端到端测试脚本

基于真实环境（LLM API + 数据库 + Elasticsearch）的完整测试
演示 Stage2 多跳循环搜索算法的正确性
"""

import asyncio
from dataflow.core.ai import get_llm_client
from dataflow.core.prompt.manager import PromptManager
from dataflow.modules.search.config import SearchConfig, SearchMode
from dataflow.modules.search.stage1 import Stage1Searcher
from dataflow.modules.search.stage2 import Stage2Searcher
from dataflow.modules.search.stage3 import Stage3Searcher
from dataflow.utils import get_logger
from dataflow.utils.logger import setup_logging
logger = get_logger("test.stage2_e2e")

setup_logging(level="INFO")

class Stage2E2ETest:
    """Stage2 端到端测试类"""

    def __init__(self):
        """初始化测试环境"""
        self.llm_client = None
        self.prompt_manager = None
        self.stage1_searcher = None
        self.stage2_searcher = None
        self.stage3_searcher = None
        self.config = None

    async def setup(self):
        """设置真实的LLM客户端和搜索器"""
        print("🔧 初始化Stage2测试环境...")

        # 初始化LLM客户端
        self.llm_client = get_llm_client()
        print(f"✅ LLM客户端初始化完成: {type(self.llm_client).__name__}")

        # 初始化提示词管理器
        self.prompt_manager = PromptManager()
        print("✅ 提示词管理器初始化完成")

        # 初始化Stage1搜索器
        self.stage1_searcher = Stage1Searcher(self.llm_client, self.prompt_manager)
        print("✅ Stage1搜索器初始化完成")

        # 初始化Stage2搜索器
        self.stage2_searcher = Stage2Searcher(
            self.llm_client,
            self.prompt_manager,
            self.stage1_searcher
        )
        print("✅ Stage2搜索器初始化完成")

        # 初始化Stage3搜索器
        self.stage3_searcher = Stage3Searcher(self.llm_client)
        print("✅ Stage3搜索器初始化完成")

        print("🎯 Stage2测试环境准备完成！\n")

    async def cleanup(self):
        """清理测试资源"""
        print("🧹 清理测试资源...")

        try:
            # 清理LLM客户端
            if self.llm_client:
                if hasattr(self.llm_client, 'client') and hasattr(self.llm_client.client, 'close'):
                    await self.llm_client.client.close()
                    print("✅ LLM客户端已关闭")
                elif hasattr(self.llm_client, 'close'):
                    await self.llm_client.close()
                    print("✅ LLM客户端已关闭")

            # 清理Elasticsearch客户端
            if self.stage1_searcher and hasattr(self.stage1_searcher, 'es_client'):
                await self.stage1_searcher.es_client.close()
                print("✅ Stage1 Elasticsearch客户端已关闭")

            if self.stage2_searcher and hasattr(self.stage2_searcher, 'es_client'):
                await self.stage2_searcher.es_client.close()
                print("✅ Stage2 Elasticsearch客户端已关闭")

            if self.stage3_searcher and hasattr(self.stage3_searcher, 'es_client'):
                await self.stage3_searcher.es_client.close()
                print("✅ Stage3 Elasticsearch客户端已关闭")

            # 清理数据库连接
            from dataflow.db.base import close_database
            try:
                await close_database()
                print("✅ 数据库连接已关闭")
            except Exception as db_error:
                print(f"⚠️ 数据库连接关闭警告: {db_error}")

        except Exception as cleanup_error:
            print(f"⚠️ 清理资源时出错: {cleanup_error}")

        print("✅ 测试资源清理完成")

    async def test_stage2_search(self):
        """测试Stage2搜索功能"""

        # 配置搜索参数
        self.config = SearchConfig(
            source_config_id="1b89c57b-7e41-495a-ad4a-9362f7295c2b",  # 使用实际存在的数据源
        query="混合专家模型",
        mode=SearchMode.NORMAL,  # 使用普通模式（LLM属性抽取）

        # Stage1参数
        key_similarity_threshold=0.4,  # 降低阈值以获得更多结果
        event_similarity_threshold=0.5,
        max_keys=15,
        max_events=30,
        final_key_threshold=0.3,
        top_n_keys=8,

        # Stage2参数
        enable_stage2=True,
        max_jumps=3,
        stage2_event_threshold=0.3,
        stage2_convergence_threshold=0.15,
        stage2_min_events=3,
        stage2_max_events=50,

        #stage3参数
        stage3_vector_k=15,         # KNN搜索返回15个结果  
        )

        try:
            print("🚀 === 开始Stage2搜索测试 ===")

            # 执行Stage2搜索
            result = await self.stage2_searcher.search(self.config)

            # 输出结果
            print("📊 === Stage2搜索结果 ===")
            print(f"  • 实际跳跃次数: {result.total_jumps}")
            print(f"  • 是否收敛: {result.convergence_reached}")
            print(f"  • 最终keys数量: {len(result.key_final)}")

            # 显示最终keys
            print("\n🔑 === 最终重要Keys ===")
            for i, key in enumerate(result.key_final, 1):
                print(f"  {i}. {key['name']} [{key['type']}] - 权重: {key['weight']:.4f}, 步骤: {key['steps']}")

            # 显示跳跃过程
            print("\n🔄 === 跳跃过程 ===")
            for jump_result in result.jump_results:
                print(f"  第{jump_result['jump']}跳: "
                      f"发现事件{jump_result['events_found']}个, "
                      f"相似事件{jump_result['events_similar']}个, "
                      f"keys数量{jump_result['keys_count']}, "
                      f"总权重{jump_result['total_weight']:.4f}, "
                      f"权重变化{jump_result['weight_change']:.4f}")

            # 显示权重演化
            print("\n📈 === 权重演化 ===")
            for jump, weights in result.weight_evolution.items():
                top_keys = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:3]
                top_keys_str = ", ".join([f"{k}:{v:.3f}" for k, v in top_keys])
                print(f"  第{jump}跳 Top3: {top_keys_str}")

            print("✅ === Stage2搜索测试完成 ===")

            return result

        except Exception as e:
            print(f"❌ Stage2搜索测试失败: {e}")
            logger.error(f"Stage2搜索测试失败: {e}", exc_info=True)
            raise

    async def test_stage2_with_single_key(self):
        """测试使用Stage1单个key作为种子的Stage2搜索"""

        # 配置搜索参数
        self.config = SearchConfig(
            source_config_id="1b89c57b-7e41-495a-ad4a-9362f7295c2b",  # 使用实际存在的数据源
            query="混合专家模型",
            mode=SearchMode.NORMAL,

            # Stage1参数
            key_similarity_threshold=0.4,
            event_similarity_threshold=0.6,
            max_keys=10,
            max_events=25,
            final_key_threshold=0.4,
            top_n_keys=8,  # 获取较多的keys以便选择

            # Stage2参数
            enable_stage2=True,
            max_jumps=3,
            stage2_event_threshold=0.2,
            stage2_convergence_threshold=0.1,
            #stage3参数
 
            stage3_vector_k=15,         # KNN搜索返回15个结果

        )

        try:
            print("🚀 === 开始Stage2单Key种子测试 ===")

            # 步骤1: 执行Stage1获取候选keys
            print("步骤1: 执行Stage1搜索获取候选keys")
            stage1_result = await self.stage1_searcher.search(self.config)

            print(f"✅ Stage1完成，找到 {len(stage1_result.key_final)} 个候选keys:")
            for i, key in enumerate(stage1_result.key_final, 1):
                print(f"  {i}. {key['name']} [{key['type']}] - 权重: {key['weight']:.4f}")

            if len(stage1_result.key_final) == 0:
                print("❌ Stage1没有产生keys，无法进行测试")
                return None

            # 步骤2: 选择权重最高的key作为种子
            seed_key = max(stage1_result.key_final, key=lambda x: x['weight'])
            print(f"\n🎯 步骤2: 选择种子key")
            print(f"  🌱 种子key: {seed_key['name']} [{seed_key['type']}] - 权重: {seed_key['weight']:.4f}")

            # 步骤3: 创建只包含种子key的虚拟Stage1结果
            from dataflow.modules.search.stage1 import Stage1Result
            seed_stage1_result = Stage1Result(
                key_final=[seed_key],  # 只包含种子key
                key_query_related=[],
                event_key_query_related=[],
                event_query_related=[],
                event_related=[],
                key_related=[],
                event_key_weights={},
                event_key_query_weights={},
                key_event_weights={},
            )

            # 步骤4: 执行Stage2扩展
            print(f"\n🔄 步骤3: 基于种子key '{seed_key['name']}' 执行Stage2扩展")
            stage2_result = await self.stage2_searcher.search(self.config, seed_stage1_result)

            # 步骤5: 分析扩展效果
            print(f"\n📊 === 单Key扩展效果分析 ===")
            print(f"  • 种子key: {seed_key['name']} (权重: {seed_key['weight']:.4f})")
            print(f"  • 扩展后总keys: {len(stage2_result.key_final)} 个")
            print(f"  • 扩展倍数: {len(stage2_result.key_final)}x")

            # 显示扩展结果
            if stage2_result.key_final:
                print(f"\n🔑 === Stage2扩展结果 ===")
                for i, key in enumerate(stage2_result.key_final, 1):
                    is_seed = key['key_id'] == seed_key['key_id']
                    seed_marker = "🌱" if is_seed else "🆕"
                    print(f"  {i}. {seed_marker} {key['name']} [{key['type']}] - "
                          f"权重: {key['weight']:.4f}, 发现步骤: {key['steps']}")

            # 显示跳跃过程
            print(f"\n🔄 === 多跳扩展过程 ===")
            for jump_result in stage2_result.jump_results:
                print(f"  第{jump_result['jump']}跳: "
                      f"发现事件{jump_result['events_found']}个, "
                      f"相似事件{jump_result['events_similar']}个, "
                      f"keys数量{jump_result['keys_count']}, "
                      f"总权重{jump_result['total_weight']:.4f}, "
                      f"权重变化{jump_result['weight_change']:.4f}")

            print(f"\n✅ === Stage2单Key种子测试完成 ===")
            return stage2_result

        except Exception as e:
            print(f"❌ Stage2单Key种子测试失败: {e}")
            logger.error(f"Stage2单Key种子测试失败: {e}", exc_info=True)
            raise

    async def test_stage2_key_expansion(self):
        """测试Stage2从Stage1 keys开始的扩展效果"""

        print("🚀 === 开始Stage2 Key扩展测试 ===")

        # 配置搜索参数
        self.config = SearchConfig(
            source_config_id="ccf99a1e-6e67-452e-be04-53e0117c05a9",  # 使用实际存在的数据源
            query="AI技术在医疗健康领域的创新应用",
            mode=SearchMode.NORMAL,

            # Stage1参数 - 生成高质量的初始keys
            key_similarity_threshold=0.5,
            event_similarity_threshold=0.6,
            max_keys=8,
            max_events=20,
            final_key_threshold=0.5,
            top_n_keys=5,  # 只取top 5 keys作为种子

            # Stage2参数 - 优化配置以观察扩展效果
            enable_stage2=True,
            max_jumps=3,
            stage2_event_threshold=0.15,  # 较低的相似度阈值
            stage2_convergence_threshold=0.08,
            stage2_min_events=2,
            stage2_max_events=30,
            # stage3参数
    
            stage3_vector_k=15,         # KNN搜索返回15个结果
  
        )

        try:
            # 步骤1: 执行Stage1获得种子keys
            print("📝 步骤1: 执行Stage1搜索获取种子keys")
            stage1_result = await self.stage1_searcher.search(self.config)

            print(f"✅ Stage1完成，获得 {len(stage1_result.key_final)} 个种子keys:")
            for i, key in enumerate(stage1_result.key_final, 1):
                print(f"  🏷️  种子{i}: {key['name']} [{key['type']}] - 权重: {key['weight']:.4f}")

            if len(stage1_result.key_final) < 2:
                print("❌ Stage1产生的keys数量太少，无法进行有效扩展测试")
                return None

            # 步骤2: 执行Stage2扩展
            print(f"\n🔄 步骤2: 基于这 {len(stage1_result.key_final)} 个种子keys执行Stage2扩展")
            stage2_result = await self.stage2_searcher.search(self.config, stage1_result)

            # 步骤3: 分析扩展效果
            print(f"\n📊 === 扩展效果分析 ===")

            # 比较keys数量变化
            stage1_keys = {key['key_id']: key for key in stage1_result.key_final}
            stage2_keys = {key['key_id']: key for key in stage2_result.key_final}

            new_keys = []
            existing_keys = []

            for key_id, key in stage2_keys.items():
                if key_id in stage1_keys:
                    existing_keys.append((key, stage1_keys[key_id]))
                else:
                    new_keys.append(key)

            print(f"  • Stage1种子keys: {len(stage1_keys)} 个")
            print(f"  • Stage2最终keys: {len(stage2_keys)} 个")
            print(f"  • 扩展新增keys: {len(new_keys)} 个")
            print(f"  • 保留原有keys: {len(existing_keys)} 个")
            print(f"  • 扩展率: {len(stage2_keys)/len(stage1_keys):.2f}x")

            # 显示新增的keys
            if new_keys:
                print(f"\n🆕 === Stage2扩展发现的新Keys ===")
                for i, key in enumerate(new_keys, 1):
                    print(f"  {i}. {key['name']} [{key['type']}] - 权重: {key['weight']:.4f}, 发现步骤: {key['steps']}")

            # 显示原有keys的权重变化
            if existing_keys:
                print(f"\n📈 === 原有Keys权重变化 ===")
                sorted_existing = sorted(existing_keys, key=lambda x: x[0]['weight'], reverse=True)
                for i, (stage2_key, stage1_key) in enumerate(sorted_existing, 1):
                    weight_change = stage2_key['weight'] - stage1_key['weight']
                    change_pct = (weight_change / stage1_key['weight']) * 100 if stage1_key['weight'] > 0 else 0
                    change_symbol = "📈" if weight_change > 0 else "📉" if weight_change < 0 else "➡️"
                    print(f"  {i}. {stage2_key['name']} [{stage2_key['type']}] - "
                          f"权重: {stage1_key['weight']:.4f} → {stage2_key['weight']:.4f} "
                          f"{change_symbol} {weight_change:+.4f} ({change_pct:+.1f}%)")

            # 显示跳跃过程详情
            print(f"\n🔄 === 多跳扩展过程 ===")
            for jump_result in stage2_result.jump_results:
                print(f"  第{jump_result['jump']}跳: "
                      f"发现事件{jump_result['events_found']}个, "
                      f"相似事件{jump_result['events_similar']}个, "
                      f"keys数量{jump_result['keys_count']}, "
                      f"总权重{jump_result['total_weight']:.4f}, "
                      f"权重变化{jump_result['weight_change']:.4f}")

            print(f"\n✅ === Stage2 Key扩展测试完成 ===")
            return stage2_result

        except Exception as e:
            print(f"❌ Stage2 Key扩展测试失败: {e}")
            logger.error(f"Stage2 Key扩展测试失败: {e}", exc_info=True)
            raise

    async def test_stage3_from_stage2(self, stage2_result):
        """
        测试Stage3搜索功能（基于Stage2结果，返回事项列表）

        Args:
            stage2_result: Stage2的搜索结果（包含key_final）
        """
        try:
            print("\n🚀 === 开始Stage3搜索测试（基于Stage2结果）===")

            # 检查Stage2结果
            if not stage2_result or not stage2_result.key_final:
                print("❌ Stage2结果为空或没有key_final，无法进行Stage3测试")
                return None

            print(f"📝 从Stage2获得 {len(stage2_result.key_final)} 个keys")

            # 执行Stage3搜索，返回事项列表
            event_results = await self.stage3_searcher.search(
                key_final=stage2_result.key_final,
                config=self.config
            )

            # 输出结果
            print(f"\n📊 === Stage3搜索结果 ===")
            print(f"  • 返回事项数量: {len(event_results)}")

            if not event_results:
                print("⚠️  未找到任何事项")
                return None

            # 显示前5个事项
            print(f"\n📋 === 事项预览（前5个）===")
            for i, event in enumerate(event_results[:5], 1):
                print(f"\n【事项 {i}】")
                print(f"  🆔 事项ID: {event.id}")
                print(f"  📌 标题: {event.title}")

                # 显示摘要
                summary = event.summary if event.summary else 'N/A'
                if len(summary) > 150:
                    print(f"  📝 摘要: {summary[:150]}...")
                else:
                    print(f"  📝 摘要: {summary}")

                # 显示召回线索（clues）
                if hasattr(event, 'clues') and event.clues:
                    print(f"  📌 召回线索 (共{len(event.clues)}个):")
                    for clue in event.clues[:3]:  # 只显示前3个
                        clue_type = clue.get('type', 'unknown')
                        clue_name = clue.get('name', 'N/A')
                        clue_weight = clue.get('weight', 0.0)
                        clue_steps = clue.get('steps', [])

                        # 根据类型选择图标
                        if clue_type == 'query':
                            icon = "🔍"
                        elif clue_type == 'organization':
                            icon = "🏢"
                        elif clue_type == 'person':
                            icon = "👤"
                        elif clue_type == 'location':
                            icon = "📍"
                        else:
                            icon = "🔖"

                        # 格式化 step 信息
                        if clue_steps:
                            step_str = f", step={clue_steps}"
                        else:
                            step_str = ""

                        print(f"    {icon} [{clue_type}] {clue_name[:40]} (weight={clue_weight:.2f}{step_str})")

                    if len(event.clues) > 3:
                        print(f"    ... 还有 {len(event.clues) - 3} 个线索")
                else:
                    print(f"  ⚠️ 无召回线索")

            print(f"\n✅ === Stage3搜索测试完成 ===")
            return event_results

        except Exception as e:
            print(f"❌ Stage3搜索测试失败: {e}")
            logger.error(f"Stage3搜索测试失败: {e}", exc_info=True)
            raise

    async def test_stage3_events_from_stage2(self, stage2_result):
        """
        测试Stage3搜索功能（返回完整事项列表，基于Stage2结果）

        Args:
            stage2_result: Stage2的搜索结果（包含key_final）
        """
        try:
            print("\n🚀 === 开始Stage3完整事项搜索测试（基于Stage2结果）===")

            # 检查Stage2结果
            if not stage2_result or not stage2_result.key_final:
                print("❌ Stage2结果为空或没有key_final，无法进行Stage3测试")
                return None

            print(f"📝 从Stage2获得 {len(stage2_result.key_final)} 个keys")

            # 执行Stage3搜索，返回事项列表
            event_results = await self.stage3_searcher.search(
                key_final=stage2_result.key_final,
                config=self.config
            )

            # 输出结果
            print(f"\n📊 === Stage3完整事项搜索结果 ===")
            print(f"  • 返回事项数量: {len(event_results)}")

            if not event_results:
                print("⚠️  未找到任何事项")
                return None

            # 显示所有事项
            print(f"\n📋 === 完整事项列表 ===")
            for i, event in enumerate(event_results, 1):
                print(f"\n【事项 {i}】")
                print(f"  🆔 事项ID: {event.id}")
                print(f"  📌 标题: {event.title}")

                # 显示摘要
                summary = event.summary if event.summary else 'N/A'
                if len(summary) > 150:
                    print(f"  📝 摘要: {summary[:150]}...")
                else:
                    print(f"  📝 摘要: {summary}")

                # 显示内容预览
                content = event.content if event.content else 'N/A'
                if len(content) > 200:
                    print(f"  📄 内容: {content[:200]}...")
                else:
                    print(f"  📄 内容: {content}")

                # 显示召回线索（clues）
                if hasattr(event, 'clues') and event.clues:
                    print(f"  📌 召回线索 (共{len(event.clues)}个):")
                    for clue in event.clues:
                        clue_type = clue.get('type', 'unknown')
                        clue_name = clue.get('name', 'N/A')
                        clue_weight = clue.get('weight', 0.0)
                        clue_steps = clue.get('steps', [])

                        # 根据类型选择图标
                        if clue_type == 'query':
                            icon = "🔍"
                        elif clue_type == 'organization':
                            icon = "🏢"
                        elif clue_type == 'person':
                            icon = "👤"
                        elif clue_type == 'location':
                            icon = "📍"
                        else:
                            icon = "🔖"

                        # 格式化 step 信息
                        if clue_steps:
                            step_str = f", step={clue_steps}"
                        else:
                            step_str = ""

                        print(f"    {icon} [{clue_type}] {clue_name[:40]} (weight={clue_weight:.2f}{step_str})")
                else:
                    print(f"  ⚠️ 无召回线索")

                # 显示其他信息
                if hasattr(event, 'rank'):
                    print(f"  🔢 事项序号: {event.rank}")
                if hasattr(event, 'article_id'):
                    print(f"  📰 文章ID: {event.article_id}")

            print(f"\n✅ === Stage3完整事项搜索测试完成 ===")
            return event_results

        except Exception as e:
            print(f"❌ Stage3完整事项搜索测试失败: {e}")
            logger.error(f"Stage3完整事项搜索测试失败: {e}", exc_info=True)
            raise


async def main():
    """主测试函数"""
    test_instance = Stage2E2ETest()

    try:
        # 初始化测试环境
        await test_instance.setup()

        # 测试1: 独立Stage2搜索
        print("🧪 开始测试1: 独立Stage2搜索")
        result1 = await test_instance.test_stage2_search()

        # 测试2: 基于Stage2结果的Stage3事项搜索（预览版）
        print("\n🧪 开始测试2: Stage3事项搜索-预览版（基于测试1的结果，显示前5个事项含clues）")
        stage3_preview_result = await test_instance.test_stage3_from_stage2(result1)

        # 测试3: 基于Stage2结果的Stage3完整事项搜索
        print("\n🧪 开始测试3: Stage3完整事项搜索（基于测试1的结果，显示所有事项含clues）")
        stage3_full_result = await test_instance.test_stage3_events_from_stage2(result1)

        # # 测试2: 使用Stage1单个key作为种子的Stage2搜索
        # print("\n🧪 开始测试2: Stage2单Key种子扩展测试")
        # result2 = await test_instance.test_stage2_with_single_key()

        # # 测试3: Stage2 Key扩展效果测试（保留作对比）
        # print("\n🧪 开始测试3: Stage2 Key扩展效果测试")
        # result3 = await test_instance.test_stage2_key_expansion()

        print("\n🎉 === 所有测试完成 ===")

        # 清理测试资源
        await test_instance.cleanup()

    except Exception as e:
        print(f"❌ 测试执行失败: {e}")
        logger.error(f"测试执行失败: {e}", exc_info=True)

        # 尝试清理资源
        try:
            await test_instance.cleanup()
        except:
            pass

        return 1

    return 0


if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)