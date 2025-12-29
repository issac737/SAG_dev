"""
测试从数据库加载会话并执行 Extract

流程：
1. 创建信息源
2. 创建真实的会话数据（ChatConversation + ChatMessage）- 不手动切块
3. 调用 /pipeline/run API 执行 load_from_database + extract
4. API 内部的 ConversationLoader 会自动处理切块和保存 SourceChunk
5. 轮询任务状态
6. 验证结果

测试目标：验证 API 的自动处理功能、可用性和准确性
"""

import asyncio
import os
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dataflow.db import ChatConversation, ChatMessage, get_session_factory
from dataflow.models.conversation import MessageType, SenderRole

# 加载环境变量
load_dotenv()

# 配置
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_VERSION = "/api/v1"
API_BASE = f"{API_BASE_URL}{API_VERSION}"


class TestLoadConversation:
    """测试从数据库加载会话"""

    def __init__(self):
        self.api_base = API_BASE
        self.session_factory = get_session_factory()
        self.source_config_id = None
        self.conversation_id = None
        self.start_time = None
        self.end_time = None

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
                "name": f"测试信息源-会话处理-{datetime.now().strftime('%H%M%S')}",
                "description": "用于测试会话自动处理的信息源",
                "config": {
                    "test": True, 
                    "platform": "wechat",
                    "scenario": "customer_service"
                }
            },
            timeout=30
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

    async def insert_mock_conversation(self):
        """
        创建真实的会话数据到数据库
        
        只创建 ChatConversation 和 ChatMessage
        不手动切块，让 API 内部的 ConversationLoader 自动处理
        """
        self.print_step(2, "创建真实会话数据（ChatConversation + ChatMessage）")

        # 准备会话脚本（一个真实的客服咨询场景）
        base_time = datetime.now().replace(minute=0, second=0, microsecond=0)
        self.start_time = base_time
        
        conversation_script = [
            {
                "role": SenderRole.USER,
                "sender_id": "user_001",
                "sender_name": "张三",
                "sender_avatar": "https://example.com/avatar/user001.jpg",
                "sender_title": "客户",
                "content": "你好，我想了解一下你们公司的智能客服系统。我们是一家电商平台，每天客服咨询量很大，想引入AI系统辅助人工客服。",
                "offset_minutes": 0,
                "type": MessageType.TEXT
            },
            {
                "role": SenderRole.ASSISTANT,
                "sender_id": "assistant_001",
                "sender_name": "AI助手",
                "sender_avatar": "https://example.com/avatar/assistant.jpg",
                "sender_title": "销售顾问",
                "content": "您好！很高兴为您服务。我们的智能客服系统主要包括以下核心功能：\n\n1. **智能问答引擎**：基于大语言模型，能够理解客户意图，自动回答常见问题，准确率达95%以上\n2. **工单自动分类**：智能识别客户问题类型，自动路由到对应的专业客服团队\n3. **情感分析**：实时监测客户情绪，对负面情绪及时预警并优先处理\n4. **知识库管理**：支持导入产品手册、FAQ等，自动提取关键信息构建知识图谱\n5. **多渠道接入**：支持网站、APP、微信、抖音等多平台统一接入\n\n请问您的日均咨询量大概是多少？这样我可以为您推荐更合适的方案。",
                "offset_minutes": 2,
                "type": MessageType.TEXT
            },
            {
                "role": SenderRole.USER,
                "sender_id": "user_001",
                "sender_name": "张三",
                "sender_avatar": "https://example.com/avatar/user001.jpg",
                "sender_title": "客户",
                "content": "我们日均咨询量在5000-8000之间，高峰期（如促销活动）可能达到1.5万。目前有30个人工客服，但还是经常忙不过来，客户等待时间太长导致投诉较多。",
                "offset_minutes": 8,
                "type": MessageType.TEXT
            },
            {
                "role": SenderRole.ASSISTANT,
                "sender_id": "assistant_001",
                "sender_name": "AI助手",
                "sender_avatar": "https://example.com/avatar/assistant.jpg",
                "sender_title": "销售顾问",
                "content": "明白了，您这个规模非常适合部署我们的智能客服系统。针对您的需求，我推荐以下方案：\n\n**方案配置：**\n- 部署规模：标准版（支持1万并发对话）\n- AI机器人：可处理70-80%的常见问题\n- 人机协同：复杂问题自动转人工，AI辅助人工客服提供答案建议\n\n**预期效果：**\n- 客服响应时间：从平均5分钟降至30秒内\n- 问题解决率：AI独立解决70%，转人工30%\n- 人力成本：可减少40-50%人工客服投入\n- 客户满意度：预计提升25-30个百分点\n\n您对这个方案感兴趣吗？",
                "offset_minutes": 15,
                "type": MessageType.TEXT
            },
            {
                "role": SenderRole.USER,
                "sender_id": "user_001",
                "sender_name": "张三",
                "sender_avatar": "https://example.com/avatar/user001.jpg",
                "sender_title": "客户",
                "content": "听起来不错！我想了解一下系统的部署方式和周期。另外，成本方面大概是怎样的？",
                "offset_minutes": 20,
                "type": MessageType.TEXT
            },
            {
                "role": SenderRole.ASSISTANT,
                "sender_id": "assistant_001",
                "sender_name": "AI助手",
                "sender_avatar": "https://example.com/avatar/assistant.jpg",
                "sender_title": "销售顾问",
                "content": "**部署方式：**\n我们提供两种部署方式供您选择：\n\n1. **SaaS云端部署**（推荐）\n   - 优势：快速上线，无需维护，自动升级\n   - 周期：3-5个工作日即可上线\n\n2. **私有化部署**\n   - 优势：数据完全自主可控，可定制化开发\n   - 周期：2-3周\n\n**成本结构：**\nSaaS云端版：约12-15万/年\n私有化部署：首年约38万，次年仅需维护费5万",
                "offset_minutes": 25,
                "type": MessageType.TEXT
            },
            {
                "role": SenderRole.USER,
                "sender_id": "user_001",
                "sender_name": "张三",
                "sender_avatar": "https://example.com/avatar/user001.jpg",
                "sender_title": "客户",
                "content": "我们倾向于SaaS方案，这样上线快一些。能否安排一次产品演示？最好本周内，我们技术团队也想一起参与评估。",
                "offset_minutes": 90,
                "type": MessageType.TEXT
            },
            {
                "role": SenderRole.ASSISTANT,
                "sender_id": "assistant_001",
                "sender_name": "AI助手",
                "sender_avatar": "https://example.com/avatar/assistant.jpg",
                "sender_title": "销售顾问",
                "content": "好的，我为您安排产品演示。\n\n**演示安排：**\n- 时间建议：本周四下午14:00-16:00\n- 形式：线上会议（腾讯会议/飞书）或现场演示\n- 演示内容：系统功能完整展示、实际场景模拟、技术架构讲解、客户案例分享\n\n我会在今天下午给您发送正式的会议邀请。",
                "offset_minutes": 95,
                "type": MessageType.TEXT
            }
        ]

        async with self.session_factory() as session:
            # 创建 ChatConversation
            conversation_id = str(uuid.uuid4())
            self.conversation_id = conversation_id

            conversation = ChatConversation(
                id=conversation_id,
                source_config_id=self.source_config_id,
                title="智能客服系统咨询对话",
                last_message_time=None,  # 稍后更新
                messages_count=len(conversation_script),
                extra_data={
                    "scenario": "customer_service",
                    "platform": "wechat",
                    "customer_type": "enterprise",
                    "industry": "e-commerce",
                    "tags": ["产品咨询", "方案推荐", "价格谈判"]
                },
                del_flag=0,  # 正常状态
                delete_time=None
            )
            session.add(conversation)
            await session.flush()

            # 创建 ChatMessage（严格按照数据库设计）
            messages = []
            for i, msg_data in enumerate(conversation_script):
                msg_time = base_time + timedelta(minutes=msg_data["offset_minutes"])
                
                message = ChatMessage(
                    id=str(uuid.uuid4()),
                    conversation_id=conversation.id,
                    timestamp=msg_time,
                    content=msg_data["content"],
                    sender_id=msg_data.get("sender_id"),
                    sender_name=msg_data["sender_name"],
                    sender_avatar=msg_data.get("sender_avatar"),
                    sender_title=msg_data.get("sender_title"),
                    type=msg_data.get("type", MessageType.TEXT),
                    sender_role=msg_data["role"],
                    extra_data={
                        "message_index": i,
                        "platform": "wechat",
                        "client": "ios"
                    },
                    del_flag=0,  # 正常状态
                    delete_time=None
                )
                session.add(message)
                messages.append(message)

            # 更新会话的最后消息时间
            conversation.last_message_time = messages[-1].timestamp
            self.end_time = messages[-1].timestamp

            await session.commit()

            self.print_success(f"会话创建成功: {conversation_id}")
            self.print_info(f"  - 标题: {conversation.title}")
            self.print_info(f"  - 消息数量: {len(messages)}")
            self.print_info(f"  - 时间跨度: {(self.end_time - self.start_time).total_seconds() / 60:.0f} 分钟")
            self.print_info(f"  ⚠️  注意：不手动切块，由 API 的 ConversationLoader 自动处理")

    def run_pipeline(self) -> str:
        """调用 pipeline 接口执行 load + extract"""
        self.print_step(3, "调用 Pipeline API（自动处理会话 → 事项）")

        payload = {
            "source_config_id": self.source_config_id,
            "task_name": "测试会话自动处理",
            "task_description": "测试 ConversationLoader 自动切块 + Extract 提取事项",
            "background": "这是一段智能客服系统的商业咨询对话，包含产品介绍、方案推荐、价格咨询和演示安排",
            "load": {
                # "source_config_id": self.source_config_id,
                "conversation_id": self.conversation_id,
                "start_time": self.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": self.end_time.strftime("%Y-%m-%d %H:%M:%S"),
                "interval_minutes": 60,  # 60分钟时间窗口
                # "max_tokens": 8000,      # 每个 chunk 最大 8000 tokens
                # "auto_vector": True
            },
            "extract": {
                "max_concurrency": 5,
                # "auto_vector": True
            }
        }

        self.print_info("请求配置:")
        self.print_info(f"  - source_config_id: {self.source_config_id}")
        self.print_info(f"  - conversation_id: {self.conversation_id}")
        self.print_info(f"  - 时间范围: {self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}")
        self.print_info(f"  - 时间窗口: {payload['load']['interval_minutes']} 分钟")
        self.print_info(f"  - 最大tokens: {payload['load'].get('max_tokens', 8000)}")

        response = requests.post(
            f"{self.api_base}/pipeline/run",
            json=payload,
            timeout=30
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
            response = requests.get(f"{self.api_base}/tasks/{task_id}", timeout=30)

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
            self.print_info(f"  ✅ ConversationLoader 自动完成了切块和保存")
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

            # 2. 创建真实会话数据（不手动切块）
            await self.insert_mock_conversation()

            # 3. 调用 Pipeline API（让 API 自动处理）
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
║  测试：会话自动处理（Conversation → SourceChunk → Event） ║
║  测试目标：验证 API 的自动处理功能、可用性和准确性           ║
╚══════════════════════════════════════════════════════════╝
""")

    test = TestLoadConversation()
    await test.run()


if __name__ == "__main__":
    asyncio.run(main())
