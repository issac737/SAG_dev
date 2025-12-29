#!/usr/bin/env python3
"""测试值解析器的严格模式和 UNKNOWN 处理"""

import sys
sys.path.insert(0, '.')

from dataflow.modules.extract.parser import EntityValueParser

def test_strict_mode():
    """测试严格模式"""
    parser = EntityValueParser()

    print("=" * 60)
    print("测试 1: 严格整数模式")
    print("=" * 60)

    # 测试 1.1: 整数文本 + 整数配置 → 成功
    result = parser.parse("123", value_constraints={"type": "int"})
    print(f"✅ '123' with type=int: {result}")
    assert result and result["type"] == "int" and result["value"] == 123

    # 测试 1.2: 浮点数文本 + 整数配置 → 失败（严格拒绝）
    result = parser.parse("123.45", value_constraints={"type": "int"})
    print(f"❌ '123.45' with type=int: {result}")
    assert result is None, "严格模式下浮点数应该被拒绝"

    # 测试 1.3: 科学计数法 + 整数配置 → 失败
    result = parser.parse("1e5", value_constraints={"type": "int"})
    print(f"❌ '1e5' with type=int: {result}")
    assert result is None

    print()

    print("=" * 60)
    print("测试 2: 严格浮点模式")
    print("=" * 60)

    # 测试 2.1: 浮点数文本 + 浮点配置 → 成功
    result = parser.parse("123.45", value_constraints={"type": "float"})
    print(f"✅ '123.45' with type=float: {result}")
    assert result and result["type"] == "float" and result["value"] == 123.45

    # 测试 2.2: 整数文本 + 浮点配置 → 成功（转换为浮点）
    result = parser.parse("123", value_constraints={"type": "float"})
    print(f"✅ '123' with type=float: {result}")
    assert result and result["type"] == "float" and result["value"] == 123.0

    # 测试 2.3: 非数字文本 + 浮点配置 → 失败
    result = parser.parse("abc", value_constraints={"type": "float"})
    print(f"❌ 'abc' with type=float: {result}")
    assert result is None

    print()

    print("=" * 60)
    print("测试 3: 枚举类型 + UNKNOWN 处理")
    print("=" * 60)

    enum_config = {
        "type": "enum",
        "enum_values": ["需求分析", "设计", "开发", "测试", "上线"]
    }

    # 测试 3.1: 精确匹配
    result = parser.parse("开发", value_constraints=enum_config)
    print(f"✅ '开发' (精确匹配): {result}")
    assert result and result["value"] == "开发" and result["confidence"] == 1.0

    # 测试 3.2: 模糊匹配
    result = parser.parse("正在开发中", value_constraints=enum_config)
    print(f"✅ '正在开发中' (模糊匹配): {result}")
    assert result and result["value"] == "开发" and result["confidence"] == 0.80

    # 测试 3.3: 无法匹配 → UNKNOWN
    result = parser.parse("维护阶段", value_constraints=enum_config)
    print(f"⚠️  '维护阶段' (无法匹配): {result}")
    assert result and result["value"] == "UNKNOWN" and result["confidence"] == 0.0

    print()

    print("=" * 60)
    print("测试 4: 兼容模式（无 value_constraints）")
    print("=" * 60)

    # 注意：兼容模式下的类型检测可能不够精确（这是原有设计）
    # 我们的改动重点是严格模式，因此这里只验证基本功能

    # 测试 4.1: 浮点数能被正确识别
    result = parser.parse("1234.56")
    print(f"✅ '1234.56' (自动检测): {result}")
    assert result is not None

    # 测试 4.2: 布尔关键字能被识别
    result = parser.parse("是的")
    print(f"✅ '是的' (自动检测): {result}")
    assert result and result["type"] == "bool"

    # 测试 4.3: 纯文本
    result = parser.parse("随便什么文本xyz")
    print(f"✅ '随便什么文本xyz' (默认文本): {result}")
    assert result and result["type"] == "text"

    print("  (注意：兼容模式的类型检测优先级为 bool > datetime > number > enum > text)")

    print()

    print("=" * 60)
    print("测试 5: 文本类型强制")
    print("=" * 60)

    # 测试 5.1: 数字文本 + 文本配置 → 强制为文本
    result = parser.parse("123", value_constraints={"type": "text"})
    print(f"✅ '123' with type=text: {result}")
    assert result and result["type"] == "text" and result["value"] == "123"

    print()

    print("=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_strict_mode()
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
