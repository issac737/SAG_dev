#!/usr/bin/env python3
"""
Query Recall 测试脚本

简化版：只输出问题和对应答案
"""

import json
import sys
import asyncio
from pathlib import Path
from typing import List, Dict, Any
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
from dataflow.core.storage.repositories.source_chunk_repository import SourceChunkRepository

# Import recall metrics
from evaluation.hotpotqa_evaluation.scripts.recall_metrics import RecallCalculator, RecallResult


class SimpleVectorSearcher:
    """简单的向量搜索器，用于测试召回效果"""

    def __init__(self):
        """初始化搜索器"""
        # 初始化 ES 客户端
        es_client = ElasticsearchClient(config=ESConfig.from_env())

        # 初始化 SourceChunkRepository
        self.chunk_repo = SourceChunkRepository(es_client=es_client)

        # 初始化 Embedding 客户端
        self.embedding_client = EmbeddingClient()

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        计算两个向量的余弦相似度

        Args:
            vec1: 向量1 (query_vector)
            vec2: 向量2 (content_vector)

        Returns:
            余弦相似度，范围 [-1, 1]
            - 1.0: 完全同向（相似）
            - 0.0: 正交（无关）
            - -1.0: 完全反向（相反）
        """
        if not vec1 or not vec2:
            return 0.0

        try:
            v1 = np.array(vec1, dtype=np.float32)
            v2 = np.array(vec2, dtype=np.float32)

            if len(v1) != len(v2):
                print(f"      [WARN] 向量长度不一致: {len(v1)} vs {len(v2)}")
                return 0.0

            # 计算点积
            dot_product = np.dot(v1, v2)
            # 计算向量的模
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            # 余弦相似度 = 点积 / (模1 × 模2)
            similarity = dot_product / (norm1 * norm2)
            # ✅ 保留完整范围 [-1, 1]，只限制浮点误差
            return float(np.clip(similarity, -1.0, 1.0))

        except Exception as e:
            print(f"      [ERROR] 余弦相似度计算失败: {e}")
            return 0.0

    async def check_es_data(self):
        """检查ES中的数据情况"""
        es_client = self.chunk_repo.es_client.client

        # 1. 获取总数
        count_result = await es_client.count(index="source_chunks")
        total_count = count_result['count']
        print(f"      [DEBUG] ES中source_chunks总数: {total_count}")

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

        response = await es_client.search(index="source_chunks", body=agg_query)

        if 'aggregations' in response and 'source_configs' in response['aggregations']:
            buckets = response['aggregations']['source_configs']['buckets']
            print(f"      [DEBUG] ES中的source_config_id列表:")
            for bucket in buckets:
                print(f"         - {bucket['key']}: {bucket['doc_count']} 个文档")

        # 3. 如果总数为0，给出提示
        if total_count == 0:
            print(f"      [WARNING] ES中没有任何数据！请先导入数据。")

        return total_count

    async def search(
        self,
        query: str,
        source_config_id: str,
        es_retrieve_k: int = 50
    ) -> List[Dict[str, Any]]:
        """
        向量搜索段落（从 ES 召回指定数量）

        Args:
            query: 查询文本
            source_config_id: 数据源配置ID
            es_retrieve_k: 从 ES 召回的段落数量（后续会去重和筛选）

        Returns:
            段落列表，每个段落包含 chunk_id, heading, content, score, cosine_similarity 等字段
        """
        # 1. 生成 query 的 embedding
        query_vector = await self.embedding_client.generate(query)

        # 2. 使用 SourceChunkRepository 搜索（召回 es_retrieve_k 个段落）
        print(f"      [DEBUG] source_config_id: {source_config_id}, es_retrieve_k: {es_retrieve_k}")
        print(f"      [DEBUG] query_vector维度: {len(query_vector)}")

        results = await self.chunk_repo.search_similar_by_content(
            query_vector=query_vector,
            k=es_retrieve_k,
            source_config_id=source_config_id
        )

        print(f"      [DEBUG] 搜索返回结果数: {len(results)}")
        if results:
            print(f"      [DEBUG] 第一个结果字段: {list(results[0].keys())}")

        # 3. 转换为统一格式，并手动计算余弦相似度
        sections = []
        for hit in results:
            chunk_id = hit.get('id', '')
            es_score = hit.get('_score', 0.0)

            # 🔑 获取段落的 content_vector（从 ES 结果中）
            content_vector = hit.get('content_vector', None)

            # 🔑 手动计算余弦相似度
            if content_vector:
                manual_cosine_similarity = self._cosine_similarity(query_vector, content_vector)
            else:
                manual_cosine_similarity = None
                print(f"      [WARN] chunk {chunk_id[:8]}... 没有 content_vector")

            sections.append({
                'chunk_id': chunk_id,
                'heading': hit.get('heading', ''),
                'content': hit.get('content', ''),
                'score': es_score,  # ES 返回的 _score
                'cosine_similarity': manual_cosine_similarity,  # 手动计算的余弦相似度
                'weight': es_score  # 保持兼容性
            })

        return sections

    async def cleanup(self):
        """清理资源"""
        if hasattr(self.chunk_repo, 'es_client') and hasattr(self.chunk_repo.es_client, 'client'):
            await self.chunk_repo.es_client.client.close()


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


def find_latest_source_dir(base_dir: Path) -> Path:
    """
    查找最新的源数据文件夹

    文件夹格式：YYYYMMDD_HHMMSS
    """
    print(f"[INFO] 查找最新的源数据文件夹: {base_dir}")

    if not base_dir.exists():
        print(f"[ERROR] 源数据目录不存在: {base_dir}")
        sys.exit(1)

    # 获取所有文件夹
    dirs = [d for d in base_dir.iterdir() if d.is_dir()]

    if not dirs:
        print(f"[ERROR] 源数据目录下没有文件夹: {base_dir}")
        sys.exit(1)

    # 按名称排序（YYYYMMDD_HHMMSS 格式可以直接字符串排序）
    dirs.sort(key=lambda x: x.name, reverse=True)

    latest_dir = dirs[0]
    print(f"[INFO] 找到最新文件夹: {latest_dir.name}")

    return latest_dir


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='Query Recall 测试脚本')
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
    parser.add_argument('--es-retrieve-k', type=int, default=50,
                       help='从 ES 召回的段落数量（默认: 50），召回后会去重并筛选 top-k')
    parser.add_argument('--top-k', type=int, default=5,
                       help='去重后选择的段落数量（默认: 10）')
    parser.add_argument('--output', type=Path, required=False, default=None,
                       help='保存搜索结果的文件路径（JSONL格式）')

    args = parser.parse_args()

    # 获取脚本所在目录作为基准
    script_dir = Path(__file__).parent  # scripts/
    eval_base_dir = script_dir.parent   # evaluation/hotpotqa_evaluation/

    # 确定源数据目录
    if args.source_dir:
        # 使用指定的源数据目录
        source_dir = Path(args.source_dir)
        print(f"[INFO] 使用指定的源数据目录: {source_dir}")
    else:
        # 自动查找最新的源数据目录
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

    # 确定语料库文件
    if args.corpus:
        corpus_file = Path(args.corpus)
    else:
        corpus_file = source_dir / "corpus.jsonl"
        if not corpus_file.exists():
            print(f"[ERROR] 源数据目录下找不到 corpus.jsonl: {corpus_file}")
            sys.exit(1)
        print(f"[INFO] 使用源数据目录下的 corpus.jsonl: {corpus_file}")

    # 验证文件
    if not input_file.exists():
        print(f"[ERROR] 问题文件不存在: {input_file}")
        sys.exit(1)

    if not corpus_file.exists():
        print(f"[ERROR] 语料库文件不存在: {corpus_file}")
        sys.exit(1)

    # 加载数据
    corpus_dict = load_corpus(corpus_file)
    questions = load_questions(input_file)

    # 限制问题数
    if args.max_questions:
        questions = questions[:args.max_questions]
        print(f"[INFO] 限制处理前 {args.max_questions} 个问题")

    # 输出问题和答案
    print("\n" + "="*80)
    print("开始处理问题并执行向量搜索")
    print("="*80)

    # 初始化搜索器
    print("\n[INFO] 初始化向量搜索器...")
    searcher = SimpleVectorSearcher()
    print("[INFO] 搜索器初始化完成")

    # 检查ES数据
    print("\n[INFO] 检查ES中的数据...")
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

        # 执行向量搜索
        print(f"\n🔍 执行向量搜索 (ES召回: {args.es_retrieve_k}, 去重后选择: top-{args.top_k})...")
        try:
            import time
            start_time = time.time()
            search_results = await searcher.search(
                query=question,
                source_config_id=source_config_id,  # 使用从文件读取的 source_config_id
                es_retrieve_k=args.es_retrieve_k  # 从 ES 召回的段落数量
            )
            search_time = time.time() - start_time

            print(f"   ES 召回完成，找到 {len(search_results)} 个段落 (耗时: {search_time:.3f}秒)")

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

            # 2. 对检索结果去重（基于内容）
            seen_contents = set()
            deduped_results = []
            duplicates_count = 0

            for section in search_results:
                content = section.get('content', '')
                # 使用内容的归一化版本作为去重键
                content_key = ' '.join(content.strip().split())

                if content_key not in seen_contents:
                    seen_contents.add(content_key)
                    deduped_results.append(section)
                else:
                    duplicates_count += 1

            if duplicates_count > 0:
                print(f"   ⚠️  检测到 {duplicates_count} 个重复段落，已自动过滤")

            # 3. 从去重结果中选择 top-k 个段落
            final_results = deduped_results[:args.top_k]
            if len(deduped_results) > args.top_k:
                print(f"   ✂️  去重后从 {len(deduped_results)} 个段落中选择 top-{args.top_k}")

            # 4. 使用 RecallCalculator 计算召回率（���用最终筛选后的结果）
            recall_result = RecallCalculator.calculate(
                question_id=question_id,
                oracle_chunks=oracle_chunks_for_calc,
                retrieved_sections=final_results,
                verbose=False
            )

            # 显示搜索结果（最终筛选后）
            print(f"\n   检索结果 (最终: {len(final_results)} 个段落):")
            for idx, section in enumerate(final_results, 1):
                chunk_id = section.get('chunk_id', '')
                heading = section.get('heading', 'N/A')
                content = section.get('content', '')[:200]  # 限制长度
                es_score = section.get('score', 0.0)
                manual_cosine = section.get('cosine_similarity', None)

                # 检查是否命中标准答案（基于文本匹配）
                is_hit = ''
                for detail in recall_result.recalled_details:
                    if detail.get('retrieved_chunk_id') == chunk_id:
                        is_hit = '✅ 命中'
                        break

                print(f"   [{idx}] {heading} {is_hit}")
                print(f"       ES Score: {es_score:.4f}")
                if manual_cosine is not None:
                    print(f"       Manual Cosine Similarity: {manual_cosine:.4f}")
                    # 🔑 显示两者的差异
                    diff = abs(es_score - manual_cosine)
                    print(f"       差异: {diff:.4f} (ES Score - Manual Cosine)")
                else:
                    print(f"       Manual Cosine Similarity: N/A (无向量)")
                print(f"       内容: {content}...")

            # 显示召回统计
            print(f"\n   📊 召回统计: {recall_result.recalled}/{recall_result.total_oracle} ({recall_result.recall:.2%})")
            if recall_result.recalled_details:
                print(f"   匹配详情:")
                for detail in recall_result.recalled_details[:5]:  # 只显示前5个
                    print(f"      - {detail['oracle_title']} <-> {detail['retrieved_heading']}")
                if len(recall_result.recalled_details) > 5:
                    print(f"      ... 还有 {len(recall_result.recalled_details) - 5} 个匹配")

            # 累计统计
            if recall_result.total_oracle > 0:
                total_recall += recall_result.recall
                total_questions_with_oracle += 1

            # 保存结果（使用最终筛选后的结果）
            result = {
                'question_id': question_id,
                'question': question,
                'answer': answer,
                'oracle_chunk_ids': oracle_chunk_ids,
                'es_retrieved': len(search_results),
                'duplicates_filtered': duplicates_count,
                'deduped_count': len(deduped_results),
                'final_count': len(final_results),
                'search_results': [
                    {
                        'chunk_id': s.get('chunk_id', ''),
                        'heading': s.get('heading', ''),
                        'content': s.get('content', ''),
                        'score': s.get('score', 0.0),
                        'cosine_similarity': s.get('cosine_similarity', None)  # 🔑 添加手动计算的余弦相似度
                    }
                    for s in final_results
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
                'search_results': []
            })

    # 打印总体统计
    print("\n" + "="*80)
    print("📊 总体统计")
    print("="*80)
    print(f"总问题数: {len(questions)}")

    if total_questions_with_oracle > 0:
        avg_recall = total_recall / total_questions_with_oracle
        print(f"平均召回率: {avg_recall:.2%}")
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
    if args.output:
        print(f"\n[INFO] 保存结果到: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            for result in all_results:
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
        print(f"[INFO] 结果已保存")

    # 清理资源
    print("\n[INFO] 清理搜索器资源...")
    await searcher.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

