"""
关键词提取测试 - 最佳实践示例

演示使用单例模式提取关键词，对比三种模式效果。

运行方式：
    python tests/ai/test_tokenizer_keywords.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataflow.core.ai.tokensize import get_keyword_extractor


# 测试文本
TEST_CASES = [
    ("中文", "苹果公司发布了新款iPhone 15系列手机，这是苹果今年最重要的产品发布。"),
    ("英文", "Apple Inc. announced the new iPhone 15 series, the most important product launch this year."),
    ("中英混合", "特斯拉CEO Elon Musk宣布推出Cybertruck电动皮卡，这是特斯拉最具创新性的产品。"),
    ("人名机构", "马云创建了阿里巴巴集团，张一鸣创建了字节跳动公司。"),
]


async def main():
    """主测试函数"""
    print("=" * 70)
    print("关键词提取 - 模式对比测试")
    print("=" * 70)
    
    # 获取单例提取器
    extractor = get_keyword_extractor()
    
    for name, text in TEST_CASES:
        print(f"\n【{name}】")
        print(f"  文本: {text}")
        print("-" * 60)
        
        # tokenizer 模式（同步，快速，离线）
        result = extractor.extract(text)
        print(f"  tokenizer: {result}")
        
        # llm 模式（异步，精准，需要API）
        try:
            result = await extractor.extract_async(text, mode="llm")
            print(f"  llm:       {result}")
        except Exception as e:
            print(f"  llm:       ❌ {e}")
        
        # merge 模式（异步，合并两者）
        try:
            result = await extractor.extract_async(text, mode="merge")
            print(f"  merge:     {result}")
        except Exception as e:
            print(f"  merge:     ❌ {e}")
    
    print("\n" + "=" * 70)
    print("✅ 测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())

