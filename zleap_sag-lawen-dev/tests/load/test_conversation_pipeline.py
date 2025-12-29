"""
测试 ConversationLoader - 完整流程

这个脚本完成完整的测试流程：
1. 生成测试数据（3个场景）
2. 自动运行测试
3. 询问是否删除测试数据
"""

import asyncio
import uuid
from datetime import datetime, timedelta

from dataflow.modules.load import ConversationLoadConfig, ConversationLoader
from dataflow.db import (
    ChatConversation,
    ChatMessage,
    SourceConfig,
    get_session_factory,
    init_database,
    SourceChunk,
)
from dataflow.models.conversation import MessageType, SenderRole
from sqlalchemy import select


# ==============================================================================
# 数据生成部分
# ==============================================================================

async def generate_test_conversations():
    """生成测试会话数据并返回测试配置"""

    print("\n" + "=" * 80)
    print("生成测试数据")
    print("=" * 80)

    # 初始化数据库
    await init_database()

    session_factory = get_session_factory()

    async with session_factory() as session:
        # 1. 创建测试信息源
        source_config_id = str(uuid.uuid4())
        source_config = SourceConfig(
            id=source_config_id,
            name="测试会话源",
            description="用于测试 ConversationLoader 的信息源",
            config={"platform": "test"},
        )
        session.add(source_config)
        await session.flush()

        print(f"✓ 创建信息源: {source_config_id}")

        # 2. 场景1：正常时间窗口（60分钟间隔）
        conversation_id_1 = str(uuid.uuid4())
        conversation_1 = ChatConversation(
            id=conversation_id_1,
            source_config_id=source_config_id,
            title="测试会话1 - 正常时间窗口",
            last_message_time=datetime.now(),
            messages_count=0,
        )
        session.add(conversation_1)
        await session.flush()

        # 生成消息（2小时内，每10分钟几条消息）
        base_time_1 = datetime(2025, 1, 1, 10, 0, 0)
        messages_1 = []
        for i in range(12):  # 12个10分钟时间段
            time_offset = timedelta(minutes=i * 10)
            for j in range(3):  # 每个时间段3条消息
                msg_time = base_time_1 + time_offset + timedelta(seconds=j * 30)
                sender_role = SenderRole.USER if j % 2 == 0 else SenderRole.ASSISTANT

                message = ChatMessage(
                    id=str(uuid.uuid4()),
                    conversation_id=conversation_id_1,
                    timestamp=msg_time,
                    content=f"这是测试消息 #{i * 3 + j + 1}，时间段 {i + 1}",
                    sender_name="张三" if sender_role == SenderRole.USER else "AI助手",
                    sender_role=sender_role,
                    type=MessageType.TEXT,
                )
                session.add(message)
                messages_1.append(message)

        conversation_1.messages_count = len(messages_1)
        conversation_1.last_message_time = messages_1[-1].timestamp

        print(f"✓ 创建会话1: {len(messages_1)} 条消息")

        # 3. 场景2：Token溢出场景（单窗口消息超多）
        conversation_id_2 = str(uuid.uuid4())
        conversation_2 = ChatConversation(
            id=conversation_id_2,
            source_config_id=source_config_id,
            title="测试会话2 - Token溢出场景",
            last_message_time=datetime.now(),
            messages_count=0,
        )
        session.add(conversation_2)
        await session.flush()

        # 生成大量消息（1小时内，100条消息，每条消息较长）
        base_time_2 = datetime(2025, 1, 2, 14, 0, 0)
        messages_2 = []
        for i in range(100):
            time_offset = timedelta(seconds=i * 36)  # 每36秒一条消息
            msg_time = base_time_2 + time_offset
            sender_role = SenderRole.USER if i % 2 == 0 else SenderRole.ASSISTANT

            long_content = f"""这是一条较长的测试消息 #{i + 1}。
我们在讨论一个复杂的技术话题，涉及到架构设计、性能优化、安全性考虑等等。
需要仔细权衡各种因素，做出最佳的技术选择。
这条消息的目的是为了测试当单个时间窗口内消息过多时，系统如何处理 token 溢出的情况。"""

            message = ChatMessage(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id_2,
                timestamp=msg_time,
                content=long_content,
                sender_name="李四" if sender_role == SenderRole.USER else "AI专家",
                sender_role=sender_role,
                type=MessageType.TEXT,
            )
            session.add(message)
            messages_2.append(message)

        conversation_2.messages_count = len(messages_2)
        conversation_2.last_message_time = messages_2[-1].timestamp

        print(f"✓ 创建会话2: {len(messages_2)} 条消息")

        # 4. 场景3：跨多个时间窗口场景
        conversation_id_3 = str(uuid.uuid4())
        conversation_3 = ChatConversation(
            id=conversation_id_3,
            source_config_id=source_config_id,
            title="测试会话3 - 跨多个时间窗口",
            last_message_time=datetime.now(),
            messages_count=0,
        )
        session.add(conversation_3)
        await session.flush()

        # 生成消息（6小时内，分散在不同时间段）
        base_time_3 = datetime(2025, 1, 3, 9, 0, 0)
        messages_3 = []

        for hour in range(6):
            hour_base_time = base_time_3 + timedelta(hours=hour)
            msg_count = 5 + (hour * 2)
            for i in range(msg_count):
                time_offset = timedelta(
                    minutes=i * (60 // msg_count),
                    seconds=i * 15,
                )
                msg_time = hour_base_time + time_offset
                sender_role = SenderRole.USER if i % 2 == 0 else SenderRole.ASSISTANT

                message = ChatMessage(
                    id=str(uuid.uuid4()),
                    conversation_id=conversation_id_3,
                    timestamp=msg_time,
                    content=f"会话3消息 - 第{hour + 1}小时，消息 #{i + 1}：讨论项目进展",
                    sender_name="王五" if sender_role == SenderRole.USER else "项目经理",
                    sender_role=sender_role,
                    type=MessageType.TEXT,
                )
                session.add(message)
                messages_3.append(message)

        conversation_3.messages_count = len(messages_3)
        conversation_3.last_message_time = messages_3[-1].timestamp

        print(f"✓ 创建会话3: {len(messages_3)} 条消息")

        # 提交所有数据
        await session.commit()

        print("\n" + "=" * 80)
        print("测试数据生成完成")
        print("=" * 80)

        # 返回测试配置
        return {
            "source_config_id": source_config_id,
            "conversations": [
                {
                    "id": conversation_id_1,
                    "title": conversation_1.title,
                    "start_time": base_time_1.isoformat(),
                    "end_time": messages_1[-1].timestamp.isoformat(),
                    "interval_minutes": 60,
                    "max_tokens": 8000,
                },
                {
                    "id": conversation_id_2,
                    "title": conversation_2.title,
                    "start_time": base_time_2.isoformat(),
                    "end_time": messages_2[-1].timestamp.isoformat(),
                    "interval_minutes": 60,
                    "max_tokens": 2000,  # 较小的 token 限制，触发切分
                },
                {
                    "id": conversation_id_3,
                    "title": conversation_3.title,
                    "start_time": base_time_3.isoformat(),
                    "end_time": messages_3[-1].timestamp.isoformat(),
                    "interval_minutes": 30,  # 30分钟间隔
                    "max_tokens": 8000,
                },
            ],
        }


# ==============================================================================
# 测试部分
# ==============================================================================

async def test_conversation_loader(
    conversation_id: str,
    source_config_id: str,
    start_time: str = None,
    end_time: str = None,
    interval_minutes: int = 60,
    max_tokens: int = 8000,
):
    """测试会话加载器"""

    print(f"\n{'=' * 80}")
    print(f"测试会话加载: {conversation_id[:8]}...")
    print(f"{'=' * 80}")

    # 创建加载器
    loader = ConversationLoader(max_tokens=max_tokens)

    # 创建配置
    config = ConversationLoadConfig(
        source_config_id=source_config_id,
        conversation_id=conversation_id,
        start_time=start_time,
        end_time=end_time,
        interval_minutes=interval_minutes,
        max_tokens=max_tokens,
        auto_vector=False,  # 暂时不索引到 ES
    )

    try:
        # 加载会话
        print("开始加载会话...")
        result_conversation_id = await loader.load(config)
        print(f"✓ 会话加载成功: {result_conversation_id[:8]}...\n")

        # 查询生成的 SourceChunk
        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = (
                select(SourceChunk)
                .where(
                    SourceChunk.source_id == result_conversation_id,
                    SourceChunk.source_type == "CHAT",
                )
                .order_by(SourceChunk.rank)
            )
            result = await session.execute(stmt)
            chunks = result.scalars().all()

            print(f"生成的 SourceChunk 数量: {len(chunks)}\n")

            for i, chunk in enumerate(chunks, 1):
                print(f"Chunk #{i}: {chunk.heading}")
                print(f"  ID: {chunk.id[:8]}...")
                print(f"  Rank: {chunk.rank}")
                print(f"  Content Length: {chunk.chunk_length} 字符")
                print(f"  References: {len(chunk.references)} 条消息")
                print()

        return {
            "conversation_id": result_conversation_id,
            "chunk_count": len(chunks),
            "chunks": chunks,
        }

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def run_all_tests(test_config: dict):
    """运行所有测试场景"""

    print("\n" + "=" * 80)
    print("开始运行测试套件")
    print("=" * 80)

    source_config_id = test_config["source_config_id"]
    results = []

    for i, conv in enumerate(test_config["conversations"], 1):
        print(f"\n[{i}/{len(test_config['conversations'])}] 测试: {conv['title']}")
        print("-" * 80)

        result = await test_conversation_loader(
            conversation_id=conv["id"],
            source_config_id=source_config_id,
            start_time=conv.get("start_time"),
            end_time=conv.get("end_time"),
            interval_minutes=conv["interval_minutes"],
            max_tokens=conv["max_tokens"],
        )

        if result:
            results.append({
                "title": conv["title"],
                "conversation_id": conv["id"],
                "chunk_count": result["chunk_count"],
            })

    # 打印测试摘要
    print("\n" + "=" * 80)
    print("测试完成摘要")
    print("=" * 80)
    for r in results:
        print(f"✓ {r['title']}")
        print(f"  会话 ID: {r['conversation_id'][:8]}...")
        print(f"  生成 Chunk 数量: {r['chunk_count']}")
        print()

    return results


# ==============================================================================
# 清理部分
# ==============================================================================

async def cleanup_test_data(test_config: dict):
    """清理测试数据"""

    print("\n" + "=" * 80)
    print("清理测试数据")
    print("=" * 80)

    source_config_id = test_config["source_config_id"]
    conversation_ids = [conv["id"] for conv in test_config["conversations"]]

    session_factory = get_session_factory()
    async with session_factory() as session:
        # 删除 SourceChunk
        result = await session.execute(
            select(SourceChunk).where(SourceChunk.source_id.in_(conversation_ids))
        )
        chunks = result.scalars().all()
        for chunk in chunks:
            await session.delete(chunk)
        print(f"✓ 删除 {len(chunks)} 个 SourceChunk")

        # 删除 ChatMessage
        result = await session.execute(
            select(ChatMessage).where(ChatMessage.conversation_id.in_(conversation_ids))
        )
        messages = result.scalars().all()
        for message in messages:
            await session.delete(message)
        print(f"✓ 删除 {len(messages)} 条 ChatMessage")

        # 删除 ChatConversation
        result = await session.execute(
            select(ChatConversation).where(ChatConversation.id.in_(conversation_ids))
        )
        conversations = result.scalars().all()
        for conv in conversations:
            await session.delete(conv)
        print(f"✓ 删除 {len(conversations)} 个 ChatConversation")

        # 删除 SourceConfig
        result = await session.execute(
            select(SourceConfig).where(SourceConfig.id == source_config_id)
        )
        source_config = result.scalar_one_or_none()
        if source_config:
            await session.delete(source_config)
            print(f"✓ 删除 SourceConfig: {source_config_id}")

        await session.commit()

    print("\n✓ 测试数据清理完成")


# ==============================================================================
# 主流程
# ==============================================================================

async def run_complete_pipeline():
    """运行完整的测试流程：生成数据 → 运行测试 → 询问清理"""

    print("\n" + "=" * 80)
    print("ConversationLoader 完整测试流程")
    print("=" * 80)

    try:
        # 步骤1: 生成测试数据
        test_config = await generate_test_conversations()

        # 步骤2: 运行测试
        await run_all_tests(test_config)

        # 步骤3: 询问是否清理数据
        print("\n" + "=" * 80)
        print("测试流程完成")
        print("=" * 80)

        choice = input("\n是否删除测试数据? (y/N): ").strip().lower()
        if choice == 'y':
            await cleanup_test_data(test_config)
        else:
            print("\n测试数据已保留在数据库中")
            print(f"信息源 ID: {test_config['source_config_id']}")
            print("会话 ID:")
            for conv in test_config["conversations"]:
                print(f"  - {conv['id']}")

    except Exception as e:
        print(f"\n✗ 流程执行失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_complete_pipeline())
