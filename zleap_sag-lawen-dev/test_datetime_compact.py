#!/usr/bin/env python3
"""测试紧凑日期格式解析（YYYYMMDD / YYYYMM）"""

import sys
sys.path.insert(0, '.')

from dataflow.modules.extract.parser import EntityValueParser
from datetime import datetime

def test_compact_date_formats():
    """测试紧凑日期格式"""
    parser = EntityValueParser()

    print("=" * 80)
    print("测试紧凑日期格式解析")
    print("=" * 80)
    print()

    # (描述, 文本, entity_type_category, entity_type, value_constraints, 期望类型, 期望值)
    test_cases = [
        # ===== 1. 时间类型属性 + 紧凑格式 =====
        ("✅ 8位日期 + time类型", "20230117", "time", None, None, "datetime", datetime(2023, 1, 17)),
        ("✅ 8位日期 + date类型", "20211225", "date", None, None, "datetime", datetime(2021, 12, 25)),
        ("✅ 6位月份 + time类型", "202301", "time", None, None, "datetime", datetime(2023, 1, 1)),

        # ===== 2. 实体类型包含时间关键词 =====
        ("✅ 实体类型=创建时间", "20230117", None, "创建时间", None, "datetime", datetime(2023, 1, 17)),
        ("✅ 实体类型=更新日期", "20210601", None, "更新日期", None, "datetime", datetime(2021, 6, 1)),

        # ===== 3. 严格模式 =====
        ("✅ 严格模式datetime", "20230117", None, None, {"type": "datetime"}, "datetime", datetime(2023, 1, 17)),

        # ===== 4. 日期验证 =====
        ("❌ 无效日期→int", "20231332", "time", None, None, "int", 20231332),  # 13月32日不存在，回退为int
        ("❌ 无效月份→int", "20231500", "time", None, None, "int", 20231500),  # 15月不存在，回退为int

        # ===== 5. 无提示时保守处理 =====
        ("🔒 无提示→int", "20230117", None, None, None, "int", 20230117),  # 保守：识别为数字
        ("🔒 6位无提示→int", "202301", None, None, None, "int", 202301),

        # ===== 6. 中文日期格式（向后兼容） =====
        ("✅ 中文格式", "2023年1月17日", "time", None, None, "datetime", datetime(2023, 1, 17)),
        ("✅ ISO格式", "2023-01-17", None, None, None, "datetime", datetime(2023, 1, 17)),
    ]

    success_count = 0
    total_count = len(test_cases)

    for desc, text, type_cat, entity_type, constraints, expected_type, expected_value in test_cases:
        result = parser.parse(
            text,
            entity_type=entity_type,
            entity_type_category=type_cat,
            value_constraints=constraints
        )

        actual_type = result["type"] if result else None
        actual_value = result["value"] if result else None

        is_success = (actual_type == expected_type and actual_value == expected_value)
        status = "✅" if is_success else "❌"
        success_count += (1 if is_success else 0)

        print(f"{status} [{desc}] '{text}'")
        if not is_success:
            print(f"   期望: type={expected_type}, value={expected_value}")
            print(f"   实际: type={actual_type}, value={actual_value}")
            if type_cat:
                print(f"   entity_type_category={type_cat}")
            if entity_type:
                print(f"   entity_type={entity_type}")
        print()

    print("=" * 80)
    print(f"测试结果: {success_count}/{total_count} 通过")
    print("=" * 80)

    return success_count == total_count


def test_edge_cases():
    """测试边界情况"""
    parser = EntityValueParser()

    print()
    print("=" * 80)
    print("测试边界情况")
    print("=" * 80)
    print()

    test_cases = [
        # (描述, 文本, type_cat, 期望类型, 期望值)
        ("闰年日期", "20240229", "time", "datetime", datetime(2024, 2, 29)),  # 2024是闰年
        ("非闰年→int", "20230229", "time", "int", 20230229),  # 2023不是闰年，2月29日无效，回退为int
        ("最小日期", "19700101", "time", "datetime", datetime(1970, 1, 1)),
        ("未来日期", "20991231", "time", "datetime", datetime(2099, 12, 31)),
        ("12月31日", "20231231", "time", "datetime", datetime(2023, 12, 31)),
    ]

    success_count = 0
    total_count = len(test_cases)

    for desc, text, type_cat, expected_type, expected_value in test_cases:
        result = parser.parse(text, entity_type_category=type_cat)

        actual_type = result["type"] if result else None
        actual_value = result["value"] if result else None

        is_success = (actual_type == expected_type and actual_value == expected_value)
        status = "✅" if is_success else "❌"
        success_count += (1 if is_success else 0)

        print(f"{status} {desc}: '{text}'")
        if not is_success:
            print(f"   期望: {expected_type}={expected_value}")
            print(f"   实际: {actual_type}={actual_value}")
        print()

    print("=" * 80)
    print(f"测试结果: {success_count}/{total_count} 通过")
    print("=" * 80)

    return success_count == total_count


if __name__ == "__main__":
    try:
        result1 = test_compact_date_formats()
        result2 = test_edge_cases()

        if result1 and result2:
            print()
            print("=" * 80)
            print("🎉 所有测试通过！紧凑日期格式识别功能正常工作！")
            print("=" * 80)
            print()
            print("✨ 支持的格式:")
            print("  1. ✅ YYYYMMDD (8位) - 完整日期")
            print("  2. ✅ YYYYMM (6位) - 年月")
            print("  3. ✅ 根据属性类型智能识别")
            print("  4. ✅ 日期验证（拒绝无效日期）")
            print("  5. ✅ 保守策略（无提示时识别为int）")
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
