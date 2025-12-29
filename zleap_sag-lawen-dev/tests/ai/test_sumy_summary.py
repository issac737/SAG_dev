"""
测试 Sumy 摘要生成功能

使用方法:
    # 使用内置示例文本（自动策略）
    python test_sumy_summary.py

    # 使用指定文件（自动策略）
    python test_sumy_summary.py path/to/file.txt

    # 使用指定文件和句子数
    python test_sumy_summary.py path/to/file.txt 5

    # 使用压缩率模式
    python test_sumy_summary.py path/to/file.txt --ratio 0.2
"""
import asyncio
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dataflow.core.ai.sumy import SumySummarizer
from dataflow.utils import setup_logging

setup_logging()

async def test_with_builtin_text():
    """使用内置文本测试"""
    print("\n" + "=" * 70)
    print("Sumy + LLM 摘要测试 - 内置示例")
    print("=" * 70)

    text = """人工智能（Artificial Intelligence，简称AI）是计算机科学的一个重要分支，旨在研究和开发能够模拟、延伸和扩展人类智能的理论、方法、技术及应用系统。

自20世纪50年代诞生以来，人工智能经历了多次发展高潮和低谷。近年来，随着深度学习技术的突破，AI在图像识别、语音识别、自然语言处理等领域取得了巨大进展。

深度学习是机器学习的一个子领域，它通过构建多层神经网络来学习数据的高级特征表示。深度学习的成功得益于三个关键因素：大规模数据集的可用性、强大的计算能力（特别是GPU的应用），以及改进的算法和网络架构。

在自然语言处理领域，Transformer架构的提出标志着一个重要的里程碑。基于Transformer的模型如BERT、GPT系列在各种NLP任务上刷新了性能记录。这些大语言模型不仅能够理解和生成文本，还展现出了令人惊讶的推理和问题解决能力。

然而，人工智能的发展也带来了一些挑战和担忧。算法偏见、隐私保护、就业影响、AI安全等问题需要被认真对待。研究者和政策制定者正在努力制定相关的伦理准则和监管框架。

展望未来，人工智能将继续快速发展，并在医疗、教育、交通、金融等各个领域产生深远影响。通用人工智能（AGI）的实现仍然是一个长期目标，但即使是当前的弱人工智能技术也已经在改变我们的生活方式。

人工智能的发展需要跨学科的合作，包括计算机科学、数学、认知科学、神经科学、语言学等多个领域。只有通过持续的研究和负责任的应用，我们才能充分发挥AI技术的潜力，同时避免其潜在的负面影响。"""

    summarizer = SumySummarizer()

    # 自动检测语言
    detected_lang = summarizer.detect_language(text)
    print(f"\n自动检测语言: {detected_lang}")

    # 统计字符和句子
    char_count = len(text)
    total_sentences = summarizer.count_sentences(text)
    print(f"\n原文统计:")
    print(f"  字符数: {char_count}")
    print(f"  句子数: {total_sentences}")

    # 测试1: 自动智能处理（不指定句子数）
    print(f"\n{'='*70}")
    print("测试1: 自动智能处理（根据文本长度自动决策）")
    print(f"{'='*70}")

    # generate_summary 现在直接返回解析后的字典
    result = await summarizer.generate_summary(
        text,
        background="人工智能发展概述"
    )

    print(f"\n生成的结果:")
    print(f"  标题: {result['title']}")
    print(f"  分类: {result['category']}")
    print(f"  标签: {', '.join(result['tags'])}")
    print(f"\n摘要:")
    print(f"  {result['summary']}")
    print(f"\n摘要长度: {len(result['summary'])} 字符")


async def test_with_file(file_path: str, sentence_count: Optional[int] = None):
    """使用文件测试"""
    print("\n" + "=" * 70)
    print(f"Sumy + LLM 摘要测试 - 文件: {file_path}")
    print("=" * 70)

    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    summarizer = SumySummarizer()

    # 自动检测语言
    detected_lang = summarizer.detect_language(text)
    print(f"\n自动检测语言: {detected_lang}")

    char_count = len(text)
    total_sentences = summarizer.count_sentences(text)

    print(f"\n文件统计:")
    print(f"  字符数: {char_count}")
    print(f"  句子数: {total_sentences}")

    # generate_summary_with_ratio 现在直接返回解析后的字典
    result = await summarizer.generate_summary_with_ratio(
        text,
        background=Path(file_path).stem
    )

    print(f"\n生成的结果:")
    print(f"  标题: {result['title']}")
    print(f"  分类: {result['category']}")
    print(f"  标签: {', '.join(result['tags'])}")
    print(f"\n摘要:")
    print(f"  {result['summary']}")
    print(f"\n摘要长度: {len(result['summary'])} 字符")


async def main():
    if len(sys.argv) == 1:
        # 无参数：使用内置文本
        await test_with_builtin_text()
    else:
        # 指定文件和可选的句子数
        file_path = sys.argv[1]
        sentence_count = int(sys.argv[2]) if len(sys.argv) > 2 else None  # None表示自动计算
        await test_with_file(file_path, sentence_count)

    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n测试被中断")
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
