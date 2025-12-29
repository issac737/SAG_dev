#!/usr/bin/env python3
"""综合测试：保守解析策略 + 智能单位匹配"""

import sys
sys.path.insert(0, '.')

from dataflow.modules.extract.parser import EntityValueParser

def test_all_optimizations():
    """综合测试所有优化功能"""
    parser = EntityValueParser()

    print("=" * 80)
    print("综合测试：保守解析策略 + 智能单位匹配")
    print("=" * 80)
    print()

    # (描述, 文本, 配置, 期望类型, 期望值, 期望单位)
    test_cases = [
        # 【保守策略测试】避免误判
        ("❌ 误判案例1", "一对一帮扶", None, "text", "一对一帮扶", None),
        ("❌ 误判案例2", "每天10点上线", None, "text", "每天10点上线", None),
        ("❌ 误判案例3", "五六个订单", None, "text", "五六个订单", None),
        ("❌ 误判案例4", "六大核心技能", None, "text", "六大核心技能", None),

        # 【保守策略测试】正确识别
        ("✅ 布尔识别", "是", None, "bool", True, None),
        ("✅ 布尔识别", "否", None, "bool", False, None),
        ("✅ 数字识别", "123", None, "int", 123, None),
        ("✅ 中文数字", "三千万", None, "int", 30000000, None),

        # 【智能单位匹配】配置单位时的智能提取
        ("🆕 智能匹配1", "七个订单", {"type": "int", "unit": "订单"}, "int", 7, "订单"),
        ("🆕 智能匹配2", "三个项目", {"type": "int", "unit": "项目"}, "int", 3, "项目"),
        ("🆕 智能匹配3", "10件商品", {"type": "int", "unit": "商品"}, "int", 10, "商品"),
        ("🆕 智能匹配4", "5订单", {"type": "int", "unit": "订单"}, "int", 5, "订单"),
        ("🆕 智能匹配5", "3.5个", {"type": "float", "unit": "个"}, "float", 3.5, "个"),

        # 【智能单位匹配】单位不匹配时拒绝
        ("🆕 拒绝不匹配", "七个订单", {"type": "int", "unit": "项目"}, None, None, None),

        # 【严格模式】仍然工作
        ("🔒 严格整数", "123", {"type": "int"}, "int", 123, None),
        ("🔒 严格拒绝", "123.45", {"type": "int"}, None, None, None),
        ("🔒 枚举UNKNOWN", "维护", {"type": "enum", "enum_values": ["开发", "测试"]}, "enum", "UNKNOWN", None),
    ]

    success_count = 0
    total_count = len(test_cases)

    for desc, text, constraints, expected_type, expected_value, expected_unit in test_cases:
        result = parser.parse(text, value_constraints=constraints)

        actual_type = result["type"] if result else None
        actual_value = result["value"] if result else None
        actual_unit = result.get("unit") if result else None

        is_success = (
            actual_type == expected_type and
            actual_value == expected_value and
            actual_unit == expected_unit
        )

        status = "✅" if is_success else "❌"
        success_count += (1 if is_success else 0)

        print(f"{status} [{desc}] '{text}'")
        if not is_success:
            print(f"   期望: type={expected_type}, value={expected_value}, unit={expected_unit}")
            print(f"   实际: type={actual_type}, value={actual_value}, unit={actual_unit}")
        print()

    print("=" * 80)
    print(f"测试结果: {success_count}/{total_count} 通过")
    print("=" * 80)

    if success_count == total_count:
        print("✅ 所有优化功能正常工作！")
        print()
        print("✨ 功能总结:")
        print("  1. ✅ 保守解析策略 - 避免误判长文本和复杂文本")
        print("  2. ✅ 智能单位匹配 - 配置单位时智能提取数字（支持量词）")
        print("  3. ✅ 严格模式 - 按配置类型强制解析")
        print("  4. ✅ UNKNOWN 枚举 - 无法匹配时返回 UNKNOWN")
        return True
    else:
        print(f"❌ {total_count - success_count} 个测试失败")
        return False


if __name__ == "__main__":
    try:
        result = test_all_optimizations()
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
