"""
HotpotQA 数据处理模块

封装三个处理阶段：
1. 构建语料库 (build_corpus)
2. 提取标准答案 (extract_oracle)
3. 上传到系统 (upload_corpus)
"""

import json
import logging
import time
import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
import sys
import io

# Ensure UTF-8 encoding for stdout/stderr on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到 Python 路径
# 脚本在 scripts/ 目录下运行，需要添加父目录的父目录
# 即：C:\Users\user\zleap_sag
from pathlib import Path
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

# 导入 DataFlowEngine 和相关配置
from dataflow import DataFlowEngine, ExtractBaseConfig
from dataflow.modules.load.config import DocumentLoadConfig
from evaluation.hotpotqa_evaluation.modules.hotpotqa_loader import HotpotQALoader
from evaluation.hotpotqa_evaluation.modules.utils import (
    format_chunk_id,
    split_merged_id,
    print_stats,
    ChunkDeduplicator
)
from evaluation.hotpotqa_evaluation import config as hotpot_config


class HotpotQAProcessor:
    """
    HotpotQA 数据集处理器

    功能特性：
    - 构建全局语料库（文档级拼接、去重）
    - 提取标准答案（ground truth）
    - 上传语料库到系统（支持测试）
    - 自动生成时间戳文件夹，隔离每次运行

    示例：
        processor = HotpotQAProcessor(
            dataset_path="path/to/hotpotqa",
            data_dir="data"
        )

        # 阶段1：构建语料库
        stats = processor.build_corpus(sample_start=0, sample_end=100)

        # 阶段2：提取标准答案
        stats = processor.extract_oracle(sample_start=0, sample_end=100)

        # 阶段3：上传并测试
        result = await processor.upload_corpus(test_queries=True)
    """

    def __init__(
        self,
        dataset_path: Optional[str] = None,
        base_data_dir: Optional[str] = None,
        enable_logging: bool = True,
        use_timestamp_folder: bool = True
    ):
        """
        初始化处理器

        Args:
            dataset_path: HotpotQA数据集路径，为None则使用config中的配置
            base_data_dir: 基础数据目录，为None则使用config中的配置
            enable_logging: 是否启用日志
            use_timestamp_folder: 是否为每次运行创建时间戳子文件夹
        """
        # Configure paths
        self.dataset_path = dataset_path or hotpot_config.HOTPOTQA_DATASET_PATH

        # Initialize logger first to avoid AttributeError in _log calls
        self.logger = None
        if enable_logging:
            self._setup_logging()

        # Base data directory
        base_dir = Path(base_data_dir) if base_data_dir else hotpot_config.DATA_DIR

        if use_timestamp_folder:
            # Create timestamp subfolder: data/source/20251209_143025/
            self.run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.data_dir = base_dir / "source" / self.run_timestamp
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self._log(f"Created timestamped folder: {self.data_dir}")
        else:
            # Use base directory directly
            self.data_dir = base_dir
            self.data_dir.mkdir(parents=True, exist_ok=True)

        # Output file paths (all inside the timestamped folder)
        self.corpus_path = self.data_dir / "corpus.jsonl"
        self.corpus_md_path = self.data_dir / "corpus_merged.md"
        self.oracle_path = self.data_dir / "oracle.jsonl"
        self.process_result_path = self.data_dir / "process_result.json"

        # 错误收集
        self.errors = []

    @property
    def output_files(self) -> Dict[str, Path]:
        """获取所有输出文件的路径"""
        return {
            'corpus_jsonl': self.corpus_path,
            'corpus_md': self.corpus_md_path,
            'oracle': self.oracle_path,
            'process_result': self.process_result_path
        }

    def get_output_folder(self) -> Path:
        """获取输出文件夹路径"""
        return self.data_dir

    def print_output_info(self):
        """打印输出文件信息"""
        self._log("=" * 60)
        self._log("输出文件位置")
        self._log("=" * 60)
        self._log(f"输出文件夹: {self.data_dir}")
        self._log("文件列表:")
        self._log(f"  - 语料库 (JSONL): {self.corpus_path.name}")
        self._log(f"  - 语料库 (Markdown): {self.corpus_md_path.name}")
        self._log(f"  - 标准答案: {self.oracle_path.name}")
        self._log(f"  - 处理结果: {self.process_result_path.name}")
        self._log("=" * 60)

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

    def _log_error(self, message: str, exc_info: bool = False):
        """记录错误"""
        self.errors.append({
            'timestamp': datetime.now().isoformat(),
            'message': message
        })
        if self.logger:
            self.logger.error(message, exc_info=exc_info)
        else:
            print(f"错误: {message}")

    # ==================== Stage 1: Build Corpus ====================

    def _extract_chunks_from_sample(self, sample: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        从单个样本中提取chunks（文档级拼接）

        Args:
            sample: HotpotQA样本

        Returns:
            chunks列表
        """
        sample_id = sample['id']
        context = sample['context']

        chunks = []

        for idx, (title, sentences) in enumerate(zip(context['title'], context['sentences'])):
            # Document-level concatenation: Markdown format
            chunk_text = f"# {title}\n{' '.join(sentences)}"

            # Generate chunk ID
            chunk_id = format_chunk_id(sample_id, idx)

            chunks.append({
                "id": chunk_id,
                "title": title,
                "text": chunk_text,
                "sample_id": sample_id,
                "local_index": idx
            })

        return chunks

    def build_corpus(
        self,
        sample_start: int = 0,
        sample_end: Optional[int] = None,
        enable_dedup: bool = True,
        append_mode: bool = False
    ) -> Dict[str, Any]:
        """
        构建全局语料库

        Args:
            sample_start: 起始索引（包含）
            sample_end: 结束索引（不包含）
            enable_dedup: 是否启用去重
            append_mode: 追加模式

        Returns:
            统计信息字典
        """
        self._log("=" * 60)
        self._log("阶段1：构建全局语料库")
        self._log("=" * 60)

        try:
            # 1. Load dataset
            self._log(f"\nLoad dataset: {hotpot_config.DATASET_CONFIG}/{hotpot_config.DATASET_SPLIT}")
            loader = HotpotQALoader(self.dataset_path)

            if hotpot_config.DATASET_SPLIT == "validation":
                samples = loader.load_validation(config=hotpot_config.DATASET_CONFIG, limit=None)
            else:
                samples = loader.load_train(config=hotpot_config.DATASET_CONFIG, limit=None)

            total_samples = len(samples)

            # Adjust boundaries
            if sample_end is None or sample_end > total_samples:
                sample_end = total_samples

            if sample_start >= total_samples:
                error_msg = f"Error: Start index {sample_start} exceeds total samples ({total_samples})"
                self._log_error(error_msg)
                return {'status': 'error', 'message': error_msg}

            # Slice dataset
            samples = samples[sample_start:sample_end]

            self._log(f"✓ Total samples: {total_samples}")
            self._log(f"✓ Processing range: [{sample_start}:{sample_end}]")
            self._log(f"✓ Actual samples to process: {len(samples)}\n")

            # 2. Extract all chunks
            self._log("Extract document-level chunks...")
            all_chunks = []

            for sample in samples:
                chunks = self._extract_chunks_from_sample(sample)
                all_chunks.extend(chunks)

            self._log(f"[OK] Extracted {len(all_chunks)} chunks\n")

            # 3. Deduplication
            final_chunks = all_chunks
            if enable_dedup:
                self._log("Deduplicate...")
                deduplicator = ChunkDeduplicator()
                deduplicated_chunks = {}

                for chunk in all_chunks:
                    chunk_id = chunk['id']
                    chunk_text = chunk['text']
                    final_id = deduplicator.add_chunk(chunk_id, chunk_text)

                    if final_id not in deduplicated_chunks:
                        deduplicated_chunks[final_id] = {
                            "id": final_id,
                            "title": chunk['title'],
                            "text": chunk_text
                        }

                dedup_stats = deduplicator.get_stats()
                if hasattr(hotpot_config, 'PRINT_STATS') and hotpot_config.PRINT_STATS:
                    print_stats("Deduplication Stats", dedup_stats)

                final_chunks = list(deduplicated_chunks.values())
                self._log(f"✓ After deduplication: {len(final_chunks)} chunks\n")

            # 4. Save to file
            write_mode = 'a' if append_mode else 'w'
            mode_desc = "Append" if append_mode else "Overwrite"

            self._log(f"Save to: {self.corpus_path} ({mode_desc} mode)")

            # Append mode: check existing data
            existing_ids = set()
            if append_mode and self.corpus_path.exists():
                self._log("Read existing data to check duplicates...")
                with open(self.corpus_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            existing_chunk = json.loads(line)
                            existing_ids.add(existing_chunk['id'])
                self._log(f"✓ Found {len(existing_ids)} existing chunks\n")

            # Filter and save
            chunks_to_save = []
            duplicates_count = 0
            for chunk in final_chunks:
                if chunk['id'] in existing_ids:
                    duplicates_count += 1
                else:
                    chunks_to_save.append(chunk)

            if append_mode and duplicates_count > 0:
                self._log(f"⚠️  Skipped {duplicates_count} duplicate chunks\n")

            with open(self.corpus_path, write_mode, encoding='utf-8') as f:
                for i, chunk in enumerate(chunks_to_save):
                    try:
                        line = json.dumps(chunk, ensure_ascii=False) + '\n'
                        f.write(line)
                        # 每100个chunk刷新一次缓冲区，避免缓冲区过大
                        if (i + 1) % 100 == 0:
                            f.flush()
                            os.fsync(f.fileno())  # 强制写入磁盘
                    except OSError as e:
                        self._log(f"⚠️ 写入chunk {i} 失败 (OSError): {e}, chunk_id={chunk.get('id', 'unknown')}")
                        # 尝试截断过长的text字段后重试
                        if 'text' in chunk and len(chunk['text']) > 50000:
                            chunk['text'] = chunk['text'][:50000] + '... [truncated]'
                            try:
                                line = json.dumps(chunk, ensure_ascii=False) + '\n'
                                f.write(line)
                            except Exception as retry_e:
                                self._log(f"⚠️ 重试写入chunk {i} 仍失败: {retry_e}")
                        raise  # 重新抛出异常以便上层处理
                    except Exception as e:
                        self._log(f"⚠️ 写入chunk {i} 失败: {e}, chunk_id={chunk.get('id', 'unknown')}")
                        raise
                f.flush()
                os.fsync(f.fileno())  # 最终强制写入磁盘

            if append_mode:
                total_records = len(existing_ids) + len(chunks_to_save)
                self._log(f"✓ Added {len(chunks_to_save)} chunks (total {total_records})\n")
            else:
                self._log(f"✓ Saved {len(chunks_to_save)} chunks\n")

            # 5. Generate merged Markdown file
            md_write_mode = 'a' if append_mode else 'w'
            self._log(f"Generate merged Markdown: {self.corpus_md_path} ({mode_desc} mode)")

            with open(self.corpus_md_path, md_write_mode, encoding='utf-8') as f:
                for i, chunk in enumerate(chunks_to_save, 1):
                    f.write(chunk['text'])
                    f.write('\n\n')

                    if i % 100 == 0:
                        self._log(f"  Processed {i}/{len(chunks_to_save)} chunks...")

            self._log(f"✓ Markdown file generated\n")

            # 6. Return statistics
            stats = {
                'status': 'success',
                'sample_count': len(samples),
                'original_chunks': len(all_chunks),
                'final_chunks': len(final_chunks),
                'chunks_saved': len(chunks_to_save),
                'duplicates_skipped': duplicates_count if append_mode else 0,
                'corpus_path': str(self.corpus_path),
                'corpus_md_path': str(self.corpus_md_path),
                'timestamp': datetime.now().isoformat()
            }

            self._log("=" * 60)
            self._log("✅ 阶段1完成")
            self._log("=" * 60)

            return stats

        except Exception as e:
            error_msg = f"阶段1失败: {e}"
            self._log_error(error_msg, exc_info=True)
            return {'status': 'error', 'message': error_msg}

    # ==================== Stage 2: Extract Oracle ====================

    def _load_corpus_index(self) -> Dict[str, Dict]:
        """
        Load corpus and build index

        Returns:
            chunk_id -> chunk mapping
        """
        self._log(f"Load corpus index: {self.corpus_path}")

        corpus_index = {}

        if not self.corpus_path.exists():
            error_msg = f"Error: corpus.jsonl not found: {self.corpus_path}"
            self._log_error(error_msg)
            return corpus_index

        with open(self.corpus_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    chunk = json.loads(line)
                    chunk_id = chunk['id']

                    # Handle merged IDs
                    if "//" in chunk_id:
                        original_ids = split_merged_id(chunk_id)
                        for original_id in original_ids:
                            corpus_index[original_id] = chunk
                    else:
                        corpus_index[chunk_id] = chunk

        self._log(f"✓ Loaded {len(corpus_index)} chunk indexes\n")
        return corpus_index

    def _extract_oracle_for_sample(self, sample: Dict[str, Any], corpus_index: Dict[str, Dict]) -> Dict[str, Any]:
        """
        Extract oracle chunks for single sample

        Args:
            sample: HotpotQA sample
            corpus_index: Corpus index

        Returns:
            Oracle data
        """
        sample_id = sample['id']
        supporting_facts = sample['supporting_facts']
        context = sample['context']

        # 1. Extract titles from supporting_facts
        oracle_titles = supporting_facts['title']

        # 2. Map titles to indices
        title_to_indices = {}
        for idx, title in enumerate(context['title']):
            if title not in title_to_indices:
                title_to_indices[title] = []
            title_to_indices[title].append(idx)

        # 3. Construct chunk IDs
        oracle_chunk_ids = []
        oracle_titles_unique = []

        for title in oracle_titles:
            if title in title_to_indices:
                idx = title_to_indices[title][0]
                chunk_id = format_chunk_id(sample_id, idx)

                if chunk_id in corpus_index:
                    oracle_chunk_ids.append(chunk_id)
                    if title not in oracle_titles_unique:
                        oracle_titles_unique.append(title)
                else:
                    self._log(f"⚠️  Warning: chunk ID {chunk_id} not in corpus (sample {sample_id})", 'warning')

        # 4. Deduplicate (preserve order)
        seen = set()
        deduplicated_ids = []
        for chunk_id in oracle_chunk_ids:
            if chunk_id not in seen:
                deduplicated_ids.append(chunk_id)
                seen.add(chunk_id)

        return {
            "id": sample_id,
            "question": sample['question'],
            "answer": sample['answer'],
            "oracle_chunk_ids": deduplicated_ids,
            "oracle_titles": oracle_titles_unique,
            "type": sample['type'],
            "level": sample['level']
        }

    def extract_oracle(
        self,
        sample_start: int = 0,
        sample_end: Optional[int] = None,
        append_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Extract oracle (ground truth)

        Args:
            sample_start: Start index (inclusive)
            sample_end: End index (exclusive)
            append_mode: Append mode

        Returns:
            Statistics dictionary
        """
        self._log("=" * 60)
        self._log("阶段2：提取标准答案（Oracle）")
        self._log("=" * 60)

        try:
            # 1. Load corpus index
            corpus_index = self._load_corpus_index()
            if not corpus_index:
                return {'status': 'error', 'message': 'Failed to load corpus index'}

            # 2. Load dataset
            self._log(f"Load dataset: {hotpot_config.DATASET_CONFIG}/{hotpot_config.DATASET_SPLIT}")
            loader = HotpotQALoader(self.dataset_path)

            if hotpot_config.DATASET_SPLIT == "validation":
                samples = loader.load_validation(config=hotpot_config.DATASET_CONFIG, limit=None)
            else:
                samples = loader.load_train(config=hotpot_config.DATASET_CONFIG, limit=None)

            total_samples = len(samples)

            # Adjust boundaries
            if sample_end is None or sample_end > total_samples:
                sample_end = total_samples

            if sample_start >= total_samples:
                error_msg = f"Error: Start index {sample_start} exceeds total samples ({total_samples})"
                self._log_error(error_msg)
                return {'status': 'error', 'message': error_msg}

            samples = samples[sample_start:sample_end]

            self._log(f"✓ Total samples: {total_samples}")
            self._log(f"✓ Processing range: [{sample_start}:{sample_end}]")
            self._log(f"✓ Actual samples to process: {len(samples)}\n")

            # 3. Extract oracle
            self._log("Extract oracle chunks...")

            oracles = []
            total_oracle_chunks = 0
            missing_chunks = 0

            for sample in samples:
                oracle = self._extract_oracle_for_sample(sample, corpus_index)
                oracles.append(oracle)
                total_oracle_chunks += len(oracle['oracle_chunk_ids'])

                expected_count = len(sample['supporting_facts']['title'])
                actual_count = len(oracle['oracle_chunk_ids'])
                if actual_count < expected_count:
                    missing_chunks += (expected_count - actual_count)

            self._log(f"✓ Extracted oracle for {len(oracles)} questions\n")

            # 4. Save to file
            write_mode = 'a' if append_mode else 'w'
            mode_desc = "Append" if append_mode else "Overwrite"

            self._log(f"Save to: {self.oracle_path} ({mode_desc} mode)")

            # Append mode: check existing data
            existing_ids = set()
            if append_mode and self.oracle_path.exists():
                self._log("Read existing data to check duplicates...")
                with open(self.oracle_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            existing_oracle = json.loads(line)
                            existing_ids.add(existing_oracle['id'])
                self._log(f"✓ Found {len(existing_ids)} existing records\n")

            # Filter and save
            oracles_to_save = []
            duplicates_count = 0
            for oracle in oracles:
                if oracle['id'] in existing_ids:
                    duplicates_count += 1
                else:
                    oracles_to_save.append(oracle)

            if append_mode and duplicates_count > 0:
                self._log(f"⚠️  Skipped {duplicates_count} duplicate oracle records\n")

            with open(self.oracle_path, write_mode, encoding='utf-8') as f:
                for oracle in oracles_to_save:
                    f.write(json.dumps(oracle, ensure_ascii=False) + '\n')

            if append_mode:
                total_records = len(existing_ids) + len(oracles_to_save)
                self._log(f"✓ Added {len(oracles_to_save)} oracle records (total {total_records})\n")
            else:
                self._log(f"✓ Saved {len(oracles_to_save)} oracle records\n")

            # 5. Statistics
            oracle_counts = [len(o['oracle_chunk_ids']) for o in oracles]
            avg_oracle_count = sum(oracle_counts) / len(oracle_counts) if oracle_counts else 0

            type_stats = {}
            level_stats = {}
            for oracle in oracles:
                type_stats[oracle['type']] = type_stats.get(oracle['type'], 0) + 1
                level_stats[oracle['level']] = level_stats.get(oracle['level'], 0) + 1

            stats = {
                'status': 'success',
                'question_count': len(oracles),
                'oracle_chunk_total': total_oracle_chunks,
                'avg_oracle_per_question': avg_oracle_count,
                'missing_chunks': missing_chunks,
                'type_distribution': type_stats,
                'level_distribution': level_stats,
                'oracle_path': str(self.oracle_path),
                'file_size_kb': self.oracle_path.stat().st_size / 1024 if self.oracle_path.exists() else 0,
                'timestamp': datetime.now().isoformat()
            }

            self._log("=" * 60)
            self._log("✅ 阶段2完成")
            self._log("=" * 60)

            return stats

        except Exception as e:
            error_msg = f"阶段2失败: {e}"
            self._log_error(error_msg, exc_info=True)
            return {'status': 'error', 'message': error_msg}

    # ==================== Stage 3: Upload Corpus ====================

    def _load_existing_result(self) -> Optional[Dict[str, Any]]:
        """Load existing processing result"""
        if not self.process_result_path.exists():
            return None

        try:
            with open(self.process_result_path, 'r', encoding='utf-8') as f:
                result = json.load(f)

            if 'source_config_id' in result and 'article_id' in result:
                return result
            else:
                self._log("⚠️  process_result.json missing required fields", 'warning')
                return None
        except Exception as e:
            self._log(f"⚠️  Failed to read process_result.json: {e}", 'warning')
            return None

    async def upload_corpus(
        self,
        source_name: str = "HotpotQA Corpus",
        source_description: str = "HotpotQA Evaluation Corpus (Document-level concatenation, deduplicated)",
        enable_extraction: bool = True
    ) -> Dict[str, Any]:
        """
        上传语料库到系统（使用 DataFlowEngine）

        Args:
            source_name: 信息源名称
            source_description: 信息源描述
            enable_extraction: 是否执行提取阶段（False 则只加载文档）

        Returns:
            处理结果字典
        """
        self._log("=" * 60)
        self._log("阶段3：处理语料库并加载到系统")
        self._log("=" * 60)

        # 检查文件是否存在
        if not self.corpus_md_path.exists():
            error_msg = f"错误：corpus_merged.md 不存在: {self.corpus_md_path}"
            self._log_error(error_msg)
            return {'status': 'error', 'message': error_msg}

        file_size_mb = self.corpus_md_path.stat().st_size / 1024 / 1024
        self._log(f"\n语料库文件: {self.corpus_md_path}")
        self._log(f"   文件大小: {file_size_mb:.2f} MB\n")

        # 创建 DataFlowEngine
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        source_config_id = f"hotpotqa-corpus-{timestamp}"

        self._log(f"创建信息源...")
        self._log(f"   信息源 ID: {source_config_id}")
        self._log(f"   信息源名称: {source_name}")
        self._log(f"   描述: {source_description}\n")

        engine = DataFlowEngine(source_config_id=source_config_id)

        # Load 阶段 - 加载文档
        self._log(f"开始加载语料库文件...")
        load_start = time.perf_counter()

        try:
            await engine.load_async(
                DocumentLoadConfig(
                    path=str(self.corpus_md_path),
                    recursive=False,
                    source_config_id=source_config_id
                )
            )
            load_time = time.perf_counter() - load_start
            self._log(f"✅ 文档加载完成，耗时: {load_time:.1f} 秒\n")
        except Exception as e:
            error_msg = f"文档加载失败: {e}"
            self._log_error(error_msg, exc_info=True)
            return {'status': 'error', 'message': error_msg}

        # 获取 Load 结果
        engine_result = engine.get_result()
        if not engine_result or not engine_result.load_result:
            error_msg = "Load 阶段失败：无法获取加载结果"
            self._log_error(error_msg)
            return {'status': 'error', 'message': error_msg}

        # 从 engine_result 获取数据
        # Note: article_id 在 engine_result 上，chunk_count 在 load_result.stats 中
        try:
            article_id = engine_result.article_id
            load_result = engine_result.load_result
            sections_count = load_result.stats.get("chunk_count", 0) if load_result.stats else 0

            self._log(f"Load 统计:")
            self._log(f"   Article ID: {article_id}")
            self._log(f"   文档片段数: {sections_count}\n")
        except Exception as e:
            error_msg = f"读取 Load 结果失败: {e}"
            self._log_error(error_msg, exc_info=True)
            return {'status': 'error', 'message': error_msg}

        events_count = 0

        # Extract 阶段 - 提取事项（可选）
        if enable_extraction:
            self._log(f"开始提取事项...")
            extract_start = time.perf_counter()

            try:
                await engine.extract_async(
                    ExtractBaseConfig(
                        parallel=True,
                        max_concurrency=50
                    )
                )
                extract_time = time.perf_counter() - extract_start
                self._log(f"✅ 事项提取完成，耗时: {extract_time:.1f} 秒\n")

                # 获取 Extract 结果
                engine_result = engine.get_result()
                if engine_result and engine_result.extract_result:
                    extract_result = engine_result.extract_result
                    events_count = len(extract_result.data_ids) if extract_result.data_ids else 0
                    self._log(f"Extract 统计:")
                    self._log(f"   生成事项数: {events_count}\n")
                else:
                    self._log(f"⚠️  Extract 结果为空\n")
            except Exception as e:
                error_msg = f"事项提取失败: {e}"
                self._log_error(error_msg, exc_info=True)
                # 提取失败不返回错误，因为 Load 已经成功
        else:
            extract_time = 0
            self._log(f"跳过提取阶段（enable_extraction=False）\n")

        # 构建结果
        total_time = load_time + extract_time
        result = {
            "source_config_id": source_config_id,
            "source_name": source_name,
            "source_description": source_description,
            "article_id": article_id,
            "sections_count": sections_count,
            "events_count": events_count,
            "load_time_seconds": load_time,
            "extract_time_seconds": extract_time if enable_extraction else 0,
            "total_processing_time_seconds": total_time,
            "corpus_file": str(self.corpus_md_path),
            "corpus_size_mb": file_size_mb,
            "timestamp": timestamp,
            "status": "completed",
            "extraction_enabled": enable_extraction
        }

        # 保存结果
        with open(self.process_result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        self._log(f"💾 处理结果已保存: {self.process_result_path}\n")

        # 返回结果
        self._log("=" * 60)
        self._log("✅ 阶段3完成")
        self._log("=" * 60)

        return result



# ==================== Usage Examples ====================

if __name__ == "__main__":
    import argparse

    # 设置命令行参数
    parser = argparse.ArgumentParser(description='HotpotQA 数据处理流程')
    parser.add_argument('--start', type=int, default=0, help='起始样本索引 (default: 0)')
    parser.add_argument('--end', type=int, default=None, help='结束样本索引 (default: None, 处理全部数据)')
    parser.add_argument('--enable-extraction', action='store_false', help='禁用事项提取 (默认: 启用)')
    parser.add_argument('--no-upload', action='store_true', help='不上传到系统，只构建数据文件 (默认: 上传)')
    parser.add_argument('--no-log', action='store_true', help='禁用日志输出')

    args = parser.parse_args()

    # 示例1：基本用法（带自动时间戳文件夹）
    async def example1(sample_start: int, sample_end: int, enable_extraction: bool, skip_upload: bool):
        # 创建文件夹: data/source/YYYYMMDD_HHMMSS/
        processor = HotpotQAProcessor(
            enable_logging=not args.no_log,
            use_timestamp_folder=True  # 默认选项，创建时间戳子文件夹
        )

        # 打印输出位置
        processor.print_output_info()
        print(f"\n处理样本范围: [{sample_start}:{sample_end}]")
        print(f"事项提取: {'启用' if enable_extraction else '禁用'}")
        print(f"上传信息源: {'禁用' if skip_upload else '启用'}")

        # 分阶段处理
        print("\n阶段1: 构建语料库...")
        stats = processor.build_corpus(sample_start=sample_start, sample_end=sample_end)
        print(f"✓ 语料库构建完成: {stats.get('final_chunks', 0)} 个chunks")

        print("\n阶段2: 提取标准答案...")
        stats = processor.extract_oracle(sample_start=sample_start, sample_end=sample_end)
        print(f"✓ 标准答案提取完成: {stats.get('question_count', 0)} 个问题")

        # 阶段3: 上传到系统（可选）
        if not skip_upload:
            print("\n阶段3: 上传到系统...")
            result = await processor.upload_corpus(enable_extraction=enable_extraction)
            print(f"✓ 上传完成: source_config_id={result.get('source_config_id')}")
        else:
            print("\n阶段3: 跳过上传（--no-upload）")

        # 显示文件保存位置
        print(f"\n{'='*60}")
        print("所有文件已保存至:")
        print(f"  {processor.get_output_folder()}")
        print(f"{'='*60}")


    # 运行示例
    print("=" * 60)
    print("HotpotQAProcessor 使用示例")
    print("=" * 60)
    print(f"\n处理参数:")
    print(f"  样本范围: [{args.start}:{args.end}]")
    print(f"  事项提取: {'启用' if args.enable_extraction else '禁用'}")
    print(f"  上传信息源: {'禁用' if args.no_upload else '启用'}")
    print(f"  日志输出: {'启用' if not args.no_log else '禁用'}")
    print("=" * 60)

    # 执行处理（注意：--enable-extraction 现在是否定标志）
    asyncio.run(example1(args.start, args.end, args.enable_extraction, args.no_upload))
