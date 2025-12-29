"""
HotpotQA 数据集与检索系统集成工具

功能：
1. 将 HotpotQA 样本转换为 MD 格式
2. 创建信息源
3. 上传 MD 文件到信息源
4. 等待事项创建完成
5. 根据问题搜索事项

使用示例:
    from hotpotqa_pipeline import HotpotQAPipeline

    pipeline = HotpotQAPipeline(
        api_base_url="http://localhost:8000/api/v1",
        dataset_path="path/to/hotpotqa"
    )

    # 运行完整流程
    results = pipeline.run_pipeline(sample_limit=5)
"""

import json
import time
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional
from hotpotqa_loader import HotpotQALoader


class HotpotQAPipeline:
    """HotpotQA 与检索系统集成管道"""

    def __init__(
        self,
        api_base_url: str = "http://localhost:8000/api/v1",
        dataset_path: Optional[str] = None
    ):
        """
        初始化管道

        Args:
            api_base_url: API 基础 URL
            dataset_path: HotpotQA 数据集路径（可选）
        """
        self.api_base_url = api_base_url.rstrip('/')
        self.dataset_path = dataset_path
        self.loader = HotpotQALoader(dataset_path) if dataset_path else None

    def sample_to_markdown(self, sample: Dict[str, Any]) -> str:
        """
        将单个 HotpotQA 样本转换为 Markdown 格式

        Args:
            sample: HotpotQA 样本

        Returns:
            Markdown 格式的文本
        """
        md_lines = []

        # 标题：使用问题作为主标题
        md_lines.append(f"# {sample['question']}\n")

        # 元数据
        md_lines.append("## 元数据\n")
        md_lines.append(f"- **问题ID**: {sample['id']}")
        md_lines.append(f"- **问题类型**: {sample['type']}")
        md_lines.append(f"- **难度等级**: {sample['level']}")
        md_lines.append(f"- **标准答案**: {sample['answer']}\n")

        # 上下文文档
        md_lines.append("## 上下文文档\n")
        context = sample['context']

        for i, (title, sentences) in enumerate(zip(context['title'], context['sentences']), 1):
            md_lines.append(f"### {i}. {title}\n")

            # 将句子合并为段落
            content = " ".join(sentences)
            md_lines.append(f"{content}\n")

        # 支持性事实（可选，用于验证）
        if self.loader:
            supporting_sentences = self.loader.get_supporting_sentences(sample)
            if supporting_sentences:
                md_lines.append("## 支持性事实\n")
                for i, sent in enumerate(supporting_sentences, 1):
                    md_lines.append(f"{i}. {sent}")
                md_lines.append("")

        return "\n".join(md_lines)

    def save_sample_to_md(
        self,
        sample: Dict[str, Any],
        output_path: str
    ) -> str:
        """
        保存样本为 MD 文件

        Args:
            sample: HotpotQA 样本
            output_path: 输出文件路径

        Returns:
            保存的文件路径
        """
        md_content = self.sample_to_markdown(sample)

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(md_content)

        print(f"✓ MD 文件已保存: {output_file}")
        return str(output_file)

    def create_source(
        self,
        name: str = "HotpotQA 测试数据集",
        description: str = "用于测试的 HotpotQA 问答数据",
        config: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        创建信息源

        Args:
            name: 信息源名称
            description: 信息源描述
            config: 配置信息

        Returns:
            创建的信息源数据（包含 source_config_id）
        """
        url = f"{self.api_base_url}/sources"

        payload = {
            "name": name,
            "description": description,
            "config": config or {
                "focus": ["问答", "知识检索"],
                "language": "zh"
            }
        }

        print(f"📝 创建信息源: {name}")
        response = requests.post(url, json=payload)
        response.raise_for_status()

        result = response.json()
        source_config_id = result['data']['id']
        print(f"✅ 信息源创建成功: {source_config_id}\n")

        return result['data']

    def _match_document(
        self,
        documents: list,
        filename: str,
        upload_time,
        time_tolerance_seconds: int = 300
    ) -> Optional[Dict]:
        """
        从文档列表中匹配目标文档

        匹配规则（按优先级）：
        1. 创建时间在上传时间前后 5 分钟内
        2. 文件名匹配（标题包含文件名或文件名包含标题）
        3. 优先返回最新的文档

        Args:
            documents: 文档列表
            filename: 目标文件名
            upload_time: 上传时间（UTC）
            time_tolerance_seconds: 时间容差（秒）

        Returns:
            匹配的文档，如果没找到返回 None
        """
        from datetime import datetime

        # 预处理文件名（去除扩展名）
        filename_base = Path(filename).stem

        candidates = []

        for doc in documents:
            doc_id = doc.get("id", "")
            doc_title = doc.get("title", "")
            doc_created_time = doc.get("created_time", "")

            # 解析创建时间
            try:
                # ISO 8601 格式: "2024-01-01T10:00:00"
                doc_time = datetime.fromisoformat(
                    doc_created_time.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                print(f"      ⚠️  无法解析时间: {doc_created_time}")
                continue

            # 时间匹配：在上传时间前后 time_tolerance_seconds 秒内
            time_diff = abs((doc_time - upload_time).total_seconds())
            is_time_match = time_diff <= time_tolerance_seconds

            # 文件名匹配（宽松匹配）
            is_name_match = (
                filename_base.lower() in doc_title.lower() or
                doc_title.lower() in filename_base.lower() or
                filename.lower() in doc_title.lower()
            )

            print(f"      检查: {doc_title[:40]}...")
            print(
                f"         时间差: {time_diff:.1f}秒 ({'✓' if is_time_match else '✗'})")
            print(f"         名称匹配: {'✓' if is_name_match else '✗'}")

            # 如果时间匹配，加入候选（放宽条件，不强制名称匹配）
            if is_time_match:
                candidates.append({
                    "doc": doc,
                    "time_diff": time_diff,
                    "name_match": is_name_match
                })
                print(f"         → 加入候选")

        # 如果有候选，优先选择名称匹配的，其次选择时间最近的
        if candidates:
            # 先按名称匹配排序，再按时间排序
            candidates.sort(key=lambda x: (
                not x["name_match"], x["time_diff"]))
            best_match = candidates[0]["doc"]
            print(f"\n      🎯 最佳匹配: {best_match['id']}")
            return best_match

        return None

    def _find_document_from_list(
        self,
        source_config_id: str,
        filename: str,
        upload_time,
        max_attempts: int = 10,
        interval: int = 2
    ) -> str:
        """
        从文档列表中查找刚上传的文档

        Args:
            source_config_id: 信息源 ID
            filename: 上传的文件名
            upload_time: 上传时间（UTC）
            max_attempts: 最大尝试次数
            interval: 每次尝试间隔（秒）

        Returns:
            article_id: 文档 ID

        Raises:
            ValueError: 找不到文档
        """
        print(f"   🔍 从文档列表查找...")

        for attempt in range(1, max_attempts + 1):
            print(f"\n   尝试 {attempt}/{max_attempts}...")

            # 等待后端处理（给数据库插入留时间）
            if attempt > 1:
                time.sleep(interval)

            try:
                # 调用列表 API（模仿 Web 端的 getDocuments）
                response = requests.get(
                    f"{self.api_base_url}/sources/{source_config_id}/documents",
                    params={"page": 1, "page_size": 20},
                    timeout=10
                )

                response.raise_for_status()
                result = response.json()

                documents = result.get("data", [])
                print(f"      获取到 {len(documents)} 个文档")

                # 查找匹配的文档
                matched_doc = self._match_document(
                    documents=documents,
                    filename=filename,
                    upload_time=upload_time
                )

                if matched_doc:
                    article_id = matched_doc["id"]
                    print(f"\n   ✅ 找到匹配文档!")
                    print(f"      Article ID: {article_id}")
                    print(
                        f"      标题: {matched_doc.get('title', 'N/A')[:60]}...")
                    print(f"      状态: {matched_doc.get('status', 'N/A')}")
                    return article_id

                print(f"      ⏳ 未找到匹配文档，继续等待...")

            except requests.exceptions.RequestException as e:
                print(f"      ⚠️  请求失败: {e}")
                if attempt == max_attempts:
                    raise

        # 所有尝试都失败
        raise ValueError(
            f"无法从文档列表中找到刚上传的文件: {filename}\n"
            f"已尝试 {max_attempts} 次，每次间隔 {interval} 秒\n"
            f"可能原因：\n"
            f"1. 后端处理异常（检查日志）\n"
            f"2. 文件未成功插入数据库\n"
            f"3. auto_process 参数未生效"
        )

    def get_document_by_filename(
        self,
        source_config_id: str,
        filename: str,
        max_wait: int = 30
    ) -> Optional[str]:
        """
        通过文件名查询文档 ID（轮询方式）
        已弃用：推荐直接使用 _find_document_from_list

        Args:
            source_config_id: 信息源 ID
            filename: 文件名
            max_wait: 最大等待时间（秒）

        Returns:
            article_id，如果找不到返回 None
        """
        from datetime import datetime
        upload_time = datetime.utcnow()
        try:
            return self._find_document_from_list(
                source_config_id=source_config_id,
                filename=filename,
                upload_time=upload_time,
                max_attempts=max_wait // 2,
                interval=2
            )
        except ValueError:
            return None

    def upload_document(
        self,
        source_config_id: str,
        file_path: str,
        background: str = "HotpotQA 问答数据集文档",
        auto_process: bool = True
    ) -> Dict[str, Any]:
        """
        上传 MD 文件到信息源
        模仿 Web 端逻辑：上传 → 尝试获取 article_id → 失败则查询列表

        Args:
            source_config_id: 信息源 ID
            file_path: MD 文件路径
            background: 文档背景描述
            auto_process: 是否自动处理

        Returns:
            上传结果（包含 article_id 和获取方式）
        """
        from datetime import datetime

        url = f"{self.api_base_url}/sources/{source_config_id}/documents/upload"
        filename = Path(file_path).name

        print(f"📤 上传文件: {filename}")

        # 记录上传开始时间（用于后续匹配）
        upload_start_time = datetime.utcnow()

        with open(file_path, 'rb') as f:
            files = {'file': (filename, f, 'text/markdown')}
            data = {
                'background': background,
                'auto_process': str(auto_process).lower()
            }

            response = requests.post(url, files=files, data=data)
            response.raise_for_status()

        result = response.json()

        # 打印完整的 API 响应（方便调试）
        print(f"\n📋 API 上传响应:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print()

        # 检查上传是否成功
        if not result.get('success'):
            error_msg = result.get('message', '未知错误')
            raise Exception(f"上传失败: {error_msg}")

        print(f"✅ 文件上传成功")

        # 🎯 方案 1：尝试从响应中直接获取 article_id
        data_obj = result.get('data', {})
        article_id_from_response = data_obj.get('article_id')

        if article_id_from_response and str(article_id_from_response) != 'null':
            print(f"✅ 从响应获取到 article_id: {article_id_from_response}")
            return {
                'article_id': article_id_from_response,
                'filename': filename,
                'source_config_id': source_config_id,
                'method': 'response'
            }

        # 🎯 方案 2：响应中没有 article_id，通过文档列表查询（模仿 Web 端逻辑）
        print(f"⚠️  响应中 article_id 为 null，使用列表查询...")

        article_id = self._find_document_from_list(
            source_config_id=source_config_id,
            filename=filename,
            upload_time=upload_start_time,
            max_attempts=10,
            interval=2
        )

        print(f"✅ 获取到 Article ID: {article_id}\n")

        # 返回包含 article_id 的数据
        return {
            'article_id': article_id,
            'filename': filename,
            'source_config_id': source_config_id,
            'method': 'list_query'
        }

    def wait_for_completion(
        self,
        article_id: str,
        max_attempts: int = 60,
        poll_interval: int = 2
    ) -> Dict[str, Any]:
        """
        等待文档处理完成（轮询状态）

        Args:
            article_id: 文档 ID
            max_attempts: 最大尝试次数
            poll_interval: 轮询间隔（秒）

        Returns:
            文档最终状态
        """
        # 验证 article_id
        if not article_id or str(article_id).lower() in ['none', 'null', '']:
            raise ValueError(f"❌ 无效的 article_id: {article_id}")

        url = f"{self.api_base_url}/documents/{article_id}"

        print(f"⏳ 等待事项生成完成... (article_id: {article_id})")

        for attempt in range(1, max_attempts + 1):
            response = requests.get(url)
            response.raise_for_status()

            result = response.json()
            data = result['data']
            status = data['status']
            events_count = data.get('events_count', 0)

            if status == 'COMPLETED':
                print(f"✅ 事项生成完成！共生成 {events_count} 个事项\n")
                return data
            elif status == 'FAILED':
                error_msg = data.get('error_message', '未知错误')
                raise Exception(f"❌ 事项生成失败: {error_msg}")
            else:
                print(f"   进度: {attempt}/{max_attempts} - 状态: {status}")
                time.sleep(poll_interval)

        raise TimeoutError(f"❌ 轮询超时：超过 {max_attempts * poll_interval} 秒")

    def search_events(
        self,
        source_config_id: str,
        query: str,
        mode: str = "fast",
        top_k: int = 5,
        threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        根据问题搜索事项

        Args:
            source_config_id: 信息源 ID
            query: 查询问题
            mode: 搜索模式（fast/normal）
            top_k: 返回前 K 个结果
            threshold: 相似度阈值

        Returns:
            搜索到的事项列表
        """
        url = f"{self.api_base_url}/pipeline/search"

        payload = {
            "source_config_id": source_config_id,
            "query": query,
            "mode": mode,
            "top_k": top_k,
            "threshold": threshold
        }

        print(f"🔍 搜索问题: {query}")
        response = requests.post(url, json=payload)
        response.raise_for_status()

        result = response.json()
        events = result['data'].get('events', [])

        print(f"✅ 找到 {len(events)} 个相关事项\n")

        # # 打印搜索结果
        # for i, event in enumerate(events, 1):
        #     print(f"{i}. {event.get('title', 'N/A')}")
        #     print(f"   summary: {event.get('summary', 'N/A')}")
        #     print(f"   content: {event.get('content', 'N/A')}")

        return events

    def delete_source(self, source_config_id: str):
        """
        删除信息源（级联删除所有数据）

        Args:
            source_config_id: 信息源 ID
        """
        url = f"{self.api_base_url}/sources/{source_config_id}"

        print(f"🗑️  删除信息源: {source_config_id}")
        response = requests.delete(url)
        response.raise_for_status()

        print(f"✅ 信息源已删除（包括所有文档和事项）\n")

    def run_pipeline(
        self,
        sample_limit: int = 1,
        config: str = "distractor",
        cleanup: bool = False,
        output_dir: str = "./hotpotqa_output"
    ) -> Dict[str, Any]:
        """
        运行完整的测试流程

        Args:
            sample_limit: 要处理的样本数量
            config: HotpotQA 配置（distractor/fullwiki）
            cleanup: 是否在结束后清理数据
            output_dir: MD 文件输出目录

        Returns:
            流程执行结果
        """
        if not self.loader:
            raise ValueError("未设置 dataset_path，无法加载数据集")

        print("="*60)
        print("🚀 HotpotQA 检索系统测试流程")
        print("="*60 + "\n")

        # 1. 加载数据集
        print(f"📊 加载 HotpotQA 数据集...")
        samples = self.loader.load_validation(
            config=config, limit=sample_limit)
        print(f"✓ 加载了 {len(samples)} 个样本\n")

        results = {
            "samples": [],
            "source_config_id": None,
            "total_samples": len(samples)
        }

        # 2. 创建信息源
        source_data = self.create_source(
            name=f"HotpotQA 测试集 ({config})",
            description=f"包含 {len(samples)} 个 HotpotQA 样本"
        )
        source_config_id = source_data['id']
        results['source_config_id'] = source_config_id

        try:
            # 3. 处理每个样本
            for i, sample in enumerate(samples, 1):
                print(f"\n{'='*60}")
                print(f"📄 处理样本 {i}/{len(samples)}: {sample['id']}")
                print(f"{'='*60}\n")

                sample_result = {
                    "sample_id": sample['id'],
                    "question": sample['question'],
                    "answer": sample['answer'],
                    "type": sample['type'],
                    "level": sample['level']
                }

                # 3.1 转换为 MD 文件
                md_filename = f"{sample['id']}.md"
                md_path = Path(output_dir) / md_filename
                self.save_sample_to_md(sample, str(md_path))
                sample_result['md_file'] = str(md_path)

                # 3.2 上传到信息源
                upload_result = self.upload_document(
                    source_config_id=source_config_id,
                    file_path=str(md_path),
                    background=f"问题: {sample['question']}"
                )
                sample_result['article_id'] = upload_result['article_id']

                # 3.3 等待处理完成
                doc_status = self.wait_for_completion(
                    article_id=upload_result['article_id']
                )
                sample_result['events_count'] = doc_status.get(
                    'events_count', 0)

                # 3.4 使用原问题搜索
                search_results = self.search_events(
                    source_config_id=source_config_id,
                    query=sample['question'],
                    top_k=5
                )
                sample_result['search_results'] = search_results

                results['samples'].append(sample_result)

            # 4. 总结
            print("\n" + "="*60)
            print("📊 流程执行完成")
            print("="*60)
            print(f"✓ 处理样本数: {len(results['samples'])}")
            print(f"✓ 信息源 ID: {source_config_id}")

            total_events = sum(s['events_count'] for s in results['samples'])
            print(f"✓ 生成事项总数: {total_events}")

        finally:
            # 5. 清理（可选）
            if cleanup:
                print("\n")
                self.delete_source(source_config_id)

        return results


def main():
    """示例用法"""

    # 配置参数
    API_BASE_URL = "http://localhost:8000/api/v1"
    DATASET_PATH = r"C:\Users\user\Downloads\bench dataset\datasets--hotpotqa--hotpot_qa\snapshots\1908d6afbbead072334abe2965f91bd2709910ab"

    # 创建管道
    pipeline = HotpotQAPipeline(
        api_base_url=API_BASE_URL,
        dataset_path=DATASET_PATH
    )

    # 运行完整流程（处理 3 个样本）
    results = pipeline.run_pipeline(
        sample_limit=3,
        config="distractor",
        cleanup=False,  # 设置为 True 会在结束后删除信息源
        output_dir="./hotpotqa_output"
    )

    # 保存结果
    output_file = Path("./hotpotqa_test_results.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 结果已保存到: {output_file}")


if __name__ == "__main__":
    main()
