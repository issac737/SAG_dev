#!/usr/bin/env python3
"""测试值解析器的保守策略（修复数据库误判案例）"""

import sys
sys.path.insert(0, '.')

from dataflow.modules.extract.parser import EntityValueParser

def test_conservative_parsing():
    """测试保守解析策略 - 修复数据库中的误判案例"""
    parser = EntityValueParser()

    print("=" * 80)
    print("测试保守解析策略 - 数据库误判案例")
    print("=" * 80)
    print()

    # ❌ 原来的问题案例（应该都返回 text 类型）
    test_cases = [
        # 案例1：包含"一"字但不是数字
        ("一对一帮扶", "text"),
        # 案例2：包含"点"但不是时间
        ("每天10点上线", "text"),
        # 案例3：中文数字但包含其他字
        ("五六个订单", "text"),
        ("六大核心技能", "text"),
        # 案例4：长文本不应被识别为bool
        ("已经完成了项目", "text"),
        # 案例5：纯布尔关键词应该被识别
        ("是", "bool"),
        ("否", "bool"),
        ("true", "bool"),
        ("false", "bool"),
        # 案例6：纯数字应该被识别
        ("123", "int"),
        ("123.45", "float"),
        # 案例7：纯中文数字应该被识别
        ("三千万", "int"),
        ("五十", "int"),
        # 案例8：包含数字关键词但过长
        ("一二三四五六七八", "text"),  # 8个字符，超过6个限制
    ]

    success_count = 0
    total_count = len(test_cases)

    for text, expected_type in test_cases:
        result = parser.parse(text)
        actual_type = result["type"] if result else None

        status = "✅" if actual_type == expected_type else "❌"
        success_count += (1 if actual_type == expected_type else 0)

        print(f"{status} '{text}'")
        print(f"   期望: {expected_type}, 实际: {actual_type}")
        if result:
            print(f"   值: {result['value']}, 置信度: {result['confidence']}")
        print()

    print("=" * 80)
    print(f"测试结果: {success_count}/{total_count} 通过")
    print("=" * 80)

    if success_count == total_count:
        print("✅ 所有测试通过！保守策略生效。")
        return True
    else:
        print(f"❌ {total_count - success_count} 个测试失败")
        return False


def test_strict_mode_still_works():
    """确保严格模式仍然正常工作"""
    parser = EntityValueParser()

    print()
    print("=" * 80)
    print("测试严格模式（确保之前的功能没有被破坏）")
    print("=" * 80)
    print()

    # 严格模式测试
    test_cases = [
        # 整数严格模式
        ("123", {"type": "int"}, "int", 123),
        ("123.45", {"type": "int"}, None, None),  # 拒绝浮点数
        # 浮点严格模式
        ("123.45", {"type": "float"}, "float", 123.45),
        ("123", {"type": "float"}, "float", 123.0),
        # 枚举严格模式
        ("开发", {"type": "enum", "enum_values": ["需求分析", "开发", "测试"]}, "enum", "开发"),
        ("维护", {"type": "enum", "enum_values": ["需求分析", "开发", "测试"]}, "enum", "UNKNOWN"),
        # 文本强制模式
        ("123", {"type": "text"}, "text", "123"),
    ]

    success_count = 0
    total_count = len(test_cases)

    for text, constraints, expected_type, expected_value in test_cases:
        result = parser.parse(text, value_constraints=constraints)
        actual_type = result["type"] if result else None
        actual_value = result["value"] if result else None

        is_success = (actual_type == expected_type and actual_value == expected_value)
        status = "✅" if is_success else "❌"
        success_count += (1 if is_success else 0)

        print(f"{status} '{text}' with constraints={constraints['type']}")
        print(f"   期望: type={expected_type}, value={expected_value}")
        print(f"   实际: type={actual_type}, value={actual_value}")
        print()

    print("=" * 80)
    print(f"测试结果: {success_count}/{total_count} 通过")
    print("=" * 80)

    if success_count == total_count:
        print("✅ 严格模式测试通过！")
        return True
    else:
        print(f"❌ {total_count - success_count} 个测试失败")
        return False


if __name__ == "__main__":
    try:
        result1 = test_conservative_parsing()
        result2 = test_strict_mode_still_works()

        if result1 and result2:
            print()
            print("=" * 80)
            print("🎉 所有测试通过！值解析器优化成功！")
            print("=" * 80)
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
