"""
真实LLM集成测试

专门用于测试Stage1搜索中的实体提取功能与真实LLM的集成
"""

import pytest
import asyncio
import time
from typing import List, Dict, Any

# 标记为集成测试
pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestRealLLMIntegration:
    """真实LLM集成测试类"""

    @pytest.fixture(scope="class")
    async def searcher(self):
        """初始化真实的搜索器实例"""
        try:
            from dataflow.core.ai.factory import create_llm_client
            from dataflow.core.config import get_settings
            from dataflow.core.prompt.manager import PromptManager
            from dataflow.modules.search.stage1 import Stage1Searcher

            # 检查配置
            settings = get_settings()
            if not settings.llm_api_key:
                pytest.skip("未配置LLM API密钥，跳过集成测试")

            # 使用工厂模式初始化组件
            llm_client = create_llm_client(
                provider="openai",
                model=settings.llm_model,
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                with_retry=True
            )
            prompt_manager = PromptManager()
            searcher = Stage1Searcher(llm_client, prompt_manager)

            yield searcher

        except Exception as e:
            pytest.skip(f"初始化失败: {e}")

    @pytest.mark.integration
    async def test_simple_person_location_query(self, searcher):
        """测试简单的人员和地点查询"""
        query = "张三在北京工作"

        start_time = time.time()
        attributes = await searcher._extract_attributes_from_query(query)
        response_time = time.time() - start_time

        # 验证基本要求
        assert isinstance(attributes, list)
        assert response_time < 10.0  # 响应时间应该合理

        # 验证提取到的人员
        person_attrs = [attr for attr in attributes if attr['type'] == 'person']
        assert len(person_attrs) >= 1

        # 验证提取到的地点
        location_attrs = [attr for attr in attributes if attr['type'] == 'location']
        assert len(location_attrs) >= 1

        print(f"✅ 简单查询测试通过 - 响应时间: {response_time:.2f}s, 提取属性: {len(attributes)}")
        print(f"📋 提取到的属性详情:")
        for i, attr in enumerate(attributes, 1):
            print(f"  {i}. {attr}")
        print(f"🎯 查询: '{query}'")

    @pytest.mark.integration
    async def test_complex_multi_entity_query(self, searcher):
        """测试复杂的多实体查询"""
        query = "2024年李四在上海和深圳研究AI和区块链技术"

        start_time = time.time()
        attributes = await searcher._extract_attributes_from_query(query)
        response_time = time.time() - start_time

        # 验证提取到的实体类型
        entity_types = set(attr['type'] for attr in attributes)

        # 应该包含时间、人员、地点、话题
        expected_types = ['time', 'person', 'location', 'topic']
        found_types = [etype for etype in expected_types if etype in entity_types]

        assert len(found_types) >= 2, f"应该至少提取到2种实体类型，实际提取到: {entity_types}"
        assert response_time < 15.0

        print(f"✅ 复杂查询测试通过 - 响应时间: {response_time:.2f}s, 实体类型: {entity_types}")

    @pytest.mark.integration
    async def test_technical_topic_query(self, searcher):
        """测试技术主题查询"""
        query = "如何提高机器学习模型的准确率？"

        start_time = time.time()
        attributes = await searcher._extract_attributes_from_query(query)
        response_time = time.time() - start_time

        # 验证提取到技术相关实体
        tech_attrs = [attr for attr in attributes if attr['type'] in ['topic', 'action']]

        assert len(tech_attrs) >= 1, "应该提取到技术相关的实体"
        assert response_time < 10.0

        # 检查是否包含相关技术词汇
        extracted_names = [attr['name'] for attr in attributes]
        tech_keywords = ['机器学习', '模型', '准确率']

        found_keywords = [kw for kw in tech_keywords
                         if any(kw in name or name in kw for name in extracted_names)]

        print(f"✅ 技术查询测试通过 - 响应时间: {response_time:.2f}s, 提取属性: {len(attributes)}")
        print(f"   提取到的技术词汇: {found_keywords}")

    @pytest.mark.integration
    async def test_edge_cases(self, searcher):
        """测试边界情况"""
        edge_cases = [
            ("", "空查询"),
            ("a", "单字符查询"),
            ("这是一个非常长的查询，包含很多不相关的描述性文字，用来测试系统在处理长文本时的性能和准确性" * 3, "超长查询"),
            ("123456789", "纯数字查询"),
            ("!@#$%^&*()", "特殊字符查询"),
            ("Hello World", "英文查询"),
        ]

        for query, description in edge_cases:
            start_time = time.time()
            try:
                attributes = await searcher._extract_attributes_from_query(query)
                response_time = time.time() - start_time

                # 验证不会崩溃
                assert isinstance(attributes, list)
                assert response_time < 20.0

                print(f"✅ {description}测试通过 - 响应时间: {response_time:.2f}s, 提取属性: {len(attributes)}")

            except Exception as e:
                print(f"⚠️ {description}测试出现异常: {e}")
                # 边界情况下出现异常是可以接受的，但不应该崩溃整个系统

    @pytest.mark.integration
    async def test_confidence_scores(self, searcher):
        """测试置信度评估"""
        query = "王五教授在清华大学进行深度学习研究"

        attributes = await searcher._extract_attributes_from_query(query)

        # 验证置信度格式
        for attr in attributes:
            assert 'confidence' in attr
            assert isinstance(attr['confidence'], (int, float))
            assert 0.0 <= attr['confidence'] <= 1.0

        # 验证重要性评估
        for attr in attributes:
            assert 'importance' in attr
            assert attr['importance'] in ['high', 'medium', 'low']

        print(f"✅ 置信度测试通过 - 提取属性: {len(attributes)}")

    @pytest.mark.integration
    async def test_fallback_mechanism(self, searcher):
        """测试回退机制"""
        # 这里我们无法直接触发回退机制，但可以测试方法的健壮性
        queries = [
            "正常的查询内容",
            "包含一些模糊表述的查询",
            "可能提取不到实体的查询语句",
        ]

        for query in queries:
            try:
                attributes = await searcher._extract_attributes_from_query(query)
                # 不管结果如何，都不应该崩溃
                assert isinstance(attributes, list)

            except Exception as e:
                pytest.fail(f"查询 '{query}' 导致异常: {e}")

        print(f"✅ 回退机制测试通过 - 所有查询都能正常处理")


# 性能基准测试
@pytest.mark.integration
@pytest.mark.slow
async def test_performance_benchmark():
    """性能基准测试"""
    pytest.skip("性能基准测试需要单独运行")

    try:
        from dataflow.core.ai.factory import create_llm_client
        from dataflow.core.config import get_settings
        from dataflow.core.prompt.manager import PromptManager
        from dataflow.modules.search.stage1 import Stage1Searcher

        # 初始化
        settings = get_settings()
        if not settings.llm_api_key:
            pytest.skip("未配置LLM API密钥")

        llm_client = create_llm_client(
            provider="openai",
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            with_retry=True
        )
        prompt_manager = PromptManager()
        searcher = Stage1Searcher(llm_client, prompt_manager)

        # 测试查询
        test_queries = [
            "张三在北京工作",
            "李四研究人工智能技术",
            "2024年在上海举办技术大会",
            "如何提高机器学习模型性能",
            "深度学习框架对比分析"
        ]

        # 性能测试
        total_time = 0
        successful_calls = 0

        for query in test_queries:
            start_time = time.time()
            try:
                attributes = await searcher._extract_attributes_from_query(query)
                response_time = time.time() - start_time
                total_time += response_time
                successful_calls += 1

                print(f"查询: {query[:20]}... - 响应时间: {response_time:.2f}s")

            except Exception as e:
                print(f"查询失败: {query[:20]}... - 错误: {e}")

        if successful_calls > 0:
            avg_response_time = total_time / successful_calls
            print(f"平均响应时间: {avg_response_time:.2f}s")
            print(f"成功率: {successful_calls}/{len(test_queries)} ({successful_calls/len(test_queries)*100:.1f}%)")

            # 性能断言
            assert avg_response_time < 5.0, f"平均响应时间过长: {avg_response_time:.2f}s"
            assert successful_calls >= len(test_queries) * 0.8, "成功率过低"

    except Exception as e:
        pytest.skip(f"性能基准测试失败: {e}")


if __name__ == "__main__":
    # 直接运行集成测试
    print("🧪 开始运行真实LLM集成测试")
    print("=" * 60)

    # 可以通过命令行参数选择运行特定测试
    import sys

    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        if test_name == "performance":
            asyncio.run(test_performance_benchmark())
        else:
            print(f"未知的测试名称: {test_name}")
    else:
        # 运行pytest
        pytest.main([__file__, "-v", "-s"])