"""
测试从数据库加载文章并执行 Extract

流程：
1. 创建信息源
2. 直接写入模拟数据到数据库（Article + ArticleSection + SourceChunk）
3. 调用 /pipeline/run 执行 load_from_database + extract
4. 轮询任务状态
5. 验证结果
"""

import asyncio
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dataflow.db import Article, ArticleSection, SourceChunk, get_session_factory
from dataflow.modules.load.parser import MarkdownParser
from dataflow.modules.load.sentence_splitter import SentenceSplitter

# 加载环境变量
load_dotenv()

# 配置
# 通过 nginx 反向代理访问 API (端口 80)
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost")
API_VERSION = "/api/v1"
API_BASE = f"{API_BASE_URL}{API_VERSION}"


class TestLoadFromDatabase:
    """测试从数据库加载文章"""

    def __init__(self):
        self.api_base = API_BASE
        self.session_factory = get_session_factory()
        self.source_config_id = None
        self.article_id = None

    def print_step(self, step: int, message: str):
        """打印步骤信息"""
        print(f"\n{'='*60}")
        print(f"步骤 {step}: {message}")
        print(f"{'='*60}")

    def print_success(self, message: str):
        """打印成功信息"""
        print(f"✅ {message}")

    def print_error(self, message: str):
        """打印错误信息"""
        print(f"❌ {message}")

    def print_info(self, message: str):
        """打印信息"""
        print(f"ℹ️  {message}")

    def create_source(self) -> str:
        """创建信息源"""
        self.print_step(1, "创建信息源")

        response = requests.post(
            f"{self.api_base}/sources",
            json={
                "name": f"测试信息源-LoadFromDB-{datetime.now().strftime('%H%M%S')}",
                "description": "用于测试从数据库加载文章的信息源",
                "config": {"test": True}
            }
        )

        if response.status_code == 201:
            data = response.json()
            source_id = data["data"]["id"]
            self.source_config_id = source_id
            self.print_success(f"信息源创建成功: {source_id}")
            return source_id
        else:
            self.print_error(f"创建信息源失败: {response.text}")
            raise Exception(f"创建信息源失败: {response.status_code}")

    async def insert_mock_data(self):
        """
        写入模拟数据到数据库

        流程（遵循 loader.py 的 _save_to_database 逻辑）：
        1. 创建 Article 记录（包含完整 Markdown 格式的文章内容）
        2. 使用 MarkdownParser.parse_content() 解析内容 → 得到 sections
        3. 遍历 sections，为每个 section：
           - 创建 SourceChunk 记录
           - 使用 SentenceSplitter.split_by_punctuation() 切分内容为句子
           - 为每个句子创建 ArticleSection 记录
           - 更新 SourceChunk.references 字段记录它包含的所有 ArticleSection IDs
        """
        self.print_step(2, "写入模拟数据到数据库（使用 Parser 和 Splitter）")

        # 1. 准备完整的 Markdown 文章内容
        markdown_content = """# 深度学习技术综述

深度学习是机器学习的一个分支，它使用多层神经网络来学习数据的表示。近年来在图像识别、自然语言处理等领域取得了突破性进展。

## 基础概念

深度学习的核心是神经网络，特别是深度神经网络（DNN）。这些网络由多个层组成，每一层都可以学习不同级别的特征表示。神经网络通过反向传播算法进行训练，不断调整权重以最小化损失函数。梯度下降是最常用的优化算法。

## 主要技术

### 卷积神经网络（CNN）

CNN主要用于图像处理任务，它通过卷积层提取图像特征，在计算机视觉领域取得了巨大成功。卷积层可以自动学习图像的局部特征，通过池化层降低维度。著名的CNN架构包括LeNet、AlexNet、VGG、ResNet等。这些架构在ImageNet等比赛中取得了优异成绩。

### 循环神经网络（RNN）

RNN专门用于处理序列数据，如自然语言处理和时间序列分析。传统RNN存在梯度消失问题，难以处理长序列。LSTM和GRU是RNN的改进版本，能更好地处理长期依赖问题。LSTM通过门控机制控制信息流动，有效解决了梯度消失问题。

### Transformer架构

Transformer使用注意力机制，在NLP任务中表现出色。它摒弃了循环结构，完全基于注意力机制。BERT、GPT等模型都基于Transformer架构。自注意力机制允许模型在处理序列时关注所有位置，并行计算大大提高了训练效率。

## 应用场景

深度学习已在多个领域得到广泛应用。在计算机视觉领域，包括图像分类、目标检测、图像生成等任务。在自然语言处理领域，应用于机器翻译、文本生成、情感分析等。语音识别方面有语音转文字、语音合成等应用。推荐系统中用于个性化推荐、内容过滤等场景。

## 未来展望

深度学习将继续快速发展。预训练模型技术使得小样本学习成为可能。迁移学习让模型可以在不同任务间共享知识。联邦学习保护用户隐私的同时实现协同训练。多模态学习、可解释AI、边缘计算等方向也将成为研究热点。
"""

        # 2. 初始化解析器和切分器
        self.print_info("初始化 MarkdownParser 和 SentenceSplitter...")

        parser = MarkdownParser(
            max_tokens=1000,
            model_type="generic",
            enable_converter=False,  # 我们直接处理 Markdown，不需要转换器
            min_content_length=50,
            merge_short_sections=True
        )

        sentence_splitter = SentenceSplitter(min_sentence_length=5)

        # 3. 使用 MarkdownParser 解析内容
        self.print_info("使用 MarkdownParser 解析 Markdown 内容...")
        sections = parser.parse_content(markdown_content)
        self.print_success(f"MarkdownParser 解析出 {len(sections)} 个 sections (将成为 SourceChunks)")

        # 4. 保存到数据库（遵循 loader.py 的 _save_to_database 逻辑）
        async with self.session_factory() as session:
            # 4.1 创建 Article
            article_id = str(uuid.uuid4())
            self.article_id = article_id

            article = Article(
                id=article_id,
                source_config_id=self.source_config_id,
                title="深度学习技术综述",
                summary="本文介绍了深度学习的基本概念、主要技术和应用场景",
                content=markdown_content,  # 保存完整的 Markdown 内容
                category="AI技术",
                tags=["深度学习", "神经网络", "AI"],  # tags 应该是 list 类型
                status="COMPLETED",
                extra_data={
                    "source": "test_script",
                    "test": True,
                    "parser_settings": {
                        "max_tokens": 1000,
                        "min_content_length": 50
                    }
                }
            )
            session.add(article)
            await session.flush()  # 确保 article.id 可用

            # 4.2 遍历 sections，创建 SourceChunk 和 ArticleSection
            # 使用计数器保持 ArticleSection 的 rank 连续递增
            section_rank_counter = 0
            total_sentences = 0

            self.print_info(f"开始处理 {len(sections)} 个 SourceChunks...")

            for chunk_model in sections:
                # 创建 SourceChunk
                chunk_id = str(uuid.uuid4())
                chunk_length = len(chunk_model.content)

                source_chunk = SourceChunk(
                    id=chunk_id,
                    source_type="ARTICLE",
                    source_id=article.id,
                    source_config_id=self.source_config_id,
                    heading=chunk_model.heading or "",
                    content=chunk_model.content,
                    raw_content=chunk_model.content,  # 保存原始内容
                    rank=chunk_model.rank,
                    chunk_length=chunk_length,
                    extra_data=chunk_model.extra_data,  # 保存 parser 的 extra_data (level, char_count, word_count)
                )
                session.add(source_chunk)

                # 使用 SentenceSplitter 切分内容为句子
                sentences = sentence_splitter.split_by_punctuation(chunk_model.content)
                total_sentences += len(sentences)

                # 为每个句子创建 ArticleSection
                section_ids = []
                for sentence in sentences:
                    section_id = str(uuid.uuid4())
                    section_ids.append(section_id)

                    section = ArticleSection(
                        id=section_id,
                        article_id=article.id,
                        rank=section_rank_counter,  # 连续递增
                        heading=chunk_model.heading or "",  # 继承 SourceChunk 的 heading
                        content=sentence,
                        extra_data={
                            "type": "TEXT",
                            "from_chunk": chunk_id,
                            "chunk_heading": chunk_model.heading
                        }
                    )
                    session.add(section)
                    section_rank_counter += 1

                # 更新 SourceChunk 的 references 字段
                # references 记录这个 SourceChunk 包含的所有 ArticleSection IDs
                source_chunk.references = section_ids

            await session.commit()

            self.print_success(f"Article 创建成功: {article_id}")
            self.print_success(f"  - 标题: 深度学习技术综述")
            self.print_success(f"  - 内容长度: {len(markdown_content)} 字符")
            self.print_success(f"SourceChunks 创建成功: {len(sections)} 个")
            self.print_success(f"ArticleSections 创建成功: {total_sentences} 个句子")
            self.print_info(f"  - 平均每个 SourceChunk 包含 {total_sentences / len(sections):.1f} 个句子")

    def run_pipeline(self) -> str:
        """调用 pipeline 接口执行 load + extract"""
        self.print_step(3, "调用 Pipeline 接口（Load from Database + Extract）")

        payload = {
            "source_config_id": self.source_config_id,
            "task_name": "测试从数据库加载文章",
            "task_description": "测试 load_from_database 功能和 extract 流程",
            "background": "这是一篇关于深度学习技术的综述文章",
            "load": {
                # "source_config_id": self.source_config_id,
                "article_id": self.article_id,
                "load_from_database": True,
                # "max_tokens": 8000,
                # "auto_vector": True
            },
            "extract": {
                "max_concurrency": 5,
                # "auto_vector": True
            }
        }

        self.print_info(f"请求配置:")
        self.print_info(f"  - source_config_id: {self.source_config_id}")
        self.print_info(f"  - article_id: {self.article_id}")
        self.print_info(f"  - load_from_database: True")
        self.print_info(f"  - extract.max_concurrency: 5")

        response = requests.post(
            f"{self.api_base}/pipeline/run",
            json=payload
        )

        if response.status_code == 202:
            data = response.json()
            task_id = data["data"]["task_id"]
            self.print_success(f"Pipeline 任务创建成功: {task_id}")
            return task_id
        else:
            self.print_error(f"Pipeline 任务创建失败: {response.text}")
            raise Exception(f"Pipeline 任务创建失败: {response.status_code}")

    def poll_task_status(self, task_id: str, timeout: int = 300):
        """轮询任务状态"""
        self.print_step(4, "轮询任务状态")

        start_time = time.time()
        last_status = None

        while time.time() - start_time < timeout:
            response = requests.get(f"{self.api_base}/tasks/{task_id}")

            if response.status_code != 200:
                self.print_error(f"查询任务状态失败: {response.text}")
                time.sleep(2)
                continue

            data = response.json()
            task_data = data["data"]
            status = task_data["status"]
            progress = task_data.get("progress", 0) or 0  # 处理 None 的情况
            message = task_data.get("message", "")

            # 只在状态变化时打印
            if status != last_status:
                self.print_info(f"状态: {status} | 进度: {progress:.1%} | {message}")
                last_status = status

            if status == "completed":
                self.print_success("任务执行完成！")
                return task_data
            elif status == "failed":
                error = task_data.get("error", "未知错误")
                self.print_error(f"任务执行失败: {error}")
                return task_data

            time.sleep(2)

        self.print_error(f"任务超时（{timeout}秒）")
        return None

    def verify_results(self, task_data: dict):
        """验证结果"""
        self.print_step(5, "验证结果")

        if not task_data:
            self.print_error("没有任务数据")
            return

        result = task_data.get("result", {})

        # Load 阶段结果
        if "load_result" in result:
            load_result = result["load_result"]
            self.print_success("Load 阶段:")
            self.print_info(f"  - 状态: {load_result.get('status')}")
            self.print_info(f"  - Chunk数量: {len(load_result.get('data_ids', []))}")
            if load_result.get("stats"):
                self.print_info(f"  - 统计: {load_result['stats']}")

        # Extract 阶段结果
        if "extract_result" in result:
            extract_result = result["extract_result"]
            self.print_success("Extract 阶段:")
            self.print_info(f"  - 状态: {extract_result.get('status')}")
            self.print_info(f"  - 事项数量: {len(extract_result.get('data_ids', []))}")
            if extract_result.get("stats"):
                self.print_info(f"  - 统计: {extract_result['stats']}")

        # 打印完整结果
        print("\n" + "="*60)
        print("完整任务结果:")
        print("="*60)
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False))

    async def run(self):
        """运行完整测试流程"""
        try:
            # 1. 创建信息源
            self.create_source()

            # 2. 写入模拟数据
            await self.insert_mock_data()

            # 3. 调用 Pipeline
            task_id = self.run_pipeline()

            # 4. 轮询任务状态
            task_data = self.poll_task_status(task_id)

            # 5. 验证结果
            self.verify_results(task_data)

            print("\n" + "="*60)
            print("✅ 测试完成！")
            print("="*60)

        except Exception as e:
            self.print_error(f"测试失败: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """主函数"""
    print("""
╔══════════════════════════════════════════════════════════╗
║  测试：从数据库加载文章并执行 Extract                      ║
╚══════════════════════════════════════════════════════════╝
""")

    test = TestLoadFromDatabase()
    await test.run()


if __name__ == "__main__":
    asyncio.run(main())
