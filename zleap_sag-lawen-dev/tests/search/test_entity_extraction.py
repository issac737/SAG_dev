"""
测试Stage1搜索中的实体提取功能

包含单元测试（模拟）和集成测试（真实LLM）
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from typing import List, Dict, Any

from dataflow.core.ai.base import BaseLLMClient
from dataflow.core.prompt.manager import PromptManager
from dataflow.modules.search.stage1 import Stage1Searcher
from dataflow.modules.search.config import SearchConfig

# 标记集成测试
pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_llm_client():
    """模拟LLM客户端"""
    client = MagicMock(spec=BaseLLMClient)
    client.chat_with_schema = AsyncMock()
    return client


@pytest.fixture
def mock_prompt_manager():
    """模拟提示词管理器"""
    manager = MagicMock(spec=PromptManager)

    # 创建一个真正的 MagicMock 对象来模拟 render 方法
    render_mock = MagicMock()

    # 配置 render 方法的行为
    def mock_render_impl(template, **kwargs):
        query = kwargs.get('query', '')
        return (
            f"请从查询 '{query}' 中提取实体。"
            f"实体类型包括：person（人物）、location（地点）、time（时间）、"
            f"topic（话题）、action（动作）、organization（组织）、product（产品）等。"
            f"请按照 JSON Schema 格式返回结构化结果。"
        )

    # 使用 side_effect 让函数返回实际字符串，同时保持 mock 功能
    render_mock.side_effect = mock_render_impl
    manager.render = render_mock

    return manager


@pytest.fixture
def stage1_searcher(mock_llm_client, mock_prompt_manager):
    """创建Stage1搜索器实例"""
    return Stage1Searcher(mock_llm_client, mock_prompt_manager)


@pytest.mark.asyncio
async def test_extract_attributes_with_new_method(stage1_searcher, mock_llm_client):
    """测试新的属性提取方法"""

    # 模拟LLM响应 - 使用 attributes 格式
    mock_response = {
        "attributes": [
            {"name": "张三", "type": "person", "context": "张三在北京从事人工智能相关工作", "importance": "high"},
            {"name": "北京", "type": "location", "context": "张三在北京从事人工智能相关工作", "importance": "high"},
            {"name": "人工智能", "type": "topic", "context": "张三在北京从事人工智能相关工作", "importance": "high"}
        ]
    }
    mock_llm_client.chat_with_schema.return_value = mock_response

    # 测试查询
    query = "张三在北京从事人工智能相关工作"

    # 调用属性提取方法
    attributes = await stage1_searcher._extract_attributes_from_query(query)

    # 验证结果
    assert len(attributes) == 3

    # 验证人员实体
    person_attrs = [attr for attr in attributes if attr["type"] == "person"]
    assert len(person_attrs) == 1
    assert person_attrs[0]["name"] == "张三"
    assert person_attrs[0]["importance"] == "high"
    assert person_attrs[0]["confidence"] == 0.9  # high importance 对应 0.9 置信度

    # 验证地点实体
    location_attrs = [attr for attr in attributes if attr["type"] == "location"]
    assert len(location_attrs) == 1
    assert location_attrs[0]["name"] == "北京"
    assert location_attrs[0]["importance"] == "high"
    assert location_attrs[0]["confidence"] == 0.9  # high importance 对应 0.9 置信度

    # 验证话题实体
    topic_attrs = [attr for attr in attributes if attr["type"] == "topic"]
    assert len(topic_attrs) == 1
    assert topic_attrs[0]["name"] == "人工智能"
    assert topic_attrs[0]["importance"] == "high"
    assert topic_attrs[0]["confidence"] == 0.9  # high importance 对应 0.9 置信度


@pytest.mark.asyncio
async def test_extract_attributes_with_string_format(stage1_searcher, mock_llm_client):
    """测试字符串格式的实体响应"""

    # 模拟LLM响应 - 使用 attributes 格式
    mock_response = {
        "attributes": [
            {"name": "李四", "type": "person", "context": "李四在上海和深圳研究区块链技术", "importance": "high"},
            {"name": "上海", "type": "location", "context": "李四在上海和深圳研究区块链技术", "importance": "high"},
            {"name": "深圳", "type": "location", "context": "李四在上海和深圳研究区块链技术", "importance": "high"},
            {"name": "区块链技术", "type": "topic", "context": "李四在上海和深圳研究区块链技术", "importance": "medium"}
        ]
    }
    mock_llm_client.chat_with_schema.return_value = mock_response

    # 测试查询
    query = "李四在上海和深圳研究区块链技术"

    # 调用属性提取方法
    attributes = await stage1_searcher._extract_attributes_from_query(query)

    # 验证结果
    assert len(attributes) == 4

    # 验证人员实体
    person_attrs = [attr for attr in attributes if attr["type"] == "person"]
    assert len(person_attrs) == 1
    assert person_attrs[0]["name"] == "李四"

    # 验证地点实体
    location_attrs = [attr for attr in attributes if attr["type"] == "location"]
    assert len(location_attrs) == 2
    location_names = [attr["name"] for attr in location_attrs]
    assert "上海" in location_names
    assert "深圳" in location_names

    # 验证话题实体
    topic_attrs = [attr for attr in attributes if attr["type"] == "topic"]
    assert len(topic_attrs) == 1
    assert topic_attrs[0]["name"] == "区块链技术"


@pytest.mark.asyncio
async def test_extract_attributes_empty_response(stage1_searcher, mock_llm_client):
    """测试空响应的处理"""

    # 模拟空响应
    mock_response = {"attributes": []}
    mock_llm_client.chat_with_schema.return_value = mock_response

    # 测试查询
    query = "这是一个没有实体的查询"

    # 调用属性提取方法
    attributes = await stage1_searcher._extract_attributes_from_query(query)

    # 验证结果（应该使用回退方案）
    assert isinstance(attributes, list)
    # 回退方案可能返回一些基础属性，或者空列表


@pytest.mark.asyncio
async def test_extract_attributes_llm_failure(stage1_searcher, mock_llm_client):
    """测试LLM调用失败时的回退处理"""

    # 模拟LLM调用失败
    mock_llm_client.chat_with_schema.side_effect = Exception("LLM调用失败")

    # 测试查询
    query = "张三在北京工作"

    # 调用属性提取方法
    attributes = await stage1_searcher._extract_attributes_from_query(query)

    # 验证结果（应该使用回退方案）
    assert isinstance(attributes, list)
    # 回退方案应该能够提取到一些基础属性


async def test_build_attribute_extraction_prompt(stage1_searcher):
    """测试提示词构建"""

    query = "张三在北京从事AI研究"

    prompt = stage1_searcher._build_attribute_extraction_prompt(query)

    # 验证提示词包含关键元素
    assert "张三在北京从事AI研究" in prompt
    assert "time" in prompt or "person" in prompt  # 至少包含一些实体类型提示
    assert "JSON Schema" in prompt

    # 验证 render 方法被正确调用
    stage1_searcher.prompt_manager.render.assert_called_once_with("search/extract_attributes", query=query)


async def test_build_attribute_extraction_schema(stage1_searcher):
    """测试JSON Schema构建"""

    schema = stage1_searcher._build_attribute_extraction_schema()

    # 验证Schema结构
    assert schema["type"] == "object"
    assert "attributes" in schema["properties"]
    assert schema["properties"]["attributes"]["type"] == "array"
    assert "items" in schema["properties"]["attributes"]

    # 验证属性项的schema
    item_schema = schema["properties"]["attributes"]["items"]
    assert "name" in item_schema["properties"]
    assert "type" in item_schema["properties"]
    assert "context" in item_schema["properties"]
    assert "importance" in item_schema["properties"]


async def test_parse_attribute_extraction_response(stage1_searcher):
    """测试响应解析"""

    # 模拟响应
    response = {
        "attributes": [
            {"name": "王五", "type": "person", "context": "王五在杭州工作", "importance": "high"},
            {"name": "杭州", "type": "location", "context": "王五在杭州工作", "importance": "medium"}
        ]
    }

    attributes = stage1_searcher._parse_attribute_extraction_response(response)

    # 验证解析结果
    assert len(attributes) == 2

    person_attrs = [attr for attr in attributes if attr["type"] == "person"]
    assert len(person_attrs) == 1
    assert person_attrs[0]["name"] == "王五"
    assert person_attrs[0]["importance"] == "high"
    assert person_attrs[0]["confidence"] == 0.9  # high importance 对应 0.9

    location_attrs = [attr for attr in attributes if attr["type"] == "location"]
    assert len(location_attrs) == 1
    assert location_attrs[0]["name"] == "杭州"
    assert location_attrs[0]["importance"] == "medium"
    assert location_attrs[0]["confidence"] == 0.7  # medium importance 对应 0.7


async def test_parse_attribute_extraction_response_string_format(stage1_searcher):
    """测试字符串格式的响应解析"""

    # 模拟字符串格式的响应
    response = {
        "attributes": [
            {"name": "赵六", "type": "person", "context": "赵六研究机器学习", "importance": "medium"},
            {"name": "机器学习", "type": "topic", "context": "赵六研究机器学习", "importance": "medium"}
        ]
    }

    attributes = stage1_searcher._parse_attribute_extraction_response(response)

    # 验证解析结果
    assert len(attributes) == 2

    person_attrs = [attr for attr in attributes if attr["type"] == "person"]
    assert len(person_attrs) == 1
    assert person_attrs[0]["name"] == "赵六"
    assert person_attrs[0]["importance"] == "medium"
    assert person_attrs[0]["confidence"] == 0.7  # medium importance 对应 0.7

    topic_attrs = [attr for attr in attributes if attr["type"] == "topic"]
    assert len(topic_attrs) == 1
    assert topic_attrs[0]["name"] == "机器学习"


# ==================== 集成测试（真实LLM） ====================

@pytest.mark.integration
async def test_real_llm_entity_extraction():
    """使用真实LLM测试实体提取功能"""
    pytest.skip("需要配置API密钥才能运行集成测试")

@pytest.mark.integration
async def test_real_llm_simple_query():
    """测试简单查询的真实LLM实体提取"""
    pytest.skip("需要配置API密钥才能运行集成测试")

@pytest.mark.integration
async def test_real_llm_complex_query():
    """测试复杂查询的真实LLM实体提取"""
    pytest.skip("需要配置API密钥才能运行集成测试")


# 手动运行集成测试的辅助函数
async def run_integration_tests():
    """手动运行集成测试（不通过pytest）"""
    print("🧪 开始运行真实LLM集成测试")
    print("=" * 50)

    try:
        from dataflow.core.ai.llm import OpenAIClient
        from dataflow.core.config import get_settings

        # 检查配置
        settings = get_settings()
        if not settings.llm_api_key:
            print("❌ 未配置LLM API密钥，跳过集成测试")
            return

        # 初始化组件
        llm_client = OpenAIClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
        prompt_manager = PromptManager()
        searcher = Stage1Searcher(llm_client, prompt_manager)

        # 测试用例
        test_cases = [
            {
                "name": "简单实体查询",
                "query": "张三在北京从事人工智能相关工作",
                "expected_entities": ["张三", "北京", "人工智能"]
            },
            {
                "name": "多地点查询",
                "query": "李四的公司在上海和深圳都有分公司，主要做区块链技术",
                "expected_entities": ["李四", "上海", "深圳", "区块链技术"]
            },
            {
                "name": "时间相关查询",
                "query": "2024年夏季，王五在杭州参加了AI技术大会",
                "expected_entities": ["2024年夏季", "王五", "杭州", "AI技术大会"]
            },
            {
                "name": "技术主题查询",
                "query": "如何提高机器学习模型的准确率？",
                "expected_entities": ["机器学习", "模型", "准确率"]
            },
            {
                "name": "复杂技术查询",
                "query": "深度学习框架TensorFlow和PyTorch在自然语言处理中的应用对比",
                "expected_entities": ["深度学习", "TensorFlow", "PyTorch", "自然语言处理"]
            }
        ]

        # 运行测试
        results = []
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n📝 测试用例 {i}: {test_case['name']}")
            print(f"查询: {test_case['query']}")
            print("-" * 40)

            try:
                # 记录开始时间
                import time
                start_time = time.time()

                # 调用实体提取
                attributes = await searcher._extract_attributes_from_query(test_case['query'])

                # 计算响应时间
                response_time = time.time() - start_time

                # 分析结果
                extracted_names = [attr['name'] for attr in attributes]
                found_entities = []
                missing_entities = []

                for expected in test_case['expected_entities']:
                    if any(expected in extracted or extracted in expected for extracted in extracted_names):
                        found_entities.append(expected)
                    else:
                        missing_entities.append(expected)

                # 输出结果
                print(f"✅ 响应时间: {response_time:.2f}秒")
                print(f"📊 提取到 {len(attributes)} 个属性:")

                for attr in attributes:
                    confidence_bar = "█" * int(attr['confidence'] * 5) + "░" * (5 - int(attr['confidence'] * 5))
                    print(f"  • {attr['name']} [{attr['type']}] {confidence_bar} {attr['confidence']:.2f}")

                # 分析覆盖率
                coverage = len(found_entities) / len(test_case['expected_entities']) * 100
                print(f"🎯 实体覆盖率: {coverage:.1f}% ({len(found_entities)}/{len(test_case['expected_entities'])})")

                if missing_entities:
                    print(f"⚠️ 未提取到: {', '.join(missing_entities)}")

                # 记录结果
                results.append({
                    "test_case": test_case['name'],
                    "query": test_case['query'],
                    "extracted_count": len(attributes),
                    "expected_count": len(test_case['expected_entities']),
                    "coverage": coverage,
                    "response_time": response_time,
                    "attributes": attributes
                })

            except Exception as e:
                print(f"❌ 测试失败: {e}")
                results.append({
                    "test_case": test_case['name'],
                    "query": test_case['query'],
                    "error": str(e)
                })

        # 总结报告
        print("\n" + "=" * 50)
        print("📈 测试总结报告")
        print("=" * 50)

        successful_tests = [r for r in results if 'error' not in r]
        failed_tests = [r for r in results if 'error' in r]

        if successful_tests:
            avg_coverage = sum(r['coverage'] for r in successful_tests) / len(successful_tests)
            avg_response_time = sum(r['response_time'] for r in successful_tests) / len(successful_tests)
            total_extracted = sum(r['extracted_count'] for r in successful_tests)

            print(f"✅ 成功测试: {len(successful_tests)}/{len(test_cases)}")
            print(f"📊 平均实体覆盖率: {avg_coverage:.1f}%")
            print(f"⏱️ 平均响应时间: {avg_response_time:.2f}秒")
            print(f"🔍 总提取实体数: {total_extracted}")

        if failed_tests:
            print(f"❌ 失败测试: {len(failed_tests)}")
            for failed in failed_tests:
                print(f"  • {failed['test_case']}: {failed['error']}")

        # 保存详细结果
        save_test_results(results)

    except Exception as e:
        print(f"❌ 集成测试初始化失败: {e}")


def save_test_results(results: List[Dict[str, Any]]):
    """保存测试结果到文件"""
    import json
    import os
    from datetime import datetime

    # 创建results目录
    os.makedirs("test_results", exist_ok=True)

    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"test_results/entity_extraction_{timestamp}.json"

    # 保存结果
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"📁 详细结果已保存到: {filename}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--integration":
        # 运行集成测试
        asyncio.run(run_integration_tests())
    else:
        # 运行单元测试
        pytest.main([__file__])