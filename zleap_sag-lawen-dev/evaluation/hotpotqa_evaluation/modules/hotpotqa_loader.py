"""
HotpotQA 数据集加载和处理工具

功能：
1. 加载 HotpotQA 数据集 (parquet 格式)
2. 数据预处理和格式转换
3. 导出为 Event Flow 可用的格式
4. 生成 RAGAS 评估数据集

使用方法:
    from hotpotqa_loader import HotpotQALoader

    # 加载数据集
    loader = HotpotQALoader("path/to/hotpotqa")
    samples = loader.load_validation(limit=100)

    # 转换为 Event Flow 格式
    documents = loader.to_eventflow_documents(samples)
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd


class HotpotQALoader:
    """HotpotQA 数据集加载器"""

    def __init__(self, dataset_path: str):
        """
        初始化加载器

        Args:
            dataset_path: HotpotQA 数据集根目录
                例如: "C:/Users/user/Downloads/bench dataset/datasets--hotpotqa--hotpot_qa/snapshots/xxx"
        """
        self.dataset_path = Path(dataset_path)
        self.distractor_path = self.dataset_path / "distractor"
        self.fullwiki_path = self.dataset_path / "fullwiki"

    def load_validation(
        self,
        config: str = "distractor",
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        加载验证集

        Args:
            config: 配置类型，"distractor" 或 "fullwiki"
            limit: 限制加载的样本数量，None 表示加载全部

        Returns:
            样本列表
        """
        if config == "distractor":
            parquet_path = self.distractor_path / "validation-00000-of-00001.parquet"
        else:
            parquet_path = self.fullwiki_path / "validation-00000-of-00001.parquet"

        if not parquet_path.exists():
            raise FileNotFoundError(f"数据文件不存在: {parquet_path}")

        # 读取 parquet 文件
        df = pd.read_parquet(parquet_path)

        if limit:
            df = df.head(limit)

        # 转换为字典列表
        samples = df.to_dict("records")

        print(f"✓ 加载了 {len(samples)} 个样本 (config={config})")
        return samples

    def load_train(
        self,
        config: str = "distractor",
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """加载训练集"""
        if config == "distractor":
            base_path = self.distractor_path
        else:
            base_path = self.fullwiki_path

        # 训练集分为两个文件
        dfs = []
        for i in range(2):
            parquet_path = base_path / f"train-0000{i}-of-00002.parquet"
            if parquet_path.exists():
                df = pd.read_parquet(parquet_path)
                dfs.append(df)

        df = pd.concat(dfs, ignore_index=True)

        if limit:
            df = df.head(limit)

        samples = df.to_dict("records")
        print(f"✓ 加载了 {len(samples)} 个训练样本 (config={config})")
        return samples

    def get_sample_info(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        """获取样本基本信息"""
        return {
            "id": sample["id"],
            "question": sample["question"],
            "answer": sample["answer"],
            "type": sample["type"],
            "level": sample["level"],
            "num_contexts": len(sample["context"]["title"]),
            "num_supporting_facts": len(sample["supporting_facts"]["title"]),
        }

    def get_supporting_sentences(self, sample: Dict[str, Any]) -> List[str]:
        """
        获取支持句子（ground truth）

        Returns:
            支持句子列表
        """
        supporting_facts = sample["supporting_facts"]
        context = sample["context"]

        sentences = []

        # 将 numpy array 转换为 list（从 parquet 读取时是 numpy array）
        context_titles = list(context["title"]) if hasattr(context["title"], 'tolist') else context["title"]

        for title, sent_id in zip(
            supporting_facts["title"], supporting_facts["sent_id"]
        ):
            # 找到对应的文档
            try:
                doc_idx = context_titles.index(title)
                sentence = context["sentences"][doc_idx][sent_id]
                sentences.append(sentence)
            except (ValueError, IndexError):
                continue

        return sentences

    def to_eventflow_documents(
        self,
        samples: List[Dict[str, Any]],
        merge_sentences: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        转换为 Event Flow 可用的文档格式

        Args:
            samples: HotpotQA 样本列表
            merge_sentences: 是否将同一文档的句子合并

        Returns:
            文档列表，格式:
            [
                {
                    "title": "文档标题",
                    "content": "文档内容",
                    "metadata": {...}
                }
            ]
        """
        documents = []

        for sample in samples:
            context = sample["context"]

            for i, (title, sentences) in enumerate(
                zip(context["title"], context["sentences"])
            ):
                if merge_sentences:
                    # 合并句子为一个文档
                    content = " ".join(sentences)
                    documents.append(
                        {
                            "title": title,
                            "content": content,
                            "metadata": {
                                "question_id": sample["id"],
                                "doc_index": i,
                                "num_sentences": len(sentences),
                            },
                        }
                    )
                else:
                    # 每个句子作为独立文档
                    for j, sentence in enumerate(sentences):
                        documents.append(
                            {
                                "title": f"{title} (Sent {j})",
                                "content": sentence,
                                "metadata": {
                                    "question_id": sample["id"],
                                    "doc_index": i,
                                    "sent_index": j,
                                },
                            }
                        )

        return documents

    def to_ragas_format(
        self,
        samples: List[Dict[str, Any]],
        search_results: Optional[List[List[Dict]]] = None,
    ) -> Dict[str, List]:
        """
        转换为 RAGAS 评估格式

        Args:
            samples: HotpotQA 样本
            search_results: Event Flow 的检索结果（可选）

        Returns:
            RAGAS 格式的数据:
            {
                "question": [...],
                "ground_truth": [...],
                "contexts": [...],
                "answer": [...] (如果有 search_results)
            }
        """
        ragas_data = {
            "question": [],
            "ground_truth": [],
            "contexts": [],
        }

        for i, sample in enumerate(samples):
            ragas_data["question"].append(sample["question"])
            ragas_data["ground_truth"].append(sample["answer"])

            # 使用 supporting facts 作为理想上下文
            supporting_sentences = self.get_supporting_sentences(sample)
            ragas_data["contexts"].append(supporting_sentences)

        # 如果有检索结果，添加答案字段
        if search_results:
            ragas_data["answer"] = []
            for result in search_results:
                # 提取检索到的事项作为答案
                if result:
                    answer = result[0].get("summary", "")
                else:
                    answer = ""
                ragas_data["answer"].append(answer)

        return ragas_data

    def save_to_markdown(
        self,
        samples: List[Dict[str, Any]],
        output_path: str,
        limit: int = 10,
    ):
        """
        保存样本为 Markdown 格式（便于导入 Event Flow）

        Args:
            samples: 样本列表
            output_path: 输出目录
            limit: 每个文件包含的样本数量
        """
        output_dir = Path(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)

        for i in range(0, len(samples), limit):
            batch = samples[i : i + limit]
            file_path = output_dir / f"hotpotqa_batch_{i//limit + 1}.md"

            with open(file_path, "w", encoding="utf-8") as f:
                for sample in batch:
                    # 写入问题信息
                    f.write(f"# Question: {sample['question']}\n\n")
                    f.write(f"**Type**: {sample['type']} | ")
                    f.write(f"**Level**: {sample['level']} | ")
                    f.write(f"**Answer**: {sample['answer']}\n\n")

                    # 写入上下文文档
                    f.write("## Context Documents\n\n")
                    context = sample["context"]
                    for title, sentences in zip(
                        context["title"], context["sentences"]
                    ):
                        f.write(f"### {title}\n\n")
                        for sentence in sentences:
                            f.write(f"{sentence}\n\n")

                    f.write("---\n\n")

            print(f"✓ 保存到: {file_path}")

    def analyze_dataset(
        self,
        samples: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """分析数据集统计信息"""
        stats = {
            "total_samples": len(samples),
            "question_types": {},
            "difficulty_levels": {},
            "avg_contexts": 0,
            "avg_supporting_facts": 0,
        }

        total_contexts = 0
        total_supporting = 0

        for sample in samples:
            # 问题类型统计
            q_type = sample["type"]
            stats["question_types"][q_type] = (
                stats["question_types"].get(q_type, 0) + 1
            )

            # 难度统计
            level = sample["level"]
            stats["difficulty_levels"][level] = (
                stats["difficulty_levels"].get(level, 0) + 1
            )

            # 上下文统计
            total_contexts += len(sample["context"]["title"])
            total_supporting += len(sample["supporting_facts"]["title"])

        stats["avg_contexts"] = total_contexts / len(samples)
        stats["avg_supporting_facts"] = total_supporting / len(samples)

        return stats

    def print_sample(self, sample: Dict[str, Any]):
        """打印样本详细信息（用于调试）"""
        print("\n" + "=" * 60)
        print(f"ID: {sample['id']}")
        print(f"Question: {sample['question']}")
        print(f"Answer: {sample['answer']}")
        print(f"Type: {sample['type']} | Level: {sample['level']}")

        print("\n--- Supporting Facts ---")
        supporting_sentences = self.get_supporting_sentences(sample)
        for i, sent in enumerate(supporting_sentences, 1):
            print(f"{i}. {sent}")

        print("\n--- Context Documents ---")
        context = sample["context"]
        for title, sentences in zip(context["title"], context["sentences"]):
            print(f"\n{title}:")
            for sent in sentences:
                print(f"  - {sent}")

        print("=" * 60 + "\n")


def main():
    """示例用法"""

    # 修改为你的数据集路径
    DATASET_PATH = r"C:\Users\user\Downloads\bench dataset\datasets--hotpotqa--hotpot_qa\snapshots\1908d6afbbead072334abe2965f91bd2709910ab"

    loader = HotpotQALoader(DATASET_PATH)

    # 加载验证集的前 10 个样本
    samples = loader.load_validation(config="distractor", limit=10)

    # 分析数据集
    stats = loader.analyze_dataset(samples)
    print("\n数据集统计:")
    print(json.dumps(stats, indent=2))

    # 打印第一个样本
    if samples:
        loader.print_sample(samples[0])

    # 转换为 Event Flow 文档格式
    documents = loader.to_eventflow_documents(samples)
    print(f"\n转换为 {len(documents)} 个文档")

    # 保存为 Markdown
    # loader.save_to_markdown(samples, "./hotpotqa_data", limit=10)


if __name__ == "__main__":
    main()
