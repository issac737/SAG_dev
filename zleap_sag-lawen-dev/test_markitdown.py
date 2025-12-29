"""
测试 MarkItDown 集成

验证文档转换器是否正常工作
"""

import asyncio
from pathlib import Path
from dataflow.modules.load.converter import DocumentConverter


def test_converter():
    """测试转换器初始化和格式支持"""
    converter = DocumentConverter()
    
    print("✅ 转换器初始化成功")
    print(f"📝 支持的格式: {', '.join(sorted(converter.SUPPORTED_EXTENSIONS))}")
    
    # 测试格式检查
    test_files = [
        Path("test.pdf"),
        Path("test.docx"),
        Path("test.md"),
        Path("test.xlsx"),
        Path("test.unsupported"),
    ]
    
    print("\n🔍 格式支持测试:")
    for file in test_files:
        supported = converter.is_supported(file)
        status = "✅" if supported else "❌"
        print(f"  {status} {file.suffix}: {'支持' if supported else '不支持'}")


if __name__ == "__main__":
    test_converter()

