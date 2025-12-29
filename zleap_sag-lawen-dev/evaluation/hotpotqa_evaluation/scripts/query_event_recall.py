#!/usr/bin/env python3
"""
Query Event Recall 测试脚本

简化版：输出问题、召回的事项和对应的段落
"""

import json
import sys
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"[INFO] Loaded environment variables: {env_path}")
else:
    print(f"[WARN] .env file not found: {env_path}")

# Import ES and Embedding clients
from dataflow.core.storage.elasticsearch import ElasticsearchClient, ESConfig
from dataflow.core.ai.embedding import EmbeddingClient
from dataflow.core.storage.repositories.event_repository import EventVectorRepository

# Import database
from dataflow.db import get_session_factory, SourceEvent, SourceChunk
from sqlalchemy import select, and_

# Import recall metrics
from evaluation.hotpotqa_evaluation.scripts.recall_metrics import RecallCalculator, RecallResult


class SimpleEventSearcher:
    """简单的事项向量搜索器"""

    def __init__(self):
        """初始化搜索器"""
        # 初始化 ES 客户端
        es_client = ElasticsearchClient(config=ESConfig.from_env())

        # 初始化 EventVectorRepository
        self.event_repo = EventVectorRepository(es_client=es_client)

        # 初始化 Embedding 客户端
        self.embedding_client = EmbeddingClient()

        # 初始化数据库会话工厂
        self.session_factory = get_session_factory()

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        if not vec1 or not vec2:
            return 0.0

        try:
            v1 = np.array(vec1, dtype=np.float32)
            v2 = np.array(vec2, dtype=np.float32)

            if len(v1) != len(v2):
                return 0.0

            dot_product = np.dot(v1, v2)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            similarity = dot_product / (norm1 * norm2)
            return float(np.clip(similarity, -1.0, 1.0))

        except Exception as e:
            print(f"      [ERROR] 余弦相似度计算失败: {e}")
            return 0.0

    async def check_es_data(self):
        """检查ES中的事项数据情况"""
        es_client = self.event_repo.es_client.client

        # 1. 获取总数
        count_result = await es_client.count(index="event_vectors")
        total_count = count_result['count']
        print(f"      [DEBUG] ES中event_vectors总数: {total_count}")

        # 2. 聚合查询，获取所有不同的source_config_id
        agg_query = {
            "size": 0,
            "aggs": {
                "source_configs": {
                    "terms": {
                        "field": "source_config_id",
                        "size": 100
                    }
                }
            }
        }

        response = await es_client.search(index="event_vectors", body=agg_query)

        if 'aggregations' in response and 'source_configs' in response['aggregations']:
            buckets = response['aggregations']['source_configs']['buckets']
            print(f"      [DEBUG] ES中的source_config_id列表:")
            for bucket in buckets:
                print(f"         - {bucket['key']}: {bucket['doc_count']} 个事项")

        # 3. 如果总数为0，给出提示
        if total_count == 0:
            print(f"      [WARNING] ES中没有任何事项数据！请先导入数据。")

        return total_count

    async def search(
        self,
        query: str,
        source_config_id: str,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        向量搜索事项

        Args:
            query: 查询文本
            source_config_id: 数据源配置ID
            top_k: 返回事项数量

        Returns:
            事项列表
        """
        # 1. 生成 query 的 embedding
        query_vector = await self.embedding_client.generate(query)

        # 2. 使用 EventVectorRepository 搜索
        print(f"      [DEBUG] source_config_id: {source_config_id}, top_k: {top_k}")
        print(f"      [DEBUG] query_vector维度: {len(query_vector)}")

        results = await self.event_repo.search_similar_by_content(
            query_vector=query_vector,
            k=top_k,
            source_config_id=source_config_id
        )

        print(f"      [DEBUG] 搜索返回结果数: {len(results)}")
        if results:
            print(f"      [DEBUG] 第一个结果字段: {list(results[0].keys())}")

        # 3. 转换为统一格式，并手动计算余弦相似度
        events = []
        for hit in results:
            event_id = hit.get('event_id', '')
            es_score = hit.get('_score', 0.0)

            # 获取事项的 content_vector（从 ES 结果中）
            content_vector = hit.get('content_vector', None)

            # 手动计算余弦相似度
            if content_vector:
                manual_cosine_similarity = self._cosine_similarity(query_vector, content_vector)
            else:
                manual_cosine_similarity = None
                print(f"      [WARN] event {event_id[:8]}... 没有 content_vector")

            events.append({
                'event_id': event_id,
                'title': hit.get('title', ''),
                'content': hit.get('content', ''),
                'summary': hit.get('summary', ''),
                'category': hit.get('category', ''),
                'start_time': hit.get('start_time', ''),
                'end_time': hit.get('end_time', ''),
                'score': es_score,
                'cosine_similarity': manual_cosine_similarity,
                'weight': es_score
            })

        return events

    async def get_chunks_from_events(
        self,
        source_config_id: str,
        event_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        从事项列表获取去重后的段落信息

        Args:
            source_config_id: 信息源ID
            event_ids: 事项ID列表

        Returns:
            去重后的段落列表
        """
        if not event_ids:
            return []

        async with self.session_factory() as session:
            # 1. 查询事项，获取 chunk_id
            event_query = (
                select(SourceEvent.id, SourceEvent.chunk_id)
                .where(
                    and_(
                        SourceEvent.source_config_id == source_config_id,
                        SourceEvent.id.in_(event_ids),
                        SourceEvent.chunk_id.isnot(None)  # 过滤掉没有 chunk_id 的事项
                    )
                )
            )

            event_result = await session.execute(event_query)
            events = event_result.all()

            print(f"      [DEBUG] 查询到 {len(events)} 个事项有 chunk_id")

            # 2. 提取并去重 chunk_id
            chunk_ids = list(set([e.chunk_id for e in events]))

            if not chunk_ids:
                print(f"      [WARN] 没有找到任何 chunk_id")
                return []

            print(f"      [DEBUG] 去重后有 {len(chunk_ids)} 个唯一 chunk_id")

            # 3. 查询段落信息
            chunk_query = (
                select(SourceChunk)
                .where(
                    and_(
                        SourceChunk.source_config_id == source_config_id,
                        SourceChunk.id.in_(chunk_ids)
                    )
                )
                .order_by(SourceChunk.rank)  # 按 rank 排序
            )

            chunk_result = await session.execute(chunk_query)
            chunks = chunk_result.scalars().all()

            print(f"      [DEBUG] 查询到 {len(chunks)} 个段落")

            # 4. 转换为字典列表
            return [
                {
                    'chunk_id': chunk.id,
                    'heading': chunk.heading or '',
                    'content': chunk.content or '',
                    'rank': chunk.rank,
                    'source_config_id': chunk.source_config_id
                }
                for chunk in chunks
            ]

    async def cleanup(self):
        """清理资源"""
        if hasattr(self.event_repo, 'es_client') and hasattr(self.event_repo.es_client, 'client'):
            await self.event_repo.es_client.client.close()


def load_questions(questions_path: Path) -> List[Dict[str, Any]]:
    """加载问题列表"""
    print(f"[INFO] 加载问题列表: {questions_path}")
    questions = []
    with open(questions_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    q = json.loads(line)
                    questions.append(q)
                except json.JSONDecodeError as e:
                    print(f"[WARN] 第 {line_num} 行JSON解析失败: {e}")

    print(f"[INFO] 问题加载完成，共 {len(questions)} 个问题")
    return questions


def load_corpus(corpus_path: Path) -> Dict[str, Dict[str, str]]:
    """加载语料库"""
    print(f"[INFO] 加载语料库: {corpus_path}")
    corpus_dict = {}
    with open(corpus_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    chunk = json.loads(line)
                    chunk_id = chunk['id']

                    # 处理合并的ID
                    if "//" in chunk_id:
                        original_ids = chunk_id.split("//")
                        for original_id in original_ids:
                            corpus_dict[original_id] = {
                                'title': chunk.get('title', ''),
                                'text': chunk.get('text', '')
                            }
                    else:
                        corpus_dict[chunk_id] = {
                            'title': chunk.get('title', ''),
                            'text': chunk.get('text', '')
                        }
                except json.JSONDecodeError as e:
                    print(f"[WARN] 第 {line_num} 行JSON解析失败: {e}")

    print(f"[INFO] 语料库加载完成，共 {len(corpus_dict)} 个段落")
    return corpus_dict


def find_latest_source_dir(base_dir: Path) -> Path:
    """查找最新的源数据文件夹"""
    print(f"[INFO] 查找最新的源数据文件夹: {base_dir}")

    if not base_dir.exists():
        print(f"[ERROR] 源数据目录不存在: {base_dir}")
        sys.exit(1)

    dirs = [d for d in base_dir.iterdir() if d.is_dir()]

    if not dirs:
        print(f"[ERROR] 源数据目录下没有文件夹: {base_dir}")
        sys.exit(1)

    dirs.sort(key=lambda x: x.name, reverse=True)
    latest_dir = dirs[0]
    print(f"[INFO] 找到最新文件夹: {latest_dir.name}")

    return latest_dir


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='Query Event Recall 测试脚本')
    parser.add_argument('--source-config-id', type=str, required=False, default=None,
                       help='数据源配置ID (如果不指定，将从源目录的 process_result.json 中读取)')
    parser.add_argument('--input', type=Path, required=False, default=None,
                       help='问题列表文件路径 (JSONL格式)。如果未指定，将使用最新源数据目录下的 oracle.jsonl')
    parser.add_argument('--corpus', type=Path, required=False, default=None,
                       help='语料库文件路径 (JSONL格式)。如果未指定，将使用最新源数据目录下的 corpus.jsonl')
    parser.add_argument('--source-dir', type=Path, required=False, default=None,
                       help='源数据目录路径 (包含 oracle.jsonl)。如果未指定，将自动查找最新目录')
    parser.add_argument('--max-questions', type=int, default=None,
                       help='最大处理问题数（默认: 全部）')
    parser.add_argument('--top-k', type=int, default=100,
                       help='每个问题返回的事项数量（默认: 10）')
    parser.add_argument('--output', type=Path, required=False, default=None,
                       help='保存搜索结果的文件路径（JSONL格式）')
    parser.add_argument('--show-events', action='store_true', default=False,
                       help='是否显示召回的事项信息（默认: 只显示段落）')

    args = parser.parse_args()

    # 获取脚本所在目录作为基准
    script_dir = Path(__file__).parent
    eval_base_dir = script_dir.parent

    # 确定源数据目录
    if args.source_dir:
        source_dir = Path(args.source_dir)
        print(f"[INFO] 使用指定的源数据目录: {source_dir}")
    else:
        base_dir = eval_base_dir / "data" / "source"
        source_dir = find_latest_source_dir(base_dir)
        print(f"[INFO] 自动选择最新源数据目录: {source_dir}")

    # 确定 source_config_id
    if args.source_config_id:
        source_config_id = args.source_config_id
        print(f"[INFO] 使用指定的 source_config_id: {source_config_id}")
    else:
        # 从 process_result.json 中读取
        process_result_file = source_dir / "process_result.json"
        if process_result_file.exists():
            with open(process_result_file, 'r', encoding='utf-8') as f:
                process_result = json.load(f)
                source_config_id = process_result.get('source_config_id')
                if source_config_id:
                    print(f"[INFO] 从 process_result.json 读取 source_config_id: {source_config_id}")
                else:
                    print(f"[ERROR] process_result.json 中没有 source_config_id 字段")
                    sys.exit(1)
        else:
            print(f"[ERROR] 未找到 process_result.json: {process_result_file}")
            print(f"[ERROR] 请使用 --source-config-id 参数手动指定")
            sys.exit(1)

    # 确定输入文件
    if args.input:
        input_file = Path(args.input)
    else:
        input_file = source_dir / "oracle.jsonl"
        if not input_file.exists():
            print(f"[ERROR] 源数据目录下找不到 oracle.jsonl: {input_file}")
            sys.exit(1)
        print(f"[INFO] 使用源数据目录下的 oracle.jsonl: {input_file}")

    # 验证文件
    if not input_file.exists():
        print(f"[ERROR] 问题文件不存在: {input_file}")
        sys.exit(1)

    # 确定语料库文件
    if args.corpus:
        corpus_file = Path(args.corpus)
    else:
        corpus_file = source_dir / "corpus.jsonl"
        if not corpus_file.exists():
            print(f"[ERROR] 源数据目录下找不到 corpus.jsonl: {corpus_file}")
            sys.exit(1)
        print(f"[INFO] 使用源数据目录下的 corpus.jsonl: {corpus_file}")

    if not corpus_file.exists():
        print(f"[ERROR] 语料库文件不存在: {corpus_file}")
        sys.exit(1)

    # 确定输出目录 (data/query_event_chunk/时间戳)
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = eval_base_dir / "data" / "query_event_chunk" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] 输出目录: {output_dir}")

    # 设置输出文件路径
    if args.output:
        output_file = Path(args.output)
    else:
        output_file = output_dir / "results.jsonl"
    print(f"[INFO] 结果文件: {output_file}")

    # 加载数据
    corpus_dict = load_corpus(corpus_file)
    questions = load_questions(input_file)

    # 限制问题数
    if args.max_questions:
        questions = questions[:args.max_questions]
        print(f"[INFO] 限制处理前 {args.max_questions} 个问题")

    # 输出问题和召回的事项
    print("\n" + "="*80)
    print("开始处理问题并执行事项向量搜索")
    print("="*80)

    # 初始化搜索器
    print("\n[INFO] 初始化事项向量搜索器...")
    searcher = SimpleEventSearcher()
    print("[INFO] 搜索器初始化完成")

    # 检查ES数据
    print("\n[INFO] 检查ES中的事项数据...")
    await searcher.check_es_data()
    print()

    # 用于保存所有结果
    all_results = []
    total_recall = 0.0
    total_questions_with_oracle = 0

    for i, q in enumerate(questions, 1):
        question_id = q.get('id', 'unknown')
        question = q.get('question', '')
        answer = q.get('answer', '')
        oracle_chunk_ids = q.get('oracle_chunk_ids', [])

        print(f"\n{'='*80}")
        print(f"[{i}/{len(questions)}] ID: {question_id}")
        print(f"❓ 问题: {question}")
        print(f"✅ 答案: {answer}")
        print(f"📌 标准答案段落数: {len(oracle_chunk_ids)}")

        # 显示标准答案段落的详细内容
        if oracle_chunk_ids and corpus_dict:
            print(f"\n   标准答案段落:")
            for j, chunk_id in enumerate(oracle_chunk_ids, 1):
                if chunk_id in corpus_dict:
                    chunk = corpus_dict[chunk_id]
                    title = chunk.get('title', 'N/A')
                    text = chunk.get('text', '')[:200]  # 限制预览长度

                    print(f"   [{j}] {title}")
                    print(f"       {text}...")
                else:
                    print(f"   [{j}] chunk_id: {chunk_id} (未找到对应段落)")

        # 执行事项向量搜索
        print(f"\n🔍 执行事项向量搜索 (top-{args.top_k})...")
        try:
            import time
            start_time = time.time()
            search_results = await searcher.search(
                query=question,
                source_config_id=source_config_id,
                top_k=args.top_k
            )
            search_time = time.time() - start_time

            print(f"   搜索完成，找到 {len(search_results)} 个事项 (耗时: {search_time:.3f}秒)")

            # 显示搜索结果（可选）
            if args.show_events:
                print(f"\n   检索到的事项:")
                for idx, event in enumerate(search_results, 1):
                    event_id = event.get('event_id', '')
                    title = event.get('title', 'N/A')
                    content = event.get('content', '')[:200]  # 限制长度
                    summary = event.get('summary', '')[:100]  # 限制长度
                    category = event.get('category', 'N/A')
                    start_time_str = event.get('start_time', 'N/A')
                    es_score = event.get('score', 0.0)
                    manual_cosine = event.get('cosine_similarity', None)

                    print(f"   [{idx}] {title}")
                    print(f"       事项ID: {event_id[:16]}...")
                    print(f"       分类: {category}")
                    print(f"       时间: {start_time_str}")
                    if summary:
                        print(f"       摘要: {summary}...")
                    print(f"       ES Score: {es_score:.4f}")
                    if manual_cosine is not None:
                        print(f"       Cosine Similarity: {manual_cosine:.4f}")
                        diff = abs(es_score - manual_cosine)
                        print(f"       差异: {diff:.4f}")
                    else:
                        print(f"       Cosine Similarity: N/A (无向量)")
                    print(f"       内容: {content}...")

            # 🆕 获取段落信息
            print(f"\n📄 从事项中提取段落信息...")
            event_ids = [e.get('event_id', '') for e in search_results]
            chunks = await searcher.get_chunks_from_events(
                source_config_id=source_config_id,
                event_ids=event_ids
            )

            print(f"   提取到 {len(chunks)} 个唯一段落")

            # 准备召回率计算所需的数据
            # 1. 准备 oracle chunks（标准答案段落）
            oracle_chunks_for_calc = []
            for chunk_id in oracle_chunk_ids:
                if chunk_id in corpus_dict:
                    chunk = corpus_dict[chunk_id]
                    oracle_chunks_for_calc.append({
                        'chunk_id': chunk_id,
                        'title': chunk.get('title', ''),
                        'text': chunk.get('text', '')
                    })

            # 2. 将提取的 chunks 转换为召回计算格式
            retrieved_sections = [
                {
                    'chunk_id': c.get('chunk_id', ''),
                    'heading': c.get('heading', ''),
                    'content': c.get('content', ''),
                    'score': 1.0  # 段落通过事项召回，不使用分数排序
                }
                for c in chunks
            ]

            # 3. 使用 RecallCalculator 计算召回率
            recall_result = RecallCalculator.calculate(
                question_id=question_id,
                oracle_chunks=oracle_chunks_for_calc,
                retrieved_sections=retrieved_sections,
                verbose=False
            )

            # 显示召回统计
            print(f"\n   📊 召回统计: {recall_result.recalled}/{recall_result.total_oracle} ({recall_result.recall:.2%})")
            if recall_result.recalled_details:
                print(f"   匹配详情:")
                for detail in recall_result.recalled_details[:5]:  # 只显示前5个
                    print(f"      - {detail['oracle_title']} <-> {detail['retrieved_heading']}")
                if len(recall_result.recalled_details) > 5:
                    print(f"      ... 还有 {len(recall_result.recalled_details) - 5} 个匹配")

            if chunks:
                print(f"\n   段落详情:")
                for idx, chunk in enumerate(chunks, 1):
                    chunk_id = chunk.get('chunk_id', '')
                    heading = chunk.get('heading', 'N/A')
                    content = chunk.get('content', '')[:300]  # 限制长度
                    rank = chunk.get('rank', 0)

                    # 检查是否命中标准答案
                    is_hit = ''
                    for detail in recall_result.recalled_details:
                        if detail.get('retrieved_chunk_id') == chunk_id:
                            is_hit = '✅ 命中'
                            break

                    print(f"   [{idx}] {heading} {is_hit}")
                    print(f"       段落ID: {chunk_id[:16]}...")
                    print(f"       排序: {rank}")
                    print(f"       内容: {content}...")
                    print()

            # 累计统计
            if recall_result.total_oracle > 0:
                total_recall += recall_result.recall
                total_questions_with_oracle += 1

            # 保存结果
            result = {
                'question_id': question_id,
                'question': question,
                'answer': answer,
                'oracle_chunk_ids': oracle_chunk_ids,
                'search_results': [
                    {
                        'event_id': e.get('event_id', ''),
                        'title': e.get('title', ''),
                        'content': e.get('content', ''),
                        'summary': e.get('summary', ''),
                        'category': e.get('category', ''),
                        'start_time': e.get('start_time', ''),
                        'score': e.get('score', 0.0),
                        'cosine_similarity': e.get('cosine_similarity', None)
                    }
                    for e in search_results
                ],
                'chunks': [
                    {
                        'chunk_id': c.get('chunk_id', ''),
                        'heading': c.get('heading', ''),
                        'content': c.get('content', ''),
                        'rank': c.get('rank', 0)
                    }
                    for c in chunks
                ],
                'recall': recall_result.recall,
                'total_oracle': recall_result.total_oracle,
                'recalled': recall_result.recalled,
                'retrieved': recall_result.retrieved,
                'recalled_details': recall_result.recalled_details,
                'search_time': search_time
            }
            all_results.append(result)

        except Exception as e:
            print(f"   ⚠️ 搜索失败: {e}")
            import traceback
            traceback.print_exc()

            # 保存失败记录
            all_results.append({
                'question_id': question_id,
                'question': question,
                'answer': answer,
                'oracle_chunk_ids': oracle_chunk_ids,
                'error': str(e),
                'search_results': [],
                'chunks': []
            })

    # 打印总体统计
    print("\n" + "="*80)
    print("📊 总体统计")
    print("="*80)
    print(f"总问题数: {len(questions)}")
    print(f"成功搜索: {sum(1 for r in all_results if 'error' not in r)} 个")
    print(f"搜索失败: {sum(1 for r in all_results if 'error' in r)} 个")

    # 统计平均召回事项数和段落数
    successful_results = [r for r in all_results if 'error' not in r]
    if successful_results:
        avg_events = sum(len(r['search_results']) for r in successful_results) / len(successful_results)
        avg_chunks = sum(len(r.get('chunks', [])) for r in successful_results) / len(successful_results)
        print(f"平均召回事项数: {avg_events:.2f}")
        print(f"平均提取段落数: {avg_chunks:.2f}")

    # 召回率统计
    if total_questions_with_oracle > 0:
        avg_recall = total_recall / total_questions_with_oracle
        print(f"\n平均召回率: {avg_recall:.2%}")
        print(f"  计算方式: 宏平均 (Macro Average)")
        print(f"  公式: Σ(每个问题的召回率) / 问题总数")
        print(f"  说明: 每个问题权重相同，不论其标准答案数量")

        # 统计不同召回情况的问题数
        perfect_recall = 0  # 完美召回（100%）
        partial_recall = 0  # 部分召回（0% < recall < 100%）
        zero_recall = 0     # 零召回（0%）

        # 统计部分召回的详细情况
        from collections import defaultdict
        partial_recall_details = defaultdict(int)  # {召回数量: 问题数}

        # 统计总的标准答案数和召回数（用于计算微平均）
        total_oracle_chunks = 0
        total_recalled_chunks = 0

        for result in all_results:
            if 'error' in result:
                continue

            recall = result.get('recall', 0.0)
            recalled_count = result.get('recalled', 0)
            total_oracle_count = result.get('total_oracle', 0)

            total_oracle_chunks += total_oracle_count
            total_recalled_chunks += recalled_count

            if recall >= 1.0:
                perfect_recall += 1
            elif recall > 0.0:
                partial_recall += 1
                # 记录部分召回的详细情况
                partial_recall_details[recalled_count] += 1
            else:
                zero_recall += 1

        print(f"\n召回情况分布:")
        print(f"  ✅ 完美召回 (100%): {perfect_recall} 个问题 ({perfect_recall/total_questions_with_oracle:.2%})")
        print(f"  🔶 部分召回 (1%-99%): {partial_recall} 个问题 ({partial_recall/total_questions_with_oracle:.2%})")

        # 显示部分召回的详细分布
        if partial_recall_details:
            print(f"     部分召回详情:")
            for recalled_count in sorted(partial_recall_details.keys()):
                count = partial_recall_details[recalled_count]
                print(f"       - 召回 {recalled_count} 个答案: {count} 个问题")

        print(f"  ❌ 零召回 (0%): {zero_recall} 个问题 ({zero_recall/total_questions_with_oracle:.2%})")

    print(f"\n有标准答案的问题数: {total_questions_with_oracle}")
    print("="*80)

    # 保存结果到文件
    print(f"\n[INFO] 保存结果到: {output_file}")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        for result in all_results:
            f.write(json.dumps(result, ensure_ascii=False) + '\n')
    print(f"[INFO] 结果已保存")

    # 清理资源
    print("\n[INFO] 清理搜索器资源...")
    await searcher.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
