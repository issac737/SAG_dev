"""
文档解析Token统计测试脚本

测试10个文档的解析过程,统计每篇文章解析消耗的输入token和输出token

使用方法:
    python -m tests.token_stats.test_document_parsing_tokens
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from dataflow.modules.load.config import DocumentLoadConfig
from dataflow.modules.load.loader import DocumentLoader
from dataflow.modules.extract.config import ExtractConfig
from dataflow.modules.extract.extractor import EventExtractor
from dataflow.core.prompt.manager import PromptManager
from dataflow.db import get_session_factory, Article
from dataflow.utils import get_logger, setup_logging

# 配置日志 - 显示详细的处理过程
# 设置根logger和dataflow logger都输出
import sys
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True  # 强制重新配置
)
setup_logging(level="INFO")  # 配置dataflow命名空间

logger = get_logger("test.token_stats")


# ============================================================
# Token追踪器 - 追踪所有LLM调用
# ============================================================

class LLMCallTracker:
    """追踪所有LLM调用的token消耗"""

    def __init__(self):
        self.calls = []
        self.total = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }

    def record(self, stage: str, purpose: str, usage):
        """记录一次LLM调用"""
        if usage is None:
            return

        tokens = {
            "stage": stage,
            "purpose": purpose,
            "prompt_tokens": getattr(usage, 'prompt_tokens', 0),
            "completion_tokens": getattr(usage, 'completion_tokens', 0),
            "total_tokens": getattr(usage, 'total_tokens', 0)
        }

        self.calls.append(tokens)
        self.total["prompt_tokens"] += tokens["prompt_tokens"]
        self.total["completion_tokens"] += tokens["completion_tokens"]
        self.total["total_tokens"] += tokens["total_tokens"]

        logger.info(
            f"🤖 [{stage}] {purpose}: "
            f"输入={tokens['prompt_tokens']:,}, "
            f"输出={tokens['completion_tokens']:,}, "
            f"总计={tokens['total_tokens']:,}"
        )

    def reset(self):
        """重置统计"""
        self.calls = []
        self.total = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }

    def get_stats_by_stage(self):
        """按阶段分组统计"""
        stats = {}
        for call in self.calls:
            stage = call['stage']
            if stage not in stats:
                stats[stage] = {
                    "calls": [],
                    "total": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                }
            stats[stage]["calls"].append(call)
            stats[stage]["total"]["prompt_tokens"] += call["prompt_tokens"]
            stats[stage]["total"]["completion_tokens"] += call["completion_tokens"]
            stats[stage]["total"]["total_tokens"] += call["total_tokens"]
        return stats


# 全局追踪器
_llm_tracker = LLMCallTracker()


def enable_llm_tracking():
    """启用LLM调用追踪"""
    from dataflow.core.ai import llm

    original_chat = llm.OpenAIClient.chat

    async def tracked_chat(self, messages, **kwargs):
        # 调用原始方法
        result = await original_chat(self, messages, **kwargs)

        # 判断调用来源
        import inspect
        frame = inspect.currentframe()
        stage = "UNKNOWN"
        purpose = "LLM调用"

        # 向上查找调用栈
        try:
            for _ in range(15):
                if frame is None:
                    break
                frame = frame.f_back
                if frame and 'self' in frame.f_locals:
                    obj = frame.f_locals['self']
                    class_name = obj.__class__.__name__

                    if 'SumySummarizer' in class_name or 'DocumentProcessor' in class_name:
                        stage = "LOAD"
                        purpose = "生成元数据(标题/摘要/分类/标签)"
                        break
                    elif 'ExtractorAgent' in class_name:
                        stage = "EXTRACT"
                        purpose = "提取事项"
                        break
                    elif 'EventExtractor' in class_name:
                        stage = "EXTRACT"
                        purpose = "提取事项"
                        break
        except:
            pass

        # 记录usage
        if hasattr(result, 'usage'):
            _llm_tracker.record(stage, purpose, result.usage)

        return result

    # 替换方法
    llm.OpenAIClient.chat = tracked_chat
    logger.info("✅ LLM调用追踪已启用")


# 在模块加载时启用追踪
enable_llm_tracking()


class DocumentTokenStats:
    """文档解析Token统计器"""

    def __init__(self, source_config_id: str):
        """
        初始化统计器

        Args:
            source_config_id: 源配置ID (字符串类型)
        """
        self.source_config_id = source_config_id
        self.doc_stats: List[Dict] = []
        self.total_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        self.session_factory = get_session_factory()

    async def process_document(self, file_path: str, doc_index: int, background: Optional[str] = None):
        """
        处理单个文档并统计token

        Args:
            file_path: 文档路径
            doc_index: 文档索引(从0开始)
            background: 背景信息(可选)
        """
        print(f"\n{'=' * 80}")
        print(f"📄 处理文档 {doc_index + 1}: {Path(file_path).name}")
        print(f"{'=' * 80}")

        start_time = datetime.now()

        # 重置全局追踪器
        _llm_tracker.reset()

        try:
            # 1. 加载文档
            logger.info("步骤1: 加载文档...")

            # 使用DocumentLoader直接加载
            # 注意: DocumentLoader会自动创建source_config(如果不存在)
            loader = DocumentLoader()

            # 构建加载配置
            load_config = DocumentLoadConfig(
                source_config_id=str(self.source_config_id),  # 确保是字符串
                path=file_path,
                background=background or "测试文档解析token消耗",
                auto_vector=True,  # 自动生成向量
            )

            # 加载文档
            load_result = await loader.load(load_config)
            article_id = load_result.source_id

            # 从数据库获取article对象
            async with self.session_factory() as session:
                article = await session.get(Article, article_id)
                if not article:
                    raise Exception(f"未找到文章: {article_id}")

            logger.info(f"文档已加载: article_id={article.id}, title={article.title}")

            # 2. 提取事项(这里会调用LLM)
            logger.info("步骤2: 提取事项...")

            # 创建提取器
            prompt_manager = PromptManager()
            extractor = EventExtractor(
                prompt_manager=prompt_manager,
                model_config=None  # 使用默认配置
            )

            # 获取该文档的所有chunks
            async with self.session_factory() as session:
                from sqlalchemy import select
                from dataflow.db import SourceChunk

                result = await session.execute(
                    select(SourceChunk)
                    .where(SourceChunk.source_id == article.id)
                    .where(SourceChunk.source_type == "ARTICLE")
                    .order_by(SourceChunk.rank)
                )
                chunks = list(result.scalars().all())

            if not chunks:
                logger.warning("未找到chunks,跳过提取")
                return

            logger.info(f"找到 {len(chunks)} 个chunks")

            # 构建提取配置
            extract_config = ExtractConfig(
                source_config_id=str(self.source_config_id),  # 添加必需的source_config_id
                chunk_ids=[chunk.id for chunk in chunks],
                parallel=True,
                max_concurrency=5,
            )

            # 执行提取
            events = await extractor.extract(extract_config)

            # 记录耗时
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # 获取按阶段分组的统计 - 使用tracker的完整统计
            stage_stats = _llm_tracker.get_stats_by_stage()

            # 统计信息 - 使用tracker的总计(包含Load和Extract)
            doc_stat = {
                "index": doc_index + 1,
                "filename": Path(file_path).name,
                "article_id": article.id,
                "article_title": article.title,
                "chunks_count": len(chunks),
                "events_count": len(events),
                "prompt_tokens": _llm_tracker.total["prompt_tokens"],
                "completion_tokens": _llm_tracker.total["completion_tokens"],
                "total_tokens": _llm_tracker.total["total_tokens"],
                "duration_seconds": duration,
                "stage_stats": stage_stats,  # 添加阶段统计
            }

            self.doc_stats.append(doc_stat)

            # 累加总计
            self.total_usage["prompt_tokens"] += _llm_tracker.total["prompt_tokens"]
            self.total_usage["completion_tokens"] += _llm_tracker.total["completion_tokens"]
            self.total_usage["total_tokens"] += _llm_tracker.total["total_tokens"]

            # 打印详细统计
            print(f"\n{'─' * 80}")
            print("📊 Token消耗详细统计:")
            print(f"{'─' * 80}")

            # Load阶段统计
            if "LOAD" in stage_stats:
                load_total = stage_stats["LOAD"]["total"]
                print(f"\n📂 Load阶段 (文档加载+元数据生成):")
                print(f"   输入Token:  {load_total['prompt_tokens']:>12,}")
                print(f"   输出Token:  {load_total['completion_tokens']:>12,}")
                print(f"   总计Token:  {load_total['total_tokens']:>12,}")

            # Extract阶段统计
            if "EXTRACT" in stage_stats:
                extract_total = stage_stats["EXTRACT"]["total"]
                print(f"\n🔍 Extract阶段 (事项提取):")
                print(f"   输入Token:  {extract_total['prompt_tokens']:>12,}")
                print(f"   输出Token:  {extract_total['completion_tokens']:>12,}")
                print(f"   总计Token:  {extract_total['total_tokens']:>12,}")

            # 总计
            print(f"\n{'─' * 80}")
            print(f"✅ 总输入Token:  {_llm_tracker.total['prompt_tokens']:>12,}")
            print(f"✅ 总输出Token:  {_llm_tracker.total['completion_tokens']:>12,}")
            print(f"✅ 总计Token:    {_llm_tracker.total['total_tokens']:>12,}")
            print(f"{'─' * 80}")
            print(f"📊 提取事项:  {len(events):>12} 个")
            print(f"📊 文档片段:  {len(chunks):>12} 个")
            print(f"⏱️  处理耗时:  {duration:>12.2f} 秒")

        except Exception as e:
            logger.error(f"处理文档失败: {e}", exc_info=True)
            print(f"❌ 处理失败: {e}")

            # 记录失败的文档
            doc_stat = {
                "index": doc_index + 1,
                "filename": Path(file_path).name,
                "error": str(e),
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
            self.doc_stats.append(doc_stat)

    def print_summary(self):
        """打印汇总统计"""
        print(f"\n{'=' * 120}")
        print("📊 Token消耗统计汇总")
        print(f"{'=' * 120}\n")

        # 表头
        print(
            f"{'序号':>4} | {'文件名':<35} | {'事项数':>8} | "
            f"{'Load Token':>14} | {'Extract Token':>14} | {'总Token':>14} | {'耗时(秒)':>10}"
        )
        print("-" * 120)

        # 明细
        for stat in self.doc_stats:
            if "error" in stat:
                print(
                    f"{stat['index']:>4} | {stat['filename']:<35} | "
                    f"{'失败':>8} | {'-':>14} | {'-':>14} | {'-':>14} | {'-':>10}"
                )
            else:
                # 计算Load和Extract的token
                stage_stats = stat.get('stage_stats', {})
                load_tokens = stage_stats.get('LOAD', {}).get('total', {}).get('total_tokens', 0)
                extract_tokens = stage_stats.get('EXTRACT', {}).get('total', {}).get('total_tokens', 0)

                print(
                    f"{stat['index']:>4} | {stat['filename']:<35} | "
                    f"{stat['events_count']:>8,} | "
                    f"{load_tokens:>14,} | "
                    f"{extract_tokens:>14,} | "
                    f"{stat['total_tokens']:>14,} | "
                    f"{stat['duration_seconds']:>10.2f}"
                )

        print("-" * 120)

        # 统计成功的文档数
        success_docs = [s for s in self.doc_stats if "error" not in s]
        total_docs = len(self.doc_stats)
        success_count = len(success_docs)

        # 总计
        total_events = sum(s.get("events_count", 0) for s in success_docs)
        total_duration = sum(s.get("duration_seconds", 0) for s in success_docs)

        # 计算各阶段总token
        total_load_tokens = 0
        total_extract_tokens = 0
        for stat in success_docs:
            stage_stats = stat.get('stage_stats', {})
            total_load_tokens += stage_stats.get('LOAD', {}).get('total', {}).get('total_tokens', 0)
            total_extract_tokens += stage_stats.get('EXTRACT', {}).get('total', {}).get('total_tokens', 0)

        print(
            f"{'总计':>4} | {f'{success_count}/{total_docs} 个文档':<35} | "
            f"{total_events:>8,} | "
            f"{total_load_tokens:>14,} | "
            f"{total_extract_tokens:>14,} | "
            f"{self.total_usage['total_tokens']:>14,} | "
            f"{total_duration:>10.2f}"
        )

        if success_count > 0:
            # 平均值
            avg_events = total_events / success_count
            avg_load = total_load_tokens / success_count
            avg_extract = total_extract_tokens / success_count
            avg_total = self.total_usage["total_tokens"] / success_count
            avg_duration = total_duration / success_count

            print(
                f"{'平均':>4} | {'':<35} | "
                f"{avg_events:>8,.1f} | "
                f"{avg_load:>14,.0f} | "
                f"{avg_extract:>14,.0f} | "
                f"{avg_total:>14,.0f} | "
                f"{avg_duration:>10.2f}"
            )

        print(f"\n{'=' * 120}\n")

        # 阶段占比分析
        if total_load_tokens + total_extract_tokens > 0:
            print("📊 各阶段Token占比:")
            print(f"   Load阶段 (元数据生成):  {total_load_tokens:>12,} tokens ({total_load_tokens/(total_load_tokens+total_extract_tokens)*100:>5.1f}%)")
            print(f"   Extract阶段 (事项提取): {total_extract_tokens:>12,} tokens ({total_extract_tokens/(total_load_tokens+total_extract_tokens)*100:>5.1f}%)")
            print(f"   总计:                    {total_load_tokens+total_extract_tokens:>12,} tokens\n")

        # 成本估算(基于302.AI的Qwen3-30B定价,假设每百万token价格)
        # 注意: 请根据实际API定价修改这里的价格
        input_price_per_m = 1.0  # 每百万输入token的价格(美元)
        output_price_per_m = 1.0  # 每百万输出token的价格(美元)

        input_cost = (self.total_usage["prompt_tokens"] / 1_000_000) * input_price_per_m
        output_cost = (self.total_usage["completion_tokens"] / 1_000_000) * output_price_per_m
        total_cost = input_cost + output_cost

        print("💰 成本估算 (基于假设定价: $1.0/M tokens)")
        print(f"   输入成本: ${input_cost:.4f}")
        print(f"   输出成本: ${output_cost:.4f}")
        print(f"   总成本:   ${total_cost:.4f}")
        print()

    def export_to_csv(self, output_path: str = "token_stats.csv"):
        """
        导出统计结果为CSV文件

        Args:
            output_path: 输出文件路径
        """
        import csv

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "序号",
                "文件名",
                "文章ID",
                "文章标题",
                "片段数",
                "事项数",
                "Load阶段Token",
                "Extract阶段Token",
                "输入Token",
                "输出Token",
                "总Token",
                "耗时(秒)",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            writer.writeheader()
            for stat in self.doc_stats:
                if "error" not in stat:
                    # 计算各阶段token
                    stage_stats = stat.get('stage_stats', {})
                    load_tokens = stage_stats.get('LOAD', {}).get('total', {}).get('total_tokens', 0)
                    extract_tokens = stage_stats.get('EXTRACT', {}).get('total', {}).get('total_tokens', 0)

                    writer.writerow(
                        {
                            "序号": stat["index"],
                            "文件名": stat["filename"],
                            "文章ID": stat.get("article_id", ""),
                            "文章标题": stat.get("article_title", ""),
                            "片段数": stat.get("chunks_count", 0),
                            "事项数": stat.get("events_count", 0),
                            "Load阶段Token": load_tokens,
                            "Extract阶段Token": extract_tokens,
                            "输入Token": stat["prompt_tokens"],
                            "输出Token": stat["completion_tokens"],
                            "总Token": stat["total_tokens"],
                            "耗时(秒)": f"{stat.get('duration_seconds', 0):.2f}",
                        }
                    )

        logger.info(f"统计结果已导出到: {output_path}")


async def main():
    """主测试函数"""

    # ============================================================
    # 配置区域 - 请根据实际情况修改
    # ============================================================

    # 1. 源配置ID (需要先创建source_config)
    # 注意: source_config_id 必须是字符串类型
    # 每次测试使用新的ID避免数据冲突
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    SOURCE_CONFIG_ID = f"token-test-source"  # 使用时间戳生成唯一ID

    # 2. 测试文档列表 - 自动遍历目录下所有md文件
    # 支持格式: .md, .pdf, .html, .txt
    data_dir = Path("tests/token_stats/data")

    # 自动获取所有 .md 文件
    test_documents = [str(f) for f in data_dir.glob("*.md")]

    # 或者手动指定文件列表:
    # test_documents = [
    #     "tests\\token_stats\\data\\文件1.md",
    #     "tests\\token_stats\\data\\文件2.md",
    # ]
    print(test_documents)
    # 3. 背景信息 (可选)
    background = "这是一批测试文档,用于统计文档解析的token消耗"

    # 4. 限制处理文档数量 (用于测试,None表示处理全部)
    MAX_DOCS = 10

    # ============================================================

    print("=" * 80)
    print("📊 文档解析Token统计测试")
    print("=" * 80)
    print(f"源配置ID: {SOURCE_CONFIG_ID}")
    print(f"文档数量: {min(len(test_documents), MAX_DOCS) if MAX_DOCS else len(test_documents)}")
    print("=" * 80)

    # 检查文档是否存在
    valid_docs = []
    for doc_path in test_documents:
        if Path(doc_path).exists():
            valid_docs.append(doc_path)
        else:
            logger.warning(f"文档不存在,跳过: {doc_path}")

    if not valid_docs:
        logger.error("没有找到有效的测试文档,请检查文档路径配置")
        return

    # 限制文档数量
    if MAX_DOCS:
        valid_docs = valid_docs[:MAX_DOCS]

    print(f"\n找到 {len(valid_docs)} 个有效文档\n")

    # 创建统计器
    stats = DocumentTokenStats(source_config_id=SOURCE_CONFIG_ID)

    # 依次处理文档
    for idx, doc_path in enumerate(valid_docs):
        await stats.process_document(doc_path, idx, background)

    # 打印汇总
    stats.print_summary()

    # 导出CSV
    output_csv = "token_stats_result.csv"
    stats.export_to_csv(output_csv)
    print(f"📄 详细数据已导出到: {output_csv}\n")


if __name__ == "__main__":
    asyncio.run(main())
