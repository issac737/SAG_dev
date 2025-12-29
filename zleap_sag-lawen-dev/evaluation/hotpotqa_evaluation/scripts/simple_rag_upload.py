#!/usr/bin/env python3
"""
简单的 RAG 文档上传脚本

功能：
1. 使用 MarkdownParser 解析 md 文件
2. 使用 EmbeddingClient 批量生成 embedding
3. 批量上传到 Elasticsearch
4. 记录信息源 ID 和段落 ID

特性：
- Embedding 生成重试机制
- ES 上传重试机制
- 详细的日志记录
- 自动生成时间戳文件夹
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 加载 .env 文件
from dotenv import load_dotenv
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"[INFO] 已加载环境变量: {env_path}")
else:
    print(f"[WARN] 未找到 .env 文件: {env_path}")

# 导入依赖
from dataflow.modules.load.parser import MarkdownParser
from dataflow.core.ai.embedding import EmbeddingClient
from dataflow.core.storage.elasticsearch import ElasticsearchClient, ESConfig
from dataflow.core.storage.repositories.source_chunk_repository import SourceChunkRepository


class SimpleRAGUploader:
    """简单的 RAG 文档上传器"""

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        enable_logging: bool = True,
        use_timestamp_folder: bool = True,
        max_retries: int = 3,
        retry_delay: int = 2,
        embedding_batch_size: int = 10,
        es_batch_size: int = 50
    ):
        """
        初始化上传器

        Args:
            output_dir: 输出目录（默认: evaluation/hotpotqa_evaluation/data/rag_uploads）
            enable_logging: 是否启用日志
            use_timestamp_folder: 是否为每次运行创建时间戳子文件夹
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
            embedding_batch_size: Embedding 批量大小
            es_batch_size: ES 批量索引大小
        """
        # 初始化日志
        self.logger = None
        if enable_logging:
            self._setup_logging()

        # 配置参数
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.embedding_batch_size = embedding_batch_size
        self.es_batch_size = es_batch_size

        # 输出目录
        base_dir = output_dir or (Path(__file__).parent.parent / "data" / "rag_uploads")

        if use_timestamp_folder:
            self.run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.output_dir = base_dir / self.run_timestamp
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self._log(f"创建时间戳文件夹: {self.output_dir}")
        else:
            self.output_dir = base_dir
            self.output_dir.mkdir(parents=True, exist_ok=True)

        # 输出文件路径
        self.result_path = self.output_dir / "upload_result.json"
        self.chunks_path = self.output_dir / "chunks.jsonl"

        # 初始化组件
        self.parser = None
        self.embedding_client = None
        self.es_client = None
        self.chunk_repo = None

        # 统计信息
        self.stats = {
            'total_chunks': 0,
            'embedding_success': 0,
            'embedding_failed': 0,
            'embedding_retries': 0,
            'es_success': 0,
            'es_failed': 0,
            'es_retries': 0,
        }

    def _setup_logging(self):
        """配置日志"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    def _log(self, message: str, level: str = 'info'):
        """统一日志方法"""
        if self.logger:
            getattr(self.logger, level.lower())(message)
        else:
            print(message)

    async def _init_components(self):
        """初始化组件"""
        self._log("初始化组件...")

        # 1. 初始化 MarkdownParser
        self.parser = MarkdownParser(
            max_tokens=1000,
            min_content_length=100,
            merge_short_sections=True
        )
        self._log("✓ MarkdownParser 初始化完成")

        # 2. 初始化 EmbeddingClient
        self.embedding_client = EmbeddingClient()
        self._log("✓ EmbeddingClient 初始化完成")

        # 3. 初始化 ElasticsearchClient
        self.es_client = ElasticsearchClient(config=ESConfig.from_env())
        self._log("✓ ElasticsearchClient 初始化完成")

        # 4. 初始化 SourceChunkRepository
        self.chunk_repo = SourceChunkRepository(es_client=self.es_client)
        self._log("✓ SourceChunkRepository 初始化完成")

    async def _generate_embeddings_with_retry(
        self,
        texts: List[str]
    ) -> Optional[List[List[float]]]:
        """
        批量生成 embedding（带重试机制）

        Args:
            texts: 文本列表

        Returns:
            embedding 向量列表，失败返回 None
        """
        for attempt in range(self.max_retries):
            try:
                embeddings = await self.embedding_client.batch_generate(texts)
                self.stats['embedding_success'] += len(texts)
                return embeddings
            except Exception as e:
                self.stats['embedding_retries'] += 1
                if attempt < self.max_retries - 1:
                    self._log(
                        f"⚠️ Embedding 生成失败 (尝试 {attempt + 1}/{self.max_retries}): {e}，"
                        f"{self.retry_delay}秒后重试...",
                        'warning'
                    )
                    await asyncio.sleep(self.retry_delay)
                else:
                    self._log(f"❌ Embedding 生成失败（已达最大重试次数）: {e}", 'error')
                    self.stats['embedding_failed'] += len(texts)
                    return None

    async def _bulk_index_with_retry(
        self,
        documents: List[Dict[str, Any]],
        source_config_id: str
    ) -> bool:
        """
        批量索引到 ES（带重试机制）

        Args:
            documents: 文档列表
            source_config_id: 信息源 ID

        Returns:
            是否成功
        """
        for attempt in range(self.max_retries):
            try:
                result = await self.es_client.bulk_index(
                    index="source_chunks",
                    documents=documents,
                    return_details=True,
                    routing=source_config_id
                )

                if result['success']:
                    self.stats['es_success'] += result['success_count']
                    self._log(f"✓ 批量索引成功: {result['success_count']} 个文档")
                    return True
                else:
                    self._log(
                        f"⚠️ 批量索引部分失败: 成功 {result['success_count']}, "
                        f"失败 {result['error_count']}",
                        'warning'
                    )
                    self.stats['es_success'] += result['success_count']
                    self.stats['es_failed'] += result['error_count']

                    # 如果有错误，记录错误详情
                    if result['errors']:
                        for error in result['errors'][:5]:  # 只显示前5个错误
                            self._log(f"   错误: ID={error.get('id')}, {error.get('error')}", 'error')

                    return False

            except Exception as e:
                self.stats['es_retries'] += 1
                if attempt < self.max_retries - 1:
                    self._log(
                        f"⚠️ ES 批量索引失败 (尝试 {attempt + 1}/{self.max_retries}): {e}，"
                        f"{self.retry_delay}秒后重试...",
                        'warning'
                    )
                    await asyncio.sleep(self.retry_delay)
                else:
                    self._log(f"❌ ES 批量索引失败（已达最大重试次数）: {e}", 'error')
                    self.stats['es_failed'] += len(documents)
                    return False

    async def upload_markdown(
        self,
        md_file_path: Path,
        source_name: Optional[str] = None,
        source_description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        上传 Markdown 文件

        Args:
            md_file_path: Markdown 文件路径
            source_name: 信息源名称（默认使用文件名）
            source_description: 信息源描述

        Returns:
            上传结果字典
        """
        self._log("=" * 60)
        self._log("开始上传 Markdown 文件")
        self._log("=" * 60)

        # 验证文件
        if not md_file_path.exists():
            error_msg = f"文件不存在: {md_file_path}"
            self._log(error_msg, 'error')
            return {'status': 'error', 'message': error_msg}

        file_size_mb = md_file_path.stat().st_size / 1024 / 1024
        self._log(f"文件: {md_file_path}")
        self._log(f"文件大小: {file_size_mb:.2f} MB\n")

        # 初始化组件
        await self._init_components()

        # 生成信息源 ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        source_config_id = f"rag-{md_file_path.stem}-{timestamp}"
        source_name = source_name or md_file_path.stem
        source_description = source_description or f"RAG upload from {md_file_path.name}"

        self._log(f"信息源 ID: {source_config_id}")
        self._log(f"信息源名称: {source_name}")
        self._log(f"描述: {source_description}\n")

        # 1. 解析文件
        self._log("阶段 1: 解析 Markdown 文件...")
        parse_start = time.perf_counter()

        try:
            content, sections = self.parser.parse_file(md_file_path)
            parse_time = time.perf_counter() - parse_start

            self.stats['total_chunks'] = len(sections)
            self._log(f"✓ 解析完成: {len(sections)} 个段落，耗时 {parse_time:.2f}秒\n")
        except Exception as e:
            error_msg = f"文件解析失败: {e}"
            self._log(error_msg, 'error')
            return {'status': 'error', 'message': error_msg}

        # 2. 批量生成 Embedding
        self._log("阶段 2: 批量生成 Embedding...")
        embedding_start = time.perf_counter()

        # 准备文本列表（使用 content，如果有 heading 则拼接）
        chunks_data = []
        for idx, section in enumerate(sections):
            heading = section.heading or ""
            content = section.content or ""

            # 拼接标题和内容
            full_text = f"{heading}\n{content}" if heading else content

            chunks_data.append({
                'index': idx,
                'heading': heading,
                'content': content,
                'full_text': full_text,
                'section': section
            })

        # 批量生成 embedding
        all_embeddings = []
        failed_indices = []

        for i in range(0, len(chunks_data), self.embedding_batch_size):
            batch = chunks_data[i:i + self.embedding_batch_size]
            batch_texts = [chunk['content'] for chunk in batch]  # 只用 content 生成 embedding

            self._log(f"生成 Embedding 批次 {i // self.embedding_batch_size + 1}: "
                     f"{len(batch)} 个段落...")

            embeddings = await self._generate_embeddings_with_retry(batch_texts)

            if embeddings:
                all_embeddings.extend(embeddings)
            else:
                # 记录失败的索引
                failed_indices.extend([chunk['index'] for chunk in batch])
                # 添加 None 占位符
                all_embeddings.extend([None] * len(batch))

        embedding_time = time.perf_counter() - embedding_start
        self._log(f"✓ Embedding 生成完成，耗时 {embedding_time:.2f}秒")
        self._log(f"  成功: {self.stats['embedding_success']}, "
                 f"失败: {self.stats['embedding_failed']}, "
                 f"重试次数: {self.stats['embedding_retries']}\n")

        # 3. 批量上传到 ES
        self._log("阶段 3: 批量上传到 Elasticsearch...")
        es_start = time.perf_counter()

        # 准备 ES 文档（只包含成功生成 embedding 的段落）
        es_documents = []
        chunk_ids = []

        for idx, (chunk, embedding) in enumerate(zip(chunks_data, all_embeddings)):
            if embedding is None:
                continue  # 跳过失败的 embedding

            chunk_id = f"{source_config_id}_chunk_{idx}"
            chunk_ids.append(chunk_id)

            # 构建 ES 文档
            document = {
                "id": chunk_id,
                "chunk_id": chunk_id,
                "source_id": source_config_id,  # 使用 source_config_id 作为 source_id
                "source_config_id": source_config_id,
                "rank": idx,
                "heading": chunk['heading'],
                "content": chunk['content'],
                "heading_vector": embedding if chunk['heading'] else None,  # 如果有标题，使用同样的 embedding
                "content_vector": embedding,
                "references": [],
                "chunk_type": "paragraph",
                "content_length": len(chunk['content'])
            }

            es_documents.append(document)

        # 批量上传
        total_uploaded = 0
        for i in range(0, len(es_documents), self.es_batch_size):
            batch = es_documents[i:i + self.es_batch_size]

            self._log(f"上传批次 {i // self.es_batch_size + 1}: {len(batch)} 个文档...")

            success = await self._bulk_index_with_retry(batch, source_config_id)
            if success:
                total_uploaded += len(batch)

        es_time = time.perf_counter() - es_start
        self._log(f"✓ ES 上传完成，耗时 {es_time:.2f}秒")
        self._log(f"  成功: {self.stats['es_success']}, "
                 f"失败: {self.stats['es_failed']}, "
                 f"重试次数: {self.stats['es_retries']}\n")

        # 4. 保存段落信息到 JSONL
        self._log("保存段落信息...")
        with open(self.chunks_path, 'w', encoding='utf-8') as f:
            for idx, (chunk, embedding) in enumerate(zip(chunks_data, all_embeddings)):
                chunk_info = {
                    'chunk_id': f"{source_config_id}_chunk_{idx}",
                    'index': idx,
                    'heading': chunk['heading'],
                    'content': chunk['content'],
                    'has_embedding': embedding is not None,
                }
                f.write(json.dumps(chunk_info, ensure_ascii=False) + '\n')

        self._log(f"✓ 段落信息已保存: {self.chunks_path}\n")

        # 5. 构建结果
        total_time = parse_time + embedding_time + es_time
        result = {
            "status": "completed",
            "source_config_id": source_config_id,
            "source_name": source_name,
            "source_description": source_description,
            "file_path": str(md_file_path),
            "file_size_mb": file_size_mb,
            "total_chunks": self.stats['total_chunks'],
            "chunks_uploaded": total_uploaded,
            "embedding_stats": {
                "success": self.stats['embedding_success'],
                "failed": self.stats['embedding_failed'],
                "retries": self.stats['embedding_retries']
            },
            "es_stats": {
                "success": self.stats['es_success'],
                "failed": self.stats['es_failed'],
                "retries": self.stats['es_retries']
            },
            "chunk_ids": chunk_ids,
            "failed_chunk_indices": failed_indices,
            "timing": {
                "parse_time": parse_time,
                "embedding_time": embedding_time,
                "es_time": es_time,
                "total_time": total_time
            },
            "output_dir": str(self.output_dir),
            "chunks_file": str(self.chunks_path),
            "timestamp": timestamp
        }

        # 6. 保存结果
        with open(self.result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        self._log(f"💾 上传结果已保存: {self.result_path}\n")

        # 7. 打印摘要
        self._log("=" * 60)
        self._log("✅ 上传完成")
        self._log("=" * 60)
        self._log(f"总段落数: {self.stats['total_chunks']}")
        self._log(f"成功上传: {total_uploaded}")
        self._log(f"失败数: {self.stats['es_failed']}")
        self._log(f"总耗时: {total_time:.2f}秒")
        self._log(f"输出目录: {self.output_dir}")
        self._log("=" * 60)

        return result

    async def delete_by_source_config_id(
        self,
        source_config_id: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        根据 source_config_id 删除所有相关文档

        Args:
            source_config_id: 信息源 ID
            dry_run: 是否仅预览（不实际删除）

        Returns:
            删除结果字典
        """
        self._log("=" * 60)
        self._log(f"删除信息源: {source_config_id}")
        if dry_run:
            self._log("⚠️ 预览模式（不会实际删除）")
        self._log("=" * 60)

        # 初始化组件（只需要 ES 客户端）
        if not self.es_client:
            self.es_client = ElasticsearchClient(config=ESConfig.from_env())
            self._log("✓ ElasticsearchClient 初始化完成")

        try:
            # 1. 查询该 source_config_id 下的所有文档
            self._log(f"\n查询 source_config_id={source_config_id} 的文档...")

            query = {
                "query": {
                    "term": {
                        "source_config_id": source_config_id
                    }
                },
                "size": 10000  # 最多返回 10000 个文档
            }

            response = await self.es_client.client.search(
                index="source_chunks",
                body=query,
                routing=source_config_id  # 使用路由提高查询效率
            )

            hits = response["hits"]["hits"]
            total_count = response["hits"]["total"]["value"]

            self._log(f"找到 {total_count} 个文档")

            if total_count == 0:
                self._log("⚠️ 没有找到任何文档", 'warning')
                return {
                    'status': 'success',
                    'source_config_id': source_config_id,
                    'deleted_count': 0,
                    'message': '没有找到任何文档'
                }

            # 显示前几个文档的信息
            self._log(f"\n预览前 5 个文档:")
            for i, hit in enumerate(hits[:5], 1):
                doc = hit["_source"]
                self._log(f"  [{i}] ID: {doc.get('chunk_id', 'N/A')[:50]}...")
                self._log(f"      Heading: {doc.get('heading', 'N/A')[:50]}...")

            if total_count > 5:
                self._log(f"  ... 还有 {total_count - 5} 个文档")

            if dry_run:
                self._log(f"\n⚠️ 预览模式：将删除 {total_count} 个文档（未实际删除）")
                return {
                    'status': 'dry_run',
                    'source_config_id': source_config_id,
                    'would_delete_count': total_count,
                    'message': f'预览模式：将删除 {total_count} 个文档'
                }

            # 2. 用户确认删除
            self._log(f"\n{'='*60}")
            self._log(f"⚠️  警告：即将删除 {total_count} 个文档")
            self._log(f"⚠️  信息源 ID: {source_config_id}")
            self._log(f"⚠️  此操作不可撤销！")
            self._log(f"{'='*60}")

            # 交互式确认
            try:
                confirmation = input("\n是否确认删除？输入 'yes' 或 'y' 确认，其他任意键取消: ").strip().lower()

                if confirmation not in ['yes', 'y']:
                    self._log("\n❌ 用户取消删除操作", 'warning')
                    return {
                        'status': 'cancelled',
                        'source_config_id': source_config_id,
                        'message': '用户取消删除操作'
                    }

                self._log("\n✓ 用户已确认删除")
            except (EOFError, KeyboardInterrupt):
                self._log("\n\n❌ 用户中断操作", 'warning')
                return {
                    'status': 'cancelled',
                    'source_config_id': source_config_id,
                    'message': '用户中断操作'
                }

            # 3. 执行删除
            self._log(f"\n开始删除 {total_count} 个文档...")
            delete_start = time.perf_counter()

            # 使用 delete_by_query API 批量删除
            delete_response = await self.es_client.client.delete_by_query(
                index="source_chunks",
                body=query,
                routing=source_config_id,
                refresh=True  # 立即刷新索引
            )

            deleted_count = delete_response.get("deleted", 0)
            delete_time = time.perf_counter() - delete_start

            self._log(f"✓ 删除完成: {deleted_count} 个文档，耗时 {delete_time:.2f}秒")

            # 4. 验证删除结果
            self._log("\n验证删除结果...")
            verify_response = await self.es_client.client.search(
                index="source_chunks",
                body=query,
                routing=source_config_id
            )

            remaining_count = verify_response["hits"]["total"]["value"]

            if remaining_count == 0:
                self._log("✓ 验证通过：所有文档已删除")
            else:
                self._log(f"⚠️ 警告：仍有 {remaining_count} 个文档未删除", 'warning')

            # 5. 构建结果
            result = {
                "status": "completed",
                "source_config_id": source_config_id,
                "deleted_count": deleted_count,
                "remaining_count": remaining_count,
                "delete_time": delete_time,
                "timestamp": datetime.now().isoformat()
            }

            # 6. 保存删除结果
            delete_result_path = self.output_dir / f"delete_result_{source_config_id}.json"
            with open(delete_result_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            self._log(f"💾 删除结果已保存: {delete_result_path}")

            # 7. 打印摘要
            self._log("\n" + "=" * 60)
            self._log("✅ 删除完成")
            self._log("=" * 60)
            self._log(f"信息源 ID: {source_config_id}")
            self._log(f"删除文档数: {deleted_count}")
            self._log(f"剩余文档数: {remaining_count}")
            self._log(f"耗时: {delete_time:.2f}秒")
            self._log("=" * 60)

            return result

        except Exception as e:
            error_msg = f"删除失败: {e}"
            self._log(error_msg, 'error')
            return {
                'status': 'error',
                'source_config_id': source_config_id,
                'message': error_msg
            }

    async def cleanup(self):
        """清理资源"""
        if self.es_client and hasattr(self.es_client, 'client'):
            await self.es_client.client.close()


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description='简单的 RAG 文档上传/删除脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 上传文档（默认）
  python %(prog)s document.md

  # 删除指定信息源
  python %(prog)s --delete --source-config-id rag-document-20231209_143025

  # 删除前预览（不实际删除）
  python %(prog)s --delete --source-config-id rag-document-20231209_143025 --dry-run
        """
    )

    # 操作模式
    parser.add_argument('--delete', action='store_true',
                       help='删除模式（删除指定 source_config_id 的所有文档）')
    parser.add_argument('--source-config-id', type=str,
                       help='[删除模式] 要删除的信息源 ID')
    parser.add_argument('--dry-run', action='store_true',
                       help='[删除模式] 预览模式，不实际删除')

    # 上传模式参数
    parser.add_argument('md_file', type=Path, nargs='?',
                       help='[上传模式] Markdown 文件路径')
    parser.add_argument('--name', type=str, help='[上传模式] 信息源名称（默认使用文件名）')
    parser.add_argument('--description', type=str, help='[上传模式] 信息源描述')
    parser.add_argument('--output-dir', type=Path, help='输出目录')
    parser.add_argument('--max-retries', type=int, default=3, help='最大重试次数（默认: 3）')
    parser.add_argument('--retry-delay', type=int, default=2, help='重试延迟秒数（默认: 2）')
    parser.add_argument('--embedding-batch-size', type=int, default=10,
                       help='[上传模式] Embedding 批量大小（默认: 10）')
    parser.add_argument('--es-batch-size', type=int, default=50,
                       help='[上传模式] ES 批量索引大小（默认: 50）')
    parser.add_argument('--no-timestamp', action='store_true',
                       help='不创建时间戳文件夹')

    args = parser.parse_args()

    # 创建上传器/删除器
    uploader = SimpleRAGUploader(
        output_dir=args.output_dir,
        enable_logging=True,
        use_timestamp_folder=not args.no_timestamp,
        max_retries=args.max_retries,
        retry_delay=args.retry_delay,
        embedding_batch_size=args.embedding_batch_size,
        es_batch_size=args.es_batch_size
    )

    try:
        # 删除模式
        if args.delete:
            if not args.source_config_id:
                print("[ERROR] 删除模式需要指定 --source-config-id")
                sys.exit(1)

            # 执行删除
            result = await uploader.delete_by_source_config_id(
                source_config_id=args.source_config_id,
                dry_run=args.dry_run
            )

            # 打印结果
            print(f"\n删除结果:")
            print(f"  状态: {result.get('status')}")
            print(f"  信息源 ID: {result.get('source_config_id')}")

            if result.get('status') == 'dry_run':
                print(f"  预计删除: {result.get('would_delete_count')} 个文档")
                print(f"\n提示：这是预览模式，未实际删除文档")
                print(f"如需实际删除，请移除 --dry-run 参数")
            elif result.get('status') == 'cancelled':
                print(f"  信息: {result.get('message')}")
                print(f"\n操作已取消，未删除任何文档")
            elif result.get('status') == 'completed':
                print(f"  删除文档数: {result.get('deleted_count')}")
                print(f"  剩余文档数: {result.get('remaining_count')}")
                print(f"  耗时: {result.get('delete_time', 0):.2f}秒")
            elif result.get('status') == 'error':
                print(f"  错误: {result.get('message')}")
                sys.exit(1)

        # 上传模式（默认）
        else:
            if not args.md_file:
                print("[ERROR] 上传模式需要指定 Markdown 文件路径")
                parser.print_help()
                sys.exit(1)

            # 验证文件
            if not args.md_file.exists():
                print(f"[ERROR] 文件不存在: {args.md_file}")
                sys.exit(1)

            # 执行上传
            result = await uploader.upload_markdown(
                md_file_path=args.md_file,
                source_name=args.name,
                source_description=args.description
            )

            # 打印结果
            print(f"\n上传结果:")
            print(f"  状态: {result.get('status')}")
            print(f"  信息源 ID: {result.get('source_config_id')}")
            print(f"  总段落数: {result.get('total_chunks')}")
            print(f"  成功上传: {result.get('chunks_uploaded')}")
            print(f"  结果文件: {result.get('output_dir')}")

            if result.get('status') == 'error':
                sys.exit(1)

    except Exception as e:
        print(f"\n[ERROR] 操作失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # 清理资源
        await uploader.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
