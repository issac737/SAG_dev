#!/usr/bin/env python3
"""
Entity-Event-Chunk Recall 测试脚本

召回链路：Query → Key（向量+分词）→ Event（SQL关联）→ Chunk（event.chunk_id）

输入输出与 query_recall.py 保持一致
"""

import json
import sys
import asyncio
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import defaultdict
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
from dataflow.core.storage.repositories.entity_repository import EntityVectorRepository
from dataflow.core.storage.repositories.event_repository import EventVectorRepository
from dataflow.core.storage.repositories.source_chunk_repository import SourceChunkRepository
from dataflow.core.ai.tokensize import extract_keywords
from dataflow.db import Entity, EventEntity, SourceEvent, SourceChunk, get_session_factory

# Import recall metrics
from evaluation.hotpotqa_evaluation.scripts.recall_metrics import RecallCalculator, RecallResult

# SQLAlchemy
from sqlalchemy import select, and_


# ==================== 配置参数（参考 recall.py） ====================

class RecallConfigParams:
    """召回配置参数"""
    # 相似度阈值
    entity_similarity_threshold: float = 0.4
    event_similarity_threshold: float = 0.4

    # 数量控制
    vector_top_k: int = 40
    max_entities: int = 25
    max_events: int = 60

    # 分词器配置
    tokenizer_top_k: int = 15
    tokenizer_similarity: float = 0.99

    # 权重平衡
    step4_event_key_balance: float = 0.5


# ==================== 搜索器主类 ====================

class EntityEventRecallSearcher:
    """
    Entity-Event-Chunk 召回搜索器

    实现 6 步召回算法：
    1. Query → Key（语义相似度）
    2. Query → Key（分词补充）
    3. Key 并集排序
    4. Key → Event（SQL关联）
    5. Event 排序
    6. Event → Chunk
    """

    def __init__(self):
        """初始化搜索器"""
        # 初始化 ES 客户端
        es_config = ESConfig.from_env()
        self.es_client = ElasticsearchClient(config=es_config)

        # 初始化 Repositories
        self.entity_repo = EntityVectorRepository(self.es_client.client)
        self.event_repo = EventVectorRepository(self.es_client.client)
        self.chunk_repo = SourceChunkRepository(es_client=self.es_client)

        # 初始化 Embedding 客户端
        self.embedding_client = EmbeddingClient()

        # 数据库会话工厂
        self.session_factory = get_session_factory()

        # 配置参数
        self.config = RecallConfigParams()

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """
        计算两个向量的余弦相似度

        Args:
            vec1: 向量1
            vec2: 向量2

        Returns:
            余弦相似度，范围 [-1, 1]
        """
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

    async def _step1_semantic_key_recall(
        self,
        query: str,
        query_vector: List[float],
        source_config_id: str
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        """
        Step 1: Query → Key（语义相似度召回）

        Args:
            query: 查询文本
            query_vector: 查询向量
            source_config_id: 数据源配置ID

        Returns:
            (key_results, k1_weights) - 召回的 key 列表和权重映射
        """
        print(f"   [Step1] 语义相似度召回 Key...")

        # 向量搜索
        similar_entities = await self.entity_repo.search_similar(
            query_vector=query_vector,
            k=self.config.vector_top_k,
            source_config_ids=[source_config_id],
            include_type_threshold=False
        )

        # 过滤并构建结果
        key_results = []
        k1_weights = {}

        for entity in similar_entities:
            similarity = float(entity.get("_score", 0.0))
            if similarity >= self.config.entity_similarity_threshold:
                entity_id = entity.get("entity_id", "")
                key_results.append({
                    "entity_id": entity_id,
                    "name": entity.get("name", ""),
                    "type": entity.get("type", ""),
                    "similarity": similarity,
                    "source_method": "semantic"
                })
                k1_weights[entity_id] = similarity

        print(f"      向量召回 {len(similar_entities)} 个，阈值过滤后 {len(key_results)} 个")
        return key_results, k1_weights

    async def _step2_tokenizer_key_recall(
        self,
        query: str,
        source_config_id: str,
        existing_entity_ids: Set[str]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        """
        Step 2: Query → Key（分词补充召回）

        Args:
            query: 查询文本
            source_config_id: 数据源配置ID
            existing_entity_ids: 已召回的 entity_id 集合

        Returns:
            (key_results, k1_weights) - 新增的 key 列表和权重映射
        """
        print(f"   [Step2] 分词补充召回 Key...")

        # 提取关键词
        keywords = extract_keywords(query, top_k=self.config.tokenizer_top_k, mode="tokenizer")
        print(f"      提取关键词: {keywords}")

        if not keywords:
            return [], {}

        # SQL 前缀匹配
        key_results = []
        k1_weights = {}

        async with self.session_factory() as session:
            for keyword in keywords:
                # 前缀匹配查询
                stmt = (
                    select(Entity)
                    .where(
                        and_(
                            Entity.source_config_id == source_config_id,
                            Entity.normalized_name.like(f"{keyword.lower()}%")
                        )
                    )
                    .limit(2)  # 每个关键词最多匹配 2 个
                )
                result = await session.execute(stmt)
                entities = result.scalars().all()

                for entity in entities:
                    if entity.id not in existing_entity_ids:
                        existing_entity_ids.add(entity.id)
                        key_results.append({
                            "entity_id": entity.id,
                            "name": entity.name,
                            "type": entity.type,
                            "similarity": 0.99,
                            "source_method": "tokenizer"
                        })
                        k1_weights[entity.id] = 0.99

        print(f"      分词召回新增 {len(key_results)} 个 Key")
        return key_results, k1_weights

    def _step3_union_and_rank_keys(
        self,
        semantic_keys: List[Dict[str, Any]],
        tokenizer_keys: List[Dict[str, Any]],
        semantic_weights: Dict[str, float],
        tokenizer_weights: Dict[str, float]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        """
        Step 3: Key 并集排序

        Args:
            semantic_keys: 语义召回的 key
            tokenizer_keys: 分词召回的 key
            semantic_weights: 语义召回权重
            tokenizer_weights: 分词召回权重

        Returns:
            (final_keys, final_weights) - 排序后的 key 列表和权重映射
        """
        print(f"   [Step3] Key 并集排序...")

        # 合并（语义优先，已在 step2 中去重）
        merged_keys = semantic_keys + tokenizer_keys
        merged_weights = {**semantic_weights, **tokenizer_weights}

        # 按相似度降序排序
        merged_keys.sort(key=lambda x: x["similarity"], reverse=True)

        # 限制数量
        final_keys = merged_keys[:self.config.max_entities]
        final_weights = {k["entity_id"]: merged_weights[k["entity_id"]] for k in final_keys}

        print(f"      合并后 {len(merged_keys)} 个，取前 {len(final_keys)} 个")
        return final_keys, final_weights

    async def _step4_keys_to_events(
        self,
        key_results: List[Dict[str, Any]],
        source_config_id: str
    ) -> Tuple[List[str], Dict[str, List[str]]]:
        """
        Step 4: Key → Event（SQL 关联）

        Args:
            key_results: Key 列表
            source_config_id: 数据源配置ID

        Returns:
            (event_ids, event_to_entities) - event_id 列表和 event→entities 映射
        """
        print(f"   [Step4] Key → Event SQL 关联...")

        entity_ids = [k["entity_id"] for k in key_results]

        if not entity_ids:
            return [], {}

        async with self.session_factory() as session:
            # 查询 EventEntity 关联表
            stmt = (
                select(EventEntity.event_id, EventEntity.entity_id)
                .where(EventEntity.entity_id.in_(entity_ids))
            )
            result = await session.execute(stmt)
            pairs = result.fetchall()

            # 构建映射
            event_ids = list(set(event_id for event_id, _ in pairs))
            event_to_entities: Dict[str, List[str]] = defaultdict(list)
            for event_id, entity_id in pairs:
                event_to_entities[event_id].append(entity_id)

        print(f"      找到 {len(event_ids)} 个关联的 Event")
        return event_ids, dict(event_to_entities)

    async def _step5_rank_events(
        self,
        event_ids: List[str],
        event_to_entities: Dict[str, List[str]],
        k1_weights: Dict[str, float],
        query_vector: List[float],
        source_config_id: str
    ) -> List[Tuple[str, float]]:
        """
        Step 5: Event 排序（recall.py 公式）

        公式：event_weight = 0.5 * e1_weight + 0.5 * key_weight_sum

        Args:
            event_ids: Event ID 列表
            event_to_entities: Event → Entity 映射
            k1_weights: Key 权重映射
            query_vector: 查询向量
            source_config_id: 数据源配置ID

        Returns:
            排序后的 (event_id, weight) 列表
        """
        print(f"   [Step5] Event 排序...")

        if not event_ids:
            return []

        # 获取 Event 向量
        events_data = await self.event_repo.get_events_by_ids(event_ids)
        event_vectors = {
            e.get("event_id"): e.get("content_vector")
            for e in events_data if e.get("event_id") and e.get("content_vector")
        }

        # 计算 Event 权重
        event_weights = {}
        balance = self.config.step4_event_key_balance

        for event_id in event_ids:
            # e1_weight: event 与 query 的相似度
            content_vector = event_vectors.get(event_id)
            if content_vector:
                e1_weight = self._cosine_similarity(query_vector, content_vector)
            else:
                e1_weight = 0.0

            # key_weight_sum: 关联 key 的权重之和
            event_keys = event_to_entities.get(event_id, [])
            key_weight_sum = sum(k1_weights.get(key_id, 0.0) for key_id in event_keys)

            # 综合权重
            combined_weight = balance * e1_weight + (1 - balance) * key_weight_sum
            event_weights[event_id] = combined_weight

        # 排序并限制数量
        sorted_events = sorted(event_weights.items(), key=lambda x: x[1], reverse=True)
        final_events = sorted_events[:self.config.max_events]

        print(f"      计算后 {len(event_weights)} 个，取前 {len(final_events)} 个")
        return final_events

    async def _step6_events_to_chunks(
        self,
        ranked_events: List[Tuple[str, float]],
        source_config_id: str,
        top_k: int
    ) -> List[Dict[str, Any]]:
        """
        Step 6: Event → Chunk

        Args:
            ranked_events: 排序后的 (event_id, weight) 列表
            source_config_id: 数据源配置ID
            top_k: 返回数量

        Returns:
            Chunk 列表
        """
        print(f"   [Step6] Event → Chunk...")

        if not ranked_events:
            return []

        event_ids = [event_id for event_id, _ in ranked_events]
        event_weight_map = {event_id: weight for event_id, weight in ranked_events}

        async with self.session_factory() as session:
            # 获取 Event 的 chunk_id
            stmt = (
                select(SourceEvent)
                .where(
                    and_(
                        SourceEvent.source_config_id == source_config_id,
                        SourceEvent.id.in_(event_ids)
                    )
                )
            )
            result = await session.execute(stmt)
            events = result.scalars().all()

            # 构建 event_id → chunk_id 映射（保持 event 顺序）
            event_to_chunk = {}
            chunk_ids = []
            for event in events:
                if event.chunk_id:
                    event_to_chunk[event.id] = event.chunk_id
                    if event.chunk_id not in chunk_ids:
                        chunk_ids.append(event.chunk_id)

            # 获取 Chunk 详情
            if not chunk_ids:
                print(f"      没有找到关联的 Chunk")
                return []

            chunks_stmt = (
                select(SourceChunk)
                .where(SourceChunk.id.in_(chunk_ids))
            )
            chunks_result = await session.execute(chunks_stmt)
            chunks = chunks_result.scalars().all()
            chunk_map = {chunk.id: chunk for chunk in chunks}

        # 按 event 权重顺序输出 Chunk
        results = []
        seen_chunks = set()

        for event_id, event_weight in ranked_events:
            chunk_id = event_to_chunk.get(event_id)
            if chunk_id and chunk_id not in seen_chunks:
                chunk = chunk_map.get(chunk_id)
                if chunk:
                    seen_chunks.add(chunk_id)
                    results.append({
                        'chunk_id': chunk_id,
                        'heading': chunk.heading or '',
                        'content': chunk.content or '',
                        'score': event_weight,
                        'weight': event_weight,
                        'event_id': event_id
                    })

                    if len(results) >= top_k:
                        break

        print(f"      返回 {len(results)} 个 Chunk")
        return results

    async def search(
        self,
        query: str,
        source_config_id: str,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        主搜索方法

        Args:
            query: 查询文本
            source_config_id: 数据源配置ID
            top_k: 返回段落数量

        Returns:
            段落列表，包含 chunk_id, heading, content, score 等字段
        """
        # 生成 query embedding
        query_vector = await self.embedding_client.generate(query)
        print(f"      [DEBUG] query_vector 维度: {len(query_vector)}")

        # Step 1: 语义召回 Key
        semantic_keys, semantic_weights = await self._step1_semantic_key_recall(
            query, query_vector, source_config_id
        )

        # Step 2: 分词补充召回 Key
        existing_ids = {k["entity_id"] for k in semantic_keys}
        tokenizer_keys, tokenizer_weights = await self._step2_tokenizer_key_recall(
            query, source_config_id, existing_ids
        )

        # Step 3: Key 并集排序
        final_keys, k1_weights = self._step3_union_and_rank_keys(
            semantic_keys, tokenizer_keys, semantic_weights, tokenizer_weights
        )

        if not final_keys:
            print(f"      [WARN] 没有召回任何 Key")
            return []

        # Step 4: Key → Event
        event_ids, event_to_entities = await self._step4_keys_to_events(
            final_keys, source_config_id
        )

        if not event_ids:
            print(f"      [WARN] 没有关联到任何 Event")
            return []

        # Step 5: Event 排序
        ranked_events = await self._step5_rank_events(
            event_ids, event_to_entities, k1_weights, query_vector, source_config_id
        )

        if not ranked_events:
            print(f"      [WARN] Event 排序后为空")
            return []

        # Step 6: Event → Chunk
        chunks = await self._step6_events_to_chunks(
            ranked_events, source_config_id, top_k
        )

        return chunks

    async def cleanup(self):
        """清理资源"""
        if hasattr(self.es_client, 'client') and self.es_client.client:
            await self.es_client.client.close()


# ==================== 辅助函数（与 query_recall.py 一致） ====================

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


# ==================== 主函数 ====================

async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='Entity-Event-Chunk Recall 测试脚本')
    parser.add_argument('--source-config-id', type=str, required=False, default=None,
                       help='数据源配置ID')
    parser.add_argument('--input', type=Path, required=False, default=None,
                       help='问题列表文件路径 (JSONL格式)')
    parser.add_argument('--corpus', type=Path, required=False, default=None,
                       help='语料库文件路径 (JSONL格式)')
    parser.add_argument('--source-dir', type=Path, required=False, default=None,
                       help='源数据目录路径')
    parser.add_argument('--max-questions', type=int, default=None,
                       help='最大处理问题数')
    parser.add_argument('--top-k', type=int, default=10,
                       help='每个问题返回的段落数量（默认: 10）')
    parser.add_argument('--output', type=Path, required=False, default=None,
                       help='保存搜索结果的文件路径（JSONL格式）')

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
    print("开始处理问题并执行 Entity-Event-Chunk 召回")
    print("="*80)

    # 初始化搜索器
    print("\n[INFO] 初始化 Entity-Event-Chunk 搜索器...")
    searcher = EntityEventRecallSearcher()
    print("[INFO] 搜索器初始化完成")

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
                    text = chunk.get('text', '')[:200]

                    print(f"   [{j}] {title}")
                    print(f"       {text}...")
                else:
                    print(f"   [{j}] chunk_id: {chunk_id} (未找到对应段落)")

        # 执行搜索
        print(f"\n🔍 执行 Entity-Event-Chunk 召回 (top-{args.top_k})...")
        try:
            start_time = time.time()
            search_results = await searcher.search(
                query=question,
                source_config_id=source_config_id,
                top_k=args.top_k
            )
            search_time = time.time() - start_time

            print(f"   搜索完成，找到 {len(search_results)} 个段落 (耗时: {search_time:.3f}秒)")

            # 准备召回率计算所需的数据
            oracle_chunks_for_calc = []
            for chunk_id in oracle_chunk_ids:
                if chunk_id in corpus_dict:
                    chunk = corpus_dict[chunk_id]
                    oracle_chunks_for_calc.append({
                        'chunk_id': chunk_id,
                        'title': chunk.get('title', ''),
                        'text': chunk.get('text', '')
                    })

            # 使用 RecallCalculator 计算召回率
            recall_result = RecallCalculator.calculate(
                question_id=question_id,
                oracle_chunks=oracle_chunks_for_calc,
                retrieved_sections=search_results,
                verbose=False
            )

            # 显示搜索结果
            print(f"\n   检索结果:")
            for idx, section in enumerate(search_results, 1):
                chunk_id = section.get('chunk_id', '')
                heading = section.get('heading', 'N/A')
                content = section.get('content', '')[:200]
                score = section.get('score', 0.0)

                # 检查是否命中标准答案
                is_hit = ''
                for detail in recall_result.recalled_details:
                    if detail.get('retrieved_chunk_id') == chunk_id:
                        is_hit = '✅ 命中'
                        break

                print(f"   [{idx}] {heading} {is_hit}")
                print(f"       Score: {score:.4f}")
                print(f"       内容: {content}...")

            # 显示召回统计
            print(f"\n   📊 召回统计: {recall_result.recalled}/{recall_result.total_oracle} ({recall_result.recall:.2%})")
            if recall_result.recalled_details:
                print(f"   匹配详情:")
                for detail in recall_result.recalled_details[:5]:
                    print(f"      - {detail['oracle_title']} <-> {detail['retrieved_heading']}")
                if len(recall_result.recalled_details) > 5:
                    print(f"      ... 还有 {len(recall_result.recalled_details) - 5} 个匹配")

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
                        'chunk_id': s.get('chunk_id', ''),
                        'heading': s.get('heading', ''),
                        'content': s.get('content', ''),
                        'score': s.get('score', 0.0),
                        'cosine_similarity': None
                    }
                    for s in search_results
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

        # 统计不同召回情况的问题数
        perfect_recall = 0
        partial_recall = 0
        zero_recall = 0

        for result in all_results:
            if 'error' in result:
                continue

            recall = result.get('recall', 0.0)
            if recall >= 1.0:
                perfect_recall += 1
            elif recall > 0.0:
                partial_recall += 1
            else:
                zero_recall += 1

        print(f"\n召回情况分布:")
        print(f"  ✅ 完美召回 (100%): {perfect_recall} 个问题 ({perfect_recall/total_questions_with_oracle:.2%})")
        print(f"  🔶 部分召回 (1%-99%): {partial_recall} 个问题 ({partial_recall/total_questions_with_oracle:.2%})")
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
