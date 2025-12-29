"""
搜索模式演示

展示如何使用两种不同的搜索模式：
1. 快速模式 - 跳过LLM属性抽取，快速召回
2. 普通模式 - 使用LLM属性抽取，精确搜索
"""

import asyncio
import logging
import warnings

# 抑制异步资源未关闭的警告
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=ResourceWarning)

# 可选：关闭SQLAlchemy SQL日志
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

from dataflow.core.ai.factory import create_llm_client
from dataflow.core.prompt.manager import PromptManager
from dataflow.modules.search import EventSearcher, SearchConfig, SearchMode


# ========== 统一配置 ==========
# 修改这里的参数来测试不同场景

# 数据源配置
SOURCE_CONFIG_ID = "test-search-mode-02"  # 修改为你的source_config_id
ARTICLE_ID = None  # 可选：限制在特定文章内搜索

# 查询配置（所有模式使用相同query，便于对比效果）
# QUERY = "查找关于人工智能的重要事项"  # 修改为你想测试的query
QUERY = "脑机接口"  # 修改为你想测试的query

# 搜索参数
TOP_K = 10  # 返回结果数量（1-100）
THRESHOLD = 0.7  # 相似度阈值（0.0-1.0）

# 背景信息（可选）
BACKGROUND = "这是一个科技领域的文档集合"

# 搜索模式专用参数（用于展示参数调节能力）
KEY_SIMILARITY_THRESHOLD = 0.7  # Key语义相似度阈值
EVENT_SIMILARITY_THRESHOLD = 0.6  # Event语义相似度阈值
MAX_KEYS = 20  # 最大Key数量
MAX_EVENTS = 50  # 最大Event数量
FINAL_KEY_THRESHOLD = 0.5  # 最终Key权重阈值
TOP_N_KEYS = 10  # 返回Top-N重要Key
VECTOR_K = 10  # 向量搜索返回数量

# 展示配置
DISPLAY_MODE = "detailed"  # simple: 只显示标题 | detailed: 显示标题+摘要+内容预览
SHOW_ENTITIES = True  # 是否显示关联实体

# ==============================


def display_results(results, mode_name="搜索", extra_info=None):
    """
    统一的结果展示方法
    
    Args:
        results: 搜索结果列表
        mode_name: 模式名称（用于显示）
        extra_info: 额外信息（如检索策略说明）
    """
    print(f"\n✅ {mode_name}完成，找到 {len(results)} 个匹配事项")
    
    # 显示额外信息
    if extra_info:
        print(extra_info)
    
    # 显示结果
    if not results:
        print("   无匹配结果")
        return
    
    print()  # 空行
    
    for i, event in enumerate(results, 1):
        if DISPLAY_MODE == "simple":
            # 简单模式：只显示标题
            print(f"{i}. {event.title}")
            
        elif DISPLAY_MODE == "detailed":
            # 详细模式：显示标题+摘要+内容预览
            print(f"{i}. {event.title}")
            if event.summary:
                summary = event.summary[:150] + "..." if len(event.summary) > 150 else event.summary
                print(f"   摘要: {summary}")
            if event.content and DISPLAY_MODE == "detailed":
                content_preview = event.content[:200] + "..." if len(event.content) > 200 else event.content
                print(f"   内容: {content_preview}")
            
            # 显示关联实体
            if SHOW_ENTITIES and hasattr(event, 'event_associations'):
                entities = [
                    f"{assoc.entity.type}:{assoc.entity.name}" 
                    for assoc in event.event_associations 
                    if assoc.entity is not None  # 过滤None
                ]
                if entities:
                    print(f"   实体: {', '.join(entities[:5])}")  # 最多显示5个
            print()  # 事项之间空行


async def demo_fast_search():
    """演示快速模式搜索"""
    print("\n" + "=" * 60)
    print("快速模式搜索演示")
    print("=" * 60)

    # 初始化
    llm_client = create_llm_client()
    prompt_manager = PromptManager()
    searcher = EventSearcher(llm_client, prompt_manager)

    # 配置搜索（使用统一配置）
    config = SearchConfig(
        query=QUERY,
        source_config_id=SOURCE_CONFIG_ID,
        article_id=ARTICLE_ID,
        mode=SearchMode.FAST,
        use_fast_mode=True,  # 跳过LLM属性抽取
        top_k=TOP_K,
        threshold=THRESHOLD,
        background=BACKGROUND,
    )

    # 执行搜索
    results = await searcher.search(config)

    # 使用统一展示方法
    extra_info = "检索策略：跳过LLM属性抽取，快速向量召回"
    display_results(results, "快速搜索", extra_info)


async def demo_normal_search():
    """演示普通模式搜索"""
    print("\n" + "=" * 60)
    print("普通模式搜索演示")
    print("=" * 60)

    # 初始化
    llm_client = create_llm_client()
    prompt_manager = PromptManager()
    searcher = EventSearcher(llm_client, prompt_manager)

    # 配置搜索（使用统一配置）
    config = SearchConfig(
        query=QUERY,
        source_config_id=SOURCE_CONFIG_ID,
        article_id=ARTICLE_ID,
        mode=SearchMode.NORMAL,
        use_fast_mode=False,  # 使用LLM属性抽取
        top_k=TOP_K,
        threshold=THRESHOLD,

        # 搜索参数
        key_similarity_threshold=KEY_SIMILARITY_THRESHOLD,
        event_similarity_threshold=EVENT_SIMILARITY_THRESHOLD,
        max_keys=MAX_KEYS,
        max_events=MAX_EVENTS,
        final_key_threshold=FINAL_KEY_THRESHOLD,
        top_n_keys=TOP_N_KEYS,
        vector_k=VECTOR_K,
    )

    # 执行搜索
    results = await searcher.search(config)

    # 使用统一展示方法
    extra_info = "检索策略：LLM属性抽取 + 精确搜索"
    display_results(results, "普通搜索", extra_info)


async def demo_comparison():
    """对比两种搜索模式"""
    print("\n" + "=" * 60)
    print("搜索模式对比")
    print("=" * 60)

    # 初始化
    llm_client = create_llm_client()
    prompt_manager = PromptManager()
    searcher = EventSearcher(llm_client, prompt_manager)

    modes = [SearchMode.FAST, SearchMode.NORMAL]

    print(f"\n查询: {QUERY}")
    print(f"信息源: {SOURCE_CONFIG_ID}")
    print(f"参数: top_k={TOP_K}, threshold={THRESHOLD}")
    print("\n结果对比:\n")

    for mode in modes:
        config = SearchConfig(
            query=QUERY,
            source_config_id=SOURCE_CONFIG_ID,
            article_id=ARTICLE_ID,
            mode=mode,
            use_fast_mode=(mode == SearchMode.FAST),
            top_k=TOP_K,
            threshold=THRESHOLD,
        )

        results = await searcher.search(config)

        if mode == SearchMode.FAST:
            status = "✅ 可用（快速召回）"
        else:
            status = "✅ 可用（精确搜索）"

        print(f"{mode.value.upper():8s} 模式: {status:18s} - 返回 {len(results):2d} 个结果")


async def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("DataFlow 搜索模式演示")
    print("=" * 60)

    try:

        # 1. 快速模式搜索
        await demo_fast_search()

        # 2. 普通模式搜索
        await demo_normal_search()

        # 3. 对比两种模式
        await demo_comparison()

        print("\n" + "=" * 60)
        print("演示完成")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 演示过程出错: {e}")
        import traceback

        traceback.print_exc()
        
    finally:
        # 清理所有异步资源，避免警告
        try:
            # 关闭数据库引擎
            from dataflow.db.base import get_engine
            engine = get_engine()
            if engine:
                await engine.dispose()
            
            # 关闭ES客户端
            from dataflow.core.storage.elasticsearch import close_es_client
            await close_es_client()
            
            # 关闭Redis客户端
            from dataflow.core.storage.redis import close_redis_client
            await close_redis_client()
            
        except Exception:
            pass  # 忽略清理错误


if __name__ == "__main__":
    asyncio.run(main())

