"""
Sumy 各算法模块性能测试和关键词统计

测试内容：
1. LexRank 算法（基于图的方法，使用余弦相似度）
2. Luhn 算法（基于词频和句子聚类）
3. TextRank 算法（基于 PageRank 的图算法）
4. Latent Semantic Analysis (LSA) 算法（基于奇异值分解）
5. KL-Sum 算法（基于 KL 散度的方法）

性能指标：
- 算法执行耗时
- 提取的关键句子数量
- 关键词统计和分析

使用方法:
    # 使用内置示例文本
    python test_sumy_algorithms_benchmark.py

    # 使用指定文件
    python test_sumy_algorithms_benchmark.py path/to/file.txt

    # 指定提取的句子数量
    python test_sumy_algorithms_benchmark.py path/to/file.txt 10
"""

import sys
import time
from pathlib import Path
from collections import Counter
from typing import List, Dict, Tuple
import re

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sumy.nlp.tokenizers import Tokenizer
from sumy.parsers.plaintext import PlaintextParser
from sumy.summarizers.lex_rank import LexRankSummarizer
from sumy.summarizers.luhn import LuhnSummarizer
from sumy.summarizers.text_rank import TextRankSummarizer
from sumy.summarizers.lsa import LsaSummarizer
from sumy.summarizers.kl import KLSummarizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words

from dataflow.utils import setup_logging

setup_logging()


# 内置测试文本
BUILTIN_TEXT = """人工智能（Artificial Intelligence，简称AI）是计算机科学的一个重要分支，旨在研究和开发能够模拟、延伸和扩展人类智能的理论、方法、技术及应用系统。

自20世纪50年代诞生以来，人工智能经历了多次发展高潮和低谷。近年来，随着深度学习技术的突破，AI在图像识别、语音识别、自然语言处理等领域取得了巨大进展。

深度学习是机器学习的一个子领域，它通过构建多层神经网络来学习数据的高级特征表示。深度学习的成功得益于三个关键因素：大规模数据集的可用性、强大的计算能力（特别是GPU的应用），以及改进的算法和网络架构。

在自然语言处理领域，Transformer架构的提出标志着一个重要的里程碑。基于Transformer的模型如BERT、GPT系列在各种NLP任务上刷新了性能记录。这些大语言模型不仅能够理解和生成文本，还展现出了令人惊讶的推理和问题解决能力。

然而，人工智能的发展也带来了一些挑战和担忧。算法偏见、隐私保护、就业影响、AI安全等问题需要被认真对待。研究者和政策制定者正在努力制定相关的伦理准则和监管框架。

展望未来，人工智能将继续快速发展，并在医疗、教育、交通、金融等各个领域产生深远影响。通用人工智能（AGI）的实现仍然是一个长期目标，但即使是当前的弱人工智能技术也已经在改变我们的生活方式。

人工智能的发展需要跨学科的合作，包括计算机科学、数学、认知科学、神经科学、语言学等多个领域。只有通过持续的研究和负责任的应用，我们才能充分发挥AI技术的潜力，同时避免其潜在的负面影响。

机器学习作为人工智能的核心技术，包括监督学习、无监督学习和强化学习等多种方法。监督学习通过标注数据训练模型，无监督学习从未标注数据中发现模式，强化学习则通过与环境交互来学习最优策略。

计算机视觉是人工智能的另一个重要应用领域。通过卷积神经网络（CNN）等深度学习技术，计算机已经能够在图像分类、目标检测、语义分割等任务上达到甚至超越人类的表现。

自然语言处理技术使计算机能够理解和生成人类语言。从早期的规则系统到现在的大语言模型，NLP技术经历了革命性的发展。现代NLP系统可以进行机器翻译、情感分析、问答系统、文本摘要等多种任务。"""


class AlgorithmBenchmark:
    """算法性能基准测试类"""

    def __init__(self, text: str, language: str = "chinese", sentence_count: int = 5):
        """
        初始化基准测试

        Args:
            text: 测试文本
            language: 语言类型（chinese/english）
            sentence_count: 要提取的句子数量
        """
        self.text = text
        self.language = language
        self.sentence_count = sentence_count
        self.parser = PlaintextParser.from_string(text, Tokenizer(language))
        self.stemmer = Stemmer(language)
        self.stop_words = get_stop_words(language)

        # 统计原文信息
        self.char_count = len(text)
        self.total_sentences = len(list(self.parser.document.sentences))

    def extract_keywords(self, sentences: List[str], top_n: int = 20) -> List[Tuple[str, int]]:
        """
        从句子中提取关键词

        Args:
            sentences: 句子列表
            top_n: 返回前N个关键词

        Returns:
            关键词及其频率的列表
        """
        text = " ".join(sentences)

        # 根据语言选择分词方式
        if self.language == "chinese":
            # 中文：按字符切分（简单方式）
            words = re.findall(r'[\u4e00-\u9fff]+', text)
            # 提取2-4字的词语
            words = [w for w in words if 2 <= len(w) <= 4]
        else:
            # 英文：按单词切分
            words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
            # 过滤停用词和短词
            words = [w for w in words if len(w) > 3 and w not in self.stop_words]

        # 统计词频
        word_counts = Counter(words)
        return word_counts.most_common(top_n)

    def test_lexrank(self) -> Dict:
        """测试 LexRank 算法"""
        print(f"\n{'='*70}")
        print("测试 LexRank 算法（基于图的方法，使用余弦相似度）")
        print(f"{'='*70}")

        start_time = time.time()

        summarizer = LexRankSummarizer(self.stemmer)
        summarizer.stop_words = self.stop_words

        summary_sentences = summarizer(
            self.parser.document,
            sentences_count=self.sentence_count
        )

        elapsed_time = time.time() - start_time

        sentences = [str(s) for s in summary_sentences]
        keywords = self.extract_keywords(sentences)

        # 输出结果
        print(f"\n⏱️  执行时间: {elapsed_time:.4f} 秒")
        print(f"📝 提取句子数: {len(sentences)}/{self.sentence_count}")

        print(f"\n提取的关键句子:")
        for i, sentence in enumerate(sentences, 1):
            print(f"  {i}. {sentence[:100]}{'...' if len(sentence) > 100 else ''}")

        print(f"\n🔑 Top 10 关键词:")
        for word, count in keywords[:10]:
            print(f"  {word}: {count}")

        return {
            "algorithm": "LexRank",
            "time": elapsed_time,
            "sentences": sentences,
            "keywords": keywords
        }

    def test_luhn(self) -> Dict:
        """测试 Luhn 算法"""
        print(f"\n{'='*70}")
        print("测试 Luhn 算法（基于词频和句子聚类）")
        print(f"{'='*70}")

        start_time = time.time()

        summarizer = LuhnSummarizer(self.stemmer)
        summarizer.stop_words = self.stop_words

        summary_sentences = summarizer(
            self.parser.document,
            sentences_count=self.sentence_count
        )

        elapsed_time = time.time() - start_time

        sentences = [str(s) for s in summary_sentences]
        keywords = self.extract_keywords(sentences)

        # 输出结果
        print(f"\n⏱️  执行时间: {elapsed_time:.4f} 秒")
        print(f"📝 提取句子数: {len(sentences)}/{self.sentence_count}")

        print(f"\n提取的关键句子:")
        for i, sentence in enumerate(sentences, 1):
            print(f"  {i}. {sentence[:100]}{'...' if len(sentence) > 100 else ''}")

        print(f"\n🔑 Top 10 关键词:")
        for word, count in keywords[:10]:
            print(f"  {word}: {count}")

        return {
            "algorithm": "Luhn",
            "time": elapsed_time,
            "sentences": sentences,
            "keywords": keywords
        }

    def test_textrank(self) -> Dict:
        """测试 TextRank 算法"""
        print(f"\n{'='*70}")
        print("测试 TextRank 算法（基于 PageRank 的图算法）")
        print(f"{'='*70}")

        start_time = time.time()

        summarizer = TextRankSummarizer(self.stemmer)
        summarizer.stop_words = self.stop_words

        summary_sentences = summarizer(
            self.parser.document,
            sentences_count=self.sentence_count
        )

        elapsed_time = time.time() - start_time

        sentences = [str(s) for s in summary_sentences]
        keywords = self.extract_keywords(sentences)

        # 输出结果
        print(f"\n⏱️  执行时间: {elapsed_time:.4f} 秒")
        print(f"📝 提取句子数: {len(sentences)}/{self.sentence_count}")

        print(f"\n提取的关键句子:")
        for i, sentence in enumerate(sentences, 1):
            print(f"  {i}. {sentence[:100]}{'...' if len(sentence) > 100 else ''}")

        print(f"\n🔑 Top 10 关键词:")
        for word, count in keywords[:10]:
            print(f"  {word}: {count}")

        return {
            "algorithm": "TextRank",
            "time": elapsed_time,
            "sentences": sentences,
            "keywords": keywords
        }

    def test_lsa(self) -> Dict:
        """测试 LSA 算法"""
        print(f"\n{'='*70}")
        print("测试 LSA 算法（Latent Semantic Analysis - 基于奇异值分解）")
        print(f"{'='*70}")

        start_time = time.time()

        summarizer = LsaSummarizer(self.stemmer)
        summarizer.stop_words = self.stop_words

        summary_sentences = summarizer(
            self.parser.document,
            sentences_count=self.sentence_count
        )

        elapsed_time = time.time() - start_time

        sentences = [str(s) for s in summary_sentences]
        keywords = self.extract_keywords(sentences)

        # 输出结果
        print(f"\n⏱️  执行时间: {elapsed_time:.4f} 秒")
        print(f"📝 提取句子数: {len(sentences)}/{self.sentence_count}")

        print(f"\n提取的关键句子:")
        for i, sentence in enumerate(sentences, 1):
            print(f"  {i}. {sentence[:100]}{'...' if len(sentence) > 100 else ''}")

        print(f"\n🔑 Top 10 关键词:")
        for word, count in keywords[:10]:
            print(f"  {word}: {count}")

        return {
            "algorithm": "LSA",
            "time": elapsed_time,
            "sentences": sentences,
            "keywords": keywords
        }

    def run_all_tests(self) -> List[Dict]:
        """运行所有算法测试"""
        print(f"\n{'#'*70}")
        print("Sumy 算法性能基准测试")
        print(f"{'#'*70}")
        print(f"\n文本信息:")
        print(f"  字符数: {self.char_count}")
        print(f"  句子数: {self.total_sentences}")
        print(f"  语言: {self.language}")
        print(f"  提取句子数: {self.sentence_count}")

        results = []

        # 测试所有算法
        results.append(self.test_luhn())
        results.append(self.test_textrank())

        # 输出性能对比
        self.print_performance_comparison(results)

        return results

    def print_performance_comparison(self, results: List[Dict]):
        """输出性能对比表"""
        print(f"\n{'='*70}")
        print("性能对比总结")
        print(f"{'='*70}")

        # 按执行时间排序
        sorted_results = sorted(results, key=lambda x: x['time'])

        print(f"\n⏱️  执行时间排名（从快到慢）:")
        for i, result in enumerate(sorted_results, 1):
            print(f"  {i}. {result['algorithm']:15s} - {result['time']:.4f} 秒")

        print(f"\n📊 算法特点总结:")
        print(f"  LexRank:  基于图的方法，计算句子间余弦相似度，适合多文档摘要")
        print(f"  Luhn:     基于词频统计，速度快，适合快速摘要")
        print(f"  TextRank: 基于 PageRank，考虑句子重要性传播")
        print(f"  LSA:      基于矩阵分解，捕捉潜在语义关系")
        print(f"  KL-Sum:   基于 KL 散度，选择信息量最大的句子")

        # 关键词重叠分析
        print(f"\n🔑 关键词统计:")
        for result in results:
            top_5_keywords = [w for w, _ in result['keywords'][:5]]
            print(f"  {result['algorithm']:15s}: {', '.join(top_5_keywords)}")


def detect_language(text: str) -> str:
    """自动检测文本语言"""
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    total_chars = chinese_chars + english_chars

    if total_chars == 0:
        return "english"

    chinese_ratio = chinese_chars / total_chars
    return "chinese" if chinese_ratio > 0.3 else "english"


def main():
    """主函数"""
    # 解析命令行参数
    if len(sys.argv) == 1:
        # 使用内置文本
        text = BUILTIN_TEXT
        sentence_count = 3
        print("\n使用内置示例文本")
    else:
        # 从文件读取
        file_path = sys.argv[1]
        sentence_count = int(sys.argv[2]) if len(sys.argv) > 2 else 500

        print(f"\n从文件读取: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()

    # 自动检测语言
    language = detect_language(text)
    print(f"检测到语言: {language}")

    # 创建基准测试实例
    benchmark = AlgorithmBenchmark(
        text=text,
        language=language,
        sentence_count=sentence_count
    )

    # 运行所有测试
    benchmark.run_all_tests()

    print(f"\n{'='*70}")
    print("测试完成！")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n测试被中断")
    except Exception as e:
        print(f"\n\n测试失败: {e}")
        import traceback
        traceback.print_exc()
