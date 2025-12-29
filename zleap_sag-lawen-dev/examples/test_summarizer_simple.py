"""
简单测试 SummarizerAgent

使用虚拟文档事项测试总结功能
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("🚀 测试 SummarizerAgent")
    print("=" * 70)
    
    try:
        from dataflow.core.agent import SummarizerAgent
        
        # 虚拟事项
        events = [
            {
                "id": "doc-001",
                "summary": "2024年Q3财务报告",
                "content": "2024年第三季度，公司总收入达到1.2亿元人民币，同比增长15%。净利润为2千万元，同比增长20%。主要增长来自新产品线的推出和市场份额的扩大。",
                "date": "2024-10-31",
                "category": "financial",
            },
            {
                "id": "doc-002",
                "summary": "市场份额分析报告",
                "content": "根据最新市场调研数据，公司产品在目标市场的份额已达到30%，较上季度提升5个百分点。主要竞争对手份额为25%和20%。",
                "date": "2024-10-30",
                "category": "market",
            },
            {
                "id": "doc-003",
                "summary": "用户满意度调查",
                "content": "2024年Q3用户满意度调查显示，整体满意度达到90%，较上季度提升3个百分点。用户最满意的功能是智能推荐（95%）和界面设计（92%）。",
                "date": "2024-10-29",
                "category": "user_feedback",
            },
        ]
        
        # 创建 Agent（带初始事项）
        print("\n1. 创建 SummarizerAgent")
        agent = SummarizerAgent(events=events)
        print(f"   ✓ 已加载 {len(events)} 条文档事项")
        
        # 查看数据库状态
        print("\n2. 数据库状态")
        db_summary = agent.get_database_summary()
        print(f"   分区数量: {db_summary['total_partitions']}")
        for partition in db_summary['partitions']:
            print(f"   - {partition['type']}: {partition['count']} 条（{partition['description']}）")
        
        # 查看待办任务
        print("\n3. 待办任务")
        todo_summary = agent.get_todo_summary()
        print(f"   任务数量: {todo_summary['total_tasks']}")
        if agent.todo:
            task = agent.todo[0]
            print(f"   任务ID: {task['id']}")
            print(f"   描述: {task['description']}")
        
        # 验证事项序号
        print("\n4. 事项序号验证")
        doc_partition = [p for p in agent.database if p['type'] == '文档事项'][0]
        for item in doc_partition['list'][:3]:
            print(f"   [{item['order']}] {item['summary']}")
        
        # 执行查询
        print("\n5. 执行查询（流式输出）")
        print("-" * 70)
        
        # query = "苹果发布会是什么时候？"
        query = "总结Q3的业务亮点"
        print(f"查询: {query}\n")
        
        # 流式输出
        async for chunk in agent.run(query):
            if chunk.get("reasoning"):
                # print(f"💭 思考: {chunk['reasoning']}")
                print(chunk["reasoning"], end="", flush=True)
            if chunk.get("content"):
                print(chunk["content"], end="", flush=True)
        
        print("\n" + "-" * 70)
        
        print("\n" + "=" * 70)
        print("✅ 测试完成！")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        
        print("\n💡 可能的原因:")
        print("  1. 未配置 LLM API（检查 .env 文件）")
        print("  2. API 密钥无效")
        print("  3. 网络连接问题")


if __name__ == "__main__":
    asyncio.run(main())

