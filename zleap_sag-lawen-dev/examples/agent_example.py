"""
Agent 使用示例

展示 Agent v2.0 的各种使用方式
"""

import asyncio
from dataflow.core.agent import SummarizerAgent


async def example_1_basic():
    """示例 1: 最基础的使用"""
    print("=" * 60)
    print("示例 1: 基础使用")
    print("=" * 60)
    
    # 创建 Agent（零参数）
    agent = SummarizerAgent()
    
    # 添加数据
    agent.add_database(
        data_type="financial_reports",
        items=[
            {
                "id": "q3-2024",
                "summary": "2024年Q3财报",
                "content": "总收入1.2亿元，同比增长15%；净利润2千万元，同比增长20%。",
                "quarter": "Q3",
                "year": 2024
            }
        ],
        description="财务报告"
    )
    
    # 运行查询
    result = await agent.run("总结Q3财报的关键数据")
    print("\n查询:", "总结Q3财报的关键数据")
    print("回答:", result["content"])
    
    return agent


async def example_2_with_initial_data():
    """示例 2: 初始化时注入数据"""
    print("\n" + "=" * 60)
    print("示例 2: 初始化时注入数据")
    print("=" * 60)
    
    # 初始化时注入所有数据
    agent = SummarizerAgent(
        timezone="Asia/Shanghai",
        database=[
            {
                "type": "financial_reports",
                "description": "财务报告",
                "list": [
                    {"id": "q3", "summary": "Q3财报", "content": "总收入1.2亿元..."}
                ]
            }
        ],
        memory=[
            {
                "type": "user_preferences",
                "description": "用户偏好",
                "list": [
                    {"id": "pref1", "summary": "偏好表格", "content": "用户喜欢表格"}
                ]
            }
        ],
        output={"stream": False, "format": "markdown"}
    )
    
    # 直接运行，无需再添加数据
    result = await agent.run("根据用户偏好，生成Q3财报总结")
    print("\n✅ 已使用初始数据和用户偏好")
    
    return agent


async def example_3_stream():
    """示例 3: 流式输出"""
    print("\n" + "=" * 60)
    print("示例 3: 流式输出")
    print("=" * 60)
    
    agent = SummarizerAgent()
    agent.add_database(
        data_type="reports",
        items=[{"id": "1", "summary": "市场报告", "content": "市场份额增长..."}]
    )
    
    print("\n开始流式输出:")
    print("-" * 60)
    
    # 流式输出
    async for chunk in agent.run("详细分析市场报告", stream=True, think=True):
        if chunk["reasoning"]:
            print(f"\n💭 思考: {chunk['reasoning']}")
        if chunk["content"]:
            print(chunk["content"], end="", flush=True)
    
    print("\n" + "-" * 60)


async def example_4_multi_partition():
    """示例 4: 多分区联合查询"""
    print("\n" + "=" * 60)
    print("示例 4: 多分区联合查询")
    print("=" * 60)
    
    agent = SummarizerAgent()
    
    # 添加多个数据源
    agent.add_database(
        data_type="sales",
        items=[{"id": "s1", "summary": "销售数据", "content": "月销售额100万"}]
    )
    
    agent.add_database(
        data_type="users",
        items=[{"id": "u1", "summary": "用户数据", "content": "活跃用户1万"}]
    )
    
    agent.add_database(
        data_type="feedback",
        items=[{"id": "f1", "summary": "用户反馈", "content": "产品好评率90%"}]
    )
    
    # Agent 会自动在所有分区中查找相关数据
    result = await agent.run("综合销售、用户和反馈数据，评估产品表现")
    print("\n✅ Agent 自动联合查询了3个分区")
    print("数据库摘要:", agent.get_database_summary())


async def example_5_todo():
    """示例 5: 待办任务管理"""
    print("\n" + "=" * 60)
    print("示例 5: 待办任务管理")
    print("=" * 60)
    
    agent = SummarizerAgent()
    
    # 添加待办任务
    agent.add_todo(
        task_id="task-001",
        description="分析Q3财报",
        status="pending",
        priority=8,
        deadline="2025-11-05"
    )
    
    agent.add_todo(
        task_id="task-002",
        description="生成分析报告",
        status="pending",
        priority=7
    )
    
    print("\n待办任务摘要:", agent.get_todo_summary())
    
    # 更新任务状态
    agent.update_todo_status("task-001", "completed")
    
    print("更新后:", agent.get_todo_summary())


async def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("🚀 Agent v2.0 使用示例")
    print("=" * 60)
    
    try:
        # 示例 1: 基础使用
        # await example_1_basic()
        
        # 示例 2: 初始化注入
        # await example_2_with_initial_data()
        
        # 示例 3: 流式输出
        # await example_3_stream()  # 需要 LLM API
        
        # 示例 4: 多分区查询
        # await example_4_multi_partition()
        
        # 示例 5: 待办管理
        # await example_5_todo()
        
        print("\n" + "=" * 60)
        print("✅ 所有示例完成！")
        print("=" * 60)
        
        print("\n📝 核心要点:")
        print("  1. 初始化：agent = SummarizerAgent()")
        print("  2. 添加数据：agent.add_database(data_type=..., items=[...])")
        print("  3. 执行：result = await agent.run('查询')")
        print("  4. 参数名：data_type, task_id, output_format")
        
    except Exception as e:
        print(f"\n⚠️  示例需要配置 LLM API: {e}")


if __name__ == "__main__":
    # 注意：需要配置有效的 LLM API 才能运行
    print("\n⚠️  运行此示例需要配置有效的 LLM API")
    print("请设置环境变量：LLM_API_KEY, LLM_MODEL 等")
    
    # asyncio.run(main())
